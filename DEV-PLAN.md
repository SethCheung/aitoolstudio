# Development Plan - Comfy Canvas

## 当前策略

从旧的 `img-platform` 重置为基于 Infinite-Canvas 的新项目。旧代码不再继续填补，当前仓库内容以 `hero8152/Infinite-Canvas` 为基础模板。

当前入口分层（2026-05-27）：
- `/projects`：项目主页（新）
- `/admin`：后台控制台（管理员）
- `/studio`：旧多工具壳（保留）

导入来源：

- 仓库：`https://github.com/hero8152/Infinite-Canvas`
- 导入版本：`2026.05.25.5`
- commit：`92145706e00ed36571355b7668ed3c570a117c01`

## Phase 1: 底座清理和运行确认

**目标**：确认 Infinite-Canvas 在本地能跑，理解现有入口和数据结构。

**任务**

- 跑通原项目启动流程。
- 确认主要页面：`static/index.html`、`static/smart-canvas.html`、`static/canvas.html`、`static/api-settings.html`、`static/comfyui-settings.html`。
- 梳理 `main.py` 中的 API：画布、workflow、ComfyUI、RunningHub、API provider。
- 标记哪些原功能保留，哪些隐藏，哪些重写。

**关键文件**

- `main.py`
- `static/js/smart-canvas.js`
- `static/js/canvas.js`
- `static/api-settings.html`
- `static/comfyui-settings.html`
- `requirements.txt`

**验收**

- 本地服务能启动。
- 画布页面能打开。
- 能保存和读取一个测试画布。

## Phase 2: 登录和用户角色

**目标**：增加最小可用登录系统。

**任务**

- 增加用户表或用户 JSON 存储，优先 SQLite。
- 增加登录、登出、当前用户接口。
- 增加管理员角色。
- 保护后台配置接口。
- 普通用户只能访问项目和画布。

**关键文件**

- `main.py`
- `static/index.html`
- `static/js/*.js`
- `data/` 运行时目录

**验收**

- 未登录不能进入项目画布。
- 管理员可以进入后台。
- 普通用户不能访问 API/Profile/Workflow 配置接口。

**实现记录（2026-05-26）**

- 已落地 SQLite 用户与会话表（`data/auth.db`）。
- 已新增登录/登出/当前用户接口：`/api/auth/login`、`/api/auth/logout`、`/api/auth/me`。
- 已新增管理员创建用户接口：`/api/auth/users`（admin only）。
- 默认管理员初始化支持环境变量 `AITOOL_ADMIN_USERNAME`、`AITOOL_ADMIN_PASSWORD`，缺省 `admin/admin123`（仅建议本地首次使用）。
- 已保护后台配置页面/API（admin）与核心页面/API（login required）。

## Phase 3: 项目管理

**目标**：把画布从独立文件变成项目工作区。

**任务**

- 增加项目列表。
- 支持创建、重命名、删除或归档项目。
- 每个项目绑定一张默认画布。
- 项目记录 owner。
- 项目卡片显示缩略图或最近生成结果。

**关键文件**

- `main.py`
- `static/index.html`
- `static/js/canvas.js`
- `static/js/smart-canvas.js`
- `data/projects*`
- `data/canvases/`

**验收**

- 用户登录后看到自己的项目。
- 新建项目后进入项目画布。
- 刷新后项目和画布仍然存在。

**实现记录（2026-05-26）**

- 已新增 SQLite 项目表与预留成员表（复用 `data/auth.db`）：`projects`、`project_members`。
- 已新增项目 API：列表、回收站、创建、读取、重命名、归档、恢复、彻底删除。
- 新建项目会自动创建一张默认画布，并写入 `owner_user_id`、`project_id`。
- 已给现有 canvas API 加 owner/admin/member 权限检查。
- 首页默认进入无限画布，画布入口面板切换为项目列表，创建/重命名/归档/恢复/删除均走项目 API。
- 运行时测试已覆盖：普通用户创建项目、管理员可见、默认画布绑定、项目重命名同步画布标题、归档后画布隐藏、恢复后可见、彻底删除后项目消失。

## Phase 4: 后台 Workflow 导入和参数映射

**目标**：管理员可以导入不同 ComfyUI workflow，并配置普通用户可控参数。

**任务**

