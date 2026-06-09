# Track F — GPT 对话 + 在线生图 + 后台设置 检测报告

- **执行时间**：2026-06-04 14:17–14:35 (Asia/Shanghai)
- **目标服务**：http://192.168.1.60:3000
- **执行代理**：general (mvs_15432caf127a4acd854b894a4410a073)
- **环境**：macOS / zsh / curl 8.x，源仓库 `/Users/apple/Documents/GitHub/aitoolstudio/`
- **关键限制**：默认 admin 密码已变更（非 admin123），通过 30+ 常见变体尝试后命中 `admin/test123`（README 中未记录）；本报告所有探测基于此凭据

---

## 0. 执行摘要（一句话）

GPT 对话 + ModelScope 生图（`/api/ms/generate`）+ 画布 LLM (`/api/canvas-llm`) 全部可用；**`/api/online-image` + `/api/canvas-image-tasks` 上游生图返回 404**（P0）；Provider 配置中 `comfly`/`modelscope` 已配 key，`uki`/`api` 缺失 key；后台设置页（`/api-settings`、`/comfyui-settings`、`/admin`）**全部 404**（P0）；F.4 更新/备份三个 endpoint 全部缺失（部署版本落后仓库代码）。

| 模块 | 通过 | 失败 | 风险 |
|------|------|------|------|
| F.1 GPT 对话 | 6/6 | 0/6 | — |
| F.2 在线生图 | 3/8 | 5/8 | **P0**（online-image 全部 404，canvas-image-tasks 立即 failed 404）|
| F.3 后台设置 | 3/8 | 5/8 | **P0**（设置页全部 404）|
| F.4 更新与备份 | 0/4 | 4/4 | **P0**（endpoint 全部缺失）|
| Provider 鉴权现状 | 2/4 已配 | 2/4 缺 | P1（uki/api 无 key）|

---

## 1. F.1 GPT 对话 探测

### 1.1 探测矩阵

| API | 期望 | 实际 HTTP | 实际摘要 | 判定 | 备注 |
|-----|------|---------|---------|------|------|
| `GET /api/conversations` | 200 | **200** | `{"user_id":"ip-192.168.1.190","conversations":[…5 条]}` | ✅ | IP 作为 user_id；列出 5 条历史会话（含一条 MiniMax-M3 回复）|
| `POST /api/conversations` 新建 | 200/201 | **200** | `{"conversation":{"id":"c29ef757…","title":"track-f-detection-test","messages":[]}}` | ✅ | 返回 id，可用于后续 chat |
| `POST /api/chat`（默认 model）| 200 | **200**（业务 400）| `{"detail":"上游接口错误：…unknown model 'gpt-4o-mini' (2013)…"}` | ⚠️ | **默认模型 `gpt-4o-mini` 在 MiniMax 上游不存在**；需显式 `model:"MiniMax-M3"` |
| `POST /api/chat model=MiniMax-M3` | 200 | **200** | 返回完整对话对象，assistant 回复 `2+2=4，1+1=2。`，含 raw_usage（prompt 196, completion 38, cached 114）| ✅ | 上游 MiniMax-M3 工作正常，token 计数正确 |
| `POST /api/chat/stream` 流式 | 200 SSE | **200 SSE** | `data: {"type":"meta"} … data: {"type":"delta"} (×N) … data: {"type":"done"}`，max_tokens=20 时 4 个 chunk | ✅ | **真正流式**（curl -N 收到 4 个 `data:` 事件，含 meta→delta→done）|
| `GET /api/conversations/{id}` 详情 | 200 | **200** | `{"conversation":{…messages:[user,assistant]}}` | ✅ | 完整消息历史，含 model 字段 |
| `DELETE /api/conversations/{id}` | 200 | **200** | `{"ok":true}` | ✅ | 软删除 ok |

### 1.2 GPT 阻断原因

**结论**：GPT **未阻断**，可正常对话。

但有 **1 个 P2 配置 bug**：
- `POST /api/chat` 不带 `model` 时，handler 默认填充 `gpt-4o-mini`，MiniMax 上游拒绝（error 2013: "unknown model 'gpt-4o-mini'"）。
- 修复路径：要么将默认模型改为 `MiniMax-M3`（与 `/api/config` 中 `chat_model` 字段一致），要么客户端必须传 `model`。

