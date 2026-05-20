from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import sys, os, logging, uuid, binascii, shutil
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from schemas.music import MusicGenerateRequest, MusicResponse
from schemas.generation import GenerationResponse
from services.minimax import generate_music as http_generate_music
from services.cli_runner import generate_music as cli_generate_music
from services.profile_manager import get_profile_for_model
from services.storage import upload_category_dir, upload_url
from models.database import get_db
from models.user import User
from models.generation import Generation
from api.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/music", tags=["音乐生成"])

UPLOAD_DIR = upload_category_dir("music")


def save_audio_hex(audio_hex: str, ext: str = "mp3") -> str:
    """将 MiniMax hex 音频保存为本地文件，返回可播放 URL。"""
    try:
        audio_bytes = binascii.unhexlify(audio_hex)
    except (binascii.Error, TypeError, ValueError):
        raise HTTPException(status_code=502, detail="Invalid music audio data from MiniMax API")
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = UPLOAD_DIR / filename
    with filepath.open("wb") as f:
        f.write(audio_bytes)
    return upload_url("music", filename)


def serve_cli_file(src_path: Path) -> str:
    """将 CLI 生成的音乐复制到 uploads 目录，返回可播放 URL。"""
    ext = src_path.suffix.lstrip(".") or "mp3"
    filename = f"{uuid.uuid4().hex}.{ext}"
    dst = UPLOAD_DIR / filename
    shutil.copy2(src_path, dst)
    return upload_url("music", filename)


def resolve_music_audio_url(result: dict, ext: str) -> str:
    data = result.get("data", {})
    audio_value = data.get("audio") or data.get("audio_url") or data.get("url") or ""
    if isinstance(audio_value, Path):
        return serve_cli_file(audio_value)
    if isinstance(audio_value, str) and audio_value.startswith(("http://", "https://", "/")):
        return audio_value
    return save_audio_hex(audio_value, ext=ext)


@router.post("/generate", response_model=GenerationResponse)
async def generate(
    req: MusicGenerateRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """文生音乐 — 按模型路由到对应 profile"""
    profile = get_profile_for_model(req.model)
    if not profile:
        raise HTTPException(
            status_code=400,
            detail=f"No enabled profile found for model '{req.model}'",
        )
    try:
        auth_type = profile.get("auth_type", "http")
        if auth_type == "cli":
            result = await cli_generate_music(
                prompt=req.prompt,
                model=req.model,
                lyrics=req.lyrics,
                is_instrumental=req.is_instrumental,
                lyrics_optimizer=req.lyrics_optimizer,
            )
        else:
            result = await http_generate_music(
                prompt=req.prompt,
                model=req.model,
                lyrics=req.lyrics,
                is_instrumental=req.is_instrumental,
                lyrics_optimizer=req.lyrics_optimizer,
                audio_format=req.audio_format,
                output_format=req.output_format,
                sample_rate=req.sample_rate,
                bitrate=req.bitrate,
                seed=req.seed,
                aigc_watermark=req.aigc_watermark,
                reference_audio_url=req.reference_audio_url,
                api_key=profile["api_key"],
                base_url=profile.get("base_url", "https://api.minimax.io"),
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Music generation failed")
        raise HTTPException(status_code=500, detail="生成失败，请稍后重试")

    base_resp = result.get("base_resp", {})
    if base_resp.get("status_code", 0) != 0:
        raise HTTPException(
            status_code=400,
            detail=f"MiniMax Music API error: {base_resp.get('status_msg', 'unknown')}",
        )

    audio_url = resolve_music_audio_url(result, ext=req.audio_format)

    gen = Generation(
        type="music",
        prompt=req.prompt,
        audio_url=audio_url,
        voice_model=req.model,
        n_generated=1,
        mini_max_id=result.get("trace_id", ""),
        worker_id=None,
        run_type="direct_music",
        entrypoint="POST /api/music/generate",
        error_source=None,
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
        voice_id=None,
        video_model=None,
        video_duration=None,
        n_generated=gen.n_generated,
        created_at=gen.created_at,
    )
