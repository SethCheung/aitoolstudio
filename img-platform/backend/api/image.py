from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from schemas.image import ImageGenerateRequest
from schemas.generation import GenerationResponse
from services.minimax import generate_image
from models.database import get_db
from models.generation import Generation

router = APIRouter(prefix="/api/image", tags=["图像生成"])


@router.post("/generate", response_model=GenerationResponse)
async def generate(req: ImageGenerateRequest, db: Session = Depends(get_db)):
    """文生图 — 代理 MiniMax API，生成后入库"""
    try:
        result = await generate_image(
            prompt=req.prompt,
            model=req.model,
            aspect_ratio=req.aspect_ratio,
            n=req.n,
            response_format=req.response_format,
            prompt_optimizer=req.prompt_optimizer,
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

    # 保存到数据库
    gen = Generation(
        type="image",
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
        type=gen.type or "image",
        prompt=gen.prompt,
        image_urls=gen.image_urls or image_urls,
        audio_url=gen.audio_url,
        video_url=gen.video_url,
        model=gen.model or "",
        aspect_ratio=gen.aspect_ratio,
        voice_model=gen.voice_model,
        voice_id=gen.voice_id,
        video_model=gen.video_model,
        video_duration=gen.video_duration,
        n_generated=gen.n_generated or 0,
        created_at=gen.created_at,
    )
