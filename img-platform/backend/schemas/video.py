from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class VideoGenerateRequest(BaseModel):
    prompt: str
    model: str = "MiniMax-Hailuo-2.3"
    duration: str = "6s"
    resolution: str = "720p"
    fps: int = 30
    seed: Optional[int] = None


class VideoResponse(BaseModel):
    id: int
    prompt: str
    video_url: str
    video_model: str
    duration: str
    created_at: datetime

    class Config:
        from_attributes = True
