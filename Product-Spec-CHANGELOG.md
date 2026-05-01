# Product Spec 变更记录

## v1.0 - 2026-04-30

**初始版本**

### 变更内容
- 创建内网 AI 生图协作平台 Product Spec
- 明确产品定位：10 人团队内网使用，ComfyUI + MiniMax API 双引擎
- 核心功能：文生图、图生图、inpainting、upscale、ControlNet、LoRA、批量生成、历史记录、提示词保存、API 接口
- MiniMax API 用途：提示词优化 + 图像理解 + image-01 生图
- 用户系统：管理员创建账号，登录后查看所有项目
- 管理员后台：用户管理、工作流配置、API 配额管理（高优先级）；使用统计（中）；系统设置（低）
- 技术栈：Vue 3 + FastAPI + Celery + Docker Compose

### 待确认事项
- RTX 4090 显存为 24GB（非 48GB），需在 Spec 中修正

---

## 变更日志格式说明

| 字段 | 说明 |
|------|------|
| **版本** | v1.0, v1.1 等 |
| **日期** | YYYY-MM-DD |
| **变更内容** | 简要描述本次变更的核心内容 |
