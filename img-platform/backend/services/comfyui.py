import asyncio
import base64
import os
import random
import struct
import time
import zlib
from pathlib import Path
from typing import Optional
from urllib.parse import quote
from urllib.parse import unquote, urlparse

import httpx

from services.storage import local_path_from_public_url, upload_category_dir, upload_url


DEFAULT_COMFYUI_BASE_URL = os.getenv("COMFYUI_BASE_URL", "http://192.168.1.195:8188")


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


def _comfyui_wait_timeout() -> float:
    return float(int(os.getenv("COMFYUI_GENERATION_TIMEOUT", "300")) + 45)


async def _download_outputs(client: httpx.AsyncClient, base_url: str, prompt_id: str, history: dict) -> list[str]:
    urls: list[str] = []
    output_dir = upload_category_dir("comfyui")

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
            local_path = output_dir / local_name
            local_path.write_bytes(resp.content)
            urls.append(upload_url("comfyui", local_name))

    return urls


def _output_extension(filename: str, fallback: str = "mp4") -> str:
    suffix = Path(filename or "").suffix.lower().lstrip(".")
    return suffix or fallback


async def _download_media_outputs(
    client: httpx.AsyncClient,
    base_url: str,
    prompt_id: str,
    history: dict,
    output_keys: set[str],
    category: str,
    fallback_ext: str,
    allowed_exts: set[str],
) -> list[str]:
    urls: list[str] = []
    output_dir = upload_category_dir(category)

    for node_output in history.get("outputs", {}).values():
        if not isinstance(node_output, dict):
            continue
        for key in output_keys:
            for item in node_output.get(key, []) or []:
                filename = item.get("filename")
                if not filename:
                    continue
                ext = _output_extension(filename, fallback_ext)
                if ext.lower() not in allowed_exts:
                    continue
                subfolder = item.get("subfolder") or ""
                media_type = item.get("type") or "output"
                view_url = (
                    f"{base_url}/view?filename={quote(filename, safe='')}"
                    f"&subfolder={quote(subfolder, safe='')}&type={quote(media_type, safe='')}"
                )
                resp = await client.get(view_url)
                resp.raise_for_status()

                local_name = f"{prompt_id}_{Path(filename).name}"
                local_path = output_dir / local_name
                local_path.write_bytes(resp.content)
                urls.append(upload_url(category, local_name))

    return urls


async def _download_video_outputs(client: httpx.AsyncClient, base_url: str, prompt_id: str, history: dict) -> list[str]:
    return await _download_media_outputs(
        client=client,
        base_url=base_url,
        prompt_id=prompt_id,
        history=history,
        output_keys={"videos", "gifs"},
        category="videos",
        fallback_ext="mp4",
        allowed_exts={"mp4", "mov", "webm", "m4v", "gif"},
    )


def _workflow_uses_batch(workflow: dict) -> bool:
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        if node.get("class_type") == "EmptyLatentImage" and int(inputs.get("batch_size") or 1) > 1:
            return True
    return False


def _workflow_with_seed(workflow: dict, seed: int) -> dict:
    import copy

    patched = copy.deepcopy(workflow)
    for node in patched.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        if node.get("class_type") in {"KSampler", "ERNIEImage"} and "seed" in inputs:
            inputs["seed"] = seed
    return patched


async def _queue_workflow(client: httpx.AsyncClient, base_url: str, workflow: dict) -> str:
    queue_resp = await client.post(f"{base_url}/prompt", json={"prompt": workflow})
    try:
        queue_resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = queue_resp.text[:2000] if queue_resp.text else str(exc)
        raise ValueError(f"ComfyUI rejected workflow: {detail}") from exc
    queued = queue_resp.json()
    if "error" in queued:
        raise ValueError(str(queued.get("error")))
    prompt_id = queued.get("prompt_id")
    if not prompt_id:
        raise ValueError("ComfyUI did not return prompt_id")
    return prompt_id


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


