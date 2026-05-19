from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from api.auth import get_current_user, require_admin
from models.user import User
from services.comfyui import generate_sam_mask, get_status, list_checkpoints
from services.comfyui_workflows import delete_workflow, import_workflows_from_dir, list_workflows, reorder_workflows, upsert_workflow
from services.comfyui_workers import (
    delete_worker,
    get_worker,
    get_workers_status,
    list_workers,
    upsert_worker,
)
from services.model_paths import delete_model_path, list_model_paths, upsert_model_path


router = APIRouter(prefix="/api/comfyui", tags=["ComfyUI"])


class ModelPathRequest(BaseModel):
    label: str
    category: str
    uri: str
    mount_path: Optional[str] = ""
    notes: Optional[str] = ""
    enabled: bool = True


class WorkflowRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    category: str = "image"
    enabled: bool = True
    workflow_json: dict
    notes: Optional[str] = ""
    backend: Optional[str] = ""


class WorkflowReorderRequest(BaseModel):
    category: str
    workflow_ids: list[str]


class SamMaskRequest(BaseModel):
    source_image: str
    x: float
    y: float
    dilation: int = 8
    bbox_expansion: int = 20


class WorkerRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    name: str
    url: str
    tier: str = "heavy"
    gpu: Optional[str] = ""
    vram_gb: int = 0
    tags: list[str] = Field(default_factory=list)
    model_root_uri: Optional[str] = ""
    model_mount_path: Optional[str] = ""
    enabled: bool = True
    notes: Optional[str] = ""


@router.get("/status")
async def status(_: User = Depends(get_current_user)):
    """Return local ComfyUI service status."""
    try:
        return await get_status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ComfyUI 不可用: {exc}")


@router.get("/checkpoints")
async def checkpoints(_: User = Depends(get_current_user)):
    """Return installed ComfyUI checkpoint model names."""
    try:
        return {"checkpoints": await list_checkpoints()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ComfyUI 模型列表读取失败: {exc}")


@router.post("/sam-mask")
async def sam_mask(req: SamMaskRequest, _: User = Depends(get_current_user)):
    """Return a visible SAM mask preview for an image click target."""
    if not 0 <= req.x <= 1 or not 0 <= req.y <= 1:
        raise HTTPException(status_code=400, detail="x/y 必须是 0-1 的归一化坐标")
    try:
        return await generate_sam_mask(
            source_image=req.source_image,
            x=req.x,
            y=req.y,
            dilation=req.dilation,
            bbox_expansion=req.bbox_expansion,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SAM 自动蒙版生成失败: {exc}")


@router.get("/model-paths")
async def model_paths(_: User = Depends(require_admin)):
    """Return saved ComfyUI model path shortcuts."""
    return {"paths": list_model_paths()}


@router.post("/model-paths")
async def create_model_path(req: ModelPathRequest, _: User = Depends(require_admin)):
    try:
        return upsert_model_path(req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/model-paths/{path_id}")
async def update_model_path(path_id: str, req: ModelPathRequest, _: User = Depends(require_admin)):
    try:
        return upsert_model_path(req.model_dump(), path_id=path_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/model-paths/{path_id}")
async def remove_model_path(path_id: str, _: User = Depends(require_admin)):
    if not delete_model_path(path_id):
        raise HTTPException(status_code=404, detail="Model path not found")
    return {"ok": True}


@router.get("/workflows")
async def workflows(include_disabled: bool = False, current_user: User = Depends(get_current_user)):
    """Return saved ComfyUI workflows. Admin can request disabled workflows too."""
    if include_disabled and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"workflows": list_workflows(include_disabled=include_disabled)}


@router.post("/workflows")
async def create_workflow(req: WorkflowRequest, _: User = Depends(require_admin)):
    try:
        return upsert_workflow(req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/workflows/{workflow_id}")
async def update_workflow(workflow_id: str, req: WorkflowRequest, _: User = Depends(require_admin)):
    try:
        return upsert_workflow(req.model_dump(), workflow_id=workflow_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/workflows/{workflow_id}")
async def remove_workflow(workflow_id: str, _: User = Depends(require_admin)):
    if not delete_workflow(workflow_id):
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"ok": True}


@router.post("/workflows/reorder")
async def reorder_workflow_list(req: WorkflowReorderRequest, _: User = Depends(require_admin)):
    if reorder_workflows(req.category, req.workflow_ids):
        return {"ok": True}
    raise HTTPException(status_code=400, detail="No workflows updated")


@router.post("/workflows/import")
async def import_workflows(_: User = Depends(require_admin)):
    return import_workflows_from_dir()


# ---------------------------------------------------------------------------
# Worker Registry
# ---------------------------------------------------------------------------


@router.get("/workers")
async def workers_list(_: User = Depends(get_current_user)):
    """Return all configured ComfyUI workers."""
    return {"workers": list_workers()}


@router.post("/workers")
async def workers_create(req: WorkerRequest, _: User = Depends(require_admin)):
    """Register a new ComfyUI worker."""
    try:
        return upsert_worker(req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/workers/{worker_id}")
async def workers_update(worker_id: str, req: WorkerRequest, _: User = Depends(require_admin)):
    """Update an existing ComfyUI worker."""
    try:
        return upsert_worker(req.model_dump(), worker_id=worker_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/workers/{worker_id}")
async def workers_delete(worker_id: str, _: User = Depends(require_admin)):
    """Remove a ComfyUI worker."""
    if not delete_worker(worker_id):
        raise HTTPException(status_code=404, detail="Worker not found")
    return {"ok": True}


@router.get("/workers/status")
async def workers_status(_: User = Depends(require_admin)):
    """Health-check all workers. A single offline worker does not fail the endpoint."""
    return {"workers": await get_workers_status()}
