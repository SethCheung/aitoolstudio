# 60 Docker 画板清理与用户迁移 How-to

更新时间：2026-06-01

目标：60 服务器最终只保留新的 AIToolStudio / Canvas 服务入口，把旧 Docker 画板工具下线；旧系统只保留用户登录信息，迁移到新系统的 `data/auth.db`。

## 1. 当前判断

2026-06-01 从本机抽检到的 60 服务：

| 端口 | 状态 | 判断 |
|---:|---|---|
| `3000` | `uvicorn`，访问 `/` 跳转登录 | 新 AIToolStudio / Canvas |
| `5173` | `nginx` 静态前端 | 旧画板/旧平台前端 |
| `8000` | `AI 生图协作平台 API - 运行中` | 旧画板/旧平台后端 |
| `8080` | `Tapnow Studio` | 旧画板/旧工具 |
| `80` | nginx 跳转到 `5666` | 非本次直接清理对象，先保留 |

结论：可以清理旧画板工具，但要先备份和迁移用户库。不要直接 `docker rm -f` 后再找账号数据。

## 2. 必须保留的数据

新系统登录数据库：

```text
/opt/aitoolstudio-canvas/data/auth.db
```

仓库内对应：

```text
data/auth.db
```

旧系统如果是 SQLite，迁移脚本要求旧库里有：

```text
users(username, password_hash, is_admin, created_at, updated_at)
```

迁移命令：

```bash
cd /opt/aitoolstudio-canvas
python scripts/import_legacy_users.py --source /path/to/legacy.db --target data/auth.db
```

如果需要用旧库覆盖同名用户密码和管理员状态：

```bash
python scripts/import_legacy_users.py --source /path/to/legacy.db --target data/auth.db --replace
```

## 3. 清理前备份

在 60 服务器上执行：

```bash
cd /opt/aitoolstudio-canvas
TS=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR=/vol3/@team/SJM-MediaFile/AI-Tool-Studio/backups/canvas-cleanup-$TS
mkdir -p "$BACKUP_DIR"

cp -a data/auth.db "$BACKUP_DIR/auth.db.before-cleanup" 2>/dev/null || true
cp -a API/.env "$BACKUP_DIR/API.env.before-cleanup" 2>/dev/null || true
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}' > "$BACKUP_DIR/docker-ps-before.txt"
docker compose -f docker-compose.60.yml ps > "$BACKUP_DIR/new-compose-ps-before.txt" 2>&1 || true
```

若已找到旧系统数据库，也复制一份：

```bash
cp -a /path/to/legacy.db "$BACKUP_DIR/legacy.db"
```

## 4. 盘点旧容器

先看全部容器：

```bash
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}'
```

重点找占用这些端口的容器：

```text
5173
8000
8080
```

不要删除：

```text
aitoolstudio-canvas
```

也不要动 ComfyUI worker 机器上的 ComfyUI 进程；这次只清理 60 Docker 里的旧画板服务。

## 5. 用脚本执行 dry-run

仓库里提供了安全脚本：

```bash
cd /opt/aitoolstudio-canvas
bash scripts/cleanup_60_canvas_docker.sh
```

默认只输出建议，不会停止或删除容器。

指定旧库并 dry-run 迁移检查：

```bash
LEGACY_DB=/path/to/legacy.db bash scripts/cleanup_60_canvas_docker.sh
```

## 6. 真正执行

确认备份、迁移、容器名都正确后，再执行：

```bash
cd /opt/aitoolstudio-canvas
LEGACY_DB=/path/to/legacy.db \
LEGACY_CONTAINERS="old_frontend old_backend tapnow" \
bash scripts/cleanup_60_canvas_docker.sh --apply
```

脚本会：

1. 备份新系统 `data/auth.db`。
2. 如果设置 `LEGACY_DB`，把旧用户导入 `data/auth.db`。
3. 停止并删除 `LEGACY_CONTAINERS` 指定的旧容器。
4. 保留 `aitoolstudio-canvas`。
5. 输出清理后的 `docker ps -a`。

脚本默认不删除 Docker volumes、不 `docker system prune`，避免误删用户数据。等新系统稳定一段时间后，再安排维护窗口清理旧目录和旧镜像。

## 7. 验收

新系统入口：

```bash
curl -fsSI http://192.168.1.60:3000/
```

用户列表：

```bash
cd /opt/aitoolstudio-canvas
sqlite3 data/auth.db "select id, username, is_admin, is_disabled, created_at, updated_at from users order by id;"
```

旧端口应不再响应或返回连接失败：

```bash
curl -fsSI --max-time 3 http://192.168.1.60:5173/ || true
curl -fsSI --max-time 3 http://192.168.1.60:8000/ || true
curl -fsSI --max-time 3 http://192.168.1.60:8080/ || true
```

## 8. 回滚

如果迁移后账号异常：

```bash
cd /opt/aitoolstudio-canvas
cp -a /vol3/@team/SJM-MediaFile/AI-Tool-Studio/backups/canvas-cleanup-YYYYMMDD-HHMMSS/auth.db.before-cleanup data/auth.db
docker compose -f docker-compose.60.yml restart
```

如果旧服务需要临时恢复，使用备份里的 `docker-ps-before.txt` 找容器名和镜像，再按旧 compose 或旧启动方式恢复。
