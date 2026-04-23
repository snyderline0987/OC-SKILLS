# FFWD Trailer Kitchen v0.8.0 🍳

> *Agentic Video Highlight Platform — Phase 3: Agent Integration*

Video Kitchen v0.8.0 transforms video into highlights, teasers, and social clips using an AI-powered pipeline with full OpenClaw agent integration, W24 source handling, zai-vision MCP, and production hardening.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│              Video Kitchen v0.8.0 — Phase 3                        │
├─────────────────────────────────────────────────────────────────┤
│  OpenClaw Agent  │  Dashboard (HTML)  │  CLI (Python)            │
│     ↓            │         ↓          │      ↓                   │
│  Tool Registry   │   SSE/WebSocket    │  Kitchen Scripts         │
├─────────────────────────────────────────────────────────────────┤
│              Express REST API (Node.js)                          │
│  /tools  │  /projects  │  /jobs  │  /w24  │  /vision  │  /webhooks│
├─────────────────────────────────────────────────────────────────┤
│              SQLite Database                                     │
│  projects │ scenes │ jobs │ outputs │ recipes                   │
├─────────────────────────────────────────────────────────────────┤
│              Python Pipeline Engine                              │
│  prep → scoring → select → plate → season → qc                   │
├─────────────────────────────────────────────────────────────────┤
│              Integrations                                        │
│  W24 Handler │ zai-vision MCP │ Retry Logic │ Thumbnail Gallery  │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# 1. Clone & install Python deps
git clone https://github.com/snyderline0987/VideoKitchen.git
cd VideoKitchen
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Install backend
cd backend
npm install
node scripts/init-db.js
node scripts/seed-recipes.js

# 3. Start API server
node server.js
# → http://localhost:3001

# 4. Open dashboard
cd ../dashboard
open index.html
```

## OpenClaw Agent Integration

Agents can now call Video Kitchen directly as a tool:

```javascript
// Create a project
const result = await executeTool('video_kitchen_create_project', {
  title: 'My Teaser',
  source: '/path/to/video.mp4',
  recipe_id: 'social_teaser_w24'
});

// Run pipeline
await executeTool('video_kitchen_run_pipeline', {
  project_id: result.project_id,
  auto: true
});

// Check status
const status = await executeTool('video_kitchen_get_status', {
  project_id: result.project_id
});
```

## W24 Source Handler

Process W24 news URLs automatically:

```bash
curl -X POST http://localhost:3001/api/w24/parse \
  -H "Content-Type: application/json" \
  -d '{"url": "https://w24.at/News/2026-04-23/Some-Topic-123"}'

curl -X POST http://localhost:3001/api/tools/video_kitchen_process_w24 \
  -H "Content-Type: application/json" \
  -d '{"w24_url": "https://w24.at/News/2026-04-23/Some-Topic-123"}'
```

## zai-vision MCP Integration

Analyze videos with zai-vision:

```bash
curl -X POST http://localhost:3001/api/vision/analyze \
  -H "Content-Type: application/json" \
  -d '{"video_path": "/path/to/video.mp4"}'
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/tools` | GET | List agent tools |
| `/api/tools/:tool` | POST | Execute tool |
| `/api/projects` | GET/POST | List/Create projects |
| `/api/projects/:id` | GET/PATCH/DELETE | Project CRUD |
| `/api/projects/:id/gallery` | GET | Output gallery |
| `/api/jobs` | GET/POST | List/Create jobs |
| `/api/jobs/:id` | GET | Job status |
| `/api/jobs/:id/run` | POST | Execute job |
| `/api/jobs/:id/progress` | GET | SSE progress stream |
| `/api/outputs` | GET | List outputs |
| `/api/w24/parse` | POST | Parse W24 URL |
| `/api/w24/download` | POST | Download W24 video |
| `/api/w24/metadata` | POST | Get W24 metadata |
| `/api/vision/analyze` | POST | Analyze video |
| `/api/vision/feed-scoring` | POST | Feed into scoring |
| `/api/webhooks/job-complete` | POST | Webhook callback |

## Pipeline Stages

| Stage | Script | Description |
|-------|--------|-------------|
| **Prep** | `prep_station.py` | Scene detection, thumbnails, transcription |
| **Analyze** | `scoring.py` | AI scoring — visual, transcript, audio |
| **Select** | `kitchen.py --select` | Auto-select by recipe criteria |
| **Plate** | `plating.py` | MoviePy assembly, aspect ratio |
| **Season** | `seasoning.py` | VO generation, music, mixing |
| **QC** | `taste_test.py` | ffprobe validation, preview GIF |

## Recipes

| Recipe | Duration | Aspect | Use Case |
|--------|----------|--------|----------|
| `social_teaser_w24` | 20-30s | 9:16 | Instagram/TikTok teaser |
| `spicy_trailer` | 30-45s | 16:9 | YouTube trailer |
| `highlight_abendsendung` | 60-90s | 16:9 | Broadcast highlight |
| `bts_soup` | 45-60s | 1:1 | Behind the scenes |

## Docker

```bash
docker compose up -d
# → API on http://localhost:3001
```

## What's New in v0.8.0 (Phase 3)

### Sprint 6: OpenClaw Agent Tool Registration ✅
- Agent can trigger kitchen.py via API
- Return structured results (scores, clips, output paths)
- Webhook callbacks for long-running jobs

### Sprint 7: W24 Source Handler Integration ✅
- Auto-download video from W24 CDN (ms01.w24.at)
- Extract metadata (date, topic, segment)
- Create project automatically from URL

### Sprint 8: zai-vision MCP Integration ✅
- Connect zai-vision analyze_video to prep_station
- Auto-analyze uploaded videos for scene quality
- Feed analysis results into scoring engine
- Handle 8MB limit with chunking strategy

### Sprint 9: Production Hardening ✅
- Error recovery & retry logic (3 retries with backoff)
- Progress streaming (SSE) to dashboard
- Output gallery with preview thumbnails
- Cleanup of temp files after rendering
- Automatic thumbnail and preview GIF generation

## Requirements

- Python 3.11+
- Node.js 18+
- ffmpeg (system)
- OpenAI API key (for Whisper + LLM scoring)

## License

Proprietary — FFWD Media
