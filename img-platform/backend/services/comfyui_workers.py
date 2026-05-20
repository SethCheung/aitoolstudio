"""
ComfyUI Multi-Worker Registry

Persistence: JSON file at backend/config/comfyui_workers.json
Override:   COMFYUI_WORKERS_JSON env var (raw JSON list)
Fallback:   legacy worker derived from COMFYUI_BASE_URL

No database dependency — follows the same file-based pattern as
model_paths.py and comfyui_workflows.py.

Docker / persistence:
  The config directory MUST be mounted as a Docker volume (or bind mount) to
  the host machine.  Without a persistent mount the worker config file is
  lost every time the container is rebuilt.  For production deployments we
  recommend using the COMFYUI_WORKERS_JSON environment variable instead —
  it is the canonical source when set and survives container rebuilds
  without any volume plumbing.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

# ---------------------------------------------------------------------------
# Config paths
# ---------------------------------------------------------------------------
CONFIG_FILE = Path(__file__).resolve().parents[1] / "config" / "comfyui_workers.json"

DEFAULT_COMFYUI_BASE_URL = os.getenv("COMFYUI_BASE_URL", "http://192.168.1.195:8188")
DEFAULT_SMB_MODEL_ROOT = (
    "smb://192.168.1.60/团队文件-SJM-MediaFile/Comfyui_Model"
)

VALID_TIERS = {"heavy", "medium", "light"}

# Core nodes that every worker should expose for basic image workflows
REQUIRED_CORE_NODES = ["CheckpointLoaderSimple", "KSampler", "SaveImage"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_url(url: str) -> str:
    """Strip trailing slash and clean whitespace."""
    return url.strip().rstrip("/")


def normalize_worker_url(url: str) -> str:
    """Public alias for url normalisation."""
    return _normalize_url(url)


def _normalize_tags(tags: list[str]) -> list[str]:
    """Deduplicate, lowercase, strip empty strings."""
    return sorted({t.strip().lower() for t in (tags or []) if t.strip()})


def _build_legacy_worker() -> dict:
    """Construct a single fallback worker from COMFYUI_BASE_URL."""
    now = _now()
    return {
        "id": "legacy",
        "name": "Legacy ComfyUI",
        "url": _normalize_url(DEFAULT_COMFYUI_BASE_URL),
        "tier": "heavy",
        "gpu": "",
        "vram_gb": 0,
        "tags": [],
        "model_root_uri": DEFAULT_SMB_MODEL_ROOT,
        "model_mount_path": "",
        "enabled": True,
        "notes": "Auto-generated legacy worker from COMFYUI_BASE_URL",
        "created_at": now,
        "updated_at": now,
    }


def _load_from_env() -> Optional[list[dict]]:
    """Parse COMFYUI_WORKERS_JSON env var if set."""
    raw = os.getenv("COMFYUI_WORKERS_JSON", "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    # Ensure each worker has at least an id and url
    result: list[dict] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        if not item.get("url"):
            continue
        result.append(item)
    return result or None


def _load_from_file() -> Optional[dict]:
    """Load the JSON config file; returns None if the file doesn't exist."""
    if not CONFIG_FILE.exists():
        return None
    with CONFIG_FILE.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _save_to_file(data: dict) -> None:
    os.makedirs(CONFIG_FILE.parent, exist_ok=True)
    with CONFIG_FILE.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def _resolve_source() -> tuple[list[dict], str]:
    """
    Determine where worker definitions come from.

    Priority:
    1. COMFYUI_WORKERS_JSON env var
    2. comfyui_workers.json config file
    3. Legacy fallback (COMFYUI_BASE_URL)

    Returns (workers_list, source_label).
    """
    # 1  Env var
    env_workers = _load_from_env()
    if env_workers is not None:
        # Normalise env workers on the fly (they lack timestamps)
        now = _now()
        normalized: list[dict] = []
        for w in env_workers:
            nw = _normalize_worker_fields(w, now)
            normalized.append(nw)
        return normalized, "env"

    # 2  Config file
    file_data = _load_from_file()
    if file_data is not None and isinstance(file_data.get("workers"), list):
        if file_data["workers"]:
            return file_data["workers"], "file"
        # Empty file workers list — treat as no config, fall through to legacy

    # 3  Legacy
    return [_build_legacy_worker()], "legacy"


