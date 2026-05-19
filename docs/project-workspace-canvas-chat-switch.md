# 项目内对话 / Canvas 双模式切换需求与任务拆分

## 1. 背景

当前平台已经有两套核心工作界面：

- `/generate`：对话式生成工作台，围绕 `conversation` 展示 prompt、生成记录和底部生成框。
- `/canvas`：流水线无限画布，围绕 `canvas_documents` 保存节点、连线、运行记录和结果。

现在的问题不是“再做一个 canvas”，而是两个界面割裂。用户希望在同一个项目中，在对话模式和画布模式之间切换，并共享同一批生成结果、项目标题、模型配置和 workflow。

## 2. 目标

把“项目”作为一级工作上下文，同一个项目内提供两种工作模式：

- 对话模式：沿用现有 Generate 对话生成体验。
- Canvas 模式：沿用现有 `/canvas` 流水线工作台体验。

用户从首页进入一个项目后，不应该感觉自己跳到另一个产品里。模式切换要像同一个工作台里的 Tab，而不是两个互不认识的页面。

## 3. 非目标

本轮不要做这些事：

- 不重写 GenerateView 的生成逻辑。
- 不重写 CanvasView 的节点拖拽、连线、运行逻辑。
- 不新增复杂 DAG 队列。
- 不做完整权限系统重构。
- 不改 ComfyUI workflow JSON 参数映射体系。
- 不强制迁移旧 localStorage 画布，只做向服务端项目绑定的主路径，localStorage 继续作为降级缓存。

说白了：先把两个房间打通，别顺手盖一栋楼。

## 4. 用户故事

### 4.1 从首页进入项目

用户在首页点击已有项目卡片后，进入统一项目工作台。

预期：

- 默认进入对话模式。
- 顶部显示项目标题。
- 顶部或左侧提供 `对话 / Canvas` 切换。
- 切换到 Canvas 后仍处于同一个项目上下文。

### 4.2 对话和 Canvas 互相切换

用户在一个项目里生成图片后，可以切到 Canvas 继续编排。

预期：

- URL 能体现项目上下文，例如：
  - `/project/:conversationId?mode=chat`
  - `/project/:conversationId?mode=canvas`
- 也可以保留兼容路由：
  - `/generate?convId=123` 重定向或进入 `/project/123?mode=chat`
  - `/canvas?convId=123` 进入 `/project/123?mode=canvas`
- 切换模式不丢当前项目标题和登录态。

### 4.3 对话结果送入 Canvas

用户在对话生成结果中看到某张图片，可以把它作为 Canvas 素材节点。

预期：

- 每张图片结果提供 `发送到 Canvas` 操作。
- 点击后在当前项目绑定的 Canvas 文档中创建一个 Media 节点。
- 创建成功后切换到 Canvas 模式，并选中或定位到该 Media 节点。
- 不要复制文件，只引用现有 `/uploads/...` 或 `/minimax-output/...` URL。

### 4.4 Canvas 结果回到项目历史

用户在 Canvas 中运行 Workflow 节点生成图片或视频后，结果必须属于同一个项目。

预期：

- `CanvasRun` 继续记录运行过程。
- `Generation` 记录绑定当前项目 / conversation。
- 对话模式刷新后能看到 Canvas 生成结果。
- 首页项目卡片缩略图可以使用 Canvas 生成结果。

## 5. 数据模型要求

### 5.1 推荐最小改动

在现有 `CanvasDocument` 上增加：

```text
conversation_id: int | null
```

关系：

```text
Conversation
  ├── ConversationMessage[]
  ├── Generation[]
  └── CanvasDocument[]
```

如果当前 `Generation` 还没有稳定绑定 `conversation_id`，本轮至少要在 Canvas 运行成功时写入可以被项目历史读取的关系；如果只能先通过 message 保存，也要在交付说明中写清楚。

### 5.2 约束

- 一个 conversation 默认创建一个主 CanvasDocument。
- 同一用户只能访问自己的 conversation 和对应 CanvasDocument。
- 后端创建 CanvasDocument 时，如果传入 `conversation_id`，必须校验该 conversation 属于当前用户。
- 老的无 `conversation_id` CanvasDocument 可以继续显示在 `/canvas` 兼容路径中，不要删。

## 6. API 设计

### 6.1 获取或创建项目 Canvas

新增或扩展：

```http
GET /api/canvas/documents/by-conversation/{conversation_id}
```

行为：

- 如果当前用户已有该 conversation 的 CanvasDocument，返回它。
- 如果没有，创建一个默认 CanvasDocument 并返回。
- 返回结构沿用 `CanvasGraphResponse`。

### 6.2 创建 Canvas Media 节点

新增：

```http
POST /api/canvas/documents/{document_id}/media-nodes
```

请求：

```json
{
  "asset_url": "/uploads/comfyui/xxx.png",
  "title": "Image Result",
  "source": "conversation",
  "source_generation_id": 123,
  "position": { "x": 180, "y": 220 }
}
```

行为：

- 校验 document 属于当前用户。
- 创建 Media 节点。
- 返回更新后的 CanvasGraphResponse，或返回新节点 payload。

### 6.3 Canvas 节点运行绑定项目

扩展：

```http
POST /api/canvas/documents/{document_id}/nodes/{node_id}/run
```

要求：

- 如果 CanvasDocument 有 `conversation_id`，运行成功创建的 Generation / message 必须绑定该 conversation。
- 返回中继续保留 `generation_id`、`urls`、`result_type`。

## 7. 前端设计要求

### 7.1 新增项目工作台壳层

建议新增：

```text
frontend/src/views/ProjectWorkspaceView.vue
```

职责：

