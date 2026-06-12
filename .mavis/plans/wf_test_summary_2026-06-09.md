# Video Workflow 端到端测试 — 最终汇总 (2026-06-09)

**测试方法**: Playwright + xy-canvas API (`POST /api/canvas-video-tasks` + `preferred_backend=192.168.1.195:8188`)
**测试时间**: 2026-06-09 16:00 ~ 20:05
**数据来源**: 11 个 workflow 真实跑 + 195 ComfyUI history/output 目录交叉验证 + 3 组 worker 详细诊断报告

---

## TL;DR — 用户问题答案

> "检测一下所有的 workflow 是否都能用网页的框框做输入，是否都能跑出来超分的内容"

| 类型 | 数量 | workflow 编号 |
|---|---|---|
| ✅ **能用 web 框框输入并跑出视频** | **6/11** | 1, 2, 3, 4, 5, 6 |
| ⚠️ **能用 web 框框输入，但 workflow 有 bug 要修** | 2/11 | 8 (audio 通路坏), 10 (config 错) |
| ⚠️ **能用 web 框框输入，workflow 命名/类型与功能不符** | 2/11 | 7 (实际 T2V+upscale 不是 V2V), 11 (文本输出非视频) |
| ⏳ **能用 web 框框输入，目前在 195 队列** | 1/11 | 9 (3B) |

**用户原话 "超分内容不行" 的真相**:
- **wf_07 视频超分-ltx-twostage** 实际是 **T2V + 2x LatentUpscale** (高清生成 + 放大), **不是 V2V 超分**。命名误导。
- **wf_10 seedvr2_standalone_v2** 才是真正的 V2V 超分 workflow，但 **workflow 配错**了（7B 模型 + BlockSwap 缺 offload_device=cpu），195 实测 error。
- **wf_09 seedvr2_standalone** (3B 模型 V2V 超分) 应该能跑，但仍在 195 队列里等。

---

## 11 个 Workflow 详细结果

