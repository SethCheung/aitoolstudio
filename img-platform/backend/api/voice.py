from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import sys, os, uuid, binascii, logging, shutil
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from schemas.voice import VoiceGenerateRequest, VoiceResponse
from schemas.generation import GenerationResponse
from services.minimax import generate_voice as http_generate_voice
from services.cli_runner import generate_voice as cli_generate_voice
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


def normalize_audio_format(req: VoiceGenerateRequest) -> str:
    """兼容旧前端字段 response_format，新的官方参数使用 audio_format。"""
    return req.response_format or req.audio_format


def serve_cli_file(src_path: "Path") -> str:
    """将 CLI 生成的文件复制到 uploads 目录，返回访问路径"""
    ext = src_path.suffix.lstrip(".") or "mp3"
    filename = f"{uuid.uuid4().hex}.{ext}"
    dst = os.path.join(UPLOAD_DIR, filename)
    shutil.copy2(src_path, dst)
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
        auth_type = profile.get("auth_type", "http")
        audio_format = normalize_audio_format(req)
        if auth_type == "cli":
            result = await cli_generate_voice(
                text=req.text,
                voice_id=req.voice_id,
                model=req.model,
                speed=req.speed,
                output_format=audio_format,
            )
        else:
            result = await http_generate_voice(
                text=req.text,
                voice_id=req.voice_id,
                model=req.model,
                speed=req.speed,
                vol=req.vol,
                pitch=req.pitch,
                emotion=req.emotion,
                audio_format=audio_format,
                sample_rate=req.sample_rate,
                bitrate=req.bitrate,
                channel=req.channel,
                subtitle_enable=req.subtitle_enable,
                stream=req.stream,
                latex_read=req.latex_read,
                language_boost=req.language_boost,
                pronunciation_tones=req.pronunciation_tones,
                voice_effect_pitch=req.voice_effect_pitch,
                voice_effect_intensity=req.voice_effect_intensity,
                voice_effect_timbre=req.voice_effect_timbre,
                voice_effect=req.voice_effect,
                api_key=profile["api_key"],
                base_url=profile.get("base_url", "https://api.minimax.io"),
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
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
    audio_value = data.get("audio") or data.get("audio_url") or data.get("url") or ""

    # CLI 模式：audio_value 是 Path 对象（文件路径），直接 serve
    # HTTP 模式：audio_value 是 hex 编码的字符串
    from pathlib import Path
    if isinstance(audio_value, Path):
        audio_url = serve_cli_file(audio_value)
    elif isinstance(audio_value, str) and audio_value.startswith(("http://", "https://")):
        audio_url = audio_value
    else:
        audio_url = save_audio_hex(audio_value, ext=audio_format)

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
        model=gen.voice_model,
        aspect_ratio=None,
        voice_model=gen.voice_model,
        voice_id=gen.voice_id,
        video_model=None,
        video_duration=None,
        n_generated=gen.n_generated,
        created_at=gen.created_at,
    )
