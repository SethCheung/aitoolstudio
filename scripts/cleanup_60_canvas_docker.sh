#!/usr/bin/env bash
set -euo pipefail

APPLY=0
if [ "${1:-}" = "--apply" ]; then
  APPLY=1
fi

PROJECT_DIR="${PROJECT_DIR:-/opt/aitoolstudio-canvas}"
SHARE_BACKUP_ROOT="${SHARE_BACKUP_ROOT:-/vol3/@team/SJM-MediaFile/AI-Tool-Studio/backups}"
NEW_CONTAINER_NAME="${NEW_CONTAINER_NAME:-aitoolstudio-canvas}"
LEGACY_DB="${LEGACY_DB:-}"
LEGACY_CONTAINERS="${LEGACY_CONTAINERS:-}"
TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$SHARE_BACKUP_ROOT/canvas-cleanup-$TS"

echo "mode: $([ "$APPLY" -eq 1 ] && echo apply || echo dry-run)"
echo "project: $PROJECT_DIR"
echo "backup: $BACKUP_DIR"
echo

if [ ! -d "$PROJECT_DIR" ]; then
  echo "ERROR: PROJECT_DIR 不存在：$PROJECT_DIR" >&2
  exit 1
fi

cd "$PROJECT_DIR"

echo "== Current docker containers =="
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}' || true
echo

echo "== Candidate legacy ports =="
docker ps -a --format '{{.Names}}\t{{.Ports}}' \
  | awk 'BEGIN{FS="\t"} $2 ~ /(5173|8000|8080)/ {print "candidate:", $0}' || true
echo

if [ "$APPLY" -ne 1 ]; then
  echo "DRY-RUN only. No backup, migration, stop, or remove was performed."
  echo
  echo "To apply, run for example:"
  echo "LEGACY_DB=/path/to/legacy.db \\"
  echo "LEGACY_CONTAINERS=\"old_frontend old_backend tapnow\" \\"
  echo "bash scripts/cleanup_60_canvas_docker.sh --apply"
  exit 0
fi

mkdir -p "$BACKUP_DIR"
cp -a data/auth.db "$BACKUP_DIR/auth.db.before-cleanup" 2>/dev/null || true
cp -a API/.env "$BACKUP_DIR/API.env.before-cleanup" 2>/dev/null || true
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}' > "$BACKUP_DIR/docker-ps-before.txt" || true
docker compose -f docker-compose.60.yml ps > "$BACKUP_DIR/new-compose-ps-before.txt" 2>&1 || true

if [ -n "$LEGACY_DB" ]; then
  if [ ! -f "$LEGACY_DB" ]; then
    echo "ERROR: LEGACY_DB 不存在：$LEGACY_DB" >&2
    exit 1
  fi
  cp -a "$LEGACY_DB" "$BACKUP_DIR/legacy.db"
  python scripts/import_legacy_users.py --source "$LEGACY_DB" --target data/auth.db
else
  echo "WARN: LEGACY_DB 未设置，跳过用户迁移。"
fi

if [ -z "$LEGACY_CONTAINERS" ]; then
  echo "ERROR: LEGACY_CONTAINERS 未设置；为避免误删，脚本不会自动猜测容器名。" >&2
  echo "请先 dry-run 查看候选容器，再设置 LEGACY_CONTAINERS 后重试。" >&2
  exit 1
fi

for name in $LEGACY_CONTAINERS; do
  if [ "$name" = "$NEW_CONTAINER_NAME" ]; then
    echo "ERROR: 不能删除新系统容器：$NEW_CONTAINER_NAME" >&2
    exit 1
  fi
done

for name in $LEGACY_CONTAINERS; do
  if docker ps -a --format '{{.Names}}' | grep -Fxq "$name"; then
    echo "Stopping/removing legacy container: $name"
    docker stop "$name" >/dev/null 2>&1 || true
    docker rm "$name" >/dev/null
  else
    echo "skip missing container: $name"
  fi
done

docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}' > "$BACKUP_DIR/docker-ps-after.txt" || true

echo
echo "Cleanup complete."
echo "backup: $BACKUP_DIR"
echo
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}' || true
