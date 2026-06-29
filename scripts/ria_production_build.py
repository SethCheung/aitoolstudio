#!/usr/bin/env python3
"""构建 ria 量产工作流：Qwen-Image 2512 + ria_v4 LoRA + FaceDetailer 精修脸/皮肤。

检测器用 MediaPipeFaceMeshDetectorProvider //Inspire（无需 Impact-Subpack / 额外权重）。
输出 workflows/Qwen-Image-ria.json。--test 时在 249 出一张对比（base vs 精修）。

    python3 scripts/ria_production_build.py           # 只生成 workflow 文件
    python3 scripts/ria_production_build.py --test     # 生成并出对比图
"""
import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORKER = "192.168.1.249:8188"
LORA = "digital_humans/ria_v4.safetensors"
WF_PATH = REPO / "workflows/Qwen-Image-ria.json"

POS_DEFAULT = "ria, wearing a white t-shirt, sitting in a sunlit cafe, upper body, looking at camera, photorealistic, natural skin texture"
NEG_DEFAULT = "lowres, bad anatomy, blurry, watermark, text, plastic skin, waxy, airbrushed"


def build(pos=POS_DEFAULT, neg=NEG_DEFAULT, seed=612001, save_base=True):
    g = {
        "1": {"inputs": {"model_name": "qwen_image_2512_fp8_e4m3fn.safetensors", "weight_dtype": "default",
                          "key_opt": "", "mode": "Auto"}, "class_type": "LoadDiffusionModelShared //Inspire"},
        "2": {"inputs": {"clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "type": "qwen_image", "device": "default"},
              "class_type": "CLIPLoader"},
        "3": {"inputs": {"vae_name": "qwen_image_vae.safetensors"}, "class_type": "VAELoader"},
        "11": {"inputs": {"lora_name": LORA, "strength_model": 1.0, "model": ["1", 0]},
               "class_type": "LoraLoaderModelOnly"},
        "4": {"inputs": {"shift": 3.1, "model": ["11", 0]}, "class_type": "ModelSamplingAuraFlow"},
        "5": {"inputs": {"text": pos, "clip": ["2", 0]}, "class_type": "CLIPTextEncode"},
        "6": {"inputs": {"text": neg, "clip": ["2", 0]}, "class_type": "CLIPTextEncode"},
        # 脸部精修专用正向：聚焦皮肤纹理/眼睛细节
        "15": {"inputs": {"text": "ria, face portrait, detailed natural skin texture with visible pores, sharp clear eyes, photorealistic",
                           "clip": ["2", 0]}, "class_type": "CLIPTextEncode"},
        "7": {"inputs": {"width": 1140, "height": 1472, "batch_size": 1}, "class_type": "EmptySD3LatentImage"},
        "8": {"inputs": {"seed": seed, "steps": 20, "cfg": 2.5, "sampler_name": "euler", "scheduler": "simple",
                          "denoise": 1, "model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0],
                          "latent_image": ["7", 0]}, "class_type": "KSampler"},
        "9": {"inputs": {"samples": ["8", 0], "vae": ["3", 0]}, "class_type": "VAEDecode"},
        # 人脸检测器（MediaPipe，全脸）
        "12": {"inputs": {"max_faces": 1, "face": True, "mouth": False, "left_eyebrow": False, "left_eye": False,
                           "left_pupil": False, "right_eyebrow": False, "right_eye": False, "right_pupil": False},
               "class_type": "MediaPipeFaceMeshDetectorProvider //Inspire"},
        # 脸部精修：同模型(含 ria LoRA)+同提示词，denoise 0.45 还皮肤细节
        "13": {"inputs": {
            "image": ["9", 0], "model": ["4", 0], "clip": ["2", 0], "vae": ["3", 0],
            "positive": ["15", 0], "negative": ["6", 0], "bbox_detector": ["12", 0],
            "guide_size": 768, "guide_size_for": True, "max_size": 1024,
            "seed": seed, "steps": 20, "cfg": 2.5, "sampler_name": "euler", "scheduler": "simple", "denoise": 0.5,
            "feather": 5, "noise_mask": True, "force_inpaint": True,
            "bbox_threshold": 0.5, "bbox_dilation": 10, "bbox_crop_factor": 3.0,
            "sam_detection_hint": "center-1", "sam_dilation": 0, "sam_threshold": 0.93,
            "sam_bbox_expansion": 0, "sam_mask_hint_threshold": 0.7, "sam_mask_hint_use_negative": "False",
            "drop_size": 10, "wildcard": "", "cycle": 1},
            "class_type": "FaceDetailer"},
        # SeedVR2-7b 超分：还原皮肤/发丝真实细节 + 升到 2048 短边，治油画感+分辨率
        "16": {"inputs": {"model": "seedvr2_ema_7b_fp16.safetensors", "device": "cuda:0", "blocks_to_swap": 36,
                           "swap_io_components": True, "offload_device": "cpu", "cache_model": False,
                           "attention_mode": "sdpa"}, "class_type": "SeedVR2LoadDiTModel"},
        "17": {"inputs": {"model": "ema_vae_fp16.safetensors", "device": "cuda:0", "encode_tiled": True,
                           "encode_tile_size": 1024, "encode_tile_overlap": 128, "decode_tiled": True,
                           "decode_tile_size": 1024, "decode_tile_overlap": 128, "tile_debug": "false",
                           "offload_device": "cpu", "cache_model": False}, "class_type": "SeedVR2LoadVAEModel"},
        "18": {"inputs": {"seed": seed, "resolution": 2048, "max_resolution": 4096, "batch_size": 1,
                           "uniform_batch_size": False, "color_correction": "lab", "temporal_overlap": 0,
                           "prepend_frames": 0, "input_noise_scale": 0, "latent_noise_scale": 0,
                           "offload_device": "cpu", "enable_debug": False, "image": ["13", 0],
                           "dit": ["16", 0], "vae": ["17", 0]}, "class_type": "SeedVR2VideoUpscaler"},
        "14": {"inputs": {"filename_prefix": "ria_prod/final", "images": ["18", 0]}, "class_type": "SaveImage"},
    }
    if save_base:
        g["10"] = {"inputs": {"filename_prefix": "ria_prod/base", "images": ["9", 0]}, "class_type": "SaveImage"}
    return g


def submit(graph):
    req = urllib.request.Request(f"http://{WORKER}/prompt", data=json.dumps({"prompt": graph}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())["prompt_id"]


def test():
    import time
    out = Path("/tmp/ria_prod_test")
    out.mkdir(parents=True, exist_ok=True)
    g = build(save_base=True)
    pid = submit(g)
    print(f"[test] 提交 {pid[:8]}，等待（base + FaceDetailer 两张输出）...", flush=True)
    t0 = time.time()
    while time.time() - t0 < 900:
        h = json.loads(urllib.request.urlopen(f"http://{WORKER}/history/{pid}", timeout=15).read())
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("completed"):
                for node_id, o in h[pid]["outputs"].items():
                    if "images" not in o:
                        continue
                    for img in o["images"]:
                        tag = "final" if node_id == "14" else "base"
                        url = (f"http://{WORKER}/view?filename={urllib.parse.quote(img['filename'])}"
                               f"&subfolder={urllib.parse.quote(img.get('subfolder', ''))}&type=output")
                        urllib.request.urlretrieve(url, out / f"{tag}.png")
                        print(f"[test] saved {tag}.png", flush=True)
                print(f"[test] DONE -> {out}", flush=True)
                return True
            if st.get("status_str") == "error":
                print(f"[test] EXEC ERROR: {json.dumps(h[pid].get('status'), ensure_ascii=False)[:500]}", flush=True)
                # 打印节点错误细节
                msgs = h[pid].get("status", {}).get("messages", [])
                for m in msgs:
                    if "error" in str(m).lower():
                        print("   ", str(m)[:400], flush=True)
                return False
        time.sleep(4)
    print("[test] TIMEOUT", flush=True)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()
    # 保存模板（不含 base 保存节点，量产只出精修图）
    WF_PATH.write_text(json.dumps(build(save_base=False), ensure_ascii=False, indent=2))
    print(f"[build] 工作流已写 -> {WF_PATH}")
    if args.test:
        test()


if __name__ == "__main__":
    main()