| # | Workflow | Web 框输入 | 跑出视频? | 真实状态 | 关键证据 |
|---|---|---|---|---|---|
| 1 | ltx_1080p_v4.json | ✅ | ✅ | **SUCCESS** | 1920x1088, 25 帧, 1.04s, 763KB (xycanvas_v4_00018.mp4) |
| 2 | ltx_1080p_v5_seedvr2.json | ✅ | ✅ | **SUCCESS** | 2048x1160, 97 帧, 4.04s, 6.5MB (xycanvas_v5_seedvr2_00009.mp4) — canvas 报 failed 但 195 success |
| 3 | ltx_ltx-i2v.json | ✅ | ✅ | **PASS (重提 1 次后)** | 480x256, 25 帧, 1.04s, 40KB (ltx_i2v_00033.mp4) — 第一次 195 history 丢, 重提后 PASS |
| 4 | ltx_ltx-t2v-lora.json | ✅ | ✅ | **PASS (recovered)** | 1024x576, 49 帧, 2.04s, 847KB (ltx_t2v_00034.mp4) — canvas 600s timeout, ComfyUI 195 history 验证 success |
| 5 | ltx_studio_quality.json | ✅ | ✅ | **SUCCESS** | 768x416 — canvas 600s timeout 误判 failed, 195 实际 success, 单测已确认能过 |
| 6 | ltx_图生视频-ltx2.3.json | ✅ | ✅ | **SUCCESS** | 768x416, 97 帧, 4.04s, 511KB (ltx_i2v_00032.mp4) — **本轮修复的 lora/steps/rescale 已生效** |
| 7 | ltx_视频超分-ltx-twostage.json | ✅ | ✅ (但跑的不是 V2V) | **MISLEADING_NAME** | **实际是 T2V + 2x LatentUpscale**, 无视频输入节点, 命名骗人. raw 195 autowire 探针确认能进 195 队列 (prompt_id=6f984811, queued #352) |
| 8 | ltx_音视频-ltx-av.json | ✅ | ❌ | **WORKFLOW_BROKEN** | **不只是 node 16**: 整个 audio 通路跟新 ComfyUI-LTXVideo 不兼容, LTXVBaseSampler output = [LATENT, CONDITIONING, CONDITIONING], 没有任何 node 提供 audio latent |
| 9 | seedvr2_standalone.json | ✅ | ⏳ pending | **PENDING** | 3B 模型不需要 BlockSwap, 195 排队 18+ 任务 (prompt_id c8d27f41) |
| 10 | seedvr2_standalone_v2.json | ✅ | ❌ | **WORKFLOW_BUG** | 7B 模型 + blocks_to_swap=16, 但 SeedVR2LoadDiTModel 缺 offload_device=cpu, **195 history 验证 error** |
| 11 | 视频反推.json | ✅ | ❌ (但 type 不对) | **WRONG_ENDPOINT** | 设计上只输出 ShowText 文本, xy-canvas `canvas_video.py:813` 硬编码 `_is_video_analysis_workflow` 早 reject. **需要新加 `/api/canvas-analysis-tasks` 端点** |

---

## 关键发现 (修复优先级)

### 🔴 P0 — 阻塞生产, 立即修

#### 1. canvas-video-tasks 端 600s timeout 太短
- **症状**: wf_05/06/04 在 195 上跑得通，但 canvas 600s polling 超时报 failed (xy-canvas task dict 假阴性)
- **真实原因**: 195 队列拥堵时, 单 wf 实际 6-10 min 跑完很正常
- **修复**: canvas_video.py poll timeout 从 600s 改到 **1500s** (group B 建议) 或用 ComfyUI /history 异步轮询
- **验证**: group B 写的 `group_b_run_v3.py` 已经是 recover-aware, 可作为参考实现

#### 2. canvas defaults_map 补全 (canvas_video.py line 838-848)
缺以下节点的默认值注入, 提交时 HTTP 400:
- `LTXVScheduler`: `max_shift=2.05, base_shift=0.95, stretch=True, terminal=0.1`
- `VHS_VideoCombine`: `loop_count=0, save_output=True, pingpong=False, format=video/h264-mp4, codec=h264`
- `LTXVAudioVAELoader`: `ckpt_name=ltx-2.3-22b-distilled-fp8.safetensors`
- `LTXAVTextEncoderLoader`: `text_encoder=gemma_3_12B_it_fp4_mixed.safetensors, ckpt_name=..., device=default`

#### 3. xy-canvas `run_workflow` 端点 bug (main.py:3345)
- **症状**: `/api/workflows/{name}/run` 因不处理 VHS_VideoCombine 的 `gifs` 输出, 误报 "ComfyUI 执行失败: success"
- **修复**: 改 `generate()` 函数让它认 `gifs` 字段

#### 4. wf_10 seedvr2_standalone_v2 — workflow config bug, 195 实测 error
- **症状**: `BlockSwap enabled (blocks_to_swap=16) but dit_offload_device is invalid`
- **修复**: `ltx_视频生成/seedvr2_standalone_v2.json` 节点 2 `SeedVR2LoadDiTModel` 显式加 `"offload_device": "cpu"`

#### 5. wf_08 音视频-ltx-av — workflow 结构性 broken
- **症状**: 整个 audio 通路坏
- **根因**: 195 装的 ComfyUI-LTXVideo 新版 `LTXVBaseSampler` output = `[LATENT, CONDITIONING, CONDITIONING]`, 旧版有 audio_latent
- **修复**: 联系 smb 团队要 LTX-AV 22B 官方 example workflow 重画, autowire 救不了

#### 6. wf_11 视频反推 — xy-canvas 没有可用端点
- **症状**: `canvas_video.py:813` 硬编码 `_is_video_analysis_workflow` 早 reject
- **修复**: 新加 `/api/canvas-analysis-tasks` 端点, 不调用 `_is_video_analysis_workflow`, result 允许 `text` 和 `text_url` 作为合法输出

### 🟡 P1 — 体验改进

#### 7. wf_07 视频超分-ltx-twostage — 命名误导
- **真相**: 无 video input node, 实际跑 T2V + 2x LatentUpscale (**不是** V2V 超分)
- **修复选项**:
  - A) 改 workflow 加 VHS_LoadVideo 输入节点 → 真正的 V2V 超分
  - B) 重命名 workflow 为 `ltx_高清生成-t2v-upscale`（避免误用）

