from typing import Optional

import httpx
import os
from dotenv import load_dotenv

load_dotenv()

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_BASE_URL = "https://api.minimaxi.com"


async def generate_image(
    prompt: str,
    model: str = "image-01",
    aspect_ratio: str = "16:9",
    n: int = 1,
    response_format: str = "url",
    prompt_optimizer: bool = False,
) -> dict:
    """调用 MiniMax 文生图 API"""
    if not MINIMAX_API_KEY:
        raise ValueError("MINIMAX_API_KEY not configured")

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{MINIMAX_BASE_URL}/v1/image_generation",
            headers={
                "Authorization": f"Bearer {MINIMAX_API_KEY}",
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
    """调用 MiniMax TTS (语音合成) API"""
    if not MINIMAX_API_KEY:
        raise ValueError("MINIMAX_API_KEY not configured")

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{MINIMAX_BASE_URL}/v1/t2a_v2",
            headers={
                "Authorization": f"Bearer {MINIMAX_API_KEY}",
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
    """调用 MiniMax Hailuo (文生视频) API"""
    if not MINIMAX_API_KEY:
        raise ValueError("MINIMAX_API_KEY not configured")

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
                "Authorization": f"Bearer {MINIMAX_API_KEY}",
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
    """调用 MiniMax Music API"""
    if not MINIMAX_API_KEY:
        raise ValueError("MINIMAX_API_KEY not configured")

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{MINIMAX_BASE_URL}/v1/music_generation",
            headers={
                "Authorization": f"Bearer {MINIMAX_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "prompt": prompt,
            },
        )
        resp.raise_for_status()
        return resp.json()
