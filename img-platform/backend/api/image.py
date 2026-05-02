from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import sys, os, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from schemas.image import ImageGenerateRequest
from schemas.generation import GenerationResponse
from services.minimax import generate_image
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

    # 保存到数据库
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
        prompt=gen.prompt,
        image_urls=image_urls,
        model=gen.model,
        aspect_ratio=gen.aspect_ratio,
        n_generated=gen.n_generated,
        created_at=gen.created_at,
    )