def _normalize_worker_fields(worker: dict, now: Optional[str] = None) -> dict:
    """Ensure all fields are present with sensible defaults."""
    if now is None:
        now = _now()
    return {
        "id": str(worker.get("id") or "worker-" + now.replace(":", "")),
        "name": str(worker.get("name") or "").strip(),
        "url": _normalize_url(str(worker.get("url") or DEFAULT_COMFYUI_BASE_URL)),
        "tier": str(worker.get("tier") or "heavy").strip(),
        "gpu": str(worker.get("gpu") or "").strip(),
        "vram_gb": int(worker.get("vram_gb") or 0),
        "tags": _normalize_tags(worker.get("tags") or []),
        "model_root_uri": str(worker.get("model_root_uri") or DEFAULT_SMB_MODEL_ROOT).strip(),
        "model_mount_path": str(worker.get("model_mount_path") or "").strip(),
        "enabled": bool(worker.get("enabled", True)),
        "notes": str(worker.get("notes") or "").strip(),
        "created_at": str(worker.get("created_at") or now),
        "updated_at": now,
    }


def _is_env_managed() -> bool:
    """Return True when COMFYUI_WORKERS_JSON env var is set and non-empty."""
    return bool(os.getenv("COMFYUI_WORKERS_JSON", "").strip())


# ---------------------------------------------------------------------------
# Public CRUD
# ---------------------------------------------------------------------------

def list_workers() -> list[dict]:
    """Return all configured workers, sorted by tier + name."""
    workers, _ = _resolve_source()
    tier_order = {"heavy": 0, "medium": 1, "light": 2}
    return sorted(
        workers,
        key=lambda w: (
            tier_order.get(w.get("tier", "heavy"), 99),
            w.get("name", "").lower(),
        ),
    )


def get_worker(worker_id: str) -> Optional[dict]:
    """Find a single worker by id."""
    for w in list_workers():
        if w.get("id") == worker_id:
            return w
    return None


def upsert_worker(worker_data: dict, worker_id: Optional[str] = None) -> dict:
    """
    Create or update a worker.  Always persists to the JSON config file.

    Raises ValueError when COMFYUI_WORKERS_JSON is set (env-managed mode)
    because writes to the file would have no observable effect — the env
    var always wins on read.  Modify the env var directly instead.
    """
    if _is_env_managed():
        raise ValueError(
            "Workers are managed by COMFYUI_WORKERS_JSON env var, "
            "modify it directly"
        )

    # Load current state from FILE (or start fresh)
    file_data = _load_from_file()
    workers: list[dict] = (
        file_data.get("workers", []) if file_data is not None else []
    )

    now = _now()
    normalized = _normalize_worker_fields(worker_data, now)
    target_id = worker_id or str(worker_data.get("id") or normalized["id"])

    if not target_id:
        raise ValueError("Worker id is required")

    normalized["id"] = target_id  # id comes from path param, explicit field, or auto-generated

    # Validate tier
    if normalized["tier"] not in VALID_TIERS:
        raise ValueError(
            f"tier must be one of {sorted(VALID_TIERS)}, got '{normalized['tier']}'"
        )

    # Update or append
    for idx, item in enumerate(workers):
        if item.get("id") == target_id:
            normalized["created_at"] = item.get("created_at") or now
            workers[idx] = normalized
            _save_to_file({"workers": workers})
            return normalized

    # New worker
    normalized["created_at"] = now
    workers.append(normalized)
    _save_to_file({"workers": workers})
    return normalized


