# 2026-05-27 Workflow 导入与安装器 Session 总结

## 背景

本次 session 围绕 ComfyUI workflow 导入、依赖预检与安全安装计划展开。项目部署在 `192.168.1.60:3000`，远端生产目录为 `/opt/aitoolstudio-canvas`，容器名为 `aitoolstudio-canvas`。

用于复现和验收的测试 JSON 文件为：

```text
/Users/apple/Downloads/1-Aiden-极致真实摄影人像工作流，文生图（小白福音）.json
```

用户要求本次所有代码修改都由 subagent 完成，主 agent 只负责下任务和验收。

## 初始问题

导入测试 JSON 时，后端返回错误：

```text
400 请粘贴有效的 ComfyUI API 工作流 JSON（需包含 class_type）
```

本地和远端均可复现该问题。

根因是测试 JSON 并非 ComfyUI API workflow，而是 ComfyUI 前端 UI workflow。其顶层结构包含 `nodes`、`links`、`widgets_values` 等字段；原后端只接受 API workflow，即类似如下结构：

```json
{
  "node_id": {
    "class_type": "...",
    "inputs": {}
  }
}
```

因此，原导入逻辑无法识别 UI workflow 中的节点、连线和 widget 值，也无法生成后续依赖检测所需的 API prompt。

## 已实现功能

### UI Workflow 自动转换

导入流程已支持自动识别 ComfyUI 前端 UI workflow，并转换为 API prompt。转换逻辑覆盖：

- 解析顶层 `nodes`、`links`、`widgets_values`。
- 根据 link 关系还原节点输入连接。
- 绕过 `Reroute` 节点，将真实上游节点连接到下游输入。
- 跳过 seed 后面的 `fixed`、`randomize` 等控制值，避免把前端控制项误写入 API prompt。
- 保留后端依赖检测需要的 `class_type` 与 `inputs`。

### 导入结果安装计划

导入结果中新增安全安装计划 `install_plan`，用于把缺失模型和缺失自定义节点拆分成可审查、可执行的安装动作。

### 缺失模型下载

后端支持管理员为缺失模型填写下载 URL 后，将模型下载到 60 盘的 `models/...` 路径下。安全限制包括：

- 只允许 `http` 和 `https` URL。
- 下载目标路径必须限制在资源根目录内，避免路径穿越。
- 下载时先写入 `downloads/cache` 临时文件。
- 下载完成后再原子替换到目标模型路径。

上传或导入 JSON 本身不会触发自动下载，必须由管理员明确填写 URL 并点击下载。

### 自定义节点安装计划

安装计划会列出缺失的 `class_type`，用于提示可能缺少的 ComfyUI custom nodes。

自定义节点 clone 的执行条件较严格：

- 必须配置 `AITOOL_COMFYUI_CUSTOM_NODES_DIR` 或 `COMFYUI_CUSTOM_NODES_DIR`。
- 配置目录必须存在且可写。
- 管理员必须填写 GitHub repo URL。
- 满足条件后，后端才执行 `git clone --depth 1`。

系统不会自动执行 `pip install`，也不会自动安装 Python requirements。

### 缺失模型候选链接查找

前端新增“查找链接”能力，用于辅助管理员寻找缺失模型下载地址。

候选链接查找逻辑：

- 优先调用 Hugging Face public API 搜索模型仓库 siblings，并生成 `resolve` 直链。
- Hugging Face 无结果时，可尝试已配置的 LLM provider 作为辅助来源。
- 候选会被严格过滤，只接受模型文件直链。
- 允许的模型文件后缀包括 `.safetensors`、`.ckpt`、`.pt`、`.pth`、`.bin`、`.gguf`。
- 普通页面链接会被拒绝，例如 `https://huggingface.co/comfy-org/` 不会作为可下载候选。

AI 或搜索返回的候选只作为辅助信息，不会自动触发下载。

### 前端安装计划 UI

前端已补充安装计划交互，包括：

