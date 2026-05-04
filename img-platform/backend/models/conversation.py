from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime, func
from sqlalchemy.orm import relationship

from .database import BaseModel


class Conversation(BaseModel):
    """对话记录（包含用户输入 + AI 回复的完整消息历史）"""
    __tablename__ = "conversations"

    title = Column(String(200), default="New Conversation")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    messages = relationship("ConversationMessage", back_populates="conversation", cascade="all, delete-orphan", order_by="ConversationMessage.created_at")


class ConversationMessage(BaseModel):
    """对话中的单条消息"""
    __tablename__ = "conversation_messages"

    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    conversation = relationship("Conversation", back_populates="messages")

    role = Column(String(10), nullable=False)  # 'user' | 'assistant' | 'error'
    type = Column(String(20), default="text")  # 'text' | 'image' | 'voice' | 'video' | 'music'
    content = Column(Text, nullable=False)  # 用户输入的文字 / 错误信息
    results = Column(String(500), nullable=True)  # JSON string of result URLs (image_urls, audio_url, etc.)
    model = Column(String(50), nullable=True)  # 使用的模型
    task_id = Column(String(100), nullable=True)  # 视频生成的任务 ID（轮询用）