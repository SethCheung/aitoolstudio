# Product Spec - 内网 AI 生图协作平台

## 产品概述

这是一个部署在公司内网的 AI 生图协作平台，整合 ComfyUI 工作流引擎和 MiniMax API 能力，为 10 人左右的设计/创作团队提供统一的生图工具。

**目标用户**：公司内部的 designer、内容创作者、营销人员等需要快速生成高质量图像的员工。他们可能有 AI 生图经验，但不想自己折腾 ComfyUI 的复杂节点；或者完全不懂 AI，需要简单可控的生图工具。

**核心价值**：管理员统一管理工作流和模型，用户无需学习 ComfyUI 即可使用预设的高质量工作流；MiniMax API 提供提示词优化和图像理解能力，降低使用门槛；所有生成内容集中管理，便于团队复用和协作。

## 当前 MVP 状态（2026-05-05）

当前代码已从最初的“ComfyUI + MiniMax 生图平台”扩展为一个 MiniMax 多模态生成 MVP。后续开发必须区分“已实现能力”和“规划能力”，不要把规划当成已经可用。

### 已实现

| 模块 | 当前表现 |
|------|----------|
| **登录认证** | 用户通过用户名和密码登录，前端保存 JWT Token，后端保护生成、历史、Profile 和 Admin 接口 |
| **后台用户管理** | 管理员通过 `/admin` 的 Users / All Users 界面查看全部账号，支持搜索、创建用户、编辑/重置密码、授予/撤销管理员权限和删除账号；关键危险操作有后端保护 |
| **项目首页** | 登录后进入项目首页，展示当前用户的对话项目；如果项目中已有生成图片，卡片显示第一张图片缩略图 |
| **生成工作台** | 用户可在同一页面选择 image / voice / video / music 分类、模型和参数后发起生成；Generate 页面采用顶部项目名 + 搜索 + 生成记录流 + 底部停靠生成框 |
| **提示词优化** | 用户可点击「AI enhance」显式调用文本模型扩写当前输入，优化结果回填输入框，用户确认后再生成 |
| **图片生成参数** | image 分类对齐 MiniMax 官方图片调试台，支持参考图微缩预览、URL/拖拽添加参考图、`1x / 2x / 3x / 4x` 快捷数量、1-9 自定义数量、官方 Prompt 优化、Seed、AIGC 水印、宽高比和 image-01 自定义尺寸 |
| **本地 ComfyUI 直连** | image 分类 `comfyui-local` 模型入口，默认连接 `http://192.168.1.195:8188`，后端通过 ComfyUI HTTP API 提交工作流，支持选择 checkpoint，生成结果下载到本平台 `/uploads/comfyui` 后按现有图片网格展示 |
| **ComfyUI 操作者参数** | 用户可在 Generate 页"图片高级设置"和 Canvas Workflow/Video 节点面板中调整 `Steps`（采样步数 1-100，默认 28）、`CFG`（提示词遵循强度 0-30，默认 7）、`Denoise`（重绘强度 0-1，默认 1）；后端 `runtime_workflow()` 通过 patch KSampler 和占位符 `{{steps}}`/`{{cfg}}`/`{{denoise}}` 注入，范围校验在后端 schema 和前端 input min/max 双保险 |
| **ComfyUI Workflow 管理** | 管理员可在 `/admin` 的 Workflows 面板管理 ComfyUI API-format workflow JSON：支持启停、编辑、删除、Validate JSON 校验、Duplicate 复制（默认 disabled），可从 SMB 固定目录 `团队文件-SJM-MediaFile/Comfyui_Workflows` 同步导入；后端自动计算 workflow summary（节点数、输出类型、required inputs、patchable inputs），Admin 面板以彩色徽标展示，Canvas 画布插入 workflow 节点时根据 summary 给出上游依赖提示（需要图片节点/蒙版）；编辑时 sort_order 不重置；生成页选择 `comfyui-local` 后可选择启用的 workflow |
| **ERNIE Image 工作流** | 本地 ComfyUI 检测到 `ComfyUI-ERNIE-Image` 自定义节点后，平台内置 `ERNIE Image` workflow 模板，使用 `baidu/ERNIE-Image` 模型路径，运行时注入 prompt、宽高和 seed |
| **ComfyUI 模型路径快捷管理** | 管理员可在 `/admin` 的 Paths 面板保存 SMB 模型目录和 195 服务器本地挂载路径备注，首个默认快捷路径指向 `smb://192.168.1.60/团队文件-SJM-MediaFile/Comfyui_Model/audio_encoders` |
| **ComfyUI GPU 状态** | `comfyui-local` 状态条展示在线状态、VRAM 已用/总量、占用百分比和 Torch VRAM，生成中每 2 秒刷新，帮助用户判断本地 GPU 是否正在工作 |
| **ComfyUI Upscale** | 图片结果中的 Upscale 按钮接入 ComfyUI 原生 `ImageScale` 工作流，默认 2x `lanczos` 放大，结果作为新生成记录展示 |
| **Flux 局部重绘** | 用户选择 `Flux 局部重绘` workflow 后上传原图，默认在居中的图片画布上直接涂抹要修改的区域；也可切换为点选目标，由后端生成 SAM 提示遮罩后提交 ComfyUI |
| **流水线无限画布** | Canvas 画布必须绑定项目（conversation），不允许独立工作区。主入口为 `/project/:conversationId?mode=canvas`，从项目卡片进入画布模式。画布使用无限画布承载 Text / Media / Workflow / Video 节点；左侧"工作流"tab 必须读取平台现有 `/api/comfyui/workflows`，按已启用 ComfyUI workflow 生成可插入节点；画布文档、节点、连线、运行记录和结果由 `/api/canvas` 保存并关联当前 conversation，不能和后台 workflow 管理割裂。返回按钮回到项目列表页 |
| **视频生成参数面板** | video 分类对齐 MiniMax 官方视频调试方案，支持文生视频、首帧图生视频、首尾帧视频、主体参考视频、官方 Prompt 优化、快速预处理、时长和分辨率 |
| **语音生成参数面板** | voice 分类对齐 MiniMax 官方同步语音调试台，支持模型、音色、情绪、语速、音量、音调、格式、采样率、比特率、声道、字幕、LaTeX 朗读、语言增强、发音词典、声音效果和语气词标签 |
| **音乐生成参数面板** | music 分类对齐 MiniMax 官方音乐调试台，支持歌曲模板、歌词结构标签、风格描述、歌词、纯音乐模式、AI 歌词优化、采样率、比特率、音频格式、返回格式、Seed 和 AI 音频水印 |
| **取消生成** | 生成过程中前端可取消当前请求，立即停止等待并在记录中标记“已取消生成” |
| **图片结果预览** | 生成图片以稳定比例网格展示；点击图片本身或“放大”按钮后在当前页面打开原图预览层，可点背景、关闭按钮或按 Esc 退出 |
| **生成历史** | 用户 prompt 和 AI 结果保存为 conversation / conversation_messages，可从首页项目卡片或 Generate 页面恢复 |
| **Profile 管理** | 管理员通过前端 `/admin` 管理模型供应商 Profile，支持 HTTP API 和 CLI 路由；各分类除预设模型外必须支持手动填写自定义模型 ID，用于后续接入其他供应商模型 |
| **权限加固** | `/api/admin/*` 和 `/api/profiles` 管理接口要求管理员；`/api/profiles/models` 要求登录 |

