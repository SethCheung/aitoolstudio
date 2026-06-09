#!/usr/bin/env bash
set -euo pipefail

COMFYUI_DIR="${COMFYUI_DIR:-$HOME/ComfyUI}"
RESOURCE_MOUNT="${RESOURCE_MOUNT:-/mnt/nas_comfyui}"
RESOURCE_ROOT="${RESOURCE_ROOT:-${RESOURCE_MOUNT}/AI-Tool-Studio/comfyui}"
COMFYUI_PORT="${COMFYUI_PORT:-8188}"

echo "# ComfyUI worker snapshot"
echo "generated_at=$(date -Iseconds)"
echo "host=$(hostname -f 2>/dev/null || hostname)"
echo "user=$(id -un)"
echo "kernel=$(uname -srmo)"
echo

echo "## service"
if command -v systemctl >/dev/null 2>&1; then
  systemctl is-enabled comfyui.service 2>/dev/null | sed 's/^/enabled=/' || echo "enabled=unknown"
  systemctl is-active comfyui.service 2>/dev/null | sed 's/^/active=/' || echo "active=unknown"
else
  echo "systemctl=missing"
fi
echo

echo "## mount"
echo "resource_mount=$RESOURCE_MOUNT"
echo "resource_root=$RESOURCE_ROOT"
if command -v findmnt >/dev/null 2>&1; then
  findmnt "$RESOURCE_MOUNT" || true
else
  mount | grep " $RESOURCE_MOUNT " || true
fi
if [ -d "$RESOURCE_ROOT" ]; then
  echo "resource_root_exists=yes"
  ls -ld "$RESOURCE_ROOT" "$RESOURCE_ROOT/models" 2>/dev/null || true
  for model_dir in checkpoints loras vae clip text_encoders unet diffusion_models controlnet upscale_models clip_vision embeddings; do
    if [ -d "$RESOURCE_ROOT/models/$model_dir" ]; then
      count="$(find "$RESOURCE_ROOT/models/$model_dir" -mindepth 1 -maxdepth 2 -type f 2>/dev/null | wc -l | tr -d ' ')"
      echo "models/$model_dir files_depth2=$count"
    else
      echo "models/$model_dir missing"
    fi
  done
else
  echo "resource_root_exists=no"
fi
echo

echo "## comfyui"
echo "comfyui_dir=$COMFYUI_DIR"
if [ -d "$COMFYUI_DIR/.git" ]; then
  git -C "$COMFYUI_DIR" rev-parse --short HEAD | sed 's/^/commit=/'
  git -C "$COMFYUI_DIR" status --short | sed 's/^/status=/' || true
else
  echo "commit=unknown"
fi
echo

echo "## extra_model_paths"
for extra_paths_file in \
  "$COMFYUI_DIR/extra_model_paths.yaml" \
  "$COMFYUI_DIR/extra_model_paths.yml" \
  "$COMFYUI_DIR/extra_model_paths.yaml.example"
do
  if [ -f "$extra_paths_file" ]; then
    echo "file=$extra_paths_file"
    sed -n '1,220p' "$extra_paths_file"
  fi
done
if ! ls "$COMFYUI_DIR"/extra_model_paths.y* >/dev/null 2>&1; then
  echo "extra_model_paths=missing"
fi
echo

echo "## custom_nodes"
if [ -d "$COMFYUI_DIR/custom_nodes" ]; then
  find "$COMFYUI_DIR/custom_nodes" -mindepth 1 -maxdepth 1 -type d | sort | while read -r node_dir; do
    name="$(basename "$node_dir")"
    if [ -d "$node_dir/.git" ]; then
      commit="$(git -C "$node_dir" rev-parse --short HEAD 2>/dev/null || true)"
      dirty="$(git -C "$node_dir" status --short 2>/dev/null | wc -l | tr -d ' ')"
      echo "$name commit=${commit:-unknown} dirty=$dirty"
    else
      echo "$name commit=unknown dirty=unknown"
    fi
  done
else
  echo "custom_nodes=missing"
fi
echo

echo "## python"
if command -v python >/dev/null 2>&1; then
  python - <<'PY' || true
import sys
print("python=" + sys.version.replace("\n", " "))
try:
    import torch
    print("torch=" + getattr(torch, "__version__", "unknown"))
    print("cuda_available=" + str(torch.cuda.is_available()))
    if torch.cuda.is_available():
        print("cuda_device=" + torch.cuda.get_device_name(0))
except Exception as exc:
    print("torch_error=" + repr(exc))
PY
else
  echo "python=missing"
fi
echo

echo "## http"
if command -v curl >/dev/null 2>&1; then
  curl -fsS "http://127.0.0.1:${COMFYUI_PORT}/system_stats" >/dev/null \
    && echo "system_stats=ok" \
    || echo "system_stats=failed"
  if curl -fsS "http://127.0.0.1:${COMFYUI_PORT}/object_info" >/tmp/comfyui-object-info.json 2>/dev/null; then
    echo "object_info=ok"
    python - <<'PY' || true
import json
required = [
    "CheckpointLoaderSimple",
    "LoraLoaderModelOnly",
    "UNETLoader",
    "VAELoader",
    "CLIPLoader",
    "DualCLIPLoader",
]
try:
    with open("/tmp/comfyui-object-info.json", encoding="utf-8") as handle:
        data = json.load(handle)
except Exception as exc:
    print("object_info_parse_error=" + repr(exc))
else:
    print("object_info_class_count=" + str(len(data)))
    for name in required:
        print(f"loader_{name}={'present' if name in data else 'missing'}")
PY
  else
    echo "object_info=failed"
  fi
else
  echo "curl=missing"
fi
