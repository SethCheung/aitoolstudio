from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Literal, Optional


class VoiceGenerateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    voice_id: str = "male-qn-qingse"
    model: str = "speech-2.8-hd"
    speed: float = Field(default=1, ge=0.5, le=2)
    vol: float = Field(default=1, ge=0, le=10)
    pitch: int = Field(default=0, ge=-12, le=12)
    emotion: str = "auto"
    audio_format: Literal["mp3", "wav", "pcm", "flac"] = "mp3"
    response_format: Optional[Literal["mp3", "wav", "pcm", "flac"]] = None
    sample_rate: Literal[8000, 16000, 22050, 24000, 32000, 44100] = 32000
    bitrate: Literal[32000, 64000, 128000, 256000] = 128000
    channel: Literal[1, 2] = 1
    subtitle_enable: bool = False
    stream: bool = False
    latex_read: bool = False
    language_boost: Optional[str] = None
    pronunciation_tones: list[str] = Field(default_factory=list)
    voice_effect_pitch: Optional[int] = Field(default=None, ge=-100, le=100)
    voice_effect_intensity: Optional[int] = Field(default=None, ge=-100, le=100)
    voice_effect_timbre: Optional[int] = Field(default=None, ge=-100, le=100)
    voice_effect: Optional[Literal["spacious_echo", "auditorium_echo", "lofi_telephone", "robotic"]] = None

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("text cannot be blank")
        return text

    @field_validator("pronunciation_tones")
    @classmethod
    def clean_pronunciation_tones(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class VoiceResponse(BaseModel):
    id: int
    text: str
    audio_url: str
    voice_model: str
    voice_id: str
    created_at: datetime

    class Config:
        from_attributes = True
