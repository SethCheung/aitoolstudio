from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.profile_manager import (
    list_profiles,
    get_profile,
    add_profile,
    update_profile,
    delete_profile,
    set_enabled,
    get_all_models,
)

router = APIRouter(prefix="/api/profiles", tags=["Profile 管理"])


class ProfileCreateRequest(BaseModel):
    name: str
    api_key: str
    base_url: str = "https://api.minimaxi.com"
    enabled: bool = True
    priority: int = 99
    daily_quota: Optional[int] = None
    monthly_quota: Optional[int] = None
    notes: str = ""
    models: dict = {}  # {"image": ["image-01"], "voice": ["speech-02-hd"]}


class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    daily_quota: Optional[int] = None
    monthly_quota: Optional[int] = None
    notes: Optional[str] = None
    models: Optional[dict] = None


def _mask_key(key: str) -> str:
    """只返回 api_key 后4位，隐私保护"""
    if len(key) <= 4:
        return "****"
    return "****" + key[-4:]


@router.get("")
async def list_all():
    """列出所有 profiles（api_key 脱敏）"""
    raw = list_profiles()
    # list_profiles already strips api_key, so we just return raw
    return raw


@router.get("/models")
async def available_models():
    """获取所有可用模型（按 category 分组，带来源标签）"""
    return get_all_models()


@router.get("/{name}")
async def get(name: str):
    """获取指定 profile（含 api_key）"""
    profile = get_profile(name)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    return profile


@router.post("")
async def create(req: ProfileCreateRequest):
    """添加新 profile"""
    try:
        profile = add_profile(req.name, {
            "name": req.name,
            "api_key": req.api_key,
            "base_url": req.base_url,
            "enabled": req.enabled,
            "priority": req.priority,
            "daily_quota": req.daily_quota,
            "monthly_quota": req.monthly_quota,
            "notes": req.notes,
            "models": req.models,
        })
        return profile
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{name}")
async def update(name: str, req: ProfileUpdateRequest):
    """更新 profile"""
    current = get_profile(name)
    if not current:
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")

    update_data = {k: v for k, v in req.model_dump().items() if v is not None}
    if "name" in update_data:
        del update_data["name"]  # 不允许改 name

    merged = {**current, **update_data}
    try:
        return update_profile(name, merged)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{name}")
async def remove(name: str):
    """删除 profile"""
    if not delete_profile(name):
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    return {"ok": True}


@router.post("/{name}/enable")
async def enable(name: str):
    """启用 profile"""
    profile = set_enabled(name, True)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    return profile


@router.post("/{name}/disable")
async def disable(name: str):
    """禁用 profile"""
    profile = set_enabled(name, False)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    return profile