### 未实现或仅规划

| 模块 | 当前状态 |
|------|----------|
| **ComfyUI 工作流高级管理** | summary 计算、validate/duplicate 接口、Admin 徽标展示和 Canvas 上游依赖提示已完成；完整节点参数映射 UI（将 workflow 参数暴露为表单控件）、图生图/inpainting/ControlNet 专用参数表单和生成队列管理仍未完成 |
| **ControlNet / LoRA** | 属于规划能力，当前 UI/后端未形成完整闭环；Upscale 已完成第一版 ComfyUI ImageScale 放大；Flux 局部重绘已完成第一版涂抹/点选交互 |
| **图像理解/自动标签** | 规划中，当前未形成独立 API 和 UI 流程 |
| **批量提示词任务、提示词库、收藏、下载 ZIP** | 规划中；当前只实现单 prompt 下的 `1x / 2x / 4x` 多图数量 |
| **GPU 监控、系统日志、队列管理** | 规划中 |
| **生成文件鉴权** | 当前 `/minimax-output` 仍是公开静态目录，生产前必须改为受控文件代理 |

## 应用场景

- **营销素材生成**：运营小张需要为新品发布制作社交媒体配图。他登录平台，在底部生成框输入"做一个电商海报，产品是运动鞋，背景要科技感"，AI prompt enhance 后得到详细 prompt，选择"电商海报"工作流，1 分钟后得到高质量宣传图。

