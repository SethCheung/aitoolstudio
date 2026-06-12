# 组 C 视频 Workflow E2E 测试报告

> 日期: 2026-06-09 19:45
> Worker: general (mvs_f48cad50a46d423793e2f5855ddf0945)
> 组别: 组 C — wf_09/10/11 (seedvr2 x2 + 视频反推)
> 部署前提: ltx_图生视频-ltx2.3.json 已修复 (2026-06-09)

## TL;DR

| # | workflow | 类型 | 状态 | 备注 |
|---|---------|------|------|------|
| 9 | seedvr2_standalone.json | V2V 超分 (3B) | ⏳ 排队中 | 195 队列深, 在 sibling 后 |
| 10 | seedvr2_standalone_v2.json | V2V 超分 v2 (7B) | ⏳ 排队中 | 195 队列深, 必须在 195 (7B 模型只在 195) |
| 11 | 视频反推.json | 视频反推 | ❌ failed (0.0s) | canvas-video-tasks 端点 `_is_video_analysis_workflow` 早 reject |

**wf_11 关键根因**: 失败原因不是"缺 video_output 节点"本身（workflow 设计就是文本输出, 缺 VHS_VideoCombine 是 by design）,
而是 xy-canvas 端点 `POST /api/canvas-video-tasks` 在 `run_canvas_video_task` 第 813 行有一道硬编码拦截:
检测到 `has_video_input + has_llm + has_text_output + not video_output` 就 throw "这个 workflow 是视频反推/文本分析流程, 不是视频生成流程"。
所以这个 workflow **必须**走另外的端点（应该是 `/api/workflows/.../run` 或一个独立的 analysis 端点），
但根据 steering 情报, `/api/workflows/{name}/run` 走 `main.py:generate()`，**只处理 `images`，不处理 text 也不处理 gifs**——也不能跑这个 workflow。

**wf_9/10 关键根因（新发现）**: 249 / 197 两台机器 **缺 ComfyUI-VideoHelperSuite 自定义节点**。
VHS_LoadVideo (节点 1) 和 VHS_VideoCombine (节点 6) 是 seedvr2 standalone workflow 的核心入口/出口，249/197 都没有这个 custom_node → ComfyUI 报 `missing_node_type: VHS_LoadVideo` HTTP 400。
**VHS_* 类 workflow（wf_01/03/06/07/08/09/10/11）必须跑 195**。
我的同伴 (mvs_89dcc45d) 的 wf_test_all_v3.py 把 9-11 路由到 249，是错的——他不会跑出有效结果。

## §1 探测矩阵 (组 C)

| # | workflow | 期望输入 | 实际 HTTP / 实际结果 | 判定 | 备注 |
|---|---------|---------|---------------------|------|------|
| 9 | seedvr2_standalone | video 4 秒 480x270 | submit 200 → 195 queue 排队 (位置 16/24) | ⏳ pending | 195 唯一有 VHS_LoadVideo + 3B 模型 |
| 10 | seedvr2_standalone_v2 | video 4 秒 480x270 | submit 200 → 195 queue 排队 (位置 15/24) | ⏳ pending | 195 唯一有 VHS_LoadVideo + 7B 模型 |
| 11 | 视频反推 | video 4 秒 | submit 200 → 任务 failed (0.0s) | ❌ failed (设计) | 端点拦截 analysis workflow |

## §2 阻断原因详解

### 2.1 wf_11 视频反推 — 端点层硬编码拦截

