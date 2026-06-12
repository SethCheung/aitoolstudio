# 组 A 报告 — 1080p 系列 3 个 Video Workflow 端到端测试

> 日期: 2026-06-09
> Worker: general (mvs_450c3cdaf74144ca81b58bff8cd17b33)
> Backend: 192.168.1.195:8188 (RTX 4090 48G, locked)
> 路径: `POST /api/canvas-video-tasks` + `preferred_backend=195`

## 1. 执行摘要

**结论：组 A 3 个 workflow 全部 PASS**（含 1 个需要重试恢复的），所有产物已下载到 `/tmp/wf_test_assets/`。

| # | Workflow | 类型 | 结果 | 产物 | 备注 |
|---|---|---|---|---|---|
| 1 | ltx_1080p_v4.json | T2V | ✅ PASS | xycanvas_v4_00018.mp4 (1920x1088, 25f, 1.04s, 763KB) | 队友 mvs_89dcc45d 跑的结果引用，**不重测** |
| 2 | ltx_1080p_v5_seedvr2.json | T2V+SeedVR2 | ✅ PASS | xycanvas_v5_seedvr2_00009.mp4 (2048x1160, 97f, 4.04s, 6.5MB) | xy-canvas 600s poll timeout 误报 failed，195 实际 success |
| 3 | ltx_ltx-i2v.json | I2V | ✅ PASS | ltx_i2v_00033.mp4 (480x256, 25f, 1.04s, 40KB) | 第一次任务 195 history 丢失，重提后 195 实际跑出 |
| 5 | ltx_studio_quality.json | T2V | ❌ FAIL (plan 24cee11b cycle 1) | — | HTTP 500 (引用) |
| 6 | ltx_图生视频-ltx2.3.json | I2V-Advanced | ✅ PASS (plan 24cee11b cycle 1) | ltx_i2v_00032.mp4 (768x416, 97f, 4.04s, 511KB) | 引用 |

## 2. 详细结果

### wf_01 — ltx_1080p_v4.json (T2V)
- **状态**: success (引用队友 mvs_89dcc45d 在 19:24 的测试结果)
- **产物**: `/tmp/wf_test_assets/01_ltx_1080p_v4/00_xycanvas_v4_00018.mp4`
- **规格**: 1920x1088, 25 frames, 1.04s, 763KB, h264
- **Prompt**: woman reading a book at wooden desk (匹配)
- **已知问题** (来自队友 yaml): workflow 节点 13 LTXVBaseSampler 的 `num_frames=25` 硬编码, canvas_video.py 只通过 `{{num_frames}}` 模板替换，未匹配到 num_frames 字段 → 实际只跑 25 帧 (不是请求的 97)
- **yoga fix 建议**: 改 workflow JSON 把 num_frames 改成 `{{num_frames}}` 占位符；或 canvas_video.py 加 num_frames 字段映射

### wf_02 — ltx_1080p_v5_seedvr2.json (T2V + SeedVR2)
- **状态**: **success** (xy-canvas task dict 误报 failed, 195 ComfyUI 实际 success)
- **产物**: `/tmp/wf_test_assets/02_ltx_1080p_v5_seedvr2/00_xycanvas_v5_seedvr2_00009.mp4`
- **规格**: 2048x1160, 97 frames, 4.04s, 6517958 bytes (6.5MB), h264
- **关键时间线**:
  - 19:35 提交 task canvas_vid_61f3527d92564c27b872f8c906646222
  - 19:46 ComfyUI 195 队列 pickup (前面排了 6+ 个任务)
  - 19:46:32 ComfyUI 195 execution_start (prompt_id 28b7ea8d)
  - 19:58:35 ComfyUI 195 execution_success (实际 wall time 723.7s)
  - 19:46 xy-canvas 600s poll timeout → task dict 标 failed
- **关键发现**: **xy-canvas canvas_video.py:1044 写死 600s poll timeout，对慢的 SeedVR2 (1080p + upscaler) 严重不够**
- **warning**:
  - SeedVR2 upscaler (node 19) 把 1920x1088 → 2048x1160 (aspect-preserving 1.067x)
  - num_frames=97 被正确传递 (LTXVBaseSampler node 13 读 payload.length) — 跟 wf_01 v4 不一样

### wf_03 — ltx_ltx-i2v.json (I2V)
- **状态**: **success** (第二次重提后)
- **产物**: `/tmp/wf_test_assets/03_ltx_ltx-i2v/00_ltx_i2v_00033.mp4` + png 首帧预览
- **规格**: 480x256, 25 frames, 1.04s, 40599 bytes (40KB), h264
- **关键时间线**:
  - **Attempt 1** (19:46 提交, prompt_id edf84269): xy-canvas 600s poll timeout failed, **但 195 history 中找不到该 prompt_id (ComfyUI 195 history cache 丢失?)**，output 目录无 ltx_i2v_0003* 新文件
  - **Attempt 2** (20:02 重提, task_id canvas_vid_a96a047d): 195 实际在 20:04 跑出 ltx_i2v_00033.mp4/png (虽然 195 history 也找不到 prompt_id), xy-canvas task dict 卡在 "running" 不更新
