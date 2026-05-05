# Development Plan — 内网 AI 生图协作平台

> 本文件记录项目的开发阶段划分、当前进度和剩余工作。
> 新 session 启动时应首先阅读此文件，了解项目状态后再继续开发。

---

## 当前实现快照（2026-05-05）

当前代码不是严格按原 Phase 文件名落地，后续开发必须以本节为准，别照着旧文件名硬找。

**已实现**
- FastAPI 后端、Vue 3 前端、SQLite 数据库初始化
- JWT 登录认证：`POST /api/auth/login`、`GET /api/auth/me`
- 管理员权限依赖：`require_admin`
- `/api/admin/users` 用户管理接口已加管理员鉴权
- `/api/profiles` 管理接口已加管理员鉴权；`/api/profiles/models` 要求已登录用户
- MiniMax Profile 路由：HTTP API / CLI profile 管理
- 图片、语音、视频、音乐生成入口：`api/image.py`、`api/voice.py`、`api/video.py`、`api/music.py`
- 提示词优化入口：`api/prompt.py`，显式调用文本模型扩写 prompt 后回填前端输入框
- 项目首页：`frontend/src/views/HomeView.vue`，对话有图片结果时显示缩略图
- 生成页面：`frontend/src/views/GenerateView.vue`，采用单栏生成工作台，支持多类别生成、历史恢复、AI enhance、`1x / 2x / 4x` 图片数量、生成中取消、图片点击同页原图预览
- Vue 管理页：`frontend/src/views/AdminView.vue`
- Docker Compose 基础前后端编排，后端要求 `JWT_SECRET_KEY`
- `.gitignore` 已补充运行时数据、密钥文件、构建产物忽略规则

**仍未完成**
- ComfyUI 工作流上传、队列、任务状态、结果归档
- Celery / Redis 任务队列
- 图像理解、自动标签
- 提示词库、收藏、批量下载
- GPU 监控和系统日志
- Nginx 反向代理与生产部署脚本
- 自动化测试和 CI

**当前最高优先级技术债**
- `/minimax-output` 仍是公开静态目录，生产前必须改为带鉴权的文件代理
- `profiles.json` 已被 git 跟踪，不适合继续承载真实 API Key
- `conversation_messages.results` 仍是 `String(500)`，应改为 `Text` 或 JSON
- `backend/api/admin.py` 内联 HTML Admin 页应删除或废弃，管理入口统一到 Vue `/admin`
- `DATABASE_URL` 已环境化，但 `create_engine` 仍无条件传 SQLite 专用 `connect_args`
- Generate 页的“取消生成”目前主要中断前端请求等待；如果后端/模型已开始执行，仍需服务端任务取消能力才能真正停止外部生成

---

## Phase 1: 项目骨架（Vue 3 + FastAPI + SQLite）

**交付内容**：
- Vue 3 + TypeScript + Vite 前端项目初始化
- FastAPI 后端项目初始化（Python 3.10+）
- SQLite 数据库初始化（sqlite3 + SQLAlchemy ORM）
- Element Plus UI 组件库集成
- Tailwind CSS 工具类集成
- 基础目录结构和路由配置
- 前后端通信（Axios + FastAPI CORS）

**关键文件**：
- `img-platform/frontend/package.json` — 前端依赖配置
- `img-platform/frontend/src/main.ts` — Vue 应用入口
- `img-platform/frontend/src/App.vue` — 根组件
- `img-platform/frontend/vite.config.ts` — Vite 配置（CORS、代理）
- `img-platform/backend/requirements.txt` — Python 依赖配置
- `img-platform/backend/main.py` — FastAPI 应用入口
- `img-platform/backend/models/database.py` — 数据库初始化
- `docker-compose.yml` — Docker Compose 基础配置

**验收标准**：
- 前端 `npm run dev` 可启动，访问 `http://localhost:5173`
- 后端 `uvicorn main:app --reload` 可启动，`/docs` 显示 Swagger UI
- Docker Compose 可启动前后端容器

---

## Phase 2: 用户认证系统

