from typing import Optional
import httpx
import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

MINIMAX_BASE_URL = "https://api.minimaxi.com"

# Profile config path (project-root/config/profiles.json)
PROFILE_CONFIG = Path(__file__).resolve().parent.parent.parent / "config" / "profiles.json"


def _load_profiles() -> list:
    if not PROFILE_CONFIG.exists():
        return []
    with open(PROFILE_CONFIG) as f:
        raw = json.load(f)
    if isinstance(raw, dict):
        return raw.get("profiles", [])
    return []


def _get_api_key_for_model(model_name: str) -> str:
    """
    Find the enabled profile that declares the given model,
    returned sorted by priority (asc). Returns the API key or empty string.
    """
    profiles = _load_profiles()
    matching = []
    for p in profiles:
        if not p.get("enabled", True):
            continue
        for cat, model_list in p.get("models", {}).items():
            if model_name in model_list:
                matching.append((p.get("priority", 999), p.get("api_key", "")))
                break
    matching.sort(key=lambda x: x[0])
    return matching[0][1] if matching else ""


async def generate_image(
    prompt: str,
    model: str = "image-01",
    aspect_ratio: str = "16:9",
    n: int = 1,
    response_format: str = "url",
    prompt_optimizer: bool = False,
) -> dict:
    """调用 MiniMax 文生图 API，按 model 名自动路由到对应 profile"""
    api_key = _get_api_key_for_model(model)
    if not api_key:
        raise ValueError(f"No enabled profile found for model: {model}")

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
    """调用 MiniMax TTS API，按 model 路由到对应 profile"""
    api_key = _get_api_key_for_model(model)
    if not api_key:
        raise ValueError(f"No enabled profile found for model: {model}")

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
    """调用 MiniMax Hailuo 文生视频 API，按 model 路由到对应 profile"""
    api_key = _get_api_key_for_model(model)
    if not api_key:
        raise ValueError(f"No enabled profile found for model: {model}")

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
    """调用 MiniMax Music API，按 model 路由到对应 profile"""
    api_key = _get_api_key_for_model(model)
    if not api_key:
        raise ValueError(f"No enabled profile found for model: {model}")

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
