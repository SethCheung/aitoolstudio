# `ltx_图生视频-ltx2.3.json` 质量诊断 + 修复

> 日期：2026-06-09
> 作者：Mavis
> 给谁：用户（确认是否应用修复）
> 受影响：图生视频工作流（I2V）输出

---

## TL;DR

**这个 workflow 配错了 3 个关键参数**，导致出来的视频质量差。

| 问题 | 错值 | 对值（参考 v4） | 影响 |
|---|---|---|---|
| **LoraLoaderModelOnly.strength_model** | **1.0** | 0.4 | 把模型覆盖成 distilled，但没减少步数 |
| **LTXVScheduler.steps** | **25** | 35 | 步数少 30%，细节直接丢 |
| **STGGuiderNode.rescale** | **0.0** | 0.5 | 噪声累积，颜色偏（油画感来源之一） |

**根因**：smb 团队配 workflow 时没把 `studio_quality` 的好参数复制到 `图生视频`。

---

## 完整对比

| 节点 | ltx_1080p_v4.json | ltx_studio_quality.json | ltx_图生视频-ltx2.3.json | ltx_ltx-i2v.json |
|---|---|---|---|---|
| LoRA 主: `ltx-2.3-22b-distilled-lora-384` strength | **0.4** | **0.4** | **1.0** ❌ | 无 |
| LoRA 辅: `ltx-2-19b-squish-lora` strength | **0.15** | **0.15** | 无 | 无 |
| LTXVScheduler.steps | **35** | **35** | **25** ❌ | 20 |
| LTXVScheduler.max_shift | 1.8 | 1.8 | (默认) | 2.05 |
| LTXVScheduler.base_shift | 0.85 | 0.85 | (默认) | 0.95 |
| STGGuiderNode.cfg | 3.0 | 3.0 | 1.0 | (CFGGuider 1.0) |
| STGGuiderNode.rescale | **0.5** | **0.5** | **0.0** ❌ | 无 STG |
| LTXVApplySTG.block_indices | 14, 19 | 14, 19 | 14, 19 | (无 STG) |

**核心：v4 是 35 步 + rescale 0.5 + distilled lora 0.4，你这个是 25 步 + rescale 0 + distilled lora 1.0** —— 三个关键参数全错。

---

## 修复方案

把 `ltx_图生视频-ltx2.3.json` 改成跟 v4 / studio_quality 一样的配置：

```diff
节点 4 LoraLoaderModelOnly:
-  strength_model = 1.0
+  strength_model = 0.4
+  // (可选) 加一个 squish lora:
+  lora_name = 'ltx-2-19b-squish-lora.safetensors'  // strength_model = 0.15

节点 12 LTXVScheduler:
+  max_shift = 1.8
+  base_shift = 0.85
+  stretch = True
+  terminal = 0.15
-  steps = 25
+  steps = 35   // 跟 v4 一样

节点 10 STGGuiderNode:
+  rescale = 0.5   // 噪声重新缩放, 避免颜色偏
   cfg = 1.0   // 保留 I2V 弱 cfg, 比 v4 的 3.0 强更接近原图
   stg = 0.0   // 保留
```

**外加 `LTXVImgToVideoAdvanced.strength = 0.85`**：当前是 0.85（保留原图 85%），可以保持。如果想"动得更多"改成 0.7；如果想"保留原图"改成 0.95。

---

## 修复后预期

- 跟 v4 studio_quality 同一个质量档（3-4/10 photorealism，因为 LTX 22B 蒸馏版本身就这样）
- 内容更稳，颜色不会油画感
- 步数 25→35 慢 ~40%（v4 一次 ~3-5 分钟，这个 ~4-7 分钟）

---

## 工作量

- 修改 workflow JSON：5 分钟
- 复测 1 个视频验证质量：~5-7 分钟
- 截图对比：2 分钟
- **总计：~15 分钟**

---

## 要不要做？

A. **做**——按上面方案改 + 复测
B. **先这样，记下待办**——放 todo 里，下次一起处理
C. **改一部分**——比如只改 lora 强度，不动步数（快但效果有限）

我建议 **A**。
