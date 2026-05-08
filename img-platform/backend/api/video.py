from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import sys, os, logging, httpx, uuid
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from schemas.video import VideoGenerateRequest
from schemas.generation import GenerationResponse
from services.minimax import (
    generate_video as http_generate_video,
    query_video_task as http_query_video_task,
    retrieve_video_file as http_retrieve_video_file,
)
from services.cli_runner import generate_video as cli_generate_video
from services.comfyui import generate_video as comfyui_generate_video
from services.comfyui_workflows import runtime_workflow
from services.profile_manager import get_profile_for_model
from services.storage import upload_category_dir, upload_url
from models.database import get_db
from models.user import User
from models.generation import Generation
from api.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/video", tags=["视频生成"])

UPLOAD_DIR = upload_category_dir("videos")


def normalize_video_status(status: str | int | None) -> str:
    normalized = str(status or "processing").strip().lower()
    if normalized in {"success", "succeeded", "done", "completed"}:
        return "success"
    if normalized in {"fail", "failed", "error"}:
        return "failed"
    return "processing"


def extract_file_id(result: dict) -> str:
    data = result.get("data", {})
    return str(result.get("file_id") or data.get("file_id") or "")


def extract_status(result: dict) -> str:
    data = result.get("data", {})
    return normalize_video_status(result.get("status") or data.get("status"))


def video_extension_from(download_url: str, filename: str = "") -> str:
    candidate = filename or Path(urlparse(download_url).path).name
    suffix = Path(candidate).suffix.lower().lstrip(".")
    return suffix if suffix in {"mp4", "mov", "webm", "m4v"} else "mp4"


async def save_video_from_url(download_url: str, filename: str = "") -> str:
    ext = video_extension_from(download_url, filename)
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    filepath = UPLOAD_DIR / stored_name
    async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
        resp = await client.get(download_url)
        resp.raise_for_status()
    with filepath.open("wb") as f:
        f.write(resp.content)
    return upload_url("videos", stored_name)


