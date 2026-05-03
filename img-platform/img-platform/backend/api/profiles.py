import json
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/profiles", tags=["Profile 管理"])

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "profiles.json"
CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)


class ProfileModel(BaseModel):
    name: str
    api_key: str
    enabled: bool = True
    priority: int = 1
    models: dict = {}


class ProfileOut(BaseModel):
    name: str
    api_key_masked: str  # 只返回后4位
    enabled: bool
    priority: int
    models: dict


def _load() -> list:
    """返回 profiles 列表"""
    if not CONFIG_PATH.exists():
        return []
    with open(CONFIG_PATH) as f:
        raw = json.load(f)
    # 支持 { "token-plan": {...} } 或 { "profiles": [...] } 两种格式
    if isinstance(raw, dict):
        if "profiles" in raw:
            return raw["profiles"]
        # flat dict with profile name as key → 转成 list
        return [
            {"name": k, **v} for k, v in raw.items()
        ]
    return []


def _save(profiles: list):
    data = {"profiles": profiles}
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _mask_key(key: str) -> str:
    if len(key) <= 4:
        return "****"
    return "****" + key[-4:]


@router.get("")
def list_profiles():
    """列出所有 profiles，api_key 脱敏"""
    profiles = _load()
    return [
        ProfileOut(
            name=p["name"],
            api_key_masked=_mask_key(p.get("api_key", "")),
            enabled=p.get("enabled", True),
            priority=p.get("priority", 1),
            models=p.get("models", {}),
        )
        for p in profiles
    ]


@router.get("/models")
def list_models():
    """聚合所有启用 profile 的模型，按 category 返回"""
    profiles = _load()
    models_by_category = {}
    for p in profiles:
        if not p.get("enabled", True):
            continue
        for cat, model_list in p.get("models", {}).items():
            if cat not in models_by_category:
                models_by_category[cat] = []
            for m in model_list:
                if m not in models_by_category[cat]:
                    models_by_category[cat].append(m)
    return models_by_category


@router.post("")
def create_profile(prof: ProfileModel):
    profiles = _load()
    for p in profiles:
        if p["name"] == prof.name:
            raise HTTPException(status_code=400, detail=f"Profile '{prof.name}' 已存在")
    profiles.append(prof.model_dump())
    _save(profiles)
    return {"ok": True, "name": prof.name}


@router.put("/{name}")
def update_profile(name: str, prof: ProfileModel):
    profiles = _load()
    for i, p in enumerate(profiles):
        if p["name"] == name:
            profiles[i] = prof.model_dump()
            _save(profiles)
            return {"ok": True}
    raise HTTPException(status_code=404, detail=f"Profile '{name}' 不存在")


@router.delete("/{name}")
def delete_profile(name: str):
    profiles = _load()
    new_profiles = [p for p in profiles if p["name"] != name]
    if len(new_profiles) == len(profiles):
        raise HTTPException(status_code=404, detail=f"Profile '{name}' 不存在")
    _save(new_profiles)
    return {"ok": True}


@router.post("/{name}/enable")
def enable_profile(name: str):
    profiles = _load()
    for p in profiles:
        if p["name"] == name:
            p["enabled"] = True
            _save(profiles)
            return {"ok": True}
    raise HTTPException(status_code=404, detail=f"Profile '{name}' 不存在")


@router.post("/{name}/disable")
def disable_profile(name: str):
    profiles = _load()
    for p in profiles:
        if p["name"] == name:
            p["enabled"] = False
            _save(profiles)
            return {"ok": True}
    raise HTTPException(status_code=404, detail=f"Profile '{name}' 不存在")
