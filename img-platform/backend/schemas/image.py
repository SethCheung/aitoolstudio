from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional


class ImageStyle(BaseModel):
    """image-01-live 画风设置"""
    style_type: str = Field(..., description="画风类型，如 漫画 / 元气 / 中世纪 / 水彩")
    style_weight: float = Field(default=0.8, ge=0.1, le=1, description="画风权重 0.1-1")


class ImageSubjectReference(BaseModel):
    """图生图主体参考"""
    type: str = Field(default="character", description="参考类型，目前使用 character")
    image_file: str = Field(..., description="参考图片 URL 或 data URL")

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        if value != "character":
            raise ValueError("subject_reference.type 目前仅支持 character")
        return value


class ImageGenerateRequest(BaseModel):
    """生图请求"""
    prompt: str = Field(..., max_length=1500, description="文本描述，最长1500字符")
    model: str = Field(default="image-01", description="模型：image-01 或 image-01-live")
    aspect_ratio: Optional[str] = Field(default="16:9", description="宽高比：1:1 / 16:9 / 4:3 / 3:2 / 2:3 / 3:4 / 9:16 / 21:9")
    width: Optional[int] = Field(default=None, ge=512, le=2048, description="自定义宽度，必须与 height 同时提供且可被 8 整除")
    height: Optional[int] = Field(default=None, ge=512, le=2048, description="自定义高度，必须与 width 同时提供且可被 8 整除")
    n: int = Field(default=1, ge=1, le=9, description="生成数量1-9")
    response_format: str = Field(default="url", description="返回格式：url 或 base64")
    prompt_optimizer: bool = Field(default=False, description="是否开启prompt自动优化")
    seed: Optional[int] = Field(default=None, description="随机种子，相同参数可复现相似结果")
    aigc_watermark: bool = Field(default=False, description="是否添加 AIGC 水印")
    style: Optional[ImageStyle] = Field(default=None, description="image-01-live 画风设置")
    subject_reference: list[ImageSubjectReference] = Field(default_factory=list, max_length=4, description="参考图片列表")
    comfyui_checkpoint: Optional[str] = Field(default=None, description="ComfyUI checkpoint 文件名，仅 comfyui-local 生效")
    comfyui_workflow_id: Optional[str] = Field(default=None, description="ComfyUI workflow ID，仅 comfyui-local 生效")
    # Scheduling fields (Agent B — used by comfyui_scheduler.select_worker)
    comfyui_job_class: str = Field(default="auto", description="调度优先级：auto / heavy / medium / light")
    comfyui_required_tags: list[str] = Field(default_factory=list, description="调度要求 — worker 必须包含的全部标签")
    comfyui_required_models: list[str] = Field(default_factory=list, description="调度要求 — worker 必须可见的 checkpoint 列表")
    comfyui_required_nodes: list[str] = Field(default_factory=list, description="调度要求 — worker 必须支持的节点类型列表")
    comfyui_estimated_vram_gb: Optional[float] = Field(default=None, description="调度要求 — 预估显存占用 (GB)")
    sam_x: Optional[float] = Field(default=None, ge=0, le=1, description="局部重绘点击点 X，0-1 归一化坐标")
    sam_y: Optional[float] = Field(default=None, ge=0, le=1, description="局部重绘点击点 Y，0-1 归一化坐标")

    @field_validator("aspect_ratio")
    @classmethod
    def validate_aspect_ratio(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        allowed = {"1:1", "16:9", "4:3", "3:2", "2:3", "3:4", "9:16", "21:9"}
        if value not in allowed:
            raise ValueError("aspect_ratio 不支持")
        return value

    @field_validator("response_format")
    @classmethod
    def validate_response_format(cls, value: str) -> str:
        if value not in {"url", "base64"}:
            raise ValueError("response_format 仅支持 url 或 base64")
        return value

    @field_validator("width", "height")
    @classmethod
    def validate_dimension(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value % 8 != 0:
            raise ValueError("自定义尺寸必须可被 8 整除")
        return value

    @model_validator(mode="after")
    def validate_custom_size(self):
        if (self.width is None) != (self.height is None):
            raise ValueError("width 和 height 必须同时提供")
        if self.style is not None and self.model != "image-01-live":
            raise ValueError("style 仅对 image-01-live 生效")
        return self


class ImageGenerateResponse(BaseModel):
    """生图响应"""
    id: str
    image_urls: list[str]
    success_count: int
    failed_count: int


class ImageUpscaleRequest(BaseModel):
    """图片放大请求"""
    source_url: str = Field(..., description="已有图片 URL，支持 /uploads、/minimax-output 或 http(s)")
    scale: float = Field(default=2, ge=1, le=4, description="放大倍数")
    method: str = Field(default="lanczos", description="ComfyUI ImageScale 方法")
    aspect_ratio: Optional[str] = Field(default=None, description="源图展示比例，用于结果预览")

    @field_validator("method")
    @classmethod
    def validate_method(cls, value: str) -> str:
        allowed = {"nearest-exact", "bilinear", "area", "bicubic", "lanczos"}
        if value not in allowed:
            raise ValueError("upscale method 不支持")
        return value
