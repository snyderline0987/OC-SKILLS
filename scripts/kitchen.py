#!/usr/bin/env python3
"""
kitchen.py — Video Kitchen v0.6.0 Orchestrator

The main CLI for the Video Kitchen pipeline. Supports:
  - Full auto pipeline: open → analyze → plate → qc
  - Step-by-step mode
  - Recipe-driven output

Usage:
    # Full auto
    python3 kitchen.py --open video.mp4 --recipe spicy_trailer --auto

    # Step by step
    python3 kitchen.py --open video.mp4              # Prep (scene detection)
    python3 kitchen.py --analyze --project my_proj   # Score scenes
    python3 kitchen.py --analyze --project my_proj --top 5  # Score + rank top 5
    python3 kitchen.py --select --auto --recipe social_teaser_w24  # Select scenes
    python3 kitchen.py --plate --project my_proj     # Assemble
    python3 kitchen.py --season --vo "Hook text..."  # Add audio
    python3 kitchen.py --qc                           # Quality check

    # List projects
    python3 kitchen.py --list

    # Show project info
    python3 kitchen.py --info --project my_proj
"""

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

# Add scripts dir to path
sys.path.insert(0, str(Path(__file__).parent))

from pantry import Pantry
from prep_station import PrepStation
from scoring import ScoringEngine
from plating import PlatingStation
from seasoning import SeasoningStation
from taste_test import TasteTester


# ─── Recipe Definitions ─────────────────────────────────────────────

RECIPES = {
    "social_teaser_w24": {
        "recipe": "social_teaser_w24",
        "name": "Social Media Teaser für W24",
        "target_duration": "20-30s",
        "scene_count": "3-5",
        "scene_selection": "auto_highlights",
        "music_mood": "upbeat",
        "music_bpm": "120-140",
        "vo_style": "punchy",
        "aspect_ratio": "9:16",
        "transitions": "quick_cuts",
    },
    "spicy_trailer": {
        "recipe": "spicy_trailer",
        "name": "Spicy Trailer",
        "target_duration": "30-45s",
        "scene_count": "5-8",
        "scene_selection": "auto_highlights",
        "music_mood": "epic",
        "music_bpm": "100-130",
        "vo_style": "dramatic",
        "aspect_ratio": "16:9",
        "transitions": "crossfade",
    },
    "highlight_abendsendung": {
        "recipe": "highlight_abendsendung",
        "name": "Highlight Abendsendung",
        "target_duration": "60-90s",
        "scene_count": "6-12",
        "scene_selection": "auto_highlights",
        "music_mood": "professional",
        "music_bpm": "90-110",
        "vo_style": "professional",
        "aspect_ratio": "16:9",
        "transitions": "cut",
    },
    "bts_soup": {
        "recipe": "bts_soup",
        "name": "Behind the Scenes Soup",
        "target_duration": "45-60s",
        "scene_count": "5-8",
        "scene_selection": "random_diverse",
        "music_mood": "chill",
        "music_bpm": "80-100",
        "vo_style": "conversational",
        "aspect_ratio": "1:1",
        "transitions": "crossfade",
    },
}


def get_recipe(name: str) -> dict:
    """Get recipe by name, or return a custom template."""
    if name in RECIPES:
        return RECIPES[name]
    return {
        "recipe": name,
        "name": name,
        "target_duration": "30-60s",
        "scene_count": "4-8",
        "scene_selection": "auto_highlights",
        "music_mood": "epic",
        "aspect_ratio": "16:9",
        "transitions": "cut",
    }


