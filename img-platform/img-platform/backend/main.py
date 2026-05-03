from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from api.auth import router as auth_router
from api.image import router as image_router
from api.voice import router as voice_router
from api.video import router as video_router
from api.music import router as music_router
from api.generation import router as generation_router
from api.profiles import router as profiles_router
from models.database import init_db

app = FastAPI(
    title="AI 生图协作平台 API",
    description="内网 AI 生图协作平台 - FastAPI 后端",
    version="0.2.0",
)

# CORS 配置 - 允许前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    """启动时初始化数据库"""
    init_db()


# 注册路由
app.include_router(auth_router)
app.include_router(image_router)
app.include_router(voice_router)
app.include_router(video_router)
app.include_router(music_router)
app.include_router(generation_router)
app.include_router(profiles_router)


@app.get("/")
async def root():
    return {"message": "AI 生图协作平台 API - 运行中", "docs": "/docs"}


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "version": "0.2.0"}