- 读取 `conversationId`。
- 展示项目标题和模式切换。
- 根据 mode 渲染 Generate 或 Canvas。
- 不承载具体生成逻辑。

推荐路由：

```text
/project/:conversationId
```

query：

```text
?mode=chat
?mode=canvas
```

### 7.2 GenerateView 改造边界

GenerateView 需要支持从 props 或 route 接收 conversationId。

要求：

- 不能破坏 `/generate?convId=xxx` 旧入口。
- 如果被 ProjectWorkspaceView 包裹，隐藏重复的全局顶部导航，只保留生成内容区。
- 对话记录、保存消息、生成结果都使用当前 conversationId。
- 图片结果增加 `发送到 Canvas` 按钮。

### 7.3 CanvasView 改造边界

CanvasView 需要支持从 props 或 route 接收 conversationId。

要求：

- 如果有 conversationId，优先调用 `/api/canvas/documents/by-conversation/{conversationId}`。
- 如果没有 conversationId，保持现有 `/api/canvas/documents` 默认逻辑。
- 运行节点时沿用当前 documentId。
- 支持接收 “从对话发送来的素材节点” 后定位到节点。

### 7.4 首页入口

HomeView 调整：

- 点击项目卡片进入 `/project/:id?mode=chat`。
- “新建项目”创建 conversation 后进入 `/project/:id?mode=chat`。
- “打开 Canvas”如果没有项目上下文，需要先创建或选择项目，不要直接进全局 `/canvas` 当默认路径。

## 8. 任务拆分

### Task 1：需求与路由骨架

涉及文件：

- `Product-Spec.md`
- `DEV-PLAN.md`
- `frontend/src/router/index.ts`
- `frontend/src/views/ProjectWorkspaceView.vue`
- `frontend/src/views/HomeView.vue`

交付：

- 新增 `/project/:conversationId` 路由。
- 首页项目入口改到项目工作台。
- 工作台顶部提供 `对话 / Canvas` 切换。
- 旧 `/generate`、`/canvas` 入口保持可用。

验收：

- 点击首页已有项目进入项目工作台。
- 切换 mode 不刷新登录态。
- `/generate?convId=123` 仍可访问。
- `/canvas` 仍可访问。

### Task 2：CanvasDocument 绑定 conversation

涉及文件：

- `backend/models/canvas.py`
- `backend/schemas/canvas.py`
- `backend/api/canvas.py`
- `backend/models/conversation.py`

交付：

- `CanvasDocument` 增加 `conversation_id`。
- 新增 `GET /api/canvas/documents/by-conversation/{conversation_id}`。
- 创建和读取时校验用户权限。
- 保持旧 document API 不坏。

验收：

- 同一个 conversation 多次打开 Canvas 返回同一个 document。
- 不同 conversation 拿到不同 document。
- 用户 A 不能访问用户 B 的 conversation canvas。

### Task 3：Canvas 运行结果写回项目历史

涉及文件：

- `backend/api/canvas.py`
- `backend/models/generation.py`
- `backend/api/conversation.py`
- 可能涉及 `backend/schemas/generation.py`

交付：

- Canvas 节点运行成功后，Generation 绑定当前 conversation。
- 对话模式能展示 Canvas 生成结果。
- 首页项目卡片可使用 Canvas 结果作为缩略图。

验收：

- 在项目 Canvas 中运行 Workflow 节点。
- 切回对话模式后能看到对应结果。
- 刷新页面后结果仍在。

### Task 4：对话结果发送到 Canvas

涉及文件：

- `frontend/src/views/GenerateView.vue`
- `frontend/src/views/CanvasView.vue`
- `backend/api/canvas.py`
- `backend/schemas/canvas.py`

交付：

- Generate 图片结果增加 `发送到 Canvas`。
- 后端新增创建 Media 节点接口。
- 成功后切换到当前项目 Canvas 模式。
- Canvas 自动展示新 Media 节点。

验收：

- 对话生成结果点击 `发送到 Canvas`。
- 页面进入 Canvas 模式。
- 画布中出现对应 Media 节点。
- 节点图片 URL 可正常预览。

### Task 5：兼容与回归

涉及文件：

- 所有上述改动文件
- `frontend/vite.config.ts`
- `frontend/nginx.conf`

交付：

- 旧路由兼容。
- 构建通过。
- 后端编译通过。
- 不破坏 `/canvas/` 统一入口。

验收命令：

```bash
cd img-platform/frontend && npm run build
cd ../backend && python3 -m compileall api services models schemas main.py
```

浏览器验收：

- `http://192.168.1.60:5173/`
- `http://192.168.1.60:5173/project/<id>?mode=chat`
- `http://192.168.1.60:5173/project/<id>?mode=canvas`
- `http://192.168.1.60:5173/canvas/`

## 9. 交付给验收方的证据

别只说“已完成”。每个 agent 交付时必须给：

- 改动文件清单。
- 新增或变更 API 清单。
- 数据库字段变更说明。
- 构建命令结果。
- 3 条手动验收路径截图或文字步骤。
- 已知风险。

## 10. 验收标准总表

| 验收点 | 必须结果 |
|---|---|
| 项目入口 | 首页项目卡片进入统一工作台 |
| 模式切换 | 同项目内可切换对话和 Canvas |
| 数据绑定 | 每个项目有自己的 CanvasDocument |
| 对话到 Canvas | 对话生成图片可发送为 Media 节点 |
| Canvas 到对话 | Canvas 生成结果可在对话历史中看到 |
| 权限 | 用户只能访问自己的项目和画布 |
| 兼容 | 旧 `/generate`、`/canvas` 不失效 |
| 构建 | 前端 build 和后端 compileall 通过 |

