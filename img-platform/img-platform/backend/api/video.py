import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import sys, os
import httpx
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from schemas.video import VideoGenerateRequest, VideoResponse
from schemas.generation import GenerationResponse
from services.minimax import generate_video
from models.database import get_db
from models.generation import Generation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/video", tags=["视频生成"])


@router.post("/generate", response_model=GenerationResponse)
async def generate(req: VideoGenerateRequest, db: Session = Depends(get_db)):
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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        status = e.response.status_code if e.response is not None else 502
        out_status = status if 400 <= status < 500 else 502
        logger.warning("MiniMax upstream error %s: %s", status, e)
        raise HTTPException(status_code=out_status, detail="Upstream video generation failed")
    except httpx.HTTPError as e:
        logger.warning("MiniMax network error: %s", e)
        raise HTTPException(status_code=502, detail="Upstream video generation unreachable")
    except Exception:
        logger.exception("Unexpected error in /api/video/generate")
        raise HTTPException(status_code=500, detail="Internal server error")

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
