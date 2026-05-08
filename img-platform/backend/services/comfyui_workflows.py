import copy
import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from services.comfyui import _size_for


CONFIG_FILE = Path(__file__).resolve().parents[1] / "config" / "comfyui_workflows.json"
IMPORT_DIR = Path(os.getenv("COMFYUI_WORKFLOW_IMPORT_DIR", "/app/workflow-imports"))

DEFAULT_WORKFLOW_JSON = {
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 123456,
            "steps": 28,
            "cfg": 7,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 1,
            "model": ["4", 0],
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["5", 0],
        },
    },
    "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {
            "ckpt_name": "dreamshaperXL_lightningDPMSDE.safetensors",
        },
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {
            "width": 1216,
            "height": 704,
            "batch_size": 1,
        },
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "{{prompt}}",
            "clip": ["4", 1],
        },
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "low quality, blurry, watermark, text, logo",
            "clip": ["4", 1],
        },
    },
    "8": {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["3", 0],
            "vae": ["4", 2],
        },
    },
    "9": {
        "class_type": "SaveImage",
        "inputs": {
            "filename_prefix": "aitoolstudio",
            "images": ["8", 0],
        },
    },
}

ERNIE_IMAGE_WORKFLOW_JSON = {
    "1": {
        "class_type": "LoadERNIEImageModel",
        "inputs": {
            "model_path": "baidu/ERNIE-Image",
        },
    },
    "2": {
        "class_type": "ERNIEImagePrompt",
        "inputs": {
            "text": "{{prompt}}",
        },
    },
    "3": {
        "class_type": "ERNIEImageNegativePrompt",
        "inputs": {
            "text": "",
        },
    },
    "4": {
        "class_type": "ERNIEImage",
        "inputs": {
            "pipeline": ["1", 0],
            "prompt": ["2", 0],
            "negative_prompt": ["3", 0],
            "width": 1024,
            "height": 1024,
            "num_inference_steps": 50,
            "guidance_scale": 5,
            "seed": 42,
        },
    },
    "5": {
        "class_type": "SaveERNIEImage",
        "inputs": {
            "image": ["4", 0],
            "filename_prefix": "aitoolstudio_ernie",
        },
    },
}

DEFAULT_WORKFLOWS = [
    {
        "id": "default-txt2img",
        "name": "Default txt2img",
        "description": "Basic ComfyUI text-to-image workflow used by AI Tool Studio.",
        "category": "image",
        "enabled": True,
        "workflow_json": DEFAULT_WORKFLOW_JSON,
        "notes": "Runtime patches prompt, checkpoint, seed, size, and batch size.",
    },
    {
        "id": "ernie-image",
        "name": "ERNIE Image",
        "description": "Baidu ERNIE-Image workflow through ComfyUI-ERNIE-Image custom nodes.",
        "category": "image",
        "enabled": True,
        "workflow_json": ERNIE_IMAGE_WORKFLOW_JSON,
        "notes": "Requires custom_nodes.ComfyUI-ERNIE-Image and model_path baidu/ERNIE-Image on the ComfyUI host. Runtime patches prompt, seed, width, and height.",
    },
]

VIDEO_WORKFLOW_HINTS = (
    "animatediff",
    "ltx",
    "mochi",
    "svd",
    "video",
    "vhs",
    "wan",
    "wanvideo",
    "hunyuan",
    "cogvideo",
)

PROMPT_INPUT_NAMES = ("text", "prompt", "positive", "positive_prompt", "caption")
NEGATIVE_PROMPT_KEYS = ("negative", "neg")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    parts = [part for part in cleaned.split("-") if part]
    return "-".join(parts)[:72] or f"workflow-{int(datetime.now().timestamp())}"


