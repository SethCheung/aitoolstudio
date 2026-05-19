# Infinite-Canvas 参考方案评估与调整需求

## 1. 结论

`hero8152/Infinite-Canvas` 可以作为能力参考，但不应该作为本项目的直接替换方案。

原因很简单：它是一个独立的便携式应用，不是可嵌入组件库。核心代码集中在：

- `/tmp/infinite-canvas-reference/main.py`
- `/tmp/infinite-canvas-reference/static/canvas.html`

它的后端、前端、配置、模型供应商、画布存储、任务状态都揉在自己的体系里。我们当前项目已经有 Vue、FastAPI、SQLite、Conversation、Generation、CanvasDocument、ComfyUI workflow 等现成架构，直接搬会造成重复系统。

正确做法：

- 保留我们当前项目架构。
- 不复制它的 `main.py` 和 `static/canvas.html`。
- 只抽取它的产品能力设计和关键交互思路。
- 逐步翻译成我们自己的数据模型、API 和 Vue 组件。

说白了：这个库是参考答案，不是作业模板。

## 2. Infinite-Canvas 值得借鉴的能力

### 2.1 LLM 节点

它有独立的 LLM 节点，可以在画布中接收上游文本或图片，再调用 OpenAI-compatible `/chat/completions`。

可借鉴点：

- 画布节点类型新增 `llm`。
- 节点输入可以来自 prompt 节点、图片节点、上游生成结果。
- 支持多模态输入，即图片反推 prompt、图片分析、文字扩写。
- 输出结果可以继续流向 generator/comfy 节点。

我们项目中的落地方式：

- 前端在 `CanvasView.vue` 中新增 LLM 节点 UI。
- 后端新增或复用 canvas 节点运行接口。
- 模型调用走我们已有本地模型 / OpenAI-compatible 配置，不引入它自己的 provider 配置页。

### 2.2 Loop 节点

它有 `loop` 节点，支持循环次数、串行/并行执行、占位符替换。

可借鉴点：

- 变量占位符：
  - `《计数》`
  - `《总数》`
  - `《进度》`
- 串行模式适合逐步演化。
- 并行模式适合批量生成多张图。
- 下游节点可以被循环驱动多次运行。

我们项目中的落地方式：

- 不先做复杂 DAG 队列。
- 先新增 `loop` 节点数据结构和 UI。
- 后端执行时必须加并发上限，不能只靠前端循环。
- 每一轮运行结果都写入 `CanvasRun`，并在绑定项目时写回 `Generation`。

### 2.3 级联执行

它的前端有 `computeCascadeOrder(targetId)` 和 `runNodeCascade(nodeId)` 思路：从目标节点反查上游依赖，再按顺序执行。

可借鉴点：

- 用户点击某个节点运行时，可以自动补跑上游依赖。
- 支持 prompt -> LLM -> generator -> output 这种链路。
- 支持 loop 节点驱动多轮执行。

我们项目中的落地方式：

- 不把级联逻辑塞成几千行前端 JS。
- 后端新增 canvas graph runner service，基于 `CanvasNode` / `CanvasEdge` 计算执行顺序。
- 前端只负责触发、展示状态、轮询结果。

### 2.4 输出节点与结果沉淀

它有输出节点和生成图片追加到画布的行为。

可借鉴点：

- 运行结果不只是弹窗或临时状态，而是成为画布上的可继续操作素材。
- output 节点可以收集上游结果。
- 新生成的图片节点应该自动定位到合理位置。

我们项目中的落地方式：

- Task 3 中，Canvas 运行结果必须写回当前 conversation 的项目历史。
- Task 4 中，对话结果发送到 Canvas 时创建 Media 节点。
- 后续增加 output 节点，把画布运行结果自动挂成图片/视频素材节点。

### 2.5 ComfyUI 自定义 workflow 参数映射

它支持自定义 ComfyUI workflow，并在画布节点中配置参数。

可借鉴点：

- 节点可以绑定不同 workflow。
- 节点参数可以映射到 workflow JSON 的具体 node input。
- 运行前动态替换 prompt、图片、尺寸等参数。

