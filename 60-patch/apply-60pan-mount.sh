#!/bin/bash
# 给 60 的 xy-canvas 容器挂载 60 盘资源根（/vol3/.../AI-Tool-Studio/comfyui），
# 之后平台才能做模型命中检测（AITOOL_RESOURCE_ROOT）。
# 用法：bash ~/Documents/GitHub/aitoolstudio/60-patch/apply-60pan-mount.sh
# 会提示输入两次密码（ssh + sudo），均为 sethchang 的密码
set -e

HOST="sethchang@192.168.1.60"

ssh -t "$HOST" '
  set -e
  COMPOSE=/opt/xy-canvas/docker-compose.60.yml
  MOUNT_LINE="      - /vol3/@team/SJM-MediaFile/AI-Tool-Studio/comfyui:/vol3/@team/SJM-MediaFile/AI-Tool-Studio/comfyui"

  echo "== 0/4 前置检查 =="
  if [ ! -f "$COMPOSE" ]; then echo "!! 找不到 $COMPOSE，停止"; exit 1; fi
  if ! sudo test -d /vol3/@team/SJM-MediaFile/AI-Tool-Studio/comfyui; then
    echo "!! 60 盘路径 /vol3/@team/SJM-MediaFile/AI-Tool-Studio/comfyui 不存在，停止"; exit 1
  fi
  if sudo grep -qF "AI-Tool-Studio/comfyui:/vol3" "$COMPOSE"; then
    echo "== 资源根挂载已存在，跳过修改，仅确认容器状态 =="
  else
    echo "== 1/4 备份 compose =="
    TS=$(date +%Y%m%d-%H%M%S)
    sudo cp -a "$COMPOSE" "$COMPOSE.bak.$TS"
    echo "已备份到 $COMPOSE.bak.$TS"

    echo "== 2/4 在 volumes 里加入资源根挂载 =="
    # 在 workflows/shared 挂载行后面插入（该行是 volumes 列表的最后一项）
    sudo sed -i "\#workflows/shared:ro#a\\
$MOUNT_LINE" "$COMPOSE"
    echo "---- 修改后的 volumes ----"
    sudo grep -A2 -B8 "AI-Tool-Studio/comfyui:/vol3" "$COMPOSE" || true
  fi

  echo "== 3/4 重建容器（应用新挂载）=="
  cd /opt/xy-canvas
  sudo docker compose -f docker-compose.60.yml up -d 2>/dev/null || sudo docker-compose -f docker-compose.60.yml up -d

  echo "== 4/4 验证容器内可见 60 盘 =="
  sleep 5
  sudo docker exec xy-canvas ls /vol3/@team/SJM-MediaFile/AI-Tool-Studio/comfyui | head -10
  echo "== 完成。容器启动约需 1-2 分钟（要重装 pip 依赖），之后让 Claude 配置 AITOOL_RESOURCE_ROOT =="
'
