#!/usr/bin/env python3
"""ria_v4 验收：扫所有 checkpoint × 场景，同种子出图 + ArcFace 打分，找甜点 epoch 并 A/B vs v3。

alpha 修对后甜点通常在中段（非最后一个 epoch），所以要逐 epoch 扫。

在 Mac 跑（用 249 出图——195 在训练；197 打分）。
    python3 scripts/ria_v4_verify.py --out /tmp/ria_v4_verify
"""
import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORKERS = ["192.168.1.249:8188", "192.168.1.195:8188"]
SEED = 612001
RIA = "ria"  # 触发词；v4 打标已不含发色/眼睛，靠 token 还原身份

PROMPTS = [
    ("front", f"{RIA}, bare shoulders, closeup beauty portrait, white background, front view, looking at camera"),
    ("cafe", f"{RIA}, wearing a white t-shirt, sitting in a sunlit cafe, upper body, looking at camera, photorealistic, natural skin texture"),
    ("outfit", f"{RIA}, wearing an elegant red evening gown, standing on a city street at night, upper body, looking at camera, photorealistic"),
]


def build_graph(lora_name, prompt_text):
    g = json.loads((REPO / "workflows/Qwen-Image-Casting.json").read_text())
    g["11"] = {"inputs": {"lora_name": lora_name, "strength_model": 1.0, "model": ["1", 0]},
               "class_type": "LoraLoaderModelOnly"}
    g["4"]["inputs"]["model"] = ["11", 0]
    g["5"]["inputs"]["text"] = prompt_text
    g["8"]["inputs"]["seed"] = SEED
    g["10"]["inputs"]["filename_prefix"] = "ria_v4_verify/v"
    return g


def submit(worker, graph):
    req = urllib.request.Request(f"http://{worker}/prompt", data=json.dumps({"prompt": graph}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())["prompt_id"]


def fetch(worker, pid, dest, timeout_s=900):
    import time
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


def discover_v4_loras():
    """SSH 列出 NAS 上的 v4 checkpoint（含 v3 最终作基线）。"""
    import subprocess
    out = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=12", "sjm@192.168.1.249",
         "ls /mnt/nas_comfyui/AI-Tool-Studio/comfyui/models/loras/digital_humans/ | "
         "grep -E 'ria_v4|ria_v3\\.safetensors'"],
        capture_output=True, text=True)
    names = [n.strip() for n in out.stdout.splitlines() if n.strip()]
    return [f"digital_humans/{n}" for n in names]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/ria_v4_verify")
    ap.add_argument("--loras", nargs="*", help="覆盖：显式给 LoRA 列表")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    loras = args.loras or discover_v4_loras()
    print(f"[verify] LoRA: {len(loras)} 个")
    for l in loras:
        print(f"   {l}")

    jobs = []
    i = 0
    for lora in loras:
        tag = Path(lora).stem.replace("ria_", "")
        for pname, ptext in PROMPTS:
            worker = WORKERS[i % len(WORKERS)]
            i += 1
            pid = submit(worker, build_graph(lora, ptext))
            jobs.append((f"{tag}__{pname}.png", worker, pid))
    print(f"[verify] 已提交 {len(jobs)} 张 -> {len(WORKERS)} 台", flush=True)
    ok = 0
    for name, worker, pid in jobs:
        if fetch(worker, pid, out / name):
            ok += 1
            print(f"[verify] ok {name}", flush=True)
        else:
            print(f"[verify] FAIL {name}", flush=True)
    print(f"[verify] DONE {ok}/{len(jobs)} -> {out}", flush=True)


if __name__ == "__main__":
    main()
