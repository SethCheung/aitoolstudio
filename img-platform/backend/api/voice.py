from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import sys, os, uuid, binascii, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from schemas.voice import VoiceGenerateRequest, VoiceResponse
from schemas.generation import GenerationResponse
from services.minimax import generate_voice
from services.profile_manager import get_profile_for_model
from models.database import get_db
from models.user import User
from models.generation import Generation
from api.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/voice", tags=["语音生成"])

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads", "voices")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def save_audio_hex(audio_hex: str, ext: str = "mp3") -> str:
    """将 hex 编码的音频数据保存为文件，返回访问路径"""
    try:
        audio_bytes = binascii.unhexlify(audio_hex)
    except (binascii.Error, TypeError, ValueError):
        raise HTTPException(status_code=502, detail="Invalid audio data from MiniMax API")
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "wb") as f:
        f.write(audio_bytes)
    return f"/uploads/voices/{filename}"


@router.post("/generate", response_model=GenerationResponse)
async def generate(
    req: VoiceGenerateRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """文合成语音 — 按模型路由到对应 profile"""
    profile = get_profile_for_model(req.model)
    if not profile:
        raise HTTPException(
            status_code=400,
            detail=f"No enabled profile found for model '{req.model}'",
        )
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
            api_key=profile["api_key"],
            base_url=profile.get("base_url", "https://api.minimaxi.com"),
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
    audio_hex = data.get("audio", "")
    audio_url = save_audio_hex(audio_hex, ext=req.response_format)

    gen = Generation(
        type="voice",
        prompt=req.text,
        audio_url=audio_url,
        voice_model=req.model,
        voice_id=req.voice_id,
        n_generated=1,
        mini_max_id=result.get("trace_id", ""),
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
