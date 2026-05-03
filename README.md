# 内网 AI 生图协作平台

基于 Vue 3 + FastAPI 的本地部署 AI 生图协作平台，整合 ComfyUI 工作流引擎和 MiniMax API 能力。

## 技术栈

| 层级 | 技术 |
|------|------|
| **前端** | Vue 3 + TypeScript + Element Plus + Tailwind CSS |
| **后端** | FastAPI (Python 3.10+) + SQLAlchemy + SQLite |
| **任务队列** | Celery + Redis (Phase 3) |
| **AI 引擎** | ComfyUI (本地 GPU) + MiniMax API |
| **部署** | Docker Compose |

## 快速开始

### 前置要求

- Node.js 18.x+
- Python 3.10+
- Docker + Docker Compose (可选，用于容器化部署)
- NVIDIA GPU + CUDA 环境 (ComfyUI 生图需要)

### 开发模式启动

**前端**：
```bash
cd img-platform/frontend
npm install
npm run dev
```

访问 http://localhost:5173

**后端**：
```bash
cd img-platform/backend
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
export JWT_SECRET_KEY="$(openssl rand -hex 32)"
uvicorn main:app --reload
```

访问 http://localhost:8000/admin 打开 API 配置面板，访问 http://localhost:8000/docs 查看 Swagger UI

如果本机 8000 端口已被其他服务占用，可以换端口启动后端，并让前端指向新端口：

```bash
# backend
uvicorn main:app --reload --port 8001

# frontend
VITE_API_BASE_URL=http://localhost:8001 npm run dev
```

### Docker Compose 部署

```bash
docker-compose up -d
```

## 项目结构

```
img-platform/
├── frontend/           # Vue 3 前端项目
│   ├── src/
│   │   ├── components/ # UI 组件
│   │   ├── views/      # 页面视图
│   │   ├── stores/     # Pinia 状态管理
│   │   └── router/     # 路由配置
│   ├── package.json
│   └── vite.config.ts
├── backend/            # FastAPI 后端项目
│   ├── api/           # API 路由
│   ├── models/        # SQLAlchemy 模型
│   ├── schemas/       # Pydantic Schema
│   ├── services/      # 业务服务层
│   └── main.py        # FastAPI 入口
├── docker-compose.yml
└── README.md
```

## 开发阶段

- ✅ **Phase 1**: 项目骨架（Vue 3 + FastAPI + SQLite）
- ⏳ **Phase 2**: 用户认证系统
- ⏳ **Phase 3**: ComfyUI API 集成
- ⏳ **Phase 4**: MiniMax API 集成
- ⏳ **Phase 5**: 对话式生图界面
- ⏳ **Phase 6**: 历史记录/图库管理
- ⏳ **Phase 7**: 管理员后台
- ⏳ **Phase 8**: Docker Compose 部署 + 收尾

## API 文档

后端启动后访问：
- API 配置面板: http://localhost:8000/admin
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 许可证

内部项目，仅供团队使用。
