#!/usr/bin/env python3
"""
taste_test.py — Preview & QC for Video Kitchen v0.6.0

Stage 5: Quality check and preview generation.
  - ffprobe validation (codec, resolution, duration)
  - Visual quality check via thumbnails
  - Rule-based compliance checks
  - Generate preview GIF

Usage:
    from taste_test import TasteTester
    tester = TasteTester(project_dir="/path/to/project")
    report = tester.run_qc("output.mp4", recipe={...})
"""

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Optional


class TasteTester:
    """Stage 5: QC — validate output and generate previews."""

    # Hard rules from the Kitchen
    HARD_RULES = {
        "min_duration": 5.0,      # seconds
        "max_duration": 300.0,    # seconds (5 min)
        "min_resolution": 720,    # minimum height
        "required_codec": "h264",
        "required_audio_codec": "aac",
        "max_file_size_mb": 500,
    }

    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)
        self.output_dir = self.project_dir / "outputs"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run_qc(
        self,
        output_path: str,
        recipe: Optional[dict] = None,
        generate_preview: bool = True,
    ) -> dict:
        """
        Run full QC pipeline on an output video.

        Returns:
            QC report dict with pass/fail status
        """
        output_path = str(Path(output_path).resolve())
        if not os.path.exists(output_path):
            return {"passed": False, "error": f"File not found: {output_path}"}

        print(f"[QC] Running quality check on {output_path}")

        report = {
            "id": str(uuid.uuid4())[:8],
            "output_path": output_path,
            "passed": True,
            "issues": [],
            "warnings": [],
            "checks": {},
        }

        # Check 1: File probe
        probe = self._probe(output_path)
        report["checks"]["probe"] = probe

        if not probe:
            report["passed"] = False
            report["issues"].append("ffprobe failed — cannot read file")
            return report

        # Check 2: Duration
        duration = probe.get("duration", 0)
        if duration < self.HARD_RULES["min_duration"]:
            report["passed"] = False
            report["issues"].append(
                f"Duration too short: {duration:.1f}s (min: {self.HARD_RULES['min_duration']}s)"
            )
        elif duration > self.HARD_RULES["max_duration"]:
            report["passed"] = False
            report["issues"].append(
                f"Duration too long: {duration:.1f}s (max: {self.HARD_RULES['max_duration']}s)"
            )

        # Check 3: Resolution
        height = probe.get("height", 0)
        if height < self.HARD_RULES["min_resolution"]:
            report["passed"] = False
            report["issues"].append(
                f"Resolution too low: {height}p (min: {self.HARD_RULES['min_resolution']}p)"
            )

        # Check 4: Codec
        video_codec = probe.get("video_codec", "")
        if "264" not in video_codec and "h264" not in video_codec.lower() and "avc" not in video_codec.lower():
            report["warnings"].append(f"Non-standard codec: {video_codec}")

        # Check 5: File size
        file_size_mb = probe.get("file_size", 0) / (1024 * 1024)
        if file_size_mb > self.HARD_RULES["max_file_size_mb"]:
            report["passed"] = False
            report["issues"].append(
                f"File too large: {file_size_mb:.1f}MB (max: {self.HARD_RULES['max_file_size_mb']}MB)"
            )

        # Check 6: Has audio
        if not probe.get("has_audio"):
            report["warnings"].append("No audio track")

        # Check 7: Recipe compliance
        if recipe:
            recipe_check = self._check_recipe_compliance(probe, recipe)
            report["checks"]["recipe"] = recipe_check
            if recipe_check.get("issues"):
                report["warnings"].extend(recipe_check["issues"])

        # Check 8: Generate preview
        if generate_preview:
            preview_path = self._generate_preview(output_path)
            if preview_path:
                report["preview_path"] = preview_path

        # Summary
        status = "✅ PASSED" if report["passed"] else "❌ FAILED"
        print(f"[QC] {status}")
        if report["issues"]:
            for issue in report["issues"]:
                print(f"  ❌ {issue}")
        if report["warnings"]:
            for warn in report["warnings"]:
                print(f"  ⚠️  {warn}")

        # Save report
        report_path = self.output_dir / f"qc_{uuid.uuid4().hex[:6]}.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        return report

    def _probe(self, path: str) -> dict:
        """Probe video file with ffprobe."""
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return {}

        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        streams = data.get("streams", [])

        video_stream = next(
            (s for s in streams if s.get("codec_type") == "video"), {}
        )
        audio_stream = next(
            (s for s in streams if s.get("codec_type") == "audio"), None
        )

        return {
            "duration": float(fmt.get("duration", 0)),
            "file_size": int(fmt.get("size", 0)),
            "bit_rate": int(fmt.get("bit_rate", 0)),
            "width": int(video_stream.get("width", 0)),
            "height": int(video_stream.get("height", 0)),
            "video_codec": video_stream.get("codec_name", ""),
            "fps": video_stream.get("r_frame_rate", ""),
            "has_audio": audio_stream is not None,
            "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
            "audio_channels": audio_stream.get("channels") if audio_stream else 0,
        }

    def _check_recipe_compliance(self, probe: dict, recipe: dict) -> dict:
        """Check if output matches recipe requirements."""
        issues = []

        # Aspect ratio check
        aspect = recipe.get("aspect_ratio", "16:9")
        w, h = probe.get("width", 0), probe.get("height", 0)
        if w and h:
            actual_ratio = w / h
            expected_ratios = {
                "16:9": 16 / 9,
                "9:16": 9 / 16,
                "1:1": 1.0,
                "4:3": 4 / 3,
            }
            expected = expected_ratios.get(aspect)
            if expected and abs(actual_ratio - expected) > 0.1:
                issues.append(
                    f"Aspect ratio mismatch: expected {aspect}, got {w}:{h} ({actual_ratio:.2f})"
                )

        # Duration range check
        target = recipe.get("target_duration", "")
        duration = probe.get("duration", 0)
        if "-" in str(target):
            try:
                parts = str(target).replace("s", "").split("-")
                min_d, max_d = float(parts[0]), float(parts[1])
                if duration < min_d or duration > max_d:
                    issues.append(
                        f"Duration outside target range: {duration:.1f}s (target: {min_d}-{max_d}s)"
                    )
            except (ValueError, IndexError):
                pass

        return {"compliant": len(issues) == 0, "issues": issues}

    def _generate_preview(
        self, output_path: str, width: int = 320, fps: int = 4, max_duration: float = 10.0
    ) -> Optional[str]:
        """Generate a preview GIF from the output."""
        preview_path = self.output_dir / f"preview_{uuid.uuid4().hex[:6]}.gif"

        cmd = [
            "ffmpeg", "-y",
            "-i", output_path,
            "-t", str(max_duration),
            "-vf", f"fps={fps},scale={width}:-1:flags=lanczos",
            "-loop", "0",
            str(preview_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0 and preview_path.exists():
            print(f"[QC] Preview generated: {preview_path}")
            return str(preview_path)
        return None


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Taste Tester — QC Pipeline")
    parser.add_argument("video", help="Path to output video")
    parser.add_argument("--project-dir", default="./projects/default")
    parser.add_argument("--no-preview", action="store_true")
    parser.add_argument("--recipe", help="Recipe JSON file")

    args = parser.parse_args()

    recipe = None
    if args.recipe and os.path.exists(args.recipe):
        with open(args.recipe) as f:
            recipe = json.load(f)

    tester = TasteTester(args.project_dir)
    report = tester.run_qc(
        output_path=args.video,
        recipe=recipe,
        generate_preview=not args.no_preview,
    )

    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
