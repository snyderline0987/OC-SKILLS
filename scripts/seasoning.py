#!/usr/bin/env python3
"""
seasoning.py — Audio Integration for Video Kitchen v0.6.0

Stage 4b: Season the plated video with VO, music, and mixed audio.
Handles:
  - Music selection from library
  - VO generation (OpenAI TTS + ElevenLabs)
  - Audio mixing (VO + Music + Original)
  - Final audio-merge to video

Usage:
    from seasoning import SeasoningStation
    season = SeasoningStation(project_dir="/path/to/project")
    season.apply(output_path="output.mp4", recipe={...})
"""

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Optional


class SeasoningStation:
    """Stage 4b: Season — add audio (VO + music + mix) to plated video."""

    def __init__(self, project_dir: str, music_library_dir: str = "./music_library"):
        self.project_dir = Path(project_dir)
        self.output_dir = self.project_dir / "outputs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.music_library_dir = Path(music_library_dir)
        self.music_manifest = None

        manifest_path = self.music_library_dir / "music_library.json"
        if not manifest_path.exists():
            # Try parent
            manifest_path = Path("./music_library.json")
        if manifest_path.exists():
            with open(manifest_path) as f:
                self.music_manifest = json.load(f)

    def apply(
        self,
        output_path: str,
        recipe: dict,
        vo_text: Optional[str] = None,
        vo_style: str = "nova",
        music_mood: Optional[str] = None,
        vo_volume: float = 1.0,
        music_volume: float = 0.1,
        original_volume: float = 0.0,
        output_name: Optional[str] = None,
    ) -> dict:
        """
        Apply audio seasoning to a plated video.

        Args:
            output_path: Path to the plated (visual-only or original-audio) video
            recipe: Recipe configuration
            vo_text: Voice-over text (None = no VO)
            vo_style: TTS voice style
            music_mood: Music mood to select (None = from recipe)
            vo_volume: VO volume (0.0-1.0)
            music_volume: Music volume (0.0-1.0)
            original_volume: Original audio volume (0.0-1.0)
            output_name: Output filename

        Returns:
            Seasoned output record
        """
        print(f"[SEASON] Seasoning: {output_path}")

        if music_mood is None:
            music_mood = recipe.get("music_mood", "epic")

        base_name = Path(output_path).stem
        if output_name is None:
            output_name = f"{base_name}_seasoned.mp4"
        final_path = self.output_dir / output_name

        # Track generated temp files for cleanup
        temp_files = []

        try:
            # Step 1: Generate VO if text provided
            vo_path = None
            if vo_text:
                print(f"[SEASON] Generating VO ({len(vo_text)} chars, voice={vo_style})...")
                vo_path = self._generate_vo(vo_text, vo_style)
                if vo_path:
                    temp_files.append(vo_path)

            # Step 2: Select music
            music_path = self._select_music(music_mood)

            # Step 3: Extract original audio
            original_audio_path = self._extract_audio(output_path)
            if original_audio_path:
                temp_files.append(original_audio_path)

            # Step 4: Mix audio
            print(f"[SEASON] Mixing audio: VO={vo_volume}, Music={music_volume}, Original={original_volume}")
            mixed_audio_path = self._mix_audio(
                video_path=output_path,
                vo_path=vo_path,
                music_path=music_path,
                original_path=original_audio_path,
                vo_volume=vo_volume,
                music_volume=music_volume,
                original_volume=original_volume,
            )
            if mixed_audio_path:
                temp_files.append(mixed_audio_path)

            # Step 5: Merge mixed audio with video
            if mixed_audio_path:
                print(f"[SEASON] Merging audio into video...")
                cmd = [
                    "ffmpeg", "-y",
                    "-i", output_path,
                    "-i", mixed_audio_path,
                    "-c:v", "copy",
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-shortest",
                    str(final_path),
                ]
                subprocess.run(cmd, capture_output=True, text=True, check=True)
            else:
                # No audio mixing needed, just copy
                import shutil
                shutil.copy2(output_path, final_path)

            # Get output metadata
            output_info = self._probe(str(final_path))

            result = {
                "id": str(uuid.uuid4())[:8],
                "type": "seasoned",
                "filename": output_name,
                "file_path": str(final_path),
                "duration": output_info.get("duration", 0),
                "file_size": output_info.get("size", 0),
                "vo_generated": vo_path is not None,
                "music_mood": music_mood,
                "mix_settings": {
                    "vo_volume": vo_volume,
                    "music_volume": music_volume,
                    "original_volume": original_volume,
                },
            }

            print(f"[SEASON] Done! Output: {final_path}")
            return result

        finally:
            # Clean up temp files
            for f in temp_files:
                if os.path.exists(f):
                    os.unlink(f)

    def _generate_vo(self, text: str, style: str = "nova") -> Optional[str]:
        """Generate VO using OpenAI TTS or ElevenLabs."""
        vo_path = self.project_dir / f"_vo_{uuid.uuid4().hex[:6]}.mp3"

        try:
            import openai
            client = openai.OpenAI()

            response = client.audio.speech.create(
                model="tts-1",
                voice=style,
                input=text,
            )

            with open(vo_path, "wb") as f:
                f.write(response.content)

            print(f"[SEASON] VO generated: {vo_path}")
            return str(vo_path)

        except Exception as e:
            print(f"[SEASON] VO generation failed: {e}")
            # Try ElevenLabs fallback
            return self._generate_vo_elevenlabs(text, style)

    def _generate_vo_elevenlabs(self, text: str, style: str) -> Optional[str]:
        """Fallback VO generation via ElevenLabs."""
        api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not api_key:
            return None

        voice_map = {
            "dramatic": "21m00Tcm4TlvDq8ikWAM",
            "professional": "AZnzlk1XvdvUeBnXmlld",
            "punchy": "EXAVITQu4vr4xnSDxMaL",
            "conversational": "MF3mGyEYCl7XYWbV9V6O",
            "news": "TxGEqnHWrfWFTfGW9XjX",
        }

        voice_id = voice_map.get(style, voice_map.get("dramatic"))
        vo_path = self.project_dir / f"_vo_{uuid.uuid4().hex[:6]}.mp3"

        try:
            import httpx
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {
                "xi-api-key": api_key,
                "Content-Type": "application/json",
            }
            data = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            }
            resp = httpx.post(url, json=data, headers=headers, timeout=30)
            resp.raise_for_status()

            with open(vo_path, "wb") as f:
                f.write(resp.content)

            return str(vo_path)
        except Exception as e:
            print(f"[SEASON] ElevenLabs fallback failed: {e}")
            return None

    def _select_music(self, mood: str) -> Optional[str]:
        """Select a music track from the library by mood."""
        if not self.music_manifest:
            # Check common paths
            for path in [
                Path("./music_library"),
                Path(self.music_library_dir),
            ]:
                mp3s = list(path.glob("*.mp3"))
                if mp3s:
                    return str(mp3s[0])
            return None

        # Find matching mood
        tracks = self.music_manifest if isinstance(self.music_manifest, list) else self.music_manifest.get("tracks", [])
        for track in tracks:
            track_mood = track.get("mood", "").lower()
            if mood.lower() in track_mood or track_mood in mood.lower():
                track_path = Path(track.get("path", ""))
                if not track_path.exists():
                    # Try relative to music library
                    track_path = self.music_library_dir / track.get("filename", "")
                if track_path.exists():
                    return str(track_path)

        # Fallback: return first available track
        if isinstance(tracks, list) and tracks:
            track_path = self.music_library_dir / tracks[0].get("filename", "")
            if track_path.exists():
                return str(track_path)

        # Last resort: find any mp3
        for path in [Path("./music_library"), Path(self.music_library_dir)]:
            mp3s = list(path.glob("*.mp3"))
            if mp3s:
                return str(mp3s[0])

        return None

    def _extract_audio(self, video_path: str) -> Optional[str]:
        """Extract audio from video to WAV."""
        audio_path = self.project_dir / f"_original_audio_{uuid.uuid4().hex[:6]}.wav"
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "44100", "-ac", "2",
            str(audio_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and audio_path.exists():
            return str(audio_path)
        return None

    def _mix_audio(
        self,
        video_path: str,
        vo_path: Optional[str] = None,
        music_path: Optional[str] = None,
        original_path: Optional[str] = None,
        vo_volume: float = 1.0,
        music_volume: float = 0.1,
        original_volume: float = 0.0,
    ) -> Optional[str]:
        """Mix audio tracks using ffmpeg."""
        # Get video duration for padding music
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True,
        )
        duration = float(probe.stdout.strip()) if probe.stdout.strip() else 30

        output_path = self.project_dir / f"_mixed_audio_{uuid.uuid4().hex[:6]}.wav"

        # Build ffmpeg complex filter for mixing
        inputs = []
        filter_parts = []
        mix_labels = []

        idx = 0
        if original_path and os.path.exists(original_path) and original_volume > 0:
            inputs.extend(["-i", original_path])
            filter_parts.append(f"[{idx}:a]volume={original_volume}[a{idx}]")
            mix_labels.append(f"[a{idx}]")
            idx += 1

        if vo_path and os.path.exists(vo_path):
            inputs.extend(["-i", vo_path])
            filter_parts.append(f"[{idx}:a]volume={vo_volume}[a{idx}]")
            mix_labels.append(f"[a{idx}]")
            idx += 1

        if music_path and os.path.exists(music_path) and music_volume > 0:
            inputs.extend(["-i", music_path])
            # Loop music if shorter than video, and set volume
            filter_parts.append(
                f"[{idx}:a]volume={music_volume},atrim=0:{duration},apad[dur{idx}]"
            )
            filter_parts.append(f"[dur{idx}]aresample=44100[a{idx}]")
            mix_labels.append(f"[a{idx}]")
            idx += 1

        if not mix_labels:
            return None

        # Mix all tracks
        mix_input = "".join(mix_labels)
        filter_parts.append(f"{mix_input}amix=inputs={len(mix_labels)}:duration=longest[out]")

        filter_str = ";".join(filter_parts)

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_str,
            "-map", "[out]",
            "-ar", "44100", "-ac", "2",
            str(output_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and output_path.exists():
            return str(output_path)

        print(f"[SEASON] Audio mixing failed: {result.stderr[:200]}")
        return None

    def _probe(self, path: str) -> dict:
        """Probe video file metadata."""
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", str(path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        return {
            "duration": float(fmt.get("duration", 0)),
            "size": int(fmt.get("size", 0)),
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Seasoning Station — Audio Integration")
    parser.add_argument("video", help="Path to input video")
    parser.add_argument("--project-dir", default="./projects/default")
    parser.add_argument("--vo-text", help="VO text to generate")
    parser.add_argument("--vo-style", default="nova")
    parser.add_argument("--music-mood", default="epic")
    parser.add_argument("--vo-volume", type=float, default=1.0)
    parser.add_argument("--music-volume", type=float, default=0.1)
    parser.add_argument("--original-volume", type=float, default=0.0)

    args = parser.parse_args()

    recipe = {"music_mood": args.music_mood}
    season = SeasoningStation(args.project_dir)
    result = season.apply(
        output_path=args.video,
        recipe=recipe,
        vo_text=args.vo_text,
        vo_style=args.vo_style,
        vo_volume=args.vo_volume,
        music_volume=args.music_volume,
        original_volume=args.original_volume,
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
