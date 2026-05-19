import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.auth import get_current_user
from models.canvas import CanvasDocument, CanvasEdge, CanvasNode, CanvasRun
from models.conversation import Conversation, ConversationMessage
from models.database import get_db
from models.generation import Generation
from models.user import User
from schemas.canvas import (
    CanvasDocumentCreate,
    CanvasDocumentSummary,
    CanvasEdgePayload,
    CanvasGraphResponse,
    CanvasGraphSave,
    CanvasMediaNodeCreate,
    CanvasNodePayload,
    CanvasNodeRunRequest,
    CanvasNodeRunResponse,
    CanvasPosition,
)
from services.comfyui import generate_image as comfyui_generate_image
from services.comfyui import generate_video as comfyui_generate_video
from services.comfyui_workflows import runtime_workflow
from services.minimax import chat_text

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/canvas", tags=["流水线画布"])


def _get_document(db: Session, document_id: int, user_id: int) -> CanvasDocument:
    document = (
        db.query(CanvasDocument)
        .filter(CanvasDocument.id == document_id, CanvasDocument.user_id == user_id)
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Canvas document not found")
    return document


def _node_to_payload(node: CanvasNode) -> CanvasNodePayload:
    data = dict(node.data or {})
    data.setdefault("status", node.status)
    if node.error:
        data["error"] = node.error
    if node.output:
        data["output"] = node.output
    return CanvasNodePayload(
        id=node.node_id,
        type=node.type,
        position=CanvasPosition(x=node.position_x, y=node.position_y),
        width=node.width,
        height=node.height,
        data=data,
    )


def _edge_to_payload(edge: CanvasEdge) -> CanvasEdgePayload:
    return CanvasEdgePayload(
        id=edge.edge_id,
        source=edge.source_node_id,
        target=edge.target_node_id,
        sourceHandle=edge.source_handle,
        targetHandle=edge.target_handle,
        type=edge.type,
        data=edge.data or {},
    )


def _graph_response(document: CanvasDocument) -> CanvasGraphResponse:
    return CanvasGraphResponse(
        id=document.id,
        title=document.title,
        description=document.description,
        conversation_id=document.conversation_id,
        viewport=document.viewport or {},
        nodes=[_node_to_payload(node) for node in document.nodes],
        edges=[_edge_to_payload(edge) for edge in document.edges],
    )


def _save_graph(db: Session, document: CanvasDocument, payload: CanvasGraphSave) -> None:
    if payload.title:
        document.title = payload.title
    document.viewport = payload.viewport or {}

    # Preserve backend-written output images before frontend overwrites them
    existing_output_images: dict[str, list[dict]] = {}
    for node in db.query(CanvasNode).filter(
        CanvasNode.document_id == document.id,
        CanvasNode.type == "output",
    ).all():
        existing_data = dict(node.data or {})
        if existing_data.get("images"):
            existing_output_images[node.node_id] = existing_data["images"]

    db.query(CanvasNode).filter(CanvasNode.document_id == document.id).delete()
    db.query(CanvasEdge).filter(CanvasEdge.document_id == document.id).delete()

    for node in payload.nodes:
        data = dict(node.data or {})
        output = data.pop("output", {}) if isinstance(data.get("output"), dict) else {}
        # Merge preserved images for output nodes
        if node.type == "output" and node.id in existing_output_images:
            data["images"] = existing_output_images[node.id]
        db.add(CanvasNode(
            document_id=document.id,
            node_id=node.id,
            type=node.type,
            position_x=node.position.x,
            position_y=node.position.y,
            width=node.width,
            height=node.height,
            data=data,
            status=str(data.get("status") or "idle"),
            error=data.get("error"),
            output=output,
        ))

    for edge in payload.edges:
        db.add(CanvasEdge(
            document_id=document.id,
            edge_id=edge.id,
            source_node_id=edge.source,
            target_node_id=edge.target,
            source_handle=edge.sourceHandle,
            target_handle=edge.targetHandle,
            type=edge.type,
            data=edge.data or {},
        ))


def _safe_number(value: Any, fallback: int) -> int:
    return value if isinstance(value, int) else fallback


def _incoming_pairs(nodes: list[CanvasNodePayload], edges: list[CanvasEdgePayload], target_id: str) -> list[tuple[CanvasEdgePayload, int, CanvasNodePayload]]:
    by_id = {node.id: node for node in nodes}
    pairs = []
    for index, edge in enumerate(edge for edge in edges if edge.target == target_id):
        source = by_id.get(edge.source)
        if source:
            pairs.append((edge, index, source))
    return pairs


def _upstream_prompt(nodes: list[CanvasNodePayload], edges: list[CanvasEdgePayload], target: CanvasNodePayload) -> str:
    text_nodes = [
        (edge, index, node)
        for edge, index, node in _incoming_pairs(nodes, edges, target.id)
        if node.type == "text"
    ]
    text_nodes.sort(key=lambda item: _safe_number(item[0].data.get("promptOrder"), item[1] + 1))
    parts = [str(node.data.get("body") or "").strip() for _, _, node in text_nodes]

    # Also collect from LLM nodes' outputText
    llm_nodes = [
        (edge, index, node)
        for edge, index, node in _incoming_pairs(nodes, edges, target.id)
        if node.type == "llm"
    ]
    llm_nodes.sort(key=lambda item: _safe_number(item[0].data.get("promptOrder"), item[1] + 1))
    for _, _, node in llm_nodes:
        output_text = str(node.data.get("outputText") or "").strip()
        if output_text:
            parts.append(output_text)

    prompt = "\n\n".join(part for part in parts if part).strip()
    return prompt or str(target.data.get("body") or "").strip()


def _upstream_media(nodes: list[CanvasNodePayload], edges: list[CanvasEdgePayload], target: CanvasNodePayload) -> list[str]:
    media_nodes = [
        (edge, index, node)
        for edge, index, node in _incoming_pairs(nodes, edges, target.id)
        if node.type == "media"
    ]
    media_nodes.sort(key=lambda item: _safe_number(item[0].data.get("imageOrder"), item[1] + 1))
    return [
        str(node.data.get("assetUrl") or "").strip()
        for _, _, node in media_nodes
        if str(node.data.get("assetUrl") or "").strip()
    ]


def _write_to_output_nodes(
    db: Session,
    document_id: int,
    nodes: list[CanvasNodePayload],
    edges: list[CanvasEdgePayload],
    source_node_id: str,
    result: dict,
) -> None:
    """Write generation results to all downstream Output nodes."""
    url_list = result.get("urls") or []
    if not url_list:
        return

    # BFS to find all downstream output nodes
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        adjacency.setdefault(edge.source, []).append(edge.target)

    visited: set[str] = set()
    queue = [source_node_id]
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        for neighbor in adjacency.get(current, []):
            if neighbor not in visited:
                queue.append(neighbor)

    output_nodes = [n for n in nodes if n.id in visited and n.type == "output" and n.id != source_node_id]

    for out_node in output_nodes:
        saved = db.query(CanvasNode).filter(
            CanvasNode.document_id == document_id,
            CanvasNode.node_id == out_node.id,
        ).first()
        if not saved:
            continue

        data = dict(saved.data or {})
        images: list[dict] = list(data.get("images") or [])
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        for url in url_list:
            images.append({
                "url": url,
                "run_id": result.get("run_id"),
                "generation_id": result.get("generation_id"),
                "source_node_id": source_node_id,
                "prompt": result.get("prompt", ""),
                "created_at": now,
            })
        data["images"] = images
        data["status"] = "done"
        saved.data = data
        saved.status = "done"
        db.add(saved)


async def _run_llm_node_impl(
    db: Session,
    document: CanvasDocument,
    payload: CanvasNodeRunRequest,
    target: CanvasNodePayload,
    node_id: str,
    current_user: User,
):
    """Run an LLM node: collect upstream, call model, save outputText."""
    from datetime import datetime, timezone
    import json as _json

    # Collect upstream text
    upstream_text = _upstream_prompt(payload.nodes, payload.edges, target)
    # Also collect media URLs for context
    upstream_media = _upstream_media(payload.nodes, payload.edges, target)

    system_prompt = str(target.data.get("systemPrompt") or "You are a helpful assistant.")
    model_name = str(target.data.get("model") or "MiniMax-M2.7")

    # Build user prompt from upstream text + image context
    user_prompt = upstream_text or str(target.data.get("userInput") or "Describe this.")
    if upstream_media:
        user_prompt = f"[Image context: {len(upstream_media)} image(s) provided]\n{user_prompt}"

    if not user_prompt.strip():
        raise HTTPException(status_code=400, detail="LLM 节点缺输入。请连接上游 Text 节点或填写 userInput。")

    run = CanvasRun(
        document_id=document.id,
        node_id=node_id,
        status="running",
        prompt=user_prompt[:500],
        request_payload=payload.model_dump(),
        result_payload={},
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        llm_result = await chat_text(prompt=user_prompt, system_prompt=system_prompt, model=model_name)
        # Extract reply text from MiniMax response
        reply = ""
        if isinstance(llm_result, dict):
            choices = llm_result.get("choices") or []
            if choices:
                reply = choices[0].get("message", {}).get("content", "") or ""
            # fallback
            if not reply:
                reply = llm_result.get("reply", "") or str(llm_result.get("data", "")) or ""
        else:
            reply = str(llm_result)

        if not reply.strip():
            raise ValueError("LLM returned empty response")

        run.status = "success"
        run.result_payload = {"output_text": reply, "model": model_name}

        # Save to DB node
        saved_node = db.query(CanvasNode).filter(
            CanvasNode.document_id == document.id,
            CanvasNode.node_id == node_id,
        ).first()
        if saved_node:
            data = dict(saved_node.data or {})
            data["outputText"] = reply
            data["status"] = "success"
            data["error"] = ""
            saved_node.data = data
            saved_node.status = "success"
            saved_node.error = None

        db.commit()
        db.refresh(run)
        return CanvasNodeRunResponse(
            run_id=run.id,
            generation_id=None,
            node_id=node_id,
            status="success",
            prompt=user_prompt[:200],
            urls=[],
            result_type="text",
            output={"output_text": reply},
        )

    except ValueError as exc:
        message = str(exc)
        status_code = 400
    except Exception as exc:
        logger.exception("LLM node run failed")
        message = f"LLM 调用失败：{exc}"
        status_code = 502

    run.status = "error"
    run.error = message
    saved_node = db.query(CanvasNode).filter(
        CanvasNode.document_id == document.id,
        CanvasNode.node_id == node_id,
    ).first()
    if saved_node:
        data = dict(saved_node.data or {})
        data["status"] = "error"
        data["error"] = message
        saved_node.data = data
        saved_node.status = "error"
        saved_node.error = message
    db.commit()
    raise HTTPException(status_code=status_code, detail=message)


@router.get("/documents/by-conversation/{conversation_id}", response_model=CanvasGraphResponse)
def get_or_create_by_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get or create CanvasDocument for a conversation. Ownership validated."""
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found or access denied")

    document = (
        db.query(CanvasDocument)
        .filter(
            CanvasDocument.conversation_id == conversation_id,
            CanvasDocument.user_id == current_user.id,
        )
        .first()
    )
    if document:
        return _graph_response(document)

    document = CanvasDocument(
        user_id=current_user.id,
        conversation_id=conversation_id,
        title=conv.title or "流水线",
        viewport={},
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return _graph_response(document)


@router.post("/documents/{document_id}/media-nodes", response_model=CanvasGraphResponse)
def create_media_node(
    document_id: int,
    payload: CanvasMediaNodeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a Media node from a conversation result."""
    document = _get_document(db, document_id, current_user.id)

    # Generate ID from the generation source if available
    node_id = f"media-{payload.source_generation_id}" if payload.source_generation_id else f"media-{uuid.uuid4().hex[:8]}"

    # Check if this node already exists (idempotent)
    existing = (
        db.query(CanvasNode)
        .filter(CanvasNode.document_id == document.id, CanvasNode.node_id == node_id)
        .first()
    )
    if existing:
        data = dict(existing.data or {})
        data["assetUrl"] = payload.asset_url
        data["title"] = payload.title
        existing.data = data
    else:
        node = CanvasNode(
            document_id=document.id,
            node_id=node_id,
            type="media",
            position_x=payload.position.x,
            position_y=payload.position.y,
            data={"assetUrl": payload.asset_url, "title": payload.title, "hint": "来自对话生成结果"},
        )
        db.add(node)

    db.commit()
    db.refresh(document)
    return _graph_response(document)


@router.get("/documents", response_model=list[CanvasDocumentSummary])
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(CanvasDocument)
        .filter(CanvasDocument.user_id == current_user.id)
        .order_by(CanvasDocument.updated_at.desc())
        .all()
    )


@router.post("/documents", response_model=CanvasGraphResponse)
def create_document(
    payload: CanvasDocumentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation_id = None
    if payload.conversation_id:
        conv = (
            db.query(Conversation)
            .filter(Conversation.id == payload.conversation_id, Conversation.user_id == current_user.id)
            .first()
        )
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found or access denied")
        conversation_id = conv.id

    document = CanvasDocument(
        user_id=current_user.id,
        conversation_id=conversation_id,
        title=payload.title or "流水线",
        description=payload.description,
        viewport={},
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return _graph_response(document)


@router.get("/documents/{document_id}", response_model=CanvasGraphResponse)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _graph_response(_get_document(db, document_id, current_user.id))


@router.put("/documents/{document_id}/graph", response_model=CanvasGraphResponse)
def save_graph(
    document_id: int,
    payload: CanvasGraphSave,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = _get_document(db, document_id, current_user.id)
    _save_graph(db, document, payload)
    db.commit()
    db.refresh(document)
    return _graph_response(document)


@router.post("/documents/{document_id}/nodes/{node_id}/run", response_model=CanvasNodeRunResponse)
async def run_node(
    document_id: int,
    node_id: str,
    payload: CanvasNodeRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = _get_document(db, document_id, current_user.id)
    _save_graph(db, document, payload)

    target = next((node for node in payload.nodes if node.id == node_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Canvas node not found")
    if target.type not in {"workflow", "video", "llm"}:
        raise HTTPException(status_code=400, detail="Only Workflow, Video, and LLM nodes can run")

    # === LLM node path ===
    if target.type == "llm":
        return await _run_llm_node_impl(db, document, payload, target, node_id, current_user)

    workflow_id = str(target.data.get("workflowId") or "").strip()
    if not workflow_id:
        raise HTTPException(status_code=400, detail="这个节点还没绑定 ComfyUI workflow")

    prompt = _upstream_prompt(payload.nodes, payload.edges, target)
    if not prompt:
        raise HTTPException(status_code=400, detail="缺 prompt。请连接 Text 节点或在节点中填写描述")

    category = str(target.data.get("workflowCategory") or ("video" if target.type == "video" else "image"))
    run = CanvasRun(
        document_id=document.id,
        node_id=node_id,
        status="running",
        prompt=prompt,
        request_payload=payload.model_dump(),
        result_payload={},
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        if category == "video":
            workflow = runtime_workflow(
                workflow_id=workflow_id,
                prompt=prompt,
                aspect_ratio=payload.aspect_ratio or str(target.data.get("aspectRatio") or "16:9"),
                width=None,
                height=None,
                n=1,
                seed=payload.seed,
                checkpoint=None,
                expected_category="video",
                duration=payload.duration,
                fps=payload.fps,
            )
            result = await comfyui_generate_video(prompt=prompt, workflow=workflow)
            urls = result.get("data", {}).get("video_urls") or [result.get("data", {}).get("video_url")]
            urls = [url for url in urls if url]
            generation = Generation(
                type="video",
                prompt=prompt,
                video_url=urls[0] if urls else "",
                video_model="comfyui-local-video",
                video_duration=str(payload.duration),
                n_generated=len(urls) or 1,
                mini_max_id=result.get("id", ""),
                user_id=current_user.id,
                conversation_id=document.conversation_id,
            )
            result_type = "video"
        else:
            media_urls = _upstream_media(payload.nodes, payload.edges, target)
            quantity = payload.quantity or int(target.data.get("quantity") or 1)
            workflow = runtime_workflow(
                workflow_id=workflow_id,
                prompt=prompt,
                aspect_ratio=payload.aspect_ratio or str(target.data.get("aspectRatio") or "1:1"),
                width=None,
                height=None,
                n=quantity,
                seed=payload.seed,
                checkpoint=None,
            )
            result = await comfyui_generate_image(
                prompt=prompt,
                aspect_ratio=payload.aspect_ratio or str(target.data.get("aspectRatio") or "1:1"),
                n=quantity,
                seed=payload.seed,
                workflow=workflow,
                source_image=media_urls[0] if media_urls else None,
                mask_image=media_urls[1] if len(media_urls) > 1 else None,
            )
            urls = result.get("data", {}).get("image_urls") or []
            generation = Generation(
                type="image",
                prompt=prompt,
                image_urls=urls,
                model="comfyui-local",
                aspect_ratio=payload.aspect_ratio,
                n_generated=len(urls),
                mini_max_id=result.get("id", ""),
                user_id=current_user.id,
                conversation_id=document.conversation_id,
            )
            result_type = "image"

        if not urls:
            raise ValueError("ComfyUI workflow did not return output URLs")

        output = {"urls": urls, "result_type": result_type, "comfyui_prompt_id": result.get("id", "")}
        db.add(generation)
        db.flush()

        # If this CanvasDocument belongs to a conversation, create a message
        if document.conversation_id:
            import json as _json
            results_json = _json.dumps(urls)
            msg = ConversationMessage(
                conversation_id=document.conversation_id,
                role="assistant",
                type=result_type,
                content=f"Canvas 节点生成: {prompt[:120]}",
                results=results_json,
                model=workflow_id,
                task_id=f"canvas_run:{run.id}",
            )
            db.add(msg)
            # 同步更新 Conversation.updated_at，确保项目在列表中按最新活跃时间排序
            conv = db.query(Conversation).filter(Conversation.id == document.conversation_id).first()
            if conv:
                conv.updated_at = func.now()

        run.status = "success"
        run.generation_id = generation.id
        run.result_payload = output

        saved_node = (
            db.query(CanvasNode)
            .filter(CanvasNode.document_id == document.id, CanvasNode.node_id == node_id)
            .first()
        )
        if saved_node:
            data = dict(saved_node.data or {})
            data.update({"body": prompt, "status": "success", "error": "", "results": urls})
            saved_node.data = data
            saved_node.status = "success"
            saved_node.error = None
            saved_node.output = output

        # Write results to downstream Output nodes
        _write_to_output_nodes(db, document.id, payload.nodes, payload.edges, node_id, {
            "urls": urls,
            "result_type": result_type,
            "generation_id": generation.id,
            "run_id": run.id,
            "prompt": prompt[:200],
        })

        db.commit()
        db.refresh(run)
        return CanvasNodeRunResponse(
            run_id=run.id,
            generation_id=generation.id,
            node_id=node_id,
            status="success",
            prompt=prompt,
            urls=urls,
            result_type=result_type,
            output=output,
        )
    except ValueError as exc:
        message = str(exc)
        status_code = 400
    except TimeoutError:
        logger.exception("Canvas node run timed out")
        message = "ComfyUI 生成超时，请检查本地队列和 workflow"
        status_code = 504
    except Exception as exc:
        logger.exception("Canvas node run failed")
        message = f"节点运行失败：{exc}"
        status_code = 502

    run.status = "error"
    run.error = message
    saved_node = (
        db.query(CanvasNode)
        .filter(CanvasNode.document_id == document.id, CanvasNode.node_id == node_id)
        .first()
    )
    if saved_node:
        data = dict(saved_node.data or {})
        data.update({"status": "error", "error": message, "results": []})
        saved_node.data = data
        saved_node.status = "error"
        saved_node.error = message
    db.commit()
    raise HTTPException(status_code=status_code, detail=message)