- **设计灵感探索**：设计师小李需要为项目找参考风格。他上传一张竞品图片，系统自动分析风格标签并推荐相似的工作流和参数，快速生成多个变体进行对比。

- **批量内容生产**：内容团队需要为 10 篇文章生成封面图。团队成员选择"文章封面"工作流，批量输入标题和关键词，自动生成风格统一的封面图集合。

- **设计资产沉淀**：团队积累的优秀工作流和提示词可以保存为模板，新人可以直接复用，避免重复摸索。管理员可以看到每个人的生成历史和使用统计。

## 功能需求

### 核心功能

| 功能 | 用户做什么 → 系统做什么 → 得到什么 |
|------|-----------------------------------|
| **生成工作台生图** | 用户在底部生成框输入描述（如"做一个电商海报，产品是运动鞋"）→ 可点击 AI enhance 扩写 prompt → 点击生成 → 当前引擎生成图像 → 得到高质量生图 |
| **文生图 (txt2img)** | 用户输入提示词 + 选择工作流 → 点击生成 → ComfyUI 执行 → 得到图像 |
| **图生图 (img2img)** | 用户上传参考图 + 输入提示词 → 选择工作流 → 生成 → 得到基于原图的变体 |
| **局部重绘 (inpainting)** | 用户上传图像 + 涂抹需要修改的区域 → 输入修改描述 → 生成 → 得到局部修改后的图像 |
| **高清修复/放大 (upscale)** | 用户选择已生成的图像 → 点击 Upscale → 系统调用 ComfyUI `LoadImage → ImageScale → SaveImage` 工作流 → 得到 2x 放大版本 |
| **ControlNet 控制** | 用户上传姿态图/边缘图/深度图 → 选择对应 ControlNet 模型 → 生成 → 得到符合控制条件的图像 |
| **LoRA 模型支持** | 用户在下拉框选择 LoRA 模型 → 调整权重 → 生成 → 得到具有特定风格的图像 |
| **图片参数选择** | 用户输入单条提示词 → 可拖入参考图或粘贴参考图 URL → 选择比例/自定义尺寸、Seed、数量和官方 Prompt 优化 → 点击生成 → 得到对应参数的图片 |
| **批量生成** | 用户输入多条提示词或上传多个参考图 → 设置批量任务 → 生成 → 得到多组图像（规划中，当前未实现） |
| **提示词优化** | 用户输入简单描述 → 点击「AI enhance」 → 文本模型扩写为详细 prompt 并回填输入框 → 用户可继续编辑或点击生成 |
| **图像理解/自动标签** | 用户上传或生成图像 → 系统自动调用 MiniMax 视觉模型分析 → 得到自动标签和描述（用于分类和搜索） |
| **MiniMax image-01 生图** | 用户在生成框选择 image 分类和 MiniMax 图像模型 → 输入提示词和可选参考图 → 调用 MiniMax `/v1/image_generation`，支持 `subject_reference`、`width/height`、`seed`、`n`、`prompt_optimizer` → 得到另一种风格的生图（作为 ComfyUI 的备选） |
| **本地 ComfyUI 生图** | 用户在 image 分类选择 `comfyui-local` → 输入提示词、选择比例/数量/Seed 或自定义尺寸 → 后端提交到 `192.168.1.195:8188` 的 ComfyUI `/prompt` → 轮询 `/history/{prompt_id}` → 下载 `/view` 输出图到本平台并展示 |
| **MiniMax 同步语音生成** | 用户在生成框选择 voice 分类 → 输入要合成的文本，可插入停顿 `<#0.5#>` 和官方语气词标签 → 选择模型、音色、情绪和音频规格 → 调用 MiniMax `/v1/t2a_v2` → 得到可在线播放/下载的音频 |
| **MiniMax 视频生成** | 用户在生成框选择 video 分类 → 选择文生视频、首帧、首尾帧或主体参考模式 → 调用 MiniMax `/v1/video_generation` 创建异步任务 → 轮询 `/v1/query/video_generation` → 成功后用 `file_id` 调用 `/v1/files/retrieve` → 下载视频到本平台 `/uploads/videos` 并展示播放器 |
| **MiniMax 音乐生成** | 用户在生成框选择 music 分类 → 输入音乐风格描述，填写或用 AI 优化歌词，可选择纯音乐、Seed、音频规格和水印 → 调用 MiniMax `/v1/music_generation` → 得到可在线播放/下载的音乐 |
| **历史记录/图库管理** | 用户登录后查看项目首页/我的作品 → 系统展示所有生成记录，有图片结果的项目显示缩略图 → 可进入项目继续生成或查看历史 |
| **原图预览** | 用户点击生成结果图片或“放大”按钮 → 系统在当前页面打开原图预览层 → 用户可检查细节并关闭返回生成记录 |
| **提示词保存/复用** | 用户点击"保存提示词" → 填写名称和标签 → 保存到个人/公共库 → 后续可一键调用 |

