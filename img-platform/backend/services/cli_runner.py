"""MiniMax CLI (mmx) 调用封装 — 用于 Token Plan 用户

生成的文件保存在 `minimax-output/` 目录，调用方负责扫描取回 URL。
"""
import asyncio
import base64
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from services.storage import get_minimax_output_root

MINIMAX_OUTPUT = get_minimax_output_root()


def _ensure_output_dir() -> Path:
    MINIMAX_OUTPUT.mkdir(parents=True, exist_ok=True)
    return MINIMAX_OUTPUT


def _run_sync(cmd: list[str], timeout: int = 120) -> str:
    """同步执行 mmx 命令，等待结果"""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(_ensure_output_dir()),
    )
    if result.returncode != 0:
        raise RuntimeError(f"mmx CLI error: {result.stderr.strip()}")
    return result.stdout.strip()


def _data_url_to_file(data_url: str, prefix: str = "ref") -> str:
    header, _, encoded = data_url.partition(",")
    if not encoded or not header.startswith("data:image/"):
        raise ValueError("Invalid image data URL")
    image_type = header.split(";", 1)[0].split("/", 1)[1].lower()
    extension = "jpg" if image_type == "jpeg" else image_type
    if extension not in {"jpg", "png", "webp"}:
        raise ValueError("Unsupported reference image type")
    filename = f"{prefix}_{uuid.uuid4().hex[:8]}.{extension}"
    output_path = _ensure_output_dir() / filename
    output_path.write_bytes(base64.b64decode(encoded))
    return str(output_path)


def _optimizer_instruction_for(target: str, generation_model: Optional[str] = None) -> str:
    normalized = target.lower().strip()
    is_comfy = generation_model and "comfyui" in generation_model.lower()

    if normalized == "voice":
        return (
            "Optimize this as text for text-to-speech. Improve natural punctuation and pacing, preserve speech "
            "tags and pause markers, and do not add visual composition, camera, lighting, or color details."
        )
    if normalized == "music":
        return (
            "Optimize this as a music generation style prompt. Focus on genre, mood, tempo, rhythm, "
            "instrumentation, vocal character, arrangement, production texture, and performance energy. "
            "Do not turn it into an image prompt, concert photo, lighting plan, or color palette. "
            "Do not write lyrics unless the user explicitly asked for lyrics in this field."
        )
    if normalized == "video":
        return (
            "Optimize this as a video generation prompt with scene, subject, action, camera movement, timing, "
            "atmosphere, motion, and production details."
        )
    
    if is_comfy:
        return (
            "Optimize this as an image generation prompt for Stable Diffusion / ComfyUI. "
            "Use descriptive keywords, artistic styles, and technical terms (e.g., 'masterpiece', 'hyperrealistic', 'bokeh'). "
            "The output should be a single coherent descriptive paragraph or a comma-separated list of tags."
        )

    return (
        "Optimize this as an image generation prompt with subject, composition, style, lighting, color palette, "
        "mood, and useful visual production details."
    )


async def optimize_prompt(
    prompt: str,
    model: str = "MiniMax-M2.7",
    target: str = "image",
    generation_model: Optional[str] = None,
) -> dict:
    """mmx text chat --message "..."; returns an OpenAI-like text payload."""
    message = (
        "Rewrite this user request into one polished prompt for AI generation. "
        "Preserve the user's intent. Return only the optimized prompt, no markdown or explanation.\n\n"
        f"Target: {target}\n"
        f"User request: {prompt}\n\n"
        f"{_optimizer_instruction_for(target, generation_model)}"
    )
    system_prompt = (
        "You are a prompt engineer. Return only the optimized generation prompt, "
        "with no markdown, quotes, or explanation."
    )
    cmd = ["mmx", "text", "chat", "--system", system_prompt, "--message", message]
    if model:
        cmd.extend(["--model", model])

    out = await asyncio.get_event_loop().run_in_executor(None, _run_sync, cmd, 120)
    optimized = out.strip()
    try:
        data = json.loads(optimized)
        content = data.get("content", "")
        if isinstance(content, list):
            text_parts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            optimized = "\n".join(part for part in text_parts if part).strip()
        elif isinstance(content, str):
            optimized = content.strip()
    except json.JSONDecodeError:
        pass

    return {
        "choices": [
            {
                "message": {
                    "content": optimized,
                    "role": "assistant",
                }
            }
        ],
        "base_resp": {"status_code": 0, "status_msg": "success"},
    }