- 缺失模型 URL 输入。
- 候选链接展示。
- “使用”候选填入 URL。
- “下载”按钮创建后端安装任务。
- 安装任务轮询与日志展示。

## 关键文件

本次功能主要涉及以下文件：

- `main.py`
- `static/js/comfyui-settings.js`
- `static/css/comfyui-settings.css`
- `static/comfyui-settings.html`
- `scripts/verify_workflow_import_plan.py`

## 新增/相关 API

### `POST /api/workflows/import/plan`

用于导入 workflow 并生成预检结果。支持 ComfyUI API workflow 和前端 UI workflow。对于 UI workflow，会先转换为 API prompt，再返回节点数量、模型依赖、缺失项和 `install_plan`。

### `POST /api/workflow-install/tasks`

用于创建安装任务。当前主要支持缺失模型下载，以及在自定义节点目录已配置且可写时执行 GitHub repo clone。该接口不会自动安装 Python requirements。

### `GET /api/workflow-install/tasks/{task_id}`

用于查询安装任务状态、进度和日志。前端通过轮询该接口展示下载或 clone 过程。

### `POST /api/workflow-install/model-candidates`

用于为缺失模型查找候选下载直链。优先使用 Hugging Face public API，必要时可结合已配置 LLM provider 辅助分析。返回结果会经过模型文件直链过滤。

## 验收记录

### 本地验证命令

```bash
python3 -m py_compile main.py scripts/verify_workflow_import_plan.py
node --check static/js/comfyui-settings.js
python3 scripts/verify_workflow_import_plan.py
```

### 本地关键输出

```text
verify_workflow_import_plan: OK
ui workflow nodes: 66 required classes: 32 model deps: 22 install actions: 54 field candidates: 130
```

### 远端导入预检验收

使用 Aiden 测试 JSON 调用远端导入预检接口，返回：

- `HTTP 200`
- `node_count=66`
- `model_dependencies=22`

### 安装计划远端验收

远端安装计划曾返回：

- `install_actions=33`
- `models=22`
- `custom=11`
- `custom_nodes 目录未配置`

该结果符合预期：模型依赖可进入下载计划，自定义节点在目录未配置时只生成计划，不执行 clone。

### 候选链接远端验收

`POST /api/workflow-install/model-candidates` 返回 `HTTP 200`。

在无可靠模型直链时：

- `candidates` 返回空列表。
- bad candidates 为空。
- 普通页面链接不会被误判为可下载模型文件。

## 部署与备份记录

远端生产目录：

```text
/opt/aitoolstudio-canvas
```

容器：

```text
aitoolstudio-canvas
```

备份目录和文件包括：

```text
/opt/aitoolstudio-canvas/main.py.bak-20260527-203920
/opt/aitoolstudio-canvas/backups/workflow-import-plan-20260527-210140/
/opt/aitoolstudio-canvas/backups/deploy-missing-model-links-20260527-212255/
/opt/aitoolstudio-canvas/backups/20260527_212748/
```

部署后健康检查结果：

- `/api/auth/me` 未登录返回 `401`。
- `/login` 返回 `200`。

## 当前行为和限制

- 上传 JSON 不会自动下载模型；需要先查候选或手动填写 URL，然后点击下载。
- AI 候选仅用于辅助管理员判断，不会自动执行下载。
- `custom_nodes` 未配置时，只能生成自定义节点安装计划，不能执行 clone。
- 系统不会自动安装 Python requirements。
- 模型候选搜索可能找不到可靠直链，此时仍可由管理员手动填写 URL。

## 后续建议

- 配置 `AITOOL_COMFYUI_CUSTOM_NODES_DIR` 后，再启用自定义节点 clone。
- 增加候选来源白名单和评分展示，帮助管理员判断候选可信度。
- 增加模型下载任务持久化，避免服务重启后丢失任务状态。
- 增加安装完成后的自动重新检测兼容性能力。
- 如后续接入 Kimi 或 MiniMax CLI，也应只作为候选来源分析工具，不直接执行任意命令。
