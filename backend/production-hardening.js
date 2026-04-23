// Video Kitchen v0.8.0 — Production Hardening
// Error recovery, progress streaming, output gallery, cleanup

const EventEmitter = require('events');
const path = require('path');
const fs = require('fs');
const db = require('./db');

// Event emitter for job progress updates
const progressEmitter = new EventEmitter();

// Configuration
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 5000;
const TEMP_FILE_MAX_AGE_HOURS = 24;
const CLEANUP_INTERVAL_MS = 3600000; // 1 hour

/**
 * Run a job with retry logic
 */
async function runWithRetry(jobId, runFn) {
  let lastError = null;
  
  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      console.log(`[RETRY] Job ${jobId} attempt ${attempt}/${MAX_RETRIES}`);
      
      // Update job with attempt info
      await db.updateJob(jobId, {
        retry_attempt: attempt,
        status: attempt === 1 ? 'running' : 'retrying'
      });
      
      const result = await runFn();
      
      // Success - clear any previous error
      return result;
    } catch (err) {
      lastError = err;
      console.error(`[RETRY] Job ${jobId} attempt ${attempt} failed: ${err.message}`);
      
      if (attempt < MAX_RETRIES) {
        // Wait before retry
        await sleep(RETRY_DELAY_MS * attempt); // Exponential backoff
      }
    }
  }
  
  // All retries exhausted
  throw new Error(`Job ${jobId} failed after ${MAX_RETRIES} attempts: ${lastError.message}`);
}

/**
 * Report job progress
 */
async function reportProgress(jobId, stage, progress, message) {
  const update = {
    job_id: jobId,
    stage,
    progress: Math.min(100, Math.max(0, progress)),
    message,
    timestamp: new Date().toISOString()
  };
  
  // Save to database
  await db.updateJob(jobId, {
    progress: update.progress,
    current_stage: stage,
    status_message: message
  });
  
  // Emit for SSE/WebSocket
  progressEmitter.emit('progress', update);
  
  console.log(`[PROGRESS] Job ${jobId}: ${stage} ${progress}% - ${message}`);
}

/**
 * Generate thumbnail for output video
 */
async function generateThumbnail(videoPath, outputDir) {
  const { spawn } = require('child_process');
  const filename = path.basename(videoPath, path.extname(videoPath)) + '_thumb.jpg';
  const thumbPath = path.join(outputDir, filename);
  
  return new Promise((resolve, reject) => {
    const ffmpeg = spawn('ffmpeg', [
      '-i', videoPath,
      '-ss', '00:00:01',
      '-vframes', '1',
      '-vf', 'scale=320:-1',
      '-y',
      thumbPath
    ]);
    
    ffmpeg.on('close', (code) => {
      if (code === 0 && fs.existsSync(thumbPath)) {
        resolve(thumbPath);
      } else {
        resolve(null); // Don't fail if thumbnail generation fails
      }
    });
    
    ffmpeg.on('error', () => resolve(null));
  });
}

/**
 * Generate preview GIF for output
 */
async function generatePreviewGif(videoPath, outputDir) {
  const { spawn } = require('child_process');
  const filename = path.basename(videoPath, path.extname(videoPath)) + '_preview.gif';
  const gifPath = path.join(outputDir, filename);
  
  return new Promise((resolve, reject) => {
    const ffmpeg = spawn('ffmpeg', [
      '-i', videoPath,
      '-ss', '00:00:00',
      '-t', '3',
      '-vf', 'fps=10,scale=320:-1:flags=lanczos',
      '-y',
      gifPath
    ]);
    
    ffmpeg.on('close', (code) => {
      if (code === 0 && fs.existsSync(gifPath)) {
        resolve(gifPath);
      } else {
        resolve(null);
      }
    });
    
    ffmpeg.on('error', () => resolve(null));
  });
}

/**
 * Clean up temporary files for a project
 */
