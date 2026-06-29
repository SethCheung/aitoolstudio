#!/usr/bin/env python3
"""把 ria_ab_matrix 的产出拼成带标签 + ArcFace 分的对比图（每个场景一行 6 配置）。

用 /tmp/ria-venv/bin/python 跑（带 Pillow）。
    /tmp/ria-venv/bin/python scripts/ria_contact_sheet.py --dir /tmp/ria_ab [--scores /tmp/ria_ab/scores.json]
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# 列顺序（配置）与场景
TAGS = ["v3_s100", "v3_s085", "v3_s070", "v3e4_s085", "v2b_s085", "v1_s085"]
SCENES = ["front", "cafe", "outfit"]
CELL_W = 360
LABEL_H = 44


def load_font(size):
    for p in ["/System/Library/Fonts/Supplemental/Arial.ttf",
              "/System/Library/Fonts/Helvetica.ttc",
              "/Library/Fonts/Arial.ttf"]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/tmp/ria_ab")
    ap.add_argument("--scores", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    d = Path(args.dir)

    scores = {}
    if args.scores and Path(args.scores).exists():
        rep = json.loads(Path(args.scores).read_text())
        for r in rep.get("results", []):
            scores[Path(r["path"]).name] = r.get("score")

    font = load_font(20)
    sheets = []
    for scene in SCENES:
        cells = []
        for tag in TAGS:
            fn = f"{tag}__{scene}.png"
            p = d / fn
            if not p.exists():
                continue
            im = Image.open(p).convert("RGB")
            ratio = CELL_W / im.width
            im = im.resize((CELL_W, int(im.height * ratio)))
            sc = scores.get(fn)
            label = f"{tag}" + (f"  AF={sc:.3f}" if isinstance(sc, (int, float)) else "")
            canvas = Image.new("RGB", (CELL_W, im.height + LABEL_H), (20, 20, 24))
            ImageDraw.Draw(canvas).text((8, 10), label, fill=(255, 255, 255), font=font)
            canvas.paste(im, (0, LABEL_H))
            cells.append(canvas)
        if not cells:
            continue
        h = max(c.height for c in cells)
        row = Image.new("RGB", (CELL_W * len(cells), h), (20, 20, 24))
        for i, c in enumerate(cells):
            row.paste(c, (i * CELL_W, 0))
        # 场景标题条
        titled = Image.new("RGB", (row.width, h + 36), (10, 10, 12))
        ImageDraw.Draw(titled).text((10, 8), f"SCENE: {scene}", fill=(120, 220, 255), font=font)
        titled.paste(row, (0, 36))
        out = d / f"sheet_{scene}.png"
        titled.save(out)
        sheets.append(out)
        print(f"[sheet] {out}")

    # 总图：三行竖叠
    if sheets:
        imgs = [Image.open(s) for s in sheets]
        W = max(i.width for i in imgs)
        H = sum(i.height for i in imgs) + 8 * (len(imgs) - 1)
        big = Image.new("RGB", (W, H), (0, 0, 0))
        y = 0
        for im in imgs:
            big.paste(im, (0, y))
            y += im.height + 8
        outbig = Path(args.out) if args.out else d / "sheet_all.png"
        big.save(outbig)
        print(f"[sheet] ALL -> {outbig}")


if __name__ == "__main__":
    main()