我们项目中的落地方式：

- 继续使用本项目已有的 ComfyUI workflow 管理逻辑。
- 不搬它的 workflow 配置格式。
- 后续可以增强 Canvas workflow 节点的参数面板，让它能选择 Admin 中已有 workflow。

## 3. 明确不要复制的部分

这些东西不要让 agent 搬进来：

- 不复制 `/tmp/infinite-canvas-reference/main.py`。
- 不复制 `/tmp/infinite-canvas-reference/static/canvas.html`。
- 不引入它打包的 `python/`、`packages/`、`.bat`、`.command`。
- 不切换到它的文件型 canvas JSON 存储。
- 不新增它的登录页、API 设置页、ComfyUI 设置页。
- 不引入 ModelScope 等额外供应商，除非后面单独立项。
- 不让前端承担完整执行队列和并发控制。

这几条要写进任务要求里。否则别的 agent 一兴奋开始复制粘贴，后面验收就变成考古。

## 4. 和当前 Task 的关系

当前已完成并验收：

- Task 1：统一项目工作台与对话 / Canvas 切换。
- Task 2：`CanvasDocument` 绑定 `conversation_id`。

接下来应该按下面顺序推进。

## 5. Task 3 调整需求：Canvas 运行结果写回项目历史

### 5.1 目标

Canvas 中运行节点产生的图片或视频，必须属于当前项目 conversation。

用户切回对话模式后，能看到 Canvas 生成结果。首页项目卡片也可以使用 Canvas 结果作为缩略图。

### 5.2 参考 Infinite-Canvas 的点

参考它“运行结果变成画布素材”和“历史记录可追踪”的思路，但不复制它的任务存储。

### 5.3 涉及文件

以远程部署目录为准：

```text
/opt/aitoolstudio/img-platform/backend/api/canvas.py
/opt/aitoolstudio/img-platform/backend/models/canvas.py
/opt/aitoolstudio/img-platform/backend/models/generation.py
/opt/aitoolstudio/img-platform/backend/api/conversation.py
/opt/aitoolstudio/img-platform/backend/schemas/canvas.py
```

如果前端需要展示来源，再改：

```text
/opt/aitoolstudio/img-platform/frontend/src/views/GenerateView.vue
/opt/aitoolstudio/img-platform/frontend/src/views/HomeView.vue
```

### 5.4 交付要求

- `POST /api/canvas/documents/{document_id}/nodes/{node_id}/run` 成功后：
  - 如果 document 有 `conversation_id`，生成结果必须绑定该 conversation。
  - 必须创建或更新可被对话历史读取的数据。
  - 返回值中保留 `generation_id`、结果 URL、结果类型。
- 对话模式拉取项目历史时能包含 Canvas 生成结果。
- 首页项目卡片缩略图逻辑能读到 Canvas 生成的最新图片。

### 5.5 验收

- 在 `/project/<conversation_id>?mode=canvas` 运行一个生成节点。
- 切到 `/project/<conversation_id>?mode=chat`。
- 能看到刚刚 Canvas 生成的图片或视频。
- 刷新页面后仍然存在。
- 查询数据库时该生成记录能追溯到同一个 `conversation_id`。

### 5.6 交付证据

agent 必须给：

- 改动文件列表。
- Canvas run 接口响应示例。
- 数据库中生成记录和 `conversation_id` 的查询结果。
- 后端 `compileall` 结果。
- Docker backend 容器重建 / 重启证据。

## 6. Task 4 调整需求：对话结果发送到 Canvas

### 6.1 目标

对话模式里生成的图片，可以一键发送到当前项目 Canvas，成为 Media 节点。

### 6.2 参考 Infinite-Canvas 的点

参考它“图片结果直接追加为画布节点”的交互，但要使用我们的 `CanvasDocument`、`CanvasNode` 和服务端 API。

### 6.3 涉及文件

```text
/opt/aitoolstudio/img-platform/backend/api/canvas.py
/opt/aitoolstudio/img-platform/backend/schemas/canvas.py
/opt/aitoolstudio/img-platform/frontend/src/views/GenerateView.vue
/opt/aitoolstudio/img-platform/frontend/src/views/CanvasView.vue
/opt/aitoolstudio/img-platform/frontend/src/views/ProjectWorkspaceView.vue
```