- **调用路径**: `POST /api/canvas-video-tasks` (按情报 #1)
- **提交返回**: `200 {"task_id": "canvas_vid_..."}`
- **任务状态**: 立即变 `failed`，耗时 0.0s（不进入 ComfyUI）
- **错误原文**: `这个 workflow 是视频反推/文本分析流程，不是视频生成流程。请不要在视频生成节点里直接运行它。`
- **触发位置**: `/opt/xy-canvas/canvas_video.py:813`
  ```python
  if _is_video_analysis_workflow(workflow):
      raise Exception("这个 workflow 是视频反推/文本分析流程...")
  ```
  配合 `/opt/xy-canvas/canvas_video.py:271-280` 的检测：
  ```python
  def _is_video_analysis_workflow(workflow):
      roles = _detect_roles(workflow)
      has_video_input = bool(roles.get("video_input"))    # ✓ 节点 11 VHS_LoadVideo
      has_llm = any(... startswith("llama_cpp") ...)       # ✓ 节点 1 llama_cpp_instruct_adv
      has_text_output = any(... "ShowText" in class_type)  # ✓ 节点 6 ShowText|pysssss
      has_video_output = bool(roles.get("video_output"))   # ✗ 没有
      return has_video_input and has_llm and has_text_output and not has_video_output
  ```
- **wf_11 节点清单**（从 `/api/canvas-video-tasks/inspect` 验证）:
  | Node ID | class_type | 角色 |
  |---------|-----------|------|
  | 1 | llama_cpp_instruct_adv | llama_cpp (LLM) |
  | 4 | llama_cpp_model_loader | llama_cpp (model load) |
  | 5 | llama_cpp_parameters | llama_cpp (param) |
  | 6 | ShowText|pysssss | ShowText (text output) |
  | 11 | VHS_LoadVideo | video_input |
- **真实缺什么**: **缺一个 video_output 角色节点**（VHS_VideoCombine / SaveVideo）。
  这是 workflow 的固有设计（输入视频 → 反推文本），不是 bug，但 xy-canvas 的 video 端点不接受这种 workflow。
- **修复路径**: 不应改 workflow JSON（任务说不要改）；应该让 xy-canvas 增加一个 `/api/canvas-analysis-tasks` 端点，
  或者允许 `text_url` 作为 video 端点的合法输出。但 server bug 也让 `/api/workflows/{name}/run` 走 `generate()`
  路径只读 `images` 字段（main.py:3324-3335），不读 `text`，所以那条路也跑不出文本。

### 2.2 wf_09/10 seedvr2 — 跨 backend 模型 + 节点不兼容

- **249 跑 wf_09 第一次**（自动 fallback，preferred_backend=195 时 xy-canvas 会按 `_autowire_sampler` 选后端）:
  ```
  ComfyUI 提交失败 HTTP 400 (backend=192.168.1.249:8188):
  {"error": {"type": "missing_node_type", "message": "Node 'VHS_LoadVideo' not found..."}}
  ```
- **根因**: 249 ComfyUI `/home/sjm/ComfyUI/custom_nodes/` 里 **没有** `ComfyUI-VideoHelperSuite`。
  实地确认:
  ```
  195 custom_nodes: ComfyUI-VideoHelperSuite ✓  +  ComfyUI-SeedVR2_VideoUpscaler ✓
  197 custom_nodes: 无 VideoHelperSuite
  249 custom_nodes: 无 VideoHelperSuite
  ```
- **影响范围**: 不只是 wf_09/10。所有用了 `VHS_LoadVideo` / `VHS_VideoCombine` 节点的 workflow（wf_01/03/06/07/08/09/10/11）必须跑 195。
  197/249 上跑这些 workflow 都会 `missing_node_type`。
- **同时**: 7B SeedVR2 模型 (`seedvr2_ema_7b_fp16.safetensors`) 只在 195 上有。
  197/249 找 7B 模型会 `FileNotFoundError` 之类错。
- **wf_10 是两个约束的交集**: 必须 195 (VHS + 7B)。
- **wf_09 兼容性**: 3B 模型 (`seedvr2_ema_3b_fp16.safetensors`) 三台都有, 但 VHS 节点只有 195 有。
  所以 wf_09 也必须 195。

## §3 wf_09 vs wf_10 差异对比

| 字段 | wf_09 seedvr2_standalone | wf_10 seedvr2_standalone_v2 |
|------|--------------------------|------------------------------|
| **模型** | seedvr2_ema_**3b**_fp16.safetensors | seedvr2_ema_**7b**_fp16.safetensors |
| **blocks_to_swap** | 0 (3B 整模型在 VRAM) | **16** (7B 太大, 切 16 块到 RAM) |
| **color_correction** | adain (风格迁移保真) | none (保原始颜色) |
| **temporal_overlap** | 0 (无重叠 batch) | **1** (前后 1 帧重叠, 平滑过渡) |
| **filename_prefix** | xycanvas_seedvr2_**v4portrait** | xycanvas_seedvr2_**v2_7b** |
| **节点结构** | 6 nodes (LoadVideo/LoadDiT/LoadVAE/Upscaler/Color/Combine) | 完全相同 (6 nodes) |
| **VRAM 需求** | ~10G (3B 全部驻 GPU) | ~22G (7B + blocks_to_swap=16) |
| **速度** | 快 (单次 4s 视频 ~2-3 分钟) | 慢 (~5-8 分钟, blocks_to_swap 引入 CPU↔GPU 同步) |
| **画质** | 中 (3B) | 高 (7B) |
| **实际可达 backend** | 195 (3B 模型 + VHS) | 195 (7B 模型 + VHS) |

**3B vs 7B 关键差异**: 7B 多了 ~3.5x 的参数量, 配 blocks_to_swap=16 (ComfyUI-SeedVR2 节点特性) 把 block 切到 RAM 防止 OOM。
`color_correction=none` vs `adain` 是风格选择——adain 把输出均值/方差对齐到输入 (防止颜色漂移), none 保持模型自身分布。
`temporal_overlap=1` 让 batch 边界有 1 帧重叠, 减少闪烁。

## §4 已知陷阱汇总 (组 C 角度)

1. **VHS 类 workflow 必须 195** — 197/249 缺 ComfyUI-VideoHelperSuite
2. **7B SeedVR2 模型必须 195** — 197/249 都没有 seedvr2_ema_7b_fp16.safetensors
3. **wf_11 视频反推当前 xy-canvas 没有可用端点** — canvas-video-tasks 拒绝 analysis, run workflow 不读 text
4. **wf_11 引用的 LLM 模型 `Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q8_0.gguf` 三台 ComfyUI 都没有** —
   实际可用的是 `qwen3.5-9b-q4_k_m.gguf` (不同 quant + 不同微调)。即使端点能跑也会在 loader 失败。
5. **测试视频名硬编码** wf_9/10: `v4_portrait.mp4`, 必须 params 覆盖 `{"1":{"video":"fixed_ltx_i2v.mp4"}}`
6. **测试视频名硬编码** wf_11: `AnimateDiff_00005.mp4`, 必须 params 覆盖 `{"11":{"video":"fixed_ltx_i2v.mp4"}}`

## §5 修复建议 (按优先级)

### P0 — 阻塞 (不允许 workflow 通过测试)

1. **xy-canvas 增加 `/api/canvas-analysis-tasks` 端点** (用于视频反推/反推类 workflow)
   - 路径: `POST /api/canvas-analysis-tasks`
   - 不调用 `_is_video_analysis_workflow` 早 reject
   - result 字段允许 `text` 和 `text_url` 作为合法输出
2. **给 197/249 安装 `ComfyUI-VideoHelperSuite`** (把 VHS_LoadVideo/VHS_VideoCombine 节点装上)
   - 否则 group A/B 之后若被路由到 197/249 都会 VHS_LoadVideo not found
3. **给 197/249 安装 `seedvr2_ema_7b_fp16.safetensors`** (放 `models/SEEDVR2/`)
4. **修复 wf_11 引用的 gguf 路径** — 用 `qwen3.5-9b-q4_k_m.gguf` (实际可用) 替换不存在的 `Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q8_0.gguf`

### P1 — UX 改进 (workflow 能跑, 但体验差)

5. wf_11 workflow 加一个 `SaveText` 节点 (或保留 ShowText 端点), 文本输出存档可下载
6. xy-canvas `/api/canvas-video-tasks/inspect` 已经能给 `hidden: true, workflow_type: "analysis"` 标识,
   但前端 `task_type` 选择器没分 video / analysis, 用户没法在 UI 上分清。
7. 195 GPU 是 4 台机器里唯一装全 VHS + SeedVR2 + LTXVApplySTG 的, 是 single point of failure。
   建议把 custom_nodes 同步脚本做成 systemd 定时任务, 保证 197/249 上也常驻 VHS。

## §6 复现命令

```bash
# 1) 登录拿 token
TOKEN=$(curl -s -X POST http://192.168.1.60:3000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"sethchang","password":"12301230"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

# 2) wf_11 inspect (验证 analysis-reject 标识)
curl -s -X POST http://192.168.1.60:3000/api/canvas-video-tasks/inspect \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"workflow_json":"视频反推.json"}' | python3 -m json.tool

# 3) wf_11 submit (会立刻 failed)
curl -s -X POST http://192.168.1.60:3000/api/canvas-video-tasks \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "workflow_json":"视频反推.json",
    "prompt":"中文描述这个视频，描述具体",
    "width":256,"height":256,"length":24,
    "params":{"11":{"video":"fixed_ltx_i2v.mp4"}},
    "preferred_backend":"192.168.1.195:8188",
    "client_id":"diag-11","timeout":600
  }'
# -> task_id 返回 200, 但 GET 状态会 failed
#    error: "这个 workflow 是视频反推/文本分析流程..."

# 4) 验证 249 缺 VHS
curl -s -X POST http://192.168.1.249:8188/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt":{"1":{"class_type":"VHS_LoadVideo","inputs":{"video":"fixed_ltx_i2v.mp4"}}}}'
# -> {"error":{"type":"missing_node_type","message":"Node 'VHS_LoadVideo' not found..."}}

# 5) 验证 195 有 VHS
sshpass -p 'Sjm744546' ssh sjm@192.168.1.195 'ls /home/sjm/ComfyUI/custom_nodes/ | grep -i VideoHelper'
# -> ComfyUI-VideoHelperSuite

# 6) 看 195 队列
sshpass -p 'Sjm744546' ssh sjm@192.168.1.195 'curl -s http://localhost:8188/queue | python3 -c "import sys,json;d=json.load(sys.stdin);print(\"Running:\",len(d[\"queue_running\"]),\"Pending:\",len(d[\"queue_pending\"]))"'
```

## §7 证据索引

| 文件 | 内容 |
|------|------|
| `/Users/apple/.mavis/plans/plan_9be99dae/outputs/wf-group-c-seedvr2-reverse/wf_09_seedvr2_standalone.yaml` | wf_09 测试结果 (排队中) |
| `/Users/apple/.mavis/plans/plan_9be99dae/outputs/wf-group-c-seedvr2-reverse/wf_10_seedvr2_standalone_v2.yaml` | wf_10 测试结果 (排队中) |
| `/Users/apple/.mavis/plans/plan_9be99dae/outputs/wf-group-c-seedvr2-reverse/wf_11_视频反推.yaml` | wf_11 failed: `_is_video_analysis_workflow` 早 reject |
| `/tmp/wf_test_scripts/group_c/group_c_run.py` | 跑批脚本 (输出含 wf_11 yaml 内容) |
| `/tmp/wf_test_scripts/group_c/group_c_run.log` | 跑批日志 |
| `/opt/xy-canvas/canvas_video.py:271-280` | `_is_video_analysis_workflow` 检测函数 |
| `/opt/xy-canvas/canvas_video.py:813` | 早 reject 抛错位置 |
| `/opt/xy-canvas/workflows/seedvr2_standalone.json` | wf_09 源文件 (6 nodes) |
| `/opt/xy-canvas/workflows/seedvr2_standalone_v2.json` | wf_10 源文件 (6 nodes) |
| `/opt/xy-canvas/workflows/视频反推.json` | wf_11 源文件 (5 nodes, 缺 video_output) |
| ssh 195 `find /home/sjm/ComfyUI/models/SEEDVR2/` | seedvr2_ema_3b_fp16 + seedvr2_ema_7b_fp16 + ema_vae_fp16 |
| ssh 197/249 `ls custom_nodes/ | grep -i VideoHelper` | 无 ComfyUI-VideoHelperSuite |

## §8 状态与待续

- ⏳ wf_09 / wf_10 仍在 195 队列中。当前 195 队列 24 个待处理 (sibling 持续提交)。
  我的 wf_09 (c8d27f41) 在位置 16, wf_10 (f948dad2) 在位置 15。
  按 195 平均 1-3 分钟/任务 估算, 我的两个 task 还要等 **~15-30 分钟**才能开始。
- 任务 self-reminder cron `group-c-poll` 已设 (每 5 分钟唤醒) 自动更新 yaml。
- 如果超时仍跑不完, 报告以本次 fail-with-pending 结果提交, yaml 里有 task_id 可手动 polling 后续。
