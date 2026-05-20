# AI Tool Studio ComfyUI Worker 接入手册

本文档用于让后续 agent 或运维人员把新的 ComfyUI 机器接入 AI Tool Studio。

当前生产入口：

- Frontend: `http://192.168.1.60:5173`
- Backend: `http://192.168.1.60:8000`
- Admin: `http://192.168.1.60:5173/admin`
- Canvas: `http://192.168.1.60:5173/canvas/{conversation_id}`
- 运行数据库：`/opt/aitoolstudio/data/img_platform.db`

不要把 `/opt/aitoolstudio/img-platform/backend/img_platform.db` 当生产库，它是旧/非运行库。

## 当前已完成范围

已完成并通过回归：

- Worker Registry：多 worker CRUD + health check
- Scheduler：按 tier、tag、model、node、VRAM 过滤
- 生成入口：image、upscale、SAM、canvas run、canvas cascade 已接入 worker scheduler
- Admin Workers：列表、CRUD、状态、启用/禁用
- Admin Dashboard：workers、workflows、24h generation、24h canvas、ComfyUI、recent errors
- Canvas/对话同步：Huobao Canvas 与 ATS conversation/document 打通
- 运行记录标准化：`worker_id/run_type/entrypoint/error_source`
- 回归脚本：`scripts/verify_canvas_workers.sh`

基准验收：

```bash
cd /opt/aitoolstudio/img-platform
bash scripts/verify_canvas_workers.sh http://127.0.0.1
```

期望结果：

```text
Passed: 39  Failed: 0
ALL CHECKS PASSED
```

## 新 Worker 机器准备

新机器上必须先跑通 ComfyUI API。

假设新机器 IP 是 `192.168.1.201`，ComfyUI 端口是 `8188`。

先在 ATS 服务器上测试：

```bash
curl -s http://192.168.1.201:8188/system_stats
curl -s http://192.168.1.201:8188/queue
curl -s http://192.168.1.201:8188/object_info
```

最低要求：

- `/system_stats` 返回 200
- `/queue` 返回 200
- `/object_info` 返回 200
- `object_info` 里至少有基础节点：
  - `CheckpointLoaderSimple`
  - `KSampler`
  - `SaveImage`

如果缺节点，Dashboard/Workers 面板会显示 `Missing core nodes` 或 `Model issue`。

## 模型路径要求

当前默认模型根路径：

```text
smb://192.168.1.60/团队文件-SJM-MediaFile/Comfyui_Model
```

Worker 机器本地挂载路径按实际填写，例如：

```text
/mnt/comfyui-models
```

接入前必须确认新机器的 ComfyUI 能读到 checkpoint：

```bash
curl -s http://192.168.1.201:8188/object_info | python3 - <<'PY'
import json, sys
d = json.load(sys.stdin)
ckpt = (
    d.get("CheckpointLoaderSimple", {})
    .get("input", {})
    .get("required", {})
    .get("ckpt_name", [])
)
print(ckpt)
PY
```

如果 checkpoint 数量是 0，先修模型挂载，不要急着接入 ATS。否则 scheduler 可能能看到 worker 在线，但实际生成会失败。

## Admin Workers 配置

打开：

```text
http://192.168.1.60:5173/admin
```

进入 `Workers` 分类，点击 `Add Worker`。

字段建议：

| 字段 | 示例 | 说明 |
|---|---|---|
| Worker ID | `worker-201` | 可不填。不填后端会自动生成，但生产建议填稳定 ID |
| Name | `ComfyUI 201` | 展示名 |
| URL | `http://192.168.1.201:8188` | ComfyUI API 地址，不要带尾部 `/` |
| Tier | `heavy` / `medium` / `light` | 调度优先级和能力分组 |
| GPU | `RTX 4090` | 展示和排障用 |
| VRAM | `24` | 调度器会按估算显存过滤，`0` 表示跳过 VRAM 检查 |
| Tags | `sdxl, upscale, sam, video` | 用逗号分隔，影响 scheduler 选择 |
| Model Root URI | `smb://.../Comfyui_Model` | 模型存储源 |
| Mount Path | `/mnt/comfyui-models` | 新 worker 机器上的本地挂载路径 |
| Enabled | checked | 取消勾选后 scheduler 不应选择该 worker |
| Notes | 任意 | 写模型、节点、风险说明 |