### 6.4 后端接口

新增：

```http
POST /api/canvas/documents/{document_id}/media-nodes
```

请求：

```json
{
  "asset_url": "/uploads/comfyui/example.png",
  "title": "Image Result",
  "source": "conversation",
  "source_generation_id": 123,
  "position": { "x": 180, "y": 220 }
}
```

要求：

- 校验 document 属于当前用户。
- 如果 document 绑定了 conversation，校验 generation 也属于同一用户 / 项目。
- 创建 Media 节点。
- 返回新节点，或返回更新后的 canvas graph。
- 不复制图片文件，只引用现有 URL。

### 6.5 前端交互

- Generate 图片结果卡片增加 `发送到 Canvas` 操作。
- 如果当前在项目工作台中，使用当前 `conversationId` 找到对应 CanvasDocument。
- 调用 media node API。
- 成功后跳转到：

```text
/project/<conversation_id>?mode=canvas&focusNode=<node_id>
```

- Canvas 打开后自动定位并选中新节点。

### 6.6 验收

- 在对话模式生成一张图片。
- 点击 `发送到 Canvas`。
- 页面切换到 Canvas 模式。
- 画布中出现图片节点。
- 刷新页面后图片节点仍存在。
- 图片 URL 能正常预览。

## 7. Task 5 调整需求：LLM 节点

### 7.1 目标

Canvas 支持 LLM 节点，用本地模型或 OpenAI-compatible 模型处理文本 / 图片输入。

### 7.2 参考 Infinite-Canvas 的点

参考它的 `/api/canvas-llm` 和 LLM 节点输入输出设计。

### 7.3 落地要求

- Canvas 新增 `llm` node type。
- LLM 节点字段至少包含：
  - `prompt`
  - `model`
  - `system_prompt`
  - `temperature`
  - `use_image_inputs`
- 节点运行时收集上游文本和图片。
- 调用本项目已配置的本地模型服务。
- 输出文本写回节点结果，并可被下游 prompt/generator 节点引用。

### 7.4 非目标

- 不做新的模型供应商管理页。
- 不复制 Infinite-Canvas 的 API 设置 UI。
- 不做复杂 agent 编排。

## 8. Task 6 调整需求：Loop 节点与级联执行

### 8.1 目标

Canvas 支持批量生成和链式运行。

### 8.2 参考 Infinite-Canvas 的点

参考它的：

- loop node
- `computeCascadeOrder`
- `runNodeCascade`
- 串行 / 并行模式
- `《计数》` 等占位符

### 8.3 落地要求

- 新增 `loop` node type。
- 新增后端 graph runner service。
- 执行顺序由后端根据 node/edge 计算。
- 前端只触发运行并展示状态。
- 并发必须有上限。
- 每一轮结果都写入 `CanvasRun`。

### 8.4 建议拆分

先做：

- 手动选中一个目标节点，点击“运行上游链路”。
- 支持普通 DAG 顺序。
- 支持失败中断。

后做：

- loop 节点。
- 并行批量。
- 断点续跑。
- 节点级缓存。

## 9. 给其他 agent 的执行纪律

agent 执行时必须遵守：

- 所有改动以 `192.168.1.60:/opt/aitoolstudio` 为准。
- 修改后必须重建对应 Docker 容器。
- 不允许只改宿主机文件不重启容器就说完成。
- 不允许只给源码 grep，不验证容器内文件。
- 不允许复制 Infinite-Canvas 的整页 HTML 或整份后端。
- 每个 Task 必须单独提交证据。

## 10. 推荐路线

当前最合理顺序：

1. 完成 Task 3：Canvas 结果写回项目历史。
2. 完成 Task 4：对话结果发送到 Canvas。
3. 再做 Task 5：LLM 节点。
4. 最后做 Task 6：Loop 节点和级联执行。

不要先做 LLM / Loop。项目上下文还没打通前，做再多节点都只是玩具功能。

