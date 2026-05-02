from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class VoiceGenerateRequest(BaseModel):
    text: str
    voice_id: str = "male-qn-qingse"
    model: str = "speech-02-hd"
    speed: float = 1.0
    vol: float = 1.0
    pitch: float = 0.0
    emotion: str = "neutral"
    response_format: str = "mp3"


class VoiceResponse(BaseModel):
    id: int
    text: str
    audio_url: str
    voice_model: str
    voice_id: str
    created_at: datetime

    class Config:
        from_attributes = True
