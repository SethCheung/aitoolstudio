from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class GenerationResponse(BaseModel):
    id: int
    type: str  # image | voice | video
    prompt: str
    image_urls: list[str]
    audio_url: Optional[str]
    video_url: Optional[str]
    model: str
    aspect_ratio: Optional[str]
    voice_model: Optional[str]
    voice_id: Optional[str]
    video_model: Optional[str]
    video_duration: Optional[str]
    n_generated: int
    created_at: datetime

    class Config:
        from_attributes = True


class GenerationListResponse(BaseModel):
    total: int
    items: list[GenerationResponse]
