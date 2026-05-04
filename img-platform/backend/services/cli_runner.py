"""MiniMax CLI (mmx) 调用封装 — 用于 Token Plan 用户

生成的文件保存在 `minimax-output/` 目录，调用方负责扫描取回 URL。
"""
import asyncio
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

MINIMAX_OUTPUT = Path.home() / "minimax-output"


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


async def generate_image(
    prompt: str,
    model: str = "image-01",
    aspect_ratio: str = "16:9",
    n: int = 1,
) -> dict:
    """mmx image "prompt" [--model image-01] [--aspect-ratio 16:9]"""
    cmd = ["mmx", "image", prompt]
    if model:
        cmd.extend(["--model", model])
    if aspect_ratio:
        cmd.extend(["--aspect-ratio", aspect_ratio])
    if n and n > 1:
        cmd.extend(["--n", str(n)])

    out = await asyncio.get_event_loop().run_in_executor(None, _run_sync, cmd, 120)
    # mmx 输出格式：[Model: image-01]\n{ "saved": ["file.jpg"] }
    # 找 JSON 块，提取 saved 文件列表，转为 /minimax-output/ URL
    image_urls = []
    import re
    json_match = re.search(r'\{[\s\S]*"saved"[\s\S]*\}', out)
    if json_match:
        try:
            data = json.loads(json_match.group())
            saved = data.get("saved", [])
            for fname in saved:
                image_urls.append(f"/minimax-output/{fname}")
        except Exception:
            pass

    if not image_urls:
        raise RuntimeError(f"mmx image returned no output: {out[:200]}")

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
    speed: int = 1,
    output_format: str = "mp3",
) -> dict:
    """mmx speech synthesize --text "..." --out filename.mp3 [--voice ...]"""
    filename = f"{uuid.uuid4().hex}.{output_format}"
    cmd = ["mmx", "speech", "synthesize", "--text", text, "--out", filename]
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
) -> dict:
    """mmx music generate --prompt "..." [--out filename.mp3]"""
    filename = f"{uuid.uuid4().hex}.mp3"
    cmd = ["mmx", "music", "generate", "--prompt", prompt, "--out", filename]
    if model:
        cmd.extend(["--model", model])

    out = await asyncio.get_event_loop().run_in_executor(None, _run_sync, cmd, 300)

    music_path = MINIMAX_OUTPUT / filename
    if not music_path.exists():
        raise RuntimeError(f"mmx music: output file not found: {filename}")

    return {
        "trace_id": str(uuid.uuid4()),
        "base_resp": {"status_code": 0, "status_msg": "success"},
        "data": {"audio": music_path},
    }