### 辅助功能

| 功能 | 说明 |
|------|------|
| **账号登录** | 管理员创建账号，用户输入用户名 + 密码登录后看到所有项目和个人历史 |
| **工作流选择** | 下拉框选择管理员预设的工作流，显示工作流名称和简要说明 |
| **流水线工作流选择** | 用户从项目卡片进入画布模式（`/project/:conversationId?mode=canvas`），在左侧"工作流"tab 选择现有 ComfyUI workflow → 系统在画布中插入对应 Workflow 节点 → 节点展示分类、节点数量、说明和备注，并可与 Text / Media 节点连线；执行时后端读取节点绑定的 `workflow_id`、上游 Text 和 Media，提交本地 ComfyUI 并生成结果节点 |
| **节点生成输入框** | 用户选中 Video / Workflow 节点后，画布下方展示 RunningHub 风格生成输入框：顶部模式标签（如“全能参考”“文生视频”）、素材库入口、中间 prompt 输入区、底部模型/规格/数量/提交任务按钮；输入框参数必须结合节点绑定的 workflow/category，并通过 `/api/canvas/documents/{id}/nodes/{node_id}/run` 写入运行记录。平台为公司内网使用，不展示计费或扣费逻辑 |
| **电商套图模板** | 用户从工作流面板选择“电商套图模板” → 系统生成产品信息 Text、产品图 Media、模特/侧面/俯瞰提示词和三个 Workflow 节点 → 用户补产品图和文案后逐个运行节点，得到可继续接入下游的结果节点 |
| **流水线 Agent 助手** | 画布模式右下角提供 Agent 助手入口，读取当前画布节点、连线、选中节点和可用 workflow 摘要，通过 `/api/prompt/canvas-agent` 调用 MiniMax 文本模型给用户下一步建议、prompt 改写方向和 workflow 选择提示；回答必须中文、短、具体 |
| **参数调节** | 滑动条/输入框调整采样步数、CFG、种子等 ComfyUI 参数（可选显示） |
| **生成队列** | 多用户同时生成时显示排队状态，预估等待时间 |
| **下载/分享** | 单张或批量下载 PNG 格式，支持复制链接分享给团队成员 |
| **API 接口** | 提供 REST API 供其他系统调用生图能力（需管理员开启） |

## UI 布局

### 整体布局

**生成工作台布局**（参考作品流/生成历史工作台），单栏流式布局：
- 顶部：项目名称编辑、生成记录搜索框、返回主页按钮
- 中间：生成记录流，最新生成在上，旧生成自然滚动到下方
- 底部：停靠式生成框（多行文本框 + AI enhance + 参数选择 + 生成按钮）

