import asyncio
import os
import random
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote
from urllib.parse import unquote, urlparse

import httpx


DEFAULT_COMFYUI_BASE_URL = os.getenv("COMFYUI_BASE_URL", "http://192.168.1.195:8188")
COMFYUI_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "uploads" / "comfyui"
BACKEND_DIR = Path(__file__).resolve().parents[1]


def _clean_base_url(base_url: Optional[str] = None) -> str:
    return (base_url or DEFAULT_COMFYUI_BASE_URL).rstrip("/")


def _size_for(aspect_ratio: Optional[str], width: Optional[int], height: Optional[int]) -> tuple[int, int]:
    if width and height:
        return width, height

    sizes = {
        "1:1": (1024, 1024),
        "16:9": (1216, 704),
        "4:3": (1152, 864),
        "3:2": (1216, 832),
        "2:3": (832, 1216),
        "3:4": (864, 1152),
        "9:16": (704, 1216),
        "21:9": (1344, 576),
    }
    return sizes.get(aspect_ratio or "16:9", sizes["16:9"])


async def get_status(base_url: Optional[str] = None) -> dict:
    """Return ComfyUI health and GPU stats."""
    url = _clean_base_url(base_url)
    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.get(f"{url}/system_stats")
        resp.raise_for_status()
        return resp.json()


async def _object_options(client: httpx.AsyncClient, base_url: str) -> dict:
    resp = await client.get(f"{base_url}/object_info")
    resp.raise_for_status()
    return resp.json()


async def list_checkpoints(base_url: Optional[str] = None) -> list[str]:
    """Return image checkpoint names that work with the default text-to-image workflow."""
    url = _clean_base_url(base_url)
    async with httpx.AsyncClient(timeout=8.0) as client:
        objects = await _object_options(client, url)
    try:
        values = objects["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
        image_candidates = [
            value for value in values
            if not any(term in value.lower() for term in ("audio", "vocoder", "vae", "ltx"))
        ]
        return image_candidates or list(values)
    except (KeyError, IndexError, TypeError):
        return []


def _first_option(objects: dict, node: str, field: str, fallback: str) -> str:
    try:
        values = objects[node]["input"]["required"][field][0]
        if values:
            return values[0]
    except (KeyError, IndexError, TypeError):
        pass
    return fallback


def _checkpoint_option(objects: dict) -> str:
    try:
        values = objects["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
    except (KeyError, IndexError, TypeError):
        return "sd_xl_base_1.0.safetensors"

    preferred = ("dreamshaper", "sdxl", "stable-diffusion", "realvis", "juggernaut", "pony", "flux")
    excluded = ("audio", "vocoder", "vae", "ltx")
    image_candidates = [value for value in values if not any(term in value.lower() for term in excluded)]
    for value in image_candidates:
        normalized = value.lower()
        if any(term in normalized for term in preferred):
            return value
    return image_candidates[0] if image_candidates else (values[0] if values else "sd_xl_base_1.0.safetensors")


def _default_workflow(
    objects: dict,
    prompt: str,
    aspect_ratio: Optional[str],
    width: Optional[int],
    height: Optional[int],
    n: int,
    seed: Optional[int],
    checkpoint: Optional[str] = None,
) -> dict:
    image_width, image_height = _size_for(aspect_ratio, width, height)
    ckpt_name = checkpoint or _checkpoint_option(objects)
    sampler_name = _first_option(objects, "KSampler", "sampler_name", "euler")
    scheduler = _first_option(objects, "KSampler", "scheduler", "normal")
    resolved_seed = seed if seed is not None else random.randint(0, 2**32 - 1)

    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": resolved_seed,
                "steps": 28,
                "cfg": 7,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": 1,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": ckpt_name,
            },
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": image_width,
                "height": image_height,
                "batch_size": n,
            },
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": prompt,
                "clip": ["4", 1],
            },
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "low quality, blurry, watermark, text, logo",
                "clip": ["4", 1],
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2],
            },
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "aitoolstudio",
                "images": ["8", 0],
            },
        },
    }


async def _wait_for_history(client: httpx.AsyncClient, base_url: str, prompt_id: str) -> dict:
    deadline = time.monotonic() + int(os.getenv("COMFYUI_GENERATION_TIMEOUT", "300"))
    while time.monotonic() < deadline:
        resp = await client.get(f"{base_url}/history/{prompt_id}")
        resp.raise_for_status()
        history = resp.json()
        if prompt_id in history:
            return history[prompt_id]
        await asyncio.sleep(1.5)
    raise TimeoutError("ComfyUI generation timed out")


async def _download_outputs(client: httpx.AsyncClient, base_url: str, prompt_id: str, history: dict) -> list[str]:
    urls: list[str] = []
    COMFYUI_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for node_output in history.get("outputs", {}).values():
        for image in node_output.get("images", []):
            filename = image.get("filename")
            if not filename:
                continue
            subfolder = image.get("subfolder") or ""
            image_type = image.get("type") or "output"
            view_url = (
                f"{base_url}/view?filename={quote(filename, safe='')}"
                f"&subfolder={quote(subfolder, safe='')}&type={quote(image_type, safe='')}"
            )
            resp = await client.get(view_url)
            resp.raise_for_status()

            local_name = f"{prompt_id}_{Path(filename).name}"
            local_path = COMFYUI_OUTPUT_DIR / local_name
            local_path.write_bytes(resp.content)
            urls.append(f"/uploads/comfyui/{local_name}")

    return urls


