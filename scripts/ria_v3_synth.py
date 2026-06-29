#!/usr/bin/env python3
"""ria_v3 数据集合成：用 Qwen-Image-Edit 2511 以主脸照为身份参考，原生 1140x1472 合成多角度/表情定妆照。

在 197 上跑（NAS 挂载）。生成 → 后续由 face_qc 闸门筛选。
"""
import json
import subprocess
import time
import urllib.request
from pathlib import Path

WORKER = "192.168.1.249:8188"
NAS = Path("/mnt/nas_comfyui/AI-Tool-Studio/comfyui")
PORTRAIT = NAS / "training/jobs/ria_v1/dataset/ria_portrait.jpg"
OUT = NAS / "training/inbox/ria_v3_synth"

KEEP = ("keep her facial identity, face shape, chin and jawline exactly the same as the reference, "
        "keep the platinum blonde wavy hair with half-up bun and flower earrings, "
        "studio portrait, plain white background, soft studio lighting, photorealistic, "
        "high detail natural skin texture, youthful face")

VARIANTS = [
    ("front_neutral", "A studio portrait of the same woman facing the camera directly, neutral expression"),
    ("tq_left", "Rotate her head to a three-quarter left view"),
    ("tq_right", "Rotate her head to a three-quarter right view"),
    ("profile_left", "Show her head in a full left profile view"),
    ("profile_right", "Show her head in a full right profile view"),
    ("look_up", "She tilts her chin up slightly, eyes looking slightly upward"),
    ("look_down", "She lowers her gaze slightly, calm expression"),
    ("smile_soft", "She shows a gentle soft smile, facing the camera"),
    ("smile_big", "She shows a bright happy smile with teeth, facing the camera"),
    ("serious", "She has a calm serious editorial expression, facing the camera"),
    ("tq_left_smile", "Three-quarter left view with a gentle soft smile"),
    ("tq_right_smile", "Three-quarter right view with a gentle soft smile"),
    ("closeup", "A tighter close-up of her face, facing the camera, neutral expression"),
    ("wider", "A slightly wider head-and-shoulders framing, facing the camera"),
]
SEEDS = [613001, 613002]


def upload(path: Path) -> str:
    out = subprocess.run(["curl", "-s", "-m", "60", f"http://{WORKER}/upload/image",
                          "-F", f"image=@{path}", "-F", "overwrite=true"],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)["name"]


def graph(ref_name: str, instruction: str, seed: int, prefix: str) -> dict:
    return {
        "1": {"inputs": {"unet_name": "qwen_image_edit_2511_fp8_e4m3fn.safetensors", "weight_dtype": "default"},
              "class_type": "UNETLoader"},
        "2": {"inputs": {"clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "type": "qwen_image", "device": "default"},
              "class_type": "CLIPLoader"},
        "3": {"inputs": {"vae_name": "qwen_image_vae.safetensors"}, "class_type": "VAELoader"},
        "4": {"inputs": {"image": ref_name}, "class_type": "LoadImage"},
        "5": {"inputs": {"clip": ["2", 0], "prompt": f"{instruction}. {KEEP}", "vae": ["3", 0], "image1": ["4", 0]},
              "class_type": "TextEncodeQwenImageEditPlus"},
        "6": {"inputs": {"clip": ["2", 0], "prompt": "", "vae": ["3", 0], "image1": ["4", 0]},
              "class_type": "TextEncodeQwenImageEditPlus"},
        "7": {"inputs": {"width": 1140, "height": 1472, "batch_size": 1}, "class_type": "EmptySD3LatentImage"},
        "8": {"inputs": {"shift": 3.1, "model": ["1", 0]}, "class_type": "ModelSamplingAuraFlow"},
        "9": {"inputs": {"seed": seed, "steps": 20, "cfg": 2.5, "sampler_name": "euler", "scheduler": "simple",
                          "denoise": 1, "model": ["8", 0], "positive": ["5", 0], "negative": ["6", 0],
                          "latent_image": ["7", 0]}, "class_type": "KSampler"},
        "10": {"inputs": {"samples": ["9", 0], "vae": ["3", 0]}, "class_type": "VAEDecode"},
        "11": {"inputs": {"filename_prefix": prefix, "images": ["10", 0]}, "class_type": "SaveImage"},
    }


def submit(g: dict) -> str:
    req = urllib.request.Request(f"http://{WORKER}/prompt", data=json.dumps({"prompt": g}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())["prompt_id"]


def wait_fetch(pid: str, dest: Path, timeout_s: int = 900) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        h = json.loads(urllib.request.urlopen(f"http://{WORKER}/history/{pid}", timeout=15).read())
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("completed"):
                img = next(iter(h[pid]["outputs"].values()))["images"][0]
                url = (f"http://{WORKER}/view?filename={urllib.request.quote(img['filename'])}"
                       f"&subfolder={urllib.request.quote(img.get('subfolder', ''))}&type=output")
                urllib.request.urlretrieve(url, dest)
                return True
            if st.get("status_str") == "error":
                return False
        time.sleep(5)
    return False


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ref = upload(PORTRAIT)
    jobs = []
    for vname, instr in VARIANTS:
        for si, seed in enumerate(SEEDS):
            name = f"synth_{vname}_s{si}.png"
            if (OUT / name).exists():
                continue
            jobs.append((name, submit(graph(ref, instr, seed, f"ria_v3/{vname}_s{si}"))))
    print(f"[synth] 已提交 {len(jobs)} 张", flush=True)
    ok = 0
    for name, pid in jobs:
        if wait_fetch(pid, OUT / name):
            ok += 1
            print(f"[synth] {name} ok", flush=True)
        else:
            print(f"[synth] {name} FAILED", flush=True)
    print(f"[synth] DONE {ok}/{len(jobs)} -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
