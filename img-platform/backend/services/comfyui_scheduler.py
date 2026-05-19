"""
ComfyUI Worker Scheduler

Selects the best worker for a job based on:
- Tier requirements (light/medium/heavy)
- Required tags, models, nodes
- Estimated VRAM
- Queue depth (fewer pending/running tasks preferred)
- Tier match quality (avoid wasting heavy GPUs on light tasks)
- Health status (penalize workers with errors)

V1: Simple scoring with no persistent history or failure-rate tracking.
"""

from dataclasses import dataclass, field
from typing import Optional

import httpx

from services.comfyui_workers import get_workers_status, list_workers

# ---------------------------------------------------------------------------
# Tier constants
# ---------------------------------------------------------------------------
TIER_VALUES = {"light": 1, "medium": 2, "heavy": 3}
VALID_TIERS = set(TIER_VALUES.keys())


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class SchedulerError(ValueError):
    """Raised when no worker can satisfy a scheduling request."""


# ---------------------------------------------------------------------------
# Job model
# ---------------------------------------------------------------------------
@dataclass
class SchedulerJob:
    """Input to the scheduler describing what a task needs.

    Fields:
        job_class: "auto" | "heavy" | "medium" | "light" — auto resolves via
                   tags / estimated_vram_gb heuristics.
        required_tags: Worker must have ALL of these tags (case-insensitive).
        required_models: Checkpoint names that must be visible on the worker.
        required_nodes: ComfyUI node class names that must be in object_info.
        estimated_vram_gb: Approximate VRAM needed; worker must have at least
                           this much (0 = skip check, legacy-compatible).
        priority: Higher runs sooner (not used in v1 scoring beyond tiebreaking).
        workflow_id: Optional workflow reference for logging / future use.
        reason: Human-readable description for debugging.
    """

    job_class: str = "auto"
    required_tags: list[str] = field(default_factory=list)
    required_models: list[str] = field(default_factory=list)
    required_nodes: list[str] = field(default_factory=list)
    estimated_vram_gb: float = 0
    priority: int = 0
    workflow_id: Optional[str] = None
    reason: Optional[str] = None

    def __post_init__(self):
        if self.job_class not in ("auto", "heavy", "medium", "light"):
            raise SchedulerError(
                f"Invalid job_class '{self.job_class}'; "
                f"must be one of: auto, heavy, medium, light"
            )


# ---------------------------------------------------------------------------
# Tier resolution
# ---------------------------------------------------------------------------
def resolve_tier(job: SchedulerJob) -> str:
    """Determine effective tier from job_class.

    'auto' infers tier from required_tags and estimated_vram_gb:
      - flux / video / highres  tag  OR  vram >= 22  →  heavy
      - sdxl / controlnet / upscale  OR  vram >= 12  →  medium
      - otherwise → light
    """
    if job.job_class != "auto":
        return job.job_class

    tags_lower = {t.lower() for t in job.required_tags}
    heavy_keywords = {"flux", "video", "highres"}
    medium_keywords = {"sdxl", "controlnet", "upscale"}

    if tags_lower & heavy_keywords or job.estimated_vram_gb >= 22:
        return "heavy"
    if tags_lower & medium_keywords or job.estimated_vram_gb >= 12:
        return "medium"
    return "light"


