from sqlalchemy import Column, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from .database import BaseModel
from .conversation import Conversation


class CanvasDocument(BaseModel):
    __tablename__ = "canvas_documents"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True, index=True)
    title = Column(String(160), nullable=False, default="流水线")
    description = Column(Text, nullable=True)
    viewport = Column(JSON, nullable=False, default=dict)

    user = relationship("User")
    conversation = relationship("Conversation")
    nodes = relationship("CanvasNode", cascade="all, delete-orphan", back_populates="document")
    edges = relationship("CanvasEdge", cascade="all, delete-orphan", back_populates="document")
    runs = relationship("CanvasRun", cascade="all, delete-orphan", back_populates="document")


class CanvasNode(BaseModel):
    __tablename__ = "canvas_nodes"

    document_id = Column(Integer, ForeignKey("canvas_documents.id"), nullable=False, index=True)
    node_id = Column(String(120), nullable=False, index=True)
    type = Column(String(40), nullable=False)
    position_x = Column(Float, nullable=False, default=0)
    position_y = Column(Float, nullable=False, default=0)
    width = Column(Float, nullable=True)
    height = Column(Float, nullable=True)
    data = Column(JSON, nullable=False, default=dict)
    status = Column(String(40), nullable=False, default="idle")
    error = Column(Text, nullable=True)
    output = Column(JSON, nullable=False, default=dict)

    document = relationship("CanvasDocument", back_populates="nodes")


class CanvasEdge(BaseModel):
    __tablename__ = "canvas_edges"

    document_id = Column(Integer, ForeignKey("canvas_documents.id"), nullable=False, index=True)
    edge_id = Column(String(180), nullable=False, index=True)
    source_node_id = Column(String(120), nullable=False, index=True)
    target_node_id = Column(String(120), nullable=False, index=True)
    source_handle = Column(String(80), nullable=True)
    target_handle = Column(String(80), nullable=True)
    type = Column(String(40), nullable=True)
    data = Column(JSON, nullable=False, default=dict)

    document = relationship("CanvasDocument", back_populates="edges")


class CanvasRun(BaseModel):
    __tablename__ = "canvas_runs"

    document_id = Column(Integer, ForeignKey("canvas_documents.id"), nullable=False, index=True)
    node_id = Column(String(120), nullable=False, index=True)
    status = Column(String(40), nullable=False, default="pending")
    prompt = Column(Text, nullable=True)
    request_payload = Column(JSON, nullable=False, default=dict)
    result_payload = Column(JSON, nullable=False, default=dict)
    error = Column(Text, nullable=True)
    generation_id = Column(Integer, ForeignKey("generations.id"), nullable=True)
    # ── 可观测性字段 ──
    worker_id = Column(String(80), nullable=True, index=True)
    run_type = Column(String(40), nullable=True, index=True)
    entrypoint = Column(String(200), nullable=True)
    error_source = Column(String(40), nullable=True)

    document = relationship("CanvasDocument", back_populates="runs")
    generation = relationship("Generation")