async function cleanupProject(projectId, options = {}) {
  const PROJECTS_DIR = process.env.PROJECTS_BASE_DIR || path.join(__dirname, '..', 'projects');
  const projectDir = path.join(PROJECTS_DIR, projectId);
  
  if (!fs.existsSync(projectDir)) {
    return { cleaned: false, reason: 'Project directory not found' };
  }
  
  const cleaned = [];
  const kept = [];
  
  // Clean up temp directories
  const tempDirs = ['temp', 'chunks', '.tmp'];
  for (const dir of tempDirs) {
    const dirPath = path.join(projectDir, dir);
    if (fs.existsSync(dirPath)) {
      fs.rmSync(dirPath, { recursive: true });
      cleaned.push(dir);
    }
  }
  
  // Clean up intermediate files (but keep outputs)
  const intermediateExts = ['.tmp', '.part', '.download'];
  const files = fs.readdirSync(projectDir);
  
  for (const file of files) {
    const ext = path.extname(file);
    const isIntermediate = intermediateExts.includes(ext);
    const isInOutputs = file.startsWith('output_') || file.includes('_final');
    
    if (isIntermediate && !isInOutputs) {
      fs.unlinkSync(path.join(projectDir, file));
      cleaned.push(file);
    } else {
      kept.push(file);
    }
  }
  
  // Optionally clean up source video (if not needed)
  if (options.removeSource) {
    const sourceFiles = files.filter(f => 
      f.includes('source') || f.includes('input') || f.endsWith('.mp4') && !f.includes('output')
    );
    for (const file of sourceFiles) {
      const filePath = path.join(projectDir, file);
      if (fs.existsSync(filePath)) {
        fs.unlinkSync(filePath);
        cleaned.push(file);
      }
    }
  }
  
  return {
    cleaned: true,
    project_id: projectId,
    items_cleaned: cleaned,
    items_kept: kept,
    space_saved: 'calculated'
  };
}

/**
 * Clean up old temp files across all projects
 */
async function cleanupOldTempFiles() {
  const PROJECTS_DIR = process.env.PROJECTS_BASE_DIR || path.join(__dirname, '..', 'projects');
  
  if (!fs.existsSync(PROJECTS_DIR)) {
    return { cleaned: 0 };
  }
  
  const now = Date.now();
  const maxAgeMs = TEMP_FILE_MAX_AGE_HOURS * 3600000;
  let cleaned = 0;
  
  const projects = fs.readdirSync(PROJECTS_DIR);
  
  for (const projectId of projects) {
    const projectDir = path.join(PROJECTS_DIR, projectId);
    if (!fs.statSync(projectDir).isDirectory()) continue;
    
    // Check temp directories
    const tempDirs = ['temp', 'chunks', '.tmp'];
    for (const dir of tempDirs) {
      const dirPath = path.join(projectDir, dir);
      if (fs.existsSync(dirPath)) {
        const stats = fs.statSync(dirPath);
        if (now - stats.mtimeMs > maxAgeMs) {
          fs.rmSync(dirPath, { recursive: true });
          cleaned++;
        }
      }
    }
    
    // Check individual temp files
    const files = fs.readdirSync(projectDir);
    for (const file of files) {
      if (file.endsWith('.tmp') || file.endsWith('.part')) {
        const filePath = path.join(projectDir, file);
        const stats = fs.statSync(filePath);
        if (now - stats.mtimeMs > maxAgeMs) {
          fs.unlinkSync(filePath);
          cleaned++;
        }
      }
    }
  }
  
  return { cleaned, max_age_hours: TEMP_FILE_MAX_AGE_HOURS };
}

/**
 * Get output gallery for a project
 */
async function getOutputGallery(projectId) {
  const outputs = await db.listOutputs(projectId);
  const PROJECTS_DIR = process.env.PROJECTS_BASE_DIR || path.join(__dirname, '..', 'projects');
  const projectDir = path.join(PROJECTS_DIR, projectId);
  
  const gallery = [];
  
  for (const output of outputs) {
    const outputPath = output.file_path;
    const thumbPath = path.join(projectDir, path.basename(outputPath, path.extname(outputPath)) + '_thumb.jpg');
    const previewPath = path.join(projectDir, path.basename(outputPath, path.extname(outputPath)) + '_preview.gif');
    
    // Generate thumbnails if they don't exist
    if (!fs.existsSync(thumbPath) && fs.existsSync(outputPath)) {
      await generateThumbnail(outputPath, projectDir);
    }
    
    if (!fs.existsSync(previewPath) && fs.existsSync(outputPath)) {
      await generatePreviewGif(outputPath, projectDir);
    }
    
    gallery.push({
      id: output.id,
      filename: output.filename,
      file_size: output.file_size,
      recipe_id: output.recipe_id,
      created_at: output.created_at,
      thumbnail_url: fs.existsSync(thumbPath) ? `/projects/${projectId}/outputs/${path.basename(thumbPath)}` : null,
      preview_url: fs.existsSync(previewPath) ? `/projects/${projectId}/outputs/${path.basename(previewPath)}` : null,
      download_url: `/api/outputs/${output.id}/download?project_id=${projectId}`
    });
  }
  
  return gallery;
}

/**
 * Utility: sleep
 */
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Start cleanup cron
setInterval(cleanupOldTempFiles, CLEANUP_INTERVAL_MS);

module.exports = {
  runWithRetry,
  reportProgress,
  generateThumbnail,
  generatePreviewGif,
  cleanupProject,
  cleanupOldTempFiles,
  getOutputGallery,
  progressEmitter,
  MAX_RETRIES,
  RETRY_DELAY_MS
};
