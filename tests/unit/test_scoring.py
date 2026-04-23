"""
Unit tests for scoring.py — Sprint 2 AI Scoring Engine

Covers:
  - Heuristic transcript scoring (keyword density, excitement, length)
  - Thumbnail fallback visual scoring
  - Weight normalization
  - Score combination and ranking
  - Top-N selection with min duration and min score
  - analyze() convenience method
  - OpenClip integration (mocked)
  - Audio energy scoring (mocked ffmpeg)
  - Default weights and thresholds
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from scoring import ScoringEngine, DEFAULT_WEIGHTS, DEFAULT_THRESHOLDS


# ─── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def tmp_project(tmp_path):
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    return str(project_dir)


@pytest.fixture
def sample_scenes():
    return [
        {
            "scene_index": 0,
            "start_time": 0.0,
            "end_time": 5.0,
            "duration": 5.0,
            "thumbnail": "",
            "transcript": "Welcome to the show, today we have an amazing guest!",
        },
        {
            "scene_index": 1,
            "start_time": 5.0,
            "end_time": 10.0,
            "duration": 5.0,
            "thumbnail": "",
            "transcript": "",
        },
        {
            "scene_index": 2,
            "start_time": 10.0,
            "end_time": 15.0,
            "duration": 5.0,
            "thumbnail": "",
            "transcript": "This is incredible! You won't believe what happened next!",
        },
        {
            "scene_index": 3,
            "start_time": 15.0,
            "end_time": 17.0,
            "duration": 2.0,
            "thumbnail": "",
            "transcript": "Short but important scene with a key reveal.",
        },
        {
            "scene_index": 4,
            "start_time": 17.0,
            "end_time": 18.0,
            "duration": 1.0,
            "thumbnail": "",
            "transcript": "",
        },
    ]


@pytest.fixture
def scored_scenes(sample_scenes):
    """Pre-scored scenes for top-N selection tests."""
    scenes = []
    for i, s in enumerate(sample_scenes):
        sc = dict(s)
        sc["visual_score"] = 0.5 + i * 0.05
        sc["transcript_score"] = 0.6 if s["transcript"] else 0.2
        sc["audio_score"] = 0.4 + i * 0.03
        sc["combined_score"] = round(
            0.4 * sc["visual_score"] + 0.3 * sc["transcript_score"] + 0.3 * sc["audio_score"],
            4,
        )
        scenes.append(sc)
    return scenes


def make_scene(index, start, end, transcript="", duration=None):
    """Helper to create a scene dict."""
    dur = duration if duration is not None else (end - start)
    return {
        "scene_index": index,
        "start_time": start,
        "end_time": end,
        "duration": dur,
        "thumbnail": "",
        "transcript": transcript,
    }


# ─── Default Configuration Tests ─────────────────────────────────────

class TestDefaults:
    def test_default_weights(self):
        assert DEFAULT_WEIGHTS == {"visual": 0.40, "audio": 0.30, "transcript": 0.30}

    def test_default_thresholds(self):
        assert DEFAULT_THRESHOLDS["min_score"] == 0.15
        assert DEFAULT_THRESHOLDS["min_duration"] == 1.0
        assert "action_similarity" in DEFAULT_THRESHOLDS

    def test_engine_stores_config(self, tmp_project):
        engine = ScoringEngine(tmp_project)
        assert engine.weights == DEFAULT_WEIGHTS
        assert engine.thresholds == DEFAULT_THRESHOLDS

    def test_engine_custom_config(self, tmp_project):
        custom_weights = {"visual": 0.5, "audio": 0.25, "transcript": 0.25}
        custom_thresholds = {"min_score": 0.3, "min_duration": 2.0, "action_similarity": 0.8}
        engine = ScoringEngine(tmp_project, weights=custom_weights, thresholds=custom_thresholds)
        assert engine.weights == custom_weights
        assert engine.thresholds == custom_thresholds


# ─── Heuristic Transcript Scoring Tests ──────────────────────────────

class TestHeuristicScoring:
    def test_basic_ranking(self, tmp_project, sample_scenes):
        engine = ScoringEngine(tmp_project)
        scores = engine._heuristic_transcript_scores(sample_scenes)
        assert len(scores) == 5
        # Scene 2 has exclamations + exciting words → highest
        assert scores[2] > scores[1]  # Exciting text > silence
        assert scores[0] > scores[1]  # Some content > silence

    def test_empty_transcript(self, tmp_project):
        engine = ScoringEngine(tmp_project)
        scenes = [{"transcript": "", "scene_index": 0}]
        scores = engine._heuristic_transcript_scores(scenes)
        assert scores[0] == 0.2  # Default for empty

    def test_keyword_scoring(self, tmp_project):
        engine = ScoringEngine(tmp_project)
        scenes = [
            {"transcript": "This is normal content.", "scene_index": 0},
            {"transcript": "BREAKING NEWS! Amazing incredible exclusive!", "scene_index": 1},
        ]
        scores = engine._heuristic_transcript_scores(scenes)
        assert scores[1] > scores[0]

    def test_length_scoring(self, tmp_project):
        engine = ScoringEngine(tmp_project)
        scenes = [
            {"transcript": "Hi.", "scene_index": 0},
            {"transcript": "A" * 200, "scene_index": 1},  # Long text
        ]
        scores = engine._heuristic_transcript_scores(scenes)
        assert scores[1] > scores[0]  # Longer → higher

    def test_scores_bounded(self, tmp_project, sample_scenes):
        engine = ScoringEngine(tmp_project)
        scores = engine._heuristic_transcript_scores(sample_scenes)
        for s in scores:
            assert 0.0 <= s <= 1.0

    def test_no_transcripts_returns_neutral(self, tmp_project):
        engine = ScoringEngine(tmp_project)
        scenes = [
            {"transcript": "", "scene_index": 0},
            {"transcript": "", "scene_index": 1},
        ]
        scores = engine._transcript_scores(scenes, use_llm=False)
        assert scores == [0.5, 0.5]


# ─── Thumbnail Scoring Tests ─────────────────────────────────────────

class TestThumbnailScoring:
    def test_no_thumbnails(self, tmp_project, sample_scenes):
        engine = ScoringEngine(tmp_project)
        scores = engine._thumbnail_scores(sample_scenes)
        assert len(scores) == 5
        for s in scores:
            assert 0.0 <= s <= 1.0

    def test_with_real_thumbnail(self, tmp_project):
        engine = ScoringEngine(tmp_project)
        # Create a small test image
        from PIL import Image
        thumb_dir = Path(tmp_project) / "thumbnails"
        thumb_dir.mkdir(exist_ok=True)
        thumb_path = thumb_dir / "scene_0.jpg"

        # Colorful image → higher score
        arr = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        img = Image.fromarray(arr)
        img.save(str(thumb_path))

        scenes = [{"thumbnail": str(thumb_path), "scene_index": 0}]
        scores = engine._thumbnail_scores(scenes)
        assert len(scores) == 1
        assert scores[0] > 0.0

    def test_invalid_thumbnail_path(self, tmp_project):
        engine = ScoringEngine(tmp_project)
        scenes = [{"thumbnail": "/nonexistent/path.jpg", "scene_index": 0}]
        scores = engine._thumbnail_scores(scenes)
        assert scores[0] == 0.5  # Fallback


# ─── Weight Normalization Tests ──────────────────────────────────────

class TestWeightNormalization:
    def test_unnormalized_weights(self, tmp_project, sample_scenes):
        engine = ScoringEngine(tmp_project)
        scenes = engine.score(
            video_path="",
            scenes=sample_scenes,
            weights={"visual": 2.0, "transcript": 1.0, "audio": 1.0},
            use_llm=False,
        )
        for scene in scenes:
            assert scene["combined_score"] is not None
            assert 0.0 <= scene["combined_score"] <= 1.0

    def test_zero_weight_sum_raises(self, tmp_project, sample_scenes):
        engine = ScoringEngine(tmp_project)
        with pytest.raises(ValueError, match="Weight sum"):
            engine.score(
                video_path="",
                scenes=sample_scenes,
                weights={"visual": 0.0, "transcript": 0.0, "audio": 0.0},
                use_llm=False,
            )

    def test_custom_weights_respected(self, tmp_project, sample_scenes):
        engine = ScoringEngine(tmp_project)
        # Heavy visual weight
        scenes = engine.score(
            video_path="",
            scenes=[make_scene(0, 0, 5, "test text")],
            weights={"visual": 0.8, "transcript": 0.1, "audio": 0.1},
            use_llm=False,
        )
        assert scenes[0]["combined_score"] is not None


# ─── Score Combination & Ranking Tests ───────────────────────────────

class TestScoreCombination:
    def test_all_scenes_scored(self, tmp_project, sample_scenes):
        engine = ScoringEngine(tmp_project)
        scenes = engine.score(
            video_path="",
            scenes=sample_scenes,
            use_llm=False,
        )
        assert len(scenes) == 5
        for scene in scenes:
            assert "visual_score" in scene
            assert "transcript_score" in scene
            assert "audio_score" in scene
            assert "combined_score" in scene
            assert "rank" in scene
            assert 0.0 <= scene["combined_score"] <= 1.0

    def test_ranking_assigned(self, tmp_project, sample_scenes):
        engine = ScoringEngine(tmp_project)
        scenes = engine.score(
            video_path="",
            scenes=sample_scenes,
            use_llm=False,
        )
        ranks = sorted([s["rank"] for s in scenes])
        assert ranks == [1, 2, 3, 4, 5]

    def test_best_scene_rank_1(self, tmp_project):
        engine = ScoringEngine(tmp_project)
        scenes = [
            make_scene(0, 0, 5, ""),  # Empty
            make_scene(1, 5, 10, "Breaking news! Amazing exclusive reveal!"),  # Exciting
        ]
        scored = engine.score(video_path="", scenes=scenes, use_llm=False)
        ranked = sorted(scored, key=lambda s: s["rank"])
        assert ranked[0]["scene_index"] == 1  # Exciting scene ranks first

    def test_scenes_saved(self, tmp_project, sample_scenes):
        engine = ScoringEngine(tmp_project)
        engine.score(video_path="", scenes=sample_scenes, use_llm=False)
        saved_path = Path(tmp_project) / "scenes.json"
        assert saved_path.exists()
        with open(saved_path) as f:
            saved = json.load(f)
        assert len(saved) == 5
        assert all("combined_score" in s for s in saved)


# ─── Top-N Selection Tests ───────────────────────────────────────────

class TestTopNSelection:
    def test_basic_top_n(self, tmp_project, scored_scenes):
        engine = ScoringEngine(tmp_project)
        top = engine.select_top_n(scored_scenes, n=3)
        assert len(top) <= 3
        # All selected scenes should have combined_score
        for s in top:
            assert s["combined_score"] is not None

    def test_top_n_sorted_by_time(self, tmp_project, scored_scenes):
        engine = ScoringEngine(tmp_project)
        top = engine.select_top_n(scored_scenes, n=3)
        indices = [s["scene_index"] for s in top]
        assert indices == sorted(indices)

    def test_min_duration_filter(self, tmp_project, scored_scenes):
        engine = ScoringEngine(tmp_project, thresholds={"min_score": 0.0, "min_duration": 3.0, "action_similarity": 0.75})
        top = engine.select_top_n(scored_scenes, n=5, min_duration=3.0)
        for s in top:
            assert s["duration"] >= 3.0

    def test_min_score_filter(self, tmp_project, scored_scenes):
        engine = ScoringEngine(tmp_project)
        top = engine.select_top_n(scored_scenes, n=5, min_score=0.99)
        # Very high threshold should filter most/all
        assert len(top) <= 1

    def test_n_larger_than_scenes(self, tmp_project):
        engine = ScoringEngine(tmp_project)
        scenes = [make_scene(0, 0, 5, "test")]
        scenes[0]["combined_score"] = 0.5
        scenes[0]["duration"] = 5.0
        top = engine.select_top_n(scenes, n=10)
        assert len(top) == 1

    def test_empty_scenes(self, tmp_project):
        engine = ScoringEngine(tmp_project)
        top = engine.select_top_n([], n=5)
        assert top == []

    def test_top_n_with_defaults(self, tmp_project):
        engine = ScoringEngine(tmp_project)
        scenes = [
            {**make_scene(0, 0, 5, "good"), "combined_score": 0.8, "duration": 5.0},
            {**make_scene(1, 5, 6, "short"), "combined_score": 0.9, "duration": 0.5},  # Too short
            {**make_scene(2, 6, 10, "ok"), "combined_score": 0.1, "duration": 4.0},  # Below min_score
            {**make_scene(3, 10, 15, "best"), "combined_score": 0.95, "duration": 5.0},
        ]
        top = engine.select_top_n(scenes, n=5, min_duration=1.0, min_score=0.15)
        indices = [s["scene_index"] for s in top]
        assert 0 in indices
        assert 3 in indices
        assert 1 not in indices  # Too short
        assert 2 not in indices  # Below min_score


# ─── analyze() Convenience Method Tests ──────────────────────────────

class TestAnalyze:
    def test_analyze_returns_highlights(self, tmp_project, sample_scenes):
        engine = ScoringEngine(tmp_project)
        result = engine.analyze(
            video_path="",
            scenes=sample_scenes,
            top_n=3,
            use_llm=False,
        )
        assert "scenes" in result
        assert "highlights" in result
        assert "highlight_indices" in result
        assert len(result["scenes"]) == 5
        assert len(result["highlights"]) <= 3
        assert len(result["highlight_indices"]) <= 3

    def test_analyze_highlights_are_scored(self, tmp_project, sample_scenes):
        engine = ScoringEngine(tmp_project)
        result = engine.analyze(
            video_path="",
            scenes=sample_scenes,
            top_n=2,
            use_llm=False,
        )
        for h in result["highlights"]:
            assert "combined_score" in h
            assert "visual_score" in h
            assert "transcript_score" in h
            assert "audio_score" in h
            assert "rank" in h


# ─── OpenClip Integration Tests (mocked) ─────────────────────────────

class TestOpenClipMocked:
    """Tests for OpenClip visual scoring with mocked dependencies."""

    def test_openclip_scores_with_mock(self, tmp_project):
        """Verify OpenClip scoring path is exercised when the module is available."""
        torch = pytest.importorskip("torch")
        import scoring as sc_mod

        scenes = [make_scene(0, 0, 5, "test")]
        engine = ScoringEngine(tmp_project)

        # Mock the CLIP components
        mock_model = MagicMock()
        mock_preprocess = MagicMock()
        mock_tokenizer = MagicMock()

        # Set up encode_text to return normalized tensors
        fake_emb = torch.tensor([[0.5, 0.5, 0.5, 0.5]])
        mock_model.encode_text.return_value = fake_emb
        mock_model.encode_image.return_value = fake_emb
        mock_model.eval.return_value = None

        engine._clip_model = mock_model
        engine._clip_preprocess = mock_preprocess
        engine._clip_tokenizer = mock_tokenizer

        # We also need cv2 for frame extraction, so mock that too
        with patch.object(sc_mod, 'HAS_OPENCLIP', True), \
             patch('cv2.VideoCapture') as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap.get.return_value = 30.0  # fps
            mock_cap.read.return_value = (True, np.zeros((100, 100, 3), dtype=np.uint8))
            mock_cap_cls.return_value = mock_cap

            scores = engine._openclip_visual_scores("fake.mp4", scenes)

        assert len(scores) == 1
        assert 0.0 <= scores[0] <= 1.0

    def test_openclip_lazy_load(self, tmp_project):
        """Verify model is None before first use."""
        engine = ScoringEngine(tmp_project)
        assert engine._clip_model is None


# ─── Audio Energy Scoring Tests (mocked ffmpeg) ─────────────────────

class TestAudioEnergy:
    def test_short_scene_default(self, tmp_project):
        engine = ScoringEngine(tmp_project)
        scenes = [{"duration": 0.3, "start_time": 0.0, "scene_index": 0}]
        scores = engine._audio_energy_scores("fake.mp4", scenes)
        assert scores[0] == 0.3

    @patch("subprocess.run")
    def test_ffmpeg_failure(self, mock_run, tmp_project):
        mock_run.return_value = MagicMock(returncode=1)
        engine = ScoringEngine(tmp_project)
        scenes = [{"duration": 5.0, "start_time": 0.0, "scene_index": 0}]
        scores = engine._audio_energy_scores("fake.mp4", scenes)
        assert scores[0] == 0.3  # Fallback

    @patch("subprocess.run")
    def test_audio_scoring_with_mock_wav(self, mock_run, tmp_project):
        """Test audio scoring with a synthetic WAV file."""
        import struct

        # Create a synthetic WAV file
        tmp_wav = Path(tmp_project) / "_temp_audio_0.wav"
        sample_rate = 8000
        duration = 1.0
        n_samples = int(sample_rate * duration)

        # Generate a sine wave
        t = np.linspace(0, duration, n_samples, endpoint=False)
        signal = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16)

        # Write minimal WAV
        with open(tmp_wav, "wb") as f:
            # WAV header
            f.write(b"RIFF")
            f.write(struct.pack("<I", 36 + len(signal.tobytes())))
            f.write(b"WAVE")
            f.write(b"fmt ")
            f.write(struct.pack("<I", 16))  # chunk size
            f.write(struct.pack("<H", 1))   # PCM
            f.write(struct.pack("<H", 1))   # mono
            f.write(struct.pack("<I", sample_rate))
            f.write(struct.pack("<I", sample_rate * 2))
            f.write(struct.pack("<H", 2))   # block align
            f.write(struct.pack("<H", 16))  # bits per sample
            f.write(b"data")
            f.write(struct.pack("<I", len(signal.tobytes())))
            f.write(signal.tobytes())

        # Mock subprocess to do nothing (file already exists)
        mock_run.return_value = MagicMock(returncode=0)

        engine = ScoringEngine(tmp_project)
        scenes = [{"duration": 1.0, "start_time": 0.0, "scene_index": 0}]
        scores = engine._audio_energy_scores("fake.mp4", scenes)

        assert len(scores) == 1
        assert 0.0 < scores[0] <= 1.0  # Sine wave should have energy


# ─── Integration Test ────────────────────────────────────────────────

class TestIntegration:
    def test_full_pipeline_no_video(self, tmp_project):
        """Test the full score → select pipeline without a real video."""
        engine = ScoringEngine(tmp_project)
        scenes = [
            make_scene(0, 0, 5, "Welcome everyone to this amazing show!"),
            make_scene(1, 5, 10, ""),
            make_scene(2, 10, 15, "Breaking news! Incredible exclusive reveal!"),
            make_scene(3, 15, 20, "Some normal dialogue here."),
            make_scene(4, 20, 25, "Wow! The best thing ever! You'll love it!"),
        ]

        result = engine.analyze(
            video_path="",
            scenes=scenes,
            top_n=3,
            use_llm=False,
        )

        assert len(result["scenes"]) == 5
        assert len(result["highlights"]) <= 3
        assert all(h["combined_score"] >= 0.0 for h in result["highlights"])

        # Scene 2 and 4 should be in highlights (exciting transcripts)
        highlight_indices = result["highlight_indices"]
        assert len(highlight_indices) <= 3
        assert all(isinstance(idx, int) for idx in highlight_indices)

    def test_score_idempotent(self, tmp_project):
        """Scoring the same scenes twice should produce same results."""
        engine = ScoringEngine(tmp_project)
        scenes1 = [make_scene(0, 0, 5, "Test content")]
        scenes2 = [make_scene(0, 0, 5, "Test content")]

        r1 = engine.score(video_path="", scenes=scenes1, use_llm=False)
        r2 = engine.score(video_path="", scenes=scenes2, use_llm=False)

        assert r1[0]["combined_score"] == r2[0]["combined_score"]
