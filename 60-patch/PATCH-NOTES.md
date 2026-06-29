# xy-canvas 60 生产补丁说明（2026-06-12）

## 第七批：下架 5 个坏工具页 + 清理垃圾画布（2026-06-12 晚）

- **static/index.html（旧壳）**：从「ComfyUI应用」子菜单移除 5 个把 ComfyUI 写死为 `http://127.0.0.1:8188`、局域网访问必挂的工具页——3D视角变换 / CG一键细化 / 一键抠图 / 高清修复 / 万物移除（含对应 iframe）。保留可用的：图片编辑、2D风格细化、扩图、图像反推、文字抠图。被下架页面文件仍在 static/app/，直链可访问；后续这些能力统一走画布的已发布工作流。
- 运营清理（直接在生产执行，无需部署）：10 个垃圾画布（「11」×4、新画布 18:21、e2e_check、新画布 16:08、codex_video_line、未命名画布、111）已移入回收站，可恢复。
- 注意：本批 index.html 基于生产实时版本制作（生产 index.html 与仓库版本差异大，仓库版已过期，见「结构性还债」事项）。

## 第六批：唯一入口收口到旧壳 XY AI（2026-06-12 晚）

- `/`、`/projects`、`/smart-canvas` 全部 307 → `/static/index.html`：浅色「项目主页」与其画布链路下架，全平台只剩旧壳 XY AI 一个入口、一套画布（无限画布）。
- ComfyUI 工作台「项目主页」按钮改为「返回主页」（→ /static/index.html）。
- 项目/回收站数据未动；后台 /admin、/comfyui-workbench、/comfyui-settings 入口保持不变。

## 第五批：下架智能画布、统一 xy-canvas（2026-06-12 晚）

- **智能画布（smart-canvas，白色版）正式下架**：`/smart-canvas` 路由 307 跳回 `/projects`；项目主页移除「新建智能项目」按钮；测试用智能项目已归档（项目 id 3dafbb0c...，回收站可恢复，但恢复后打开会回项目主页）。统一只用经典 xy-canvas。
- **经典画布工作流下拉改用「已发布」列表**（/api/workflows-public）：只显示在 ComfyUI 工作台发布过的工作流、显示发布标题——与工作台词汇一致，草稿和杂项不再出现在画布。
- 60 盘上 smart-canvas.html/js/css 不再被路由引用（rsync 不删除文件，留在盘上无影响）。

## 第四批：画布走查修复（2026-06-12 晚）

### static/modules/canvas-all.js（经典画布）
- 修复 P0 bug：`runCustomWorkflow` 里 `pendingId` 声明在 try 块内、catch 在块外引用，**任何运行失败都会 ReferenceError 自爆**——错误弹窗不出、节点永远卡在「处理中/0%」。现在失败会正常弹出后端错误信息并复位节点状态。

### main.py
- 工作流列表过滤 SMB 盘的 macOS 元数据文件（`._*`），之前会以「._ltx_音视频-ltx-av」这种形态出现在画布工作流下拉里。

### 已知环境问题（非本补丁范围，需要运维处理）
- 内置文生图 Z-Image 当前在所有 worker 上失败：节点 20 (VAEDecode) IndexError: tuple index out of range。`ae.safetensors` 在各 worker 的 VAE 列表里都存在，疑似 60 盘上该文件损坏/不完整或与模型不匹配。建议在 ComfyTV 里重新验证并核对文件完整性。



## 第三批：SMB 共享 workflow 目录接入 + 列表容错（2026-06-12 傍晚）

### main.py
- 平台正式支持 `workflows/shared/`（compose 把 60 盘 `/vol3/.../AI-Tool-Studio/comfyui/workflows` 只读挂载到这里，此前代码完全不读它）：
  - 共享盘 workflow 出现在工作台/设置页列表（带「共享盘」徽标），可试跑、可发布到画布；
  - 共享目录只读：参数配置和跑通记录写到 `data/workflow-configs/shared/`，不碰盘上原文件；
  - 共享 workflow 默认停用，必须管理员确认参数后发布；平台内禁止删除（提示去 60 盘管理文件）。