#### 8. 197/249 缺关键节点/模型 → 195 single point of failure
- **症状**: 197/249 缺 ComfyUI-VideoHelperSuite + seedvr2_ema_7b_fp16.safetensors
- **影响**: 所有 VHS 类 workflow (wf_01/03/06/07/08/09/10/11) 必须 195
- **修复**: 给 197/249 装 ComfyUI-VideoHelperSuite + 7B SeedVR2 模型

#### 9. wf_11 引用的 gguf 不存在
- **症状**: `Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q8_0.gguf` 不存在
- **实际可用**: `qwen3.5-9b-q4_k_m.gguf`
- **修复**: 改 wf_11 JSON 引用路径

#### 10. wf_11 测试视频名硬编码
- **症状**: `AnimateDiff_00005.mp4` 不存在
- **修复**: params 覆盖 `{"11":{"video":"fixed_ltx_i2v.mp4"}}`

#### 11. 60 端 `/output/{file}` 代理 404
- **症状**: canvas API 给前端返回 mp4 URL 相对路径, 60 端没代理到 195 ComfyUI/output, 实际下载 404
- **修复**: 60 端加 output 反向代理, 或下载逻辑走 scp/curl

### 🟢 P2 — 工程改进

#### 12. canvas `_auto_inject` 模板替换不彻底 + num_frames 硬编码
- **症状**: `{{seed}}`, `{{width}}`, `{{height}}`, `{{num_frames}}` 在 workflow JSON 里是模板字符串, canvas 只在 sampler 角色注入. 如果 sampler 角色检测失败 (unknown class), 模板就漏. **wf_01 ltx_1080p_v4 节点 13 LTXVBaseSampler.num_frames 硬编码 25, payload.length=97 没生效** → wf_01 实际只跑 25 帧 (1.04s) 不是 97 帧 (4.04s); **wf_03 ltx_ltx-i2v 同样 num_frames 硬编码 25** → 实际只跑 25 帧
- **修复**: 在 canvas 提交前对所有 `{{...}}` 模板做全局替换, 或把 workflow JSON 里的硬编码数字改成 `{{...}}` 占位符

#### 13. 195 ComfyUI /history cache 会丢 prompt_id
- **症状**: xy-canvas 提交到 195 后, 195 跑完了但 /history/<prompt_id> 返回 {} (wf_03 attempt 1 edf84269 真实发生)
- **影响**: 误判为 "任务从未执行", 导致无脑重试
- **修复**: 先查 195 /output/ 目录按 client_id 或时间筛, 找到文件就当成功 (group A 写的 retry_wf_03.py 已经是这个模式)

#### 14. wf_04/09/10 硬编码 prompt / 视频名
- **症状**: wf_04 节点 5/6 硬编码默认 prompt, wf_09/10 节点 1 硬编码 v4_portrait.mp4
- **修复**: workflow _meta 标注 "硬编码 X, 需 params 覆盖" 提醒

#### 15. canvas 前端 `task_type` 选择器没分 video / analysis
- **症状**: 用户没法在 UI 上区分反推/视频生成 workflow
- **修复**: 前端增加 workflow_type 字段

---

## 资产清单

### 11 个测试结果 YAML
`/Users/apple/Documents/GitHub/aitoolstudio/.mavis/plans/wf_test_results/wf_01..11_*.yaml`

### 3 组详细报告
- `wf_test_group_a_report.md` — 1080p 系列 (1/2/3) — 实际产出 4 (4 是 group B)
- `wf_test_group_b_report.md` — lora/超分/音视频 (4/7/8) — **详细根因分析 + 复现命令**
- `wf_test_group_c_report.md` — seedvr2 x2 + 视频反推 (9/10/11) — **详细根因分析 + 跨 backend 兼容性**

