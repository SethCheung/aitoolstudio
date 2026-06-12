#!/usr/bin/env python3
"""定妆 prompt 矩阵批量出图：把候选脸的 prompt 组合 × 种子批量提交到 ComfyUI。

配合 workflows/Qwen-Image-Casting.json 使用。每个组合的产出图带组合编号前缀，
落在 worker 的 output/casting/ 下，方便后续 face_qc.py 质检和人工挑选。

用法：
    python3 scripts/casting_matrix.py --spec casting_spec.json \
        --instance 192.168.1.249:8188 [--seeds 4] [--dry-run]

spec 文件格式（JSON）：
{
  "template": "studio portrait photo of a {age} chinese woman, {face}, {style}, looking at camera, plain background, soft light",
  "axes": {
    "age": ["22 year old", "26 year old"],
    "face": ["oval face, almond eyes", "round face, gentle smile"],
    "style": ["fashion model look", "girl next door look"]
  },
  "negative": "lowres, bad anatomy, bad hands, blurry, watermark, text",
  "width": 1140,
  "height": 1472,
  "steps": 20
}
axes 做笛卡尔积，每个组合跑 --seeds 个种子。
"""

import argparse
import itertools
import json
import random
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = REPO_ROOT / "workflows" / "Qwen-Image-Casting.json"

PROMPT_NODE = "5"
NEGATIVE_NODE = "6"
LATENT_NODE = "7"
SAMPLER_NODE = "8"
SAVE_NODE = "10"


def post_prompt(instance: str, graph: dict) -> str:
    req = urllib.request.Request(
        f"http://{instance}/prompt",
        data=json.dumps({"prompt": graph}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["prompt_id"]


def queue_depth(instance: str) -> int:
    with urllib.request.urlopen(f"http://{instance}/queue", timeout=10) as resp:
        q = json.loads(resp.read())
    return len(q.get("queue_running", [])) + len(q.get("queue_pending", []))


def main():
    ap = argparse.ArgumentParser(description="casting prompt matrix batch submit")
    ap.add_argument("--spec", required=True, help="prompt 矩阵 spec JSON")
    ap.add_argument("--instance", required=True, help="ComfyUI worker, 如 192.168.1.249:8188")
    ap.add_argument("--seeds", type=int, default=4, help="每个组合跑几个种子")
    ap.add_argument("--seed-base", type=int, default=None, help="固定起始种子（默认随机）")
    ap.add_argument("--workflow", default=str(WORKFLOW_PATH))
    ap.add_argument("--max-queue", type=int, default=200, help="队列超过此深度则暂停提交")
    ap.add_argument("--dry-run", action="store_true", help="只打印组合，不提交")
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text())
    base_graph = json.loads(Path(args.workflow).read_text())

    axes = spec.get("axes", {})
    keys = list(axes.keys())
    combos = list(itertools.product(*(axes[k] for k in keys))) if keys else [()]
    seed_base = args.seed_base if args.seed_base is not None else random.randint(1, 2**40)

    total = len(combos) * args.seeds
    print(f"[casting] {len(combos)} 个组合 × {args.seeds} 种子 = {total} 张")

    manifest = []
    submitted = 0
    for ci, combo in enumerate(combos):
        values = dict(zip(keys, combo))
        prompt = spec["template"].format(**values)
        combo_id = f"c{ci:03d}"
        for si in range(args.seeds):
            seed = seed_base + ci * 1000 + si
            graph = json.loads(json.dumps(base_graph))
            graph[PROMPT_NODE]["inputs"]["text"] = prompt
            if spec.get("negative") is not None:
                graph[NEGATIVE_NODE]["inputs"]["text"] = spec["negative"]
            for dim in ("width", "height"):
                if spec.get(dim):
                    graph[LATENT_NODE]["inputs"][dim] = spec[dim]
            if spec.get("steps"):
                graph[SAMPLER_NODE]["inputs"]["steps"] = spec["steps"]
            graph[SAMPLER_NODE]["inputs"]["seed"] = seed
            graph[SAVE_NODE]["inputs"]["filename_prefix"] = f"casting/{combo_id}_s{si}"

            if args.dry_run:
                if si == 0:
                    print(f"  {combo_id}: {prompt}")
                continue

            while queue_depth(args.instance) >= args.max_queue:
                time.sleep(10)
            pid = post_prompt(args.instance, graph)
            submitted += 1
            manifest.append(
                {"combo": combo_id, "values": values, "seed": seed, "prompt_id": pid, "prompt": prompt}
            )

    if args.dry_run:
        return
    out = Path(args.spec).with_suffix(".manifest.json")
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"[casting] 已提交 {submitted}/{total} 到 {args.instance}，清单 -> {out}")
    print("[casting] 产出图在 worker 的 ComfyUI/output/casting/ 下，按组合编号命名")


if __name__ == "__main__":
    main()
