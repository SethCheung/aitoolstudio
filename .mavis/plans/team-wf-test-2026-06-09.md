# 11 个 Video Workflow 端到端测试 — Team 任务

> 日期: 2026-06-09
> 主 agent: Mavis (mvs_11691dee977444eb808dfc2f3d927aea)
> 目标: 用 web UI 框框做输入，逐个跑通 11 个 video workflow，记录每个的：成功/失败/质量/原因
> 部署前提: `ltx_图生视频-ltx2.3.json` 已修复 (2026-06-09)

## 11 个 Video Workflow 清单

| # | 文件 | 类型 | 关键节点 | 期望输入 |
|---|---|---|---|---|
| 1 | ltx_1080p_v4.json | T2V | LTXVBaseSampler | prompt + 8 字段 |
| 2 | ltx_1080p_v5_seedvr2.json | T2V + SeedVR2 | LTXVBaseSampler + SeedVR2 | prompt |
| 3 | ltx_ltx-i2v.json | I2V (LTXVImgToVideo) | LoadImage + ImgToVideo | prompt + 图片 |
| 4 | ltx_ltx-t2v-lora.json | T2V + LoRA | LTXVBaseSampler + LoraLoader | prompt |
| 5 | ltx_studio_quality.json | T2V | LTXVBaseSampler | prompt |
| 6 | ltx_图生视频-ltx2.3.json | I2V Advanced | LTXVImgToVideoAdvanced | prompt + 图片 (已修复) |
| 7 | ltx_视频超分-ltx-twostage.json | V2V 超分 | 双 stage + upscale | prompt + 视频 |
| 8 | ltx_音视频-ltx-av.json | T2AV | LTXAVTextEncoder + LTXVAudioVAE | prompt |
| 9 | seedvr2_standalone.json | V2V 超分 | SeedVR2 standalone | 视频 |
| 10 | seedvr2_standalone_v2.json | V2V 超分 v2 | SeedVR2 standalone v2 | 视频 |
| 11 | 视频反推.json | 视频反推 (非生成) | 视频→文字 | 视频 |

## 测试方法

用 Playwright headless Chromium (跟 Mavis 之前的 re_play.py 同款)：
1. 登录 http://192.168.1.60:3000 (sethchang/12301230)
2. 进画布 + 开 video 节点
3. 选 ComfyUI 模式 → 选目标 workflow
4. 填对应输入（prompt / 图片 / 视频）
5. 点 "生成视频"
6. 等完成 (最长 10 分钟) → 记录结果

## 测试用的资产

- 已有测试图片: `PHOTO_20260603_172636427.jpg` (在 ComfyUI input 目录)
- 已有测试视频: `ltx_i2v_00031.mp4` (用刚才跑的 4 秒视频)
- 测试 prompt: `A calm cinematic shot of a woman reading a book at a wooden desk, soft window light, subtle camera movement, natural motion`
- 负向: `blurry, low quality, distorted, watermark`

## 已有工具脚本可复用

- `/tmp/v6_check_re/re_play.py` — 完整 web UI 验证 (登录/进画布/视频节点/字段检查)
- `/tmp/v6_check_re/test_output_video.py` — 模拟右键菜单

## 报告格式

每跑完一个 workflow 写一份 YAML 进 `/Users/apple/Documents/GitHub/aitoolstudio/.mavis/plans/wf_test_results/`，文件命名 `wf_<N>_<name>.yaml`：

```yaml
workflow: ltx_1080p_v4.json
tested_at: 2026-06-09T...
backend: 192.168.1.195:8188
status: success|failed|timeout
duration_sec: 234
output:
  path: /home/sjm/ComfyUI/output/ltx_1080p_v4_00020.mp4
  width: 480
  height: 256
  fps: 24
  frames: 97
  duration: 4.04
  size_bytes: 250194
quality:
  photorealism: 3  # 主观 1-10
  notes: "跟之前 E2E 报告一致"
errors: []
warnings:
  - "length 96 → 97 (8n+1 对齐)"
node_count: 16
input: # 实际注入到 workflow 的
  prompt: "..."
  width: 480
  height: 256
  length: 97
  seed: 1234
```

最终汇总进 `/Users/apple/Documents/GitHub/aitoolstudio/.mavis/plans/wf_test_summary_2026-06-09.md`，包含 PASS/FAIL 表 + 修复建议优先级。

## 约束

- 不要改任何 workflow JSON / 代码
- 跑过的输出存到 /tmp/wf_test_assets/<name>/ 给后续 vision 分析用
- 每个 workflow 最多跑 1 次（除非出错需要重试）
- 195/197/249 任一台后端都可以
- 失败也要报告，写明失败原因 (缺模型 / 节点连线错 / OOM / ...)

## 完成标准

- 11 个 workflow 全部测过（有 PASS/FAIL 记录）
- 失败的有具体错误信息
- 输出 mp4 全部下载到 /tmp/wf_test_assets/
- 汇总报告写完
- 修建议按优先级排序

## 时间预算

- 单个 T2V workflow: ~3-5 分钟
- 单个 I2V workflow: ~3-5 分钟
- 视频反推: ~2-3 分钟
- V2V 超分: ~3-5 分钟
- 总计: 11 × 4 = ~45 分钟（顺序跑），或 ~15-20 分钟（3 并发）
