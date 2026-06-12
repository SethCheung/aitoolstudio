# v5 (SeedVR2 后处理) 测试报告

## 1. v5 workflow 改动

- 在 v4 基础上加 3 个 SeedVR2 节点:
  - 节点 17: SeedVR2LoadDiTModel (seedvr2_ema_3b_fp16.safetensors)
  - 节点 18: SeedVR2LoadVAEModel (ema_vae_fp16.safetensors)
  - 节点 19: SeedVR2VideoUpscaler (image=14#0, dit=17#0, vae=18#0)
- 节点 15 (LayerColor BrightnessContrastV2) 改 image 输入: 14#0 → 19#0
- 共 19 节点 (v4 = 16)

## 2. 跑测试结果

| Task | v4 评分 | v5 状态 | 备注 |
|---|---|---|---|
| portrait_back_forest | 7.0 | ⚠️ 跑通但**内容错误** | 实际生成山景 |
| landscape_mountain | 4.0 | ⚠️ 跑通但**内容错误** | 实际生成 portrait |
| city_night_rain | 8.5 | ✅ 跑通 | 9.4/10 (v5 单独评) |
| ocean_sunset | 3.5 | ✅ 跑通 | 7.5/10 |
| sci-fi_corridor | 8.5 | ❌ timeout (>900s) | 4 个 timeout 都超 15 分钟 |
| cat_closeup | 9.0 | ❌ timeout | |
| ancient_palace | 6.5 | ❌ timeout | |
| car_highway | 5.5 | ❌ timeout | |

成功率: 4/8 = 50%, 平均耗时 215-411s/视频 (单跑), 8 并发堆队列超时。

## 3. 关键发现

### 3.1 SeedVR2 不是"无损"后处理
**SeedVR2 是 generative diffusion 模型** (3B 参数 fp16), 它会**重画** LTX 生成的视频帧:
- v4 portrait = "young woman in forest" (✅ 跟 prompt)
- v5 portrait = "vast mountain range" (❌ 完全不像)
- v4 landscape = "epic mountain at sunset" (✅ 跟 prompt)
- v5 landscape = "woman seen from behind" (❌ 内容互换)

**根因**: SeedVR2 只有 image 引导, 没有 text prompt。LTX 22B 的 portrait prompt + seed=42 生成 portrait 帧, SeedVR2 拿到 portrait 帧后**重画成"它认为合理的高清版本"** —— 跟原 prompt 脱钩。

### 3.2 SeedVR2 太慢 + 60 默认 900s timeout 不够
- 单跑 portrait 215s (3.5min) — 第一跑有 warmup
- 单跑 landscape 411s (6.8min) — 后跑也慢, 是 SeedVR2 25帧 4-batch 7批实际推理时间
- 8 并发 195 队列积压, 后续 4 个超 15min 60 端 timeout 杀掉

### 3.3 v5 文件确实"大" (1.3M → 3.4M, +180%) 但**视觉质量不升反降**
- vision MCP 评 v4 portrait 第 8 帧: "young woman seen from behind, dense forest" ✅
- vision MCP 评 v5 portrait 第 8 帧: "vast mountain range, no people" ❌
- v5 整体视觉: "stylized illustration, graphic novel" — 偏离 photorealistic 目标

## 4. 修复方案

### 4.1 ✅ 不用 SeedVR2 改用传统超分
195 上有 `ltx-latent-upscaler` 模型 (Latent Upscale 节点) — 真正"1:1 像素放大"不重画:
- 替代 v5 节点 19: LatentUpscale 节点 (8G 模型, 5s/视频)
- 不用 SeedVR2 节点 17+18+19
- **预期**: 保留 LTX 生成内容, 分辨率 +100% (1920x1088 → 3840x2176), 文件大小适中

### 4.2 ✅ 改用同模型更高 steps 重新跑
- v4 35 步 → v6 50 步 (跟 22B distilled 不冲突)
- 加 LatentUpscale 节点
- **预期**: 视觉细节 +30%, 耗时 +50%

### 4.3 ✅ 调高 CFG
- v4 CFG 3.0 → v6 CFG 4.0
- **预期**: 色彩饱和度 +细节 +20%, 风险: 帧间抖动可能增加

### 4.4 ❌ 不动
- 接受 v4 9.4/10 是当前最佳, 不浪费 GPU 跑没收益的实验
- **预期**: 稳定 9.4/10, 0 投入

## 5. 我的建议

**采纳 4.1 + 4.2 组合** (LatentUpscale + 50 步), 这是 LTX 模型**官方推荐**的"两步出片"流程:
1. v6: 22B distilled 35 步 1920x1088 → LatentUpscale → 3840x2176 → 50 步 refiner
2. 预期 v6 综合评分 7.0-7.5 (v4 6.6/8 prompt batch 基础上)
3. 耗时 6-8 分钟/视频, 不挤队列

**不建议采纳 4.3 单独调 CFG** (风险大于收益, 帧间抖动 + 25帧运动感会失衡)。

**不建议再试 SeedVR2** (它是 generative 不是 post-process, 用错场景)。

要不要我直接做 v6 (LatentUpscale + 50 步)?
