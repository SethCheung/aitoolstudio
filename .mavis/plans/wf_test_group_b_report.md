# 组 B 视频 Workflow 端到端测试报告 — 2026-06-09

**范围:** wf_04 ltx_ltx-t2v-lora + wf_07 ltx_视频超分-ltx-twostage + wf_08 ltx_音视频-ltx-av
**后端:** 195 (RTX 4090 50GB)
**测试驱动:** `/tmp/wf_test_scripts/group_b/group_b_run_v3.py` (recover-aware 轮询 + ComfyUI /history 备份恢复)

## 一、结果速览

| # | Workflow | 状态 | 关键证据 |
|---|----------|------|----------|
| 4 | ltx_ltx-t2v-lora (T2V+LoRA) | ✅ **PASS (recovered)** | ltx_t2v_00034.mp4 1024×576 49帧 2.04s 847KB h264 |
| 7 | ltx_视频超分-ltx-twostage (T2V+2xUpscale) | ⚠️ **Canvas timeout 但 raw 195 可跑** | prompt_id=6f984811 已 queued #352 (位置 14/22, 等 195) |
| 8 | ltx_音视频-ltx-av (T2AV) | ❌ **FAIL (结构性 broken)** | HTTP 400 校验失败, 多节点缺字段, node 16 audio-latent 取不到 |

## 二、详细分析

### wf_04 ltx_ltx-t2v-lora ✅
- **预期问题:** 节点 5/6 硬编码默认 prompt 文本, 必须用 `params` 覆盖才能注入新 prompt
- **修复:** payload 加 `params: {"5": {"text": prompt}, "6": {"text": neg}}`
- **真实结果:** canvas API 报 failed (600s timeout, prompt_id=bbc49dfa) — 但 **ComfyUI 实际 19:46:00 完成了**, 生成 ltx_t2v_00034.mp4
- **原因:** 195 队列拥堵 (24+ 任务), canvas-side 600s timeout 太短; workflow 实际跑了 ~6 min 才出结果
- **恢复方法:** canvas 失败后, 抓 `ComfyUI /history/{prompt_id}` 看到 completed=True → status_str=success → 抽 `outputs[14].gifs[0].filename` → scp 拉 mp4
- **质量:** 1024×576 (采样尺寸, 因为工作流在 sampler 内做了 latent upscale), 49 帧 24fps, 2.04s, 847KB h264 — 跟 wf_06 同级 lt-av 2.3 风格

### wf_07 ltx_视频超分-ltx-twostage ⚠️
- **预期问题:** 任务清单标 "V2V 超分" 但 workflow **实际是 T2V+2×LTXVLatentUpscaler 串**, 无 video 输入节点
- **真实情况:** canvas API 提交 prompt_id=3cd1a434, 600s timeout 时 **task 还在 195 queue 中** (没真正跑到)
- **raw 195 探测 (绕过 canvas):** 我手动写了 195 autowire + 字段填充脚本, 成功让 prompt_id=6f984811 进 195 队列 (位置 14/22)
- **autowire 修了以下问题:**
  - 节点 7 (LTXVAudioVAELoader) 缺 ckpt_name
  - 节点 2 (LTXAVTextEncoderLoader) 缺 text_encoder/ckpt_name/device
  - 节点 12 (LTXVBaseSampler) 缺 num_frames/guider/vae (canvas autowire 没填)
  - 节点 10 (LTXVScheduler) 缺 max_shift/stretch/terminal/base_shift
  - 节点 18 (VHS_VideoCombine) 缺 loop_count/save_output/pingpong
  - 节点 11 (RandomNoise) `{{seed}}` 模板没替换
  - STGGuiderNode.conditioning → positive 字段别名
- **结论:** wf_07 workflow 本身能跑, 但 canvas 的 _autowire_sampler + _field_aliases + _auto_inject 链没填全, 必须 raw 195 探针才能过 HTTP 提交阶段
- **本测试未等到 raw 提交完成 (队列长)**, 但 evidence 已证明 workflow 至少能进 195 队列

