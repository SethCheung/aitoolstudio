#!/bin/bash
# 把 60-patch 部署到 192.168.1.60 的 /opt/xy-canvas（xy-canvas 容器）
# 用法：bash ~/Documents/GitHub/aitoolstudio/60-patch/deploy-from-mac.sh
# 会提示输入两次密码（ssh + sudo），均为 sethchang 的密码
set -e

SRC="$HOME/Documents/GitHub/aitoolstudio/60-patch"
HOST="sethchang@192.168.1.60"

echo "== 1/2 上传补丁到 60 临时目录 =="
rsync -av --exclude deploy-from-mac.sh "$SRC/" "$HOST:/tmp/xy-canvas-patch/"

echo "== 2/2 在 60 上备份、应用、重启容器 =="
ssh -t "$HOST" '
  set -e
  # 安全检查：确认运行容器挂载的就是 /opt/xy-canvas
  MNT=$(sudo docker inspect xy-canvas --format "{{range .Mounts}}{{if eq .Destination \"/app\"}}{{.Source}}{{end}}{{end}}")
  echo "容器 /app 挂载: $MNT"
  if [ "$MNT" != "/opt/xy-canvas" ]; then
    echo "!! 容器挂载的不是 /opt/xy-canvas，停止部署。请把这行输出发给 Claude。"
    exit 1
  fi
  TS=$(date +%Y%m%d-%H%M%S)
  BK=/opt/xy-canvas/backups/claude-patch-$TS
  sudo mkdir -p "$BK"
  sudo cp -a /opt/xy-canvas/main.py "$BK/main.py"
  sudo cp -a /opt/xy-canvas/static/login.html "$BK/login.html"
  echo "已备份到 $BK"
  sudo rsync -av /tmp/xy-canvas-patch/ /opt/xy-canvas/
  sudo chmod -R a+rX /opt/xy-canvas/static
  sudo chmod a+r /opt/xy-canvas/main.py
  sudo docker restart xy-canvas
  rm -rf /tmp/xy-canvas-patch
  echo "== 部署完成，容器重启中（约 1-2 分钟后生效）=="
'
