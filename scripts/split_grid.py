#!/usr/bin/env python3
"""把多宫格拼图素材切成单张训练图。

数字人定妆/多角度素材常以 2x3、3x2 网格交付，训练数据集需要单张。
等分切割并丢弃过小的格子。在 197 的 face_qc_env 下运行（需要 cv2+numpy）。

用法：
    ~/face_qc_env/bin/python split_grid.py --rows 2 --cols 3 \
        --input grids目录或单张图 --output 输出目录 [--prefix meimei]
"""

import argparse
from pathlib import Path

import cv2
import numpy as np

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def imread_unicode(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def main():
    ap = argparse.ArgumentParser(description="split grid images into singles")
    ap.add_argument("--rows", type=int, required=True)
    ap.add_argument("--cols", type=int, required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--prefix", default="cell")
    ap.add_argument("--min-side", type=int, default=512, help="切出格子的最短边低于此值则告警")
    args = ap.parse_args()

    src = Path(args.input)
    paths = [src] if src.is_file() else sorted(
        p for p in src.iterdir() if p.suffix.lower() in IMAGE_EXTS
    )
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    count = 0
    for gi, p in enumerate(paths):
        img = imread_unicode(p)
        if img is None:
            print(f"[split] 跳过不可读: {p}")
            continue
        h, w = img.shape[:2]
        ch, cw = h // args.rows, w // args.cols
        if min(ch, cw) < args.min_side:
            print(f"[split] 警告: {p.name} 切出格子仅 {cw}x{ch}，分辨率偏低")
        for r in range(args.rows):
            for c in range(args.cols):
                cell = img[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw]
                dest = out / f"{args.prefix}_g{gi:02d}_r{r}c{c}.png"
                cv2.imencode(".png", cell)[1].tofile(str(dest))
                count += 1
    print(f"[split] {len(paths)} 张网格 -> {count} 张单图 -> {out}")


if __name__ == "__main__":
    main()