**交付内容**：
- users 数据表（id, username, password_hash, is_admin, created_at）
- JWT Token 认证机制（当前为 access_token；refresh_token 未实现）
- 登录 API（POST /api/auth/login）— 返回 JWT Token
- 用户信息 API（GET /api/auth/me）— 获取当前用户信息
- 前端登录页面（用户名 + 密码输入框）
- 认证中间件（保护需要登录的 API 路由）
- 前端 Auth Store（Pinia 状态管理，存储 Token 和用户信息）

**关键文件**：
- `img-platform/backend/models/user.py` — User 模型定义
- `img-platform/backend/schemas/auth.py` — 认证相关的 Pydantic Schema
- `img-platform/backend/api/auth.py` — 认证 API 路由
- `img-platform/backend/core/security.py` — JWT Token 生成和验证、密码哈希
- `img-platform/frontend/src/stores/auth.ts` — 认证状态管理
- `img-platform/frontend/src/views/LoginView.vue` — 登录页面
- `img-platform/frontend/src/router/index.ts` — 路由守卫（需要登录的路由）
- `img-platform/backend/scripts/create_admin.py` — 创建初始管理员账号

**验收标准**：
- 管理员可通过脚本创建初始账号
- 用户输入用户名密码可登录，获取 Token
- 登录后访问需要认证的页面正常，未登录跳转登录页
- 刷新后 Token 不丢失（LocalStorage 持久化）

---

## Phase 3: ComfyUI API 集成

**交付内容**：
- ComfyUI 客户端封装（WebSocket + HTTP API）
- 工作流数据表（workflows: id, name, description, workflow_json, is_enabled, created_at）
- 工作流管理 API（CRUD：/api/workflows）
- 生图任务队列（Celery + Redis）
- 生图 API（POST /api/generate/comfyui）— 提交任务到队列，返回 task_id
- 任务状态 API（GET /api/tasks/{task_id}）— 查询进度和结果
- 生成历史记录表（generations: id, user_id, workflow_id, prompt, negative_prompt, image_path, parameters, created_at）

**关键文件**：
- `img-platform/backend/models/workflow.py` — Workflow 模型定义
- `img-platform/backend/models/generation.py` — Generation 模型定义
- `img-platform/backend/services/comfyui_client.py` — ComfyUI API 客户端封装
- `img-platform/backend/api/workflows.py` — 工作流管理 API
- `img-platform/backend/api/generate.py` — 生图 API
- `img-platform/backend/tasks/generation_tasks.py` — Celery 生图任务
- `img-platform/backend/core/celery_app.py` — Celery 配置
- `img-platform/frontend/src/stores/generation.ts` — 生图状态管理

**验收标准**：
- 管理员可通过 API 上传 ComfyUI JSON 工作流
- 用户可提交生图请求，返回 task_id
- 前端可轮询任务状态，显示进度条
- 生成完成后图像保存到磁盘，记录到数据库

---

## Phase 4: MiniMax API 集成

**交付内容**：
- MiniMax API 客户端封装（HTTP + SSE）
- 提示词优化 API（POST /api/minimax/optimize-prompt）— M2.7 模型扩写 prompt
- 图像理解 API（POST /api/minimax/analyze-image）— 视觉模型分析图像，返回标签和描述
- MiniMax 生图 API（POST /api/generate/minimax）— image-01 模型生图
- API 配额追踪表（api_quotas: id, user_id, model_type, used_tokens, reset_at）
- 配额检查中间件（限制用户 API 调用频率和额度）

**关键文件**：
- `img-platform/backend/services/minimax_client.py` — MiniMax API 客户端封装
- `img-platform/backend/api/minimax.py` — MiniMax 相关 API
- `img-platform/backend/models/api_quota.py` — API 配额模型定义
- `img-platform/backend/middleware/quota_check.py` — 配额检查中间件
- `img-platform/frontend/src/services/minimax.ts` — MiniMax API 前端调用封装

**验收标准**：
- 输入简单描述可调用 M2.7 扩写为详细 prompt
- 上传图像可返回自动标签和描述
- 调用 MiniMax image-01 可生成图像并保存
- API Token 使用量记录到数据库

---

## Phase 5: Generate 生成工作台（核心功能）