- 修复：workflows 目录里出现命名不合法的文件（如全角标点）时，列表接口整体 400（`Invalid workflow name`）。现在跳过该文件并打日志，其余正常列出。该问题旧 `/api/workflows` 同样存在，一并修复。

### 新增 apply-60pan-mount.sh（可选，启用模型命中检测）
把 60 盘资源根 `/vol3/@team/SJM-MediaFile/AI-Tool-Studio/comfyui` 挂进容器（自动备份 compose、重建容器）。执行后由 Claude 通过后台接口配置 `AITOOL_RESOURCE_ROOT` 并验证。



## 第二批：ComfyUI（ComfyTV）跑通 → 一键发布到画布（2026-06-12 下午）

目标：workflow 在 worker 的 ComfyUI（旧壳「ComfyTV」内嵌的就是它）里跑通后，平台直接从运行历史导入，确认参数即可发布给无限画布引用。

### 核心新能力：从 ComfyUI 跑通记录一键导入
- `GET /api/comfyui/worker-history`（管理员）：读取指定 worker 的 ComfyUI 运行历史（成功/失败、节点数、输出图缩略、时间）。
- `POST /api/comfyui/import-from-history`（管理员）：选一次跑通的运行直接导入为平台 workflow——history 自带 API 格式 prompt，无需手工导出 JSON；自动生成可调参数候选，并预填「已跑通」记录（含来源 worker 和 prompt_id），默认停用待发布。
- 工作台「工作流试跑」页签左上角新增「从 ComfyUI 跑通记录导入」按钮：选 worker → 看历史（含输出图预览）→ 起名导入 → 确认参数 → 发布到画布。

### main.py
- `POST /api/workflows/{name}/run` 新增可选 `instance` 参数：管理员试跑可指定目标 worker（须在 `COMFYUI_INSTANCES` 内，且会先校验该 worker 不缺所需节点）；普通用户与画布运行不受影响，仍走自动调度。
- workflow 运行成功后自动在 config 写入 `last_test`（时间 / worker / 运行人 / 参数快照 / 输出数），即「已跑通」记录；`PUT /api/workflows/{name}/config` 不带 `last_test` 时保留旧值（兼容旧设置页）。
- 新增 `GET /api/comfyui/workbench-workflows`（仅管理员）：全部 workflow（含未启用草稿）+ 每台 worker 的节点兼容性（缺哪些节点）+ last_test + 启用状态。

### static/comfyui-workbench.html / js/comfyui-workbench.js / css/comfyui-workbench.css
- ComfyTV 新增「工作流试跑」页签（仅管理员可见；普通用户仍只看 worker 监控）：
  - 工作流列表：状态徽标（已发布 / 已跑通 / 待试跑 / 缺依赖）+ 「N/M worker 可跑」+ 筛选与搜索。
  - 试跑面板：选 worker（自动调度或指定某台，显示 GPU/显存/队列，不兼容的置灰并提示缺哪些节点）→ 按字段映射生成参数表单（文本/数字/下拉/开关/图片视频音频上传）→ 运行 → 展示输出图/视频或报错详情。
  - 「发布到画布」：弹窗勾选要暴露给普通用户的参数（未勾选的隐藏走默认值）→ enabled=true → 画布的 workflow 节点立即可引用；已发布的可「下线」。
- 部署后浏览器若样式异常请强制刷新（Cmd+Shift+R）。



部署方式：`bash 60-patch/deploy-from-mac.sh`（会自动备份被覆盖的文件到 60 的 `/opt/xy-canvas/backups/claude-patch-<时间戳>/`，并重启容器）

## P0 安全修复

### main.py
- `/api/update-from-github` 原先**无任何鉴权**，且硬编码拉取上游模板仓库 `hero8152/Infinite-Canvas`，执行会整体覆盖 main.py 和 static/。现已：
  - 必须管理员登录才能调用；
  - 默认禁用，需设置环境变量 `XY_ENABLE_GITHUB_UPDATE=1` 才能开启。
- `/api/update-backups`、`/api/update-rollback` 补充管理员鉴权。

### static/login.html
- 隐藏「注册」按钮（后端没有 `/api/auth/register` 接口，原按钮点击必报错；账号统一由管理员创建）。

## P1 功能修复

