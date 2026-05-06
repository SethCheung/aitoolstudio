from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Literal, Optional


class MusicGenerateRequest(BaseModel):
    prompt: str = Field(default="", max_length=2000)
    model: str = "music-2.6"
    lyrics: str = Field(default="", max_length=3500)
    is_instrumental: bool = False
    lyrics_optimizer: bool = False
    audio_format: Literal["mp3", "wav", "pcm"] = "mp3"
    output_format: Literal["hex", "url"] = "hex"
    sample_rate: Literal[16000, 24000, 32000, 44100] = 44100
    bitrate: Literal[32000, 64000, 128000, 256000] = 256000
    seed: Optional[int] = Field(default=None, ge=0, le=1000000)
    aigc_watermark: bool = False
    reference_audio_url: Optional[str] = None

    @field_validator("prompt", "lyrics")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("reference_audio_url")
    @classmethod
    def strip_reference_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class MusicResponse(BaseModel):
    id: int
    prompt: str
    audio_url: str
    music_model: str
    created_at: datetime

    class Config:
        from_attributes = True
