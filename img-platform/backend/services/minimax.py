from typing import Optional

import httpx
import os
from dotenv import load_dotenv

load_dotenv()

DEFAULT_API_KEY = os.getenv("MINIMAX_API_KEY", "")
DEFAULT_BASE_URL = "https://api.minimaxi.com"


async def generate_image(
    prompt: str,
    model: str = "image-01",
    aspect_ratio: str = "16:9",
    n: int = 1,
    response_format: str = "url",
    prompt_optimizer: bool = False,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> dict:
    """调用 MiniMax 文生图 API"""
    key = api_key or DEFAULT_API_KEY
    url = base_url or DEFAULT_BASE_URL
    if not key:
        raise ValueError("MINIMAX_API_KEY not configured")

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{url}/v1/image_generation",
            headers={
                "Authorization": f"Bearer {key}",
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
    speed: int = 1,
    vol: int = 1,
    pitch: int = 0,
    emotion: str = "neutral",
    response_format: str = "mp3",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> dict:
    """调用 MiniMax TTS (语音合成) API"""
    key = api_key or DEFAULT_API_KEY
    url = base_url or DEFAULT_BASE_URL
    if not key:
        raise ValueError("MINIMAX_API_KEY not configured")

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{url}/v1/t2a_v2",
            headers={
                "Authorization": f"Bearer {key}",
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
                    "bitrate": 128000,
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
    duration: int = 6,
    resolution: str = "768P",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> dict:
    """调用 MiniMax Hailuo (文生视频) API — 异步，返回 task_id"""
    key = api_key or DEFAULT_API_KEY
    url = base_url or DEFAULT_BASE_URL
    if not key:
        raise ValueError("MINIMAX_API_KEY not configured")

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{url}/v1/video_generation",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "prompt": prompt,
                "duration": duration,
                "resolution": resolution,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def query_video_task(task_id: str, api_key: Optional[str] = None, base_url: Optional[str] = None) -> dict:
    """查询视频生成任务状态"""
    key = api_key or DEFAULT_API_KEY
    url = base_url or DEFAULT_BASE_URL
    if not key:
        raise ValueError("MINIMAX_API_KEY not configured")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{url}/v1/video_generation",
            headers={"Authorization": f"Bearer {key}"},
            params={"task_id": task_id},
        )
        resp.raise_for_status()
        return resp.json()


async def generate_music(
    prompt: str,
    model: str = "music-2.6",
    lyrics: str = "",
    is_instrumental: bool = False,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> dict:
    """调用 MiniMax Music API"""
    key = api_key or DEFAULT_API_KEY
    url = base_url or DEFAULT_BASE_URL
    if not key:
        raise ValueError("MINIMAX_API_KEY not configured")

    payload = {
        "model": model,
        "prompt": prompt,
        "output_format": "url",
        "is_instrumental": is_instrumental,
    }
    if lyrics:
        payload["lyrics"] = lyrics

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{url}/v1/music_generation",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()
