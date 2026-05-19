# Product Spec 变更记录

## v1.18 - 2026-05-18

**流水线画布接入服务端运行模型**

### 变更内容
- `/canvas` 从纯 localStorage 原型升级为服务端画布文档：节点、连线、运行状态和结果可通过 `/api/canvas/documents` 保存。
- Workflow / Video 节点运行改为走 `/api/canvas/documents/{id}/nodes/{node_id}/run`，后端负责收集上游 Text / Media、注入现有 ComfyUI workflow、写入 Generation 和 CanvasRun 记录。
- 新增电商套图模板：产品信息 + 产品图 + 三组提示词，一键生成模特图、侧面展示图、俯瞰展示图的工作流骨架。
- 参考 huobao-canvas / Tapnow / AICON 的方向，但不直接复制代码：前端借鉴节点编排和结果节点，后端借鉴模板参数映射和运行记录。

### 设计原则
- 画布必须以本地 ComfyUI workflow 为执行基准，外部项目只提供产品结构启发。
- 第一阶段只做单个 Workflow 节点的服务端执行闭环；真正的多节点 DAG 队列、参数映射 UI 和运行中 SSE 后续拆开做。

## v1.17 - 2026-05-15

**新增 RunningHub/RHTV 风格流水线画布**

### 变更内容
- 新增 `/canvas` 流水线无限画布需求，对标 RunningHub/RHTV 的画布、节点、连线、左侧 tab 和底部节点输入框交互。
- “工作流”tab 必须结合现有 ComfyUI workflows：读取 `/api/comfyui/workflows` 的 enabled workflow，按 category 展示并插入 Workflow 节点。
- 选中 Video / Workflow 节点后，下方展示生成输入框：模式标签、素材库入口、prompt 输入、模型/规格/数量和提交任务按钮；内网版本不展示计费或扣费。
- 右下角新增流水线 Agent 助手：基于当前画布状态和现有 workflows，通过 `/api/prompt/canvas-agent` 调用 MiniMax 文本能力提示用户下一步应该怎么搭建，回答必须中文、短、具体。

### 设计原则
- RunningHub 只作为交互参照，数据源必须是本平台现有 workflow 管理体系。
- 第一版先完成画布编辑和节点配置；跨节点执行 ComfyUI 编排后续单独做，不要假装已经全闭环。

## v1.16 - 2026-05-07

**新增 ERNIE Image 内置 Workflow 模板**

### 变更内容
- Workflows 自动补入 `ERNIE Image` 内置模板，使用 `ComfyUI-ERNIE-Image` 自定义节点
- ERNIE workflow 默认模型路径为 `baidu/ERNIE-Image`
- runtime patch 新增 ERNIE 支持：`ERNIEImagePrompt.text`、`ERNIEImage.width/height/seed`
- 已将 `ernie-image.json` 导出到 SMB 固定目录 `团队文件-SJM-MediaFile/Comfyui_Workflows`

### 设计原则
- ERNIE 不是 checkpoint 工作流，不能套普通 `CheckpointLoaderSimple + KSampler` 的逻辑硬跑
- 第一版先支持文生图闭环；负面词、steps、guidance 等专用参数后续再做显式 UI，不塞进隐藏魔法

---

## v1.15 - 2026-05-07

**Workflow 支持从 SMB 固定目录同步**

### 变更内容
- 在 `团队文件-SJM-MediaFile` SMB 中建立固定目录 `Comfyui_Workflows`
- 后端 Docker 挂载该目录到 `/app/workflow-imports`，作为只读 workflow 导入源
- Workflows 面板新增 `Sync Folder` 操作，可导入该目录下的 ComfyUI API-format JSON
- 已将当前 `Default txt2img` 导出为 `Comfyui_Workflows/default-txt2img.json`