async def chat_text(
    prompt: str,
    system_prompt: str,
    model: str = "MiniMax-M2.7",
) -> dict:
    """通过 mmx CLI 调用通用文本聊天。"""
    cmd = ["mmx", "text", "chat", "--system", system_prompt, "--message", prompt]
    if model:
        cmd.extend(["--model", model])
    out = await asyncio.get_event_loop().run_in_executor(None, _run_sync, cmd, 120)
    answer = out.strip()
    try:
        data = json.loads(answer)
        content = data.get("content", "")
        if isinstance(content, list):
            answer = "\n".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ).strip()
        elif isinstance(content, str):
            answer = content.strip()
    except json.JSONDecodeError:
        pass

    return {
        "choices": [
            {
                "message": {
                    "content": answer,
                    "role": "assistant",
                }
            }
        ],
        "base_resp": {"status_code": 0, "status_msg": "success"},
    }


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
) -> dict:
    """mmx image generate --prompt "..." [--model image-01] [--aspect-ratio 16:9] [--n 2]"""
    import time, re, uuid
    # 每次生成用唯一ID做前缀，彻底避免任何覆盖
    unique_id = uuid.uuid4().hex[:8]
    safe_prompt = re.sub(r'[^a-zA-Z0-9]', '_', prompt[:12])
    out_prefix = f"img_{unique_id}_{safe_prompt}"
    cmd = ["mmx", "image", "generate", "--prompt", prompt]
    if model:
        cmd.extend(["--model", model])
    if width is not None and height is not None:
        cmd.extend(["--width", str(width), "--height", str(height)])
    elif aspect_ratio:
        cmd.extend(["--aspect-ratio", aspect_ratio])
    if n and n > 1:
        cmd.extend(["--n", str(n)])
    if response_format:
        cmd.extend(["--response-format", response_format])
    if prompt_optimizer:
        cmd.append("--prompt-optimizer")
    if seed is not None:
        cmd.extend(["--seed", str(seed)])
    if aigc_watermark:
        cmd.append("--aigc-watermark")
    if style:
        print("[cli_runner] image style is only supported by HTTP profiles; ignoring for CLI", flush=True)
    for index, ref in enumerate(subject_reference or []):
        image_file = str(ref.get("image_file") or "")
        if not image_file:
            continue
        if image_file.startswith("data:image/"):
            image_file = _data_url_to_file(image_file, f"ref_{index}")
        cmd.extend(["--subject-ref", f"type={ref.get('type', 'character')},image={image_file}"])
    cmd.extend(["--out-prefix", out_prefix])

    print(f"[cli_runner] running: {' '.join(cmd)}", flush=True)
    out = await asyncio.get_event_loop().run_in_executor(None, _run_sync, cmd, 120)
    print(f"[cli_runner] raw output: {out[:300]}", flush=True)
    # mmx 输出格式：[Model: image-01]\n{ "saved": ["file.jpg"] }
    # 找 JSON 块，提取 saved 文件列表，转为 /minimax-output/ URL
    image_urls = []
    import re
    json_match = re.search(r'\{[\s\S]*"saved"[\s\S]*\}', out)
    print(f"[cli_runner] json_match: {json_match.group() if json_match else None}", flush=True)
    if json_match:
        try:
            data = json.loads(json_match.group())
            saved = data.get("saved", [])
            print(f"[cli_runner] saved files: {saved}", flush=True)
            for fname in saved:
                # 构建完整 URL：/minimax-output/ + 文件名
                abs_path = str(MINIMAX_OUTPUT / fname)
                if os.path.exists(abs_path):
                    image_urls.append(f"/minimax-output/{fname}")
                else:
                    print(f"[cli_runner] file not found: {abs_path}", flush=True)
        except Exception:
            pass

    if not image_urls:
        raise RuntimeError(f"mmx image returned no output: {out[:200]}")

    print(f"[cli_runner] final image_urls: {image_urls}", flush=True)

    return {
        "id": str(uuid.uuid4()),
        "base_resp": {"status_code": 0, "status_msg": "success"},
        "data": {"image_urls": image_urls},
        "metadata": {},
    }