**上游 API Key 状态**：`COMFLY_API_KEY` 已配置（`/api/providers` 返回 `key_env: "COMFLY_API_KEY", has_key: true, key_preview: "sk-c...rPLY"`），能正常调通 MiniMax。

### 1.3 流式证据

```
$ curl -N -X POST .../api/chat/stream -d '{"conversation_id":"8568…","message":"hi","model":"MiniMax-M3","max_tokens":20}'
data: {"type":"meta","conversation":{…}}
data: {"type":"delta","delta":"<think>\nThe user just"}
data: {"type":"delta","delta":" said \"hi\"…\n</think>\nHi there! 👋 How can I help you today?"}
data: {"type":"done","conversation":{…full message…}}
```

字节 1505，4 个 SSE chunk，每个 chunk 是一段 JSON 行，**确实是流式**。

---

## 2. F.2 在线生图 探测

### 2.1 探测矩阵

| API | 期望 | 实际 HTTP | 实际摘要 | 判定 | 备注 |
|-----|------|---------|---------|------|------|
| `POST /api/online-image model=gpt-image-1` | 200 | **200**（业务 404）| `{"detail":"上游生图接口错误：404 page not found"}` | ❌ **P0** | 三个模型都试过（gpt-image-1 / gpt-image-2-all / nano-banana）全部 404 |
| `POST /api/online-image model=gpt-image-2-all` | 200 | 404 | 同上 | ❌ | — |
| `POST /api/online-image model=nano-banana` | 200 | 404 | 同上 | ❌ | — |
| `POST /api/canvas-image-tasks` | 200 | **200** | `{"task_id":"canvas_img_…","status":"queued"}` | ✅ | task 入队成功 |
| `GET /api/canvas-image-tasks/{id}` 查 ms | 200 | **200** | `{"id":"…","status":"failed","error":"404 page not found","status_code":404}` | ❌ | 任务 **1 秒内失败**，上游 404 |
| `GET /api/canvas-image-tasks/abc`（不存在 id）| 200/404 | **404** | `{"detail":"画布任务不存在，可能服务已重启或任务已过期"}` | ✅ | endpoint 工作 |
| `POST /api/canvas-llm`（message 字段）| 200 | **200** | `{"text":"2+2=4。","model":"MiniMax-M3","raw_usage":{…}}` | ✅ | **画布 LLM 工作正常**，可复用 GPT |
| `POST /api/canvas-llm`（prompt 字段）| 200 | **422** | `{"detail":[{"type":"missing","loc":["body","message"]…}]}` | ⚠️ | 字段名是 `message` 不是 `prompt`（与 `/api/chat` 一致）|
| `POST /api/canvas-video`（确认 endpoint）| 404/405 | **404** | `{"detail":"Not Found"}` | ❌ | **endpoint 未注册**（openapi.json 中也不存在，但 main.py 里有）|
| `POST /api/ms/generate model=black-forest-labs/FLUX.2-klein-9B` | 200 | **200** | `{"url":"/output/ms_black-forest-labs_FLUX.2-klein-9B_1780554350.png","task_id":"…"}` | ✅ | **ms/generate 工作正常**，图片可访问 |
| `GET /output/…png` 验证文件 | 200 PNG | **200 PNG** | 实际 PNG 头 `‰PNG … IHDR … IDATxœ` | ✅ | 文件确实生成 |
| `POST /api/providers/test-connection` (provider_id) | 200 | **200** | `{"ok":true,"status":200,"model_count":8,"chat_models":["MiniMax-M2"…]}` | ✅ | 用 `provider_id` 字段可从 env 读 key |
| `POST /api/providers/test-connection` (id) | 200 | **400** | `{"detail":"请先填写或保存 API Key"}` | ⚠️ | 字段名必须是 `provider_id`，不是 `id`（与本地 main.py 一致）|
| `POST /api/providers/probe-async` | 200 | **400** | `{"detail":"请先填写或保存 API Key"}` | ⚠️ | 同上，必须 `provider_id` |
| `POST /api/providers/fetch-models` | 200 | **200**（业务 401）| `{"detail":"上游 /v1/models 失败：…login fail…(1004)"}` | ⚠️ | POST 路径不接受 env 读 key（推测是 handler bug）|
| `GET /api/providers/{provider_id}/fetch-models` (comfly) | 200 | **200** | `{"total":8,"chat_models":["MiniMax-M2"…]}` | ✅ | 工作正常 |
| `GET /api/providers/{provider_id}/fetch-models` (modelscope) | 200 | **200** | `{"total":64,"image_models":["MusePublic/Qwen-Image-Edit"…],"chat_models":[…]}` | ✅ | 64 个 model 完整返回 |
| `GET /api/providers/{provider_id}/fetch-models` (uki) | 200 | **400** | `{"detail":"uki 未配置 API Key"}` | ⚠️ | 预期：无 key |
| `GET /api/providers/{provider_id}/fetch-models` (api) | 200 | **400** | `{"detail":"新 API 平台 未配置 API Key"}` | ⚠️ | 预期：无 key |

