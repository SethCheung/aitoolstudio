from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from schemas.music import MusicGenerateRequest, MusicResponse
from schemas.generation import GenerationResponse
from services.minimax import generate_music
from models.database import get_db
from models.generation import Generation

router = APIRouter(prefix="/api/music", tags=["音乐生成"])


@router.post("/generate", response_model=GenerationResponse)
async def generate(req: MusicGenerateRequest, db: Session = Depends(get_db)):
    """文生音乐 — 代理 MiniMax Music API，生成后入库"""
    try:
        result = await generate_music(
            prompt=req.prompt,
            model=req.model,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    base_resp = result.get("base_resp", {})
    if base_resp.get("status_code", 0) != 0:
        raise HTTPException(
            status_code=400,
            detail=f"MiniMax Music API error: {base_resp.get('status_msg', 'unknown')}",
        )

    data = result.get("data", {})
    audio_url = data.get("audio_url", "")

    gen = Generation(
        type="music",
        prompt=req.prompt,
        audio_url=audio_url,
        voice_model=req.model,
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
        audio_url=gen.audio_url,
        video_url=None,
        model=gen.voice_model or "",
        aspect_ratio=None,
        voice_model=gen.voice_model,
        voice_id=None,
        video_model=None,
        video_duration=None,
        n_generated=gen.n_generated,
        created_at=gen.created_at,
    )
