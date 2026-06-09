#!/usr/bin/env python3
"""Audit the configured ComfyUI worker pool.

The script intentionally uses only the Python standard library so it can run
from the 60 host, a developer laptop, or inside the platform container.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = ROOT_DIR / "API" / ".env"
DEFAULT_WORKFLOW_DIR = ROOT_DIR / "workflows"
MODEL_EXTENSIONS = (
    ".safetensors",
    ".ckpt",
    ".pt",
    ".pth",
    ".bin",
    ".gguf",
    ".onnx",
)


def load_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def split_instances(value: str) -> List[str]:
    instances: List[str] = []
    for item in value.split(","):
        cleaned = item.strip()
        if not cleaned:
            continue
        cleaned = cleaned.removeprefix("http://").removeprefix("https://").rstrip("/")
        if cleaned not in instances:
            instances.append(cleaned)
    return instances


def request_json(addr: str, path: str, timeout: float) -> Any:
    url = f"http://{addr}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "aitoolstudio-comfyui-inventory/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def iter_workflow_paths(values: Optional[Sequence[str]]) -> List[Path]:
    if values:
        paths = []
        for value in values:
            p = Path(value)
            if not p.is_absolute():
                p = ROOT_DIR / value
            paths.append(p)
        return paths
    if not DEFAULT_WORKFLOW_DIR.exists():
        return []
    return sorted(
        p
        for p in DEFAULT_WORKFLOW_DIR.rglob("*.json")
        if not p.name.endswith(".config.json")
    )


def walk_values(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        for child in value.values():
            yield from walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_values(child)
    else:
        yield value


def extract_model_names(workflow: Dict[str, Any]) -> List[str]:
    names: Set[str] = set()
    for value in walk_values(workflow):
        if not isinstance(value, str):
            continue
        lower = value.lower()
        if lower.endswith(MODEL_EXTENSIONS):
            normalized = value.replace("\\", "/").split("/")[-1]
            if normalized:
                names.add(normalized)
    return sorted(names)


def extract_class_types(workflow: Dict[str, Any]) -> List[str]:
    classes: Set[str] = set()
    for node in workflow.values():
        if isinstance(node, dict) and isinstance(node.get("class_type"), str):
            classes.add(node["class_type"])
    return sorted(classes)


def load_workflow(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON object")
    # Some exports wrap the API workflow in a top-level key.
    for key in ("workflow", "prompt"):
        wrapped = payload.get(key)
        if isinstance(wrapped, dict):
            payload = wrapped
            break
    if not extract_class_types(payload):
        raise ValueError(f"{path} does not look like ComfyUI API workflow JSON")
    return payload


def summarize_system_stats(stats: Dict[str, Any]) -> Dict[str, Any]:
    system = stats.get("system") if isinstance(stats.get("system"), dict) else {}
    devices = stats.get("devices") if isinstance(stats.get("devices"), list) else []
    return {
        "os": system.get("os"),
        "python_version": system.get("python_version"),
        "pytorch_version": system.get("pytorch_version"),
        "devices": [
            {
                "name": device.get("name"),
                "type": device.get("type"),
                "index": device.get("index"),
                "vram_total": device.get("vram_total"),
                "vram_free": device.get("vram_free"),
            }
            for device in devices
            if isinstance(device, dict)
        ],
    }


def inspect_instance(addr: str, timeout: float) -> Dict[str, Any]:
    item: Dict[str, Any] = {"address": addr, "online": False}
    try:
        stats = request_json(addr, "/system_stats", timeout)
        object_info = request_json(addr, "/object_info", timeout)
        item.update(
            {
                "online": True,
                "system": summarize_system_stats(stats if isinstance(stats, dict) else {}),
                "object_class_count": len(object_info) if isinstance(object_info, dict) else 0,
                "object_classes": sorted(object_info.keys()) if isinstance(object_info, dict) else [],
            }
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        item["error"] = str(exc)
    return item


def find_model_hits(resource_root: str, model_names: Sequence[str], max_depth: int) -> Dict[str, Dict[str, Any]]:
    result = {
        name: {"status": "not_checked", "path": ""}
        for name in model_names
    }
    if not resource_root:
        for name in result:
            result[name]["status"] = "unconfigured"
        return result

    root = Path(resource_root)
    if not root.exists():
        for name in result:
            result[name]["status"] = "root_missing"
        return result

    remaining = set(model_names)
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        try:
            depth = len(current_path.relative_to(root).parts)
        except ValueError:
            depth = 0
        if depth >= max_depth:
            dirs[:] = []
        for filename in files:
            if filename in remaining:
                result[filename] = {"status": "exists", "path": str(current_path / filename)}
                remaining.remove(filename)
                if not remaining:
                    return result
    for name in remaining:
        result[name]["status"] = "missing"
    return result


def workflow_record(path: Path) -> Dict[str, Any]:
    workflow = load_workflow(path)
    try:
        display_path = str(path.relative_to(ROOT_DIR))
    except ValueError:
        display_path = str(path)
    return {
        "path": display_path,
        "required_classes": extract_class_types(workflow),
        "model_dependencies": extract_model_names(workflow),
    }


def print_summary(manifest: Dict[str, Any]) -> None:
    print("ComfyUI pool inventory")
    print(f"generated_at: {manifest['generated_at']}")
    print(f"resource_root: {manifest.get('resource_root') or '(unconfigured)'}")
    print()
    print("instances:")
    for item in manifest["instances"]:
        if not item.get("online"):
            print(f"- {item['address']}: offline ({item.get('error', 'unknown error')})")
            continue
        devices = item.get("system", {}).get("devices") or []
        device_names = ", ".join(d.get("name") or "unknown" for d in devices) or "no device data"
        print(f"- {item['address']}: online, classes={item.get('object_class_count')}, devices={device_names}")
    print()
    print("workflows:")
    for wf in manifest["workflows"]:
        print(
            f"- {wf['path']}: classes={len(wf['required_classes'])}, "
            f"models={len(wf['model_dependencies'])}"
        )
        for compat in wf["compatibility"]:
            missing = compat.get("missing_classes") or []
            status = "ok" if not missing else f"missing={len(missing)}"
            print(f"  - {compat['address']}: {status}")
    if manifest.get("model_dependencies"):
        print()
        print("model dependencies:")
        for name, info in sorted(manifest["model_dependencies"].items()):
            suffix = f" -> {info['path']}" if info.get("path") else ""
            print(f"- {name}: {info['status']}{suffix}")


def build_manifest(args: argparse.Namespace) -> Dict[str, Any]:
    env_file = Path(args.env_file) if args.env_file else DEFAULT_ENV_FILE
    env_values = load_env_file(env_file)
    raw_instances = (
        args.instances
        or os.getenv("COMFYUI_INSTANCES")
        or env_values.get("COMFYUI_INSTANCES")
        or "127.0.0.1:8188"
    )
    instances = split_instances(raw_instances)
    resource_root = (
        args.resource_root
        or os.getenv("AITOOL_RESOURCE_ROOT")
        or os.getenv("RESOURCE_ROOT")
        or env_values.get("AITOOL_RESOURCE_ROOT")
        or env_values.get("RESOURCE_ROOT")
        or ""
    )

    instance_records = [inspect_instance(addr, args.timeout) for addr in instances]
    workflow_records = [workflow_record(path) for path in iter_workflow_paths(args.workflow)]
    all_models = sorted({name for wf in workflow_records for name in wf["model_dependencies"]})
    model_hits = (
        {name: {"status": "skipped", "path": ""} for name in all_models}
        if args.skip_model_search
        else find_model_hits(resource_root, all_models, args.model_search_depth)
    )

    class_sets = {
        item["address"]: set(item.get("object_classes") or [])
        for item in instance_records
        if item.get("online")
    }
    for wf in workflow_records:
        required = set(wf["required_classes"])
        wf["compatibility"] = []
        for addr in instances:
            available = class_sets.get(addr)
            missing = sorted(required - available) if available is not None else list(wf["required_classes"])
            wf["compatibility"].append(
                {
                    "address": addr,
                    "missing_count": len(missing),
                    "missing_classes": missing,
                }
            )

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "env_file": str(env_file),
        "resource_root": resource_root,
        "instances": [
            {k: v for k, v in item.items() if k != "object_classes"}
            for item in instance_records
        ],
        "workflows": workflow_records,
        "model_dependencies": model_hits,
    }


def has_strict_issue(manifest: Dict[str, Any]) -> bool:
    if any(not item.get("online") for item in manifest["instances"]):
        return True
    for wf in manifest["workflows"]:
        if any(item.get("missing_count", 0) > 0 for item in wf["compatibility"]):
            return True
    return False


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit ComfyUI worker pool compatibility.")
    parser.add_argument("--instances", help="Comma-separated host:port list. Defaults to COMFYUI_INSTANCES.")
    parser.add_argument("--env-file", help="Env file to read. Defaults to API/.env.")
    parser.add_argument("--resource-root", help="60 resource root. Defaults to AITOOL_RESOURCE_ROOT/RESOURCE_ROOT.")
    parser.add_argument("--workflow", action="append", help="Workflow JSON path. May be repeated.")
    parser.add_argument("--timeout", type=float, default=5.0, help="HTTP timeout per ComfyUI request.")
    parser.add_argument("--output", help="Write full JSON manifest to this path.")
    parser.add_argument("--skip-model-search", action="store_true", help="Do not walk the resource root for models.")
    parser.add_argument("--model-search-depth", type=int, default=8, help="Maximum directory depth for model search.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if an instance is offline or lacks classes.")
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    manifest = build_manifest(args)
    print_summary(manifest)
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = ROOT_DIR / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print()
        print(f"wrote: {output}")
    if args.strict and has_strict_issue(manifest):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