# ---------------------------------------------------------------------------
# Worker probing helpers
# ---------------------------------------------------------------------------
async def _fetch_object_info(base_url: str) -> Optional[dict]:
    """Fetch /object_info from a single ComfyUI worker."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(f"{base_url}/object_info")
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return None


def _checkpoint_names_from_object_info(object_info: dict) -> set[str]:
    """Extract all checkpoint names from object_info."""
    try:
        ckpt_list = (
            object_info.get("CheckpointLoaderSimple", {})
            .get("input", {})
            .get("required", {})
            .get("ckpt_name", [])
        )
        if isinstance(ckpt_list, list) and len(ckpt_list) >= 1 and isinstance(ckpt_list[0], list):
            return set(ckpt_list[0])
    except Exception:
        pass
    return set()


def _available_nodes(object_info: dict) -> set[str]:
    """Return set of all node class names in object_info."""
    return set(object_info.keys()) if isinstance(object_info, dict) else set()


# ---------------------------------------------------------------------------
# Worker selection
# ---------------------------------------------------------------------------
async def select_worker(job: SchedulerJob) -> dict:
    """Select the best worker for *job*.  Returns the raw worker dict (with 'url').

    Raises SchedulerError with a descriptive message when no worker qualifies.
    """
    workers = list_workers()
    statuses = await get_workers_status()
    status_map = {s["id"]: s for s in statuses}

    required_tier = resolve_tier(job)
    required_tier_value = TIER_VALUES[required_tier]

    rejection_reasons: dict[str, str] = {}
    candidates: list[tuple[dict, dict, str, int]] = []  # (worker, status, tier, tier_val)

    for worker in workers:
        wid = worker["id"]
        status = status_map.get(wid, {})

        # ---- Filter: disabled ----
        if not worker.get("enabled", True):
            rejection_reasons[wid] = "disabled"
            continue

        # ---- Filter: offline ----
        if not status.get("online", False):
            rejection_reasons[wid] = "offline"
            continue

        # ---- Filter: tier ----
        worker_tier = worker.get("tier", "heavy")
        worker_tier_value = TIER_VALUES.get(worker_tier, 0)
        if worker_tier_value < required_tier_value:
            rejection_reasons[wid] = (
                f"tier insufficient (need {required_tier}, got {worker_tier})"
            )
            continue

        # ---- Filter: required_tags ----
        worker_tags = set(worker.get("tags", []))
        missing_tags = [t for t in job.required_tags if t.lower() not in worker_tags]
        if missing_tags:
            rejection_reasons[wid] = f"missing required tag(s): {missing_tags}"
            continue

        # ---- Fetch object_info if needed for model / node checks ----
        need_oi = bool(job.required_models) or bool(job.required_nodes)
        object_info = None
        if need_oi:
            object_info = await _fetch_object_info(worker["url"])

        # ---- Filter: required_models ----
        if job.required_models:
            if object_info is None:
                rejection_reasons[wid] = "cannot fetch object_info for model check"
                continue
            available_ckpts = _checkpoint_names_from_object_info(object_info)
            missing = [m for m in job.required_models if m not in available_ckpts]
            if missing:
                rejection_reasons[wid] = f"missing required model(s): {missing}"
                continue

        # ---- Filter: required_nodes ----
        if job.required_nodes:
            if object_info is None:
                rejection_reasons[wid] = "cannot fetch object_info for node check"
                continue
            available = _available_nodes(object_info)
            missing = [n for n in job.required_nodes if n not in available]
            if missing:
                rejection_reasons[wid] = f"missing required node(s): {missing}"
                continue

        # ---- Filter: VRAM ----
        worker_vram = worker.get("vram_gb", 0)
        if worker_vram > 0 and job.estimated_vram_gb > worker_vram:
            rejection_reasons[wid] = (
                f"insufficient VRAM (need {job.estimated_vram_gb}GB, got {worker_vram}GB)"
            )
            continue

        # ---- Candidate ----
        candidates.append((worker, status, worker_tier, worker_tier_value))

    if not candidates:
        raise _build_scheduler_error(rejection_reasons, workers, statuses)

    return _score_and_pick(candidates, required_tier, required_tier_value)


def _build_scheduler_error(
    rejection_reasons: dict[str, str],
    workers: list[dict],
    statuses: list[dict],
) -> SchedulerError:
    """Build a descriptive SchedulerError with rejection summary."""
    parts: list[str] = []

    if not workers:
        parts.append("no workers configured")
    else:
        online_count = sum(1 for s in statuses if s.get("online"))
        if online_count == 0:
            parts.append("no online workers")
        else:
            parts.append(f"all {online_count} online worker(s) rejected")

    # Summarize unique rejection reasons by category
    categories: dict[str, list[str]] = {}
    for wid, reason in rejection_reasons.items():
        cat = reason.split(":")[0].strip() if ":" in reason else reason
        categories.setdefault(cat, []).append(wid)

    for cat, ids in categories.items():
        parts.append(f"{cat}: {', '.join(ids)}")

    # Per-worker detail
    detail_parts = []
    for wid, reason in rejection_reasons.items():
        detail_parts.append(f"  {wid} → {reason}")

    msg = "No suitable worker found.\n" + "\n".join(parts)
    if detail_parts:
        msg += "\nDetails:\n" + "\n".join(detail_parts)

    return SchedulerError(msg)


def _score_and_pick(
    candidates: list[tuple[dict, dict, str, int]],
    required_tier: str,
    required_tier_value: int,
) -> dict:
    """Score candidates and return the best worker dict."""

    def score(candidate: tuple[dict, dict, str, int]) -> tuple[int, str]:
        worker, status, w_tier, w_tier_val = candidate
        s = 0

        # Lower queue = better (pending + running)
        queue_total = status.get("queue_pending", 0) + status.get("queue_running", 0)
        s -= queue_total * 10

        # Exact tier match preferred; penalize overkill
        if w_tier == required_tier:
            s += 5
        elif w_tier_val > required_tier_value:
            s -= (w_tier_val - required_tier_value) * 3

        # Health error penalty
        if status.get("last_health_error"):
            s -= 50

        # Stable tiebreak by worker id
        return (s, worker.get("id", ""))

    # Sort descending by score tuple; tiebreak via stable id
    candidates.sort(key=score, reverse=True)
    return candidates[0][0]


# ---------------------------------------------------------------------------
# Convenience builder
# ---------------------------------------------------------------------------
def build_job_from_image_request(req, workflow=None) -> SchedulerJob:
    """Build a SchedulerJob from an ImageGenerateRequest (schemas.image).

    Extracts comfyui_* scheduling fields; falls back to safe defaults when
    the request was created without them (backward-compatible).
    """
    return SchedulerJob(
        job_class=getattr(req, "comfyui_job_class", None) or "auto",
        required_tags=list(getattr(req, "comfyui_required_tags", None) or []),
        required_models=list(getattr(req, "comfyui_required_models", None) or []),
        required_nodes=list(getattr(req, "comfyui_required_nodes", None) or []),
        estimated_vram_gb=getattr(req, "comfyui_estimated_vram_gb", None) or 0,
        workflow_id=getattr(req, "comfyui_workflow_id", None),
    )