### 设计原则
- 不再全盘扫描网盘，workflow 只认固定目录，避免把模型配置 JSON、缓存 JSON 当 workflow 导入
- 195 上如果有保存的 workflow，需要放进 SMB 的 `Comfyui_Workflows` 后再同步；没有 195 SSH/文件访问时，不能凭空读取它本机用户目录

---

## v1.14 - 2026-05-07

**Admin 增加 ComfyUI Workflow 管理后台**

### 变更内容
- `/admin` 新增 Workflows 面板，支持管理 ComfyUI API-format workflow JSON
- 自动初始化 `Default txt2img` 工作流，作为本地 ComfyUI 文生图默认配置
- Workflow 支持名称、描述、分类、启用状态、备注、JSON 编辑、复制、删除和启停
- 新增 `/api/comfyui/workflows` CRUD 接口；普通用户只能读取启用 workflow，管理员可读取全部
- image 生成请求新增 `comfyui_workflow_id`，生成页选择 `comfyui-local` 后可选择启用的 workflow

### 设计原则
- 后台不能只是存配置，生成页必须能用，否则就是配置墓地
- 第一版只支持通用 runtime patch：prompt、checkpoint、seed、尺寸和 batch size；复杂节点映射后续单独做，不在这一版装全能

---

## v1.13 - 2026-05-07

**Admin 增加 ComfyUI 模型路径快捷管理**

### 变更内容
- `/admin` 新增 Paths 面板，用于集中保存 ComfyUI 模型存储路径
- 默认加入 `SJM audio_encoders` 快捷路径，指向 `smb://192.168.1.60/团队文件-SJM-MediaFile/Comfyui_Model/audio_encoders`
- 路径记录支持 SMB / 存储 URI、195 服务器本地 mount path、分类、备注、启用状态、复制和增删改

### 设计原则
- 路径管理只负责记录和复制，不假装能自动修改 195 上的 ComfyUI mount 或 `extra_model_paths.yaml`
- SMB 地址、195 本地挂载路径、ComfyUI 实际加载路径必须分开写清楚，别靠记忆维护生产系统

---

## v1.12 - 2026-05-07

**后台新增管理全部用户界面**

### 变更内容
- Admin 后台 Users 分类升级为独立的 All Users 管理界面
- 管理员可在同一界面查看所有账号、搜索用户名或用户 ID、查看角色和创建时间
- 用户列表直接提供编辑/重置密码、授予或撤销管理员权限、删除账号和 Add User 入口

### 设计原则
- “管理全部用户”是后台一级能力，不能靠一个不明显的添加按钮糊弄过去
- 账号列表、角色状态和危险操作必须集中展示，管理员才知道自己到底在管什么

---

## v1.11 - 2026-05-07

**Profile 模型支持自定义填写**

### 变更内容
- Admin Profile 的 image / voice / video / music / text 模型配置区新增自定义模型 ID 输入
- 管理员可以在预设 MiniMax 模型之外添加任意模型名，并保存到对应 Profile 的模型路由列表
- 已保存的自定义模型在编辑 Profile 时继续显示，可取消勾选移除

### 设计原则
- 模型管理不能被 MiniMax 预设锁死，后续买其他供应商 API 时必须能先录入模型 ID
- 先解决模型 ID 配置入口；不同供应商的请求协议适配后续按实际 API 单独实现，别在没买 API 前瞎兼容

---

## v1.10 - 2026-05-07

**管理员后台用户管理入口显性化**

### 变更内容
- 明确 `/admin` 需要可见的 `Add User` 操作，不能只靠切到 Users tab 后猜右上角 `+`
- 用户管理支持创建账号、编辑/重置密码、授予/撤销管理员权限和删除账号
- 后端用户管理接口增加防呆：禁止管理员删除自己、撤销自己的管理员权限、删除或撤销最后一个管理员

### 设计原则
- 后台核心操作必须明牌，别把“添加用户”藏成解谜游戏
- 权限操作宁可啰嗦一点，也不能一键把系统管理员删没

---

## v1.0 - 2026-04-30

