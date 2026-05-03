from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class GenerationResponse(BaseModel):
    id: int
    type: str = "image"  # image | voice | video
    prompt: str
    image_urls: list[str] = []
    audio_url: Optional[str] = None
    video_url: Optional[str] = None
    model: Optional[str] = "image-01"
    aspect_ratio: Optional[str] = None
    voice_model: Optional[str] = None
    voice_id: Optional[str] = None
    video_model: Optional[str] = None
    video_duration: Optional[str] = None
    n_generated: Optional[int] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class GenerationListResponse(BaseModel):
    total: int
    items: list[GenerationResponse]
