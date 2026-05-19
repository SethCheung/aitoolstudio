from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class CanvasPosition(BaseModel):
    x: float = 0
    y: float = 0


class CanvasNodePayload(BaseModel):
    id: str
    type: str
    position: CanvasPosition = Field(default_factory=CanvasPosition)
    width: Optional[float] = None
    height: Optional[float] = None
    data: dict[str, Any] = Field(default_factory=dict)


class CanvasEdgePayload(BaseModel):
    id: str
    source: str
    target: str
    sourceHandle: Optional[str] = None
    targetHandle: Optional[str] = None
    type: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)


class CanvasDocumentCreate(BaseModel):
    title: str = Field(default="流水线", max_length=160)
    description: Optional[str] = None
    conversation_id: Optional[int] = None


class CanvasDocumentSummary(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    updated_at: datetime

    class Config:
        from_attributes = True


class CanvasGraphSave(BaseModel):
    title: Optional[str] = Field(default=None, max_length=160)
    viewport: dict[str, Any] = Field(default_factory=dict)
    nodes: list[CanvasNodePayload] = Field(default_factory=list)
    edges: list[CanvasEdgePayload] = Field(default_factory=list)


class CanvasGraphResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    conversation_id: Optional[int] = None
    viewport: dict[str, Any] = Field(default_factory=dict)
    nodes: list[CanvasNodePayload] = Field(default_factory=list)
    edges: list[CanvasEdgePayload] = Field(default_factory=list)


class CanvasNodeRunRequest(CanvasGraphSave):
    aspect_ratio: Optional[str] = "1:1"
    quantity: int = Field(default=1, ge=1, le=9)
    seed: Optional[int] = None
    duration: int = Field(default=6, ge=1, le=30)
    fps: Optional[int] = None


class CanvasNodeRunResponse(BaseModel):
    run_id: int
    generation_id: Optional[int] = None
    node_id: str
    status: str
    prompt: str
    urls: list[str] = Field(default_factory=list)
    result_type: str = "image"
    output: dict[str, Any] = Field(default_factory=dict)



class CascadeIterationResult(BaseModel):
    iteration: int
    loop_prompt: str = ""
    llm_run_id: Optional[int] = None
    llm_output: Optional[str] = None
    workflow_run_id: Optional[int] = None
    workflow_urls: list[str] = Field(default_factory=list)
    output_images: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "success"
    error: Optional[str] = None


class CanvasCascadeResponse(BaseModel):
    cascade_id: str
    node_id: str
    iterations: list[CascadeIterationResult] = Field(default_factory=list)
    total_iterations: int = 0
    status: str = "success"
    failed_at_node: Optional[str] = None
    failed_at_iteration: Optional[int] = None


class CanvasMediaNodeCreate(BaseModel):
    asset_url: str
    title: str = "Image Result"
    source: str = "conversation"
    source_generation_id: Optional[int] = None
    position: CanvasPosition = Field(default_factory=CanvasPosition)