### 旧壳鉴权对接（static/modules/settings.js、static/login.html）
后端登录/me 接口返回 `{user:{username, is_admin}}`，旧前端按顶层字段读取，导致：用户名显示为空、管理员被识别为普通用户（设置按钮永远「需要管理员权限」）。已修复字段读取。

旧壳「用户管理」面板原先调用三个不存在的接口，已对接到真实接口：
- 列表：`GET /api/auth/users`
- 重置密码：`POST /api/auth/users/{id}/reset-password`
- 「删除用户」改为「禁用用户」：`PATCH /api/auth/users/{id}`（后端无删除接口，禁用可恢复更安全），列表增加「已禁用」徽标。

### 登录跳转（static/login.html）
- 登录成功后支持 `?next=` 参数回跳（仅允许站内路径），无参数时维持原行为跳 `/static/index.html`。
- 修复登录后 localStorage 用户信息存成 undefined 的问题。

### 画布深链（static/modules/canvas-all.js）
- `/canvas?id=<画布ID>` 现在会直接打开对应画布；无 id 时保持原「选择画布」列表。项目主页的「打开」按钮由此真正生效。

## 补齐缺失页面（后端路由存在、文件缺失）

修复「新建智能项目后打开报“页面文件缺失”」「/admin 404」：

- `static/smart-canvas.html` + `js/smart-canvas.js`、`css/smart-canvas.css`
- `static/admin-dashboard.html`、`static/admin-users.html` + 对应 js/css
- 依赖：`js/auth.js`、`js/theme.js`、`css/theme.css`、`js/i18n*`、`vendor/js/lucide.js`、`images/logo.png`

均来自与线上 main.py 完全一致的代码线（aitoolstudio 仓库），接口兼容。

## 部署后待办（手工）

1. 修改默认管理员密码（admin/admin123 仍可登录生产！）。
2. `API/.env` 配置 `RUNNINGHUB_API_KEY`（及 COMFLY key 如需 GPT 对话/在线生图），然后重启容器。
3. 60 上有一个 root 权限文件 `static/modules/comfyui-qwen-edit.js` 此前无法同步回本地镜像，部署脚本会顺带放开读权限，之后可重新 rsync 刷新本地 60-live。

## 已知未修（下一轮）

- 项目主页（/projects）与画布选择器数据不一致：旧画布无项目归属（孤儿画布），两个入口看到的内容不同——需要数据归属方案，建议与 xy-canvas 维护者对齐。
- 经典画布右下角「EMPTY」浮窗样式突兀（minimap/资产托盘）。
- 登录页「鼠标移至中心」动效降低登录效率、表单对比度低。
- 原生 prompt/confirm 弹窗、错误提示可见性等体验项。

## 第八批：Z-Image 文生图修复 + 子菜单交互（2026-06-12 晚，Claude 自动部署）

- **Z-Image 文生图修复（一节点修复）**：`workflows/Z-Image.json` 的空 Latent 节点 `EmptyLatentImage`（4 通道）→ `EmptySD3LatentImage`（16 通道，匹配 z_image_turbo + Flux ae 的 latent 格式）。根因：worker ComfyUI 升级后不再自动纠正空 latent 通道数。已在 195/197/249 三台全部验证出图，画布端到端（填词→运行→图回画布）验收通过。
- 旧壳子菜单修复：选中子项后保持展开（原先自动收起），切换顶级项才收起。
- 自此部署由 Claude 通过 SSH 全自动执行（rsync + docker restart + 验证），发版前自动顶 VERSION。
- 注意：195 的 ComfyUI 是 0.19.2，197/249 是 0.21.1——建议运维找时间拉齐版本，避免同 workflow 跨机差异。

## 第九批：AI-CanvasPro 评估功能卡（2026-06-12 夜）

- 第三方画布 AI-CanvasPro（B 站阿硕，Source Available 双许可）部署为**评估卡**：代码在 60 盘 `/vol3/@team/SJM-MediaFile/AI-Tool-Studio/AI-CanvasPro`，容器 `ai-canvaspro-eval`（python:3.11-slim，端口 8777，AIC_LAN_MODE=1 + AIC_ALLOWED_ORIGINS 配置完毕，restart unless-stopped）。
- 旧壳侧边栏 ComfyTV 下方新增「CanvasPro 评估」卡（iframe 懒加载，地址按主机名拼 :8777）。
- ⚠️ License 注意：其条款明确「公司/团队使用、企业内部生产系统」需作者书面商业授权；当前仅限**评估用途**。若评估后决定团队正式使用，需联系作者（bilibili 阿硕）购买授权。
- 它的项目数据存在容器内 /app/user/（即 60 盘 AI-CanvasPro/user/），与平台数据完全隔离。

