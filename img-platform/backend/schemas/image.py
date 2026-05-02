from pydantic import BaseModel, Field
from typing import Optional


class ImageGenerateRequest(BaseModel):
    """生图请求"""
    prompt: str = Field(..., max_length=1500, description="文本描述，最长1500字符")
    model: str = Field(default="image-01", description="模型：image-01 或 image-01-live")
    aspect_ratio: str = Field(default="16:9", description="宽高比：1:1 / 16:9 / 4:3 / 3:2 / 2:3 / 3:4 / 9:16 / 21:9")
    n: int = Field(default=1, ge=1, le=9, description="生成数量1-9")
    response_format: str = Field(default="url", description="返回格式：url 或 base64")
    prompt_optimizer: bool = Field(default=False, description="是否开启prompt自动优化")


class ImageGenerateResponse(BaseModel):
    """生图响应"""
    id: str
    image_urls: list[str]
    success_count: int
    failed_count: int