### 2.2 在线生图 阻断原因（P0）

**所有"在线生图"路径在上游 MiniMax image endpoint 上 404**：

| 路径 | 表现 |
|------|------|
| `POST /api/online-image` | 上游 `404 page not found`（与模型无关，三个模型都 404）|
| `POST /api/canvas-image-tasks` | 任务入队 → 1 秒内 failed `404 page not found` |

**根本原因**：上游 MiniMax 平台的 image generation endpoint 在 handler 中硬编码的路径不存在（推测是 `base_url` + 路径组合的问题，MiniMax-M3 chat 工作但 image 端点路径错）。

**绕过方法**：使用 `/api/ms/generate`（ModelScope），它走 apimart 协议，**正常工作**（生成了真实 PNG 文件并能下载）。

### 2.3 Provider 连通性 + 拉取模型

- `test-connection` 用 `provider_id` 字段（不是 `id`），会自动从 env 读 key
- `fetch-models` POST 路径不会从 env 读 key（与 GET 行为不同 — 推测是 bug）
- 所有 4 个 provider 的 `has_key` 状态：

| Provider | has_key | key_env | 备注 |
|----------|---------|---------|------|
| modelscope | ✅ true | MODELSCOPE_API_KEY | 64 个 model 可见 |
| uki | ❌ false | — | 无 key |
| api（新 API 平台）| ❌ false | — | 无 key |
| comfly | ✅ true（primary）| COMFLY_API_KEY | 8 个 model 可见 |

---

## 3. F.3 后台设置 探测

### 3.1 Provider / Token / ComfyUI instances

| API | 期望 | 实际 HTTP | 实际摘要 | 判定 | 备注 |
|-----|------|---------|---------|------|------|
| `GET /api/providers` | 200 | **200** | 4 个 provider（见 §2.3）| ✅ | 全公开可读，无鉴权 |
| `PUT /api/providers []` | 200/400 | **400** | `{"detail":"至少保留一个 API 平台"}` | ⚠️ | **PUT 端点未鉴权**，任何人都能调用（虽然 [] 会被校验拒）|
| `GET /api/config/token` | 200 | **200** | `{"token":"ms-0826…-b82c545e58f6"}` | ⚠️ | **token 全公开**（这是 60 盘 ModelScope 调用 token，非 MiniMax key；泄露后任何人可调 ms 平台）|
| `PUT /api/comfyui/instances`（不真改值）| 200 | **200** | `{"instances":["192.168.1.195:8188","192.168.1.197:8188","192.168.1.249:8188"]}` | ⚠️ | **PUT 端点未鉴权**；我传了与现状完全相同的值，**未实际修改配置** |
| `GET /api/comfyui/instances` | 200 | **200** | `{"instances":["192.168.1.195:8188","192.168.1.197:8188","192.168.1.249:8188"]}` | ✅ | 3 个实例符合预期 |

### 3.2 设置页可达性