## 第十批：CanvasPro 本地生成桥（2026-06-12 夜，Claude 自动部署）

- main.py 新增 **APIMart 兼容桥** `/bridge/apimart/v1/*`（models / images/generations / balance）：
  - 鉴权：Bearer Key（env `AIC_BRIDGE_KEY`，默认 aitool-local）
  - `models` 列出平台全部已发布工作流；`images/generations` 把 prompt 注入工作流的提示词字段后在本地 worker 执行，返回绝对 URL 的图片；未知模型名回退 env `AIC_BRIDGE_DEFAULT_WORKFLOW`（默认 Z-Image.json）
  - 运行成功同样写入 last_test（by canvaspro-bridge）
- CanvasPro 已配置完毕：APIMart apiKey=aitool-local，apiUrl 已直写其 user/config.json 指向 `http://192.168.1.60:3000/bridge/apimart`
- 协议层端到端验证：curl 模拟其请求 31 秒返回本地生成的 2 张图

## 第十一批：工作流分类跑通矩阵 + _meta 容错（2026-06-12 深夜）

- main.py：运行前过滤工作流 JSON 的非节点顶层键（如 `_meta`），修复 8 个 ltx/seedvr2 系工作流「Node 'ID #_meta' has no class_type」整单拒收。
- 三轮矩阵实测 31 个已发布工作流：14 个跑通（文生图 2、图生图 8、文生视频 3、图生视频 1），全部自动写入 last_test。
- 发现 ltx 系列为「{{placeholder}} 模板工作流」，需字段映射注入；ltx-i2v 已按此打通。
- 未通者归因：8 个需精确字段映射（工作台人工配置）、2 个需视频素材、4 个缺节点、2 个 PS 联动类不适用、1 个显存不足。

## 第十二批：CanvasPro 桥降噪 + 同源加载修复（2026-06-14，Codex 验收部署）

- APIMart 兼容桥不再把所有已发布工作流直接暴露给 CanvasPro，只列出「有公开 prompt 文本字段、且没有必填图片/视频/文件字段」的安全工作流；如需手动收窄，可用 env `AIC_BRIDGE_WORKFLOWS` 指定 workflow name/title。
- CanvasPro 模型显示名统一加前缀「本地 ComfyUI · 」，避免用户误点成线上模型；未知模型名不再静默回退，改为返回清晰错误。
- 旧壳入口从「CanvasPro 评估」改为「AI-CanvasPro（第三方评估）」，iframe title/aria-label 标明第三方评估与数据隔离。
- 修复 ComfyTV iframe 地址版本号拼接多出 `)}` 的问题。
- 60 盘 AI-CanvasPro `server.py` 已补丁：允许浏览器同源、无 Origin 的只读 GET/HEAD 读取配置/项目/工作流等接口，普通无头请求与非白名单 Origin 仍保持 403。
- 60 远端已配置非默认 `AIC_BRIDGE_KEY`，并用 `AIC_BRIDGE_WORKFLOWS=Z-Image.json,custom/黑白线稿.json` 固定 CanvasPro 可见模型；换 key 后已完成一次 Z-Image 真实出图 smoke test。

## 第十三批：CanvasPro API 设置精简（2026-06-15，Codex 远端部署）

- 60 盘 AI-CanvasPro API Key 设置页删除 GRSAI、派欧云（PPIO）、Agnes AI、火山方舟卡片。
- 新增 `Kimi Coding Plan` 与 `MiniMax Coding Plan` 卡片，均提供接口地址和 API Key 输入框；默认接口分别为 `https://api.kimi.com/coding/v1` 与 `https://api.minimax.io/v1`。
- 同步更新 CanvasPro `user/config.json`，仅保留 OpenAI、APIMart、本地新增 Kimi/MiniMax、RunningHUB；已有 APIMart 桥密钥未打印、不落文档。
- 连接测试白名单改为明文 provider id：`kimi`、`minimax`、`apimart`、`openai`、`runninghub`；旧 provider 测试入口返回不支持。
- 已完成远端 `node --check`、测试模块直调、服务重启与浏览器可见性验收。