### 顶部导航栏
- 左侧：当前项目名称，可点击编辑
- 中间：搜索框，用于搜索当前生成记录
- 右侧：返回主页按钮
- 当前 Generate 页暂不展示未完成的用户菜单和语言切换入口

### 中间生成记录区
- **记录排序**：最新生成显示在顶部，旧记录向下滚动
- **记录信息**：展示 prompt、模型、比例、风格和生成时间
- **图片网格**：按比例稳定展示图片预览，支持 `1x / 2x / 3x / 4x` 快捷数量和 1-9 自定义数量
- **记录操作**：重新生成、生成变体、下载全部、复用提示词
- **单图操作**：点击图片查看原图；底部操作包括放大、变体、Upscale（当前仅占位）、下载
- **加载状态**：生成中的记录显示稳定高度占位，并提供“取消生成”按钮

### 原图预览层
- 触发：点击生成结果中的任意图片或“放大”按钮
- 展示：深色半透明覆盖层，居中展示原图，顶部显示文件名和关闭按钮
- 关闭：点击背景、点击关闭按钮或按 Esc
- 约束：不跳转页面，不打开新窗口，用户关闭后回到原生成记录位置

### 底部输入区
- 多行文本框：placeholder"描述你想要生成的图像..."，支持上传、拖入或粘贴 URL 添加参考图，参考图在对话框顶部微缩展示
- 功能按钮（文本框下方）：
  - 「AI enhance」按钮：显式扩写当前提示词；优化后回填输入框，不自动生图
  - 「上传图片」按钮：上传参考图用于图生图/inpainting
  - 分类选择：image / voice / video / music
  - 画风选择、宽高比选择、模型选择
  - 图片数量选择：`1x / 2x / 3x / 4x` + 1-9 自定义输入
  - image 分类下展示 MiniMax 官方图片参数：参考图 `subject_reference`、官方 Prompt 优化、自定义尺寸、Seed、AIGC 水印、image-01-live 画风权重
  - voice 分类下展示 MiniMax 官方 T2A 参数：音色、情绪、语速、音量、音调、音频格式、采样率、比特率、声道、字幕、LaTeX 朗读、语言增强、发音词典、声音效果和语气词标签
  - video 分类下展示 MiniMax 官方视频参数：文生视频、首帧图生视频、首尾帧视频、主体参考视频、`prompt_optimizer`、`fast_pretreatment`、`duration`、`resolution`
  - music 分类下展示 MiniMax 官方音乐参数：歌曲模板、歌词结构标签、纯音乐模式、AI 歌词优化、歌词、采样率、比特率、格式、返回格式、Seed、AI 音频水印和 music-cover 参考音频 URL
- 生成按钮：靠右对齐，醒目样式
- 取消按钮：生成中替换主按钮为“取消生成”，用于中途停止当前请求等待

## 用户使用流程

### 首次使用
1. 管理员创建账号，告知用户名和初始密码
2. 用户访问内网地址，输入账号密码登录
3. 进入首页，查看新手引导（可跳过）

### 快速生图
1. 在底部输入框描述想要的图像（如"做一个电商海报，产品是运动鞋，背景要科技感"）
2. 选择工作流（如"电商海报"）
3. 点击「AI enhance」（可选，让 MiniMax 扩写提示词）
4. 检查优化后的 prompt，必要时继续编辑
5. 点击生成按钮
6. 等待生成完成（显示进度条，约 30-60 秒）
7. 查看生成的图像，满意则下载，不满意则调整描述重新生成

### 图生图/局部重绘
1. 点击「上传图片」按钮上传参考图
2. 输入修改描述（如"把背景换成海滩"）
3. 选择工作流（如"图生图"或"inpainting"）
4. 点击生成
5. 查看生成结果

### 浏览历史
1. 进入首页查看所有项目卡片
2. 有图片结果的项目显示第一张生成图缩略图
3. 点击项目卡片进入 Generate 页面，继续生成或查看历史结果
4. 在生成页点击任意图片缩略图可放大查看原图

## AI 能力需求

