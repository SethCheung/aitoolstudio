from fastapi import APIRouter, Depends, HTTPException
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from api.auth import get_current_user
from models.user import User
from schemas.prompt import PromptOptimizeRequest, PromptOptimizeResponse
from services.cli_runner import optimize_prompt as cli_optimize_prompt
from services.minimax import optimize_prompt as http_optimize_prompt
from services.profile_manager import get_profile_for_model

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/prompt", tags=["提示词优化"])


def _extract_optimized_prompt(result: dict) -> str:
    choices = result.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        content = "\n".join(part for part in parts if part)
    return str(content).strip().strip('"').strip("'")


@router.post("/optimize", response_model=PromptOptimizeResponse)
async def optimize(
    req: PromptOptimizeRequest,
    _current_user: User = Depends(get_current_user),
):
    """将用户原始描述扩写为更适合生成模型的 prompt。"""
    profile = get_profile_for_model(req.model)
    if not profile:
        raise HTTPException(
            status_code=400,
            detail=f"No enabled profile found for text model '{req.model}'",
        )

    try:
        auth_type = profile.get("auth_type", "http")
        if auth_type == "cli":
            result = await cli_optimize_prompt(
                prompt=req.prompt,
                model=req.model,
                target=req.target,
            )
        else:
            result = await http_optimize_prompt(
                prompt=req.prompt,
                model=req.model,
                target=req.target,
                api_key=profile["api_key"],
                base_url=profile.get("base_url", "https://api.minimax.io"),
            )
    except Exception:
        logger.exception("Prompt optimization failed")
        raise HTTPException(status_code=500, detail="提示词优化失败，请稍后重试")

    optimized = _extract_optimized_prompt(result)
    if not optimized:
        raise HTTPException(status_code=502, detail="文本模型未返回有效提示词")

    return PromptOptimizeResponse(
        original_prompt=req.prompt,
        optimized_prompt=optimized,
        model=req.model,
        target=req.target,
    )
