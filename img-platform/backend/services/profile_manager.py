import json
import os
from functools import lru_cache
from typing import Optional

PROFILE_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "profiles.json")


@lru_cache(maxsize=1)
def _load() -> dict:
    """从文件加载 profiles（带缓存）

    profiles.json 支持两种格式：
      1. dict 格式（推荐）：{"profiles": {"name": {...}}}
      2. list 格式（兼容）：{"profiles": [...]}
    """
    if not os.path.exists(PROFILE_FILE):
        return {"profiles": {}}
    with open(PROFILE_FILE, "r") as f:
        data = json.load(f)

    raw = data.get("profiles", {})
    # 兼容 list 格式：转换为 dict 格式
    if isinstance(raw, list):
        profiles = {}
        for item in raw:
            name = item.get("name")
            if name:
                profiles[name] = item
        return {"profiles": profiles}
    return {"profiles": raw}


def _save(data: dict) -> None:
    """保存 profiles 到文件"""
    os.makedirs(os.path.dirname(PROFILE_FILE), exist_ok=True)
    with open(PROFILE_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    _load.cache_clear()  # 清缓存


def get_profile_for_model(model: str) -> Optional[dict]:
    """根据模型名找到支持它的 enabled profile，按 priority 排序返回第一个"""
    data = _load()
    profiles = data.get("profiles", {})

    # 收集所有支持的 profile
    candidates = []
    for name, profile in profiles.items():
        if not profile.get("enabled", False):
            continue
        models = profile.get("models", {})
        # 遍历所有 category 找这个 model
        for category, model_list in models.items():
            if model in model_list:
                candidates.append((profile.get("priority", 999), name, profile))
                break

    if not candidates:
        return None

    # 按 priority 排序
    candidates.sort(key=lambda x: x[0])
    _, name, profile = candidates[0]
    return {"name": name, **profile}


def list_profiles() -> list[dict]:
    """列出所有 profiles（不含 api_key，补充脱敏字段）"""
    data = _load()
    profiles = []
    for name, profile in data.get("profiles", {}).items():
        api_key = profile.get("api_key") or ""
        safe_profile = {k: v for k, v in profile.items() if k != "api_key"}
        safe_profile["name"] = name
        safe_profile["api_key_masked"] = "****" + api_key[-4:] if len(api_key) > 4 else "****"
        profiles.append(safe_profile)
    profiles.sort(key=lambda p: (p.get("priority", 999), p.get("name", "")))
    return profiles


def get_profile(name: str) -> Optional[dict]:
    """获取指定 profile（含 api_key）"""
    data = _load()
    profile = data.get("profiles", {}).get(name)
    if profile:
        return {"name": name, **profile}
    return None


def add_profile(name: str, profile_data: dict) -> dict:
    """添加新 profile"""
    data = _load()
    if name in data.get("profiles", {}):
        raise ValueError(f"Profile '{name}' already exists")

    if "profiles" not in data:
        data["profiles"] = {}

    data["profiles"][name] = profile_data
    _save(data)
    return get_profile(name)


def update_profile(name: str, profile_data: dict) -> dict:
    """更新 profile"""
    data = _load()
    if name not in data.get("profiles", {}):
        raise ValueError(f"Profile '{name}' not found")

    # 保留 api_key 如果新数据没提供
    existing = data["profiles"][name]
    if "api_key" in existing and "api_key" not in profile_data:
        profile_data["api_key"] = existing["api_key"]

    data["profiles"][name] = profile_data
    _save(data)
    return get_profile(name)


def delete_profile(name: str) -> bool:
    """删除 profile"""
    data = _load()
    if name not in data.get("profiles", {}):
        return False
    del data["profiles"][name]
    _save(data)
    return True


def set_enabled(name: str, enabled: bool) -> Optional[dict]:
    """启用/禁用 profile"""
    data = _load()
    if name not in data.get("profiles", {}):
        return None
    data["profiles"][name]["enabled"] = enabled
    _save(data)
    return get_profile(name)


def get_all_models() -> dict:
    """获取所有可用模型，按 category 分组，附带来源 profile 名"""
    data = _load()
    result = {}  # category -> {model_name: [profile_names]}

    for pname, profile in data.get("profiles", {}).items():
        if not profile.get("enabled", False):
            continue
        for category, model_list in profile.get("models", {}).items():
            if category not in result:
                result[category] = {}
            for model in model_list:
                if model not in result[category]:
                    result[category][model] = []
                result[category][model].append(pname)

    # Flatten: { category: [model_names] }
    # e.g. { "image": ["image-01", "image-01-turbo"], "voice": ["speech-02-hd", "speech-02"] }
    flattened = {}
    for cat, models in result.items():
        flattened[cat] = list(models.keys())

    image_models = flattened.setdefault("image", [])
    if "comfyui-local" not in image_models:
        image_models.append("comfyui-local")

    video_models = flattened.setdefault("video", [])
    if not video_models:
        video_models.extend(["MiniMax-Hailuo-2.3", "MiniMax-Hailuo-2.3-Fast", "MiniMax-Hailuo-02", "S2V-01"])
    if "comfyui-local-video" not in video_models:
        video_models.append("comfyui-local-video")

    return flattened