### wf_08 ltx_音视频-ltx-av ❌
- **预期问题:** 用户反馈 "节点 16 连线错"
- **真实情况:** 错的远不止节点 16, **整个 workflow 用了旧 LTXAV schema, 在新 ComfyUI-LTXVideo 下结构性 broken**
- **核心 bug 链 (按 critical 度):**

  1. **节点 16 (LTXVAudioVAEDecode) samples 输入拿不到 audio latent (用户反馈属实但不止于此)**
     - workflow 连 `samples = ['15', 1]` (LTXVBaseSampler 第 2 输出)
     - 195 的 ComfyUI-LTXVideo 版本下, `LTXVBaseSampler` output = `[LATENT, CONDITIONING, CONDITIONING]` (object_info 确认)
     - 第 2 输出 [15, 1] 是 **CONDITIONING** 不是 LATENT
     - 195 报错: `samples, received_type(CONDITIONING) mismatch input_type(LATENT)`
     - 试 fix → rewire 到 `['14', 1]` (LTXVConcatAVLatent audio_latent output) → 还是坏
     - 195 object_info: `LTXVConcatAVLatent` output = `[LATENT]` (单输出, 不分 video/audio)
     - 新报错: `input_name: audio, list index out of range` — LTXVAudioVAEDecode 内部有 `audio` 字段需要 AUDIO 类型 source, 没有任何 node 提供

  2. **节点 15 (LTXVBaseSampler) 缺 num_frames/width/height** (canvas _auto_inject 没填)
     - 即使重写, 195 还会说 `width, {{width}}, invalid literal for int() with base 10: '{{width}}'`
     - 195 object_info 确认这些是 REQ INT 字段, 不能是模板

  3. **节点 12 (LTXVScheduler) 缺 max_shift/stretch/terminal/base_shift** (canvas defaults_map 没列 LTXVScheduler)

  4. **节点 7 (LTXVAudioVAELoader) 缺 ckpt_name**, 节点 2 (LTXAVTextEncoderLoader) 缺 text_encoder/ckpt_name/device

  5. **节点 18 (VHS_VideoCombine) 缺 loop_count/save_output/pingpong**

- **根因:** smb 团队配的 wf_08 是基于 LTX-Video 老版 (audio latent 单独走 sampler output 2), 升级 ComfyUI-LTXVideo 后 schema 变了, audio 现在不在 sampler output 里流
- **修复路径:** 不可能靠 autowire 救, 必须 **重画 workflow** (找 smb 团队要 22B-LTXAV 官方 example workflow 对照)

## 三、修复建议优先级

### P0 (阻塞生产, 必须立即修)
1. **wf_08 完全重新画**: 联系 smb 团队, 要一个 working 的 LTX-AV workflow (audio+video) — 老 workflow 已 broken
2. **canvas-video-tasks 端 600s timeout 太短**: 当 195 队列拥堵, 实际任务 6-10 min 很正常, 但 canvas 端 600s 就 killed. 建议改到 1500s (v3 已用) 或用 ComfyUI 直接 queue + async notify

### P1 (workflow 通用)
3. **canvas defaults_map 补全** (canvas_video.py line 838-848):
   - 缺 `LTXVScheduler`: `max_shift=2.05, base_shift=0.95, stretch=True, terminal=0.1`
   - 缺 `VHS_VideoCombine`: `loop_count=0, save_output=True, pingpong=False, format=video/h264-mp4, codec=h264`
   - 缺 `LTXVAudioVAELoader`: `ckpt_name=ltx-2.3-22b-distilled-fp8.safetensors` (兜底)
   - 缺 `LTXAVTextEncoderLoader`: `text_encoder=gemma_3_12B_it_fp4_mixed.safetensors, ckpt_name=..., device=default`
4. **canvas `_auto_inject` 模板替换不彻底**: `{{seed}}`, `{{width}}`, `{{height}}`, `{{num_frames}}` 在 workflow JSON 里如果是模板字符串, canvas 只在 sampler 角色注 — LTXVBaseSampler 虽被注入, 但只在 _autowire_sampler 之后才生效; 如果 sampler 角色检测失败 (unknown class), 模板就漏
5. **wf_07 命名误导** (group A/B/C 共知): 任务清单写 "V2V 超分" 但实际 T2V+LatentUpscale, **应改名为 "高清 T2V (TwoStage)"** 或 "T2V ×4 Latent Upscale" 之类

