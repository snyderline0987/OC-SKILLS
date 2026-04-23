"""Unit tests for pantry.py — Metadata Storage"""
import json
import os
import tempfile
import pytest

from pathlib import Path

# Add scripts to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from pantry import Pantry


@pytest.fixture
def tmp_pantry(tmp_path):
    return Pantry(base_dir=str(tmp_path / "projects"))


class TestProjectCRUD:
    def test_create_project(self, tmp_pantry):
        meta = tmp_pantry.create_project("test1", title="Test Project", source="video.mp4")
        assert meta["id"] == "test1"
        assert meta["title"] == "Test Project"
        assert meta["source"] == "video.mp4"
        assert meta["status"] == "uploaded"

    def test_create_project_auto_id(self, tmp_pantry):
        meta = tmp_pantry.create_project(title="Auto ID")
        assert meta["id"]  # Should have an auto-generated ID
        assert meta["title"] == "Auto ID"

    def test_create_project_duplicate(self, tmp_pantry):
        tmp_pantry.create_project("dup1")
        with pytest.raises(FileExistsError):
            tmp_pantry.create_project("dup1")

    def test_get_project(self, tmp_pantry):
        tmp_pantry.create_project("get1", title="Get Me")
        meta = tmp_pantry.get_project("get1")
        assert meta["title"] == "Get Me"

    def test_get_project_not_found(self, tmp_pantry):
        with pytest.raises(FileNotFoundError):
            tmp_pantry.get_project("nonexistent")

    def test_update_project(self, tmp_pantry):
        tmp_pantry.create_project("upd1", title="Before")
        meta = tmp_pantry.update_project("upd1", {"title": "After", "status": "analyzed"})
        assert meta["title"] == "After"
        assert meta["status"] == "analyzed"

    def test_delete_project(self, tmp_pantry):
        tmp_pantry.create_project("del1")
        tmp_pantry.delete_project("del1")
        with pytest.raises(FileNotFoundError):
            tmp_pantry.get_project("del1")

    def test_list_projects(self, tmp_pantry):
        tmp_pantry.create_project("list1", title="First")
        tmp_pantry.create_project("list2", title="Second")
        projects = tmp_pantry.list_projects()
        assert len(projects) == 2
        titles = [p["title"] for p in projects]
        assert "First" in titles
        assert "Second" in titles


class TestScenes:
    def test_save_and_load_scenes(self, tmp_pantry):
        tmp_pantry.create_project("scenes1")
        scenes = [
            {"scene_index": 0, "start_time": 0.0, "end_time": 5.0, "duration": 5.0},
            {"scene_index": 1, "start_time": 5.0, "end_time": 10.0, "duration": 5.0},
        ]
        tmp_pantry.save_scenes("scenes1", scenes)
        loaded = tmp_pantry.load_scenes("scenes1")
        assert len(loaded) == 2
        assert loaded[0]["scene_index"] == 0
        assert loaded[1]["duration"] == 5.0

    def test_update_scene(self, tmp_pantry):
        tmp_pantry.create_project("upd_scene")
        scenes = [
            {"scene_index": 0, "start_time": 0.0, "end_time": 5.0},
            {"scene_index": 1, "start_time": 5.0, "end_time": 10.0},
        ]
        tmp_pantry.save_scenes("upd_scene", scenes)
        updated = tmp_pantry.update_scene("upd_scene", 0, {"visual_score": 0.85})
        assert updated["visual_score"] == 0.85

    def test_update_scene_out_of_range(self, tmp_pantry):
        tmp_pantry.create_project("oor")
        tmp_pantry.save_scenes("oor", [{"scene_index": 0}])
        with pytest.raises(IndexError):
            tmp_pantry.update_scene("oor", 5, {"score": 1.0})

    def test_load_scenes_empty(self, tmp_pantry):
        tmp_pantry.create_project("empty")
        scenes = tmp_pantry.load_scenes("empty")
        assert scenes == []


class TestSelectionAndOutput:
    def test_save_and_load_selection(self, tmp_pantry):
        tmp_pantry.create_project("sel1")
        selection = {"scene_indices": [0, 2, 5], "recipe": "spicy_trailer"}
        tmp_pantry.save_selection("sel1", selection)
        loaded = tmp_pantry.load_selection("sel1")
        assert loaded["scene_indices"] == [0, 2, 5]

    def test_save_and_load_outputs(self, tmp_pantry):
        tmp_pantry.create_project("out1")
        output1 = {"filename": "output1.mp4", "duration": 30.0}
        output2 = {"filename": "output2.mp4", "duration": 45.0}
        tmp_pantry.save_output("out1", output1)
        tmp_pantry.save_output("out1", output2)
        outputs = tmp_pantry.load_outputs("out1")
        assert len(outputs) == 2

    def test_qc_report(self, tmp_pantry):
        tmp_pantry.create_project("qc1")
        report = {"passed": True, "issues": []}
        tmp_pantry.save_qc_report("qc1", "out1", report)
        loaded = tmp_pantry.load_qc_report("qc1", "out1")
        assert loaded["passed"] is True
