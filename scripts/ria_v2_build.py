#!/usr/bin/env python3
"""ria_v2 数据集构建：从 v1 数据集裁出头部特写（高权重身份信号），小图回 249 超分。

在 197 上跑（face_qc_env：有 insightface/cv2）。产出结构：
  jobs/ria_v2/dataset_face/  头部特写（含 v1 的 7 张脸图原样收编）
  jobs/ria_v2/dataset_body/  v1 全身图原样
  jobs/ria_v2/dataset.toml   双数据块：face ×15 / body ×3
"""
import json
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np

WORKER = "192.168.1.249:8188"
NAS = Path("/mnt/nas_comfyui/AI-Tool-Studio/comfyui")
V1 = NAS / "training/jobs/ria_v1/dataset"
V2 = NAS / "training/jobs/ria_v2"
FACE_DIR = V2 / "dataset_face"
BODY_DIR = V2 / "dataset_body"
MODEL_ROOT = str(NAS / "models/insightface")
MARGIN = 0.9  # bbox 各方向外扩比例

UPSCALE_GRAPH_TMPL = Path(__file__).parent / "ria_dataset_build.py"  # 复用其中的图结构常量


def build_app():
    from insightface.app import FaceAnalysis
    app = FaceAnalysis(name="buffalo_l", root=MODEL_ROOT, allowed_modules=["detection"])
    app.prepare(ctx_id=-1, det_size=(640, 640))
    return app


def imread(p: Path):
    return cv2.imdecode(np.fromfile(str(p), dtype=np.uint8), cv2.IMREAD_COLOR)


def crop_head(app, img):
    faces = app.get(img)
    if not faces:
        return None
    f = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
    x1, y1, x2, y2 = f.bbox
    w, h = x2 - x1, y2 - y1
    cx1 = max(0, int(x1 - w * MARGIN))
    cy1 = max(0, int(y1 - h * MARGIN * 1.2))
    cx2 = min(img.shape[1], int(x2 + w * MARGIN))
    cy2 = min(img.shape[0], int(y2 + h * MARGIN))
    return img[cy1:cy2, cx1:cx2]


SEEDVR2 = {
    "15": {"inputs": {"image": ""}, "class_type": "LoadImage"},
    "169": {"inputs": {"model": "seedvr2_ema_3b_fp16.safetensors", "device": "cuda:0", "blocks_to_swap": 32,
                        "swap_io_components": True, "offload_device": "cpu", "cache_model": False,
                        "attention_mode": "sdpa"}, "class_type": "SeedVR2LoadDiTModel"},
    "170": {"inputs": {"model": "ema_vae_fp16.safetensors", "device": "cuda:0", "encode_tiled": True,
                        "encode_tile_size": 1024, "encode_tile_overlap": 128, "decode_tiled": True,
                        "decode_tile_size": 1024, "decode_tile_overlap": 128, "tile_debug": "false",
                        "offload_device": "cpu", "cache_model": False}, "class_type": "SeedVR2LoadVAEModel"},
    "172": {"inputs": {"seed": 20260612, "resolution": 1024, "max_resolution": 4096, "batch_size": 5,
                        "uniform_batch_size": False, "color_correction": "lab", "temporal_overlap": 0,
                        "prepend_frames": 0, "input_noise_scale": 0, "latent_noise_scale": 0,
                        "offload_device": "cpu", "enable_debug": False, "image": ["15", 0],
                        "dit": ["169", 0], "vae": ["170", 0]}, "class_type": "SeedVR2VideoUpscaler"},
    "174": {"inputs": {"filename_prefix": "ria_v2/up", "images": ["172", 0]}, "class_type": "SaveImage"},
}


def upscale_via_worker(local: Path, dest: Path):
    out = subprocess.run(["curl", "-s", "-m", "60", f"http://{WORKER}/upload/image",
                          "-F", f"image=@{local}", "-F", "overwrite=true"],
                         capture_output=True, text=True, check=True)
    name = json.loads(out.stdout)["name"]
    g = json.loads(json.dumps(SEEDVR2))
    g["15"]["inputs"]["image"] = name
    g["174"]["inputs"]["filename_prefix"] = f"ria_v2/{dest.stem}"
    req = urllib.request.Request(f"http://{WORKER}/prompt", data=json.dumps({"prompt": g}).encode(),
                                 headers={"Content-Type": "application/json"})
    pid = json.loads(urllib.request.urlopen(req, timeout=30).read())["prompt_id"]
    for _ in range(120):
        h = json.loads(urllib.request.urlopen(f"http://{WORKER}/history/{pid}", timeout=15).read())
        if pid in h and h[pid].get("status", {}).get("completed"):
            img = next(iter(h[pid]["outputs"].values()))["images"][0]
            url = (f"http://{WORKER}/view?filename={urllib.request.quote(img['filename'])}"
                   f"&subfolder={urllib.request.quote(img.get('subfolder', ''))}&type=output")
            urllib.request.urlretrieve(url, dest)
            return
        time.sleep(4)
    raise TimeoutError(str(local))


def main():
    FACE_DIR.mkdir(parents=True, exist_ok=True)
    BODY_DIR.mkdir(parents=True, exist_ok=True)
    app = build_app()
    images = sorted([p for p in V1.iterdir() if p.suffix.lower() in (".png", ".jpg")])
    base_caption = ("ria, a young woman with long platinum blonde wavy hair, half-up bun hairstyle, "
                    "brown eyes, flower earrings, head and shoulders portrait")
    n_face = n_body = 0
    for p in images:
        cap = p.with_suffix(".txt").read_text() if p.with_suffix(".txt").exists() else base_caption
        if p.name.startswith(("ria_face", "ria_portrait")):
            shutil.copy2(p, FACE_DIR / p.name)
            (FACE_DIR / p.name).with_suffix(".txt").write_text(cap)
            n_face += 1
            continue
        # 全身图：原样进 body，头部裁切进 face
        shutil.copy2(p, BODY_DIR / p.name)
        (BODY_DIR / p.name).with_suffix(".txt").write_text(cap)
        n_body += 1
        img = imread(p)
        head = crop_head(app, img)
        if head is None:
            print(f"[v2] {p.name} 检不到脸，跳过裁切", flush=True)
            continue
        tmp = Path("/tmp") / f"head_{p.stem}.png"
        cv2.imencode(".png", head)[1].tofile(str(tmp))
        dest = FACE_DIR / f"head_{p.stem}.png"
        if min(head.shape[:2]) < 900:
            upscale_via_worker(tmp, dest)
        else:
            shutil.copy2(tmp, dest)
        dest.with_suffix(".txt").write_text(base_caption)
        n_face += 1
        print(f"[v2] {p.name} -> 头部特写 ok", flush=True)

    (V2 / "dataset.toml").write_text(f'''[general]
resolution = [1024, 1024]
caption_extension = ".txt"
batch_size = 1
enable_bucket = true
bucket_no_upscale = false

[[datasets]]
image_directory = "{FACE_DIR}"
cache_directory = "/home/sjm/lora_work/ria_v2/cache_face"
num_repeats = 15

[[datasets]]
image_directory = "{BODY_DIR}"
cache_directory = "/home/sjm/lora_work/ria_v2/cache_body"
num_repeats = 3
''')
    (V2 / "job.env").write_text("NETWORK_DIM=32\nEPOCHS=20\nSAVE_EVERY=5\n")
    print(f"[v2] DONE face={n_face} body={n_body}", flush=True)


if __name__ == "__main__":
    main()
