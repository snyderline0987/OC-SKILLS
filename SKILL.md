# Video Kitchen Skill — OpenClaw Agent Integration v0.8.0

## Description

Transform video into highlights, teasers, and social clips using an AI-powered pipeline. Video Kitchen provides a full REST API and web dashboard for agentic video processing.

## Usage

Agents can call Video Kitchen tools directly via the API:

```
POST /api/tools/video_kitchen_create_project
POST /api/tools/video_kitchen_run_pipeline
POST /api/tools/video_kitchen_get_status
POST /api/tools/video_kitchen_list_outputs
POST /api/tools/video_kitchen_process_w24
```

## Tools

### video_kitchen_create_project
Create a new video processing project.

**Parameters:**
- `title` (string, required): Project title
- `source` (string, required): Video file path or URL
- `source_type` (string, optional): 'file', 'url', or 'w24' (default: 'file')
- `recipe_id` (string, optional): Recipe ID (e.g., 'social_teaser_w24')

**Returns:** `{ success, project_id, project, message }`

### video_kitchen_run_pipeline
Run the full video processing pipeline.

**Parameters:**
- `project_id` (string, required): Project ID
- `recipe_id` (string, optional): Recipe to use
- `auto` (boolean, optional): Run full auto pipeline (default: true)
- `vo_text` (string, optional): Voice-over text

**Returns:** `{ success, job_id, project_id, status, message }`

### video_kitchen_get_status
Get project status and progress.

**Parameters:**
- `project_id` (string, required): Project ID
- `job_id` (string, optional): Specific job ID

**Returns:** `{ success, project, scenes_count, outputs_count, jobs, job }`

### video_kitchen_list_outputs
List all generated outputs.

**Parameters:**
- `project_id` (string, required): Project ID

**Returns:** `{ success, outputs: [{ id, filename, file_size, download_url }] }`

### video_kitchen_process_w24
Process a W24 news URL automatically.

**Parameters:**
- `w24_url` (string, required): W24 video URL
- `recipe_id` (string, optional): Recipe to apply (default: 'social_teaser_w24')

**Returns:** `{ success, project_id, job_id, w24_info, status, message }`

## Recipes

| Recipe | Duration | Aspect | Use Case |
|--------|----------|--------|----------|
| `social_teaser_w24` | 20-30s | 9:16 | Instagram/TikTok teaser |
| `spicy_trailer` | 30-45s | 16:9 | YouTube trailer |
| `highlight_abendsendung` | 60-90s | 16:9 | Broadcast highlight |
| `bts_soup` | 45-60s | 1:1 | Behind the scenes |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/tools` | GET | List available tools |
| `/api/tools/:tool` | POST | Execute tool |
| `/api/projects` | GET/POST | List/Create projects |
| `/api/projects/:id` | GET/PATCH/DELETE | Project CRUD |
| `/api/projects/:id/gallery` | GET | Output gallery with thumbnails |
| `/api/jobs` | GET/POST | List/Create jobs |
| `/api/jobs/:id` | GET | Job status |
| `/api/jobs/:id/run` | POST | Execute job |
| `/api/jobs/:id/progress` | GET | SSE progress stream |
| `/api/outputs` | GET | List outputs |
| `/api/w24/parse` | POST | Parse W24 URL |
| `/api/w24/download` | POST | Download W24 video |
| `/api/w24/metadata` | POST | Get W24 metadata |
| `/api/vision/analyze` | POST | Analyze video with zai-vision |
| `/api/webhooks/job-complete` | POST | Job completion webhook |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 3001 | API server port |
| `PROJECTS_BASE_DIR` | ../projects | Projects directory |
| `PYTHON_PATH` | .venv/bin/python3 | Python executable |
| `VIDEO_KITCHEN_API_URL` | http://localhost:3001 | API base URL |
| `VIDEO_KITCHEN_WEBHOOK_SECRET` | vk-webhook-secret | Webhook signature secret |

## Docker

```bash
docker compose up -d
# → API on http://localhost:3001
```

## Version

v0.8.0 — Phase 3: Agent Integration & Production Pipeline