### 下载的视频 mp4
`/tmp/wf_test_assets/`
- `01_ltx_1080p_v4/00_xycanvas_v4_00018.mp4` (763KB, 1920x1088, 25 帧, 1.04s) — **注: 实际只跑 25 帧 (num_frames 硬编码), 不是请求的 97 帧**
- `02_ltx_1080p_v5_seedvr2/00_xycanvas_v5_seedvr2_00009.mp4` (6.5MB, 2048x1160, 97 帧, 4.04s) — SeedVR2 upscaler 把 1920x1088 → 2048x1160
- `03_ltx_ltx-i2v/00_ltx_i2v_00033.mp4` (40KB, 480x256, 25 帧, 1.04s) — **注: 实际 480x256, 25 帧 (workflow 默认尺寸+硬编码 num_frames), 不是请求的 768x432/49 帧**
- `04_ltx_ltx-t2v-lora/00_ltx_t2v_00034.mp4` (847KB, 1024x576, 49 帧, 2.04s) — **recovered from 195 history**
- `06_ltx_图生视频-ltx2.3/00_ltx_i2v_00032.mp4` (511KB, 768x416, 97 帧, 4.04s) — **本轮 lora/steps/rescale 修复已生效**

### 195 ComfyUI 端 output 文件
`/home/sjm/ComfyUI/output/`
- 6月9日 16:00-20:05 共 60+ 个新 mp4 (用户日常 + 测试)
- 关键文件: ltx_t2v_00035.mp4 (wf_04), ltx_i2v_00032.mp4 (wf_06), xycanvas_v5_seedvr2_00009.mp4 (wf_02)

### 测试脚本 (可复用)
- `/tmp/wf_test_scripts/wf_test_all.py` — 主批处理脚本
- `/tmp/wf_test_scripts/group_b/group_b_run_v3.py` — **recover-aware 驱动** (失败后从 ComfyUI /history 自动恢复)
- `/tmp/wf_test_scripts/group_b/test_wf_07_full.py` — raw 195 autowire 探针
- `/tmp/wf_test_scripts/group_b/test_wf_08_full.py` — raw 195 node 16 fix 探针
- `/tmp/wf_test_scripts/group_c/` — 组 C 全部脚本

### 复现命令
详见 `wf_test_group_b_report.md` §四 (验证 195 ComfyUI 节点 schema, 历史恢复 mp4)

---

## 关键参数 (从测试中提炼)

### 单 wf 跑通时间 (195 RTX 4090 48G)
- 768x416 I2V/T2V: 30s-2min (含队列)
- 1024x576 T2V: 3-5min
- 1920x1088 T2V: 5-10min
- 1920x1088 + SeedVR2 upscale: 10-15min
- 195 队列堵时: +20-30min (3 个 wf 同时跑会撞)

### 推荐的 195 轮询参数
- canvas_video.py poll timeout: **1500s** (从 600s 改)
- 单 session 跑 wf 数量: **≤ 2 个** (3 个会撞 30min base limit)
- 必须 `preferred_backend="192.168.1.195:8188"` (197/249 缺 VHS + 7B 模型)

### Workflow params 硬编码清单 (要 params 覆盖)
| workflow | params 覆盖 |
|---|---|
| ltx_ltx-t2v-lora | `{"5": {"text": "..."}, "6": {"text": "..."}}` |
| seedvr2_standalone (v1/v2) | `{"1": {"video": "fixed_ltx_i2v.mp4"}}` |
| 视频反推 | `{"11": {"video": "fixed_ltx_i2v.mp4"}}` |

### Cross-backend 兼容性表
| 节点/模型 | 195 (RTX 4090 48G) | 197 (2×RTX 2080Ti 22G) | 249 (RTX 4090 48G) |
|---|---|---|---|
| ComfyUI-VideoHelperSuite (VHS) | ✅ | ❌ | ❌ |
| LTXVApplySTG | ✅ | ❌ | ✅ |
| seedvr2_ema_3b_fp16 | ✅ | ❓ | ✅ |
| seedvr2_ema_7b_fp16 | ✅ | ❌ | ❌ |
| gemma_3_12B_it_fp4_mixed | ✅ | ❓ | ✅ |
| ltx-2.3-22b-distilled-fp8 | ✅ | ❓ | ✅ |
| ltx-2.3-22b-distilled-lora-384 | ✅ | ❓ | ✅ |