## Tier 与 Tags 约定

Tier 建议：

- `heavy`: 高显存、主力生成机器，例如 4090/5090/A6000
- `medium`: 中等负载，例如 upscale、controlnet、SDXL
- `light`: 轻任务、测试机、低显存机器

Tags 建议：

- `sd15`: 支持 SD 1.5 工作流
- `sdxl`: 支持 SDXL/Flux 等较重工作流
- `upscale`: 支持 upscale workflow
- `sam`: 支持 SAM mask
- `preprocess`: 支持预处理节点
- `video`: 支持 video workflow
- `controlnet`: 支持 ControlNet

不要乱填 tag。Scheduler 会用 tag 过滤，填错等于给系统制造假能力。

## Env 管理模式

Worker 可以来自两种来源：

1. `COMFYUI_WORKERS_JSON` 环境变量
2. `backend/config/comfyui_workers.json` 文件
3. 没配置时 fallback 到 legacy worker：`COMFYUI_BASE_URL`

优先级：

```text
COMFYUI_WORKERS_JSON > comfyui_workers.json > legacy COMFYUI_BASE_URL
```

如果设置了 `COMFYUI_WORKERS_JSON`，Admin Workers 的新增/修改/删除会返回类似：

```text
Workers are managed by COMFYUI_WORKERS_JSON env var, modify it directly
```

这不是 bug。env-managed 模式下要改环境变量并重启后端。

## 接入后验证

### 1. Worker API

```bash
TOKEN="$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<admin-password>"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")"

curl -s http://127.0.0.1:8000/api/comfyui/workers \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

curl -s http://127.0.0.1:8000/api/comfyui/workers/status \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

新 worker 应该出现在列表里，并且：

- `online: true`
- `checkpoint_count > 0`
- `object_info_ok: true`
- `has_required_core_nodes: true`
- `last_health_error: null`

### 2. Admin 页面

打开：

```text
http://192.168.1.60:5173/admin
```

检查：

- Dashboard 的 Workers total/online/offline 正确
- Workers 页面能看到新 worker
- Refresh Status 后状态不需要刷新页面也能更新
- Offline worker 不应被 scheduler 选择

### 3. 真实生成

跑普通图片生成：

```bash
curl -s -X POST http://127.0.0.1:8000/api/image/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"model":"comfyui-local","prompt":"worker onboarding test","aspect_ratio":"1:1","n":1}' \
  | python3 -m json.tool
```

期望：

- HTTP 200
- 返回 `id`
- `image_urls` 至少 1 个

### 4. 检查运行记录

生产库：

```bash
sqlite3 /opt/aitoolstudio/data/img_platform.db \
  "select id, worker_id, run_type, entrypoint, error_source from generations order by id desc limit 5;"
