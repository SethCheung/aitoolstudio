# Infinite-Canvas 操作逻辑融合需求

## 1. 目标

本项目 Canvas 要向 `hero8152/Infinite-Canvas` 的操作逻辑靠齐。

注意，这里的“一样”指用户操作路径、节点工作流和结果流转方式一致，不是复制它的源码。

我们保留现有架构：

- Vue 前端
- FastAPI 后端
- SQLite 数据库
- Docker 部署
- `Conversation`
- `Generation`
- `CanvasDocument`
- `CanvasNode`
- `CanvasEdge`
- `CanvasRun`
- 本项目已有 ComfyUI workflow 管理

不要把 Infinite-Canvas 的 `main.py`、`static/canvas.html`、打包 Python、文件型 canvas JSON 存储搬进来。

## 2. 用户最终应该怎么操作

用户进入 `/project/<conversation_id>?mode=canvas` 后，应该像 Infinite-Canvas 一样完成下面流程：

1. 在画布上添加节点。
2. 用端口连线，把图片、提示词、LLM 输出传给下游节点。
3. 在生成节点里看到上游输入预览。
4. 点击单个节点运行，或者点击终点节点一键运行整条链路。
5. 生成结果进入 Output 节点。
6. Output 里的图片可以预览、拖回画布成为新图片节点。
7. 结果同时写回当前项目历史，对话模式和首页都能看到。

这才叫操作逻辑融合。只加几个按钮不算。

## 3. 画布基础操作对齐

### 3.1 节点新增方式

必须支持这些新增方式：

- 顶部或侧边工具栏添加节点。
- 在空白画布右键或点击添加菜单创建节点。
- 从节点端口拖到空白处时，弹出“创建并连接”菜单。
- 从生成节点输出端口拖到空白处时，可以快速创建 Output 节点并自动连接。

节点默认生成位置：

- 普通添加：当前视口中心附近。
- 端口拖拽创建：鼠标释放位置。
- 从对话发送到 Canvas：当前视口可见区域内，避免叠在已有节点上。

### 3.2 必备节点类型

第一阶段必须整理出统一节点类型枚举：

```text
image       图片素材节点
prompt      提示词节点
llm         LLM 节点
generator   图片生成节点
comfy       ComfyUI workflow 节点
video       视频生成节点
output      输出收集节点
loop        循环节点
group       分组节点，可后置
```

当前项目如果已有不同命名，允许内部兼容，但前端操作层必须向上面这套靠齐。

### 3.3 连线规则

必须实现和 Infinite-Canvas 类似的约束：

```text
image/prompt/loop/llm/output -> generator/comfy/video
generator/comfy/video -> output
generator/comfy -> generator/comfy/video
llm -> generator/comfy/video
image/output/group -> loop（仅 loop 开启图片输入时）
prompt/loop/promptGroup/llm/image/output -> llm
```

必须阻止：

- 自己连自己。
- 会造成生成节点循环依赖的连线。
- 无意义连接，例如 generator 直接连 prompt。

## 4. 生成节点操作对齐

### 4.1 输入预览

生成节点必须显示来自上游的输入：

- 上游 `prompt`：显示提示词摘要。
- 上游 `image`：显示图片缩略图。
- 上游 `llm`：显示 LLM 输出文本。
- 上游 `output`：默认取最近一次输出，作为图片输入。
- 上游 `loop`：显示当前循环渲染后的提示词。

### 4.2 节点参数

图片生成节点至少支持：

- workflow/model 选择
- aspect ratio
- quantity
- seed
- source image
- mask image，可后置

视频节点至少支持：

- workflow/model 选择
- duration
- aspect ratio
- fps，可选
- 首帧/尾帧输入，可后置

Comfy 节点必须复用本项目已有 workflow 管理，不复制 Infinite-Canvas 的 workflow 配置页。

### 4.3 单节点运行

用户点击生成节点运行按钮时：

- 如果没有上游生成依赖，只运行当前节点。
- 如果当前节点属于一条 connected workflow，允许按依赖顺序运行相关上游节点。
- 运行中显示 `queued/running/done/failed` 状态。
- 失败时保留错误信息。

后端必须创建 `CanvasRun`。

## 5. Output 节点操作对齐

### 5.1 Output 节点职责

Output 节点是画布里的结果容器，不只是展示卡片。

它必须支持：

- 接收上游 generator/comfy/video 的结果。
- 以网格展示图片/视频。
- 每个结果保存元信息：
  - url
  - run_id
  - generation_id
  - run duration
  - source node id
  - prompt
  - created_at

### 5.2 结果操作

Output 里的图片必须支持：

- 点击放大预览。
- 复制 URL，可后置。
- 下载，可后置。
- 拖回画布，成为新的 `image` 节点。
- 如果有 source image，后续支持对比预览，可后置。

