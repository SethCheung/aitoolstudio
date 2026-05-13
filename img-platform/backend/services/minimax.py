from typing import Optional

import httpx
import os
from dotenv import load_dotenv

load_dotenv()

DEFAULT_API_KEY = os.getenv("MINIMAX_API_KEY", "")
DEFAULT_BASE_URL = "https://api.minimax.io"


def _optimizer_instruction_for(target: str, generation_model: Optional[str] = None) -> str:
    normalized = target.lower().strip()
    is_comfy = generation_model and "comfyui" in generation_model.lower()

    if normalized == "voice":
        return (
            "Optimize the input as text that will be spoken by a text-to-speech model. "
            "Keep it natural to read aloud, improve punctuation and pacing, and preserve any speech tags, "
            "pause markers, names, numbers, and language choices. Do not describe camera, lighting, colors, "
            "composition, or visual details unless the user explicitly wrote them as spoken content."
        )
    if normalized == "music":
        return (
            "Optimize the input as a music generation style prompt. Focus on genre, mood, tempo, rhythm, "
            "instrumentation, vocal character, arrangement, production texture, and performance energy. "
            "Do not turn it into an image prompt, concert photo, camera shot, lighting plan, or color palette. "
            "Do not write lyrics unless the user explicitly asked for lyrics in this field."
        )
    if normalized == "video":
        return (
            "Optimize the input as a video generation prompt. Include scene, subject, action, camera movement, "
            "timing, atmosphere, motion, and production details. Keep it suitable for moving footage rather "
            "than a still image."
        )
    
    if is_comfy:
        return (
            "Optimize the input as an image generation prompt for Stable Diffusion / ComfyUI. "
            "Use descriptive keywords, artistic styles, and technical terms (e.g., 'masterpiece', 'hyperrealistic', 'bokeh'). "
            "The output should be a single coherent descriptive paragraph or a comma-separated list of tags "
            "that captures the essence of the user's request with high visual fidelity."
        )

    return (
        "Optimize the input as an image generation prompt. Include subject, composition, style, lighting, "
        "color palette, mood, and useful visual production details when they fit the request."
    )