def validate_workflow_json(workflow_json: dict) -> None:
    if not isinstance(workflow_json, dict) or not workflow_json:
        raise ValueError("Workflow JSON must be a non-empty object")
    for node_id, node in workflow_json.items():
        if not isinstance(node_id, str):
            raise ValueError("Workflow node IDs must be strings")
        if not isinstance(node, dict):
            raise ValueError(f"Workflow node {node_id} must be an object")
        if not isinstance(node.get("class_type"), str) or not node.get("class_type"):
            raise ValueError(f"Workflow node {node_id} is missing class_type")
        if not isinstance(node.get("inputs", {}), dict):
            raise ValueError(f"Workflow node {node_id} inputs must be an object")


def _infer_workflow_category(path: Path, workflow_json: dict) -> str:
    path_text = " ".join(part.lower() for part in path.parts)
    if any(hint in path_text for hint in VIDEO_WORKFLOW_HINTS):
        return "video"
    for node in workflow_json.values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "").lower()
        if any(hint in class_type for hint in VIDEO_WORKFLOW_HINTS):
            return "video"
    return "image"


def _load() -> dict:
    if not CONFIG_FILE.exists():
        now = _now()
        defaults = [{**item, "created_at": now, "updated_at": now} for item in DEFAULT_WORKFLOWS]
        data = {"workflows": defaults}
        _save(data)
        return data
    with CONFIG_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data.get("workflows"), list):
        data["workflows"] = []
    existing_ids = {workflow.get("id") for workflow in data["workflows"]}
    missing_defaults = [workflow for workflow in DEFAULT_WORKFLOWS if workflow["id"] not in existing_ids]
    if missing_defaults:
        now = _now()
        data["workflows"].extend({**item, "created_at": now, "updated_at": now} for item in missing_defaults)
        _save(data)
    return data


def _save(data: dict) -> None:
    os.makedirs(CONFIG_FILE.parent, exist_ok=True)
    with CONFIG_FILE.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def list_workflows(include_disabled: bool = False) -> list[dict]:
    workflows = _load().get("workflows", [])
    if not include_disabled:
        workflows = [item for item in workflows if item.get("enabled", True)]
    return sorted(workflows, key=lambda item: (item.get("category", ""), item.get("name", "")))


def get_workflow(workflow_id: str, include_disabled: bool = False) -> Optional[dict]:
    for item in _load().get("workflows", []):
        if item.get("id") == workflow_id and (include_disabled or item.get("enabled", True)):
            return item
    return None


def upsert_workflow(workflow_data: dict, workflow_id: Optional[str] = None) -> dict:
    data = _load()
    workflows = data.get("workflows", [])
    now = _now()
    target_id = workflow_id or workflow_data.get("id") or _slug(workflow_data.get("name") or "workflow")
    workflow_json = workflow_data.get("workflow_json")
    validate_workflow_json(workflow_json)

    normalized = {
        "id": target_id,
        "name": workflow_data.get("name", "").strip(),
        "description": (workflow_data.get("description") or "").strip(),
        "category": (workflow_data.get("category") or "image").strip(),
        "enabled": bool(workflow_data.get("enabled", True)),
        "workflow_json": workflow_json,
        "notes": (workflow_data.get("notes") or "").strip(),
        "updated_at": now,
    }
    if not normalized["name"]:
        raise ValueError("Workflow name is required")
    if not normalized["category"]:
        raise ValueError("Workflow category is required")

    for index, item in enumerate(workflows):
        if item.get("id") == target_id:
            normalized["created_at"] = item.get("created_at") or now
            workflows[index] = normalized
            _save({"workflows": workflows})
            return normalized

    normalized["created_at"] = now
    workflows.append(normalized)
    _save({"workflows": workflows})
    return normalized


def delete_workflow(workflow_id: str) -> bool:
    data = _load()
    workflows = data.get("workflows", [])
    next_workflows = [item for item in workflows if item.get("id") != workflow_id]
    if len(next_workflows) == len(workflows):
        return False
    _save({"workflows": next_workflows})
    return True


