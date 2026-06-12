# xy-canvas 60 生产补丁说明（2026-06-12）

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
