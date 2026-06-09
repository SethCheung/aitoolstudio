# Product Spec - Comfy Canvas

## 产品定位

基于 Infinite-Canvas 改造一个公司内部使用的项目化 AI 无限画布。

用户创建项目，在项目画布里组织文本、图片、参考素材和 ComfyUI 工作流。管理员在后台维护 ComfyUI 地址、API Key、模型和 workflow。普通用户只负责创作：选择已配置好的 workflow，填写 prompt，上传参考图，调整少量参数，然后运行生成。

一句话：**Infinite-Canvas 做画布底座，我们把它改造成带登录、项目管理、后台配置和 ComfyUI workflow 参数映射的内部创作工具。**

## 第一版范围

### 必须做

| 模块 | 第一版要求 |
|------|------------|
| 登录 | 保留登录，区分普通用户和管理员 |
| 项目管理 | 项目列表、新建项目、重命名、删除或归档、项目缩略图 |
| 无限画布 | 以 Infinite-Canvas 的画布交互为基础，保留拖拽、缩放、节点、连线、素材组织 |
| ComfyUI | 后台配置 ComfyUI 地址，前台运行后台启用的 workflow |
| Workflow 导入 | 管理员后台导入 ComfyUI API-format workflow，或用 RunningHub workflow 引用生成本地化预检 |
| 本地化预检 | 导入后分析缺失自定义节点、模型依赖、ComfyUI 实例兼容性，生成安装计划 |
| 60 盘资源中心 | 模型、workflow、输入素材、输出结果、下载缓存统一放在 192.168.1.60 挂载盘 |
| 参数映射 | 不同 workflow 可以暴露不同参数给普通用户 |
| 简单挑参 | prompt、参考图、steps、cfg、denoise、seed、尺寸、数量，以及 workflow 自定义字段 |
| API 管理 | API Key、provider、模型配置都进入后台，普通用户不配置 |
| 结果复用 | 生成结果落到画布节点里，可以继续连接下游 workflow |

### 第一版不做

| 功能 | 原因 |
|------|------|
| 多人实时协作 | 后期再加，第一版只预留数据结构 |
| 普通用户编辑 workflow JSON | 复杂且危险，必须后台控制 |
| 复杂权限矩阵 | 第一版只区分 owner/admin |
| 独立 Generate 工作台 | 主线是无限画布 |
| voice/music/video 大参数面板 | 后续需要时用画布节点扩展 |
| 统计大屏和配额系统 | 不是第一版核心 |

## 用户角色

| 角色 | 权限 |
|------|------|
| 普通用户 | 登录、创建项目、编辑自己的画布、运行可用 workflow、查看和下载结果 |
| 管理员 | 用户管理、ComfyUI 配置、API/Profile 管理、workflow 导入和参数暴露配置 |

协作能力后期再加。第一版项目默认属于创建者，可以在数据结构里预留成员表，但 UI 不做团队协作。

## 核心流程

### 管理员配置流程

1. 管理员登录后台。
2. 配置 ComfyUI Base URL。
3. 导入 ComfyUI API-format workflow。
4. 给 workflow 配置名称、分类、说明、缩略图。
5. 配置该 workflow 对普通用户暴露哪些参数。
6. 启用 workflow。

### 普通用户创作流程

1. 用户登录后进入项目列表。
2. 新建或打开项目。
3. 在无限画布中添加文本、图片或 workflow 节点。
4. 连接文本/图片到 workflow 节点。
5. 在参数面板中调整该 workflow 暴露的参数。
6. 点击运行。
7. 生成结果作为新节点出现在画布中。
8. 用户继续连线、复用结果或下载。

## Workflow 参数映射

这是第一版最重要的改造点。别天真地以为所有 workflow 都是 prompt + seed + steps。不同 workflow 需要控制的东西不一样。

后台导入 workflow 后，需要允许管理员配置字段：

