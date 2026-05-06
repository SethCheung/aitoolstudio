from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class VideoSubjectReference(BaseModel):
    type: str = "character"
    image: list[str]


class VideoGenerateRequest(BaseModel):
    prompt: str
    model: str = "MiniMax-Hailuo-2.3"
    duration: int = 6
    resolution: str = "768P"
    first_frame_image: Optional[str] = None
    last_frame_image: Optional[str] = None
    subject_reference: Optional[list[VideoSubjectReference]] = None
    prompt_optimizer: bool = True
    fast_pretreatment: bool = False
    callback_url: Optional[str] = None
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