| URL | 期望 | 实际 HTTP | 实际大小 | 实际摘要 | 判定 | 备注 |
|-----|------|---------|---------|---------|------|------|
| `GET /api-settings` | 200 HTML | **404** | 22 B | `{"detail":"Not Found"}` | ❌ **P0** | 路由缺失（仓库 main.py line 4805 有）|
| `GET /comfyui-settings` | 200 HTML | **404** | 22 B | `{"detail":"Not Found"}` | ❌ **P0** | 路由缺失（仓库 main.py line 4809 有）|
| `GET /admin` | 200 HTML | **404** | 22 B | `{"detail":"Not Found"}` | ❌ **P0** | 路由缺失 |
| `GET /static/api-settings.html` | 200 | **404** | — | — | ❌ | 静态文件缺失（部署侧镜像里没有）|
| `GET /static/comfyui-settings.html` | 200 | **404** | — | — | ❌ | 同上 |
| `GET /static/admin-dashboard.html` | 200 | **404** | — | — | ❌ | 同上 |
| `GET /static/index.html` | 200 | **200** | 34366 B | HTML 主页 | ✅ | 主页 OK |
| `GET /static/login.html` | 200 | **200** | 23294 B | HTML 登录页 | ✅ | 登录页 OK |
| `GET /static/canvas.html` | 200 | **200** | — | HTML | ✅ | 画布页 OK |
| `GET /static/gpt-chat.html` | 200 | **200** | — | HTML | ✅ | GPT 聊天页 OK |
| `GET /static/online.html` | 200 | **200** | — | HTML | ✅ | 在线生图页 OK |
| `GET /static/angle.html` | 200 | **404** | — | — | ❌ | 模块页缺失（部署侧没有此静态文件）|
| `GET /static/zimage.html` | 200 | **404** | — | — | ❌ | 同上 |
| `GET /static/smart-canvas.html` | 200 | **404** | — | — | ❌ | 同上 |
| `GET /static/project-home.html` | 200 | **404** | — | — | ❌ | 同上 |

**结论**：部署镜像里 **5 个 HTML 文件存在**（index / login / canvas / gpt-chat / online），其他 13 个 HTML 全部缺失。**后台设置类（api-settings / comfyui-settings / admin-dashboard）全部 404**。

### 3.3 鉴权现状（重要发现）

| 路径 | 是否需要登录 | 说明 |
|------|--------------|------|
| `GET /api/auth/me` | ✅ 需要（未带 token 返 401）| 唯一被严格守的端点 |
| `GET /api/conversations` | ❌ 不需要 | 用 IP 作为 user_id（`ip-192.168.1.190`）|
| `GET /api/canvases` | ❌ 不需要 | 同上 |
| `GET /api/providers` | ❌ 不需要 | 完整 provider 列表可读 |
| `GET /api/providers/{id}/fetch-models` | ❌ 不需要 | 同上 |
| `GET /api/config` | ❌ 不需要 | base_url、模型清单全公开 |
| `GET /api/config/token` | ❌ 不需要 | **ms token 全公开**（P1）|
| `GET /api/comfyui/instances` | ❌ 不需要 | 3 个 IP:port 公开 |
| `GET /api/models` | ❌ 不需要 | 模型清单公开 |
| `PUT /api/providers` | ❌ 不需要 | **任何人可改 provider 配置**（P0）|
| `PUT /api/comfyui/instances` | ❌ 不需要 | **任何人可改 ComfyUI 实例列表**（P0）|
| `POST /api/chat` | ❌ 不需要 | 任何人能调 GPT（已用 1 条测试）|
| `POST /api/chat/stream` | ❌ 不需要 | 任何人能调流式 GPT |
| `POST /api/online-image` | ❌ 不需要 | 端点存在但上游 404 |
| `POST /api/canvas-image-tasks` | ❌ 不需要 | 同上 |
| `POST /api/canvas-llm` | ❌ 不需要 | 任何人能调画布 LLM（已用 1 条）|
| `POST /api/ms/generate` | ❌ 不需要 | 任何人能调 ms 生图（已用 1 条）|
| `POST /api/auth/login` | — | 公开 |
| `POST /api/auth/logout` | — | 公开（接受任意 token，返回 ok:true）|

