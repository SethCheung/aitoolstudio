#!/usr/bin/env python3
"""ria 最终量产 lookbook：锁定配方出整套小红书内容。

配方（2026-06-14 多轮对标 aeri.ling 后锁定）：
  RealVisXL + ria_realvis LoRA @ 0.9 + 年轻白皙身份词 + 真实/锐度提示词
  → 生成 → SeedVR2-7b 超分（先放大） → FaceDetailer 面部精修（在高清图上修大脸） → 冷调后期
关键：超分在前、精修脸在后——让全身/半身的小脸也拿到近景级细节（修正了之前"全身脸糊"）。
FLUX/Z-Image/Qwen 因油画感/发光/欧美漂移弃用；强度 0.9 让脸贴最初定妆参考(ArcFace 0.68)。

依赖 249：Impact-Pack/Subpack + face_yolov8n.pt + SeedVR2 7b。在 249 跑。
    python3 scripts/ria_lookbook_final.py --out /tmp/ria_final
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

WORKER = "192.168.1.249:8188"
CKPT = "RealVisXL_V5.0_fp16.safetensors"
LORA = "digital_humans/ria_realvis.safetensors"
STRENGTH = 0.9
IDENT = "ria, youthful soft delicate features, fair pale skin"
QUALITY = "photorealistic, natural detailed skin texture, tack sharp focus, editorial fashion photography, natural light"
NEG = ("mature, aged, tan skin, heavy makeup, cartoon, illustration, 3d render, plastic skin, airbrushed, glow, "
       "bloom, soft focus, blurry, out of focus, lowres, deformed, extra fingers, watermark, text")

# 8 套：穿搭 × 机位（含近景/半身/3-4/全身，覆盖小红书内容形态）
LOOKS = [
    ("close",     "bare shoulders", "beauty closeup portrait, front view, looking at camera, white studio background"),
    ("cafe_half", "white silk top", "upper body, sitting by a bright cafe window, soft window light, candid"),
    ("street_full","beige knit sweater and denim shorts", "full body OOTD, standing on a city street in autumn, low angle"),
    ("3q_park",   "light blue denim shirt", "three-quarter portrait outdoors in a park, soft daylight, looking to the side"),
    ("chic_half", "black blazer dress", "upper body, minimalist studio, editorial pose, looking at camera"),
    ("dress_full","white floral summer dress", "full body, walking in a sunlit garden, candid mid-stride"),
    ("over_shoulder","cream off-shoulder top", "waist-up over-the-shoulder shot, looking back at the lens, hair flowing"),
    ("mirror_ootd","oversized denim jacket and pleated skirt", "full body mirror selfie, casual pose, bedroom"),
]


def graph(pos, seed):
    return {
        "1": {"inputs": {"ckpt_name": CKPT}, "class_type": "CheckpointLoaderSimple"},
        "2": {"inputs": {"lora_name": LORA, "strength_model": STRENGTH, "strength_clip": STRENGTH,
                          "model": ["1", 0], "clip": ["1", 1]}, "class_type": "LoraLoader"},
        "3": {"inputs": {"text": pos, "clip": ["2", 1]}, "class_type": "CLIPTextEncode"},
        "4": {"inputs": {"text": NEG, "clip": ["2", 1]}, "class_type": "CLIPTextEncode"},
        "5": {"inputs": {"width": 960, "height": 1216, "batch_size": 1}, "class_type": "EmptyLatentImage"},
        "6": {"inputs": {"seed": seed, "steps": 40, "cfg": 5.5, "sampler_name": "dpmpp_2m", "scheduler": "karras",
                          "denoise": 1, "model": ["2", 0], "positive": ["3", 0], "negative": ["4", 0],
                          "latent_image": ["5", 0]}, "class_type": "KSampler"},
        "7": {"inputs": {"samples": ["6", 0], "vae": ["1", 2]}, "class_type": "VAEDecode"},
        "169": {"inputs": {"model": "seedvr2_ema_7b_fp16.safetensors", "device": "cuda:0", "blocks_to_swap": 36,
                            "swap_io_components": True, "offload_device": "cpu", "cache_model": False,
                            "attention_mode": "sdpa"}, "class_type": "SeedVR2LoadDiTModel"},
        "170": {"inputs": {"model": "ema_vae_fp16.safetensors", "device": "cuda:0", "encode_tiled": True,
                            "encode_tile_size": 1024, "encode_tile_overlap": 128, "decode_tiled": True,
                            "decode_tile_size": 1024, "decode_tile_overlap": 128, "tile_debug": "false",
                            "offload_device": "cpu", "cache_model": False}, "class_type": "SeedVR2LoadVAEModel"},
        "172": {"inputs": {"seed": 20260614, "resolution": 1792, "max_resolution": 4096, "batch_size": 1,
                            "uniform_batch_size": False, "color_correction": "lab", "temporal_overlap": 0,
                            "prepend_frames": 0, "input_noise_scale": 0, "latent_noise_scale": 0,
                            "offload_device": "cpu", "enable_debug": False, "image": ["7", 0],
                            "dit": ["169", 0], "vae": ["170", 0]}, "class_type": "SeedVR2VideoUpscaler"},
        "12": {"inputs": {"model_name": "bbox/face_yolov8n.pt"}, "class_type": "UltralyticsDetectorProvider"},
        "13": {"inputs": {"image": ["172", 0], "model": ["2", 0], "clip": ["2", 1], "vae": ["1", 2],
                           "positive": ["3", 0], "negative": ["4", 0], "bbox_detector": ["12", 0],
                           "guide_size": 1024, "guide_size_for": True, "max_size": 1536, "seed": seed, "steps": 30,
                           "cfg": 5.5, "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 0.38,
                           "feather": 8, "noise_mask": True, "force_inpaint": True, "bbox_threshold": 0.5,
                           "bbox_dilation": 12, "bbox_crop_factor": 2.5, "sam_detection_hint": "center-1",
                           "sam_dilation": 0, "sam_threshold": 0.93, "sam_bbox_expansion": 0,
                           "sam_mask_hint_threshold": 0.7, "sam_mask_hint_use_negative": "False",
                           "drop_size": 10, "wildcard": "", "cycle": 1}, "class_type": "FaceDetailer"},
        "99": {"inputs": {"filename_prefix": "ria_final/f", "images": ["13", 0]}, "class_type": "SaveImage"},
    }


def submit(g):
    r = urllib.request.Request(f"http://{WORKER}/prompt", data=json.dumps({"prompt": g}).encode(),
                               headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=30).read())["prompt_id"]


def fetch(pid, dest, timeout=600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = json.loads(urllib.request.urlopen(f"http://{WORKER}/history/{pid}", timeout=15).read())
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("completed"):
                img = next(iter(h[pid]["outputs"].values()))["images"][0]
                url = (f"http://{WORKER}/view?filename={urllib.parse.quote(img['filename'])}"
                       f"&subfolder={urllib.parse.quote(img.get('subfolder', ''))}&type=output")
                urllib.request.urlretrieve(url, dest)
                return True
            if st.get("status_str") == "error":
                print(f"  ERR {dest.name}", flush=True)
                return False
        time.sleep(4)
    return False


def cool_grade(path):
    from PIL import Image, ImageEnhance
    im = Image.open(path).convert("RGB")
    r, g, b = im.split()
    r = r.point(lambda p: max(0, p - 4)); b = b.point(lambda p: min(255, p + 5))
    im = ImageEnhance.Color(Image.merge("RGB", (r, g, b))).enhance(0.95)
    im.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/ria_final")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    for i, (name, outfit, shot) in enumerate(LOOKS):
        pos = f"{IDENT}, {outfit}, {shot}, {QUALITY}"
        pid = submit(graph(pos, 612001 + i))
        print(f"[{i+1}/8] submit {name} {pid[:8]}", flush=True)
        dest = out / f"{i:02d}_{name}.png"
        if fetch(pid, dest):
            cool_grade(dest)
            print(f"[{i+1}/8] ok {name}", flush=True)
    print(f"DONE -> {out}", flush=True)


if __name__ == "__main__":
    main()