def _workflow_from_file(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, dict) and isinstance(data.get("workflow_json"), dict):
        workflow = data
    elif isinstance(data, dict) and isinstance(data.get("prompt"), dict):
        workflow = {"workflow_json": data["prompt"]}
    elif isinstance(data, dict) and all(isinstance(node, dict) and "class_type" in node for node in data.values()):
        workflow = {"workflow_json": data}
    else:
        raise ValueError("Not a ComfyUI API-format workflow JSON")

    workflow.setdefault("name", path.stem.replace("_", " ").replace("-", " ").strip() or path.stem)
    workflow.setdefault("description", f"Imported from SMB workflow folder: {path.name}")
    workflow.setdefault("category", _infer_workflow_category(path, workflow["workflow_json"]))
    workflow.setdefault("enabled", True)
    workflow.setdefault("notes", f"Source: {path}")
    return workflow


def import_workflows_from_dir(import_dir: Optional[str] = None) -> dict:
    source = Path(import_dir) if import_dir else IMPORT_DIR
    if not source.exists():
        return {"source": str(source), "imported": [], "skipped": [{"path": str(source), "reason": "folder not found"}]}

    imported = []
    skipped = []
    for path in sorted(source.rglob("*.json")):
        try:
            workflow = _workflow_from_file(path)
            saved = upsert_workflow(workflow, workflow_id=workflow.get("id") or _slug(path.stem))
            imported.append({"path": str(path), "id": saved["id"], "name": saved["name"]})
        except Exception as exc:
            skipped.append({"path": str(path), "reason": str(exc)})

    return {"source": str(source), "imported": imported, "skipped": skipped}


def runtime_workflow(
    workflow_id: str,
    prompt: str,
    aspect_ratio: Optional[str],
    width: Optional[int],
    height: Optional[int],
    n: int,
    seed: Optional[int],
    checkpoint: Optional[str],
    expected_category: Optional[str] = None,
    duration: Optional[int] = None,
    fps: Optional[int] = None,
) -> dict:
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise ValueError("Workflow not found or disabled")
    if expected_category and workflow.get("category") != expected_category:
        raise ValueError(f"Workflow '{workflow.get('name')}' is not a {expected_category} workflow")

    patched = copy.deepcopy(workflow["workflow_json"])
    image_width, image_height = _size_for(aspect_ratio, width, height)
    prompt_patched = False
    resolved_seed = seed if seed is not None else random.randint(0, 2**32 - 1)
    resolved_fps = fps or 24
    resolved_frames = max(1, int((duration or 0) * resolved_fps)) if duration else None

    for node in patched.values():
        class_type = node.get("class_type")
        inputs = node.get("inputs", {})
        for key, value in list(inputs.items()):
            key_lower = key.lower()
            if isinstance(value, str) and "{{prompt}}" in value:
                inputs[key] = value.replace("{{prompt}}", prompt)
                prompt_patched = True
                continue
            if (
                not prompt_patched
                and key_lower in PROMPT_INPUT_NAMES
                and not any(term in key_lower for term in NEGATIVE_PROMPT_KEYS)
                and isinstance(value, str)
                and class_type not in {"CheckpointLoaderSimple"}
            ):
                inputs[key] = prompt
                prompt_patched = True
                continue
            if key_lower in {"width", "w"} and isinstance(value, int):
                inputs[key] = image_width
            elif key_lower in {"height", "h"} and isinstance(value, int):
                inputs[key] = image_height
            elif key_lower == "batch_size":
                inputs[key] = n
            elif key_lower in {"seed", "noise_seed"}:
                inputs[key] = resolved_seed
            elif checkpoint and key_lower == "ckpt_name":
                inputs[key] = checkpoint
            elif fps and key_lower == "fps":
                inputs[key] = fps
            elif duration and key_lower == "duration":
                inputs[key] = duration
            elif resolved_frames and key_lower in {"num_frames", "frames", "frame_count", "length", "video_length"}:
                inputs[key] = resolved_frames

    if not prompt_patched:
        raise ValueError("Workflow does not contain a supported prompt text input to patch")
    return patched
