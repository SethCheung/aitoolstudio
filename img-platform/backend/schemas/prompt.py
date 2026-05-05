from pydantic import BaseModel, Field


class PromptOptimizeRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=1500, description="用户原始描述")
    model: str = Field(default="MiniMax-M2.7", description="用于优化 prompt 的文本模型")
    target: str = Field(default="image", description="目标生成类型，如 image / video")


class PromptOptimizeResponse(BaseModel):
    original_prompt: str
    optimized_prompt: str
    model: str
    target: str