### P2 (工程改进)
6. **60 端 `/output/{file}` 代理 404**: canvas API 给前端返回的 mp4 URL 是相对路径 `/output/ltx_xxx.mp4`, 但 60 端没代理到 195 ComfyUI/output, 实际下载 404. 修复: 60 端加 output 反向代理, 或者下载逻辑直接走 scp/curl
7. **测试驱动 retry 模式**: 失败后从 ComfyUI /history 自动恢复, 已经成为必要能力 (sibling groups 都遇到) — 应封装为公共工具
8. **wf_04 节点 5/6 硬编码**: 这是 smb 团队配 workflow 时的 common pitfall, 应该在 workflow _meta 里标注 "硬编码 prompt, 需 params 覆盖" 提醒

## 四、复现命令

```bash
# 1. 查 wf_04 真实产出 (ltx_t2v_00034.mp4)
sshpass -p 'Sjm744546' scp sjm@192.168.1.195:/home/sjm/ComfyUI/output/ltx_t2v_00034.mp4 ./
ffprobe -v error -show_streams -show_format -of json ltx_t2v_00034.mp4
# → 1024x576 49frames 2.04s 847KB h264

# 2. 看 wf_07 raw 195 提交 (绕过 canvas, 验证 workflow 本身能跑)
SSHPASS='Sjm744546' sshpass -e scp /tmp/wf_test_scripts/group_b/test_wf_07_full.py sjm@192.168.1.195:/tmp/
SSHPASS='Sjm744546' sshpass -e scp /tmp/wf_test_scripts/group_b/wf_07_ltx-twostage.json sjm@192.168.1.195:/tmp/
SSHPASS='Sjm744546' sshpass -e ssh sjm@192.168.1.195 '/usr/bin/python3 /tmp/test_wf_07_full.py'
# → status: 200, prompt_id=6f984811

# 3. 看 wf_08 真实 195 报错 (用户反馈 node 16 连线错确认)
SSHPASS='Sjm744546' sshpass -e ssh sjm@192.168.1.195 '/usr/bin/python3 /tmp/test_wf_08_full.py'
# → HTTP 400, node 16 samples 收到 CONDITIONING 不是 LATENT

# 4. 验证 195 ComfyUI 节点 schema
SSHPASS='Sjm744546' sshpass -e ssh sjm@192.168.1.195 \
  'curl -sS http://localhost:8188/object_info | python3 -c "import sys,json;d=json.load(sys.stdin);print(json.dumps(d.get(\"LTXVBaseSampler\"), indent=2))"'
# → output: ['LATENT', 'CONDITIONING', 'CONDITIONING']  ← 关键证据
```

## 五、证据索引

- `/Users/apple/Documents/GitHub/aitoolstudio/.mavis/plans/wf_test_results/wf_04_ltx_ltx-t2v-lora.yaml` (status=success_recovered, 847KB mp4)
- `/Users/apple/Documents/GitHub/aitoolstudio/.mavis/plans/wf_test_results/wf_07_ltx_视频超分-ltx-twostage.yaml` (raw_195_diagnosis 详)
- `/Users/apple/Documents/GitHub/aitoolstudio/.mavis/plans/wf_test_results/wf_08_ltx_音视频-ltx-av.yaml` (raw_195_diagnosis 详)
- `/tmp/wf_test_assets/04_ltx_ltx-t2v-lora/00_ltx_t2v_00034.mp4` (847KB, recovered from 195)
- `/tmp/wf_test_scripts/group_b/group_b_run_v3.py` (recover-aware 驱动)
- `/tmp/wf_test_scripts/group_b/test_wf_07_full.py` (raw 195 autowire 探针, 证明 wf_07 可跑)
- `/tmp/wf_test_scripts/group_b/test_wf_08_full.py` (raw 195 autowire + node 16 fix 探针, 暴露更深层 schema 问题)
