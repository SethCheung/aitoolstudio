from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from typing import Optional
import sys, os, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.security import decode_access_token
from schemas.image import ImageGenerateRequest, ImageUpscaleRequest
from schemas.generation import GenerationResponse
from services.minimax import generate_image as http_generate_image
from services.comfyui import generate_image as comfyui_generate_image, upscale_image as comfyui_upscale_image
from services.comfyui_scheduler import (
    SchedulerError,
    SchedulerJob,
    build_job_from_image_request,
    select_worker,
)
from services.comfyui_workflows import runtime_workflow
from services.cli_runner import generate_image as cli_generate_image
from services.profile_manager import get_profile_for_model
from models.database import get_db
from models.user import User
from models.generation import Generation
from api.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/image", tags=["图像生成"])
optional_security = HTTPBearer(auto_error=False)


def get_image_request_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Accept normal JWTs plus the backend-owned Fire Canvas frontend token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authenticated",
        )

    token = credentials.credentials
    fire_canvas_token = os.getenv("FIRE_CANVAS_FRONTEND_TOKEN", "")
    if fire_canvas_token and token == fire_canvas_token:
        return None

    token_data = decode_access_token(token)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(User).filter(User.id == token_data.user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )
    return user


@router.post("/upscale", response_model=GenerationResponse)
async def upscale(
    req: ImageUpscaleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """ComfyUI 图片放大 — 当前使用 ImageScale 2x/4x 等比例放大"""
    try:
        # ── Scheduler: select a worker for upscale ──
        job = SchedulerJob(
            job_class="medium",
            required_tags=["upscale"],
            estimated_vram_gb=8,
            reason="image upscale",
        )
        try:
            selected = await select_worker(job)
        except SchedulerError as exc:
            logger.warning("Scheduler could not find worker for upscale: %s", exc)
            raise HTTPException(
                status_code=502,
                detail=f"无可用 ComfyUI Worker 处理放大任务. {exc}",
            )

        logger.info(
            "Scheduler selected worker %s (tier=%s) for upscale",
            selected.get("id"), selected.get("tier"),
        )
        result = await comfyui_upscale_image(
            source_url=req.source_url,
            scale=req.scale,
            method=req.method,
            base_url=selected["url"],
        )
        logger.info(
            "Upscale dispatched — worker=%s url=%s tier=%s job_class=%s tags=%s models=%s nodes=%s",
            selected.get("id"), selected["url"], selected.get("tier"),
            job.job_class, job.required_tags, job.required_models, job.required_nodes,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "ComfyUI upscale failed — worker=%s url=%s tier=%s",
            selected.get("id"), selected.get("url", "N/A"), selected.get("tier"),
        )
        raise HTTPException(status_code=502, detail="ComfyUI 放大失败，请检查源图和本地服务")

    image_urls = result.get("data", {}).get("image_urls", [])
    gen = Generation(
        prompt=f"Upscale image: {req.source_url}",
        image_urls=image_urls,
        model="comfyui-upscale",
        aspect_ratio=req.aspect_ratio,
        n_generated=len(image_urls),
        mini_max_id=result.get("id", ""),
        user_id=current_user.id,
        worker_id=selected.get("id"),
        run_type="upscale",
        entrypoint="POST /api/image/upscale",
        error_source=None,
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


@router.post("/generate", response_model=GenerationResponse)
async def generate(
    req: ImageGenerateRequest,
    db: Session = Depends(get_db),
    _current_user: Optional[User] = Depends(get_image_request_user),
):
    """文生图 — 按模型自动路由到对应 profile"""
    if req.model == "comfyui-local":
        reference_images = [item.image_file for item in req.subject_reference]
        try:
            workflow = None
            if req.comfyui_workflow_id:
                try:
                    workflow = runtime_workflow(
                        workflow_id=req.comfyui_workflow_id,
                        prompt=req.prompt,
                        aspect_ratio=req.aspect_ratio,
                        width=req.width,
                        height=req.height,
                        n=req.n,
                        seed=req.seed,
                        checkpoint=req.comfyui_checkpoint,
                        steps=req.comfyui_steps,
                        cfg=req.comfyui_cfg,
                        denoise=req.comfyui_denoise,
                    )
                except ValueError:
                    logger.warning(
                        "Unknown ComfyUI workflow '%s'; falling back to default image workflow",
                        req.comfyui_workflow_id,
                    )

            # ── Scheduler: select best worker for this job ──
            job = build_job_from_image_request(req, workflow=workflow)
            if req.comfyui_checkpoint:
                job.required_models.append(req.comfyui_checkpoint)
            # Merge workflow scheduling fields (if workflow carries them)
            if workflow and isinstance(workflow, dict):
                wf_meta = workflow.get("_scheduler") or {}
                if wf_meta.get("required_worker_tier"):
                    job.job_class = wf_meta["required_worker_tier"]
                for field in ("required_worker_tags", "required_models", "required_nodes"):
                    extras = wf_meta.get(field) or []
                    existing = getattr(job, field, [])
                    merged = list({*[str(v).lower() for v in existing], *[str(v).lower() for v in extras]})
                    setattr(job, field, merged)
                if wf_meta.get("estimated_vram_gb"):
                    job.estimated_vram_gb = max(job.estimated_vram_gb, float(wf_meta["estimated_vram_gb"]))

            try:
                selected = await select_worker(job)
            except SchedulerError as exc:
                logger.warning("Scheduler could not find worker: %s", exc)
                raise HTTPException(
                    status_code=502,
                    detail=f"无可用 ComfyUI Worker. {exc}",
                )

            worker_url = selected["url"]
            logger.info(
                "Scheduler selected worker %s (tier=%s) for image generation",
                selected.get("id"), selected.get("tier"),
            )

            result = await comfyui_generate_image(
                prompt=req.prompt,
                aspect_ratio=req.aspect_ratio,
                width=req.width,
                height=req.height,
                n=req.n,
                seed=req.seed,
                checkpoint=req.comfyui_checkpoint,
                workflow=workflow,
                source_image=reference_images[0] if reference_images else None,
                mask_image=reference_images[1] if len(reference_images) > 1 else None,
                mask_point=(req.sam_x, req.sam_y) if req.sam_x is not None and req.sam_y is not None else None,
                base_url=worker_url,
            )
            logger.info(
                "Image generation dispatched — worker=%s url=%s tier=%s job_class=%s tags=%s models=%s nodes=%s",
                selected.get("id"), worker_url, selected.get("tier"),
                job.job_class, job.required_tags, job.required_models, job.required_nodes,
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception(
                "ComfyUI image generation failed — worker=%s url=%s tier=%s",
                selected.get("id"), worker_url, selected.get("tier"),
            )
            raise HTTPException(status_code=502, detail=f"ComfyUI 生成失败：{exc}")

        data = result.get("data", {})
        image_urls = data.get("image_urls", [])
        gen = Generation(
            prompt=req.prompt,
            image_urls=image_urls,
            model=req.model,
            aspect_ratio=req.aspect_ratio,
            n_generated=len(image_urls),
            mini_max_id=result.get("id", ""),
            user_id=_current_user.id if _current_user else None,
            worker_id=selected.get("id"),
            run_type="direct_image",
            entrypoint="POST /api/image/generate",
            error_source=None,
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
                width=req.width,
                height=req.height,
                n=req.n,
                response_format=req.response_format,
                prompt_optimizer=req.prompt_optimizer,
                seed=req.seed,
                aigc_watermark=req.aigc_watermark,
                style=req.style.model_dump() if req.style else None,
                subject_reference=[item.model_dump() for item in req.subject_reference],
            )
        else:
            result = await http_generate_image(
                prompt=req.prompt,
                model=req.model,
                aspect_ratio=req.aspect_ratio,
                width=req.width,
                height=req.height,
                n=req.n,
                response_format=req.response_format,
                prompt_optimizer=req.prompt_optimizer,
                seed=req.seed,
                aigc_watermark=req.aigc_watermark,
                style=req.style.model_dump() if req.style else None,
                subject_reference=[item.model_dump() for item in req.subject_reference],
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
        user_id=_current_user.id if _current_user else None,
        worker_id=None,
        run_type="direct_image",
        entrypoint="POST /api/image/generate",
        error_source=None,
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