| 能力类型 | 用途说明 | 应用位置 |
|---------|---------|---------|
| **文本生成（MiniMax M2.7）** | 提示词优化：将用户简单描述扩写为详细、专业的生图 prompt | 点击「AI enhance」时显式触发；优化结果回填输入框 |
| **图像理解（MiniMax 视觉模型）** | 自动标签：分析用户上传或生成的图像，提取内容、风格、色彩等标签；用于分类和搜索 | 上传图像后自动调用；生成完成后自动调用 |
| **图像生成（MiniMax image-01）** | 作为 ComfyUI 之外的备选生图引擎，支持文生图、参考图主体一致性、自定义尺寸、Seed 和多图输出 | 用户切换分类为 image 时调用 |
| **语音合成（MiniMax Speech T2A）** | 使用 MiniMax 同步 T2A HTTP API，把文本转成音频；支持 Speech 2.8/2.6/02/01 系列模型、系统/复刻音色、情绪、音频规格、发音词典、语言增强和声音效果 | 用户切换分类为 voice 时调用；生成结果保存为本地音频并展示播放器 |
| **视频生成（MiniMax Hailuo）** | 使用 MiniMax 异步视频 API，支持 `MiniMax-Hailuo-2.3`、`MiniMax-Hailuo-2.3-Fast`、`MiniMax-Hailuo-02`、`S2V-01`，覆盖文本、首帧、首尾帧和主体参考模式 | 用户切换分类为 video 时调用；生成完成后下载到本地并展示播放器 |
| **音乐生成（MiniMax Music）** | 使用 MiniMax 音乐生成 API，把歌词和风格描述转成完整音乐；支持 music-2.6 / music-cover / music-2.5+ / music-2.5、纯音乐、AI 歌词优化、Seed 复现、Hex/URL 返回 | 用户切换分类为 music 时调用；生成结果保存为本地音频并展示播放器 |
| **图像生成（ComfyUI + 本地 GPU）** | 主力生图引擎；管理员可通过 `/admin` Workflows 面板管理 JSON、启停、校验、复制和 SMB 同步，Canvas 插入 workflow 节点时根据 summary 给出上游依赖提示；后续扩展节点参数映射 UI、LoRA、ControlNet 专用表单 | `comfyui-local` 模型入口；管理员工作流管理已可用，节点参数映射 UI 和高级工作流表单仍待实现 |

## 技术方向

| 维度 | 选择 | 理由 |
|------|------|------|
| **产品类型** | Web | 内网部署，团队共享使用，无需安装；方便集中管理和更新；RTX 4090 服务器统一提供算力 |
| **推荐技术栈** | Frontend: Vue 3 + TypeScript + Element Plus<br>Backend: FastAPI (Python) + Celery 异步任务队列 | Vue 3 生态成熟，Element Plus 提供完整后台组件；FastAPI 适合 AI 服务集成；Celery 处理生成队列和异步任务 |
| **数据存储** | SQLite（轻量级） + 本地文件系统 | 10 人规模数据量小，无需复杂数据库；图像文件存储在本地磁盘；便于备份和迁移 |
| **部署方式** | Docker Compose 一键部署 | Ubuntu 服务器标准化部署；方便更新和维护；隔离 Python 依赖 |
| **用户认证** | JWT Token + Session | 内网环境安全性要求低，简单可靠即可；支持管理员创建账号 |

## 技术说明

### 外部依赖
| 服务 | 用途 | 注意事项 |
|------|------|---------|
| **ComfyUI** | 本地生图引擎，运行在 Ubuntu 服务器 + RTX 4090 | 需要正确配置 CUDA 环境；工作流 JSON 格式需兼容当前 ComfyUI 版本 |
| **MiniMax API** | Token Plan 订阅，提供 M2.7 文本模型、视觉模型、image-01 生图 | 需要 API Key；按 token/调用计费；注意网络连通性（可能需要代理） |

### MiniMax 当前接入说明