def _webp_dimensions(data: bytes) -> Optional[tuple[int, int]]:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    index = 12
    while index + 8 <= len(data):
        chunk_type = data[index:index + 4]
        chunk_size = int.from_bytes(data[index + 4:index + 8], "little")
        chunk_start = index + 8
        chunk_end = chunk_start + chunk_size
        if chunk_end > len(data):
            return None
        chunk = data[chunk_start:chunk_end]
        if chunk_type == b"VP8X" and len(chunk) >= 10:
            width = 1 + int.from_bytes(chunk[4:7], "little")
            height = 1 + int.from_bytes(chunk[7:10], "little")
            return width, height
        if chunk_type == b"VP8L" and len(chunk) >= 5 and chunk[0] == 0x2F:
            b1, b2, b3, b4 = chunk[1], chunk[2], chunk[3], chunk[4]
            width = 1 + (b1 | ((b2 & 0x3F) << 8))
            height = 1 + ((b2 >> 6) | (b3 << 2) | ((b4 & 0x0F) << 10))
            return width, height
        if chunk_type == b"VP8 " and len(chunk) >= 10 and chunk[3:6] == b"\x9d\x01\x2a":
            width = int.from_bytes(chunk[6:8], "little") & 0x3FFF
            height = int.from_bytes(chunk[8:10], "little") & 0x3FFF
            return width, height
        index = chunk_end + (chunk_size % 2)
    return None


def _image_dimensions(data: bytes) -> tuple[int, int]:
    size = _png_dimensions(data) or _jpeg_dimensions(data) or _webp_dimensions(data)
    if not size:
        raise ValueError("Only PNG, JPEG, and WebP images are supported")
    return size


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)
    )


def _click_mask_png(width: int, height: int, x: float, y: float) -> bytes:
    cx = min(width - 1, max(0, int(round(x * (width - 1)))))
    cy = min(height - 1, max(0, int(round(y * (height - 1)))))
    radius = max(8, min(48, int(round(min(width, height) * 0.025))))
    radius_sq = radius * radius
    rows = bytearray()
    for row in range(height):
        rows.append(0)
        dy = row - cy
        for col in range(width):
            dx = col - cx
            rows.append(255 if dx * dx + dy * dy <= radius_sq else 0)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", zlib.compress(bytes(rows))) + _png_chunk(b"IEND", b"")


async def _source_image_bytes(source_url: str) -> tuple[bytes, str]:
    if source_url.startswith("data:image/"):
        header, _, payload = source_url.partition(",")
        if not payload or ";base64" not in header:
            raise ValueError("Unsupported data URL image format")
        mime = header.split(";", 1)[0].removeprefix("data:")
        extension = {
            "image/jpeg": "jpg",
            "image/jpg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
        }.get(mime)
        if not extension:
            raise ValueError("Unsupported reference image type")
        return base64.b64decode(payload), f"reference.{extension}"

    parsed = urlparse(source_url)
    path = unquote(parsed.path if parsed.scheme else source_url.split("?", 1)[0])

    if path.startswith("/uploads/"):
        local_path = local_path_from_public_url(path)
        return local_path.read_bytes(), local_path.name
    if path.startswith("/minimax-output/"):
        local_path = local_path_from_public_url(path)
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


def _contains_placeholder(value: object, placeholders: set[str]) -> bool:
    if isinstance(value, str):
        return any(placeholder in value for placeholder in placeholders)
    if isinstance(value, list):
        return any(_contains_placeholder(item, placeholders) for item in value)
    if isinstance(value, dict):
        return any(_contains_placeholder(item, placeholders) for item in value.values())
    return False


