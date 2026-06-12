#!/usr/bin/env python3
"""ArcFace 人脸一致性质检闸门。

用途：数字人模特批量出图后，对每张候选图计算与定妆参考照的人脸相似度，
低于阈值判打回，保证商业账号输出的一致性。

用法（在 197 的 face_qc_env 里跑）：
    ~/face_qc_env/bin/python face_qc.py \
        --ref /path/to/定妆照目录或单张图 \
        --candidates /path/to/候选图目录 \
        --threshold 0.45 \
        --report report.json \
        [--sort-into /path/to/输出目录]   # 可选：按 pass/fail 分拣副本

判定口径：
  - 取每张图中最大的人脸（模特图默认单人构图，多人脸会在报告里标注）
  - 相似度 = 与参考集质心 embedding 的余弦相似度
  - >= threshold 通过；检不到脸直接打回（reason=no_face）

阈值参考：同一身份通常 > 0.55，不同身份 < 0.30。商用一致性建议 0.45 起步，
跑过第一批真实数据后按分布回调。
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
DEFAULT_MODEL_ROOT = "/mnt/nas_comfyui/AI-Tool-Studio/comfyui/models/insightface"


def imread_unicode(path: Path):
    """cv2.imread 不认中文路径，统一走 imdecode。"""
    import cv2

    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def collect_images(target: Path):
    if target.is_file():
        return [target]
    return sorted(
        p for p in target.rglob("*") if p.suffix.lower() in IMAGE_EXTS and p.is_file()
    )


def largest_face(faces):
    def area(f):
        x1, y1, x2, y2 = f.bbox
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)

    return max(faces, key=area)


def build_app(model_root: str, gpu_id: int):
    from insightface.app import FaceAnalysis

    app = FaceAnalysis(
        name="buffalo_l",
        root=model_root,
        allowed_modules=["detection", "recognition"],
    )
    app.prepare(ctx_id=gpu_id, det_size=(640, 640))
    return app


def embed(app, path: Path):
    """返回 (embedding 或 None, 人脸数, 失败原因)。"""
    img = imread_unicode(path)
    if img is None:
        return None, 0, "unreadable"
    faces = app.get(img)
    if not faces:
        return None, 0, "no_face"
    face = largest_face(faces)
    emb = face.normed_embedding
    return emb, len(faces), None


def main():
    ap = argparse.ArgumentParser(description="ArcFace face consistency QC gate")
    ap.add_argument("--ref", required=True, help="定妆参考照：单张图或目录（取质心）")
    ap.add_argument("--candidates", required=True, help="候选图：单张图或目录")
    ap.add_argument("--threshold", type=float, default=0.45)
    ap.add_argument("--report", default="face_qc_report.json")
    ap.add_argument("--csv", default=None, help="可选：同时输出 CSV")
    ap.add_argument("--sort-into", default=None, help="可选：把候选图副本分拣进 pass/ fail/ 子目录")
    ap.add_argument("--model-root", default=DEFAULT_MODEL_ROOT)
    ap.add_argument("--gpu", type=int, default=0, help="GPU 序号，-1 用 CPU")
    args = ap.parse_args()

    t0 = time.time()
    app = build_app(args.model_root, args.gpu)

    ref_paths = collect_images(Path(args.ref))
    if not ref_paths:
        print(f"[face_qc] 参考目录里没有图片: {args.ref}", file=sys.stderr)
        sys.exit(2)

    ref_embs, ref_skipped = [], []
    for p in ref_paths:
        emb, n_faces, reason = embed(app, p)
        if emb is None:
            ref_skipped.append({"path": str(p), "reason": reason})
            continue
        ref_embs.append(emb)
    if not ref_embs:
        print("[face_qc] 所有参考照都检不到人脸，无法建立基准", file=sys.stderr)
        sys.exit(2)
    centroid = np.mean(np.stack(ref_embs), axis=0)
    centroid /= np.linalg.norm(centroid)

    cand_paths = collect_images(Path(args.candidates))
    if not cand_paths:
        print(f"[face_qc] 候选目录里没有图片: {args.candidates}", file=sys.stderr)
        sys.exit(2)

    results = []
    for p in cand_paths:
        emb, n_faces, reason = embed(app, p)
        if emb is None:
            results.append(
                {"path": str(p), "score": None, "faces": n_faces, "pass": False, "reason": reason}
            )
            continue
        score = float(np.dot(centroid, emb))
        results.append(
            {
                "path": str(p),
                "score": round(score, 4),
                "faces": n_faces,
                "pass": score >= args.threshold,
                "reason": None if score >= args.threshold else "below_threshold",
            }
        )

    if args.sort_into:
        out_root = Path(args.sort_into)
        for sub in ("pass", "fail"):
            (out_root / sub).mkdir(parents=True, exist_ok=True)
        for r in results:
            src = Path(r["path"])
            dest = out_root / ("pass" if r["pass"] else "fail") / src.name
            shutil.copy2(src, dest)

    scored = [r["score"] for r in results if r["score"] is not None]
    passed = sum(1 for r in results if r["pass"])
    report = {
        "threshold": args.threshold,
        "ref_images": len(ref_embs),
        "ref_skipped": ref_skipped,
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "score_mean": round(float(np.mean(scored)), 4) if scored else None,
        "score_min": round(float(np.min(scored)), 4) if scored else None,
        "score_max": round(float(np.max(scored)), 4) if scored else None,
        "elapsed_sec": round(time.time() - t0, 1),
        "results": results,
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2))

    if args.csv:
        import csv

        with open(args.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["path", "score", "faces", "pass", "reason"])
            w.writeheader()
            w.writerows(results)

    print(
        f"[face_qc] {passed}/{len(results)} 通过 (阈值 {args.threshold}, "
        f"均分 {report['score_mean']}, 用时 {report['elapsed_sec']}s) -> {args.report}"
    )


if __name__ == "__main__":
    main()
