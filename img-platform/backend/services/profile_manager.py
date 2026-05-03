import json
import os
from typing import Optional

PROFILE_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "profiles.json")


def _load() -> dict:
    """从文件加载 profiles"""
    if not os.path.exists(PROFILE_FILE):
        return {"profiles": {}}
    with open(PROFILE_FILE, "r") as f:
        return json.load(f)


def _save(data: dict) -> None:
    """保存 profiles 到文件"""
    os.makedirs(os.path.dirname(PROFILE_FILE), exist_ok=True)
    with open(PROFILE_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


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


def list_profiles() -> dict:
    """列出所有 profiles（不含 api_key）"""
    data = _load()
    profiles = {}
    for name, profile in data.get("profiles", {}).items():
        # 隐藏 api_key
        safe_profile = {k: v for k, v in profile.items() if k != "api_key"}
        profiles[name] = safe_profile
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

    return result
