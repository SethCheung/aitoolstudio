# XY AI 功能检测计划

## 项目信息
- **主服务**: http://192.168.1.60:3000/
- **ComfyUI 后端**:
  - 192.168.1.195:8188 (RTX 4090, 32GB RAM, ComfyUI 0.19.2, 2347 nodes)
  - 192.168.1.197:8188 (RTX 2080 Ti, 32GB RAM, ComfyUI 0.21.1, 2129 nodes)
  - 192.168.1.249:8188 (RTX 4090, 64GB RAM, ComfyUI 0.21.1, 2083 nodes)

## 功能模块
1. ComfyUI应用 (主应用)
2. 图片编辑 (/static/app/klein.html)
3. 3D视角变换 (/static/app/angle.html)
4. CG一键细化 (/static/app/cgstyle.html)
5. 2D风格细化 (/static/app/2dstyle.html)
6. 一键抠图 (/static/app/rmbg.html)
7. 高清修复 (/static/app/gaoqingxiufu.html)
8. 扩图 (/static/app/kuotu.html)
9. 图像反推 (/static/app/promptgen.html)
10. 文字抠图 (/static/app/textmatting.html)
11. 万物移除 (/static/app/yichuwuti.html)
12. 在线生图 (/static/online.html)
13. GPT 对话 (/static/gpt-chat.html)
14. 无限画布 (/static/canvas.html)

## 检测阶段

### Stage 1: 基础设施检测 (并行)
- **Worker A**: 检测主服务可访问性、静态资源加载、API 基础端点
- **Worker B**: 检测三台 ComfyUI 后端连接、系统状态、节点可用性

### Stage 2: 功能模块检测 (并行)
- **Worker C**: 检测 ComfyUI 相关功能模块 (图片编辑、3D视角、CG细化、2D细化、高清修复)
- **Worker D**: 检测 AI 处理功能模块 (抠图、扩图、反推、文字抠图、万物移除)
- **Worker E**: 检测 GPT 对话、在线生图、无限画布

### Stage 3: 集成验收
- 汇总所有检测结果
- 生成检测报告
- 标记问题项和建议

## 关键 API 端点
- /api/config
- /api/comfyui/instances
- /api/workflows
- /api/queue_status
- /api/history
- /api/generate
- /api/online-image
- /api/chat
- /api/chat/stream
- /api/conversations
- /api/ai/upload
- /api/upload
- /api/user/assets
- /api/comfyui/system_stats
- /api/comfyui/object_info
- /api/comfyui/prompt
- /api/comfyui/view
- /api/comfyui/history/
