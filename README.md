# FFWD Trailer Kitchen v0.6.0 🍳

> *Agentic Video Highlight Platform*

Video Kitchen v0.6.0 transforms video into highlights, teasers, and social clips using an AI-powered pipeline.

## Quick Start

```bash
# Install dependencies
cd scripts
python3 -m venv .venv
source .venv/bin/activate
pip install -r ../requirements.txt

# Full auto: process a video
python3 kitchen.py --open video.mp4 --recipe social_teaser_w24 --auto

# Step by step
python3 kitchen.py --open video.mp4 --transcribe
python3 kitchen.py --analyze --project my_project
python3 kitchen.py --select --auto --recipe spicy_trailer --project my_project
python3 kitchen.py --plate --project my_project
python3 kitchen.py --season --vo "Check this out!" --project my_project
python3 kitchen.py --qc --project my_project

# List projects
python3 kitchen.py --list

# Project info
python3 kitchen.py --info --project my_project
```

## Pipeline Stages

| Stage | Script | Description |
|-------|--------|-------------|
| **Prep** | `prep_station.py` | Scene detection (PySceneDetect), thumbnails, transcription |
| **Analyze** | `scoring.py` | AI scoring — visual, transcript, audio energy |
| **Select** | `kitchen.py --select` | Auto-select top scenes by recipe criteria |
| **Plate** | `plating.py` | MoviePy assembly, aspect ratio conversion |
| **Season** | `seasoning.py` | VO generation, music selection, audio mixing |
| **QC** | `taste_test.py` | ffprobe validation, recipe compliance, preview GIF |

## Recipes

| Recipe | Duration | Aspect | Use Case |
|--------|----------|--------|----------|
| `social_teaser_w24` | 20-30s | 9:16 | Instagram/TikTok teaser |
| `spicy_trailer` | 30-45s | 16:9 | YouTube trailer |
| `highlight_abendsendung` | 60-90s | 16:9 | Broadcast highlight |
| `bts_soup` | 45-60s | 1:1 | Behind the scenes |

## Storage

```
projects/
└── {project_id}/
    ├── project.json      # Project metadata
    ├── scenes.json       # Detected + scored scenes
    ├── transcript.json   # Full transcript
    ├── selection.json    # Scene selection
    ├── outputs.json      # Rendered outputs
    ├── thumbnails/       # Scene thumbnails
    ├── outputs/          # Rendered videos
    └── qc/              # QC reports
```

## Architecture (Planned)

v0.6.0 adds three layers on top of the pipeline:

1. **Pipeline Engine** — Scene detection + AI scoring + MoviePy assembly ✅ (Phase 1)
2. **Agentic Backend** — Express API + SQLite + OpenClaw tools (Phase 2)
3. **Web Dashboard** — Next.js cinematic UI (Phase 3)

## Requirements

- Python 3.11+
- ffmpeg (system)
- OpenCV (for visual scoring)
- OpenAI API key (for Whisper transcription + LLM scoring)

## License

Proprietary — FFWD Media