## 第十四批：Kimi Coding Plan 连接测试修复（2026-06-15，Codex 远端部署）

- 修复 Kimi key 被误报为“无效/过期/无权限”：Kimi Coding Plan 的 `/models` 可验证 key 有效，但通用 `chat/completions` 会被官方限制为 Coding Agent 场景；连接测试改为模型列表通过后跳过额外聊天探针。
- `server.py` 将 `/api/v2/proxy/task` 加入同源无 Origin 的 GET/HEAD 只读白名单，用于浏览器同源模型列表探测；错误 Origin 仍返回 403。
- 为 `index.html`、`main.js`、`api/index.js` 增加版本化导入，避免浏览器复用旧连接测试模块。
- 已验证：Kimi 模型列表代理 200、恶意 Origin 403、浏览器内 Kimi Coding Plan 测试按钮显示“通过”。

## 第十五批：CanvasPro 文本模型菜单接入 Kimi/MiniMax（2026-06-15，Codex 远端部署）

- 文本模型分类从旧供应商列表收窄为 Kimi Coding Plan、MiniMax Coding Plan、APIMart、RunningHUB；旧供应商底层 manifest 保留，避免历史画布引用直接断裂。
- 新增文本模型 manifest：`kimi/kimi-for-coding`（Kimi For Coding）与 `minimax/MiniMax-M3`（MiniMax M3），并补齐对应 chat completion 执行 manifest、provider 前缀识别、错误提示名称。
- 修复文本节点模型菜单仍按旧 provider 索引生成子菜单的问题；Kimi/MiniMax 分类下现在会生成可点击模型项。
- 已验证：远端 `node --check`、manifest 动态导入、菜单 HTML 生成、浏览器内选择 `Kimi For Coding` 与 `MiniMax M3` 均通过。
- 接口状态：Kimi `/models` 返回 200 且包含 `kimi-for-coding`；MiniMax 当前 `/models` 返回 401，需要换有效 MiniMax Key 后再测。

## 第十六批：Kimi/MiniMax 文本生成真实跑通（2026-06-16，Codex 远端部署）

- Kimi Coding Plan 不再走 OpenAI `chat/completions` 生成链路：改由 CanvasPro 本地代理转发到 Kimi Code Anthropic Messages 接口，并把返回结构转换成 CanvasPro 现有 `choices[0].message.content` 格式。
- 修复 Kimi 代理补丁变量误插到图片代理导致文本代理 `RemoteDisconnected` 的问题；`server.py` 已通过 `python3 -m py_compile` 并重启容器。
- MiniMax Coding Plan 默认接口从 `https://api.minimaxi.com/v1` 改为 `https://api.minimaxi.com`，避免 manifest 再拼 `/v1/chat/completions` 后变成双 `/v1/v1/...`。
- MiniMax 文本生成加入专用分支：兼容用户填入带 `/v1` 或不带 `/v1` 的地址，并固定 `thinking: { type: "disabled" }`，避免 `<think>...</think>` 混入画布输出。
- 已验证：Kimi 代理真实请求 200 且返回 `OK`；MiniMax 代理真实请求 200 且返回 `OK`；前端 `generateText` 同款链路对 `kimi/kimi-for-coding`、`minimax/MiniMax-M3` 均返回 `OK`；浏览器打开 `?v=202606160016` 后确认 MiniMax 设置栏已更新为 `https://api.minimaxi.com`，旧 `/v1` 占位不存在。

## 第十七批：CanvasPro 带入本地 ComfyUI 工作流（2026-06-16，Codex 远端部署）

