# AIToolStudio 使用指南

本文面向 AIToolStudio 实际操作者，基于 2026-05-27 的验收结果编写。

## 1. 快速访问

- 平台地址：`http://192.168.1.60:3000`
- 当前版本（接口返回）：`2026.05.27.6`

可用命令：

```bash
curl -s http://192.168.1.60:3000/api/app-info
```

未登录直接访问 `/` 时，会 `307` 跳转到 `/login?next=%2F`；登录页 `/login` 状态 `200`，标题为“登录 - AI Studio”。

## 2. 登录后主要页面

登录后以下页面可正常访问（均为 `HTTP 200`）：

- `/`
- `/projects`
- `/studio`
- `/canvas`
- `/comfyui-settings`
- `/static/project-home.html`
- `/static/comfyui-settings.html`
- `/static/canvas.html`
- `/static/api-settings.html`

账号与权限请向管理员获取，不在文档中记录账号口令。

## 3. ComfyUI 状态检查

当前已接入 3 个 ComfyUI 实例：

- `192.168.1.195:8188`
- `192.168.1.197:8188`
- `192.168.1.249:8188`

验收状态：`/api/comfyui/status` 返回 3 个实例 `ok=true`，且 `queue_running=0`、`queue_pending=0`。

示例（带占位符认证）：

```bash
curl -s 'http://192.168.1.60:3000/api/comfyui/status' \
  -H 'Authorization: Bearer <TOKEN>' \
  -H 'Cookie: session=<COOKIE>'
```

## 4. 运行 Smoke 工作流

当前已启用工作流：`custom/aitool-smoke-sd15.json`  
工作流接口统计：`/api/workflows` 共 7 条，`/api/runninghub/workflows` 共 2 条。

运行示例：

```bash
curl -s -X POST \
  'http://192.168.1.60:3000/api/workflows/custom/aitool-smoke-sd15.json/run' \
  -H 'Authorization: Bearer <TOKEN>' \
  -H 'Cookie: session=<COOKIE>' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

验收样例返回关键信息：

- `task_id=1`
- `prompt_id=be97abd0-9141-46dc-ad72-7c2eeb95f824`
- `backend=192.168.1.195:8188`

## 5. 查看输出结果

本次端到端验收输出文件：

- 平台相对路径：`/assets/output/workflow-test_1779891358_0481dbb124.png`
- 访问 URL：`http://192.168.1.60:3000/assets/output/workflow-test_1779891358_0481dbb124.png`
- 验收结果：`HTTP 200`，`content-length=64449`

建议操作：

1. 在浏览器直接打开输出 URL，确认图片可访问。
2. 若需要自动检查，可用 `curl -I` 观察状态码和长度。

```bash
curl -I 'http://192.168.1.60:3000/assets/output/workflow-test_1779891358_0481dbb124.png'
```

## 6. 后端功能验收

以下为 2026-05-27 实测结果（只读验证）：

- `GET /api/comfyui/instances`：返回 3 台实例。
- `GET /api/comfyui/status`：3 台均 `ok=true`，且 `queue_running=0`、`queue_pending=0`。
- `GET /api/resource-root`：`configured=true`、`available=true`，资源根目录为 `/vol3/@team/SJM-MediaFile`，可读写，建议的 11/11 子目录均存在。
- `GET /api/workflows`：共 7 条工作流。
- `GET /api/history`：接口可正常返回。
- `GET /api/queue_status?client_id=...`：返回 `total=0`、`position=0`（当前无排队）。

建议操作者将上述接口作为日常巡检最小集合，先看实例可用性与队列，再看资源根与工作流清单。

## 7. ComfyUI 节点加载检查

对三台 ComfyUI 执行 `/object_info` 统计，节点加载数量如下：

- `192.168.1.195:8188`：2303
- `192.168.1.197:8188`：1685
- `192.168.1.249:8188`：1465

