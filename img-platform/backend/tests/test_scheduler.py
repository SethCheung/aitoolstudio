"""
Unit tests for Agent B — ComfyUI Scheduler.

Covers select_worker(), resolve_tier(), build_job_from_image_request(),
and error handling. All external dependencies (list_workers, get_workers_status,
_fetch_object_info) are mocked — no real ComfyUI connection required.

Integration tests (real ComfyUI) are skipped by default and only run when
RUN_COMFYUI_INTEGRATION=1 is set.

Run:
    cd /opt/aitoolstudio/img-platform/backend
    python3 -m pytest tests/test_scheduler.py -v
    # or standalone:
    python3 tests/test_scheduler.py
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

# Ensure backend is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Optional pytest import — fallback to standalone runner if missing
try:
    import pytest

    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False

from services.comfyui_scheduler import (
    SchedulerJob,
    SchedulerError,
    resolve_tier,
    select_worker,
    build_job_from_image_request,
    TIER_VALUES,
)

# ---------------------------------------------------------------------------
# Mock data factories
# ---------------------------------------------------------------------------


def make_worker(
    wid,
    tier="heavy",
    enabled=True,
    vram_gb=0,
    tags=None,
    url=None,
):
    """Create a mock worker dict as returned by list_workers()."""
    return {
        "id": wid,
        "name": f"Worker-{wid}",
        "url": url or f"http://comfyui-{wid}:8188",
        "tier": tier,
        "gpu": "NVIDIA RTX 4090",
        "vram_gb": vram_gb,
        "tags": tags or [],
        "enabled": enabled,
    }


def make_status(
    wid,
    online=True,
    queue_pending=0,
    queue_running=0,
    last_health_error=None,
):
    """Create a mock status dict as returned by get_workers_status()."""
    return {
        "id": wid,
        "online": online,
        "queue_pending": queue_pending,
        "queue_running": queue_running,
        "last_health_error": last_health_error,
    }


def make_object_info(checkpoint_names=None, node_names=None):
    """Create a fake /object_info response dict.

    checkpoint_names: list of checkpoint strings to expose via CheckpointLoaderSimple.
    node_names: list of node class name strings to expose as top-level keys.
    """
    info = {}
    # Add requested nodes as empty dicts (just keys matter for _available_nodes)
    for n in (node_names or []):
        info[n] = {}
    # Add CheckpointLoaderSimple with ckpt_name input
    ckpt_list = checkpoint_names or []
    info["CheckpointLoaderSimple"] = {
        "input": {
            "required": {
                "ckpt_name": [ckpt_list],
            }
        }
    }
    return info


# ---------------------------------------------------------------------------
# 1. resolve_tier — all auto inference paths
# ---------------------------------------------------------------------------

def test_tier_resolution_auto():
    """resolve_tier handles all auto inference paths and explicit tiers."""
    # Explicit tiers pass through unchanged
    assert resolve_tier(SchedulerJob(job_class="heavy")) == "heavy"
    assert resolve_tier(SchedulerJob(job_class="medium")) == "medium"
    assert resolve_tier(SchedulerJob(job_class="light")) == "light"

    # Auto: heavy triggers — tags
    assert resolve_tier(SchedulerJob(required_tags=["flux"])) == "heavy"
    assert resolve_tier(SchedulerJob(required_tags=["video"])) == "heavy"
    assert resolve_tier(SchedulerJob(required_tags=["highres"])) == "heavy"

    # Auto: heavy triggers — VRAM threshold (>= 22)
    assert resolve_tier(SchedulerJob(estimated_vram_gb=22)) == "heavy"
    assert resolve_tier(SchedulerJob(estimated_vram_gb=24)) == "heavy"

    # Auto: medium triggers — tags
    assert resolve_tier(SchedulerJob(required_tags=["sdxl"])) == "medium"
    assert resolve_tier(SchedulerJob(required_tags=["controlnet"])) == "medium"
    assert resolve_tier(SchedulerJob(required_tags=["upscale"])) == "medium"

    # Auto: medium triggers — VRAM threshold (>= 12 but < 22)
    assert resolve_tier(SchedulerJob(estimated_vram_gb=12)) == "medium"
    assert resolve_tier(SchedulerJob(estimated_vram_gb=14)) == "medium"
    assert resolve_tier(SchedulerJob(estimated_vram_gb=21)) == "medium"

    # Auto: light (default fallback)
    assert resolve_tier(SchedulerJob()) == "light"
    assert resolve_tier(SchedulerJob(required_tags=["anything-else"])) == "light"
    assert resolve_tier(SchedulerJob(estimated_vram_gb=4)) == "light"
    assert resolve_tier(SchedulerJob(estimated_vram_gb=11)) == "light"  # below medium threshold
    assert resolve_tier(SchedulerJob(estimated_vram_gb=0)) == "light"


# ---------------------------------------------------------------------------
# 2. Legacy / heavy worker selected
# ---------------------------------------------------------------------------

def test_legacy_worker_selected():
    """A legacy (tier=heavy) worker is selected for an auto job (resolves light)."""
    workers = [make_worker("legacy", tier="heavy")]
    statuses = [make_status("legacy", online=True)]

    with (
        patch("services.comfyui_scheduler.list_workers", return_value=workers),
        patch("services.comfyui_scheduler.get_workers_status", AsyncMock(return_value=statuses)),
    ):
        job = SchedulerJob(job_class="auto")
        result = asyncio.run(select_worker(job))

    assert result is not None
    assert result["id"] == "legacy"
    assert result["tier"] == "heavy"


# ---------------------------------------------------------------------------
# 3. Heavy job rejects light worker (tier insufficient)
# ---------------------------------------------------------------------------

def test_heavy_job_rejects_light_worker():
    """A heavy job_class should reject a light-tier worker."""
    workers = [make_worker("w-light", tier="light")]
    statuses = [make_status("w-light", online=True)]

    with (
        patch("services.comfyui_scheduler.list_workers", return_value=workers),
        patch("services.comfyui_scheduler.get_workers_status", AsyncMock(return_value=statuses)),
    ):
        job = SchedulerJob(job_class="heavy")
        with pytest.raises(SchedulerError) if HAS_PYTEST else _raises(SchedulerError) as exc:
            asyncio.run(select_worker(job))

    err_msg = str(exc.value if HAS_PYTEST else exc.exception)
    assert "tier insufficient" in err_msg.lower() or "rejected" in err_msg.lower()


# ---------------------------------------------------------------------------
# 4. required_models missing → filtered
# ---------------------------------------------------------------------------

def test_required_models_missing_filters():
    """Worker missing a required model is filtered out."""
    workers = [make_worker("w1", tier="heavy")]
    statuses = [make_status("w1", online=True)]
    # object_info exposes only "sd_xl.safetensors", job wants "dreamshaper.safetensors"
    fake_oi = make_object_info(checkpoint_names=["sd_xl.safetensors"])

    with (
        patch("services.comfyui_scheduler.list_workers", return_value=workers),
        patch("services.comfyui_scheduler.get_workers_status", AsyncMock(return_value=statuses)),
        patch("services.comfyui_scheduler._fetch_object_info", AsyncMock(return_value=fake_oi)),
    ):
        job = SchedulerJob(
            job_class="auto",
            required_models=["dreamshaper.safetensors"],
        )
        with pytest.raises(SchedulerError) if HAS_PYTEST else _raises(SchedulerError) as exc:
            asyncio.run(select_worker(job))

    err_msg = str(exc.value if HAS_PYTEST else exc.exception)
    assert "missing required model" in err_msg.lower()


# ---------------------------------------------------------------------------
# 5. required_nodes missing → filtered
# ---------------------------------------------------------------------------

def test_required_nodes_missing_filters():
    """Worker missing a required node class is filtered out."""
    workers = [make_worker("w1", tier="heavy")]
    statuses = [make_status("w1", online=True)]
    # object_info exposes KSampler, SaveImage but NOT VideoCombine
    fake_oi = make_object_info(node_names=["KSampler", "SaveImage", "CLIPTextEncode"])

    with (
        patch("services.comfyui_scheduler.list_workers", return_value=workers),
        patch("services.comfyui_scheduler.get_workers_status", AsyncMock(return_value=statuses)),
        patch("services.comfyui_scheduler._fetch_object_info", AsyncMock(return_value=fake_oi)),
    ):
        job = SchedulerJob(
            job_class="auto",
            required_nodes=["VideoCombine"],
        )
        with pytest.raises(SchedulerError) if HAS_PYTEST else _raises(SchedulerError) as exc:
            asyncio.run(select_worker(job))

    err_msg = str(exc.value if HAS_PYTEST else exc.exception)
    assert "missing required node" in err_msg.lower()


# ---------------------------------------------------------------------------
# 6. Offline worker filtered
# ---------------------------------------------------------------------------

def test_offline_worker_filtered():
    """An offline worker (online=False in status) is rejected."""
    workers = [make_worker("w-offline", tier="heavy")]
    statuses = [make_status("w-offline", online=False)]

    with (
        patch("services.comfyui_scheduler.list_workers", return_value=workers),
        patch("services.comfyui_scheduler.get_workers_status", AsyncMock(return_value=statuses)),
    ):
        job = SchedulerJob(job_class="auto")
        with pytest.raises(SchedulerError) if HAS_PYTEST else _raises(SchedulerError) as exc:
            asyncio.run(select_worker(job))

    err_msg = str(exc.value if HAS_PYTEST else exc.exception)
    assert "offline" in err_msg.lower() or "no online" in err_msg.lower()


# ---------------------------------------------------------------------------
# 7. Disabled worker filtered
# ---------------------------------------------------------------------------

def test_disabled_worker_filtered():
    """A disabled worker (enabled=False) is rejected even if online."""
    workers = [make_worker("w-disabled", tier="heavy", enabled=False)]
    statuses = [make_status("w-disabled", online=True)]

    with (
        patch("services.comfyui_scheduler.list_workers", return_value=workers),
        patch("services.comfyui_scheduler.get_workers_status", AsyncMock(return_value=statuses)),
    ):
        job = SchedulerJob(job_class="auto")
        with pytest.raises(SchedulerError) if HAS_PYTEST else _raises(SchedulerError) as exc:
            asyncio.run(select_worker(job))

    err_msg = str(exc.value if HAS_PYTEST else exc.exception)
    assert "disabled" in err_msg.lower()


# ---------------------------------------------------------------------------
# 8. VRAM exceeded → filtered
# ---------------------------------------------------------------------------

def test_vram_exceeded_filters():
    """Worker with insufficient VRAM is filtered out."""
    workers = [make_worker("w-small", tier="heavy", vram_gb=8)]
    statuses = [make_status("w-small", online=True)]

    with (
        patch("services.comfyui_scheduler.list_workers", return_value=workers),
        patch("services.comfyui_scheduler.get_workers_status", AsyncMock(return_value=statuses)),
    ):
        job = SchedulerJob(job_class="auto", estimated_vram_gb=16)
        with pytest.raises(SchedulerError) if HAS_PYTEST else _raises(SchedulerError) as exc:
            asyncio.run(select_worker(job))

    err_msg = str(exc.value if HAS_PYTEST else exc.exception)
    assert "insufficient vram" in err_msg.lower() or "vram" in err_msg.lower()


# ---------------------------------------------------------------------------
# 9. Multi-worker prefers better fit (tier match + queue depth)
# ---------------------------------------------------------------------------

def test_multi_worker_prefers_better_fit():
    """When multiple workers are eligible, the scheduler picks the best fit.

    Scenario:
      - w-light: tier=light, queue=0  → exact match for light job
      - w-heavy: tier=heavy, queue=0  → overkill, penalized
      → w-light should win (higher score: +5 for tier match vs -6 penalty for overkill)
    """
    workers = [
        make_worker("w-light", tier="light"),
        make_worker("w-heavy", tier="heavy"),
    ]
    statuses = [
        make_status("w-light", online=True, queue_pending=0, queue_running=0),
        make_status("w-heavy", online=True, queue_pending=0, queue_running=0),
    ]

    with (
        patch("services.comfyui_scheduler.list_workers", return_value=workers),
        patch("services.comfyui_scheduler.get_workers_status", AsyncMock(return_value=statuses)),
    ):
        job = SchedulerJob(job_class="light")
        result = asyncio.run(select_worker(job))

    # Light worker should win because it's an exact tier match
    assert result["id"] == "w-light"

    # --- Second scenario: shorter queue beats tier match ---
    # w-busy-light: tier=light, queue_pending=10 → score = -100 + 5 = -95
    # w-idle-heavy: tier=heavy, queue_pending=0  → score = 0 + 0 - 6 = -6
    # → w-idle-heavy should win despite overkill
    workers2 = [
        make_worker("w-busy-light", tier="light"),
        make_worker("w-idle-heavy", tier="heavy"),
    ]
    statuses2 = [
        make_status("w-busy-light", online=True, queue_pending=10, queue_running=0),
        make_status("w-idle-heavy", online=True, queue_pending=0, queue_running=0),
    ]

    with (
        patch("services.comfyui_scheduler.list_workers", return_value=workers2),
        patch("services.comfyui_scheduler.get_workers_status", AsyncMock(return_value=statuses2)),
    ):
        job2 = SchedulerJob(job_class="light")
        result2 = asyncio.run(select_worker(job2))

    assert result2["id"] == "w-idle-heavy"


# ---------------------------------------------------------------------------
# 10. No suitable worker → error message contains rejection reasons
# ---------------------------------------------------------------------------

def test_no_suitable_worker_error_message():
    """When no worker qualifies, the error message includes rejection reasons."""
    workers = [
        make_worker("w-offline", tier="heavy"),
        make_worker("w-disabled", tier="heavy", enabled=False),
        make_worker("w-light", tier="light"),
    ]
    statuses = [
        make_status("w-offline", online=False),
        make_status("w-disabled", online=True),
        make_status("w-light", online=True),
    ]

    with (
        patch("services.comfyui_scheduler.list_workers", return_value=workers),
        patch("services.comfyui_scheduler.get_workers_status", AsyncMock(return_value=statuses)),
    ):
        job = SchedulerJob(job_class="heavy")  # requires heavy, only light online
        with pytest.raises(SchedulerError) if HAS_PYTEST else _raises(SchedulerError) as exc:
            asyncio.run(select_worker(job))

    err_msg = str(exc.value if HAS_PYTEST else exc.exception)
    assert "No suitable worker" in err_msg
    assert "w-offline" in err_msg
    assert "w-disabled" in err_msg
    assert "w-light" in err_msg
    # Verify specific rejection categories appear
    assert "offline" in err_msg.lower()
    assert "disabled" in err_msg.lower()
    assert "tier insufficient" in err_msg.lower()


# ---------------------------------------------------------------------------
# Additional unit tests (backward compat, validation, error format)
# ---------------------------------------------------------------------------

def test_build_job_from_image_request_old_req():
    """build_job_from_image_request handles old requests without scheduling fields."""
    class OldReq:
        pass

    old = OldReq()
    job = build_job_from_image_request(old)
    assert job.job_class == "auto"
    assert job.required_tags == []
    assert job.required_models == []
    assert job.required_nodes == []
    assert job.estimated_vram_gb == 0
    assert job.workflow_id is None


def test_build_job_from_image_request_with_fields():
    """build_job_from_image_request extracts scheduling fields when present."""
    class NewReq:
        comfyui_job_class = "medium"
        comfyui_required_tags = ["sdxl"]
        comfyui_required_models = ["dreamshaper.safetensors"]
        comfyui_required_nodes = ["KSampler"]
        comfyui_estimated_vram_gb = 14
        comfyui_workflow_id = "wf-001"

    req = NewReq()
    job = build_job_from_image_request(req)
    assert job.job_class == "medium"
    assert job.required_tags == ["sdxl"]
    assert job.required_models == ["dreamshaper.safetensors"]
    assert job.required_nodes == ["KSampler"]
    assert job.estimated_vram_gb == 14
    assert job.workflow_id == "wf-001"


def test_invalid_job_class_raises():
    """SchedulerJob rejects invalid job_class values."""
    try:
        SchedulerJob(job_class="super_heavy")
        assert False, "Should have raised SchedulerError"
    except SchedulerError:
        pass


def test_scheduler_error_message_format():
    """SchedulerError preserves the descriptive message."""
    err = SchedulerError("No suitable worker found.\nno online workers\nDetails:\n  w1 → offline")
    msg = str(err)
    assert "no online workers" in msg
    assert "w1" in msg
    assert "offline" in msg


def test_scheduler_job_defaults():
    """SchedulerJob has correct defaults for all fields."""
    job = SchedulerJob()
    assert job.job_class == "auto"
    assert job.required_tags == []
    assert job.required_models == []
    assert job.required_nodes == []
    assert job.estimated_vram_gb == 0
    assert job.priority == 0
    assert job.workflow_id is None
    assert job.reason is None


def test_tier_values_mapping():
    """TIER_VALUES maps correctly."""
    assert TIER_VALUES == {"light": 1, "medium": 2, "heavy": 3}
    assert TIER_VALUES["light"] < TIER_VALUES["medium"] < TIER_VALUES["heavy"]


def test_select_worker_with_health_error_penalty():
    """Worker with last_health_error is penalized in scoring.

    With two workers at same tier+queue, the healthy one wins.
    """
    workers = [
        make_worker("w-healthy", tier="heavy"),
        make_worker("w-sick", tier="heavy"),
    ]
    statuses = [
        make_status("w-healthy", online=True, queue_pending=0, queue_running=0),
        make_status("w-sick", online=True, queue_pending=0, queue_running=0,
                    last_health_error="system_stats timeout"),
    ]

    with (
        patch("services.comfyui_scheduler.list_workers", return_value=workers),
        patch("services.comfyui_scheduler.get_workers_status", AsyncMock(return_value=statuses)),
    ):
        job = SchedulerJob(job_class="heavy")
        result = asyncio.run(select_worker(job))

    assert result["id"] == "w-healthy"


def test_select_worker_vram_zero_means_unlimited():
    """Worker with vram_gb=0 accepts any estimated_vram_gb (legacy compat)."""
    workers = [make_worker("legacy", tier="heavy", vram_gb=0)]
    statuses = [make_status("legacy", online=True)]

    with (
        patch("services.comfyui_scheduler.list_workers", return_value=workers),
        patch("services.comfyui_scheduler.get_workers_status", AsyncMock(return_value=statuses)),
    ):
        job = SchedulerJob(job_class="auto", estimated_vram_gb=999)
        result = asyncio.run(select_worker(job))

    assert result is not None
    assert result["id"] == "legacy"


def test_required_models_satisfied_selects_worker():
    """When required_models are all present, the worker is selected."""
    workers = [make_worker("w1", tier="heavy")]
    statuses = [make_status("w1", online=True)]
    fake_oi = make_object_info(checkpoint_names=["dreamshaper.safetensors", "sd_xl.safetensors"])

    with (
        patch("services.comfyui_scheduler.list_workers", return_value=workers),
        patch("services.comfyui_scheduler.get_workers_status", AsyncMock(return_value=statuses)),
        patch("services.comfyui_scheduler._fetch_object_info", AsyncMock(return_value=fake_oi)),
    ):
        job = SchedulerJob(
            job_class="auto",
            required_models=["dreamshaper.safetensors"],
        )
        result = asyncio.run(select_worker(job))

    assert result["id"] == "w1"


def test_required_nodes_satisfied_selects_worker():
    """When required_nodes are all present, the worker is selected."""
    workers = [make_worker("w1", tier="heavy")]
    statuses = [make_status("w1", online=True)]
    fake_oi = make_object_info(
        checkpoint_names=["dummy.safetensors"],
        node_names=["KSampler", "CLIPTextEncode", "SaveImage"],
    )

    with (
        patch("services.comfyui_scheduler.list_workers", return_value=workers),
        patch("services.comfyui_scheduler.get_workers_status", AsyncMock(return_value=statuses)),
        patch("services.comfyui_scheduler._fetch_object_info", AsyncMock(return_value=fake_oi)),
    ):
        job = SchedulerJob(
            job_class="auto",
            required_nodes=["KSampler"],
        )
        result = asyncio.run(select_worker(job))

    assert result["id"] == "w1"


def test_required_tags_satisfied_selects_worker():
    """Worker with matching tags is selected."""
    workers = [make_worker("w-tagged", tier="heavy", tags=["flux", "sdxl", "video"])]
    statuses = [make_status("w-tagged", online=True)]

    with (
        patch("services.comfyui_scheduler.list_workers", return_value=workers),
        patch("services.comfyui_scheduler.get_workers_status", AsyncMock(return_value=statuses)),
    ):
        job = SchedulerJob(job_class="heavy", required_tags=["flux"])
        result = asyncio.run(select_worker(job))

    assert result["id"] == "w-tagged"


def test_required_tags_case_insensitive():
    """Tag matching is case-insensitive: worker tags are normalized (lowercase)
    and job tags are lowercased for comparison."""
    # Worker tags come pre-normalized (lowercase) from the registry
    workers = [make_worker("w1", tier="heavy", tags=["flux", "sdxl"])]
    statuses = [make_status("w1", online=True)]

    with (
        patch("services.comfyui_scheduler.list_workers", return_value=workers),
        patch("services.comfyui_scheduler.get_workers_status", AsyncMock(return_value=statuses)),
    ):
        # Job tags can be mixed case — scheduler lowercases them
        job = SchedulerJob(job_class="heavy", required_tags=["FLUX", "SDXL"])
        result = asyncio.run(select_worker(job))

    assert result["id"] == "w1"


# ---------------------------------------------------------------------------
# Integration tests — skipped by default
# ---------------------------------------------------------------------------

def _should_run_integration():
    """Return True when RUN_COMFYUI_INTEGRATION=1 env var is set."""
    return os.getenv("RUN_COMFYUI_INTEGRATION", "").strip() == "1"


# pytest marker integration: use skipif when pytest is available
if HAS_PYTEST:
    _integration_skip = pytest.mark.skipif(
        not _should_run_integration(),
        reason="Set RUN_COMFYUI_INTEGRATION=1 to run ComfyUI integration tests",
    )
else:
    _integration_skip = lambda f: f  # no-op decorator


@_integration_skip
def test_select_worker_integration():
    """Integration test: real ComfyUI at COMFYUI_BASE_URL.

    This test hits the real ComfyUI and verifies worker selection end-to-end.
    Skipped by default — set RUN_COMFYUI_INTEGRATION=1 to enable.
    """

    async def _run():
        # Verify the real ComfyUI is reachable
        from services.comfyui import get_status, list_checkpoints

        status = await get_status()
        assert isinstance(status, dict), f"get_status returned {type(status)}"

        ckpts = await list_checkpoints()
        assert isinstance(ckpts, list), f"list_checkpoints returned {type(ckpts)}"

        # Auto job → should find a worker
        job = SchedulerJob(job_class="auto")
        worker = await select_worker(job)
        assert worker is not None, "Expected a worker for auto job"
        assert "url" in worker, f"Worker missing url: {worker}"

        # Light job_class
        job = SchedulerJob(job_class="light")
        worker = await select_worker(job)
        assert worker is not None, "Expected a worker for light job"

        # Heavy job_class
        job = SchedulerJob(job_class="heavy")
        worker = await select_worker(job)
        assert worker is not None, "Expected a worker for heavy job"

        # Unknown model → should raise SchedulerError
        job = SchedulerJob(
            job_class="auto",
            required_models=["this_model_does_not_exist_xyz.safetensors"],
        )
        try:
            await select_worker(job)
            assert False, "Should have raised SchedulerError for missing model"
        except SchedulerError:
            pass

        return True

    ok = asyncio.run(_run())
    assert ok, "Integration tests failed"


# ---------------------------------------------------------------------------
# Standalone runner (python3 tests/test_scheduler.py)
# ---------------------------------------------------------------------------

def _run_all_tests():
    """Collect and run all test_* functions manually."""
    import traceback

    # Get all functions starting with test_ in this module
    test_funcs = [
        (name, obj)
        for name, obj in globals().items()
        if name.startswith("test_") and callable(obj)
    ]

    # Separate unit and integration tests
    unit_tests = [
        (n, f) for n, f in test_funcs if n != "test_select_worker_integration"
    ]
    integration_tests = [
        (n, f) for n, f in test_funcs if n == "test_select_worker_integration"
    ]

    passed = 0
    failed = 0
    skipped = 0

    # --- Unit tests ---
    print("=" * 65)
    print("Unit Tests (mocked)")
    print("=" * 65)
    for name, func in unit_tests:
        try:
            func()
            print(f"  PASS  {name}")
            passed += 1
        except Exception:
            print(f"  FAIL  {name}")
            traceback.print_exc()
            failed += 1

    # --- Integration tests ---
    print()
    print("=" * 65)
    print("Integration Tests (requires ComfyUI)")
    print("=" * 65)
    if not _should_run_integration():
        print(
            "  SKIP  test_select_worker_integration  "
            "(Set RUN_COMFYUI_INTEGRATION=1 to run)"
        )
        skipped += len(integration_tests)
    else:
        for name, func in integration_tests:
            try:
                func()
                print(f"  PASS  {name}")
                passed += 1
            except Exception:
                print(f"  FAIL  {name}")
                traceback.print_exc()
                failed += 1

    # --- Summary ---
    print()
    print("=" * 65)
    total = passed + failed + skipped
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped ({total} total)")
    print("=" * 65)

    if failed > 0:
        sys.exit(1)


# Helper for non-pytest: context manager that catches the exception
class _raises:
    """Minimal context manager for asserting exceptions without pytest."""

    def __init__(self, exc_type):
        self.exc_type = exc_type
        self.exception = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            raise AssertionError(f"Expected {self.exc_type.__name__} but no exception raised")
        if issubclass(exc_type, self.exc_type):
            self.exception = exc_val
            return True  # suppress
        return False  # re-raise unexpected exceptions


if __name__ == "__main__":
    _run_all_tests()