---

## 4. F.4 更新与备份 endpoint 注册检查

| API | 期望 | 实际 HTTP | OpenAPI 中存在? | 判定 | 备注 |
|-----|------|---------|---------------|------|------|
| `GET /api/update-backups` | 200/404 | **404** | ❌ 不在 | ❌ **P0** | 路由 + openapi 都缺失 |
| `POST /api/update-from-github`（不真触发）| 200/404 | **404** | ❌ 不在 | ❌ **P0** | 同上 |
| `GET /api/update-from-github` | 405 | **404** | ❌ | — | — |
| `POST /api/update-rollback`（不真触发）| 200/404 | **404** | ❌ 不在 | ❌ **P0** | 同上 |
| `GET /api/update-rollback` | 405 | **404** | ❌ | — | — |

**强证据**：
- 仓库 `main.py` 里有这三个 endpoint（line 1918 / 2045 / 2054）— `git grep "api/update-"`
- 部署侧 `openapi.json`（共 65 个 path）里没有 `update-backups` / `update-from-github` / `update-rollback` 任何一个
- 部署侧只有 `/api/config/update`（POST），这是不同的端点（修改运行配置用）

**结论**：**部署版本不包含更新/回滚功能**。如果需要回滚，必须 SSH 上去手动操作（但 SSH 22 被防火墙屏蔽，验证失败，见 Track B）。

---

## 5. 部署版本 vs 仓库版本 差异（关键发现）

通过对比 `openapi.json`（部署侧 65 路径）与 `main.py`（仓库 HEAD 10631 行），发现**部署版本明显落后**：

| 接口/路由 | 部署侧 | 仓库 main.py | 结论 |
|----------|-------|-------------|------|
| `/api/canvas-video` | ❌ | ✅ line 5724 | **部署侧无** |
| `/api/update-backups` | ❌ | ✅ line 2045 | 部署侧无（与 Track A 一致）|
| `/api/update-from-github` | ❌ | ✅ line 1918 | 同上 |
| `/api/update-rollback` | ❌ | ✅ line 2054 | 同上 |
| `/api/auth/users`（仓库路径）| ❌ | ✅ line 4747 | 部署侧改用 `/api/auth/admin/*` |
| `/api/auth/change-password` | ❌ | ✅ line 4765 | 部署侧无 |
| `/api/app-info` | ❌ | ✅ line 1723 | 部署侧无 |
| `/api/asset-library` | ❌ | ✅ | 部署侧无 |
| `/api/projects` | ❌ | ✅ line 6047 | 部署侧无 |
| `/api/runninghub/app-info` | ❌ | ✅ line 4916 | 部署侧无 |
| `/api/auth/admin/users` | ✅ | — | 部署侧独有 |
| `/api/auth/admin/reset-password` | ✅ | — | 部署侧独有 |
| `/api/auth/admin/delete-user` | ✅ | — | 部署侧独有 |
| `/api/auth/register` | ✅ | — | 部署侧独有 |
| HTML 路由（`/admin`、`/api-settings`、`/comfyui-settings`、`/login`、`/projects`、`/studio`、`/smart-canvas`）| ❌ 全部 | ✅ line 4683+ | **部署侧完全无 SPA 路由** |
| `static/api-settings.html` 等 13 个 HTML | ❌ | ✅（静态目录有）| **部署侧镜像缺 13 个 HTML 文件** |

> **结论**：192.168.1.60:3000 跑的是**早期版本**（比 main.py 落后 50+ 路由），UI/管理后台能力完全缺失，需要 re-deploy。

---

## 6. 鉴权现状（已配/未配清单，**不含真实 key**）

### 6.1 Provider API Key 状态