**交付内容**：
- 单栏生成工作台布局（顶部项目名/搜索/返回主页，中间生成记录流，底部停靠生成框）
- 生成记录卡片（prompt、模型、比例、风格、时间、图片结果和操作按钮）
- 输入区组件（多行文本框 + AI enhance + 分类/风格/比例/数量/模型选择 + 生成/取消）
- 图像网格展示组件（`1x / 2x / 4x`，支持点击图片查看原图）
- 操作按钮（重新生成、生成变体、下载全部、单图放大/下载；Upscale 当前为占位）
- 加载状态组件（稳定高度占位 + 取消生成按钮）
- Generate 页不再保留左侧侧边栏，历史入口以首页项目卡片和当前记录流为主

**关键文件**：
- `img-platform/frontend/src/views/GenerateView.vue` — 当前生成工作台主页面
- `img-platform/frontend/src/views/HomeView.vue` — 项目首页和生成缩略图入口
- `img-platform/frontend/src/services/api.ts` — Axios API 封装
- 后续如继续扩展，应拆出 `components/chat/*` 和 `composables/useChat.ts`

**验收标准**：
- 用户可输入描述、选择参数、点击生成
- 等待时显示生成中状态，并可取消当前请求等待
- 生成完成后在顶部显示最新记录，旧记录自然向下滚动
- 图片结果按比例完整预览，不裁切、不压扁、不因为生成开始/完成导致整体布局跳动
- 图片结果可点击图片本身或“放大”按钮同页查看原图
- AI enhance 按钮可调用文本模型扩写 prompt，优化结果回填输入框
- 图片生成数量可选择 `1x / 2x / 4x`

---

## Phase 6: 历史记录/图库管理

**交付内容**：
- "我的作品"页面（按日期/标签/工作流筛选）
- 搜索功能（按提示词关键词搜索）
- 图像详情页（大图展示 + 元数据 + 操作按钮）
- 批量下载功能（多选图像打包为 ZIP）
- 提示词库页面（保存的提示词模板，支持分类和标签）
- 收藏/删除功能

**关键文件**：
- `img-platform/frontend/src/views/GalleryView.vue` — 图库页面
- `img-platform/frontend/src/views/PromptLibraryView.vue` — 提示词库页面
- `img-platform/frontend/src/components/gallery/image-card.vue` — 图像卡片
- `img-platform/frontend/src/components/gallery/filter-bar.vue` — 筛选栏
- `img-platform/backend/api/generations.py` — 历史记录 API（列表、搜索、删除）
- `img-platform/backend/api/prompts.py` — 提示词库 API

**验收标准**：
- 用户可查看自己的所有生成历史
- 支持按日期、工作流、标签筛选
- 搜索提示词关键词可找到相关图像
- 可批量下载选中的图像

---

## Phase 7: 管理员后台

**交付内容**：
- 管理员入口（仅 admin 角色可见）
- 用户管理页面（创建账号、禁用账号、重置密码）
- 工作流配置页面（上传 JSON、设置名称说明、启用/禁用）
- API 配额管理页面（MiniMax token 使用统计、自定义配额设置）
- 使用统计页面（生成次数排行、热门模型/工作流、用户活跃度图表）
- 系统设置页面（GPU 监控：温度/显存占用、生成队列管理、系统日志）

**关键文件**：
- `img-platform/frontend/src/views/AdminView.vue` — 当前管理员 Profile 管理页
- `img-platform/backend/api/admin.py` — 管理员 API（用户 CRUD、工作流 CRUD、配额设置）
- `img-platform/backend/api/profiles.py` — Profile 管理 API
- 后续如继续扩展，应拆出 `frontend/src/views/admin/*`

**验收标准**：
- 仅 admin 角色可访问管理员后台
- 可创建/禁用用户账号
- 可管理 MiniMax Profile
- 可上传和管理 ComfyUI 工作流（未完成）
- 可查看 MiniMax token 使用统计（未完成）
- GPU 温度和显存占用实时显示（未完成）

---

## Phase 8: Docker Compose 部署 + 收尾

**交付内容**：
- 完整 Docker Compose 配置（前端、后端、Redis、ComfyUI）
- Nginx 反向代理配置
- 环境变量管理（.env 文件模板）
- 启动脚本（一键部署和启动）
- README.md 文档（安装、配置、使用说明）
- 错误处理和日志系统完善
- 性能优化（图像缓存、数据库索引、API 限流）

