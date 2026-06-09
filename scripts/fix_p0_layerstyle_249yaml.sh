#!/bin/bash
# AIToolStudio P0 修复脚本
# 在用户 macOS 终端执行(不是 Claude Code 里)
# 用法:
#   cd /Users/apple/Documents/GitHub/aitoolstudio
#   bash scripts/fix_p0_layerstyle_249yaml.sh
#
# 效果:
#   1. 在 195/197/249 三台 ComfyUI 装 ComfyUI_LayerStyle 自定义节点
#   2. 改 249 的 extra_model_paths.yaml 与 195/197 对齐
#   3. 重启三台 ComfyUI systemd 服务
#   4. 验证三台 /object_info 都包含 LayerUtility: SaveImagePlus
#   5. 验证 249 上 Z-Image 模型可见

set -e

CRED="sshpass -p Sjm744546 ssh -o StrictHostKeyChecking=no -o ConnectTimeout=8 -o PreferredAuthentications=password -o PubkeyAuthentication=no -o RequestTTY=no"

# ============================================================
# 1. 装 ComfyUI_LayerStyle 到 195/197/249
# ============================================================
echo "=========================================="
echo "STEP 1: Install ComfyUI_LayerStyle on 3 nodes"
echo "=========================================="
for IP in 195 197 249; do
  echo ""
  echo "--- 192.168.1.$IP ---"
  $CRED sjm@192.168.1.$IP bash -s <<'REMOTE'
set -e
cd ~/ComfyUI/custom_nodes
if [ -d ComfyUI_LayerStyle ]; then
  echo "  ComfyUI_LayerStyle already exists, pulling latest..."
  cd ComfyUI_LayerStyle
  git pull --rebase --autostash 2>&1 | tail -3 || true
else
  echo "  Cloning ComfyUI_LayerStyle..."
  git clone https://github.com/chflame163/ComfyUI_LayerStyle.git 2>&1 | tail -3
  cd ComfyUI_LayerStyle
  if [ -f requirements.txt ]; then
    echo "  Installing requirements..."
    pip install -r requirements.txt 2>&1 | tail -5 || pip3 install -r requirements.txt 2>&1 | tail -5
  fi
fi
echo "  Done."
REMOTE
done

# ============================================================
# 2. 改 249 的 extra_model_paths.yaml
# ============================================================
echo ""
echo "=========================================="
echo "STEP 2: Fix 249 extra_model_paths.yaml"
echo "=========================================="
echo "  Backing up 249's current yaml..."
$CRED sjm@192.168.1.249 'cp ~/ComfyUI/extra_model_paths.yaml ~/ComfyUI/extra_model_paths.yaml.bak.$(date +%Y%m%d_%H%M%S) && echo "  Backup created."'

echo "  Writing new yaml to 249..."
$CRED sjm@192.168.1.249 'cat > ~/ComfyUI/extra_model_paths.yaml <<YAML
aitoolstudio:
  base_path: /mnt/nas_comfyui/AI-Tool-Studio/comfyui
  is_default: true
  checkpoints: models/checkpoints
  loras: models/loras
  vae: models/vae
  clip: models/clip
  text_encoders: models/text_encoders
  unet: models/unet
  diffusion_models: models/diffusion_models
  controlnet: models/controlnet
  upscale_models: models/upscale_models
  clip_vision: models/clip_vision
  embeddings: models/embeddings
  latent_upscale_models: models/latent_upscale_models
  audio_encoders: models/audio_encoders
  audio_vae: models/audio_vae
  model_patches: models/model_patches
  configs: models/configs
  sams: models/sams
YAML
echo "  Wrote new yaml."'

echo ""
echo "  Verifying 249 yaml:"
$CRED sjm@192.168.1.249 'cat ~/ComfyUI/extra_model_paths.yaml | head -5'

echo ""
echo "  Verifying 195/197 yaml unchanged:"
$CRED sjm@192.168.1.195 'cat ~/ComfyUI/extra_model_paths.yaml | head -5'
$CRED sjm@192.168.1.197 'cat ~/ComfyUI/extra_model_paths.yaml | head -5'

# ============================================================
# 3. 重启三台 ComfyUI
# ============================================================
echo ""
echo "=========================================="
echo "STEP 3: Restart comfyui on 3 nodes"
echo "=========================================="
for IP in 195 197 249; do
  echo "  Restart 192.168.1.$IP..."
  $CRED sjm@192.168.1.$IP 'systemctl --user restart comfyui && sleep 2 && systemctl --user is-active comfyui'
done

# ============================================================
# 4. 验证 /object_info 包含 SaveImagePlus
# ============================================================
echo ""
echo "=========================================="
echo "STEP 4: Verify SaveImagePlus on 3 nodes"
echo "=========================================="
sleep 8  # 等 ComfyUI 启动
for IP in 195 197 249; do
  echo ""
  echo "--- 192.168.1.$IP ---"
  curl -sS --max-time 6 "http://192.168.1.$IP:8188/object_info" > /tmp/claude-501/${IP}_oi.json
  python3 -c "
import json
try:
    with open('/tmp/claude-501/${IP}_oi.json') as f:
        d = json.load(f)
    keys = list(d.keys())
    found = [k for k in keys if 'SaveImagePlus' in k or 'LayerUtility' in k]
    if found:
        print('  YES  SaveImagePlus present: ' + str(found))
    else:
        print('  NO   SaveImagePlus not found, class count = ' + str(len(keys)))
except Exception as e:
    print('  ERR  parse failed: ' + str(e))
"
done

# ============================================================
# 5. 验证 249 上 Z-Image 模型可见
# ============================================================
echo ""
echo "=========================================="
echo "STEP 5: Verify Z-Image model on 249"
echo "=========================================="
for IP in 195 197 249; do
  echo ""
  echo "--- 192.168.1.$IP ---"
  $CRED sjm@192.168.1.$IP 'ls -la /mnt/nas_comfyui/AI-Tool-Studio/comfyui/diffusion_models/ 2>/dev/null | grep -i z_image; ls -la /mnt/nas_comfyui/AI-Tool-Studio/comfyui/unet/ 2>/dev/null | grep -i z_image'
done

echo ""
echo "=========================================="
echo "DONE"
echo "=========================================="
echo ""
echo "All P0 fixes applied. Next: ask Claude Code to re-run the black-white-line workflow."