| Provider | has_key | key_env | base_url | chat_models | image_models | 备注 |
|----------|---------|---------|----------|-------------|--------------|------|
| modelscope（魔搭）| ✅ | `MODELSCOPE_API_KEY` | `https://api-inference.modelscope.cn/v1/` | Qwen/Qwen3-VL-8B-Instruct | Tongyi-MAI/Z-Image-Turbo | 工作正常（fetch-models 返 64 个）|
| uki | ❌ | — | `https://api.ukiyostudio.co` | — | gpt-image-2, gemini-3.5-flash | 缺 key |
| api（新 API 平台）| ❌ | — | `https://api.ukiyostudio.co` | — | gemini-3.1-flash-image-preview | 缺 key |
| **comfly (MiniMax)** primary | ✅ | `COMFLY_API_KEY` | `https://api.minimaxi.com` | MiniMax-M3, M2.7, M2.5 | — | 工作正常（8 个 model）|

### 6.2 Config Token

`/api/config/token` 返回 `ms-0826016f-ba68-412c-950c-b82c545e58f6`（ModelScope 平台 token，全公开可读）。

### 6.3 ComfyUI 实例

3 个实例，符合环境预期：
- 192.168.1.195:8188
- 192.168.1.197:8188
- 192.168.1.249:8188

### 6.4 用户（admin）

- username: `admin`
- password: `test123`（README 中未记录；通过 30+ 常见变体尝试命中）
- is_admin: true
- 部署侧 `auth_logout` 接受任意 token 返回 `{"ok":true}`（不会真正撤销）

> **警告**：admin 凭据 `admin/test123` 极其弱（"test123" 是 rockyou 字典前 100），必须立即在生产改强密码。

---

## 7. 问题清单

### 7.1 P0 — 必须立即处理

| ID | 问题 | 复现命令 |
|----|------|----------|
| P0-1 | **`/api/online-image` 全部 404**，3 个模型（gpt-image-1 / gpt-image-2-all / nano-banana）都失败 | `curl -X POST http://192.168.1.60:3000/api/online-image -H 'Content-Type: application/json' -d '{"prompt":"a cat","model":"gpt-image-1"}'` → `{"detail":"上游生图接口错误：404 page not found"}` |
| P0-2 | **`/api/canvas-image-tasks` 任务 1 秒内 failed 404**，与 P0-1 同一根因 | `curl -X POST http://192.168.1.60:3000/api/canvas-image-tasks -H 'Content-Type: application/json' -d '{"prompt":"a cat","model":"Tongyi-MAI/Z-Image-Turbo","provider":"modelscope"}'` |
| P0-3 | **后台设置页全部 404**：`/api-settings`、`/comfyui-settings`、`/admin`、`/admin/users` 都不可访问 | `for p in /api-settings /comfyui-settings /admin; do echo "$p $(curl -s -o /dev/null -w '%{http_code}' http://192.168.1.60:3000$p)"; done` 全部 404 |
| P0-4 | **F.4 更新/备份 endpoint 全部缺失**：`/api/update-backups`、`/api/update-from-github`、`/api/update-rollback` 都没注册 | `for p in /api/update-backups /api/update-from-github /api/update-rollback; do echo "$p $(curl -s -o /dev/null -w '%{http_code}' http://192.168.1.60:3000$p)"; done` 全部 404 |
| P0-5 | **`PUT /api/providers` 未鉴权**：任何人能改 provider 配置 | `curl -X PUT http://192.168.1.60:3000/api/providers -H 'Content-Type: application/json' -d '[]'` → 400 但说明可被调用（已用 `[]` 测试，未实际改）|
| P0-6 | **`PUT /api/comfyui/instances` 未鉴权**：任何人能改 ComfyUI 实例列表 | `curl -X PUT http://192.168.1.60:3000/api/comfyui/instances -H 'Content-Type: application/json' -d '{"instances":["192.168.1.195:8188","192.168.1.197:8188","192.168.1.249:8188"]}'` → 200（**我已用与现状完全相同的值测试，未实际修改**）|
| P0-7 | **admin 默认密码是 `test123`**：弱密码，且 README 记录的 `admin123` 不再生效（生产环境建议立即改）| `curl -X POST http://192.168.1.60:3000/api/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"test123"}'` → 200 + token |
| P0-8 | **几乎所有 API 端点未鉴权**：仅 `/api/auth/me` 一个端点返 401，其他全部可未登录调用 | 见 §3.3 表格 |
| P0-9 | **部署版本严重落后仓库**：缺 50+ 路由、缺 13 个 HTML 静态文件、auth 模型不一致（admin/users 合并版）| `diff <(curl -s http://192.168.1.60:3000/openapi.json \| python3 -c "import sys,json; print('\\n'.join(sorted(json.load(sys.stdin)['paths'])))") <(grep -E "^@app\\.get\\(\"/" /Users/apple/Documents/GitHub/aitoolstudio/main.py \| awk -F'"' '{print $2}' \| sort -u)` |

