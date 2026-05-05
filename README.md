# 内网 AI 生图协作平台

基于 Vue 3 + FastAPI 的内网 AI 创作协作平台。当前版本优先打通 MiniMax/Profile 路由、图片/语音/视频/音乐生成、项目首页、对话历史、管理员配置和生成结果预览；ComfyUI 工作流、队列、GPU 监控仍是后续阶段。

## 当前状态

| 模块 | 状态 | 说明 |
|------|------|------|
| 登录认证 | 已实现 | JWT Bearer Token，登录接口有限流 |
| 项目首页 | 已实现 | 展示用户项目，对话中有图片结果时显示缩略图 |
| 生成页面 | 已实现 | 支持 image / voice / video / music 分类生成，图片结果可点开同页看原图 |
| AI 优化 | 已实现 | 用户点击「AI 优化」后调用文本模型扩写 prompt，结果回填输入框 |
| 对话历史 | 已实现 | 保存用户消息和 AI 回复，支持恢复对话 |
| Profile 管理 | 已实现 | Vue Admin 页面管理 MiniMax HTTP/CLI profile |
| Admin 鉴权 | 已加固 | `/api/admin/*` 和 profile 管理接口要求管理员 |
| ComfyUI 工作流 | 未实现 | 仍在计划中 |
| 生成队列 / Redis / Celery | 未实现 | 仍在计划中 |
| 文件访问鉴权 | 待修复 | `/minimax-output` 当前仍是静态目录，生产前必须改 |

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Vite + Pinia + Element Plus + Tailwind CSS |
| 后端 | FastAPI + SQLAlchemy + SQLite |
| AI 接入 | MiniMax HTTP API + MiniMax CLI (`mmx`) |
| 认证 | JWT Bearer Token |
| 部署 | 本地开发 / Docker Compose |

当前 `package.json` 使用 npm 生态；不要按旧文档使用 pnpm。

## 本地开发启动

### 1. 后端

```bash
cd img-platform/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

编辑 `.env`，至少设置：

```bash
JWT_SECRET_KEY=<openssl rand -hex 32 生成的值>
MINIMAX_API_KEY=<可选，仅 HTTP profile 需要>
```

启动后端：

```bash
export JWT_SECRET_KEY="$(grep JWT_SECRET_KEY .env | cut -d= -f2)"
uvicorn main:app --reload --port 8000
```

后端地址：

- API 健康检查：http://localhost:8000/api/health
- Swagger 文档：http://localhost:8000/docs

不要再把 `http://localhost:8000/admin` 当主要管理入口。后端内联 Admin 页已经被管理员鉴权挡住，且不会自动带浏览器里的前端 Token；当前可用管理入口是前端 `/admin`。

### 2. 创建管理员账号

```bash
cd img-platform/backend
source venv/bin/activate
export JWT_SECRET_KEY="$(grep JWT_SECRET_KEY .env | cut -d= -f2)"
python scripts/create_admin.py
```

脚本默认账号是 `admin / admin123`。本地调试可以用，真实环境第一件事就是改密码。别拿默认密码上线，除非你想把项目献祭给同事的好奇心。

### 3. 前端

```bash
cd img-platform/frontend
npm install
npm run dev
```

访问：

- 前端：http://localhost:5173
- 管理页：http://localhost:5173/admin

如果后端不是 8000 端口：

```bash
VITE_API_BASE_URL=http://localhost:8001 npm run dev
```

## Docker Compose

Docker Compose 启动前必须提供 `JWT_SECRET_KEY`：

```bash
export JWT_SECRET_KEY="$(openssl rand -hex 32)"
export MINIMAX_API_KEY="" # 可选
docker-compose up -d
```

当前 Compose 只编排前后端基础服务。Redis、Celery、ComfyUI、Nginx 仍是后续部署阶段。

## MiniMax 配置

当前支持两类 profile：

- CLI profile：通过本机 `mmx` 命令生成，输出文件默认落在 `~/minimax-output`
- HTTP profile：通过 MiniMax HTTP API 调用，需要 API Key

提示词优化使用 text 模型 profile。默认配置包含 `MiniMax-M2.7` 和 `MiniMax-M2.7-highspeed`。如果你新建 HTTP profile，记得在 text 分类里勾选文本模型；否则前端「AI 优化」会找不到可用 profile。

官方文档：

- Image Generation: https://platform.minimax.io/docs/guides/image-generation
- Video Generation: https://platform.minimax.io/docs/guides/video-generation
- Speech T2A HTTP: https://platform.minimax.io/docs/api-reference/speech-t2a-http

注意：视频生成是异步流程，通常先拿 `task_id`，查询成功后再拿 `file_id` 下载文件。不要把它当成同步返回视频 URL 的接口设计。

## 项目结构

```text
img-platform/
├── frontend/
│   ├── src/
│   │   ├── views/
│   │   │   ├── HomeView.vue
│   │   │   ├── GenerateView.vue
│   │   │   ├── AdminView.vue
│   │   │   └── LoginView.vue
│   │   ├── stores/
│   │   ├── router/
│   │   └── services/
│   └── package.json
├── backend/
│   ├── api/
│   ├── models/
│   ├── schemas/
│   ├── services/
│   ├── scripts/create_admin.py
│   └── main.py
└── docker-compose.yml
```

## 验证命令

```bash
cd img-platform/frontend
npm run build
```

```bash
cd img-platform/backend
JWT_SECRET_KEY=0123456789abcdef0123456789abcdef \
DATABASE_URL=sqlite:///./data/check.db \
venv/bin/python -m compileall -q api core models schemas services main.py
```

## 重要安全提醒

生产前必须处理：

- `/minimax-output` 当前是公开静态目录，需要改成带鉴权的文件代理
- `profiles.json` 仍可能承载 API Key，不能继续作为普通代码文件提交
- Token 当前存 `localStorage`，存在 XSS 风险
- SQLite 适合 10 人内网 MVP，不适合高并发和严格审计

详见 [SECURITY.md](./SECURITY.md)。

## 许可证

内部项目，仅供团队使用。
