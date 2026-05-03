from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class MusicGenerateRequest(BaseModel):
    prompt: str
    model: str = "music-2.6"
    lyrics: str = ""


class MusicResponse(BaseModel):
    id: int
    prompt: str
    audio_url: str
    music_model: str
    created_at: datetime

    class Config:
        from_attributes = True