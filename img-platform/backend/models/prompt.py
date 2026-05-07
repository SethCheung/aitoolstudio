from sqlalchemy import Column, Integer, String, Text, Boolean, JSON, ForeignKey, Index

from .database import BaseModel


class Prompt(BaseModel):
    """提示词库 - 用户收藏/创建的提示词"""
    __tablename__ = "prompts"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(50), nullable=True, index=True)  # image/video/voice/music/text
    tags = Column(JSON, nullable=True, default=list)
    is_favorite = Column(Boolean, default=False, index=True)
    is_public = Column(Boolean, default=False, index=True)
    use_count = Column(Integer, default=0)

    __table_args__ = (
        Index("ix_prompts_user_fav", "user_id", "is_favorite"),
    )