def auto_select_scenes(scenes: list[dict], recipe: dict) -> list[int]:
    """
    Auto-select scenes based on recipe criteria and scores.
    Returns list of scene indices.
    """
    target_range = recipe.get("target_duration", "30-60s")
    scene_count_range = recipe.get("scene_count", "4-8")

    # Parse duration range
    dur_str = target_range.replace("s", "").strip()
    if "-" in dur_str:
        min_dur, max_dur = [float(x) for x in dur_str.split("-")]
    else:
        min_dur, max_dur = float(dur_str), float(dur_str) * 1.5

    # Parse scene count range
    count_str = str(scene_count_range).strip()
    if "-" in count_str:
        min_count, max_count = [int(x) for x in count_str.split("-")]
    else:
        min_count = max_count = int(count_str)

    # Sort by combined score (descending)
    scored = [s for s in scenes if s.get("combined_score") is not None]
    scored.sort(key=lambda s: s.get("combined_score", 0), reverse=True)

    selected = []
    total_duration = 0.0

    for scene in scored:
        if len(selected) >= max_count:
            break
        if total_duration + scene["duration"] > max_dur:
            continue

        selected.append(scene["scene_index"])
        total_duration += scene["duration"]

        if len(selected) >= min_count and total_duration >= min_dur:
            break

    # Sort by time order for final output
    selected.sort()
    return selected


def cmd_open(args):
    """Open a video — scene detection + thumbnail extraction."""
    pantry = Pantry(args.base_dir)

    # Create project
    video_path = args.open
    project_id = args.project or Path(video_path).stem.replace(" ", "_").lower()
    project_id = project_id[:32]

    try:
        meta = pantry.create_project(
            project_id=project_id,
            title=project_id,
            source=video_path,
        )
    except FileExistsError:
        meta = pantry.get_project(project_id)

    project_dir = str(pantry._project_dir(project_id))

    print(f"\n🍳 KITCHEN OPEN: {video_path}")
    print(f"   Project: {project_id}")

    prep = PrepStation(project_dir)
    result = prep.process(
        video_path=video_path,
        threshold=args.threshold,
        min_scene_len=args.min_scene_len,
        extract_thumbs=True,
        transcribe=args.transcribe,
        whisper_model=args.whisper_model,
    )

    # Update project status
    pantry.update_project(project_id, {
        "status": "prepped",
        "video_info": result["video_info"],
        "scene_count": len(result["scenes"]),
    })

    print(f"\n✅ Prepped {len(result['scenes'])} scenes")
    print(f"   Project ID: {project_id}")
    print(f"   Directory: {project_dir}")

    return project_id


def cmd_analyze(args):
    """Analyze (score) scenes with multi-modal AI scoring."""
    pantry = Pantry(args.base_dir)
    project_id = args.project
    project_dir = str(pantry._project_dir(project_id))
    meta = pantry.get_project(project_id)

    video_path = meta.get("source", "")
    if not video_path or not os.path.exists(video_path):
        print(f"Error: Source video not found: {video_path}")
        sys.exit(1)

    scenes = pantry.load_scenes(project_id)
    if not scenes:
        print("Error: No scenes found. Run --open first.")
        sys.exit(1)

    print(f"\n🍳 KITCHEN ANALYZE: {project_id}")

    # Parse optional weights
    weights = None
    if hasattr(args, 'weights') and args.weights:
        w_parts = [float(x) for x in args.weights.split(",")]
        weights = {"visual": w_parts[0], "transcript": w_parts[1], "audio": w_parts[2]}

    # Parse optional thresholds
    thresholds = None
    if hasattr(args, 'min_score') or hasattr(args, 'min_duration'):
        thresholds = {
            "min_score": getattr(args, 'min_score', 0.15),
            "min_duration": getattr(args, 'min_duration', 1.0),
            "action_similarity": 0.75,
        }

    engine = ScoringEngine(project_dir, weights=weights, thresholds=thresholds)

    top_n = getattr(args, 'top', 0) or 0

    if top_n > 0:
        # Full analysis: score + select top-N highlights
        result = engine.analyze(
            video_path=video_path,
            scenes=scenes,
            top_n=top_n,
            use_llm=not args.no_llm,
        )
        scenes = result["scenes"]
        highlights = result["highlights"]

        pantry.save_scenes(project_id, scenes)
        pantry.update_project(project_id, {"status": "analyzed"})

        print(f"\n✅ Scored {len(scenes)} scenes")
        print(f"🎬 Top {top_n} highlights: {result['highlight_indices']}")
    else:
        scenes = engine.score(
            video_path=video_path,
            scenes=scenes,
            use_llm=not args.no_llm,
        )

        pantry.save_scenes(project_id, scenes)
        pantry.update_project(project_id, {"status": "analyzed"})

        print(f"\n✅ Scored {len(scenes)} scenes")