| 能力 | 当前接入方式 | 备注 |
|------|--------------|------|
| 图片生成 | HTTP API 或 `mmx image generate` CLI | 官方 API Base URL 使用 `https://api.minimax.io` |
| 文本优化 | HTTP text chat API 或 `mmx text chat` CLI | 当前用于「AI enhance」，只回填 prompt，不自动触发生图 |
| 语音生成 | HTTP API 或 CLI | HTTP 走 MiniMax `/v1/t2a_v2`；非流式请求使用 `output_format: "hex"`，服务端将 hex 音频保存到 `/uploads/voices`；CLI profile 保持文件输出兜底 |
| 视频生成 | HTTP 异步任务 | HTTP 走 MiniMax `/v1/video_generation` 创建任务，轮询 `/v1/query/video_generation`，成功后用 `/v1/files/retrieve` 获取 `download_url`，服务端下载到 `/uploads/videos`；CLI profile 暂保留提交任务兜底 |
| 音乐生成 | HTTP API 或 CLI | HTTP 走 MiniMax `/v1/music_generation`；默认使用 `output_format: "hex"` 并保存到 `/uploads/music`；CLI profile 保持文件输出兜底；music-cover 当前支持一步模式参考音频 URL |

### ComfyUI 当前接入说明

| 能力 | 当前接入方式 | 备注 |
|------|--------------|------|
| 服务地址 | `COMFYUI_BASE_URL`，默认 `http://192.168.1.195:8188` | 已验证 `/system_stats` 可访问，ComfyUI 版本为 `0.19.1` |
| 状态检测 | `GET /api/comfyui/status` → ComfyUI `/system_stats` | 前端在选择 `comfyui-local` 时显示在线状态和 GPU 名称 |
| GPU 占用 | ComfyUI `/system_stats` 的 `vram_total/vram_free/torch_vram_total/torch_vram_free` | 状态条显示 VRAM 占用；生成中每 2 秒刷新 |
| 模型选择 | `GET /api/comfyui/checkpoints` → ComfyUI `/object_info` | 当前过滤掉 audio / VAE / LTX 视频模型，只展示默认图片 workflow 可用 checkpoint |
| 默认文生图 | `POST /api/image/generate`，模型为 `comfyui-local` | 后端构造默认 API-format 工作流，提交到 ComfyUI `/prompt` |
| 图片放大 | `POST /api/image/upscale` → ComfyUI `LoadImage/ImageScale/SaveImage` | 当前为 2x `lanczos` 几何放大，不是 ESRGAN/模型超分 |
| 结果归档 | 轮询 `/history/{prompt_id}`，再通过 `/view` 拉取输出图 | 图片保存到本平台 `/uploads/comfyui`，沿用现有生成记录流和原图预览 |
| 暂不支持 | 参考图注入、inpainting 涂抹、ControlNet、LoRA 工作流专用参数表单和队列管理 | 节点参数映射 UI（将 workflow patchable_inputs 暴露为可编辑控件）是下一阶段重点 |

### 性能要求
| 指标 | 目标值 |
|------|--------|
| 单张图生成时间（ComfyUI） | 10-60 秒（取决于分辨率和步数） |
| 单张图生成时间（MiniMax） | 5-20 秒（取决于 API 响应） |
| 提示词优化响应时间 | < 3 秒 |
| 图像分析响应时间 | < 5 秒 |
| 并发支持 | 10 人同时使用，队列等待时间 < 5 分钟 |

### GPU 要求
| 配置 | 说明 |
|------|------|
| 显卡 | NVIDIA RTX 4090 24GB（注意：4090 是 24GB，不是 48GB） |
| 显存占用 | SDXL 工作流约 12-16GB，需预留余量给 ControlNet/LoRA |
| 温度监控 | 后台需提供 GPU 温度和显存占用实时监控 |

## 补充说明

### 管理员后台功能
| 功能模块 | 子功能 | 优先级 |
|---------|--------|--------|
| **用户管理** | 管理员在前端 `/admin` 明确进入 Users 管理区，支持创建账号、重置密码、授予/撤销管理员权限、删除账号；创建用户入口必须是可见的 `Add User` 操作，不依赖用户猜右上角 `+` 的上下文 | 高 |
| **工作流配置** | 上传 ComfyUI JSON 工作流、设置名称和说明、启用/禁用 | 高 |
| **API 配额管理** | MiniMax token 使用统计、自定义 API 接入配置；模型列表允许管理员按 image / voice / video / music / text 分类手动补充自定义模型 ID | 高 |
| **使用统计** | 生成次数排行、热门模型/工作流、用户活跃度 | 中 |
| **系统设置** | GPU 监控（温度/显存占用）、生成队列管理、系统日志 | 低 |

