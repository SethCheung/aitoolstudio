from typing import Optional

import httpx
import os
from dotenv import load_dotenv

load_dotenv()

DEFAULT_API_KEY = os.getenv("MINIMAX_API_KEY", "")
DEFAULT_BASE_URL = "https://api.minimax.io"


async def optimize_prompt(
    prompt: str,
    model: str = "MiniMax-M2.7",
    target: str = "image",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> dict:
    """调用 MiniMax 文本模型，将用户输入扩写为更适合生成的 prompt"""
    key = api_key or DEFAULT_API_KEY
    url = base_url or DEFAULT_BASE_URL
    if not key:
        raise ValueError("MINIMAX_API_KEY not configured")

    system_prompt = (
        "You are a prompt engineer for an internal creative AI platform. "
        "Rewrite the user's short request into one polished prompt for the target generation model. "
        "Preserve the user's intent and concrete details. Do not add unsafe, branded, or unrelated content. "
        "Return only the optimized prompt, with no headings, quotes, markdown, or explanations."
    )
    user_prompt = (
        f"Target generation type: {target}\n"
        f"User request: {prompt}\n\n"
        "Write a concise but vivid generation prompt. Include subject, composition, style, lighting, "
        "color palette, mood, and useful production details when they fit the request."
    )

    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post(
            f"{url}/v1/text/chatcompletion_v2",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "name": "prompt_engineer", "content": system_prompt},
                    {"role": "user", "name": "user", "content": user_prompt},
                ],
            },
        )
        resp.raise_for_status()
        return resp.json()


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
