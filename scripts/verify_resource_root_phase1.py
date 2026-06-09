#!/usr/bin/env python3
import asyncio
import os
import sys
import tempfile
import types


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

def ensure_multipart_runtime():
    try:
        from python_multipart.multipart import parse_options_header  # type: ignore # noqa: F401
        return
    except Exception:
        pass
    py_mod = types.ModuleType("python_multipart")
    py_mod.__version__ = "0.0.13"
    py_sub = types.ModuleType("python_multipart.multipart")
    py_sub.parse_options_header = lambda value: ("", {})
    sys.modules["python_multipart"] = py_mod
    sys.modules["python_multipart.multipart"] = py_sub

    multipart_mod = types.ModuleType("multipart")
    multipart_mod.__version__ = "0.0.13"
    multipart_sub = types.ModuleType("multipart.multipart")
    multipart_sub.parse_options_header = lambda value: ("", {})
    sys.modules["multipart"] = multipart_mod
    sys.modules["multipart.multipart"] = multipart_sub

ensure_multipart_runtime()

import main as app_main  # noqa: E402


def tiny_workflow():
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": "smoke-model.safetensors",
            },
        }
    }


async def run_check():
    env_keys = ("AITOOL_RESOURCE_ROOT", "RESOURCE_ROOT")
    env_backup = {k: os.environ.get(k) for k in env_keys}
    original_instances = list(app_main.COMFYUI_INSTANCES)
    try:
        for key in env_keys:
            os.environ[key] = ""
        cfg = app_main.get_resource_root_config()
        assert cfg.get("configured") is False
        state = app_main.inspect_resource_root("", create_missing=False)
        assert state.get("status") == "unconfigured"

        with tempfile.TemporaryDirectory(prefix="aitool-phase1-") as tmpdir:
            state_temp = app_main.inspect_resource_root(tmpdir, create_missing=False)
            assert state_temp.get("available") is True
            assert state_temp.get("summary", {}).get("subdir_missing", 0) > 0

            model_dir = os.path.join(tmpdir, "models", "checkpoints")
            os.makedirs(model_dir, exist_ok=True)
            model_path = os.path.join(model_dir, "smoke-model.safetensors")
            with open(model_path, "wb") as f:
                f.write(b"stub")

            deps = [{"input_key": "ckpt_name", "value": "smoke-model.safetensors"}]
            detected = app_main.detect_model_dependencies_in_resource_root(
                deps,
                app_main.inspect_resource_root(tmpdir, create_missing=False),
            )
            assert detected["items"][0]["status"] == "exists"
            assert detected["items"][0]["path"] == model_path

            os.environ["AITOOL_RESOURCE_ROOT"] = tmpdir
            os.environ["RESOURCE_ROOT"] = tmpdir
            app_main.COMFYUI_INSTANCES = []
            payload = app_main.WorkflowImportPlanRequest(
                source_type="workflow_json",
                workflow_json=tiny_workflow(),
                workflow_name="phase1-verify",
                save_workflow=False,
            )
            result = await app_main.import_workflow_plan(payload)
            dep_items = result.get("model_dependencies") or []
            assert dep_items and dep_items[0].get("status") == "exists"
            assert any("60 盘已存在" in str(item) for item in (result.get("plan_items") or []))

        print("verify_resource_root_phase1: OK")
    finally:
        app_main.COMFYUI_INSTANCES = original_instances
        for key, value in env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    asyncio.run(run_check())