| 字段类型 | 示例 | 前台控件 |
|----------|------|----------|
| text | prompt、negative prompt | 文本框 |
| image | reference image、mask image、first frame | 图片输入 |
| number | steps、cfg、denoise、weight | 数字输入或滑块 |
| select | sampler、scheduler、checkpoint、LoRA | 下拉框 |
| size | width、height、aspect ratio | 尺寸/比例控件 |
| boolean | watermark、enable upscale | 开关 |
| hidden | 固定节点参数 | 前台不可见 |

参数映射必须保存为 workflow 的配置，而不是写死在前端。

### Workflow 本地化导入

管理员希望把 RunningHub 或外部 ComfyUI workflow 迁移到本地使用。系统需要先做“预检”，别装成什么都能一键搞定。

第一版导入向导支持：

- 粘贴 ComfyUI API-format workflow JSON，或上传 JSON 文件。
- 粘贴 RunningHub `/run/workflow/{id}` / workflowId，尝试通过 RunningHub OpenAPI 拉取 API workflow。
- 粘贴 RunningHub `/post/{id}` 时，如果不能直接拉取 API workflow，明确提示用户上传/粘贴 API workflow JSON。
- 分析 workflow 所需 `class_type`，对比已配置 ComfyUI 实例的 `/object_info`，列出缺失节点。
- 提取常见模型字段，如 checkpoint、LoRA、VAE、CLIP、UNet、ControlNet，并标记为待确认。
- 后台配置 60 盘资源根目录后，导入预检需要检查模型是否已经存在于 `models/*`。
- 保存到后台自定义 workflow 时默认停用，管理员确认字段和依赖后再启用。

第一版不自动执行第三方节点安装、`pip install`、`git clone` 或模型下载。那些动作要等安装计划、白名单、日志和回滚都补上后再做。

## 技术方向

| 层级 | 方向 |
|------|------|
| 基础模板 | `hero8152/Infinite-Canvas` |
| 后端 | 沿用其 FastAPI 单体，逐步模块化 |
| 前端 | 先沿用原生 HTML/JS/CSS，稳定后再决定是否重构 |
| 数据 | 第一版可从 JSON 过渡到 SQLite；登录和项目建议优先 SQLite |
| 资源盘 | `192.168.1.60` 作为资产中心；ComfyUI 算力节点只挂载读取 |
| ComfyUI | 后端调用 `/prompt`、`/history/{prompt_id}`、`/view`、`/system_stats` |
| 部署 | 先保持原项目启动方式，后续补 Docker Compose |

## 验收标准

第一版跑通时必须满足：

- 用户可以登录。
- 用户可以创建项目并进入项目画布。
- 画布状态能按项目保存和恢复。
- 管理员可以导入一个 ComfyUI workflow。
- 管理员可以通过导入向导看到 workflow 的节点兼容性和模型依赖清单。
- 管理员可以配置该 workflow 的可见参数。
- 普通用户可以在画布中选择该 workflow，并调整参数运行。
- 生成结果能出现在画布中，并能继续作为下游输入。
- 普通用户看不到 API Key、provider 配置和 workflow JSON 编辑入口。

## 风险

| 风险 | 处理 |
|------|------|
| Infinite-Canvas 当前没有明确顶层 LICENSE | 先作为内部模板使用，发布或商用前必须确认授权 |
| 原项目是单体 FastAPI + 原生 JS | 第一阶段先改功能，不急着架构洁癖重构 |
| workflow 参数差异大 | 必须做后台参数映射层，不能前端写死 |
| RunningHub post 页面不一定暴露 API workflow | 不能假成功，提示用户导出或上传 API-format JSON |
| 自动安装 custom node 等于执行第三方代码 | 第一版只生成安装计划，后续必须加白名单、审计、回滚 |
| 模型文件可能受版权、登录或授权限制 | 只标记依赖和 SMB 映射，不绕过授权下载 |
| 旧项目内容已经删除 | 已在仓库外备份，可回滚 |