- 后台导入 ComfyUI API-format workflow。
- 增加 workflow 本地化导入向导：支持粘贴 JSON、上传 JSON、RunningHub workflow URL/ID。
- 增加 60 盘资源中心配置：检测资源根目录、建议子目录、读写状态和磁盘余量。
- 对 RunningHub `/post/{id}` 做明确兜底提示，不能把 postId 假装成可执行 workflowId。
- 生成节点兼容性、模型依赖、60 盘模型命中状态和人工安装计划；第一版不执行第三方安装和模型下载。
- 保存 workflow 名称、说明、分类、启用状态。
- 分析 workflow JSON，提取可能可控字段。
- 管理员为字段配置控件类型、标签、默认值、范围、选项、是否必填。
- 普通用户只看到管理员暴露的字段。

**关键文件**

- `main.py`
- `static/comfyui-settings.html`
- `static/js/comfyui-settings.js`
- `static/js/smart-canvas.js`
- `workflows/`
- `data/workflows*`

**验收**

- 管理员能导入 workflow。
- 管理员能看到 60 盘资源中心状态、缺失节点、模型依赖和安装计划。
- 管理员能配置至少 text/image/number/select/boolean 五类字段。
- 普通用户不能看到 workflow JSON。

**当前实现记录**

- 已扩展 workflow 配置：名称、说明、分类、封面、启用状态，以及字段的必填、启用、隐藏配置。
- 上传 ComfyUI API-format workflow 后，会自动提取可控字段候选，默认不暴露，管理员勾选后才进入前台。
- 已新增 MVP-1 导入向导：`POST /api/workflows/import/plan` 支持 workflow JSON 与 RunningHub workflow 引用，输出节点兼容性、模型依赖和安装计划。
- 已新增 Phase 1 资源中心：`AITOOL_RESOURCE_ROOT` / `RESOURCE_ROOT` 指向 60 盘挂载路径，后台可检测目录结构和模型命中状态。
- RunningHub `/post/{id}` 当前返回 `need_workflow_json`，提示上传/粘贴 API workflow JSON，不做假成功。
- 导入向导保存的新 workflow 默认 `enabled=false`，管理员验收后再启用。
- 已新增 public workflow 读取链路，普通用户只看到启用 workflow 和已暴露字段，不返回原始 workflow JSON。
- `/api/workflows/{name}/run` 对普通用户只读取服务端保存配置，忽略客户端伪造的字段映射。
- 已封堵旧 `/api/generate` 绕过路径：普通用户不能再直接提交后台 workflow 名称和任意 `params`，LTX Director 也改走受控 workflow 运行接口。
- 运行时测试已覆盖：管理员 raw 详情、普通用户 public 详情、停用 workflow 隐藏、普通用户禁止保存配置、必填参数后端校验、旧 `/api/generate` 自定义 workflow 403。

## Phase 5: 画布 Workflow 节点运行

**目标**：项目画布中可以运行后台启用的 workflow。

**任务**

- Workflow 节点绑定后台 workflow。
- 读取上游文本和图片节点作为输入。
- 展示该 workflow 的动态参数表单。
- 运行时后端根据参数映射 patch workflow JSON。
- 调用 ComfyUI 并轮询结果。
- 生成结果作为画布节点插入。

**关键文件**

- `main.py`
- `static/js/smart-canvas.js`
- `static/css/smart-canvas.css`
- `workflows/`
- `data/canvases/`

**验收**

- 用户能在画布中选择一个 workflow。
- 用户能调该 workflow 暴露的参数。
- 运行后图片结果出现在画布中。
- 结果节点可继续连接到下游 workflow。

**当前实现记录（2026-05-26）**

- 经典画布已支持自定义 ComfyUI workflow：读取后台公开 workflow、展示动态参数、把第一个 prompt 字段接上游文本，后续 prompt 类字段作为可调参数保留。
- 智能画布已补齐自定义 workflow 参数展示、必填字段预检、运行请求 `client_id` 透传。
- 后端 `/api/workflows/{name}/run` 按后台保存的字段配置 patch workflow，并把请求 `client_id` 传给 ComfyUI `/prompt`。
- 本地 ComfyUI `127.0.0.1:8188` 已跑通 smoke workflow：`custom/aitool-smoke-sd15.json`，结果输出到 `/assets/output/`。
- 安全边界已验证：普通用户不能通过 `/api/generate` 直接运行后台 custom workflow。

## Phase 6: 后台 API/Profile 管理整理

