import logging
import os
import re
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

MINIMAX_BASE_URL = "https://api.minimaxi.com"

# Profile config path (project-root/config/profiles.json)
PROFILE_CONFIG = Path(__file__).resolve().parent.parent.parent / "config" / "profiles.json"

# Valid model name format: alphanumeric, dash, underscore
_VALID_MODEL_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")

# Default priority when not specified
_DEFAULT_PRIORITY = 999


def _resolve_api_key(raw_key: str) -> str:
    """
    Resolve API key from profiles.json.

    Supports two forms:
      - Plain text key:  "sk-cp-xxxxx"
      - Env-var reference: "${MINIMAX_API_KEY}"  → reads os.environ["MINIMAX_API_KEY"]

    Falls back to empty string if the env var is unset.
    """
    raw = raw_key.strip()
    if raw.startswith("${") and raw.endswith("}"):
        env_var = raw[2:-1]
        return os.environ.get(env_var, "")
    return raw


def _load_profiles() -> list:
    """
    Load and validate profiles from profiles.json.

    Logs a warning once at startup if the file is missing.
    Returns [] for other read errors so the server still boots
    (the actual routing call will fail with a clear error at request time).
    """
    import json as _json

    if not PROFILE_CONFIG.exists():
        logger.warning(
            "profiles.json not found at %s — model routing will fail until resolved. "
            "Copy config/profiles.json.example to config/profiles.json and configure your API keys.",
            PROFILE_CONFIG,
        )
        return []
    try:
        with open(PROFILE_CONFIG) as f:
            raw = _json.load(f)
    except Exception as exc:
        logger.warning("Failed to read profiles.json: %s", exc)
        return []

    if isinstance(raw, dict):
        return raw.get("profiles", [])
    return []


def _validate_model_name(model_name: str) -> str:
    """
    Validate model_name against the allowed character pattern.

    Raises ValueError if the name contains unexpected characters,
    preventing potential injection into profile matching.
    """
    if not _VALID_MODEL_RE.match(model_name):
        raise ValueError(
            f"Invalid model name format: {model_name!r}. "
            "Only alphanumeric characters, dashes, and underscores are allowed."
        )
    return model_name


def _get_api_key_for_model(model_name: str) -> str:
    """
    Find the enabled profile that declares the given model,
    sorted by priority (ascending, lower = higher priority).

    Raises ValueError with a clear message if no matching profile is found.
    """
    _validate_model_name(model_name)

    profiles = _load_profiles()
    if not profiles:
        raise ValueError(
            f"No profiles configured — check profiles.json at {PROFILE_CONFIG}. "
            "At least one enabled profile with the requested model is required."
        )

    matching: list[tuple[int, str, str]] = []  # (priority, profile_name, resolved_key)
    for p in profiles:
        if not p.get("enabled", True):
            continue
        for cat, model_list in p.get("models", {}).items():
            if model_name in model_list:
                priority = p.get("priority", _DEFAULT_PRIORITY)
                raw_key = p.get("api_key", "")
                resolved_key = _resolve_api_key(raw_key)
                if resolved_key:
                    matching.append((priority, p.get("name", ""), resolved_key))
                break

    if not matching:
        available = [
            (p.get("name", ""), list(p.get("models", {}).values()))
            for p in profiles
            if p.get("enabled", True)
        ]
        raise ValueError(
            f"No enabled profile found for model: {model_name!r}. "
            f"Available profiles: {available}"
        )

    # Stable sort: primary key=priority, secondary key=profile name (lexicographic)
    matching.sort(key=lambda x: (x[0], x[1]))
    chosen = matching[0]
    logger.info(
        "Routing model=%s → profile=%s (priority=%d)",
        model_name, chosen[1], chosen[0],
    )
    return chosen[2]


# ── API wrappers ────────────────────────────────────────


async def generate_image(
    prompt: str,
    model: str = "image-01",
    aspect_ratio: str = "16:9",
    n: int = 1,
    response_format: str = "url",
    prompt_optimizer: bool = False,
) -> dict:
    """MiniMax 文生图 API，按 model 名路由到对应 profile"""
    api_key = _get_api_key_for_model(model)

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{MINIMAX_BASE_URL}/v1/image_generation",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "n": n,
                "response_format": response_format,
                "prompt_optimizer": prompt_optimizer,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def generate_voice(
    text: str,
    voice_id: str = "male-qn-qingse",
    model: str = "speech-02-hd",
    speed: float = 1.0,
    vol: float = 1.0,
    pitch: float = 0.0,
    emotion: str = "neutral",
    response_format: str = "mp3",
) -> dict:
    """MiniMax TTS API，按 model 路由到对应 profile"""
    api_key = _get_api_key_for_model(model)

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{MINIMAX_BASE_URL}/v1/t2a_v2",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "text": text,
                "voice_id": voice_id,
                "speed": speed,
                "vol": vol,
                "pitch": pitch,
                "emotion": emotion,
                "response_format": response_format,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def generate_video(
    prompt: str,
    model: str = "hailuo-video-01",
    duration: str = "6s",
    resolution: str = "720p",
    fps: int = 30,
    seed: Optional[int] = None,
) -> dict:
    """MiniMax Hailuo 文生视频 API，按 model 路由到对应 profile"""
    api_key = _get_api_key_for_model(model)

    payload = {
        "model": model,
        "prompt": prompt,
        "duration": duration,
        "resolution": resolution,
        "fps": fps,
    }
    if seed is not None:
        payload["seed"] = seed

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{MINIMAX_BASE_URL}/v1/video_generation",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


async def generate_music(
    prompt: str,
    model: str = "music-01",
) -> dict:
    """MiniMax Music API，按 model 路由到对应 profile"""
    api_key = _get_api_key_for_model(model)

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{MINIMAX_BASE_URL}/v1/music_generation",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "prompt": prompt,
            },
        )
        resp.raise_for_status()
        return resp.json()