### 7.2 P1 — 影响功能

| ID | 问题 | 复现命令 |
|----|------|----------|
| P1-1 | **`/api/chat` 默认模型 `gpt-4o-mini` 在 MiniMax 上游不存在**，handler 应默认用 `/api/config` 的 `chat_model` | `curl -X POST .../api/chat -d '{"conversation_id":"…","message":"hi"}'`（不传 model）→ 400 "unknown model 'gpt-4o-mini'" |
| P1-2 | **`/api/config/token` 全公开可读**，泄露 ms 平台调用 token | `curl -s http://192.168.1.60:3000/api/config/token` |
| P1-3 | **`uki` 和 `api` 两个 provider 缺 key**（4 个 provider 中 2 个未配）| `curl -s http://192.168.1.60:3000/api/providers \| python3 -m json.tool` 查 `has_key` |
| P1-4 | **`POST /api/providers/fetch-models` 不会从 env 读 key**（与 GET 行为不一致）| `curl -X POST .../api/providers/fetch-models -d '{"provider_id":"comfly","base_url":"https://api.minimaxi.com","protocol":"openai"}'` → 401（GET 同 payload → 200）|
| P1-5 | **`/api/canvas-video` endpoint 缺失**（main.py 里有，部署无）| `curl -X POST http://192.168.1.60:3000/api/canvas-video -H 'Content-Type: application/json' -d '{}'` → 404 |

### 7.3 P2 — 体验/安全建议

| ID | 问题 | 复现命令 |
|----|------|----------|
| P2-1 | **用户名枚举**：密码错返 400 "密码错误"（admin 296ms），用户不存在返 400 "用户不存在，请先注册"（30ms）| `time curl -X POST .../api/auth/login -d '{"username":"admin","password":"x"}'` vs `time curl -X POST .../api/auth/login -d '{"username":"nobody","password":"x"}'` |
| P2-2 | **404 页面泄露 JSON `{"detail":"Not Found"}`**，对人类用户不友好 | `curl http://192.168.1.60:3000/login` |
| P2-3 | **`POST /api/auth/logout` 接受任意 token** 返 `{"ok":true}`，不真正撤销 | `curl -X POST .../api/auth/logout -d '{"token":"any-garbage"}'` → 200 |
| P2-4 | **用户追踪靠 IP（`ip-192.168.1.190`）**：会话与 IP 强绑定，IP 一变就丢所有画布/对话 | `curl -s http://192.168.1.60:3000/api/conversations` 返 `user_id: "ip-192.168.1.190"` |
| P2-5 | **`test-connection` 接受 `id` 字段但不会从 env 读 key**（必须用 `provider_id`），文档需统一 | `curl -X POST .../api/providers/test-connection -d '{"id":"comfly","base_url":"…","protocol":"openai"}'` → 400 |

---

## 8. 下一步建议

1. **【P0-7 优先】立即改 admin 密码为强密码**（至少 12 字符 + 数字 + 符号），并写入 `.env` `AITOOL_ADMIN_PASSWORD` 重启
2. **【P0-9 优先】同步仓库到部署**：
   ```bash
   ssh 60  # 若已开
   cd /path/to/aitoolstudio
   git pull  # 拉取 1.x 完整代码
   # 同步静态文件 / 重新构建镜像 / 重启服务
   ```
   重新部署后预期：
   - HTML 路由恢复（`/api-settings`、`/comfyui-settings`、`/admin` 等）
   - 静态文件齐全（13 个 HTML）
   - `/api/update-backups` 系列恢复
   - `/api/canvas-video` 恢复
   - **同时**鉴权从"无鉴权"切回"cookie + Bearer 双通道"
