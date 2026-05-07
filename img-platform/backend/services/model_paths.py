import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


CONFIG_FILE = Path(__file__).resolve().parents[1] / "config" / "comfyui_model_paths.json"

DEFAULT_PATHS = [
    {
        "id": "sjm-audio-encoders",
        "label": "SJM audio_encoders",
        "category": "audio_encoders",
        "uri": "smb://192.168.1.60/团队文件-SJM-MediaFile/Comfyui_Model/audio_encoders",
        "mount_path": "",
        "notes": "SMB storage shortcut. Fill mount path with the local path used by the ComfyUI host at 192.168.1.195.",
        "enabled": True,
    }
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    parts = [part for part in cleaned.split("-") if part]
    return "-".join(parts)[:64] or f"path-{int(datetime.now().timestamp())}"


def _load() -> dict:
    if not CONFIG_FILE.exists():
        now = _now()
        defaults = [{**path, "created_at": now, "updated_at": now} for path in DEFAULT_PATHS]
        data = {"paths": defaults}
        _save(data)
        return data
    with CONFIG_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data.get("paths"), list):
        data["paths"] = []
    return data


def _save(data: dict) -> None:
    os.makedirs(CONFIG_FILE.parent, exist_ok=True)
    with CONFIG_FILE.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def list_model_paths() -> list[dict]:
    paths = _load().get("paths", [])
    return sorted(paths, key=lambda item: (item.get("category", ""), item.get("label", "")))


def get_model_path(path_id: str) -> Optional[dict]:
    for item in _load().get("paths", []):
        if item.get("id") == path_id:
            return item
    return None


def upsert_model_path(path_data: dict, path_id: Optional[str] = None) -> dict:
    data = _load()
    paths = data.get("paths", [])
    now = _now()
    target_id = path_id or path_data.get("id") or _slug(path_data.get("label") or path_data.get("category") or "model-path")

    normalized = {
        "id": target_id,
        "label": path_data.get("label", "").strip(),
        "category": path_data.get("category", "").strip(),
        "uri": path_data.get("uri", "").strip(),
        "mount_path": (path_data.get("mount_path") or "").strip(),
        "notes": (path_data.get("notes") or "").strip(),
        "enabled": bool(path_data.get("enabled", True)),
        "updated_at": now,
    }
    if not normalized["label"]:
        raise ValueError("Label is required")
    if not normalized["category"]:
        raise ValueError("Category is required")
    if not normalized["uri"]:
        raise ValueError("URI is required")

    for index, item in enumerate(paths):
        if item.get("id") == target_id:
            normalized["created_at"] = item.get("created_at") or now
            paths[index] = normalized
            _save({"paths": paths})
            return normalized

    normalized["created_at"] = now
    paths.append(normalized)
    _save({"paths": paths})
    return normalized


def delete_model_path(path_id: str) -> bool:
    data = _load()
    paths = data.get("paths", [])
    next_paths = [item for item in paths if item.get("id") != path_id]
    if len(next_paths) == len(paths):
        return False
    _save({"paths": next_paths})
    return True