def _png_dimensions(data: bytes) -> Optional[tuple[int, int]]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _jpeg_dimensions(data: bytes) -> Optional[tuple[int, int]]:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in (0xD8, 0xD9):
            continue
        length = int.from_bytes(data[index:index + 2], "big")
        if length < 2 or index + length > len(data):
            return None
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            height = int.from_bytes(data[index + 3:index + 5], "big")
            width = int.from_bytes(data[index + 5:index + 7], "big")
            return width, height
        index += length
    return None


def _image_dimensions(data: bytes) -> tuple[int, int]:
    size = _png_dimensions(data) or _jpeg_dimensions(data)
    if not size:
        raise ValueError("Only PNG and JPEG images can be upscaled")
    return size


async def _source_image_bytes(source_url: str) -> tuple[bytes, str]:
    parsed = urlparse(source_url)
    path = unquote(parsed.path if parsed.scheme else source_url.split("?", 1)[0])

    if path.startswith("/uploads/"):
        local_path = BACKEND_DIR / path.lstrip("/")
        return local_path.read_bytes(), local_path.name
    if path.startswith("/minimax-output/"):
        local_path = Path.home() / "minimax-output" / Path(path).name
        return local_path.read_bytes(), local_path.name
    if parsed.scheme in {"http", "https"}:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(source_url)
            resp.raise_for_status()
            return resp.content, Path(path).name or "source.png"

    raise ValueError("Unsupported source image URL")


async def _upload_image(client: httpx.AsyncClient, base_url: str, image_bytes: bytes, filename: str) -> str:
    safe_name = f"aitoolstudio_upscale_{int(time.time() * 1000)}_{Path(filename).name}"
    resp = await client.post(
        f"{base_url}/upload/image",
        data={"overwrite": "true"},
        files={"image": (safe_name, image_bytes, "application/octet-stream")},
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("name") or safe_name


async def upscale_image(
    source_url: str,
    scale: float = 2,
    method: str = "lanczos",
    base_url: Optional[str] = None,
) -> dict:
    """Upscale an existing image through ComfyUI ImageScale."""
    url = _clean_base_url(base_url)
    image_bytes, filename = await _source_image_bytes(source_url)
    source_width, source_height = _image_dimensions(image_bytes)
    target_width = min(16384, max(1, int(round(source_width * scale))))
    target_height = min(16384, max(1, int(round(source_height * scale))))

    async with httpx.AsyncClient(timeout=30.0) as client:
        uploaded_name = await _upload_image(client, url, image_bytes, filename)
        workflow = {
            "1": {
                "class_type": "LoadImage",
                "inputs": {
                    "image": uploaded_name,
                },
            },
            "2": {
                "class_type": "ImageScale",
                "inputs": {
                    "image": ["1", 0],
                    "upscale_method": method,
                    "width": target_width,
                    "height": target_height,
                    "crop": "disabled",
                },
            },
            "3": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": "aitoolstudio_upscale",
                    "images": ["2", 0],
                },
            },
        }
        queue_resp = await client.post(f"{url}/prompt", json={"prompt": workflow})
        queue_resp.raise_for_status()
        queued = queue_resp.json()
        if "error" in queued:
            raise ValueError(str(queued.get("error")))
        prompt_id = queued.get("prompt_id")
        if not prompt_id:
            raise ValueError("ComfyUI did not return prompt_id")

    async with httpx.AsyncClient(timeout=60.0) as client:
        history = await _wait_for_history(client, url, prompt_id)
        image_urls = await _download_outputs(client, url, prompt_id, history)

    return {
        "id": prompt_id,
        "data": {"image_urls": image_urls},
        "metadata": {
            "engine": "comfyui-upscale",
            "source_url": source_url,
            "scale": scale,
            "method": method,
            "width": target_width,
            "height": target_height,
        },
        "base_resp": {"status_code": 0, "status_msg": "success"},
    }


async def generate_image(
    prompt: str,
    aspect_ratio: Optional[str] = "16:9",
    width: Optional[int] = None,
    height: Optional[int] = None,
    n: int = 1,
    seed: Optional[int] = None,
    checkpoint: Optional[str] = None,
    workflow: Optional[dict] = None,
    base_url: Optional[str] = None,
) -> dict:
    """Queue a ComfyUI workflow and return locally proxied output image URLs."""
    url = _clean_base_url(base_url)
    async with httpx.AsyncClient(timeout=30.0) as client:
        objects = await _object_options(client, url) if workflow is None else {}
        prompt_workflow = workflow or _default_workflow(
            objects=objects,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            width=width,
            height=height,
            n=n,
            seed=seed,
            checkpoint=checkpoint,
        )
        queue_resp = await client.post(f"{url}/prompt", json={"prompt": prompt_workflow})
        queue_resp.raise_for_status()
        queued = queue_resp.json()
        if "error" in queued:
            raise ValueError(str(queued.get("error")))

        prompt_id = queued.get("prompt_id")
        if not prompt_id:
            raise ValueError("ComfyUI did not return prompt_id")

    async with httpx.AsyncClient(timeout=60.0) as client:
        history = await _wait_for_history(client, url, prompt_id)
        image_urls = await _download_outputs(client, url, prompt_id, history)

    return {
        "id": prompt_id,
        "data": {"image_urls": image_urls},
        "metadata": {"engine": "comfyui", "base_url": url},
        "base_resp": {"status_code": 0, "status_msg": "success"},
    }
