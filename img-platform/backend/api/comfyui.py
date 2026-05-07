from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from api.auth import get_current_user, require_admin
from models.user import User
from services.comfyui import get_status, list_checkpoints
from services.comfyui_workflows import delete_workflow, import_workflows_from_dir, list_workflows, upsert_workflow
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


@router.post("/workflows/import")
async def import_workflows(_: User = Depends(require_admin)):
    return import_workflows_from_dir()
