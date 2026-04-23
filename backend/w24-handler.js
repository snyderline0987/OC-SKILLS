// Video Kitchen v0.8.0 — W24 Source Handler
// Handles W24.at news URL processing and video download

const axios = require('axios');
const path = require('path');
const fs = require('fs');
const { v4: uuidv4 } = require('uuid');

const W24_CDN_BASE = 'https://ms01.w24.at';
const DOWNLOAD_TIMEOUT = 30000; // 30 seconds

/**
 * Parse a W24 URL and extract metadata
 * Supports formats:
 * - https://w24.at/News/2026-04-23/Some-Topic-123
 * - https://www.w24.at/News/2026-04-23/Some-Topic-123
 * - https://w24.at/Video/12345
 */
function parseW24Url(url) {
  try {
    const parsed = new URL(url);
    const pathParts = parsed.pathname.split('/').filter(Boolean);
    
    // Check domain
    if (!parsed.hostname.includes('w24.at')) {
      return { valid: false, error: 'Not a W24 domain' };
    }

    let info = {
      valid: true,
      url,
      domain: parsed.hostname,
      path: parsed.pathname
    };

    // Parse /News/YYYY-MM-DD/Topic-Name-ID format
    if (pathParts[0] === 'News' && pathParts.length >= 3) {
      const dateMatch = pathParts[1].match(/(\d{4})-(\d{2})-(\d{2})/);
      if (dateMatch) {
        info.date = `${dateMatch[1]}-${dateMatch[2]}-${dateMatch[3]}`;
        info.topic = pathParts[2].replace(/-/g, ' ').replace(/\d+$/, '').trim();
        info.segment = pathParts[2];
      }
    }

    // Parse /Video/ID format
    if (pathParts[0] === 'Video' && pathParts[1]) {
      info.video_id = pathParts[1];
    }

    // Extract any ID from end of path
    const idMatch = parsed.pathname.match(/(\d+)$/);
    if (idMatch) {
      info.content_id = idMatch[1];
    }

    return info;
  } catch (err) {
    return { valid: false, error: err.message };
  }
}

/**
 * Fetch W24 page and extract video URL from meta tags
 */
async function extractVideoUrl(w24Url) {
  try {
    const response = await axios.get(w24Url, {
      timeout: DOWNLOAD_TIMEOUT,
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; VideoKitchen/0.8.0)'
      }
    });

    const html = response.data;
    
    // Look for video URL in meta tags
    const ogVideoMatch = html.match(/<meta[^>]+property="og:video"[^>]+content="([^"]+)"/i);
    if (ogVideoMatch) {
      return { success: true, video_url: ogVideoMatch[1] };
    }

    // Look for video URL in JSON-LD
    const jsonLdMatch = html.match(/<script type="application\/ld\+json">([^<]+)<\/script>/i);
    if (jsonLdMatch) {
      try {
        const jsonLd = JSON.parse(jsonLdMatch[1]);
        if (jsonLd.video && jsonLd.video.contentUrl) {
          return { success: true, video_url: jsonLd.video.contentUrl };
        }
      } catch (e) {
        // Ignore JSON parse errors
      }
    }

    // Look for mp4 in page
    const mp4Match = html.match(/(https?:\/\/[^"\s]+\.mp4[^"\s]*)/i);
    if (mp4Match) {
      return { success: true, video_url: mp4Match[1] };
    }

    return { success: false, error: 'No video URL found in page' };
  } catch (err) {
    return { success: false, error: `Failed to fetch W24 page: ${err.message}` };
  }
}

/**
 * Download video from W24 CDN
 */
async function downloadW24Video(w24Url, outputDir) {
  const info = parseW24Url(w24Url);
  if (!info.valid) {
    return { success: false, error: info.error };
  }

  // First, try to extract direct video URL
  const videoExtract = await extractVideoUrl(w24Url);
  if (!videoExtract.success) {
    return { success: false, error: videoExtract.error };
  }

  const videoUrl = videoExtract.video_url;
  const filename = `w24_${info.content_id || info.video_id || uuidv4().slice(0, 8)}.mp4`;
  const outputPath = path.join(outputDir, filename);

  // Ensure output directory exists
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  try {
    const response = await axios({
      method: 'GET',
      url: videoUrl,
      responseType: 'stream',
      timeout: 120000, // 2 minutes for download
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; VideoKitchen/0.8.0)'
      }
    });

    const writer = fs.createWriteStream(outputPath);
    response.data.pipe(writer);

    await new Promise((resolve, reject) => {
      writer.on('finish', resolve);
      writer.on('error', reject);
    });

    const stats = fs.statSync(outputPath);
    
    return {
      success: true,
      file_path: outputPath,
      filename,
      file_size: stats.size,
      w24_info: info,
      video_url: videoUrl
    };
  } catch (err) {
    // Clean up partial download
    if (fs.existsSync(outputPath)) {
      fs.unlinkSync(outputPath);
    }
    return { success: false, error: `Download failed: ${err.message}` };
  }
}

/**
 * Get W24 video metadata
 */
async function getW24Metadata(w24Url) {
  const info = parseW24Url(w24Url);
  if (!info.valid) {
    return { success: false, error: info.error };
  }

  try {
    const response = await axios.get(w24Url, {
      timeout: DOWNLOAD_TIMEOUT,
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; VideoKitchen/0.8.0)'
      }
    });

    const html = response.data;
    const metadata = {
      ...info,
      title: null,
      description: null,
      thumbnail: null,
      duration: null
    };

    // Extract title
    const titleMatch = html.match(/<meta[^>]+property="og:title"[^>]+content="([^"]+)"/i);
    if (titleMatch) metadata.title = titleMatch[1];

    // Extract description
    const descMatch = html.match(/<meta[^>]+property="og:description"[^>]+content="([^"]+)"/i);
    if (descMatch) metadata.description = descMatch[1];

    // Extract thumbnail
    const thumbMatch = html.match(/<meta[^>]+property="og:image"[^>]+content="([^"]+)"/i);
    if (thumbMatch) metadata.thumbnail = thumbMatch[1];

    // Extract duration from JSON-LD
    const jsonLdMatch = html.match(/<script type="application\/ld\+json">([^<]+)<\/script>/i);
    if (jsonLdMatch) {
      try {
        const jsonLd = JSON.parse(jsonLdMatch[1]);
        if (jsonLd.video && jsonLd.video.duration) {
          metadata.duration = jsonLd.video.duration;
        }
      } catch (e) {
        // Ignore
      }
    }

    return { success: true, metadata };
  } catch (err) {
    return { success: false, error: err.message };
  }
}

module.exports = {
  parseW24Url,
  extractVideoUrl,
  downloadW24Video,
  getW24Metadata,
  W24_CDN_BASE
};