```

期望最新记录类似：

```text
worker_id=worker-201
run_type=direct_image
entrypoint=POST /api/image/generate
error_source=NULL
```

如果 `worker_id` 仍是旧 worker，说明 scheduler 没选中新机器。回头查 tier/tag/model/node/VRAM 条件。

### 5. 全量回归

```bash
cd /opt/aitoolstudio/img-platform
bash scripts/verify_canvas_workers.sh http://127.0.0.1
```

必须是：

```text
Failed: 0
ALL CHECKS PASSED
```

## Scheduler 选择逻辑排查

如果新 worker 没被选中，按顺序查：

1. Worker 是否 `enabled=true`
2. `/api/comfyui/workers/status` 是否 `online=true`
3. `checkpoint_count` 是否大于 0
4. `has_required_core_nodes` 是否 true
5. 任务需要的 tag 是否存在
6. 任务需要的 model 是否在 worker 的 checkpoint 列表里
7. 任务估算 VRAM 是否超过 worker `vram_gb`
8. 队列是否过长

后端日志里应能看到：

```text
Scheduler selected worker <worker_id> (tier=<tier>)
```

生成结果的标准记录字段：

| 字段 | 说明 |
|---|---|
| `worker_id` | scheduler 选择的 worker |
| `run_type` | `direct_image` / `upscale` / `canvas_run` / `canvas_cascade` 等 |
| `entrypoint` | 触发入口，例如 `POST /api/image/generate` |
| `error_source` | 错误来源，成功时通常为 null |

## 常见故障

### Worker offline

症状：

- Workers 页面显示 Offline
- Dashboard recent errors 有 `GET .../system_stats failed`

处理：

```bash
curl -v http://<worker-ip>:8188/system_stats
```

检查防火墙、端口、ComfyUI 是否启动、绑定地址是否为 `0.0.0.0`。

### Model issue

症状：

- Online 但 checkpoint_count 为 0
- 或 `object_info_ok=false`

处理：

- 检查模型挂载路径
- 检查 ComfyUI 启动参数
- 检查 checkpoint 是否在 ComfyUI 的模型目录里
- 重启 ComfyUI 后再点 Refresh Status

### Missing core nodes

症状：

- `has_required_core_nodes=false`

处理：

- 检查 ComfyUI 是否缺基础节点
- 检查自定义节点是否安装失败
- 查看 ComfyUI 控制台启动日志

### Scheduler 不选新 worker

处理：

- 确认 worker enabled
- 确认 tag/tier 符合任务
- 确认 `vram_gb` 不小于任务估算
- 临时把旧 worker disabled，再跑一次生成，看新 worker 是否接管

### Admin CRUD 报 env-managed

症状：

```text
Workers are managed by COMFYUI_WORKERS_JSON env var
```

处理：

- 修改 `COMFYUI_WORKERS_JSON`
- 重建或重启 backend 容器
- 不要在 Admin 页面硬改

## Agent 接入任务模板

把下面这段直接交给 agent：

```text
目标：接入新的 ComfyUI Worker 到 AI Tool Studio。

生产地址：
- Frontend: http://192.168.1.60:5173
- Backend: http://192.168.1.60:8000
- 项目目录: /opt/aitoolstudio/img-platform
- 生产数据库: /opt/aitoolstudio/data/img_platform.db

新 worker 信息：
- ID: <worker-id>
- Name: <worker-name>
- URL: http://<worker-ip>:8188
- Tier: <heavy|medium|light>
- GPU: <gpu-name>
- VRAM: <number>
- Tags: <comma-separated-tags>
- Model Root URI: smb://192.168.1.60/团队文件-SJM-MediaFile/Comfyui_Model
- Mount Path: <worker-local-model-mount-path>

要求：
1. 先验证 worker 的 /system_stats /queue /object_info。
2. 确认 checkpoint_count > 0，且 core nodes 存在。
3. 通过 Admin Workers 或 workers API 注册 worker。
4. Refresh Status 后确认 online=true。
5. 跑一次 comfyui-local image generate。
6. 查 /opt/aitoolstudio/data/img_platform.db，确认最新 generations.worker_id 是新 worker。
7. 跑 bash scripts/verify_canvas_workers.sh http://127.0.0.1，必须 0 failed。
8. 输出验收证据，不要只说“已完成”。
```

## 不要做的事

- 不要直接改 `/opt/aitoolstudio/img-platform/backend/img_platform.db`
- 不要跳过真实生成，只看 `/system_stats`
- 不要把所有 worker 都填成 `heavy`
- 不要随便填 tag
- 不要在 `COMFYUI_WORKERS_JSON` 管理模式下用 Admin CRUD 硬改
- 不要只跑前端页面检查，必须跑回归脚本