### 5.3 数据落地

Output 节点内容必须保存到 `CanvasNode.data` 或规范化的子表中。

刷新页面后：

- Output 节点仍显示历史结果。
- 结果仍能拖回画布。
- 对话模式仍能看到对应生成结果。

## 6. LLM 节点操作对齐

### 6.1 LLM 节点模式

LLM 节点至少支持两种模式：

```text
node   节点处理模式：接收上游输入，输出一段文本给下游
chat   聊天模式：节点内部维护对话，可后置
```

第一阶段先做 `node` 模式，`chat` 模式后置。

### 6.2 输入来源

LLM 节点可接收：

- prompt 节点文本
- loop 节点渲染后的文本
- 上游 LLM 输出
- image 节点图片
- output 节点最近图片

### 6.3 输出去向

LLM 输出文本可以连接到：

- generator
- comfy
- video
- 另一个 llm

### 6.4 后端模型调用

后端不复制 `/api/canvas-llm`，但要实现等价能力：

```http
POST /api/canvas/documents/{document_id}/nodes/{node_id}/run
```

当 node type 为 `llm` 时：

- 收集上游文本和图片。
- 调用本项目配置的本地模型或 OpenAI-compatible 服务。
- 保存输出到节点 `data.outputText`。
- 创建 `CanvasRun`。
- 如果 document 绑定 conversation，可选择写入项目历史，但默认不作为图片结果展示。

## 7. Loop 节点操作对齐

### 7.1 Loop 节点字段

Loop 节点必须支持：

```text
count             循环次数
mode              serial | parallel
loopStart         起始计数
imageInput        是否启用图片批量输入
imageBatchSize    每轮消耗图片数量
fixedPrompt       固定提示词
variablePrompt    可变提示词
```

### 7.2 占位符

必须支持 Infinite-Canvas 的占位符：

```text
《计数》
《总数》
《进度》
```

示例：

```text
生成第《计数》张图，共《总数》张，当前进度《进度》
```

### 7.3 串行与并行

串行模式：

- 按轮次运行。
- 每一轮从上游到下游完整执行。
- 失败后停止，显示失败节点。

并行模式：

- 多轮并发执行。
- 必须由后端限制并发。
- 如果涉及 ComfyUI，最大并发不能超过可用 ComfyUI backend 数量。
- 非 Comfy 节点默认最大并发建议为 6。

不要只在前端写循环。前端一刷新就丢状态，这种玩具逻辑不要拿来糊弄。

## 8. 一键级联运行对齐

### 8.1 触发方式

在链路终点生成节点上显示：

```text
一键运行 N 个节点
```

如果上游有 loop：

```text
一键运行 N 个节点 × M 轮
```

### 8.2 执行顺序

后端新增 graph runner，计算执行顺序：

1. 从目标节点反向追溯上游。
2. 找出可运行节点：
   - generator
   - comfy
   - video
   - llm
3. 按拓扑顺序执行。
4. output 节点作为结果中转，不参与模型运行。
5. loop 节点作为执行上下文，不直接调用模型。

### 8.3 运行状态

节点必须显示：

```text
queued
running
done
failed
```

失败后必须支持：

- 从失败节点重试。
- 停止后续链路。
- 保留错误信息。

## 9. 对话 / Canvas 融合要求

这部分继承当前 Task 1-4，不允许退化。

### 9.1 Canvas 到对话

Canvas 生成成功后：

- 创建 `Generation`
- 绑定当前 `conversation_id`
- 创建或更新 `ConversationMessage`
- 更新 `Conversation.updated_at`
- 首页项目卡片能使用最新图片缩略图

### 9.2 对话到 Canvas

对话生成结果点击“发送到 Canvas”后：

- 获取当前 conversation 对应 CanvasDocument
- 创建 `image` 或 `media` 节点
- 跳转到 Canvas 模式
- 定位并选中新节点
- 不复制图片文件，只引用已有 URL

### 9.3 Output 到 Canvas

Output 节点里的图片拖回画布时：

- 创建新的 image 节点
- 使用原 URL
- 保留来源元信息：
  - source_node_id
  - source_generation_id
  - source_run_id

## 10. API 建议

### 10.1 运行单节点

```http
POST /api/canvas/documents/{document_id}/nodes/{node_id}/run
```

继续保留。

### 10.2 创建素材节点

```http
POST /api/canvas/documents/{document_id}/media-nodes
```

继续保留。

### 10.3 级联运行

新增：

```http
POST /api/canvas/documents/{document_id}/nodes/{node_id}/run-cascade
```

请求：

```json
{
  "nodes": [],
  "edges": [],
  "mode": "serial",
  "loop": {
    "enabled": true,
    "count": 3,
    "start": 1,
    "batch_size": 1
  }
}
```