@router.post("/generate", response_model=GenerationResponse)
async def generate(
    req: VideoGenerateRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """文生视频 — 按模型路由到对应 profile，返回 task_id（需轮询 /api/video/status）"""
    if req.model == "comfyui-local-video":
        try:
            if not req.comfyui_workflow_id:
                raise ValueError("请选择一个 video 类型的 ComfyUI workflow")
            workflow = runtime_workflow(
                workflow_id=req.comfyui_workflow_id,
                prompt=req.prompt,
                aspect_ratio=req.aspect_ratio,
                width=req.width,
                height=req.height,
                n=1,
                seed=req.seed,
                checkpoint=None,
                expected_category="video",
                duration=req.duration,
                fps=req.fps,
            )
            result = await comfyui_generate_video(prompt=req.prompt, workflow=workflow)
            video_url = result.get("data", {}).get("video_url")
            if not video_url:
                raise ValueError("ComfyUI workflow did not return a video URL")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except TimeoutError:
            logger.exception("ComfyUI video generation timed out")
            raise HTTPException(status_code=504, detail="ComfyUI 视频生成超时，请检查本地队列和工作流")
        except Exception:
            logger.exception("ComfyUI video generation failed")
            raise HTTPException(status_code=502, detail="ComfyUI 视频生成失败，请检查本地服务和工作流")

        gen = Generation(
            type="video",
            prompt=req.prompt,
            video_url=video_url,
            video_model=req.model,
            video_duration=str(req.duration),
            n_generated=1,
            mini_max_id=result.get("id", ""),
        )
        db.add(gen)
        db.commit()
        db.refresh(gen)

        return {
            "id": gen.id,
            "type": "video",
            "task_id": result.get("id", ""),
            "status": "success",
            "prompt": req.prompt,
            "image_urls": [],
            "audio_url": None,
            "video_url": video_url,
            "model": req.model,
            "aspect_ratio": req.aspect_ratio,
            "voice_model": None,
            "voice_id": None,
            "video_model": req.model,
            "video_duration": str(req.duration),
            "n_generated": 1,
            "created_at": gen.created_at,
        }

    profile = get_profile_for_model(req.model)
    if not profile:
        raise HTTPException(
            status_code=400,
            detail=f"No enabled profile found for model '{req.model}'",
        )
    try:
        auth_type = profile.get("auth_type", "http")
        if auth_type == "cli":
            result = await cli_generate_video(
                prompt=req.prompt,
                model=req.model,
                duration=req.duration,
            )
        else:
            result = await http_generate_video(
                prompt=req.prompt,
                model=req.model,
                duration=req.duration,
                resolution=req.resolution,
                first_frame_image=req.first_frame_image,
                last_frame_image=req.last_frame_image,
                subject_reference=[item.model_dump() for item in req.subject_reference or []] or None,
                prompt_optimizer=req.prompt_optimizer,
                fast_pretreatment=req.fast_pretreatment,
                callback_url=req.callback_url,
                api_key=profile["api_key"],
                base_url=profile.get("base_url", "https://api.minimax.io"),
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Video generation failed")
        raise HTTPException(status_code=500, detail="生成失败，请稍后重试")

    base_resp = result.get("base_resp", {})
    if base_resp.get("status_code", 0) != 0:
        raise HTTPException(
            status_code=400,
            detail=f"MiniMax Hailuo API error: {base_resp.get('status_msg', 'unknown')}",
        )

    task_id = result.get("task_id", "")

    gen = Generation(
        type="video",
        prompt=req.prompt,
        video_url="",
        video_model=req.model,
        video_duration=req.duration,
        n_generated=1,
        mini_max_id=task_id,
    )
    db.add(gen)
    db.commit()
    db.refresh(gen)

    return {
        "id": gen.id,
        "type": "video",
        "task_id": task_id,
        "status": "pending",
        "prompt": req.prompt,
        "image_urls": [],
        "audio_url": None,
        "video_url": None,
        "model": req.model,
        "aspect_ratio": None,
        "voice_model": None,
        "voice_id": None,
        "video_model": req.model,
        "video_duration": str(req.duration),
        "n_generated": 1,
        "created_at": gen.created_at,
    }


@router.get("/status/{task_id}")
async def video_status(
    task_id: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """轮询视频生成状态；成功后用 file_id 下载并归档到本地 uploads。"""
    gen = db.query(Generation).filter(Generation.mini_max_id == task_id).first()
    if gen and gen.video_url:
        return {"task_id": task_id, "status": "success", "video_url": gen.video_url}
    if not gen:
        raise HTTPException(status_code=404, detail="Video task not found")

    profile = get_profile_for_model(gen.video_model or "")
    if not profile:
        raise HTTPException(
            status_code=400,
            detail=f"No enabled profile found for model '{gen.video_model}'",
        )
    if profile.get("auth_type", "http") == "cli":
        return {
            "task_id": task_id,
            "status": "processing",
            "video_url": None,
            "note": "CLI video status polling is not available yet",
        }

    try:
        result = await http_query_video_task(
            task_id,
            api_key=profile["api_key"],
            base_url=profile.get("base_url", "https://api.minimax.io"),
        )
    except httpx.HTTPStatusError as e:
        detail = e.response.text or str(e)
        raise HTTPException(status_code=502, detail=f"MiniMax query failed: {detail}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    base_resp = result.get("base_resp", {})
    if base_resp.get("status_code", 0) != 0:
        raise HTTPException(
            status_code=400,
            detail=f"MiniMax API error: {base_resp.get('status_msg', 'unknown')}",
        )

    status = extract_status(result)
    if status == "failed":
        message = result.get("error_message") or result.get("data", {}).get("error_message") or "视频生成失败"
        raise HTTPException(status_code=502, detail=message)

    video_url = ""
    if status == "success":
        file_id = extract_file_id(result)
        if not file_id:
            raise HTTPException(status_code=502, detail="MiniMax task succeeded without file_id")
        file_result = await http_retrieve_video_file(
            file_id,
            api_key=profile["api_key"],
            base_url=profile.get("base_url", "https://api.minimax.io"),
        )
        file_info = file_result.get("file", {})
        download_url = file_info.get("download_url", "")
        if not download_url:
            raise HTTPException(status_code=502, detail="MiniMax file retrieve returned no download_url")
        video_url = await save_video_from_url(download_url, file_info.get("filename", ""))

    if gen and video_url:
        gen.video_url = video_url
        db.commit()

    return {
        "task_id": task_id,
        "status": status,
        "video_url": video_url or None,
    }
