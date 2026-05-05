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

## v1.1 - 2026-05-05

**同步当前 MVP 实现状态**

### 变更内容
- 补充“当前 MVP 状态”章节，明确已实现和未实现能力
- 首页项目卡片新增生成图片缩略图要求：项目中存在图片结果时展示第一张图片
- Generate 页面新增原图预览要求：点击图片缩略图后在同页打开原图，支持背景点击、关闭按钮和 Esc 关闭
- 明确当前管理入口为前端 `/admin`，后端 `/admin` 不再作为主要入口
- 补充权限加固要求：Admin/Profile 管理接口需要管理员权限，模型列表需要登录
- 补充当前安全限制：`/minimax-output` 静态目录仍需鉴权改造，Profile API Key 不应继续写入 git 跟踪文件
- 补充 MiniMax 当前接入说明：图片/语音/视频/音乐均需按官方 API/CLI 行为验证，视频为异步任务流程

### 影响范围
- `Product-Spec.md`
- `Design-Brief.md`
- `DEV-PLAN.md`
- `README.md`
- `SECURITY.md`

---

## v1.2 - 2026-05-05

**新增显式提示词优化流程**

### 变更内容
- Generate 输入区新增「AI 优化」按钮
- 用户点击后调用文本模型扩写当前输入，不自动触发生图
- 优化结果回填输入框，用户可继续编辑或点击发送
- 后端新增 `/api/prompt/optimize`，通过 Profile 路由选择 HTTP 或 CLI 文本模型
- Admin Profile 增加 text 模型分类，默认支持 `MiniMax-M2.7` 和 `MiniMax-M2.7-highspeed`

### 设计原则
- 不偷偷改用户 prompt
- 不把优化和生图绑成一个不可见流程
- 优化后的 prompt 必须让用户看见并可编辑

---

## 变更日志格式说明

| 字段 | 说明 |
|------|------|
| **版本** | v1.0, v1.1 等 |
| **日期** | YYYY-MM-DD |
| **变更内容** | 简要描述本次变更的核心内容 |