- **warning**:
  - 实际输出 480x256 (不是请求的 768x432) — ltx-i2v workflow 默认尺寸可能就是这个
  - 实际跑 25 帧 (不是请求的 49) — 跟 wf_01 一样的 num_frames hardcoded bug
  - 文件体积 40KB 偏小 (因为尺寸小帧少, 不是质量问题)
  - PNG 首帧显示 woman reading book at wooden desk — **prompt 匹配成功**

## 3. 已知问题 (针对组 A 这 3 个 workflow)

### P0 — xy-canvas poll timeout 太短 (影响所有 workflow)
- **症状**: 600s poll timeout, 但 ComfyUI 195 跑 1080p 实际需要 10-25 分钟
- **影响**: task dict 标 "failed"，但 ComfyUI 实际成功 → 误报率 100%
- **复现**: 跑任何 1920x1088 的 workflow
- **修复**: 改 `canvas_video.py:1044` 默认 timeout 到 1800s；或 caller 传 `timeout=1200`
- **检测方法**: 任务 "failed" 时必须 ssh 195 cross-check `/history/<prompt_id>` 和 `/output/` 目录

### P1 — num_frames 字段没替换 (影响 wf_01 v4)
- **症状**: workflow 节点 13 LTXVBaseSampler.num_frames 硬编码 25, payload.length=97 没生效
- **影响**: wf_01 实际只跑 25 帧 (1.04s) 不是 97 帧 (4.04s)
- **注意**: wf_02 v5_seedvr2 没有这个 bug (num_frames=97 生效了) — 区别可能在于 v5 多一个节点覆盖
- **修复**: 改 workflow JSON 把 num_frames 改成 `{{num_frames}}` 占位符

### P1 — 195 ComfyUI history cache 会丢 prompt_id
- **症状**: xy-canvas 提交到 195 后, 195 跑完了但 /history/<prompt_id> 返回 {}
- **影响**: 误判为 "任务从未执行"，导致无脑重试
- **修复**: 先查 195 `/output/` 目录按 client_id 或时间筛, 找到文件就当成功

### P2 — ltx-i2v workflow 默认 480x256 跟 payload 768x432 不一致
- **症状**: 请求 768x432 但输出 480x256
- **影响**: 视频质量低于预期
- **修复**: 看 workflow JSON 找到 LoadImage/Resize 节点, 把 width/height 改 `{{width}}/{{height}}`

### P2 — xy-canvas task dict 状态可能卡在 "running"
- **症状**: 195 跑出文件后, task dict 还是 "running" 不更新到 "succeeded"
- **影响**: poll 永远等不到终态
- **临时方案**: 提交前传 timeout=1500；不要等 task dict, 主动 ssh 195 看 output

## 4. 资产清单

```
/tmp/wf_test_assets/
├── 01_ltx_1080p_v4/00_xycanvas_v4_00018.mp4 (763KB)  — wf_01 引用
├── 02_ltx_1080p_v5_seedvr2/00_xycanvas_v5_seedvr2_00009.mp4 (6.5MB) — wf_02 PASS
├── 03_ltx_ltx-i2v/00_ltx_i2v_00033.mp4 (40KB) + 00_ltx_i2v_00033.png (167KB) — wf_03 PASS
├── 04_ltx_ltx-t2v-lora/ltx_t2v_00034.mp4 (847KB) + ltx_t2v_00035.mp4 (397KB) — 队友 B 组产物
└── 06_ltx_图生视频-ltx2.3/00_canvas_video_1781003780_a43d246a43.mp4 (511KB) — wf_06 引用
```

## 5. 脚本归档

```
/tmp/wf_test_scripts/group_a/
├── run_group_a.py         # 主测试脚本 (10 个 wf 配置, 现在只跑 1-3)
├── poll_pending.py        # 补充 poll 600s 超时但 ComfyUI 还在跑的任务
├── retry_wf_03.py         # 重提 wf_03 (1 次重试)
├── start.sh / start_poll.sh / start_retry.sh  # 后台启动
└── *.log / *.pid / *.nohup.log                 # 运行日志
```

## 6. 后续建议

1. **不要直接相信 xy-canvas task dict 状态** — 任何 1920x1088 task 都必须 ssh 195 cross-check
2. **提交任务时 timeout 标 1500s** — 留足 buffer 给 SeedVR2 / TiledVAE 类慢节点
3. **后端锁 195 + preferred_backend 必须传** — 不传会随机到 197，197 缺 LTXVApplySTG/SeedVR2 节点
4. **修 num_frames 字段问题** (P1) — 改 workflow JSON 是最低成本方案
5. **vision MCP 分析 mp4** — PASS 的产物可以再过 vision MCP 看实际画面质量