async def optimize_prompt(
    prompt: str,
    model: str = "MiniMax-M2.7",
    target: str = "image",
    generation_model: Optional[str] = None,
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
        f"{_optimizer_instruction_for(target, generation_model)}\n"
        "Write one concise, vivid prompt for that exact target type."
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
    aspect_ratio: Optional[str] = "16:9",
    width: Optional[int] = None,
    height: Optional[int] = None,
    n: int = 1,
    response_format: str = "url",
    prompt_optimizer: bool = False,
    seed: Optional[int] = None,
    aigc_watermark: bool = False,
    style: Optional[dict] = None,
    subject_reference: Optional[list[dict]] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> dict:
    """调用 MiniMax 文生图 API"""
    key = api_key or DEFAULT_API_KEY
    url = base_url or DEFAULT_BASE_URL
    if not key:
        raise ValueError("MINIMAX_API_KEY not configured")

    payload = {
        "model": model,
        "prompt": prompt,
        "n": n,
        "response_format": response_format,
        "prompt_optimizer": prompt_optimizer,
    }
    if width is not None and height is not None:
        payload["width"] = width
        payload["height"] = height
    elif aspect_ratio:
        payload["aspect_ratio"] = aspect_ratio
    if seed is not None:
        payload["seed"] = seed
    if aigc_watermark:
        payload["aigc_watermark"] = True
    if style:
        payload["style"] = style
    if subject_reference:
        payload["subject_reference"] = subject_reference

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{url}/v1/image_generation",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


async def generate_voice(
    text: str,
    voice_id: str = "male-qn-qingse",
    model: str = "speech-2.8-hd",
    speed: float = 1,
    vol: float = 1,
    pitch: int = 0,
    emotion: str = "auto",
    audio_format: str = "mp3",
    sample_rate: int = 32000,
    bitrate: int = 128000,
    channel: int = 1,
    subtitle_enable: bool = False,
    stream: bool = False,
    latex_read: bool = False,
    language_boost: Optional[str] = None,
    pronunciation_tones: Optional[list[str]] = None,
    voice_effect_pitch: Optional[int] = None,
    voice_effect_intensity: Optional[int] = None,
    voice_effect_timbre: Optional[int] = None,
    voice_effect: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> dict:
    """调用 MiniMax TTS (语音合成) API"""
    key = api_key or DEFAULT_API_KEY
    url = base_url or DEFAULT_BASE_URL
    if not key:
        raise ValueError("MINIMAX_API_KEY not configured")
    if stream:
        raise ValueError("Streaming T2A is not supported by this HTTP playback flow yet")

    voice_setting = {
        "voice_id": voice_id,
        "speed": speed,
        "vol": vol,
        "pitch": pitch,
    }
    if emotion and emotion != "auto":
        voice_setting["emotion"] = emotion
    if latex_read:
        voice_setting["latex_read"] = True

    payload = {
        "model": model,
        "text": text,
        "stream": False,
        "voice_setting": voice_setting,
        "audio_setting": {
            "sample_rate": sample_rate,
            "bitrate": bitrate,
            "format": audio_format,
            "channel": channel,
        },
        "pronunciation_dict": {
            "tone": pronunciation_tones or [],
        },
        "subtitle_enable": subtitle_enable,
        "output_format": "hex",
    }
    if language_boost:
        payload["language_boost"] = language_boost

    voice_modify = {}
    if voice_effect_pitch not in (None, 0):
        voice_modify["pitch"] = voice_effect_pitch
    if voice_effect_intensity not in (None, 0):
        voice_modify["intensity"] = voice_effect_intensity
    if voice_effect_timbre not in (None, 0):
        voice_modify["timbre"] = voice_effect_timbre
    if voice_effect:
        voice_modify["sound_effects"] = voice_effect
    if voice_modify:
        payload["voice_modify"] = voice_modify

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{url}/v1/t2a_v2",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


async def generate_video(
    prompt: str,
    model: str = "MiniMax-Hailuo-2.3",
    duration: int = 6,
    resolution: str = "768P",
    first_frame_image: Optional[str] = None,
    last_frame_image: Optional[str] = None,
    subject_reference: Optional[list[dict]] = None,
    prompt_optimizer: bool = True,
    fast_pretreatment: bool = False,
    callback_url: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> dict:
    """调用 MiniMax 视频生成 API — 异步，返回 task_id。"""
    key = api_key or DEFAULT_API_KEY
    url = base_url or DEFAULT_BASE_URL
    if not key:
        raise ValueError("MINIMAX_API_KEY not configured")

    payload = {
        "model": model,
        "prompt": prompt,
        "duration": duration,
        "resolution": resolution,
        "prompt_optimizer": prompt_optimizer,
    }
    if fast_pretreatment:
        payload["fast_pretreatment"] = True
    if first_frame_image:
        payload["first_frame_image"] = first_frame_image
    if last_frame_image:
        payload["last_frame_image"] = last_frame_image
    if subject_reference:
        payload["subject_reference"] = subject_reference
    if callback_url:
        payload["callback_url"] = callback_url

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{url}/v1/video_generation",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
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
            f"{url}/v1/query/video_generation",
            headers={"Authorization": f"Bearer {key}"},
            params={"task_id": task_id},
        )
        resp.raise_for_status()
        return resp.json()


async def retrieve_video_file(file_id: str, api_key: Optional[str] = None, base_url: Optional[str] = None) -> dict:
    """根据 file_id 获取视频文件下载信息。"""
    key = api_key or DEFAULT_API_KEY
    url = base_url or DEFAULT_BASE_URL
    if not key:
        raise ValueError("MINIMAX_API_KEY not configured")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{url}/v1/files/retrieve",
            headers={"Authorization": f"Bearer {key}"},
            params={"file_id": file_id},
        )
        resp.raise_for_status()
        return resp.json()


async def generate_music(
    prompt: str,
    model: str = "music-2.6",
    lyrics: str = "",
    is_instrumental: bool = False,
    lyrics_optimizer: bool = False,
    audio_format: str = "mp3",
    output_format: str = "hex",
    sample_rate: int = 44100,
    bitrate: int = 256000,
    seed: Optional[int] = None,
    aigc_watermark: bool = False,
    reference_audio_url: Optional[str] = None,
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
        "output_format": output_format,
        "audio_setting": {
            "sample_rate": sample_rate,
            "bitrate": bitrate,
            "format": audio_format,
        },
    }
    if prompt:
        payload["prompt"] = prompt
    if lyrics:
        payload["lyrics"] = lyrics
    if is_instrumental:
        payload["is_instrumental"] = True
    if lyrics_optimizer:
        payload["lyrics_optimizer"] = True
    if seed is not None:
        payload["seed"] = seed
    if aigc_watermark:
        payload["aigc_watermark"] = True
    if model == "music-cover":
        payload["stream"] = False
        if reference_audio_url:
            payload["audio_url"] = reference_audio_url

    async with httpx.AsyncClient(timeout=300.0) as client:
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
