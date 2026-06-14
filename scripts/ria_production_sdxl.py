#!/usr/bin/env python3
"""ria 量产工作流（最终方案·Juggernaut XL）：写实+锁脸，治好了 Qwen 油画感和 Z-Image 发光/欧美漂移。

多底模对比结论（2026-06-14）：
  Juggernaut-XL(SDXL) 胜出——身份绑得最死（连文本编码器一起训），近景 ArcFace 0.73、
  脸对得上原图(非欧美)、白金发+花耳饰 LoRA 自带、无发光。
  Z-Image 写实但自带发光+加发色提示词会把脸带欧美；FLUX.2-dev 因 24B TE>195内存不可行。

管线：Juggernaut-XL + ria_sdxl LoRA + [全身镜头发色写进提示词] + YOLO FaceDetailer 锁小脸。
  近景/半身：LoRA 自带身份，纯 "ria" 触发即可。
  全身：脸太小 LoRA 抓不住，提示词补 "platinum blonde hair" + FaceDetailer 重渲染小脸（0.24→0.63）。

依赖：249 ComfyUI 需 Impact-Pack + Impact-Subpack(dill) + models/ultralytics/bbox/face_yolov8n.pt。
用法：
    python3 scripts/ria_production_sdxl.py --test --framing full
    python3 scripts/ria_production_sdxl.py            # 只写 workflow 文件
"""
import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORKER = "192.168.1.249:8188"
CKPT = "juggernautXL_version6Rundiffusion.safetensors"
LORA = "digital_humans/ria_sdxl.safetensors"
WF_PATH = REPO / "workflows/ria-sdxl-production.json"
NEG = "cartoon, illustration, 3d, plastic skin, lowres, blurry, deformed, extra fingers, glow, bloom, watermark, text"


def build(pos, seed=700300, w=832, h=1216, strength=1.0, face_detailer=True):
    g = {
        "1": {"inputs": {"ckpt_name": CKPT}, "class_type": "CheckpointLoaderSimple"},
        "2": {"inputs": {"lora_name": LORA, "strength_model": strength, "strength_clip": strength,
                          "model": ["1", 0], "clip": ["1", 1]}, "class_type": "LoraLoader"},
        "3": {"inputs": {"text": pos, "clip": ["2", 1]}, "class_type": "CLIPTextEncode"},
        "4": {"inputs": {"text": NEG, "clip": ["2", 1]}, "class_type": "CLIPTextEncode"},
        "5": {"inputs": {"width": w, "height": h, "batch_size": 1}, "class_type": "EmptyLatentImage"},
        "6": {"inputs": {"seed": seed, "steps": 30, "cfg": 6.0, "sampler_name": "dpmpp_2m", "scheduler": "karras",
                          "denoise": 1, "model": ["2", 0], "positive": ["3", 0], "negative": ["4", 0],
                          "latent_image": ["5", 0]}, "class_type": "KSampler"},
        "7": {"inputs": {"samples": ["6", 0], "vae": ["1", 2]}, "class_type": "VAEDecode"},
    }
    if not face_detailer:
        g["99"] = {"inputs": {"filename_prefix": "ria_prod/sdxl", "images": ["7", 0]}, "class_type": "SaveImage"}
        return g
    # 脸部精修（YOLO 检测 + ria LoRA 重渲染，锁全身小脸）
    g["12"] = {"inputs": {"model_name": "bbox/face_yolov8n.pt"}, "class_type": "UltralyticsDetectorProvider"}
    g["8"] = {"inputs": {"text": "ria, platinum blonde, face, photorealistic detailed skin, sharp eyes",
                          "clip": ["2", 1]}, "class_type": "CLIPTextEncode"}
    g["13"] = {"inputs": {
        "image": ["7", 0], "model": ["2", 0], "clip": ["2", 1], "vae": ["1", 2],
        "positive": ["8", 0], "negative": ["4", 0], "bbox_detector": ["12", 0],
        "guide_size": 512, "guide_size_for": True, "max_size": 1024,
        "seed": 42, "steps": 25, "cfg": 6.0, "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 0.45,
        "feather": 5, "noise_mask": True, "force_inpaint": True,
        "bbox_threshold": 0.5, "bbox_dilation": 10, "bbox_crop_factor": 3.0,
        "sam_detection_hint": "center-1", "sam_dilation": 0, "sam_threshold": 0.93,
        "sam_bbox_expansion": 0, "sam_mask_hint_threshold": 0.7, "sam_mask_hint_use_negative": "False",
        "drop_size": 10, "wildcard": "", "cycle": 1}, "class_type": "FaceDetailer"}
    g["99"] = {"inputs": {"filename_prefix": "ria_prod/sdxl", "images": ["13", 0]}, "class_type": "SaveImage"}
    return g


# 近景/半身：LoRA 自带身份，无需写发色；全身：补发色提示词
POS_CLOSE = "ria, closeup beauty portrait, front view, looking at camera, white background, photorealistic"
POS_FULL = ("ria, platinum blonde long wavy hair with half-up bun, walking on a city street in autumn, full body, "
            "beige knit sweater and denim shorts, photorealistic, natural light, detailed skin")


def test(framing):
    import time
    pos, (w, h) = (POS_FULL, (832, 1216)) if framing == "full" else (POS_CLOSE, (832, 1024))
    g = build(pos, w=w, h=h)
    req = urllib.request.Request(f"http://{WORKER}/prompt", data=json.dumps({"prompt": g}).encode(),
                                 headers={"Content-Type": "application/json"})
    pid = json.loads(urllib.request.urlopen(req, timeout=30).read())["prompt_id"]
    print(f"[test:{framing}] {pid[:8]}", flush=True)
    t0 = time.time()
    out = Path("/tmp/ria_prod_sdxl"); out.mkdir(exist_ok=True)
    while time.time() - t0 < 400:
        h2 = json.loads(urllib.request.urlopen(f"http://{WORKER}/history/{pid}", timeout=15).read())
        if pid in h2 and h2[pid].get("status", {}).get("completed"):
            img = next(iter(h2[pid]["outputs"].values()))["images"][0]
            url = (f"http://{WORKER}/view?filename={urllib.parse.quote(img['filename'])}"
                   f"&subfolder={urllib.parse.quote(img.get('subfolder', ''))}&type=output")
            urllib.request.urlretrieve(url, out / f"{framing}.png")
            print(f"[test:{framing}] ok -> {out}/{framing}.png", flush=True)
            return
        time.sleep(4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--framing", choices=["close", "full"], default="full")
    args = ap.parse_args()
    WF_PATH.write_text(json.dumps(build(POS_FULL, face_detailer=True), ensure_ascii=False, indent=2))
    print(f"[build] workflow -> {WF_PATH}")
    if args.test:
        test(args.framing)


if __name__ == "__main__":
    main()
