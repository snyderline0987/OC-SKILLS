"""Unit tests for taste_test.py — QC Pipeline"""
import json
import os
import sys
import pytest

from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from taste_test import TasteTester


@pytest.fixture
def tmp_project(tmp_path):
    project_dir = tmp_path / "test_project" / "outputs"
    project_dir.mkdir(parents=True)
    return str(tmp_path / "test_project")


class TestRecipeCompliance:
    def test_aspect_ratio_check_pass(self, tmp_project):
        tester = TasteTester(tmp_project)
        probe = {"width": 1920, "height": 1080, "duration": 30}
        recipe = {"aspect_ratio": "16:9", "target_duration": "20-40s"}
        result = tester._check_recipe_compliance(probe, recipe)
        assert result["compliant"]

    def test_aspect_ratio_check_fail(self, tmp_project):
        tester = TasteTester(tmp_project)
        probe = {"width": 1080, "height": 1920, "duration": 30}
        recipe = {"aspect_ratio": "16:9", "target_duration": "20-40s"}
        result = tester._check_recipe_compliance(probe, recipe)
        assert not result["compliant"]

    def test_duration_range_check(self, tmp_project):
        tester = TasteTester(tmp_project)
        probe = {"width": 1920, "height": 1080, "duration": 15}
        recipe = {"aspect_ratio": "16:9", "target_duration": "20-40s"}
        result = tester._check_recipe_compliance(probe, recipe)
        assert not result["compliant"]  # 15s is outside 20-40s

    def test_no_recipe(self, tmp_project):
        tester = TasteTester(tmp_project)
        probe = {"width": 1920, "height": 1080, "duration": 30}
        result = tester._check_recipe_compliance(probe, {})
        assert result["compliant"]


class TestQCReport:
    def test_missing_file(self, tmp_project):
        tester = TasteTester(tmp_project)
        report = tester.run_qc("/nonexistent/video.mp4", generate_preview=False)
        assert not report["passed"]
        assert "not found" in report.get("error", "").lower()
