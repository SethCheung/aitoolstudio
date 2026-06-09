# Infinite-Canvas (AITOOL Studio)

当前仓库是基于 Infinite-Canvas 的 FastAPI + 静态前端项目，不是旧的 Vue/img-platform 架构。

## 1) 本地启动

1. 安装依赖：
   - `pip install -r requirements.txt`
2. 复制环境变量模板：
   - `cp .env.example API/.env`
3. 启动服务：
   - `python main.py`
4. 打开：
   - `http://127.0.0.1:3000/`

路由入口：
- `/projects`：项目主页（新）
- `/admin`：后台控制台（管理员）
- `/studio`：旧多工具壳（兼容入口）

macOS 可使用现有脚本：`./mac-启动服务.sh` 或双击 `mac-启动服务.command`。

## 2) 登录与权限

- 认证数据库：`data/auth.db`（首次运行自动创建）。
- 默认管理员（建议首次登录后立刻改）：
  - 用户名：`admin`
  - 密码：`admin123`
- 可通过 `API/.env` 覆盖：
  - `AITOOL_ADMIN_USERNAME`
  - `AITOOL_ADMIN_PASSWORD`

鉴权接口：
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `POST /api/auth/users`（仅管理员）

旧系统用户迁移（60 系统 SQLite `users` -> 新系统 `data/auth.db`）：

```bash
python scripts/import_legacy_users.py --source /path/to/legacy.db
python scripts/import_legacy_users.py --source /path/to/legacy.db --replace
```

- 默认按 `username` 去重并跳过同名用户。
- 加 `--replace` 会更新同名用户的 `password_hash/is_admin/created_at/updated_at`，并重置为未禁用。

## 3) 项目与画布（普通用户）

1. 普通用户登录后进入项目列表。
2. 新建项目会自动创建默认画布。
3. 在画布中添加文本/图片/工作流节点并运行。
4. 输出图片默认落到 `assets/output/`（并可在画布继续作为上游输入）。

## 4) 后台 API Provider 设置（管理员）

管理员进入：
- `http://127.0.0.1:3000/api-settings`

可配置：
- Provider 协议（OpenAI/APIMart/Gemini/Volcengine/RunningHub）
- `base_url`
- 模型列表
- API Key（保存在 `API/.env`，不会在前台明文暴露）

关键环境变量示例见 `.env.example`，包括：
- `COMFLY_API_KEY`
- `MODELSCOPE_API_KEY`
- `RUNNINGHUB_API_KEY`
- `RUNNINGHUB_WALLET_API_KEY`

## 5) ComfyUI Workflow 设置（管理员）

管理员进入：
- `http://127.0.0.1:3000/comfyui-settings`

流程：
1. 配置 ComfyUI 实例：`COMFYUI_INSTANCES`（如 `127.0.0.1:8188`）。
2. 配置 60 盘资源中心：`AITOOL_RESOURCE_ROOT` / `RESOURCE_ROOT`。
3. 导入 ComfyUI API-format workflow JSON，或用 RunningHub workflow 引用做本地化预检。
4. 检查缺失节点、模型依赖和 60 盘模型命中状态。
5. 在后台选择并暴露可控参数（字段映射、是否必填、默认值等）。
6. 启用后普通用户可在画布直接运行该 workflow。

说明：ComfyUI 是外部服务，本项目不会在启动时自动拉起 ComfyUI。架构原则是 60 盘存模型、workflow、输入素材、输出结果和下载缓存；195/197 等 ComfyUI 机器只作为算力节点挂载读取。

## 6) Docker Compose（仅平台服务）

可用仓库内 `docker-compose.yml` 启动本服务：

```bash
docker compose up -d
```

- 服务对外端口：`3000`
- `API/.env` 通过 volume 映射到容器内 `/app/API/.env`
- `data/`、`assets/output/`、`output/` 持久化
- ComfyUI 需你自行部署，并在 `COMFYUI_INSTANCES` 中填写可访问地址
- 资源盘需通过 `AITOOL_RESOURCE_ROOT` 指向宿主机挂载路径

## 7) 60 生产部署与 ComfyUI 池运维

60 生产机当前使用 `docker-compose.60.yml`，平台唯一入口端口为 `3000`。`5173/8000` 仅视作历史端口（排障时核对），不作为日常后台入口。

旧 Docker 画板工具下线、旧用户迁移和回滚流程见：
- `docs/60-Docker-Canvas-Cleanup-HowTo.md`

ComfyUI 算力池建议用脚本巡检：

```bash
python scripts/comfyui_pool_inventory.py \
  --workflow workflows/Z-Image-Enhance.json \
  --output data/comfyui-pool-inventory.json \
  --strict
```

每台 ComfyUI worker 的开机挂载、systemd 启动和节点版本清单基线见：
- `docs/comfyui-worker-ops.md`

## 8) 目录与数据安全

- `workflows/` 下示例 workflow 可进 git。
- 运行时数据（`data/`）、鉴权库（`data/auth.db`）、输出图（`assets/output/`、`output/`）、密钥文件（`.env`、`API/.env`）不应进 git。
- 生产使用时，模型和大体积素材应放在 60 盘资源中心，平台本地目录只作为兼容旧数据的过渡位置。
