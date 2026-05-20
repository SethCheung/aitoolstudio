"""Unit tests for comfyui_workflows service layer."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure backend is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.comfyui_workflows import (
    _compute_workflow_summary,
    _save,
    _load,
    delete_workflow,
    duplicate_workflow,
    get_workflow,
    list_workflows,
    reorder_workflows,
    upsert_workflow,
    validate_workflow_json,
)


# ── Helpers ──

_ORIG_CONFIG = None


def setUpModule() -> None:
    global _ORIG_CONFIG
    from services import comfyui_workflows as mod
    _ORIG_CONFIG = str(mod.CONFIG_FILE)
    mod.CONFIG_FILE = Path(tempfile.mktemp(suffix=".json"))


def tearDownModule() -> None:
    from services import comfyui_workflows as mod
    if mod.CONFIG_FILE.exists():
        mod.CONFIG_FILE.unlink()
    mod.CONFIG_FILE = Path(_ORIG_CONFIG)


def _reset_store() -> None:
    from services import comfyui_workflows as mod
    if mod.CONFIG_FILE.exists():
        mod.CONFIG_FILE.unlink()
    mod._load.cache_clear() if hasattr(mod._load, "cache_clear") else None


MINIMAL_WF = {
    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl.safetensors"}},
    "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "cat", "clip": ["1", 1]}},
    "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry", "clip": ["1", 1]}},
    "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
    "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0], "seed": 42, "steps": 20, "cfg": 7, "sampler_name": "euler", "scheduler": "normal", "denoise": 1}},
    "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
    "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "test", "images": ["6", 0]}},
}

WF_WITH_LOADIMAGE = {
    "1": {"class_type": "LoadImage", "inputs": {"image": ""}},
    "2": {"class_type": "KSampler", "inputs": {"model": ["3", 0], "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["1", 0], "seed": 0, "steps": 20, "cfg": 7, "sampler_name": "euler", "scheduler": "normal", "denoise": 1}},
    "3": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd.safetensors"}},
    "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["3", 1]}},
    "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "bad", "clip": ["3", 1]}},
    "6": {"class_type": "VAEDecode", "inputs": {"samples": ["2", 0], "vae": ["3", 2]}},
    "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "img2img", "images": ["6", 0]}},
}


class TestValidateWorkflowJson(unittest.TestCase):

    def test_valid_workflow(self) -> None:
        validate_workflow_json(MINIMAL_WF)

    def test_empty_object(self) -> None:
        with self.assertRaises(ValueError):
            validate_workflow_json({})

    def test_non_dict(self) -> None:
        with self.assertRaises(ValueError):
            validate_workflow_json([])
        with self.assertRaises(ValueError):
            validate_workflow_json("hello")

    def test_missing_class_type(self) -> None:
        bad = {"1": {"inputs": {}}}
        with self.assertRaises(ValueError):
            validate_workflow_json(bad)

    def test_non_string_node_id(self) -> None:
        bad = {1: {"class_type": "Foo", "inputs": {}}}
        with self.assertRaises(ValueError):
            validate_workflow_json(bad)


class TestComputeWorkflowSummary(unittest.TestCase):

    def test_empty(self) -> None:
        s = _compute_workflow_summary({})
        self.assertEqual(s["node_count"], 0)
        self.assertEqual(s["output_types"], [])
        self.assertEqual(s["required_inputs"], [])

    def test_txt2img(self) -> None:
        s = _compute_workflow_summary(MINIMAL_WF)
        self.assertEqual(s["node_count"], 7)
        self.assertIn("image", s["output_types"])
        self.assertNotIn("video", s["output_types"])
        self.assertEqual(s["required_inputs"], [])

    def test_img2img_requires_source(self) -> None:
        s = _compute_workflow_summary(WF_WITH_LOADIMAGE)
        self.assertIn("source_image", s["required_inputs"])

    def test_patchable_inputs(self) -> None:
        s = _compute_workflow_summary(MINIMAL_WF)
        self.assertIn("prompt", s["patchable_inputs"])
        self.assertIn("seed", s["patchable_inputs"])
        self.assertIn("size", s["patchable_inputs"])

    def test_non_dict_returns_zeros(self) -> None:
        s = _compute_workflow_summary("bad")
        self.assertEqual(s["node_count"], 0)


class TestWorkflowCRUD(unittest.TestCase):

    def setUp(self) -> None:
        _reset_store()

    def test_create_and_list(self) -> None:
        wf = upsert_workflow({"name": "Test WF", "category": "image", "workflow_json": MINIMAL_WF})
        self.assertEqual(wf["name"], "Test WF")
        self.assertIn("summary", wf)
        self.assertEqual(wf["summary"]["node_count"], 7)

        all_wf = list_workflows()
        self.assertGreaterEqual(len(all_wf), 1)

    def test_update_preserves_sort_order(self) -> None:
        wf1 = upsert_workflow({"name": "First", "category": "image", "workflow_json": MINIMAL_WF, "sort_order": 5})
        self.assertEqual(wf1["sort_order"], 5)

        # Update without sort_order → should preserve 5
        wf2 = upsert_workflow({"name": "First Renamed", "category": "image", "workflow_json": MINIMAL_WF}, workflow_id=wf1["id"])
        self.assertEqual(wf2["sort_order"], 5)
        self.assertEqual(wf2["name"], "First Renamed")

        # Update with explicit sort_order → should override
        wf3 = upsert_workflow({"name": "First", "category": "image", "workflow_json": MINIMAL_WF, "sort_order": 99}, workflow_id=wf1["id"])
        self.assertEqual(wf3["sort_order"], 99)

    def test_delete(self) -> None:
        wf = upsert_workflow({"name": "Delete Me", "category": "image", "workflow_json": MINIMAL_WF})
        self.assertTrue(delete_workflow(wf["id"]))
        self.assertFalse(delete_workflow(wf["id"]))
        self.assertIsNone(get_workflow(wf["id"], include_disabled=True))

    def test_get_workflow_include_disabled(self) -> None:
        upsert_workflow({"name": "Hidden", "category": "image", "enabled": False, "workflow_json": MINIMAL_WF})
        wf = get_workflow("hidden", include_disabled=False)
        self.assertIsNone(wf)
        wf2 = get_workflow("hidden", include_disabled=True)
        self.assertIsNotNone(wf2)

    def test_list_include_disabled(self) -> None:
        upsert_workflow({"name": "Visible", "category": "image", "enabled": True, "workflow_json": MINIMAL_WF})
        upsert_workflow({"name": "Hidden2", "category": "image", "enabled": False, "workflow_json": MINIMAL_WF})
        enabled = list_workflows(include_disabled=False)
        all_wf = list_workflows(include_disabled=True)
        self.assertLess(len(enabled), len(all_wf))

    def test_duplicate_workflow_disabled(self) -> None:
        orig = upsert_workflow({"name": "Original", "category": "image", "enabled": True, "workflow_json": MINIMAL_WF})
        dup = duplicate_workflow(orig["id"])
        self.assertIsNotNone(dup)
        self.assertFalse(dup["enabled"])
        self.assertIn("(副本)", dup["name"])
        self.assertNotEqual(dup["id"], orig["id"])
        self.assertIn("summary", dup)

    def test_duplicate_nonexistent(self) -> None:
        self.assertIsNone(duplicate_workflow("no-such-id"))


class TestReorder(unittest.TestCase):

    def setUp(self) -> None:
        _reset_store()

    def test_reorder_sets_sort_order(self) -> None:
        cats = ["image", "video"]
        for c in cats:
            for i in range(3):
                upsert_workflow({"name": f"{c}-{i}", "category": c, "workflow_json": MINIMAL_WF, "sort_order": i}, workflow_id=f"{c}-{i}")

        # Reverse image category order
        self.assertTrue(reorder_workflows("image", ["image-2", "image-1", "image-0"]))

        wf_list = list_workflows(include_disabled=True)
        for wf in wf_list:
            if wf["category"] == "image" and wf["id"] in {"image-0", "image-1", "image-2"}:
                expected = {"image-2": 0, "image-1": 1, "image-0": 2}
                self.assertEqual(wf["sort_order"], expected[wf["id"]], f"Wrong sort for {wf['id']}")

    def test_reorder_noop(self) -> None:
        self.assertFalse(reorder_workflows("image", []))


class TestSummaryOnAllEndpoints(unittest.TestCase):

    def setUp(self) -> None:
        _reset_store()

    def test_list_workflows_includes_summary(self) -> None:
        upsert_workflow({"name": "S", "category": "image", "workflow_json": MINIMAL_WF})
        for wf in list_workflows(include_disabled=True):
            self.assertIn("summary", wf)
            self.assertIsInstance(wf["summary"], dict)

    def test_get_workflow_includes_summary(self) -> None:
        upsert_workflow({"name": "G", "category": "image", "workflow_json": MINIMAL_WF})
        wf = get_workflow("g", include_disabled=True)
        self.assertIn("summary", wf)
        self.assertEqual(wf["summary"]["node_count"], 7)


if __name__ == "__main__":
    unittest.main()
