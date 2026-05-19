from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from dotenv import load_dotenv
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

import sys
sys.path.insert(0, os.path.dirname(__file__))
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from api.auth import router as auth_router
from api.admin import router as admin_router
from api.profiles import router as profiles_router
from api.image import router as image_router
from api.voice import router as voice_router
from api.video import router as video_router
from api.music import router as music_router
from api.prompt import router as prompt_router
from api.generation import router as generation_router
from api.conversation import router as conversation_router
from api.comfyui import router as comfyui_router
from api.canvas import router as canvas_router
from api.compat import router as compat_router
import models.canvas
from models.database import init_db
from services.storage import ensure_dir, get_minimax_output_root, get_upload_root

from limiter import limiter

app = FastAPI(
    title="AI 生图协作平台 API",
    description="内网 AI 生图协作平台 - FastAPI 后端",
    version="0.2.0",
)

# Attach rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS 配置 — 限制来源和方法
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.on_event("startup")
def on_startup():
    """启动时初始化数据库"""
    init_db()


# 注册路由
app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(conversation_router)
app.include_router(image_router)
app.include_router(voice_router)
app.include_router(video_router)
app.include_router(music_router)
app.include_router(prompt_router)
app.include_router(generation_router)
app.include_router(profiles_router)
app.include_router(comfyui_router)
app.include_router(canvas_router)
app.include_router(compat_router)

# 挂载静态文件（语音文件等）
UPLOAD_DIR = ensure_dir(get_upload_root())
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# 挂载 MiniMax CLI 输出目录（Token Plan 用户生成的文件）
MINIMAX_OUTPUT_DIR = ensure_dir(get_minimax_output_root())
app.mount("/minimax-output", StaticFiles(directory=str(MINIMAX_OUTPUT_DIR), html=True), name="minimax-output")


@app.get("/")
async def root():
    return {"message": "AI 生图协作平台 API - 运行中", "docs": "/docs"}


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "version": "0.2.0"}
