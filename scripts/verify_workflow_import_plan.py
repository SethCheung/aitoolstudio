#!/usr/bin/env python3
import asyncio
import functools
import http.server
import json
import os
import sys
import tempfile
import threading
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

UI_WORKFLOW_PATH = "/Users/apple/Downloads/1-Aiden-极致真实摄影人像工作流，文生图（小白福音）.json"


def load_sample_workflow():
    sample_path = os.path.join(ROOT_DIR, "workflows", "custom", "aitool-smoke-sd15.json")
    with open(sample_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_ui_workflow():
    with open(UI_WORKFLOW_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        return


def set_env_temporarily(key, value):
    old_value = os.environ.get(key)
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value
    return old_value


def restore_env(key, old_value):
    if old_value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = old_value


async def run_check():
    ms_repos = [{"Path": "owner", "Name": "demo-model", "Revision": "master"}]
    ms_files = {
        "owner/demo-model": {
            "Data": {
                "Files": [
                    {"Name": "demo-model.safetensors", "Path": "demo-model.safetensors", "Type": "blob"},
                    {"Name": "README.md", "Path": "README.md", "Type": "blob"},
                ]
            }
        }
    }
    ms_candidates = app_main.modelscope_model_download_candidates_from_api(
        ms_repos,
        ms_files,
        "demo-model.safetensors",
    )
    assert ms_candidates
    assert ms_candidates[0]["url"] == "https://www.modelscope.cn/models/owner/demo-model/resolve/master/demo-model.safetensors"
    assert ms_candidates[0]["source"] == "modelscope"
    assert ms_candidates[0]["note"] == "ModelScope 仓库文件匹配"
    assert app_main.validate_model_candidate_download_url(
        "https://www.modelscope.cn/models/owner/repo/resolve/master/model.safetensors",
        "model.safetensors",
    )
    assert app_main.validate_model_candidate_download_url(
        "https://www.modelscope.cn/api/v1/models/owner/repo/repo?Revision=master&FilePath=folder/model.safetensors",
        "model.safetensors",
    )
    for bad_url in (
        "https://www.modelscope.cn/models/owner/repo",
        "https://www.modelscope.cn/models/owner/repo/files/model.safetensors",
        "https://www.modelscope.cn/api/v1/models/owner/repo/repo?Revision=master",
        "https://www.modelscope.cn/api/v1/models/owner/repo/repo/files?Revision=master",
    ):
        try:
            app_main.validate_model_candidate_download_url(bad_url, "model.safetensors")
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ModelScope URL rejection: {bad_url}")

    hf_repos = [{"id": "owner/demo-model"}]
    hf_details = {
        "owner/demo-model": {
            "siblings": [
                {"rfilename": "demo-model.safetensors"},
                {"rfilename": "README.md"},
            ]
        }
    }
    hf_candidates = app_main.hf_model_download_candidates_from_api(
        hf_repos,
        hf_details,
        "demo-model.safetensors",
    )
    assert hf_candidates
    assert hf_candidates[0]["url"] == "https://huggingface.co/owner/demo-model/resolve/main/demo-model.safetensors?download=true"
    assert hf_candidates[0]["source"] == "huggingface"
    priority_candidates = [
        {**hf_candidates[0], "score": 100},
        {**ms_candidates[0], "score": 35},
    ]
    priority_candidates.sort(key=app_main.model_download_candidate_sort_key)
    assert priority_candidates[0]["source"] == "modelscope"
    exact_priority_candidates = [
        {**hf_candidates[0], "score": 100},
        {**ms_candidates[0], "score": 100},
    ]
    selected_exact = app_main.select_high_confidence_model_candidate(
        exact_priority_candidates,
        "demo-model.safetensors",
    )
    assert selected_exact and selected_exact["source"] == "modelscope"
    assert app_main.select_high_confidence_model_candidate(
        [{**ms_candidates[0], "filename": "other.safetensors", "score": 100}],
        "demo-model.safetensors",
    ) is None
    assert app_main.select_high_confidence_model_candidate(
        [{**ms_candidates[0], "score": 88}],
        "demo-model.safetensors",
    ) is None
    for numeric_target in ("0.3", "0.5", "1"):
        assert app_main.workflow_auto_model_target_skip_reason({"title": numeric_target}, numeric_target)
    assert not app_main.workflow_auto_model_target_skip_reason(
        {"title": "demo-model.safetensors"},
        "demo-model.safetensors",
    )
    assert app_main.validate_model_candidate_download_url(
        "https://huggingface.co/owner/repo/resolve/main/model.safetensors?download=true",
        "model.safetensors",
    )
    assert app_main.validate_model_candidate_download_url(
        "https://example.com/model.safetensors",
        "model.safetensors",
    )
    for bad_url in ("https://huggingface.co/comfy-org/", "https://example.com/page"):
        try:
            app_main.validate_model_candidate_download_url(bad_url, "model.safetensors")
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected model candidate URL rejection: {bad_url}")
    assert app_main.hf_model_download_candidates_from_api([], {}, "") == []
    empty_candidates, empty_errors = app_main.find_huggingface_model_candidates("", "")
    assert empty_candidates == [] and empty_errors
    ai_candidates = app_main.parse_ai_model_candidate_urls(
        '{"candidates":[{"url":"ftp://invalid/model.safetensors"},{"url":"https://example.com/model.safetensors"}]}',
        "model.safetensors",
    )
    assert len(ai_candidates) == 1 and ai_candidates[0]["url"].startswith("https://")
    ai_ms_candidates = app_main.parse_ai_model_candidate_urls(
        '{"candidates":[{"url":"https://www.modelscope.cn/models/owner/repo/resolve/master/model.safetensors"}]}',
        "model.safetensors",
    )
    assert len(ai_ms_candidates) == 1
    assert ai_ms_candidates[0]["source"] == "modelscope"
    assert "ModelScope" in ai_ms_candidates[0]["note"]
    mixed_ai_candidates = app_main.parse_ai_model_candidate_urls(
        "Maybe https://huggingface.co/comfy-org/ or https://example.com/model.safetensors",
        "model.safetensors",
    )
    assert [item["url"] for item in mixed_ai_candidates] == ["https://example.com/model.safetensors"]
    direct_action = app_main.WorkflowModelCandidatesRequest(
        title="direct-model.safetensors",
        category="checkpoints",
    )
    assert app_main.workflow_model_candidate_request_action(direct_action)["title"] == "direct-model.safetensors"
    fake_request = types.SimpleNamespace(state=types.SimpleNamespace(current_user={"is_admin": True}))
    original_ms_candidates = app_main.find_modelscope_model_candidates
    original_hf_candidates = app_main.find_huggingface_model_candidates
    original_ai_candidates = app_main.find_ai_model_candidates
    original_start_task = app_main.start_workflow_install_task
    try:
        ai_called = {"value": False}
        def unexpected_ai_candidates(action, query, target):
            ai_called["value"] = True
            return [], ["unexpected ai"]

        app_main.find_modelscope_model_candidates = lambda query, target: (
            [{**ms_candidates[0], "score": 35}],
            [],
        )
        app_main.find_huggingface_model_candidates = lambda query, target: (
            [{**hf_candidates[0], "score": 100}],
            [],
        )
        app_main.find_ai_model_candidates = unexpected_ai_candidates
        sorted_result = app_main.workflow_install_model_candidates(
            app_main.WorkflowModelCandidatesRequest(title="demo-model.safetensors"),
            fake_request,
        )
        assert [item["source"] for item in sorted_result["candidates"][:2]] == ["modelscope", "huggingface"]
        assert ai_called["value"] is False

        app_main.find_modelscope_model_candidates = lambda query, target: ([], ["ms empty"])
        app_main.find_huggingface_model_candidates = lambda query, target: ([], ["empty query"])
        app_main.find_ai_model_candidates = lambda action, query, target: ([], ["ai skipped"])
        empty_result = app_main.workflow_install_model_candidates(app_main.WorkflowModelCandidatesRequest(), fake_request)
        assert empty_result["candidates"] == []
        assert empty_result["errors"]

        started_actions = []
        def fake_start_task(actions, metadata=None):
            started_actions.extend(actions)
            return {
                "task_id": "verify_auto_task",
                "status": "queued",
                "actions": actions,
                "auto_model_downloads": metadata.get("auto_model_downloads") if metadata else {},
                "logs": [],
                "results": [],
            }

        app_main.find_modelscope_model_candidates = lambda query, target: (
            [{**ms_candidates[0], "score": 100}],
            [],
        )
        app_main.find_huggingface_model_candidates = lambda query, target: (
            [{**hf_candidates[0], "score": 100}],
            [],
        )
        app_main.find_ai_model_candidates = unexpected_ai_candidates
        app_main.start_workflow_install_task = fake_start_task
        auto_result = app_main.build_auto_model_downloads_response([
            {
                "id": "auto_model",
                "type": "model_download",
                "title": "demo-model.safetensors",
                "status": "needs_url",
                "category": "checkpoints",
                "value": "demo-model.safetensors",
            },
            {
                "id": "numeric_false_positive",
                "type": "model_download",
                "title": "0.5",
                "status": "needs_url",
                "category": "checkpoints",
                "value": "0.5",
            },
            {
                "id": "custom_node",
                "type": "custom_node_install",
                "title": "SomeNode",
                "status": "needs_repo",
            },
        ])
        assert auto_result["task_id"] == "verify_auto_task"
        assert auto_result["selected"][0]["source"] == "modelscope"
        assert started_actions and started_actions[0]["source_url"].startswith("https://www.modelscope.cn/")
        assert auto_result["manual_required"][0]["id"] == "numeric_false_positive"
        assert auto_result["skipped"][0]["id"] == "custom_node"
    finally:
        app_main.find_modelscope_model_candidates = original_ms_candidates
        app_main.find_huggingface_model_candidates = original_hf_candidates
        app_main.find_ai_model_candidates = original_ai_candidates
        app_main.start_workflow_install_task = original_start_task

    parsed_run = app_main.parse_runninghub_workflow_ref("https://www.runninghub.cn/run/workflow/2058554058318897153")
    assert parsed_run.get("ok") and parsed_run.get("kind") == "workflow"
    parsed_post = app_main.parse_runninghub_workflow_ref("https://www.runninghub.cn/post/2047526849235914754?inviteCode=rh-v1234")
    assert parsed_post.get("ok") and parsed_post.get("kind") == "post"
    parsed_numeric = app_main.parse_runninghub_workflow_ref("2058554058318897153")
    assert parsed_numeric.get("ok") and parsed_numeric.get("kind") == "workflow"

    workflow = app_main.normalize_comfy_api_workflow_payload(load_sample_workflow())
    assert isinstance(workflow, dict) and workflow

    smoke_payload = app_main.WorkflowImportPlanRequest(
        source_type="workflow_json",
        workflow_json=workflow,
        workflow_name="verify-workflow-import",
        save_workflow=False,
    )

    ui_raw = load_ui_workflow()
    ui_workflow = app_main.normalize_comfy_api_workflow_payload(ui_raw)
    assert isinstance(ui_workflow, dict) and ui_workflow
    assert not any(
        isinstance(node, dict) and node.get("class_type") == "Reroute"
        for node in ui_workflow.values()
    )
    ui_model_dependencies = app_main.collect_workflow_model_dependencies(ui_workflow)
    ui_field_candidates = app_main.collect_comfy_workflow_fields(ui_workflow)
    assert len(ui_model_dependencies) > 0
    assert len(ui_field_candidates) > 0

    ui_payload = app_main.WorkflowImportPlanRequest(
        source_type="workflow_json",
        workflow_json=ui_raw,
        workflow_name="verify-ui-workflow-import",
        save_workflow=False,
    )

    original_instances = list(app_main.COMFYUI_INSTANCES)
    original_object_info = app_main.get_backend_object_classes
    old_resource_root = set_env_temporarily("AITOOL_RESOURCE_ROOT", None)
    old_custom_nodes = set_env_temporarily("AITOOL_COMFYUI_CUSTOM_NODES_DIR", None)
    try:
        app_main.COMFYUI_INSTANCES = []
        result = await app_main.import_workflow_plan(smoke_payload)
        with tempfile.TemporaryDirectory() as resource_root:
            os.makedirs(os.path.join(resource_root, "models", "checkpoints"), exist_ok=True)
            os.makedirs(os.path.join(resource_root, "downloads", "cache"), exist_ok=True)
            set_env_temporarily("AITOOL_RESOURCE_ROOT", resource_root)
            app_main.COMFYUI_INSTANCES = ["verify-comfy:8188"]
            app_main.get_backend_object_classes = lambda addr: (set(), "verify missing object_info")
            ui_result = await app_main.import_workflow_plan(ui_payload)

            install_plan = ui_result.get("install_plan") or {}
            install_actions = install_plan.get("actions") or []
            model_actions = [item for item in install_actions if item.get("type") == "model_download"]
            custom_actions = [item for item in install_actions if item.get("type") == "custom_node_install"]
            assert model_actions, "Aiden workflow should produce missing model install actions"
            assert custom_actions, "Aiden workflow should produce custom node install actions"

            with tempfile.TemporaryDirectory() as http_root:
                payload_name = "tiny-model.safetensors"
                payload_bytes = b"verify tiny model\n"
                with open(os.path.join(http_root, payload_name), "wb") as f:
                    f.write(payload_bytes)
                handler = functools.partial(QuietHTTPRequestHandler, directory=http_root)
                server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
                server_thread = threading.Thread(target=server.serve_forever, daemon=True)
                server_thread.start()
                try:
                    port = server.server_address[1]
                    task_id = f"verify_install_{os.getpid()}"
                    download_action = {
                        "id": "verify_model_download",
                        "type": "model_download",
                        "title": payload_name,
                        "status": "ready",
                        "executable": True,
                        "source_url": f"http://127.0.0.1:{port}/{payload_name}",
                        "target_path": "",
                        "target_relative_path": "",
                        "category": "checkpoints",
                        "value": payload_name,
                        "note": "",
                    }
                    with app_main.WORKFLOW_INSTALL_TASK_LOCK:
                        app_main.WORKFLOW_INSTALL_TASKS[task_id] = {
                            "task_id": task_id,
                            "status": "queued",
                            "created_at": app_main.now_utc_iso(),
                            "updated_at": app_main.now_utc_iso(),
                            "started_at": "",
                            "finished_at": "",
                            "actions": [download_action],
                            "logs": [],
                            "results": [],
                        }
                    app_main.execute_workflow_install_task(task_id)
                    task = app_main.workflow_install_task_snapshot(task_id)
                    assert task.get("status") == "done"
                    progress = (task.get("progress") or {}).get("verify_model_download") or {}
                    assert progress.get("downloaded_bytes") == len(payload_bytes)
                    assert progress.get("total_bytes") == len(payload_bytes)
                    assert progress.get("percent") == 100
                    assert progress.get("phase") == "done"
                    assert progress.get("target_relative_path") == f"models/checkpoints/{payload_name}"
                    action_progress = (task.get("actions") or [{}])[0].get("progress") or {}
                    assert action_progress.get("downloaded_bytes") == len(payload_bytes)
                    target_path = os.path.join(resource_root, "models", "checkpoints", payload_name)
                    with open(target_path, "rb") as f:
                        assert f.read() == payload_bytes
                finally:
                    server.shutdown()
                    server.server_close()
    finally:
        app_main.COMFYUI_INSTANCES = original_instances
        app_main.get_backend_object_classes = original_object_info
        restore_env("AITOOL_RESOURCE_ROOT", old_resource_root)
        restore_env("AITOOL_COMFYUI_CUSTOM_NODES_DIR", old_custom_nodes)

    assert result.get("success") is True
    assert result.get("status") == "ok"
    assert isinstance(result.get("workflow"), dict)
    assert isinstance(result.get("model_dependencies"), list)
    assert isinstance(result.get("plan_items"), list)
    assert ui_result.get("success") is True
    assert ui_result.get("status") == "ok"
    assert isinstance(ui_result.get("workflow"), dict)
    assert len(ui_result.get("model_dependencies") or []) > 0
    assert isinstance(ui_result.get("install_plan", {}).get("actions"), list)
    print("verify_workflow_import_plan: OK")
    print(
        "smoke workflow nodes:",
        result.get("workflow", {}).get("node_count"),
        "required classes:",
        result.get("workflow", {}).get("required_class_count"),
        "model deps:",
        len(result.get("model_dependencies") or []),
    )
    print(
        "ui workflow nodes:",
        ui_result.get("workflow", {}).get("node_count"),
        "required classes:",
        ui_result.get("workflow", {}).get("required_class_count"),
        "model deps:",
        len(ui_result.get("model_dependencies") or []),
        "install actions:",
        len(ui_result.get("install_plan", {}).get("actions") or []),
        "field candidates:",
        len(ui_field_candidates),
    )


if __name__ == "__main__":
    asyncio.run(run_check())
