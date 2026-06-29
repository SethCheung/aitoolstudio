#!/usr/bin/env python3
"""ria_v4 候选生成：用 Qwen-Image-Edit 2511 从用户确认的 3 张脸（c0/c1/portrait）
编辑出多角度/表情/光线/景别变体，作为 v4 训练集候选池。随后由 face_qc 硬筛 ArcFace>=0.6。

与 v3 的关键区别：v3 用 LoRA 文生图（每次现编一张飘的脸）；v4 用 Edit 编辑「确认过的真脸」，
身份信号来自真实参考图而非漂移的权重，再叠硬筛，保证训练集是同一张脸。

在 Mac 跑（参考图取本地 /tmp/ria_identity，上传到两台 worker）。
    python3 scripts/ria_v4_gen.py --out /tmp/ria_v4_pool
"""
import argparse
import json
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

WORKERS = ["192.168.1.249:8188", "192.168.1.195:8188"]
# 本地参考图（之前已 fetch）→ 上传到 worker 后的文件名
REFS = {
    "c0": "/tmp/ria_identity/01_grid_0.747.png",
    "c1": "/tmp/ria_identity/02_grid_0.650.png",
    "portrait": "/tmp/ria_identity/00_portrait_REF.jpg",
}

KEEP = ("keep her exact facial identity, face shape, jawline and features identical to the reference, "
        "platinum blonde wavy hair with a half-up bun, photorealistic, natural detailed skin texture "
        "with visible pores and fine skin detail, sharp focus, professional photograph, no plastic skin")

# (名称, 编辑指令) —— 角度 / 表情 / 光线 / 景别 / 少量场景
INSTRUCTIONS = [
    ("front_neutral_studio", "She faces the camera directly with a calm neutral expression, clean white studio background, soft even studio lighting, head and shoulders"),
    ("front_smile_studio", "She faces the camera with a gentle natural soft smile, white studio background, soft lighting, head and shoulders"),
    ("tq_left_neutral", "Turn her head to a three-quarter left view, neutral expression, light grey studio background, soft lighting"),
    ("tq_right_smile", "Turn her head to a three-quarter right view, soft smile, studio background, soft lighting"),
    ("front_daylight", "She faces the camera, neutral expression, bright natural daylight, soft outdoor background, upper body"),
    ("golden_hour", "She faces the camera with a soft smile, warm golden hour sunlight, outdoor, upper body"),
    ("cafe_window", "She sits by a cafe window with soft natural window light, looking at the camera, upper body, casual"),
    ("street_day", "She stands on a city street in daytime with natural light, looking at the camera, upper body"),
    ("serious_editorial", "She has a calm serious editorial expression, facing the camera, soft studio light, head and shoulders"),
    ("look_up_soft", "Her chin is slightly up and eyes looking gently upward, soft expression, studio soft light"),
    ("look_down_calm", "Her gaze is lowered with a calm serene expression, studio soft light"),
    ("closeup_beauty", "A tight beauty close-up of her face, facing the camera, neutral expression, soft light, highly detailed skin"),
    ("tq_left_smile", "Three-quarter left view with a bright happy smile, studio background"),
    ("indoor_warm", "Indoors with warm ambient light, looking at the camera, upper body, relaxed"),
    ("side_soft_light", "She faces the camera under soft directional side lighting, neutral expression, head and shoulders"),
    ("natural_candid", "A candid natural moment in soft daylight, slight smile, upper body"),
]
SEEDS = [614001, 614002, 614003]


def upload(worker: str, path: str) -> str:
    out = subprocess.run(["curl", "-s", "-m", "60", f"http://{worker}/upload/image",
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
        "6": {"inputs": {"clip": ["2", 0], "prompt": "plastic skin, waxy, airbrushed, blurry, lowres, deformed, extra fingers",
                          "vae": ["3", 0], "image1": ["4", 0]},
              "class_type": "TextEncodeQwenImageEditPlus"},
        "7": {"inputs": {"width": 1140, "height": 1472, "batch_size": 1}, "class_type": "EmptySD3LatentImage"},
        "8": {"inputs": {"shift": 3.1, "model": ["1", 0]}, "class_type": "ModelSamplingAuraFlow"},
        "9": {"inputs": {"seed": seed, "steps": 22, "cfg": 2.8, "sampler_name": "euler", "scheduler": "simple",
                          "denoise": 1, "model": ["8", 0], "positive": ["5", 0], "negative": ["6", 0],
                          "latent_image": ["7", 0]}, "class_type": "KSampler"},
        "10": {"inputs": {"samples": ["9", 0], "vae": ["3", 0]}, "class_type": "VAEDecode"},
        "11": {"inputs": {"filename_prefix": prefix, "images": ["10", 0]}, "class_type": "SaveImage"},
    }


def submit(worker, g):
    req = urllib.request.Request(f"http://{worker}/prompt", data=json.dumps({"prompt": g}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())["prompt_id"]


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
                return False
        time.sleep(4)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/ria_v4_pool")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # 把 3 张参考图上传到两台 worker，拿到各自文件名
    ref_names = {w: {} for w in WORKERS}
    for w in WORKERS:
        for k, p in REFS.items():
            ref_names[w][k] = upload(w, p)
        print(f"[v4gen] refs uploaded -> {w}", flush=True)

    ref_keys = list(REFS.keys())
    jobs = []
    i = 0
    for iname, instr in INSTRUCTIONS:
        for si, seed in enumerate(SEEDS):
            rk = ref_keys[i % len(ref_keys)]
            worker = WORKERS[i % len(WORKERS)]
            i += 1
            g = graph(ref_names[worker][rk], instr, seed, f"ria_v4/{iname}_{rk}_s{si}")
            pid = submit(worker, g)
            jobs.append((worker, pid, f"{iname}_{rk}_s{si}.png"))
    print(f"[v4gen] 已提交 {len(jobs)} 张候选 (跨 {len(WORKERS)} 台)", flush=True)

    ok = 0
    for worker, pid, name in jobs:
        if fetch(worker, pid, out / name):
            ok += 1
            print(f"[v4gen] ok {name}", flush=True)
        else:
            print(f"[v4gen] FAIL {name}", flush=True)
    print(f"[v4gen] DONE {ok}/{len(jobs)} -> {out}", flush=True)


if __name__ == "__main__":
    main()