def cmd_select(args):
    """Select scenes for plating."""
    pantry = Pantry(args.base_dir)
    project_id = args.project
    scenes = pantry.load_scenes(project_id)
    recipe = get_recipe(args.recipe)

    print(f"\n🍳 KITCHEN SELECT: {project_id} (recipe: {args.recipe})")

    if args.auto:
        selection = auto_select_scenes(scenes, recipe)
    else:
        # Show top scenes for manual selection
        scored = sorted(scenes, key=lambda s: s.get("combined_score", 0), reverse=True)
        print("\nTop scenes by score:")
        for s in scored[:10]:
            idx = s["scene_index"]
            score = s.get("combined_score", 0)
            dur = s["duration"]
            text = s.get("transcript", "")[:60]
            print(f"  #{idx}: score={score:.3f}  dur={dur:.1f}s  {text}")

        raw = input("\nEnter scene indices (comma-separated): ")
        selection = [int(x.strip()) for x in raw.split(",")]

    selection_data = {
        "recipe": recipe,
        "scene_indices": selection,
        "total_duration": sum(scenes[i]["duration"] for i in selection if i < len(scenes)),
    }

    pantry.save_selection(project_id, selection_data)
    print(f"\n✅ Selected {len(selection)} scenes (total: {selection_data['total_duration']:.1f}s)")
    print(f"   Scenes: {selection}")


def cmd_plate(args):
    """Plate (assemble) the selected scenes."""
    pantry = Pantry(args.base_dir)
    project_id = args.project
    meta = pantry.get_project(project_id)
    project_dir = str(pantry._project_dir(project_id))

    video_path = meta.get("source", "")
    scenes = pantry.load_scenes(project_id)
    selection_data = pantry.load_selection(project_id)

    if not selection_data:
        print("Error: No scene selection found. Run --select first.")
        sys.exit(1)

    print(f"\n🍳 KITCHEN PLATE: {project_id}")

    plate = PlatingStation(project_dir)
    result = plate.assemble(
        video_path=video_path,
        scenes=scenes,
        selection=selection_data["scene_indices"],
        recipe=selection_data["recipe"],
    )

    pantry.save_output(project_id, result)
    pantry.update_project(project_id, {"status": "plated"})

    print(f"\n✅ Plated: {result['file_path']}")
    return result


def cmd_season(args):
    """Season (add audio) to the plated output."""
    pantry = Pantry(args.base_dir)
    project_id = args.project
    project_dir = str(pantry._project_dir(project_id))

    outputs = pantry.load_outputs(project_id)
    if not outputs:
        print("Error: No outputs found. Run --plate first.")
        sys.exit(1)

    latest_output = outputs[-1]
    output_path = latest_output.get("file_path", "")

    if not os.path.exists(output_path):
        print(f"Error: Output file not found: {output_path}")
        sys.exit(1)

    recipe = get_recipe(args.recipe)
    print(f"\n🍳 KITCHEN SEASON: {project_id}")

    season = SeasoningStation(project_dir)
    result = season.apply(
        output_path=output_path,
        recipe=recipe,
        vo_text=args.vo_text,
        vo_style=recipe.get("vo_style", "nova"),
        music_mood=recipe.get("music_mood", "epic"),
        vo_volume=args.vo_volume,
        music_volume=args.music_volume,
        original_volume=args.original_volume,
    )

    pantry.save_output(project_id, result)
    pantry.update_project(project_id, {"status": "seasoned"})

    print(f"\n✅ Seasoned: {result['file_path']}")
    return result


