# ComfyUI Worker Operations Baseline

This runbook turns the current three-node pool into something repeatable. The
target pool is:

- `192.168.1.195:8188`
- `192.168.1.197:8188`
- `192.168.1.249:8188`

The platform runs on `192.168.1.60` and keeps the canonical asset root on the
60 volume. Worker machines should be treated as compute nodes only.

## Current Acceptance Snapshot

The 60 deployment is expected to keep:

```env
COMFYUI_INSTANCES=192.168.1.195:8188,192.168.1.197:8188,192.168.1.249:8188
AITOOL_RESOURCE_ROOT=/vol3/@team/SJM-MediaFile/AI-Tool-Studio/comfyui
RESOURCE_ROOT=/vol3/@team/SJM-MediaFile/AI-Tool-Studio/comfyui
```

The `Z-Image-Enhance.json` workflow currently requires 20 ComfyUI node classes.
All three workers should report `missing=0` for that workflow.

## Pool Inventory

Run this from the platform repo on `192.168.1.60`:

```bash
python scripts/comfyui_pool_inventory.py \
  --workflow workflows/Z-Image-Enhance.json \
  --output data/comfyui-pool-inventory.json \
  --strict
```

Use this after every worker change:

- adding or removing a worker from `COMFYUI_INSTANCES`
- installing or updating custom nodes
- changing model mount paths
- changing a production workflow JSON

The JSON output is safe to archive as an operations snapshot. It records worker
availability, GPU names, ComfyUI object class counts, workflow compatibility,
and model dependency hits under the 60 resource root.

## Worker Snapshot

Run this on each ComfyUI worker:

```bash
COMFYUI_DIR=/path/to/ComfyUI \
RESOURCE_MOUNT=/mnt/nas_comfyui \
COMFYUI_PORT=8188 \
bash scripts/comfyui_worker_snapshot.sh
```

Archive the output whenever a node is added, rebuilt, or upgraded. It captures:

- service enable/active state
- resource mount state
- shared resource root and model subdirectory readability
- `extra_model_paths.yaml` content, when present
- ComfyUI git commit
- `custom_nodes` git commits and dirty status
- Python, Torch, CUDA, and local `/system_stats` reachability
- local `/object_info` class count and core loader presence

## Standard Mount

Use `/mnt/nas_comfyui` as the standard worker mount point for the 60 share root.
The ComfyUI resource root under that mount is:

```text
/mnt/nas_comfyui/AI-Tool-Studio/comfyui
```

If a machine currently uses another path, such as `/mnt/comfyui-models`, migrate
in two steps:

1. Mount the 60 resource volume at `/mnt/nas_comfyui`.
2. Update ComfyUI `extra_model_paths.yaml` to use `/mnt/nas_comfyui/AI-Tool-Studio/comfyui`.

If an immediate mount path change is too risky, keep a temporary compatibility symlink for the mount point only:

```bash
sudo ln -sfn /mnt/nas_comfyui /mnt/comfyui-models
```

Remove the symlink once all local ComfyUI configs use the standard mount and resource path. Do not create symlinks inside the shared `AI-Tool-Studio/comfyui` resource root.

Example `fstab` patterns:

```fstab
# NFS example
192.168.1.60:/vol3/@team/SJM-MediaFile /mnt/nas_comfyui nfs4 defaults,_netdev,nofail,x-systemd.automount 0 0

# SMB example
//192.168.1.60/SJM-MediaFile /mnt/nas_comfyui cifs credentials=/etc/samba/aitoolstudio-60.cred,iocharset=utf8,uid=comfyui,gid=comfyui,_netdev,nofail,x-systemd.automount 0 0
```

Use the protocol already proven on the existing workers. Do not switch SMB/NFS
just to normalize the path.

## Standard systemd Service

Create `/etc/systemd/system/comfyui.service` on each worker:

```ini
[Unit]
Description=ComfyUI Worker
After=network-online.target remote-fs.target
Wants=network-online.target
RequiresMountsFor=/mnt/nas_comfyui

[Service]
Type=simple
User=comfyui
Group=comfyui
WorkingDirectory=/opt/ComfyUI
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/ComfyUI/venv/bin/python main.py --listen 0.0.0.0 --port 8188
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Adjust `User`, `Group`, `WorkingDirectory`, and `ExecStart` to match the worker.
Then enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now comfyui.service
sudo systemctl status comfyui.service --no-pager
```

## Worker Acceptance Checklist

On the worker:

```bash
findmnt /mnt/nas_comfyui
ls -lah /mnt/nas_comfyui/AI-Tool-Studio/comfyui
systemctl is-enabled comfyui.service
systemctl is-active comfyui.service
curl -fsS http://127.0.0.1:8188/system_stats >/dev/null
```

From `192.168.1.60`:

```bash
python scripts/comfyui_pool_inventory.py \
  --workflow workflows/Z-Image-Enhance.json \
  --strict
```

Acceptance is:

- mount is active after reboot
- `comfyui.service` is enabled and active after reboot
- `COMFYUI_INSTANCES` contains the worker
- platform backend can reach `/system_stats` and `/object_info`
- production workflows report `missing=0`

If `/object_info` is reachable but `CheckpointLoaderSimple`, `LoraLoaderModelOnly`,
`UNETLoader`, `VAELoader`, `CLIPLoader`, or `DualCLIPLoader` are missing, treat it
as a model path configuration problem first. On that worker, verify
`extra_model_paths.yaml` points at `/mnt/nas_comfyui/AI-Tool-Studio/comfyui` and
that the mapped `models/` subdirectories are readable before reinstalling nodes.
