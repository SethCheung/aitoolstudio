#!/usr/bin/env python3
"""ria LoRA A/B 对比矩阵：各代 LoRA × 强度 × 场景，同种子出图，供 ArcFace 打分 + 肉眼对比。

目的：用客观数据定 v4 配方——
  1) 验证「降 LoRA 强度能否压住 AI 感」（v3 @ 1.0 vs 0.85 vs 0.7）
  2) 验证「合成数据是不是质感差的元凶」（纯真实数据的 v1/v2b vs 含 75% 合成的 v3）
  3) 暴露「换造型崩脸」（outfit 场景 = 域漂移压力测试）

跨 249/195 两台 4090 轮转提交。出图拉回本地 OUT，随后 face_qc.py 在 197 上打分。

用法：
    python3 scripts/ria_ab_matrix.py --out /tmp/ria_ab
"""
import argparse
import json
import urllib.request
import urllib.parse
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORKERS = ["192.168.1.249:8188", "192.168.1.195:8188"]
SEED = 612001

RIA = ("ria, a young woman with long platinum blonde wavy hair, half-up bun hairstyle, "
       "brown eyes, flower earrings")

# 场景：identity / texture / 崩脸压力测试
PROMPTS = [
    ("front", f"{RIA}, bare shoulders, closeup beauty portrait, white background, front view, looking at camera"),
    ("cafe", f"{RIA}, wearing a white t-shirt, sitting in a sunlit cafe, upper body shot, looking at camera, photorealistic, natural skin texture"),
    ("outfit", f"{RIA}, wearing an elegant red evening gown, standing on a city street at night, full upper body, looking at camera, photorealistic"),
]

# (LoRA 路径, 强度, 标签)  —— 标签用于文件名/打分对照
MATRIX = [
    ("digital_humans/ria_v3.safetensors", 1.0, "v3_s100"),
    ("digital_humans/ria_v3.safetensors", 0.85, "v3_s085"),
    ("digital_humans/ria_v3.safetensors", 0.70, "v3_s070"),
    ("digital_humans/ria_v3-000004.safetensors", 0.85, "v3e4_s085"),  # 中段 checkpoint，过拟合更轻
    ("digital_humans/ria_v2b.safetensors", 0.85, "v2b_s085"),         # 纯真实头部特写
    ("digital_humans/ria_v1.safetensors", 0.85, "v1_s085"),           # 纯真实 grid 基线
]


def build_graph(lora_name, strength, prompt_text):
    g = json.loads((REPO / "workflows/Qwen-Image-Casting.json").read_text())
    # 注入 LoraLoaderModelOnly（取自 1，喂给 4）
    g["11"] = {"inputs": {"lora_name": lora_name, "strength_model": strength, "model": ["1", 0]},
               "class_type": "LoraLoaderModelOnly"}
    g["4"]["inputs"]["model"] = ["11", 0]
    g["5"]["inputs"]["text"] = prompt_text
    g["8"]["inputs"]["seed"] = SEED
    g["10"]["inputs"]["filename_prefix"] = "ria_ab/ab"
    return g


def submit(worker, graph):
    req = urllib.request.Request(f"http://{worker}/prompt", data=json.dumps({"prompt": graph}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())["prompt_id"]


def fetch(worker, pid, dest, timeout_s=900):
    import time as _t
    t0 = _t.time()
    while _t.time() - t0 < timeout_s:
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
        _t.sleep(4)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/ria_ab")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    jobs = []  # (worker, pid, dest_name)
    i = 0
    for lora, strength, tag in MATRIX:
        for pname, ptext in PROMPTS:
            worker = WORKERS[i % len(WORKERS)]
            i += 1
            pid = submit(worker, build_graph(lora, strength, ptext))
            dest = f"{tag}__{pname}.png"
            jobs.append((worker, pid, dest))
            print(f"[ab] submit {dest} -> {worker} ({pid[:8]})", flush=True)

    ok = 0
    for worker, pid, dest in jobs:
        if fetch(worker, pid, out / dest):
            ok += 1
            print(f"[ab] ok {dest}", flush=True)
        else:
            print(f"[ab] FAIL {dest}", flush=True)
    print(f"[ab] DONE {ok}/{len(jobs)} -> {out}", flush=True)


if __name__ == "__main__":
    main()