**目标**：所有 API 和模型配置留在后台。

**任务**

- 整理 API provider 配置页面。
- API Key 脱敏展示。
- 普通用户前台不展示 provider/API Key 配置。
- ComfyUI Base URL 和状态检测放后台。
- 模型、RunningHub、火山等 provider 后续按需要启用。

**关键文件**

- `main.py`
- `static/api-settings.html`
- `static/js/api-settings.js`
- `static/comfyui-settings.html`
- `static/js/comfyui-settings.js`

**验收**

- API Key 只有管理员可配置。
- 普通用户只看到可用 workflow 和模型选项。
- 后台能看到 ComfyUI 在线状态。

**实现记录（2026-05-27）**

- 已将 `/api/providers`、`/api/config/token`、`/api/comfyui/instances`、`/api/comfyui/status` 收口为管理员接口。
- `/api/config` 仅返回普通前台所需的模型与 provider 元数据，不再暴露 provider `base_url`、Key 状态或脱敏 Key。
- 后台 API 设置页只显示脱敏状态字段，输入框不会回显完整 Key，并兼容旧 `key_preview` 字段。
- ComfyUI 后台状态检测改为走平台后端 `/api/comfyui/status`，避免浏览器直连 ComfyUI 的跨域误报。
- 已验证普通用户不能进入后台管理接口，但仍可运行后台启用的自定义 ComfyUI workflow。

## Phase 7: 收尾和部署

**目标**：形成可交付的内部版本。

**任务**

- 补 `.env.example`。
- 补 Docker Compose 或统一启动脚本。
- 整理 README。
- 增加基础备份说明。
- 检查运行时数据、密钥、输出文件不会进入 git。

**验收**

- 新机器按 README 可以部署。
- 管理员完成配置后，普通用户能完成项目画布生成闭环。
- git 不追踪 API Key 和生成产物。

**实现记录（2026-05-27）**

- 已重写 `README.md` 为当前 Infinite-Canvas 基线说明，移除旧架构表述，补齐登录/项目/后台 API 设置/ComfyUI workflow/普通用户画布流程。
- 已新增 `.env.example`，覆盖 `main.py` 现有读取项（管理员账号、Provider Key、RunningHub Key、ComfyUI 默认实例、超时与长度限制等）。
- 已新增 `docker-compose.yml`，明确仅启动平台服务，ComfyUI 作为外部依赖通过 `COMFYUI_INSTANCES` 配置。
- 已补强 `.gitignore`：忽略 `data/`、`data/auth.db`、`API/.env`、输出目录与缓存；保留 `workflows/` 示例文件可继续纳入版本管理。

## Phase 8: 60 生产和 ComfyUI 池运维基线

**目标**：把 `195/197/249` 从“能跑”固化为可巡检、可复现、可重启恢复的 worker pool。

**任务**

- 60 平台使用 `docker-compose.60.yml` 独立运行在 `3000`，旧系统 `5173/8000` 暂不冲突。
- `API/.env` 持久化 `COMFYUI_INSTANCES=192.168.1.195:8188,192.168.1.197:8188,192.168.1.249:8188`。
- 新增池巡检脚本，读取 `COMFYUI_INSTANCES`、访问每台 `/system_stats` 与 `/object_info`，并按 workflow 校验缺失节点。
- 新增 worker snapshot 脚本，用于记录 ComfyUI 主仓、custom_nodes、Python/Torch/CUDA、mount 与 systemd 状态。
- 统一 worker 资源盘挂载点为 `/mnt/nas_comfyui`，249 当前 `/mnt/comfyui-models` 作为过渡路径处理。
- 统一 worker systemd 服务，确保机器重启后自动挂载 60 盘并拉起 ComfyUI。

**关键文件**

- `docker-compose.60.yml`
- `scripts/comfyui_pool_inventory.py`
- `scripts/comfyui_worker_snapshot.sh`
- `docs/comfyui-worker-ops.md`

**验收**

- 从 60 执行 `python scripts/comfyui_pool_inventory.py --workflow workflows/Z-Image-Enhance.json --strict`，三台 worker 均在线且缺失节点为 `0`。
- 三台 worker 重启后 `findmnt /mnt/nas_comfyui`、`systemctl is-enabled comfyui.service`、`systemctl is-active comfyui.service` 均通过。
- 249 不再依赖手工启动 ComfyUI。
