import json as _json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

MINIMAX_BASE_URL = "https://api.minimaxi.com"

# Profile config path. Override with env PROFILES_PATH; default falls back to
# <repo>/config/profiles.json relative to this file (../../config/profiles.json).
_DEFAULT_PROFILE_CONFIG = Path(__file__).resolve().parent.parent.parent / "config" / "profiles.json"
PROFILE_CONFIG = Path(os.environ.get("PROFILES_PATH") or _DEFAULT_PROFILE_CONFIG)

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
        val = os.environ.get(env_var, "")
        if not val:
            logger.warning(
                "Profile references unset env var %s — treating as missing key", env_var
            )
        return val
    return raw


@lru_cache(maxsize=4)
def _load_profiles_cached(path_str: str, mtime: float) -> tuple:
    """Read and parse profiles.json. Cached on (path, mtime) so edits are picked up
    automatically without a restart, while avoiding disk I/O on every request.
    Returns a tuple so the cached value is hashable/immutable."""
    path = Path(path_str)
    try:
        with open(path) as f:
            raw = _json.load(f)
    except Exception as exc:
        logger.warning("Failed to read profiles.json at %s: %s", path, exc)
        return tuple()
    if isinstance(raw, dict):
        return tuple(raw.get("profiles", []))
    return tuple()


def _load_profiles() -> list:
    """Load profiles, refreshing the cache automatically when the file's mtime changes."""
    if not PROFILE_CONFIG.exists():
        logger.warning(
            "profiles.json not found at %s — model routing will fail until resolved. "
            "Copy config/profiles.json.example to config/profiles.json and configure your API keys.",
            PROFILE_CONFIG,
        )
        return []
    try:
        mtime = PROFILE_CONFIG.stat().st_mtime
    except OSError:
        mtime = 0.0
    return list(_load_profiles_cached(str(PROFILE_CONFIG), mtime))


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
        # Log full profile listing server-side for debugging, but do NOT leak
        # profile names / configured models in the user-facing error message.
        available = [
            (p.get("name", ""), list(p.get("models", {}).values()))
            for p in profiles
            if p.get("enabled", True)
        ]
        logger.warning(
            "No enabled profile found for model=%s. Available: %s", model_name, available
        )
        raise ValueError(f"No profile available for model: {model_name}")

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
    model: str = "speech-2.8-hd",
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
                "stream": False,
                "voice_setting": {
                    "voice_id": voice_id,
                    "speed": speed,
                    "vol": vol,
                    "pitch": pitch,
                    "emotion": emotion,
                },
                "audio_setting": {
                    "sample_rate": 32000,
                    "bitrate": "128000",
                    "format": response_format,
                    "channel": 1,
                },
                "subtitle_enable": False,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def generate_video(
    prompt: str,
    model: str = "MiniMax-Hailuo-2.3",
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
    model: str = "music-2.6",
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