**初始版本**

### 变更内容
- 创建内网 AI 生图协作平台 Product Spec
- 明确产品定位：10 人团队内网使用，ComfyUI + MiniMax API 双引擎
- 核心功能：文生图、图生图、inpainting、upscale、ControlNet、LoRA、批量生成、历史记录、提示词保存、API 接口
- MiniMax API 用途：提示词优化 + 图像理解 + image-01 生图
- 用户系统：管理员创建账号，登录后查看所有项目
- 管理员后台：用户管理、工作流配置、API 配额管理（高优先级）；使用统计（中）；系统设置（低）
- 技术栈：Vue 3 + FastAPI + Celery + Docker Compose

### 待确认事项
- RTX 4090 显存为 24GB（非 48GB），需在 Spec 中修正

---

## v1.1 - 2026-05-05

**同步当前 MVP 实现状态**

### 变更内容
- 补充“当前 MVP 状态”章节，明确已实现和未实现能力
- 首页项目卡片新增生成图片缩略图要求：项目中存在图片结果时展示第一张图片
- Generate 页面新增原图预览要求：点击图片缩略图后在同页打开原图，支持背景点击、关闭按钮和 Esc 关闭
- 明确当前管理入口为前端 `/admin`，后端 `/admin` 不再作为主要入口
- 补充权限加固要求：Admin/Profile 管理接口需要管理员权限，模型列表需要登录
- 补充当前安全限制：`/minimax-output` 静态目录仍需鉴权改造，Profile API Key 不应继续写入 git 跟踪文件
- 补充 MiniMax 当前接入说明：图片/语音/视频/音乐均需按官方 API/CLI 行为验证，视频为异步任务流程

### 影响范围
- `Product-Spec.md`
- `Design-Brief.md`
- `DEV-PLAN.md`
- `README.md`
- `SECURITY.md`

---

## v1.2 - 2026-05-05

**新增显式提示词优化流程**

### 变更内容
- Generate 输入区新增「AI enhance」按钮
- 用户点击后调用文本模型扩写当前输入，不自动触发生图
- 优化结果回填输入框，用户可继续编辑或点击生成
- 后端新增 `/api/prompt/optimize`，通过 Profile 路由选择 HTTP 或 CLI 文本模型
- Admin Profile 增加 text 模型分类，默认支持 `MiniMax-M2.7` 和 `MiniMax-M2.7-highspeed`

### 设计原则
- 不偷偷改用户 prompt
- 不把优化和生图绑成一个不可见流程
- 优化后的 prompt 必须让用户看见并可编辑

---

## v1.3 - 2026-05-05

**首页视觉和项目管理体验升级**

### 变更内容
- 首页调整为暗色作品管理台布局
- 顶部新增品牌区、搜索框和新建项目按钮；未完成的全局切换和用户菜单暂不展示
- 内容区新增 Recent Projects 标题、项目数量、排序选择、筛选按钮、网格/列表切换
- 项目列表第一位固定为「新建项目」卡片
- 项目卡片保持生成图缩略图展示，并保留打开、重命名、删除操作
- 搜索支持按项目名、提示词和类型过滤

---

## v1.4 - 2026-05-05

**Generate 页面升级为生成工作台**

### 变更内容
- Generate 页面从旧聊天侧栏布局调整为单栏生成工作台
- 顶部展示当前项目名称，支持点击编辑；搜索框居中，右侧提供“返回主页”
- 删除 Generate 页左侧侧边栏，避免未完成入口干扰主流程
- 中间区域改为生成记录流，最新生成在上，旧记录自然向下滚动
- 底部输入区改为停靠式生成框，不再用悬浮框遮挡内容
- 图片生成支持 `1x / 2x / 4x` 数量选择
- 生成中支持“取消生成”，前端中断当前请求并停止等待
- 生成结果图片按比例稳定展示，点击图片本身即可打开原图预览
- 图片记录操作包含重新生成、生成变体、下载全部、单图放大/下载

