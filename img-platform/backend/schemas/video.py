from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class VideoGenerateRequest(BaseModel):
    prompt: str
    model: str = "MiniMax-Hailuo-2.3"
    duration: int = 6
    resolution: str = "768P"
    fps: Optional[int] = None
    seed: Optional[int] = None


class VideoResponse(BaseModel):
    id: int
    prompt: str
    task_id: str
    video_url: Optional[str] = None
    video_model: str
    duration: int
    created_at: datetime

    class Config:
        from_attributes = True
