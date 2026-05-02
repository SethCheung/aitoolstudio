from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import sys, os, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from schemas.voice import VoiceGenerateRequest, VoiceResponse
from schemas.generation import GenerationResponse
from services.minimax import generate_voice
from models.database import get_db
from models.user import User
from models.generation import Generation
from api.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/voice", tags=["语音生成"])


@router.post("/generate", response_model=GenerationResponse)
async def generate(
    req: VoiceGenerateRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """文合成语音 — 代理 MiniMax TTS API，生成后入库"""
    try:
        result = await generate_voice(
            text=req.text,
            voice_id=req.voice_id,
            model=req.model,
            speed=req.speed,
            vol=req.vol,
            pitch=req.pitch,
            emotion=req.emotion,
            response_format=req.response_format,
        )
    except Exception:
        logger.exception("Voice generation failed")
        raise HTTPException(status_code=500, detail="生成失败，请稍后重试")

    base_resp = result.get("base_resp", {})
    if base_resp.get("status_code", 0) != 0:
        raise HTTPException(
            status_code=400,
            detail=f"MiniMax TTS API error: {base_resp.get('status_msg', 'unknown')}",
        )

    data = result.get("data", {})
    audio_url = data.get("audio_url", "")

    gen = Generation(
        type="voice",
        prompt=req.text,
        audio_url=audio_url,
        voice_model=req.model,
        voice_id=req.voice_id,
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
        voice_id=gen.voice_id,
        video_model=None,
        video_duration=None,
        n_generated=gen.n_generated,
        created_at=gen.created_at,
    )
