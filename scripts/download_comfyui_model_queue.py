#!/usr/bin/env python3
"""Download vetted ComfyUI model URLs into a shared resource root.

Queue items are JSON objects with:
  filename, source_url, target_relative_path

Set allow_rename=true only for manually vetted aliases where the source
file name differs from the workflow's expected file name.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ALLOWED_EXTENSIONS = {
    ".safetensors",
    ".ckpt",
    ".pt",
    ".pth",
    ".bin",
    ".gguf",
    ".onnx",
}


def log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def safe_join(root: Path, relative_path: str) -> Path:
    clean = str(relative_path or "").strip().lstrip("/\\")
    if not clean:
        raise ValueError("empty target_relative_path")
    target = (root / clean).resolve()
    root_resolved = root.resolve()
    if os.path.commonpath([str(root_resolved), str(target)]) != str(root_resolved):
        raise ValueError(f"target path escapes resource root: {relative_path}")
    return target


def validate_item(item: dict) -> tuple[str, str, str]:
    filename = os.path.basename(str(item.get("filename") or "").strip())
    source_url = str(item.get("source_url") or item.get("url") or "").strip()
    target_relative_path = str(item.get("target_relative_path") or "").strip()
    allow_rename = bool(item.get("allow_rename"))
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"invalid URL for {filename or target_relative_path}")
    url_filename = os.path.basename(unquote(parsed.path or ""))
    if not os.path.splitext(url_filename.lower())[1]:
        query = parse_qs(parsed.query or "")
        for key in ("name", "filename"):
            if query.get(key):
                url_filename = os.path.basename(unquote(query[key][0]))
                break
    suffix = os.path.splitext(url_filename.lower())[1]
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(f"unsupported URL extension: {source_url}")
    target_filename = os.path.basename(target_relative_path)
    target_suffix = os.path.splitext(target_filename.lower())[1]
    if target_suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(f"unsupported target extension: {target_relative_path}")
    if filename and url_filename != filename and not allow_rename:
        raise ValueError(f"URL filename mismatch: {filename} != {url_filename}")
    if filename and target_filename != filename:
        raise ValueError(f"target filename mismatch: {filename} != {target_filename}")
    return filename or url_filename, source_url, target_relative_path


def looks_like_html(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(256).lstrip().lower()
        return head.startswith(b"<!doctype html") or head.startswith(b"<html")
    except OSError:
        return False


def download_one(root: Path, item: dict, retry: int) -> str:
    filename, source_url, target_relative_path = validate_item(item)
    target = safe_join(root, target_relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 0:
        return f"skip exists {target_relative_path}"

    cache_dir = root / "downloads" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    part = cache_dir / f"{target.name}.part"

    cmd = [
        "curl",
        "-L",
        "--fail",
        "--retry",
        str(retry),
        "--retry-delay",
        "5",
        "--connect-timeout",
        "30",
        "-C",
        "-",
        "-o",
        str(part),
        source_url,
    ]
    log(f"download {filename} -> {target_relative_path}")
    subprocess.run(cmd, check=True)
    if not part.exists() or part.stat().st_size <= 1024:
        raise RuntimeError(f"downloaded file is too small: {filename}")
    if looks_like_html(part):
        raise RuntimeError(f"download appears to be an HTML page, not a model: {filename}")
    os.replace(part, target)
    return f"done {target_relative_path} ({target.stat().st_size} bytes)"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Download a vetted ComfyUI model queue.")
    parser.add_argument("--queue", required=True, help="JSON queue path")
    parser.add_argument("--resource-root", required=True, help="ComfyUI shared resource root")
    parser.add_argument("--retry", type=int, default=5)
    args = parser.parse_args(argv)

    queue_path = Path(args.queue)
    root = Path(args.resource_root)
    items = json.loads(queue_path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError("queue JSON must be a list")

    failures = []
    for index, item in enumerate(items, 1):
        try:
            result = download_one(root, item, args.retry)
            log(f"[{index}/{len(items)}] {result}")
        except Exception as exc:
            failures.append({"index": index, "filename": item.get("filename"), "error": str(exc)})
            log(f"[{index}/{len(items)}] failed {item.get('filename')}: {exc}")

    if failures:
        fail_path = queue_path.with_suffix(".failures.json")
        fail_path.write_text(json.dumps(failures, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        log(f"failures: {len(failures)} -> {fail_path}")
        return 2
    log("all downloads completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