- 旧平台 APIMart 兼容桥从“只暴露纯 prompt 工作流”改为暴露 31 个已发布本地 ComfyUI 工作流；带参考图的细节增强、3D 视角、Flux2 编辑、高清修复等不再被过滤。
- 兼容桥新增 `/bridge/apimart/v1/uploads/images`，CanvasPro 的 APIMart 上传代理可以把参考图先传入本地 ComfyUI input，再由工作流节点使用。
- 兼容桥生成接口现在会把 `image_urls` / `inputImages` 等图片输入映射到公开图片字段，同时继续把 prompt 映射到公开提示词字段；无效模型名仍返回明确错误，不静默回退。
- 60 盘 AI-CanvasPro 新增 `localComfyImageModelApiManifests.js`，并注册 31 个 `apimart/local-comfy/...` 图像模型；模型菜单里会显示「本地 ComfyUI · ...」，需要参考图的模型声明对应图片槽位。
- 已验证：后端 `/bridge/apimart/v1/models` 返回 31 个本地模型；CanvasPro manifest 注册后图像模型总数 85、本地 ComfyUI 31；上传代理带浏览器 Origin 时可返回本地 `/api/view` URL；Z-Image 真实出图返回 2 张图。

## 第十八批：CanvasPro 接入本地 LTX 视频工作流（2026-06-16，Codex 远端部署）

- 旧平台 APIMart 兼容桥新增 `/bridge/apimart/v1/videos/generations`，把 CanvasPro 视频生成请求转成本地 ComfyUI LTX 工作流运行，并返回 APIMart 风格视频结果。
- 新增视频/音频上传入口 `/bridge/apimart/v1/uploads/videos`、`/bridge/apimart/v1/uploads/audio`；CanvasPro 本地 APIMart 上传代理在本地桥地址下会直传图片/视频/音频，不再对本地桥走官方 presign。
- LTX 工作流加入自动参数映射：prompt、负向提示词、首帧图、尺寸、时长、seed 会写入对应 ComfyUI 节点；图生视频未放首帧时返回明确提示。
- LTX 视频工作流从图片桥模型清单中排除，只在 CanvasPro 视频分类中出现，避免误选到图片节点。
- 60 盘 AI-CanvasPro 新增 `localComfyVideoModelApiManifests.js`，注册 9 个 `apimart/local-ltx/...` 视频模型：Director v2、文生视频 LoRA、图生视频、图生视频 2.3、1080P、1080P SeedVR2、Studio Quality、两段超分、音视频。
- 已验证：兼容桥识别 9 个 LTX 视频工作流；图片桥 `/models` 无 LTX；CanvasPro manifest 视频模型总数 61、本地 LTX 9；视频菜单渲染函数可生成 9 个「本地 LTX · ...」菜单项。

## 第十九批：CanvasPro APIMart 改为本地节点（2026-06-16，Codex 远端部署）

- 60 盘 AI-CanvasPro 不再注册线上 APIMart 图片、视频、文字模型：APIMart 图片从 33 个收窄为 23 个 `apimart/local-comfy/...`，视频从 29 个收窄为 9 个 `apimart/local-ltx/...`，文字 APIMart 模型为 0。
- 可见 provider 显示名从 `APIMart` 改为「本地节点」；图片模型分类、图片功能菜单、API 设置页 provider 名称均同步更新。
- 视频模型菜单移除 APIMart Dreamina/线上视频特例，只保留本地 LTX；文字模型菜单隐藏 APIMart 分组，保留 Kimi Coding Plan、MiniMax Coding Plan、RunningHUB。
- 已重启 `ai-canvaspro-eval` 并完成模块级验收：图片菜单 HTML 中 APIMart 线上计数 0、本地 ComfyUI 23；视频菜单 HTML 中 APIMart 线上计数 0、本地 LTX 9；前端页面加载无 console error。
- 逐节点参数映射自检：23 个图片节点、9 个视频节点全部能解析工作流并完成参数映射，LTX 视频没有残留未替换占位符。
- 后端兼容性检查结果：当前可用 ComfyUI 实例 `192.168.1.195:8188` 可运行 12/32 个本地节点；其余 20 个因当前实例缺自定义节点失败，备用实例 `192.168.1.197:8188` 超时/无路由，`192.168.1.249:8188` 连接拒绝。失败主因包括 Inspire 共享加载节点、LayerUtility/LayerColor、InspyrenetRembg、Photoshop 插件、llama_cpp、部分 LTX 1080P 所需节点缺失。