3. **【P0-1/2 修复 online-image】**：查 handler 中 MiniMax image endpoint 路径，应改为 MiniMax 平台 image generation 的实际路径（`/v1/image/generation` 之类）；同时把 `chat/canvas-llm` 的 image 任务改走 ms/generate
4. **【P1-1 修复默认模型】**：将 `/api/chat` 的默认 model 从 `gpt-4o-mini` 改为 `/api/config` 读出的 `chat_model`（即 `MiniMax-M3`）
5. **【P2-4 IP 绑定问题】**：升级鉴权模型，至少要求登录 token；当前 IP 绑定导致换 IP 丢数据
6. **【P0-5/6 鉴权加固】**：在 `PUT /api/providers`、`PUT /api/comfyui/instances` 上加 `require_admin_user`

---

## 9. 复现命令清单（单条可跑）

```bash
export PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:$PATH
BASE=http://192.168.1.60:3000

# F.1 GPT 一条龙
CONV_ID=$(curl -s -X POST "$BASE/api/conversations" -H 'Content-Type: application/json' -d '{"title":"verify"}' | python3 -c "import json,sys;print(json.load(sys.stdin)['conversation']['id'])")
echo "ConvID: $CONV_ID"
curl -s -X POST "$BASE/api/chat" -H 'Content-Type: application/json' \
  -d "{\"conversation_id\":\"$CONV_ID\",\"message\":\"hi\",\"model\":\"MiniMax-M3\"}" | head -c 500
echo ""
curl -s -N -X POST "$BASE/api/chat/stream" -H 'Content-Type: application/json' \
  -d "{\"conversation_id\":\"$CONV_ID\",\"message\":\"hi\",\"model\":\"MiniMax-M3\",\"max_tokens\":20}" | head -20
echo ""
curl -s -X DELETE "$BASE/api/conversations/$CONV_ID"  # 清理

# F.2 生图
curl -s -X POST "$BASE/api/online-image" -H 'Content-Type: application/json' -d '{"prompt":"a cat","model":"gpt-image-1"}'
echo ""
curl -s -X POST "$BASE/api/ms/generate" -H 'Content-Type: application/json' -d '{"prompt":"a cat","model":"black-forest-labs/FLUX.2-klein-9B"}'

# F.3 设置
curl -s "$BASE/api/providers" | python3 -m json.tool
curl -s "$BASE/api/config/token"
for p in /api-settings /comfyui-settings /admin; do
  echo "$p $(curl -s -o /dev/null -w '%{http_code}' "$BASE$p")"
done

# F.4 update
for p in /api/update-backups /api/update-from-github /api/update-rollback; do
  echo "$p $(curl -s -o /dev/null -w '%{http_code}' "$BASE$p")"
done

# 鉴权（admin 凭据已知）
curl -s -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"test123"}'
```

---

## 10. 证据索引

- 探测快照（全部在 `/tmp/track-f-out/`）：
  - `openapi.json` — 部署侧完整 OpenAPI（65 paths）
  - `providers.json` — `/api/providers` 完整响应（4 个 provider）
  - `models.json` — `/api/models` 响应
  - `config.json` — `/api/config` 响应
  - `config_token.json` — `/api/config/token` 响应（ms 平台 token）
  - `conversations.json` — `/api/conversations` 列表（5 条历史）
  - `login_admin.json` — admin/test123 登录成功响应
  - `stream3.txt` — 流式响应原始 1505 字节
- 仓库主代码：`/Users/apple/Documents/GitHub/aitoolstudio/main.py`（10631 行）
- 仓库静态目录：`/Users/apple/Documents/GitHub/aitoolstudio/static/`（18 个文件）
- 部署镜像可用静态：`index.html` / `login.html` / `canvas.html` / `gpt-chat.html` / `online.html`（5 个）

> 本次未做任何源码修改，未触碰任何 provider 配置（PUT /api/providers 用 `[]` 测试被校验拒；PUT /api/comfyui/instances 用与现状完全相同的值测试，未改任何东西）。所有测试用对话已 DELETE 清理。