### 设计原则
- 不用未完成的用户菜单、语言切换、收藏等入口装饰页面
- 生成结果不应因为 loading、图片加载或新增记录导致整体布局跳动
- 旧记录必须自然滚动到下方，新生成结果必须能在顶部看到完整预览

---

## v1.5 - 2026-05-06

**语音生成对齐 MiniMax 官方同步 T2A 调试台**

### 变更内容
- voice 分类从“固定音色 + 固定参数”升级为 MiniMax 官方同步语音方案
- 支持 Speech 2.8 / 2.6 / 02 / 01 系列模型
- 支持系统音色选择、自定义 voice_id、情绪、语速、音量、音调
- 支持官方语气词标签插入和 `<#x#>` 停顿控制
- 支持音频格式、采样率、比特率、声道、字幕、LaTeX 公式朗读
- 支持语言增强、发音词典、声音效果器参数
- HTTP 请求体对齐 `/v1/t2a_v2`，非流式使用 `output_format: "hex"` 并在服务端保存音频

### 设计原则
- 先复制官方调试台的真实可用参数，再谈“我们自己的高级体验”
- 前端只暴露能传到后端的参数，不做看起来热闹但请求体里消失的假按钮
- 流式语音暂不在当前播放器闭环里承诺，避免用户点了开关结果平台假装支持

---

## v1.6 - 2026-05-06

**音乐生成对齐 MiniMax 官方音乐调试台**

### 变更内容
- music 分类从单 prompt 生成升级为歌词 + 风格描述双输入
- 支持官方歌曲模板和 `[Verse]`、`[Chorus]` 等歌词结构标签
- 支持 `music-2.6`、`music-cover`、`music-2.5+`、`music-2.5` 模型入口
- 支持纯音乐模式、AI 歌词优化、采样率、比特率、音频格式、返回格式、Seed 和 AI 音频水印
- HTTP 请求体对齐 `/v1/music_generation`，默认 `output_format: "hex"` 并在服务端保存音乐音频
- `music-cover` 当前支持一步模式参考音频 URL；上传预处理和两步模式后续单独做，不塞进当前生成框

### 设计原则
- 歌词和风格描述必须分开，别把两种输入混在一个 prompt 里装聪明
- 默认走 Hex 保存本地文件，避免外部 URL 失效导致历史记录坏掉
- 先做最常用的一步生成闭环，参考音频上传/预处理后续按独立流程设计

---

## v1.7 - 2026-05-06

**图片生成对齐 MiniMax 官方图片调试台**

### 变更内容
- image 分类新增参考图微缩条，参考 flow 风格在底部对话框中展示已添加图片
- 支持点击上传、拖拽 JPG/PNG 到对话框、粘贴参考图 URL
- 参考图按 MiniMax 官方 `subject_reference: [{ type: "character", image_file }]` 传给后端；本地文件读取为 `data:image/*`
- 补充官方图片参数：`width/height` 自定义尺寸、`seed`、`prompt_optimizer`、`aigc_watermark`、`n` 1-9、`image-01-live` 画风参数
- CLI 路由兼容 `mmx image generate --subject-ref`，data URL 会在后端临时解码成本地参考图文件

### 设计原则
- 参考图要在对话框里可见，不能藏在另一个表单页里
- 本地参考图按官方调试台做成 data URL，避免把本机 `/uploads` URL 错传给云端
- 图片高级参数只放真实会进入请求体的字段，不做假控件

---

## v1.8 - 2026-05-06

**接入本地 ComfyUI 直连**

