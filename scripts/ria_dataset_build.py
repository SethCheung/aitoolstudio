#!/usr/bin/env python3
"""ria_v1 数据集构建：18 张网格单图经 SeedVR2 超分 + 主脸原图，连同打标写入训练目录。

在 197 上跑（NAS 已挂载，仅用标准库 + curl）。超分跑在指定 ComfyUI worker 上。
"""
import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

WORKER = "192.168.1.249:8188"
NAS = Path("/mnt/nas_comfyui/AI-Tool-Studio/comfyui")
CELLS = NAS / "training/inbox/ria_cells"
INBOX = NAS / "training/inbox/ria"
DATASET = NAS / "training/jobs/ria_v1/dataset"
PORTRAIT = "ria_photo_AQADbxJrG5-MYVV-.jpg"

BASE = "ria, a young woman with long platinum blonde wavy hair, half-up bun hairstyle, brown eyes, flower earrings"
FACE_VIEW = {
    (0, 0): "front view, neutral expression",
    (0, 1): "three-quarter view, looking at camera",
    (0, 2): "three-quarter view, eyes glancing aside",
    (1, 0): "left profile view",
    (1, 1): "front view, soft smile",
    (1, 2): "front view, chin up, lips parted",
}
POSE = {
    (0, 0): "standing, front view",
    (0, 1): "standing, front view, relaxed arms",
    (0, 2): "standing, three-quarter view, hand on hip",
    (1, 0): "standing, side profile view",
    (1, 1): "standing, front view, looking at camera",
    (1, 2): "standing, one arm raised above head",
}
OUTFIT = {
    "ria_face": ("bare shoulders, closeup beauty portrait, white background", FACE_VIEW),
    "ria_boho": (
        "wearing a cream silk camisole top and lace-trimmed flared pants, platform heels, full body, studio photo, white background",
        POSE,
    ),
    "ria_black": (
        "wearing a black halter bodysuit, long black gloves and khaki flared trousers, black pointed shoes, full body, studio photo, light gray background",
        POSE,
    ),
}

UPSCALE_GRAPH = {
    "15": {"inputs": {"image": ""}, "class_type": "LoadImage"},
    "169": {
        "inputs": {
            "model": "seedvr2_ema_3b_fp16.safetensors",
            "device": "cuda:0",
            "blocks_to_swap": 32,
            "swap_io_components": True,
            "offload_device": "cpu",
            "cache_model": False,
            "attention_mode": "sdpa",
        },
        "class_type": "SeedVR2LoadDiTModel",
    },
    "170": {
        "inputs": {
            "model": "ema_vae_fp16.safetensors",
            "device": "cuda:0",
            "encode_tiled": True,
            "encode_tile_size": 1024,
            "encode_tile_overlap": 128,
            "decode_tiled": True,
            "decode_tile_size": 1024,
            "decode_tile_overlap": 128,
            "tile_debug": "false",
            "offload_device": "cpu",
            "cache_model": False,
        },
        "class_type": "SeedVR2LoadVAEModel",
    },
    "172": {
        "inputs": {
            "seed": 20260612,
            "resolution": 1024,
            "max_resolution": 4096,
            "batch_size": 5,
            "uniform_batch_size": False,
            "color_correction": "lab",
            "temporal_overlap": 0,
            "prepend_frames": 0,
            "input_noise_scale": 0,
            "latent_noise_scale": 0,
            "offload_device": "cpu",
            "enable_debug": False,
            "image": ["15", 0],
            "dit": ["169", 0],
            "vae": ["170", 0],
        },
        "class_type": "SeedVR2VideoUpscaler",
    },
    "174": {
        "inputs": {"filename_prefix": "ria_up/up", "images": ["172", 0]},
        "class_type": "SaveImage",
    },
}


def upload(path: Path) -> str:
    out = subprocess.run(
        ["curl", "-s", "-m", "60", f"http://{WORKER}/upload/image",
         "-F", f"image=@{path}", "-F", "overwrite=true"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)["name"]


def queue(graph: dict) -> str:
    req = urllib.request.Request(
        f"http://{WORKER}/prompt",
        data=json.dumps({"prompt": graph}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["prompt_id"]


def wait_result(pid: str, timeout_s: int = 900):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        with urllib.request.urlopen(f"http://{WORKER}/history/{pid}", timeout=15) as r:
            h = json.loads(r.read())
        if pid in h:
            item = h[pid]
            st = item.get("status", {})
            if st.get("completed"):
                for out in item.get("outputs", {}).values():
                    for img in out.get("images", []):
                        return img
            if st.get("status_str") == "error":
                raise RuntimeError(f"execution error: {json.dumps(st)[:400]}")
        time.sleep(5)
    raise TimeoutError(pid)


def fetch(img: dict, dest: Path):
    url = (f"http://{WORKER}/view?filename={urllib.request.quote(img['filename'])}"
           f"&subfolder={urllib.request.quote(img.get('subfolder', ''))}&type={img.get('type', 'output')}")
    urllib.request.urlretrieve(url, dest)


def caption_for(name: str) -> str:
    for prefix, (outfit, views) in OUTFIT.items():
        if name.startswith(prefix):
            r, c = int(name[name.index("_r") + 2]), int(name[name.index("c", name.index("_r")) + 1])
            return f"{BASE}, {outfit}, {views[(r, c)]}"
    return BASE


def main():
    DATASET.mkdir(parents=True, exist_ok=True)
    cells = sorted(CELLS.glob("ria_*.png"))
    print(f"[build] {len(cells)} 张单图待超分", flush=True)
    done = fail = 0
    for i, cell in enumerate(cells):
        target = DATASET / cell.name
        if target.exists():
            done += 1
            continue
        try:
            uploaded = upload(cell)
            g = json.loads(json.dumps(UPSCALE_GRAPH))
            g["15"]["inputs"]["image"] = uploaded
            g["174"]["inputs"]["filename_prefix"] = f"ria_up/{cell.stem}"
            img = wait_result(queue(g))
            fetch(img, target)
            target.with_suffix(".txt").write_text(caption_for(cell.name))
            done += 1
            print(f"[build] {i+1}/{len(cells)} {cell.name} ok", flush=True)
        except Exception as e:
            fail += 1
            print(f"[build] {cell.name} FAILED: {e}", flush=True)
    portrait_src = INBOX / PORTRAIT
    if portrait_src.exists():
        dest = DATASET / "ria_portrait.jpg"
        shutil.copy2(portrait_src, dest)
        dest.with_suffix(".txt").write_text(
            f"{BASE}, gold eyeshadow, bare shoulders, closeup beauty portrait, white background, front view, looking at camera"
        )
        print("[build] portrait ok", flush=True)
    n_img = len([p for p in DATASET.iterdir() if p.suffix.lower() in (".png", ".jpg")])
    print(f"[build] DONE 数据集共 {n_img} 张图，失败 {fail}", flush=True)
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
