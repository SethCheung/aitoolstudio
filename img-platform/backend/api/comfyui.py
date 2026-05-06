from fastapi import APIRouter, Depends, HTTPException

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from api.auth import get_current_user
from models.user import User
from services.comfyui import get_status, list_checkpoints


router = APIRouter(prefix="/api/comfyui", tags=["ComfyUI"])


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
