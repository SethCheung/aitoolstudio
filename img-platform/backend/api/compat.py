import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth import get_current_user
from models.database import get_db
from models.generation import Generation
from models.user import User
from services.comfyui import generate_image as comfyui_generate_image

logger = logging.getLogger(__name__)
router = APIRouter(tags=["兼容接口"])


class FireCanvasImageRequest(BaseModel):
    model: Optional[str] = Field(default="comfyui-local")
    prompt: str = Field(..., min_length=1, max_length=4000)
    size: Optional[str] = Field(default="1024x1024")
    n: int = Field(default=1, ge=1, le=4)
    seed: Optional[int] = None
    image: Optional[str] = None


def _size_to_dimensions(size: Optional[str]) -> tuple[Optional[int], Optional[int], str]:
    if not size:
        return None, None, "1:1"
    normalized = size.lower().replace("*", "x").replace(":", "x")
    parts = normalized.split("x", 1)
    if len(parts) != 2:
        return None, None, size
    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError:
        return None, None, size
    if width <= 0 or height <= 0:
        return None, None, "1:1"
    return width, height, f"{width}:{height}"


@router.get("/api/fire-canvas/bootstrap.js")
async def fire_canvas_bootstrap():
    frontend_token = os.getenv("FIRE_CANVAS_FRONTEND_TOKEN", "")
    if not frontend_token:
        raise HTTPException(status_code=503, detail="Fire Canvas 后台配置未启用")

    script = f"""
(function () {{
  try {{
    var apiKeys = {{}};
    var baseUrls = {{}};
    try {{
      apiKeys = JSON.parse(localStorage.getItem("api-keys-by-provider") || "{{}}") || {{}};
      baseUrls = JSON.parse(localStorage.getItem("base-urls-by-provider") || "{{}}") || {{}};
    }} catch (parseError) {{}}
    apiKeys.comfyui = {frontend_token!r};
    baseUrls.comfyui = "";
    localStorage.setItem("api-provider", "comfyui");
    // Don't overwrite an existing ATS JWT with the intranet placeholder
    var currentToken = localStorage.getItem("token") || "";
    if (!currentToken || currentToken === "null" || currentToken === "undefined") {{
      localStorage.setItem("token", {frontend_token!r});
    }}
    localStorage.setItem("api-keys-by-provider", JSON.stringify(apiKeys));
    localStorage.setItem("base-urls-by-provider", JSON.stringify(baseUrls));
    localStorage.setItem("fire-canvas-backend-config", "1");
  }} catch (error) {{
    console.warn("[FireCanvas] failed to apply backend API settings", error);
  }}
}})();
""".strip()
    return Response(
        content=script,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/images/generations")
async def fire_canvas_image_generations(
    req: FireCanvasImageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    width, height, aspect_ratio = _size_to_dimensions(req.size)
    try:
        result = await comfyui_generate_image(
            prompt=req.prompt,
            aspect_ratio=aspect_ratio,
            width=width,
            height=height,
            n=req.n,
            seed=req.seed,
            source_image=req.image,
        )
    except Exception as exc:
        logger.exception("Fire canvas ComfyUI image generation failed")
        raise HTTPException(status_code=502, detail=f"ComfyUI 生成失败：{exc}")

    image_urls = result.get("data", {}).get("image_urls", [])
    if not image_urls:
        raise HTTPException(status_code=502, detail="ComfyUI workflow did not return image URLs")

    gen = Generation(
        type="image",
        prompt=req.prompt,
        image_urls=image_urls,
        model="comfyui-local",
        aspect_ratio=aspect_ratio,
        n_generated=len(image_urls),
        mini_max_id=result.get("id", ""),
        user_id=current_user.id,
        worker_id=None,
        run_type="direct_image",
        entrypoint="POST /api/compat/images/generations",
        error_source=None,
    )
    db.add(gen)
    db.commit()
    db.refresh(gen)

    return [
        {
            "url": url,
            "id": str(gen.id),
            "publicProps": {
                "name": f"ComfyUI {index + 1}",
                "prompt": req.prompt,
                "model": "comfyui-local",
            },
        }
        for index, url in enumerate(image_urls)
    ]