def cmd_qc(args):
    """Run quality check on latest output."""
    pantry = Pantry(args.base_dir)
    project_id = args.project
    project_dir = str(pantry._project_dir(project_id))

    outputs = pantry.load_outputs(project_id)
    if not outputs:
        print("Error: No outputs found. Run --plate or --season first.")
        sys.exit(1)

    latest_output = outputs[-1]
    output_path = latest_output.get("file_path", "")

    print(f"\n🍳 KITCHEN QC: {project_id}")

    recipe = get_recipe(args.recipe) if args.recipe else None
    tester = TasteTester(project_dir)
    report = tester.run_qc(output_path, recipe=recipe)

    # Update output record
    latest_output["qc_passed"] = report["passed"]
    latest_output["qc_report"] = report

    pantry.update_project(
        project_id,
        {"status": "complete" if report["passed"] else "qc_failed"},
    )

    return report


def cmd_auto(args):
    """Full auto pipeline: open → analyze → select → plate → season → qc."""
    # Step 1: Open
    project_id = cmd_open(args)

    # Override args.project for subsequent steps
    args.project = project_id

    # Step 2: Analyze
    cmd_analyze(args)

    # Step 3: Select
    args.auto = True
    cmd_select(args)

    # Step 4: Plate
    plate_result = cmd_plate(args)

    # Step 5: Season (if VO text or music available)
    if args.vo_text or True:  # Always season (music at minimum)
        season_result = cmd_season(args)

    # Step 6: QC
    report = cmd_qc(args)

    print(f"\n{'=' * 60}")
    print(f"🍳 KITCHEN COMPLETE!")
    print(f"   Project: {project_id}")
    print(f"   Status: {'✅ PASSED QC' if report['passed'] else '❌ QC ISSUES'}")
    if report.get("issues"):
        for issue in report["issues"]:
            print(f"   ⚠️  {issue}")
    print(f"{'=' * 60}")


def cmd_list(args):
    """List all projects."""
    pantry = Pantry(args.base_dir)
    projects = pantry.list_projects()

    if not projects:
        print("No projects found.")
        return

    print(f"\n{'=' * 60}")
    print(f"🍳 VIDEO KITCHEN — Projects")
    print(f"{'=' * 60}")
    for p in projects:
        pid = p.get("id", "?")
        status = p.get("status", "?")
        title = p.get("title", "?")
        scenes = p.get("scene_count", "?")
        print(f"  {pid:<24} [{status:<12}] scenes={scenes}  {title}")
    print(f"{'=' * 60}")


def cmd_info(args):
    """Show project details."""
    pantry = Pantry(args.base_dir)
    meta = pantry.get_project(args.project)
    scenes = pantry.load_scenes(args.project)
    outputs = pantry.load_outputs(args.project)

    print(f"\n{'=' * 60}")
    print(f"🍳 Project: {args.project}")
    print(f"{'=' * 60}")
    print(json.dumps(meta, indent=2, default=str))
    print(f"\nScenes: {len(scenes)}")
    print(f"Outputs: {len(outputs)}")

    if scenes:
        print(f"\n--- Top Scenes ---")
        top = sorted(scenes, key=lambda s: s.get("combined_score", 0), reverse=True)[:5]
        for s in top:
            print(f"  #{s['scene_index']}: score={s.get('combined_score', 'N/A')}  "
                  f"dur={s['duration']:.1f}s  {s.get('transcript', '')[:50]}")

    if outputs:
        print(f"\n--- Outputs ---")
        for o in outputs:
            qc = "✅" if o.get("qc_passed") else ("❌" if o.get("qc_passed") is False else "⏳")
            print(f"  {qc} {o.get('filename', '?')}  {o.get('duration', 0):.1f}s")


