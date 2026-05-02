from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import sys, os, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from schemas.video import VideoGenerateRequest, VideoResponse
from schemas.generation import GenerationResponse
from services.minimax import generate_video
from models.database import get_db
from models.user import User
from models.generation import Generation
from api.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/video", tags=["视频生成"])


@router.post("/generate", response_model=GenerationResponse)
async def generate(
    req: VideoGenerateRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """文生视频 — 代理 MiniMax Hailuo API，生成后入库"""
    try:
        result = await generate_video(
            prompt=req.prompt,
            model=req.model,
            duration=req.duration,
            resolution=req.resolution,
            fps=req.fps,
            seed=req.seed,
        )
    except Exception:
        logger.exception("Video generation failed")
        raise HTTPException(status_code=500, detail="生成失败，请稍后重试")

    base_resp = result.get("base_resp", {})
    if base_resp.get("status_code", 0) != 0:
        raise HTTPException(
            status_code=400,
            detail=f"MiniMax Hailuo API error: {base_resp.get('status_msg', 'unknown')}",
        )

    data = result.get("data", {})
    video_url = data.get("video_url", "")

    gen = Generation(
        type="video",
        prompt=req.prompt,
        video_url=video_url,
        video_model=req.model,
        video_duration=req.duration,
        n_generated=1,
        mini_max_id=result.get("id", ""),
    )
    db.add(gen)
    db.commit()
    db.refresh(gen)

    return GenerationResponse(
        id=gen.id,
        type=gen.type,
        prompt=gen.prompt,
        image_urls=[],
        audio_url=None,
        video_url=gen.video_url,
        model=gen.video_model or "",
        aspect_ratio=None,
        voice_model=None,
        voice_id=None,
        video_model=gen.video_model,
        video_duration=gen.video_duration,
        n_generated=gen.n_generated,
        created_at=gen.created_at,
    )
