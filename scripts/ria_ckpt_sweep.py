#!/usr/bin/env python3
"""ria LoRA checkpoint 扫描：每个 checkpoint 用同种子出测试图，供质检对比挑选。

用法（在 Mac 或任一能访问 worker 的机器上）：
    python3 scripts/ria_ckpt_sweep.py --worker 192.168.1.249:8188 \
        --loras digital_humans/ria_v2b-000003.safetensors digital_humans/ria_v2b.safetensors \
        --out /tmp/ria_sweep
"""
import argparse
import json
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RIA = ("ria, a young woman with long platinum blonde wavy hair, half-up bun hairstyle, "
       "brown eyes, flower earrings")
PROMPTS = [
    ("front", f"{RIA}, bare shoulders, closeup beauty portrait, white background, front view, looking at camera"),
    ("cafe", f"{RIA}, wearing a white t-shirt, sitting in a sunlit cafe, upper body shot, looking at camera, photorealistic"),
]


def submit(worker, graph):
    req = urllib.request.Request(f"http://{worker}/prompt", data=json.dumps({"prompt": graph}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())["prompt_id"]


def wait_fetch(worker, pid, dest, timeout_s=600):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        h = json.loads(urllib.request.urlopen(f"http://{worker}/history/{pid}", timeout=15).read())
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("completed"):
                img = next(iter(h[pid]["outputs"].values()))["images"][0]
                url = (f"http://{worker}/view?filename={urllib.request.quote(img['filename'])}"
                       f"&subfolder={urllib.request.quote(img.get('subfolder', ''))}&type=output")
                urllib.request.urlretrieve(url, dest)
                return True
            if st.get("status_str") == "error":
                print(f"  EXEC-ERROR {dest.name}", flush=True)
                return False
        time.sleep(5)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", required=True)
    ap.add_argument("--loras", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=612001)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    base = json.loads((REPO / "workflows/Qwen-Image-Casting.json").read_text())
    base["11"] = {"inputs": {"lora_name": "", "strength_model": 1.0, "model": ["1", 0]},
                  "class_type": "LoraLoaderModelOnly"}
    base["4"]["inputs"]["model"] = ["11", 0]

    jobs = []
    for lora in args.loras:
        tag = Path(lora).stem.replace("ria_", "")
        for pname, ptext in PROMPTS:
            g = json.loads(json.dumps(base))
            g["11"]["inputs"]["lora_name"] = lora
            g["5"]["inputs"]["text"] = ptext
            g["8"]["inputs"]["seed"] = args.seed
            g["10"]["inputs"]["filename_prefix"] = f"ria_sweep/{tag}_{pname}"
            jobs.append((f"{tag}_{pname}.png", submit(args.worker, g)))
    print(f"[sweep] 已提交 {len(jobs)} 张", flush=True)
    ok = 0
    for name, pid in jobs:
        if wait_fetch(args.worker, pid, out / name):
            ok += 1
            print(f"[sweep] {name} ok", flush=True)
    print(f"[sweep] DONE {ok}/{len(jobs)} -> {out}", flush=True)


if __name__ == "__main__":
    main()
