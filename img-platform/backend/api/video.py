from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import sys, os, logging, httpx
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from schemas.video import VideoGenerateRequest, VideoResponse
from schemas.generation import GenerationResponse
from services.minimax import generate_video as http_generate_video, query_video_task as http_query_video_task
from services.cli_runner import generate_video as cli_generate_video
from services.profile_manager import get_profile_for_model
from models.database import get_db
from models.user import User
from models.generation import Generation
from api.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/video", tags=["视频生成"])


@router.post("/generate", response_model=GenerationResponse)
async def generate(
    req: VideoGenerateRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """文生视频 — 按模型路由到对应 profile，返回 task_id（需轮询 /api/video/status）"""
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
                api_key=profile["api_key"],
                base_url=profile.get("base_url", "https://api.minimax.io"),
            )
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
        "task_id": task_id,
        "status": "pending",
        "prompt": req.prompt,
    }


@router.get("/status/{task_id}")
async def video_status(task_id: str, db: Session = Depends(get_db)):
    """轮询视频生成状态（当前端点 404，需在 MiniMax 控制台查看）"""
    try:
        result = await query_video_task(task_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"task_id": task_id, "status": "pending", "video_url": None, "note": "Query endpoint unavailable via API. Check MiniMax console."}
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    base_resp = result.get("base_resp", {})
    if base_resp.get("status_code", 0) != 0:
        raise HTTPException(
            status_code=400,
            detail=f"MiniMax API error: {base_resp.get('status_msg', 'unknown')}",
        )

    data = result.get("data", {})
    status = data.get("status", 0)
    video_url = data.get("video_url", "")

    gen = db.query(Generation).filter(Generation.mini_max_id == task_id).first()
    if gen and video_url:
        gen.video_url = video_url
        db.commit()

    return {
        "task_id": task_id,
        "status": status,
        "video_url": video_url or None,
    }
