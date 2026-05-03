from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from schemas.image import ImageGenerateRequest
from schemas.generation import GenerationResponse
from services.minimax import generate_image
from services.profile_manager import get_profile_for_model
from models.database import get_db
from models.generation import Generation

router = APIRouter(prefix="/api/image", tags=["图像生成"])


@router.post("/generate", response_model=GenerationResponse)
async def generate(req: ImageGenerateRequest, db: Session = Depends(get_db)):
    """文生图 — 按模型自动路由到对应 profile"""
    profile = get_profile_for_model(req.model)
    if not profile:
        raise HTTPException(
            status_code=400,
            detail=f"No enabled profile found for model '{req.model}'",
        )

    try:
        result = await generate_image(
            prompt=req.prompt,
            model=req.model,
            aspect_ratio=req.aspect_ratio,
            n=req.n,
            response_format=req.response_format,
            prompt_optimizer=req.prompt_optimizer,
            api_key=profile["api_key"],
            base_url=profile.get("base_url", "https://api.minimaxi.com"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    base_resp = result.get("base_resp", {})
    if base_resp.get("status_code", 0) != 0:
        raise HTTPException(
            status_code=400,
            detail=f"MiniMax API error: {base_resp.get('status_msg', 'unknown')}",
        )

    data = result.get("data", {})
    metadata = result.get("metadata", {})

    image_urls = data.get("image_urls", []) if req.response_format == "url" else data.get("image_base64", [])

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
        image_urls=gen.image_urls or [],
        audio_url=None,
        video_url=None,
        model=gen.model or "",
        aspect_ratio=gen.aspect_ratio,
        voice_model=None,
        voice_id=None,
        video_model=None,
        video_duration=None,
        n_generated=gen.n_generated,
        created_at=gen.created_at,
    )