def main():
    parser = argparse.ArgumentParser(
        description="🍳 Video Kitchen v0.6.0 — Agentic Video Highlight Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full auto pipeline
  kitchen.py --open video.mp4 --recipe social_teaser_w24 --auto

  # Step by step
  kitchen.py --open video.mp4 --transcribe
  kitchen.py --analyze --project my_project
  kitchen.py --analyze --project my_project --top 5
  kitchen.py --select --auto --recipe spicy_trailer --project my_project
  kitchen.py --plate --project my_project
  kitchen.py --season --vo "Check this out!" --project my_project
  kitchen.py --qc --project my_project

  # Info
  kitchen.py --list
  kitchen.py --info --project my_project
        """,
    )

    # Common args
    parser.add_argument("--base-dir", default="./projects", help="Base directory for projects")
    parser.add_argument("--project", help="Project ID")

    # Commands
    parser.add_argument("--open", metavar="VIDEO", help="Open a video (scene detection)")
    parser.add_argument("--analyze", action="store_true", help="Score scenes")
    parser.add_argument("--select", action="store_true", help="Select scenes")
    parser.add_argument("--plate", action="store_true", help="Assemble video")
    parser.add_argument("--season", action="store_true", help="Add audio (VO + music)")
    parser.add_argument("--qc", action="store_true", help="Quality check")
    parser.add_argument("--auto", action="store_true", help="Full auto pipeline")
    parser.add_argument("--list", action="store_true", help="List projects")
    parser.add_argument("--info", action="store_true", help="Show project info")

    # Options
    parser.add_argument("--recipe", default="spicy_trailer", help="Recipe name")
    parser.add_argument("--threshold", type=float, default=27.0, help="Scene detection threshold")
    parser.add_argument("--min-scene-len", type=int, default=15, help="Min scene length (frames)")
    parser.add_argument("--transcribe", action="store_true", help="Transcribe audio")
    parser.add_argument("--whisper-model", default="base", help="Whisper model size")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM scoring")
    parser.add_argument("--no-openclip", action="store_true", help="Skip OpenClip visual scoring")
    parser.add_argument("--top", type=int, default=0, help="Select top-N highlights after scoring")
    parser.add_argument("--weights", default=None, help="Scoring weights: visual,transcript,audio (e.g. 0.4,0.3,0.3)")
    parser.add_argument("--min-duration", type=float, default=1.0, help="Min scene duration for top-N selection")
    parser.add_argument("--min-score", type=float, default=0.15, help="Min combined score for top-N selection")
    parser.add_argument("--vo-text", help="Voice-over text")
    parser.add_argument("--vo-volume", type=float, default=1.0)
    parser.add_argument("--music-volume", type=float, default=0.1)
    parser.add_argument("--original-volume", type=float, default=0.0)

    args = parser.parse_args()

    # Route commands
    if args.list:
        cmd_list(args)
    elif args.info:
        if not args.project:
            print("Error: --project required for --info")
            sys.exit(1)
        cmd_info(args)
    elif args.auto and args.open:
        cmd_auto(args)
    elif args.open:
        cmd_open(args)
    elif args.analyze:
        if not args.project:
            print("Error: --project required for --analyze")
            sys.exit(1)
        cmd_analyze(args)
    elif args.select:
        if not args.project:
            print("Error: --project required for --select")
            sys.exit(1)
        cmd_select(args)
    elif args.plate:
        if not args.project:
            print("Error: --project required for --plate")
            sys.exit(1)
        cmd_plate(args)
    elif args.season:
        if not args.project:
            print("Error: --project required for --season")
            sys.exit(1)
        cmd_season(args)
    elif args.qc:
        if not args.project:
            print("Error: --project required for --qc")
            sys.exit(1)
        cmd_qc(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