### 变更内容
- image 分类新增 `comfyui-local` 模型入口，保持当前 Studio Tool 的生成工作台、记录流、图片网格和原图预览格式
- 后端新增 ComfyUI 客户端，默认连接 `http://192.168.1.195:8188`
- 新增 `/api/comfyui/status`，读取 ComfyUI `/system_stats` 并在前端显示在线状态和 GPU 名称
- ComfyUI 状态条新增 VRAM 已用/总量、占用百分比和 Torch VRAM，生成中每 2 秒刷新
- 新增 `/api/comfyui/checkpoints`，读取并过滤默认图片工作流可用 checkpoint；当前可选 `dreamshaperXL_lightningDPMSDE.safetensors`
- `POST /api/image/generate` 支持 `model: "comfyui-local"`，后端构造默认 API-format 文生图工作流并提交到 ComfyUI `/prompt`
- `POST /api/image/upscale` 支持对已有图片进行 2x `lanczos` 放大，使用 ComfyUI 原生 `LoadImage → ImageScale → SaveImage` 工作流
- 后端轮询 `/history/{prompt_id}`，通过 `/view` 拉取输出图并保存到本平台 `/uploads/comfyui`
- ComfyUI 结果沿用现有生成记录流、下载和图片预览体验，不另做一套页面
- 修复生成完成后必须刷新才显示的问题：前端完成响应后直接替换 loading 记录，立即展示结果图
- 修复会话标题保存的 CORS `PATCH` 预检失败问题

### 设计原则
- 第一版先把本地 ComfyUI 跑进统一工作台，别一上来幻想完整节点编辑器
- SSH 账号密码不写入仓库；当前只通过 ComfyUI HTTP API 接入
- 参考图、ControlNet、LoRA、inpainting 和管理员工作流上传仍是后续工作流管理任务，当前不伪装支持

---

## v1.9 - 2026-05-06

**视频生成对齐 MiniMax 官方视频方案**

### 变更内容
- video 分类从“提交任务后靠控制台看结果”升级为完整异步闭环
- 支持文生视频、首帧图生视频、首尾帧视频和主体参考视频
- 支持 `MiniMax-Hailuo-2.3`、`MiniMax-Hailuo-2.3-Fast`、`MiniMax-Hailuo-02` 和 `S2V-01` 模型入口
- 支持官方 `prompt_optimizer`、`fast_pretreatment`、`duration` 和 `resolution` 参数
- 后端创建任务调用 `/v1/video_generation`，轮询调用 `/v1/query/video_generation`
- 任务成功后读取 `file_id`，再调用 `/v1/files/retrieve` 获取 `download_url`
- 服务端将生成视频下载到 `/uploads/videos`，前端按现有记录流展示播放器

### 设计原则
- 视频生成必须是创建任务、查状态、取文件的完整链路，不接受“去控制台看”的半截方案
- 前端只暴露官方真实接收的参数，避免堆一堆看着高级但请求体里没影的控件
- 外部下载 URL 只作为中转，最终历史记录使用本平台本地归档地址，减少链接失效

---

## v1.10 - 2026-05-13

**Flux 局部重绘交互闭环**

### 变更内容
- `Flux 局部重绘` workflow 的默认交互改为上传原图后在居中画布上直接涂抹重绘区域
- 保留 `点选目标` 快速方式，点击图片后由后端生成 SAM 提示遮罩
- 前端提交时自动携带原图和遮罩，不再要求用户理解或手动管理 ComfyUI mask 占位符
- 后端支持 `sam_x / sam_y`、data URL 参考图、自动生成 mask PNG，并替换 `{{image}} / {{sam_mask}}`
- ComfyUI 失败时返回具体错误信息，不再只提示“检查本地服务和工作流”

### 设计原则
- 用户要的是“涂哪里改哪里”，不是学习 ComfyUI 的 mask 术语
- 局部重绘入口必须以原图为中心，重绘方式要明确可切换
- 报错必须能定位，笼统失败提示等于没提示

---

## 变更日志格式说明

| 字段 | 说明 |
|------|------|
| **版本** | v1.0, v1.1 等 |
| **日期** | YYYY-MM-DD |
| **变更内容** | 简要描述本次变更的核心内容 |