async def generate_video(
    prompt: str,
    model: str = "hailuo-video-01",
    duration: int = 6,
) -> dict:
    """mmx video generate --prompt "..." [--model ...]"""
    cmd = ["mmx", "video", "generate", "--prompt", prompt]
    if model:
        cmd.extend(["--model", model])
    if duration:
        cmd.extend(["--duration", str(duration)])

    out = await asyncio.get_event_loop().run_in_executor(None, _run_sync, cmd, 300)
    # 解析 task_id
    task_id = ""
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                data = json.loads(line)
                task_id = data.get("task_id") or data.get("id", "")
                break
            except Exception:
                pass
        if "task_id" in line.lower() or "id" in line.lower():
            parts = line.split()
            for i, p in enumerate(parts):
                if p in ("task_id", "id") and i + 1 < len(parts):
                    task_id = parts[i + 1].strip(",:;")
                    break

    return {
        "task_id": task_id or str(uuid.uuid4()),
        "base_resp": {"status_code": 0, "status_msg": "success"},
        "data": {"status": "pending"},
    }


async def generate_voice(
    text: str,
    voice_id: str = "male-qn-qingse",
    model: str = "speech-02-hd",
    speed: float = 1,
    output_format: str = "mp3",
) -> dict:
    """mmx speech synthesize --text "..." --out filename.mp3 [--voice ...]"""
    filename = f"{uuid.uuid4().hex}.{output_format}"
    cmd = ["mmx", "speech", "synthesize", "--text", text, "--out", filename]
    if model:
        cmd.extend(["--model", model])
    if voice_id:
        cmd.extend(["--voice", voice_id])
    if speed and speed != 1:
        cmd.extend(["--speed", str(speed)])

    await asyncio.get_event_loop().run_in_executor(None, _run_sync, cmd, 120)

    audio_path = MINIMAX_OUTPUT / filename
    if not audio_path.exists():
        raise RuntimeError(f"mmx speech: output file not found: {filename}")

    return {
        "trace_id": str(uuid.uuid4()),
        "base_resp": {"status_code": 0, "status_msg": "success"},
        "data": {"audio": audio_path},
    }


async def generate_music(
    prompt: str,
    model: str = "music-01",
    lyrics: str = "",
    is_instrumental: bool = False,
    lyrics_optimizer: bool = False,
) -> dict:
    """mmx music generate --prompt "..." [--out filename.mp3]"""
    filename = f"{uuid.uuid4().hex}.mp3"
    cmd = ["mmx", "music", "generate", "--prompt", prompt, "--out", filename]
    if model:
        cmd.extend(["--model", model])
    if lyrics:
        cmd.extend(["--lyrics", lyrics])
    elif is_instrumental:
        cmd.append("--instrumental")
    elif lyrics_optimizer:
        cmd.append("--lyrics-optimizer")
    else:
        cmd.append("--lyrics-optimizer")

    out = await asyncio.get_event_loop().run_in_executor(None, _run_sync, cmd, 300)

    music_path = MINIMAX_OUTPUT / filename
    if not music_path.exists():
        raise RuntimeError(f"mmx music: output file not found: {filename}")

    return {
        "trace_id": str(uuid.uuid4()),
        "base_resp": {"status_code": 0, "status_msg": "success"},
        "data": {"audio": music_path},
    }