**关键文件**：
- `docker-compose.yml` — 完整服务编排
- `docker/nginx.conf` — Nginx 配置
- `.env.example` — 环境变量模板
- `scripts/deploy.sh` — 部署脚本
- `README.md` — 项目文档
- `img-platform/backend/core/logging_config.py` — 日志配置

**验收标准**：
- 执行 `docker-compose up -d` 可一键启动所有服务
- 通过浏览器访问内网 IP 可正常使用
- GPU 监控正常工作，日志记录完整
- README.md 文档清晰，新用户可按指引部署

---

## 技术栈

| 层级 | 技术 | 版本 | 说明 |
|------|------|------|------|
| **前端框架** | Vue 3 + TypeScript | 3.5.x / 6.x | 响应式 UI，类型安全 |
| **UI 组件库** | Element Plus | 2.13.x | 完整的后台组件 |
| **CSS 框架** | Tailwind CSS | 3.4.x | 工具类快速开发 |
| **状态管理** | Pinia | 3.x | Vue 状态管理 |
| **HTTP 客户端** | Axios | 1.15.x | API 调用封装 |
| **构建工具** | Vite | 8.x | 快速开发和打包 |
| **后端框架** | FastAPI | 0.109.x | Python 异步 API，自动文档 |
| **ORM** | SQLAlchemy | 2.0.x | Python 数据库 ORM |
| **数据库** | SQLite | 3.x | 轻量级，无需额外服务 |
| **任务队列** | Celery + Redis | 5.3.x / 7.2.x | 异步生图任务处理 |
| **AI 引擎** | ComfyUI | latest | 本地生图，RTX 4090 GPU |
| **AI API** | MiniMax API | latest | M2.7 文本、视觉模型、image-01 生图 |
| **认证** | JWT (PyJWT) | latest | Token-based 认证 |
| **部署** | Docker + Docker Compose | latest | 容器化一键部署 |
| **包管理** | npm (前端) / pip (后端) | latest | 当前仓库使用 npm lockfile |

---

## 数据库表

| 表名 | 所属 Phase | 用途 |
|------|-----------|------|
| `users` | Phase 2 | 用户账号（id, username, password_hash, is_admin, created_at） |
| `conversations` | Phase 5 | 项目/对话容器（id, user_id, title, created_at） |
| `conversation_messages` | Phase 5 | 对话消息与结果 URL（role, type, content, results, model, task_id） |
| `workflows` | Phase 3 | ComfyUI 工作流配置（id, name, description, workflow_json, is_enabled） |
| `generations` | Phase 3 | 生图历史记录（id, user_id, workflow_id, prompt, image_path, parameters） |
| `api_quotas` | Phase 4 | API 配额追踪（id, user_id, model_type, used_tokens, reset_at） |
| `saved_prompts` | Phase 6 | 提示词库（id, user_id, name, content, tags） |

---

## 开发规则

- 每完成一个 Phase 执行四步走：Code Review → 测试完整性 → 编译验证 → 功能测试
- 四步走全部通过后才能 commit
- Commit message 格式：`phase-N: 简要描述`
- 包管理器：npm（前端）/ pip（后端）
- Python 版本：3.10+
- Node.js 版本：18.x LTS

---

## 已知风险与限制

| Phase | 风险/限制 | 应对方案 |
|-------|----------|---------|
| Phase 3 | ComfyUI API 版本兼容性可能变化 | 封装客户端层，隔离变化；定期更新验证 |
| Phase 4 | MiniMax API 需要网络连通性（可能需要代理） | 配置文件中预留代理设置；错误处理友好提示 |
| Phase 7 | GPU 监控需要 NVIDIA 驱动和 nvidia-smi | Docker 配置中启用 GPU 透传；文档中说明前置要求 |
| 当前版本 | `/minimax-output` 静态目录无鉴权 | 改成 `/api/files/*` 受控文件代理 |
| 当前版本 | Profile 配置可能携带 API Key 且文件已被 git 跟踪 | 改为环境变量引用或加密存储，并从 git 跟踪中移除 |
| Phase 8 | RTX 4090 显存有限（24GB），高并发可能 OOM | Celery 队列限制并发任务数；显存不足时排队等待 |
