from sqlalchemy import Column, Integer, String, JSON, ForeignKey, Text
from sqlalchemy.orm import relationship

from .database import BaseModel


class Generation(BaseModel):
    """生成记录（图片/语音/视频）"""
    __tablename__ = "generations"

    type = Column(String(10), default="image")  # image | voice | video
    prompt = Column(Text, nullable=False)
    image_urls = Column(JSON, default=list)  # image: list of URLs
    audio_url = Column(String(500), nullable=True)  # voice: audio URL
    video_url = Column(String(500), nullable=True)  # video: video URL
    model = Column(String(50), default="image-01")
    aspect_ratio = Column(String(10), nullable=True)  # image
    voice_model = Column(String(50), nullable=True)  # voice
    voice_id = Column(String(50), nullable=True)  # voice
    video_model = Column(String(50), nullable=True)  # video
    video_duration = Column(String(10), nullable=True)  # video, e.g. "6s"
    n_generated = Column(Integer, nullable=True, default=1)
    mini_max_id = Column(String(100), nullable=True)  # MiniMax task ID
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True, index=True)