def delete_worker(worker_id: str) -> bool:
    """Remove a worker from the file store. Returns False if not found.

    Raises ValueError when COMFYUI_WORKERS_JSON is set (env-managed mode)
    for the same reason as upsert_worker — file writes are invisible.
    """
    if _is_env_managed():
        raise ValueError(
            "Workers are managed by COMFYUI_WORKERS_JSON env var, "
            "modify it directly"
        )

    file_data = _load_from_file()
    if file_data is None:
        return False
    workers: list[dict] = file_data.get("workers", [])
    next_workers = [w for w in workers if w.get("id") != worker_id]
    if len(next_workers) == len(workers):
        return False
    _save_to_file({"workers": next_workers})
    return True


# ---------------------------------------------------------------------------
# Health / status
# ---------------------------------------------------------------------------


async def _fetch_json(
    client: httpx.AsyncClient, url: str, timeout: float = 6.0
) -> Optional[dict]:
    """Fetch a JSON endpoint; return None on any failure."""
    try:
        resp = await client.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


async def _check_worker_health(worker: dict) -> dict[str, Any]:
    """
    Probe a single worker for health data.

    Never raises — failures are captured in last_health_error.
    """
    base_url = _normalize_url(worker.get("url", ""))
    result: dict[str, Any] = {
        "id": worker.get("id"),
        "name": worker.get("name"),
        "url": base_url,
        "tier": worker.get("tier"),
        "gpu": worker.get("gpu"),
        "tags": worker.get("tags"),
        "enabled": worker.get("enabled"),
        "online": False,
        "system_stats": None,
        "queue_pending": 0,
        "queue_running": 0,
        "checkpoint_count": 0,
        "object_info_ok": False,
        "has_required_core_nodes": False,
        "last_health_error": None,
    }

    if not base_url:
        result["last_health_error"] = "Empty worker URL"
        return result

    async with httpx.AsyncClient(timeout=8.0) as client:
        # 1  system_stats
        stats = await _fetch_json(client, f"{base_url}/system_stats")
        if stats is None:
            result["last_health_error"] = (
                f"GET {base_url}/system_stats failed — worker may be offline"
            )
            return result

        result["online"] = True
        result["system_stats"] = stats

        # 2  queue
        queue_data = await _fetch_json(client, f"{base_url}/queue")
        if queue_data is not None:
            result["queue_pending"] = len(queue_data.get("queue_pending", []) or [])
            result["queue_running"] = len(queue_data.get("queue_running", []) or [])

        # 3  object_info
        object_info = await _fetch_json(client, f"{base_url}/object_info")
        if object_info is None:
            result["last_health_error"] = "object_info unavailable"
            return result

        result["object_info_ok"] = True

        # 3a  checkpoint count
        try:
            ckpt_data = (
                object_info.get("CheckpointLoaderSimple", {})
                .get("input", {})
                .get("required", {})
                .get("ckpt_name", [])
            )
            if isinstance(ckpt_data, list) and len(ckpt_data) >= 1:
                result["checkpoint_count"] = len(ckpt_data[0]) if isinstance(ckpt_data[0], list) else 0
        except Exception:
            result["checkpoint_count"] = 0

        # 3b  required core nodes
        available_nodes = set(object_info.keys()) if isinstance(object_info, dict) else set()
        result["has_required_core_nodes"] = all(
            node in available_nodes for node in REQUIRED_CORE_NODES
        )

        # Success — clear any previous error
        result["last_health_error"] = None
        return result


async def get_workers_status() -> list[dict]:
    """
    Return health status for every worker.

    Each worker is probed independently — a single offline worker
    does NOT cause the whole endpoint to fail.
    """
    workers = list_workers()
    results: list[dict] = []
    for w in workers:
        status = await _check_worker_health(w)
        results.append(status)
    return results
