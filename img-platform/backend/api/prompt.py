from fastapi import APIRouter, Depends, HTTPException
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from api.auth import get_current_user
from models.user import User
from schemas.prompt import CanvasAgentRequest, CanvasAgentResponse, PromptOptimizeRequest, PromptOptimizeResponse
from services.cli_runner import chat_text as cli_chat_text
from services.cli_runner import optimize_prompt as cli_optimize_prompt
from services.minimax import chat_text as http_chat_text
from services.minimax import chat_text_openai_compatible
from services.minimax import optimize_prompt as http_optimize_prompt
from services.minimax import optimize_prompt_openai_compatible
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


def _is_openai_compatible(profile: dict) -> bool:
    return str(profile.get("auth_type") or "").lower() in {
        "openai",
        "openai-compatible",
        "local",
        "local-openai",
    }


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
                generation_model=req.generation_model,
            )
        elif _is_openai_compatible(profile):
            result = await optimize_prompt_openai_compatible(
                prompt=req.prompt,
                model=req.model,
                target=req.target,
                generation_model=req.generation_model,
                api_key=profile.get("api_key") or None,
                base_url=profile.get("base_url"),
            )
        else:
            result = await http_optimize_prompt(
                prompt=req.prompt,
                model=req.model,
                target=req.target,
                generation_model=req.generation_model,
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


@router.post("/canvas-agent", response_model=CanvasAgentResponse)
async def canvas_agent(
    req: CanvasAgentRequest,
    _current_user: User = Depends(get_current_user),
):
    """根据流水线画布状态给用户下一步搭建建议。"""
    profile = get_profile_for_model(req.model)
    if not profile:
        raise HTTPException(
            status_code=400,
            detail=f"No enabled profile found for text model '{req.model}'",
        )

    system_prompt = (
        "你是 AI Tool Studio 内网流水线画布助手。只用中文回答。"
        "你的任务是根据用户提供的画布节点、连线和可用 ComfyUI workflow，给出下一步搭建建议。"
        "回答必须短、具体、可执行，不要英文，不要营销话术，不要 Markdown 大标题。"
        "固定输出三段：1. 下一步；2. 推荐节点/工作流；3. 可直接粘贴的 prompt 草稿。"
        "如果信息不足，就指出缺什么，并给一个最小可行操作。"
    )

    try:
        auth_type = profile.get("auth_type", "http")
        if auth_type == "cli":
            result = await cli_chat_text(
                prompt=req.prompt,
                system_prompt=system_prompt,
                model=req.model,
            )
        elif _is_openai_compatible(profile):
            result = await chat_text_openai_compatible(
                prompt=req.prompt,
                system_prompt=system_prompt,
                model=req.model,
                api_key=profile.get("api_key") or None,
                base_url=profile.get("base_url"),
            )
        else:
            result = await http_chat_text(
                prompt=req.prompt,
                system_prompt=system_prompt,
                model=req.model,
                api_key=profile["api_key"],
                base_url=profile.get("base_url", "https://api.minimax.io"),
            )
    except Exception:
        logger.exception("Canvas agent failed")
        raise HTTPException(status_code=500, detail="流水线 Agent 暂时不可用，请稍后重试")

    answer = _extract_optimized_prompt(result)
    if not answer:
        raise HTTPException(status_code=502, detail="文本模型未返回有效建议")
    return CanvasAgentResponse(answer=answer, model=req.model)