### 工作流管理
| 概念 | 说明 |
|------|------|
| **预设工作流** | 管理员在后台上传 ComfyUI JSON 工作流，配置名称、说明、适用场景 |
| **用户使用** | 用户通过下拉框选择可用工作流，不可修改节点逻辑 |
| **参数暴露** | 管理员可配置工作流中哪些参数对用户可见（如 seed、cfg、steps） |

### 账号权限
| 角色 | 权限 |
|------|------|
| **普通用户** | 登录、使用生图功能、查看个人历史、保存提示词 |
| **管理员** | 用户管理、工作流配置、API 配额管理、系统监控、查看所有用户历史 |

---

## 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.21 | 2026-05-21 | Canvas/Project 绑定同步：入口统一（`/project/:conversationId?mode=canvas` 替代独立 `/canvas`，必须项目绑定）、工作流同步（关联 conversation）、模型同步（共享参数配置）、topbar 同步（统一导航栏和返回按钮）、文档同步（本条目） |
| v1.20 | 2026-05-21 | ComfyUI 操作者参数开放：Generate 页"图片高级设置"和 Canvas Workflow/Video 节点面板支持调整 Steps（1-100，默认 28）、CFG（0-30，默认 7）、Denoise（0-1，默认 1）；后端 schema 加范围校验，runtime_workflow() patch KSampler 并支持 {{steps}}/{{cfg}}/{{denoise}} 占位符 |
| v1.19 | 2026-05-21 | Workflow 管理完善：后端自动计算 summary（节点数/输出类型/required inputs/patchable inputs），新增 validate 和 duplicate 接口，sort_order 编辑不重置，Admin 面板以彩色徽标展示 summary，Canvas 画布根据 summary.required_inputs 给出上游依赖提示 |
| v1.11 | 2026-05-07 | Admin Profile 模型选择支持自定义模型 ID，避免模型列表被 MiniMax 预设锁死，为后续其他供应商 API 接入预留入口 |
| v1.10 | 2026-05-07 | 明确管理员后台用户管理入口：前端 `/admin` 必须展示可见 Add User 操作，并提供创建账号、重置密码、管理员权限切换和删除保护 |
| v1.0 | 2026-04-30 | 初始版本 |
| v1.1 | 2026-05-05 | 补充当前 MVP 状态、项目缩略图、生成页原图预览、权限加固和安全限制 |
| v1.2 | 2026-05-05 | 新增显式「AI enhance」流程：文本模型扩写 prompt 后回填输入框，由用户确认后生图 |
| v1.3 | 2026-05-05 | 首页视觉和项目管理体验升级 |
| v1.4 | 2026-05-05 | Generate 页面升级为生成工作台：生成记录流、底部停靠生成框、1x/2x/4x、取消生成、点击图片查看原图 |
| v1.5 | 2026-05-06 | 语音生成对齐 MiniMax 官方同步语音调试台：补齐 Speech 2.8/2.6/02/01 模型、音色/情绪/音频规格/语言增强/发音词典/声音效果等参数 |
| v1.6 | 2026-05-06 | 音乐生成对齐 MiniMax 官方音乐调试台：补齐模板、歌词结构标签、纯音乐、AI 歌词优化、音频规格、Seed、水印和 Hex/URL 返回 |
| v1.7 | 2026-05-06 | image 分类对齐 MiniMax 官方图片调试台：参考图缩略展示、拖拽/URL 添加、subject_reference、官方 Prompt 优化、Seed、自定义尺寸、AIGC 水印和 image-01-live 画风参数 |
| v1.8 | 2026-05-06 | 接入本地 ComfyUI：新增 `comfyui-local` 模型、GPU/VRAM 状态、默认文生图工作流提交、checkpoint 选择、Upscale、历史轮询和本地结果归档 |
| v1.9 | 2026-05-06 | video 分类对齐 MiniMax 官方视频方案：文生视频、首帧图生视频、首尾帧、主体参考、异步查询 file_id 和本地视频归档 |