def _replace_placeholders(value: object, replacements: dict[str, str]) -> object:
    if isinstance(value, str):
        next_value = value
        for placeholder, replacement in replacements.items():
            next_value = next_value.replace(placeholder, replacement)
        return next_value
    if isinstance(value, list):
        return [_replace_placeholders(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _replace_placeholders(item, replacements) for key, item in value.items()}
    return value


async def _patch_workflow_image_placeholders(
    client: httpx.AsyncClient,
    base_url: str,
    workflow: dict,
    source_image: Optional[str],
    mask_image: Optional[str],
    mask_point: Optional[tuple[float, float]],
) -> None:
    source_placeholders = {"{{image}}", "{{source_image}}", "{{input_image}}"}
    mask_placeholders = {"{{sam_mask}}", "{{mask}}", "{{mask_image}}"}
    needs_source = _contains_placeholder(workflow, source_placeholders)
    needs_mask = _contains_placeholder(workflow, mask_placeholders)

    replacements: dict[str, str] = {}
    source_bytes: Optional[bytes] = None
    source_name: Optional[str] = None
    if needs_source:
        if not source_image:
            raise ValueError("ComfyUI workflow requires a source image")
        source_bytes, source_name = await _source_image_bytes(source_image)
        uploaded_source = await _upload_image(client, base_url, source_bytes, source_name)
        replacements.update({placeholder: uploaded_source for placeholder in source_placeholders})

    if needs_mask:
        if mask_image:
            mask_bytes, mask_name = await _source_image_bytes(mask_image)
        elif source_image and mask_point:
            if source_bytes is None:
                source_bytes, source_name = await _source_image_bytes(source_image)
            width, height = _image_dimensions(source_bytes)
            mask_bytes = _click_mask_png(width, height, mask_point[0], mask_point[1])
            mask_name = f"{Path(source_name or 'source').stem}_sam_mask.png"
        else:
            raise ValueError("ComfyUI workflow requires a mask image")
        uploaded_mask = await _upload_image(client, base_url, mask_bytes, mask_name)
        replacements.update({placeholder: uploaded_mask for placeholder in mask_placeholders})

    if replacements:
        patched = _replace_placeholders(workflow, replacements)
        workflow.clear()
        workflow.update(patched)


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
        prompt_id = await _queue_workflow(client, url, workflow)

    async with httpx.AsyncClient(timeout=_comfyui_wait_timeout()) as client:
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


async def generate_sam_mask(
    source_image: str,
    x: float,
    y: float,
    dilation: int = 8,
    bbox_expansion: int = 20,
    base_url: Optional[str] = None,
) -> dict:
    """Generate a visible SAM mask from a source image and normalized click point."""
    url = _clean_base_url(base_url)
    source_bytes, source_name = await _source_image_bytes(source_image)
    width, height = _image_dimensions(source_bytes)
    click_mask = _click_mask_png(width, height, x, y)

    async with httpx.AsyncClient(timeout=30.0) as client:
        uploaded_source = await _upload_image(client, url, source_bytes, source_name)
        uploaded_click = await _upload_image(
            client,
            url,
            click_mask,
            f"{Path(source_name).stem or 'source'}_click_mask.png",
        )
        workflow = {
            "1": {
                "class_type": "LoadImage",
                "inputs": {"image": uploaded_source},
            },
            "2": {
                "class_type": "SAMLoader",
                "inputs": {
                    "model_name": "sam_vit_h_4b8939.pth",
                    "device_mode": "Prefer GPU",
                },
            },
            "3": {
                "class_type": "LoadImage",
                "inputs": {"image": uploaded_click},
            },
            "4": {
                "class_type": "ImageToMask",
                "inputs": {
                    "image": ["3", 0],
                    "channel": "red",
                },
            },
            "5": {
                "class_type": "MaskToSEGS",
                "inputs": {
                    "mask": ["4", 0],
                    "combined": False,
                    "crop_factor": 3,
                    "bbox_fill": True,
                    "drop_size": 10,
                    "contour_fill": True,
                },
            },
            "6": {
                "class_type": "SAMDetectorCombined",
                "inputs": {
                    "sam_model": ["2", 0],
                    "segs": ["5", 0],
                    "image": ["1", 0],
                    "detection_hint": "center-1",
                    "dilation": dilation,
                    "threshold": 0.5,
                    "bbox_expansion": bbox_expansion,
                    "mask_hint_threshold": 0.5,
                    "mask_hint_use_negative": "Small",
                },
            },
            "7": {
                "class_type": "MaskToImage",
                "inputs": {"mask": ["6", 0]},
            },
            "8": {
                "class_type": "SaveImage",
                "inputs": {
                    "images": ["7", 0],
                    "filename_prefix": "aitoolstudio_sam_mask",
                },
            },
        }
        prompt_id = await _queue_workflow(client, url, workflow)

    async with httpx.AsyncClient(timeout=_comfyui_wait_timeout()) as client:
        history = await _wait_for_history(client, url, prompt_id)
        image_urls = await _download_outputs(client, url, prompt_id, history)

    if not image_urls:
        raise ValueError("SAM mask workflow finished but did not produce image output")

    return {
        "id": prompt_id,
        "data": {"mask_url": image_urls[0], "image_urls": image_urls},
        "metadata": {
            "engine": "comfyui-sam-mask",
            "source_url": source_image,
            "x": x,
            "y": y,
            "dilation": dilation,
            "bbox_expansion": bbox_expansion,
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
    source_image: Optional[str] = None,
    mask_image: Optional[str] = None,
    mask_point: Optional[tuple[float, float]] = None,
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
        if workflow is not None:
            await _patch_workflow_image_placeholders(
                client=client,
                base_url=url,
                workflow=prompt_workflow,
                source_image=source_image,
                mask_image=mask_image,
                mask_point=mask_point,
            )
        if workflow is not None and n > 1 and not _workflow_uses_batch(prompt_workflow):
            base_seed = seed if seed is not None else random.randint(0, 2**32 - 1)
            prompt_ids = [
                await _queue_workflow(client, url, _workflow_with_seed(prompt_workflow, (base_seed + index) % 2**32))
                for index in range(n)
            ]
        else:
            prompt_ids = [await _queue_workflow(client, url, prompt_workflow)]

    async with httpx.AsyncClient(timeout=_comfyui_wait_timeout()) as client:
        image_urls = []
        for prompt_id in prompt_ids:
            history = await _wait_for_history(client, url, prompt_id)
            image_urls.extend(await _download_outputs(client, url, prompt_id, history))
    if not image_urls:
        raise ValueError("ComfyUI workflow finished but did not produce image output")

    return {
        "id": ",".join(prompt_ids),
        "data": {"image_urls": image_urls},
        "metadata": {"engine": "comfyui", "base_url": url},
        "base_resp": {"status_code": 0, "status_msg": "success"},
    }


async def generate_video(
    prompt: str,
    workflow: dict,
    base_url: Optional[str] = None,
    source_image: Optional[str] = None,
) -> dict:
    """Queue a ComfyUI video workflow and return the first locally proxied video URL."""
    if not workflow:
        raise ValueError("ComfyUI video generation requires a saved workflow")

    url = _clean_base_url(base_url)

    # Patch source image placeholders in workflow | 替换工作流中的图片占位符
    if source_image:
        source_placeholders = {"{{image}}", "{{source_image}}", "{{input_image}}"}
        needs_source = _contains_placeholder(workflow, source_placeholders)
        if needs_source:
            source_bytes, source_name = await _source_image_bytes(source_image)
            async with httpx.AsyncClient(timeout=30.0) as upload_client:
                uploaded_source = await _upload_image(upload_client, url, source_bytes, source_name)
            replacements = {ph: uploaded_source for ph in source_placeholders}
            patched = _replace_placeholders(workflow, replacements)
            workflow.clear()
            workflow.update(patched)

    async with httpx.AsyncClient(timeout=30.0) as client:
        prompt_id = await _queue_workflow(client, url, workflow)

    async with httpx.AsyncClient(timeout=_comfyui_wait_timeout()) as client:
        history = await _wait_for_history(client, url, prompt_id)
        video_urls = await _download_video_outputs(client, url, prompt_id, history)

    if not video_urls:
        raise ValueError("ComfyUI workflow finished but did not produce a video output")

    return {
        "id": prompt_id,
        "data": {"video_url": video_urls[0], "video_urls": video_urls},
        "metadata": {"engine": "comfyui-video", "base_url": url, "prompt": prompt},
        "base_resp": {"status_code": 0, "status_msg": "success"},
    }
