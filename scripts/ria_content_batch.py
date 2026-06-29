#!/usr/bin/env python3
"""ria 内容批产：用拍摄公式（ria_shot_formula）跑成一组多样化穿搭图。

支持两套底模管线：
  --engine zimage   Z-Image Turbo + ria_v4z LoRA（写实，治油画感）
  --engine qwen     Qwen-Image + ria_v4 LoRA + FaceDetailer（旧管线，对照）

用法：
  python3 scripts/ria_content_batch.py --engine zimage --mode lookbook --out /tmp/ria_lookbook
  python3 scripts/ria_content_batch.py --engine zimage --mode series --outfit-idx 0
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ria_shot_formula as F

WORKERS = ["192.168.1.249:8188", "192.168.1.195:8188"]


def zimage_graph(lora, pos, neg, seed, w=832, h=1216, strength=1.0, steps=12, cfg=1.0):
    return {
        "33": {"inputs": {"model_name": "z_image_turbo_bf16.safetensors", "weight_dtype": "default",
                          "key_opt": "", "mode": "Auto"}, "class_type": "LoadDiffusionModelShared //Inspire"},
        "50": {"inputs": {"lora_name": lora, "strength_model": strength, "model": ["33", 0]},
               "class_type": "LoraLoaderModelOnly"},
        "34": {"inputs": {"model_name1": "qwen_3_4b.safetensors", "model_name2": "None", "model_name3": "None",
                          "type": "stable_diffusion", "key_opt": "", "mode": "Auto", "device": "default"},
               "class_type": "LoadTextEncoderShared //Inspire"},
        "27": {"inputs": {"vae_name": "ae.safetensors"}, "class_type": "VAELoader"},
        "23": {"inputs": {"text": pos, "clip": ["34", 0]}, "class_type": "CLIPTextEncode"},
        "26": {"inputs": {"text": neg, "clip": ["34", 0]}, "class_type": "CLIPTextEncode"},
        "144": {"inputs": {"width": w, "height": h, "batch_size": 1}, "class_type": "EmptySD3LatentImage"},
        "22": {"inputs": {"seed": seed, "steps": steps, "cfg": cfg, "sampler_name": "euler", "scheduler": "simple",
                          "denoise": 1, "model": ["50", 0], "positive": ["23", 0], "negative": ["26", 0],
                          "latent_image": ["144", 0]}, "class_type": "KSampler"},
        "20": {"inputs": {"samples": ["22", 0], "vae": ["27", 0]}, "class_type": "VAEDecode"},
        "99": {"inputs": {"filename_prefix": "ria_content/c", "images": ["20", 0]}, "class_type": "SaveImage"},
    }


def sdxl_graph(lora, pos, neg, seed, w=832, h=1216, strength=1.0, steps=30, cfg=6.0):
    ckpt = "juggernautXL_version6Rundiffusion.safetensors"
    return {
        "1": {"inputs": {"ckpt_name": ckpt}, "class_type": "CheckpointLoaderSimple"},
        "2": {"inputs": {"lora_name": lora, "strength_model": strength, "strength_clip": strength,
                          "model": ["1", 0], "clip": ["1", 1]}, "class_type": "LoraLoader"},
        "3": {"inputs": {"text": pos, "clip": ["2", 1]}, "class_type": "CLIPTextEncode"},
        "4": {"inputs": {"text": neg, "clip": ["2", 1]}, "class_type": "CLIPTextEncode"},
        "5": {"inputs": {"width": w, "height": h, "batch_size": 1}, "class_type": "EmptyLatentImage"},
        "6": {"inputs": {"seed": seed, "steps": steps, "cfg": cfg, "sampler_name": "dpmpp_2m", "scheduler": "karras",
                          "denoise": 1, "model": ["2", 0], "positive": ["3", 0], "negative": ["4", 0],
                          "latent_image": ["5", 0]}, "class_type": "KSampler"},
        "7": {"inputs": {"samples": ["6", 0], "vae": ["1", 2]}, "class_type": "VAEDecode"},
        "99": {"inputs": {"filename_prefix": "ria_content/c", "images": ["7", 0]}, "class_type": "SaveImage"},
    }


def submit(worker, g):
    r = urllib.request.Request(f"http://{worker}/prompt", data=json.dumps({"prompt": g}).encode(),
                               headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=30).read())["prompt_id"]


def fetch(worker, pid, dest, timeout_s=900):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        h = json.loads(urllib.request.urlopen(f"http://{worker}/history/{pid}", timeout=15).read())
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("completed"):
                img = next(iter(h[pid]["outputs"].values()))["images"][0]
                url = (f"http://{worker}/view?filename={urllib.parse.quote(img['filename'])}"
                       f"&subfolder={urllib.parse.quote(img.get('subfolder', ''))}&type=output")
                urllib.request.urlretrieve(url, dest)
                return True
            if st.get("status_str") == "error":
                print(f"  ERR {dest.name}: {json.dumps(st, ensure_ascii=False)[:200]}", flush=True)
                return False
        time.sleep(4)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["zimage", "sdxl", "qwen"], default="sdxl")
    ap.add_argument("--mode", choices=["series", "lookbook"], default="lookbook")
    ap.add_argument("--outfit-idx", type=int, default=0)
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--lora", default="digital_humans/ria_v4z.safetensors")
    ap.add_argument("--strength", type=float, default=1.0)
    ap.add_argument("--workers", default=None, help="逗号分隔覆盖 worker 列表，如 192.168.1.249:8188")
    ap.add_argument("--out", default="/tmp/ria_lookbook")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    global WORKERS
    if args.workers:
        WORKERS = [w.strip() for w in args.workers.split(",") if w.strip()]

    items = F.series(args.outfit_idx) if args.mode == "series" else F.lookbook(args.n)
    jobs = []
    for i, (name, pos) in enumerate(items):
        worker = WORKERS[i % len(WORKERS)]
        if args.engine == "zimage":
            g = zimage_graph(args.lora, pos, F.NEGATIVE, 700200 + i, strength=args.strength)
        elif args.engine == "sdxl":
            g = sdxl_graph(args.lora, pos, F.NEGATIVE, 700200 + i, strength=args.strength)
        else:
            raise SystemExit("qwen engine: 用 ria_production_build 管线")
        pid = submit(worker, g)
        jobs.append((name, worker, pid))
        print(f"submit {name} -> {worker}", flush=True)
    ok = 0
    for name, worker, pid in jobs:
        if fetch(worker, pid, out / f"{name}.png"):
            ok += 1; print(f"ok {name}", flush=True)
    print(f"DONE {ok}/{len(jobs)} -> {out}", flush=True)


if __name__ == "__main__":
    main()