Smoke 必需节点在三台均存在（6/6）：

- `CheckpointLoaderSimple`
- `CLIPTextEncode`
- `EmptyLatentImage`
- `KSampler`
- `VAEDecode`
- `SaveImage`

## 8. 工作流节点覆盖

已启用/内置的 7 个工作流，在三台实例上均验证为无缺失 `class_type`：

- `custom/aitool-smoke-sd15.json`
- `2511.json`
- `Flux2-Klein.json`
- `LTXDirectorv2-API.json`
- `Z-Image.json`
- `Z-Image-Enhance.json`
- `upscale.json`

这意味着上述工作流在当前节点环境下可通过“节点类型存在性”检查，不涉及安装动作。

## 9. 导入预检说明 / FAQ

本地预检命令（在项目根目录执行）：

```bash
python3 -m py_compile main.py scripts/verify_workflow_import_plan.py
node --check static/js/comfyui-settings.js
python3 scripts/verify_workflow_import_plan.py
```

验收通过标记包含：

- `verify_workflow_import_plan: OK`
- smoke workflow：`node_count=7`、`required_class_count=6`、`model_dependencies=1`，其中 `exists=1`，`missing class_type=0`
- Aiden UI workflow：`node_count=66`、`required_class_count=32`、`model_dependencies=22`，其中 `exists=3`、`missing=19`
- Aiden UI install_plan：`action_count=28`（`model_download_count=22`、`custom_node_install_count=6`）
- Aiden UI 缺失 `class_type` 并集（6 个）：
  - `MarkdownNote`
  - `KOOK_ImageCompression`
  - `LayerUtility: PurgeVRAM V2`
  - `TTP_Image_Assy`
  - `TTP_Image_Tile_Batch`
  - `TTP_Tile_image_size`

说明：

1. `POST /api/workflows/import/plan` 本次仅用于“非安装预检”，用于生成缺失项与安装计划，不会自动落地安装。
2. 本次验收严格在安全边界内进行：未执行安装、下载、`clone`、`pip install`。
3. 若后续要补齐 Aiden UI 缺失项，请在变更窗口执行，并保留安装审计记录（来源、版本、执行人、时间）。

## 10. 常见问题

1. 访问 `/` 被跳转到登录页：属于正常未登录行为，请先登录。
2. 页面打不开或状态非 200：先确认是否已登录、会话是否过期，再检查服务地址和网络连通性。
3. 工作流运行后无输出：先检查 `/api/comfyui/status` 队列与实例状态，再查看所用工作流是否启用。
4. 预检失败：优先按 `verify_workflow_import_plan.py` 与 `/api/workflows/import/plan` 输出定位缺失 `class_type`、模型依赖和安装计划。
5. “验完了吗？”判断口径：后端接口可用 + 节点加载统计已完成 + 7 个已启用工作流三机 `class_type` 覆盖无缺失，即可判定“后端与节点加载验收完成”；但 Aiden UI 这类扩展工作流仍可能需要后续补依赖。

## 11. 运维安全注意事项

1. 当前系统未提供标准健康探针接口（如 `/health`、`/status`、`/version`、`/api/health`），建议后续补充统一健康检查端点。
2. `.env` 包含敏感配置；禁止在文档、聊天记录、脚本日志中写入明文密码、密钥、Token。
3. 建议定期轮换管理员密码和 API 密钥，并避免 SSH/Web 口令复用。
4. 当前容器启动命令包含运行时 `pip install`，建议将依赖固化进镜像，减少漂移与启动风险。

## 12. 验收记录（2026-05-27）

- 端到端时间（UTC+8）：`2026-05-27 22:15:53` 至 `22:15:58`
- 验收动作：`POST /api/workflows/custom/aitool-smoke-sd15.json/run`
- 结果：运行成功，生成可访问输出图片，平台侧访问 `HTTP 200`
- 版本确认：`/api/app-info` 返回 `2026.05.27.6`
