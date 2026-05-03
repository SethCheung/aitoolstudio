from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class VoiceGenerateRequest(BaseModel):
    text: str
    voice_id: str = "male-qn-qingse"
    model: str = "speech-2.8-hd"
    speed: int = 1
    vol: int = 1
    pitch: int = 0
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