返回：

```json
{
  "cascade_run_id": 12,
  "status": "running",
  "order": ["llm-1", "comfy-1", "video-1"]
}
```

### 10.4 查询级联状态

新增：

```http
GET /api/canvas/cascade-runs/{cascade_run_id}
```

返回：

```json
{
  "id": 12,
  "status": "running",
  "steps": [
    {
      "node_id": "llm-1",
      "status": "done",
      "run_id": 101
    },
    {
      "node_id": "comfy-1",
      "status": "running",
      "run_id": 102
    }
  ]
}
```

第一版如果不做持久化 cascade run，也必须至少返回每个节点的执行结果，并保存到 `CanvasRun`。

## 11. 数据模型建议

### 11.1 CanvasNode.data 约定

节点通用字段：

```json
{
  "status": "queued|running|done|failed",
  "error": "",
  "output": {},
  "results": []
}
```

LLM 节点：

```json
{
  "mode": "node",
  "systemPrompt": "You are a helpful assistant.",
  "userInput": "",
  "outputText": "",
  "model": "local-model-name",
  "temperature": 0.7
}
```

Loop 节点：

```json
{
  "count": 3,
  "mode": "serial",
  "loopStart": 1,
  "imageInput": false,
  "imageBatchSize": 1,
  "fixedPrompt": "",
  "variablePrompt": ""
}
```

Output 节点：

```json
{
  "images": [
    {
      "url": "/uploads/comfyui/example.png",
      "run_id": 12,
      "generation_id": 33,
      "source_node_id": "comfy-1",
      "prompt": "a cinematic product shot",
      "run_ms": 18000,
      "viewed": false
    }
  ]
}
```

## 12. 拆分任务

### Task 3 Fix：补完整项目活跃时间

交付：

- Canvas run 写回项目历史后更新 `Conversation.updated_at`。
- `ConversationMessage.task_id` 记录 `canvas_run:<run_id>` 或 `generation:<generation_id>`。

验收：

- Canvas 生成后项目列表排序更新。
- 数据库能查到 conversation 最新更新时间变化。

### Task 4 Verify/Fix：对话结果发送到 Canvas

交付：

- 验证现有 Task 4 是否完整。
- 如果缺定位、选中、刷新持久化，就补上。

验收：

- 对话图片点击发送到 Canvas。
- Canvas 出现 image/media 节点。
- 刷新后仍存在。
- 节点可连接到 generator/comfy/video。

### Task 5：Output 节点对齐

交付：

- 新增或完善 output 节点。
- Canvas 运行结果自动写入 output 节点。
- Output 图片可拖回画布成为 image 节点。

验收：

- generator/comfy/video 连到 output 后，运行结果进入 output。
- 点击可预览。
- 拖回画布生成新 image 节点。
- 刷新不丢。

### Task 6：LLM 节点对齐

交付：

- 新增 LLM node type。
- 支持上游文本/图片输入。
- 输出文本可连接下游生成节点。
- 调用本地模型或 OpenAI-compatible 模型。

验收：

- prompt -> llm -> comfy 能跑通。
- image -> llm 能生成图片描述或提示词。
- 刷新后 LLM 输出仍存在。

### Task 7：Loop 节点与级联运行

交付：

- 新增 loop node type。
- 支持 `《计数》`、`《总数》`、`《进度》`。
- 支持一键运行整条链路。
- 支持串行 loop。
- 并行 loop 可后置，但接口设计不能堵死。

验收：

- loop -> llm -> comfy 可按 count 多轮生成。
- 终点节点显示一键运行。
- 失败节点能显示错误并允许重试。

### Task 8：交互补齐

交付：

- 端口拖拽到空白处创建并连接节点。
- generator 输出拖到空白处创建 output。
- 节点运行状态徽标。
- 失败重试 / 停止按钮。
- 基础快捷键和删除连线。

验收：

- 不通过顶部菜单，也能靠拖线创建常见工作流。
- 错误状态清晰可见。
- 删除节点会清理相关连线。

## 13. 给执行 agent 的硬性要求

所有实际修改以远程为准：

```text
192.168.1.60:/opt/aitoolstudio
```

交付必须包含：

- 改动文件清单。
- Docker 容器重建证据。
- 容器内源码 grep 证据。
- 后端 `compileall`。
- 前端 build。
- 至少一条真实浏览器操作验收路径。
- 如果涉及生成，必须给数据库查询证据。

禁止：

- 复制 Infinite-Canvas 整个 HTML。
- 复制 Infinite-Canvas 整个 FastAPI 后端。
- 切换掉本项目现有存储模型。
- 只改宿主机不重建容器。
- 只截图不查数据库。

