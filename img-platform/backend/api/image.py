from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import sys, os, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from schemas.image import ImageGenerateRequest
from schemas.generation import GenerationResponse
from services.minimax import generate_image as http_generate_image
from services.cli_runner import generate_image as cli_generate_image
from services.profile_manager import get_profile_for_model
from models.database import get_db
from models.user import User
from models.generation import Generation
from api.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/image", tags=["图像生成"])


@router.post("/generate", response_model=GenerationResponse)
async def generate(
    req: ImageGenerateRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """文生图 — 按模型自动路由到对应 profile"""
    profile = get_profile_for_model(req.model)
    if not profile:
        raise HTTPException(
            status_code=400,
            detail=f"No enabled profile found for model '{req.model}'",
        )

    try:
        auth_type = profile.get("auth_type", "http")
        if auth_type == "cli":
            result = await cli_generate_image(
                prompt=req.prompt,
                model=req.model,
                aspect_ratio=req.aspect_ratio,
                n=req.n,
            )
        else:
            result = await http_generate_image(
                prompt=req.prompt,
                model=req.model,
                aspect_ratio=req.aspect_ratio,
                n=req.n,
                response_format=req.response_format,
                prompt_optimizer=req.prompt_optimizer,
                api_key=profile["api_key"],
                base_url=profile.get("base_url", "https://api.minimax.io"),
            )
    except Exception:
        logger.exception("Image generation failed")
        raise HTTPException(status_code=500, detail="生成失败，请稍后重试")

    base_resp = result.get("base_resp", {})
    if base_resp.get("status_code", 0) != 0:
        raise HTTPException(
            status_code=400,
            detail=f"MiniMax API error: {base_resp.get('status_msg', 'unknown')}",
        )

    data = result.get("data", {})
    metadata = result.get("metadata", {})

    image_urls = data.get("image_urls", []) if req.response_format == "url" else data.get("image_base64", [])

    logger.warning(f"[image/generate] image_urls from mmx: {image_urls}")
    logger.warning(f"[image/generate] type: {type(image_urls)}")

    gen = Generation(
        prompt=req.prompt,
        image_urls=image_urls,
        model=req.model,
        aspect_ratio=req.aspect_ratio,
        n_generated=len(image_urls),
        mini_max_id=result.get("id", ""),
    )
    db.add(gen)
    db.commit()
    db.refresh(gen)

    return GenerationResponse(
        id=gen.id,
        type="image",
        prompt=gen.prompt,
        image_urls=gen.image_urls,
        audio_url=None,
        video_url=None,
        model=gen.model,
        aspect_ratio=gen.aspect_ratio,
        voice_model=None,
        voice_id=None,
        video_model=None,
        video_duration=None,
        n_generated=gen.n_generated,
        created_at=gen.created_at,
    )
