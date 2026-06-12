# 数字人模特生产线 · 操作手册

> 2026-06-12 搭建。目标：商业账号级一致性的 AI 模特资产（定妆 → LoRA → 批量出图 → 质检）。

## 基础设施一览

| 组件 | 位置 | 说明 |
|---|---|---|
| 定妆出图 workflow | `workflows/Qwen-Image-Casting.json` | Qwen-Image 2512 fp8 文生图，Apache 2.0 商用安全；已在 249 实测跑通 |
| prompt 矩阵批量脚本 | `scripts/casting_matrix.py` | 组合 × 种子批量提交到任意 worker，产出落 `output/casting/` |
| 人脸一致性质检 | `scripts/face_qc.py`（197:`~/face_qc.py`） | ArcFace 余弦相似度，阈值默认 0.45；197 上 `~/face_qc_env` 已装好 |
| insightface 权重 | NAS `models/insightface/models/buffalo_l/` | 检测 + 识别，全 worker 共享 |
| LoRA 训练环境 | 195:`~/musubi-tuner` + `~/musubi_env` | musubi-tuner，torch 2.12 cu130，bitsandbytes 已装 |
| 夜间训练调度 | 195:`~/lora_night_train.sh`（crontab 23:30） | 扫 NAS 任务目录无人值守训练，早 6 点截止 |
| 训练主权重 | NAS `models/diffusion_models/qwen_image_bf16.safetensors` | 41GB bf16（训练用；推理用已有的 fp8 版） |

## 流程 1：定妆（每个模特做一次）

1. 编辑 prompt 矩阵 spec（参考 `scripts/casting_spec.example.json`）
2. 批量提交（约 100 张，挑空闲 worker）：
   ```bash
   python3 scripts/casting_matrix.py --spec my_spec.json --instance 192.168.1.249:8188 --seeds 5
   ```
3. 人工从 `output/casting/` 选定唯一主脸，**立即做**：
   - 用主脸跑一次 face_qc 反查其余候选，确认没有撞脸真人风险（留档）
   - 记录生成参数 + 种子（manifest JSON 已自动保存）

## 流程 2：数据集与 LoRA（每个模特 1-2 周打磨）

1. 用 Qwen-Image-Edit 2511 + 多角度相机节点（195 已装）把主脸扩成 40–60 张：
   多角度 / 多表情 / 多光线 / 全身半身特写
2. 每张图配同名 `.txt` 打标（统一触发词，如 `meimei, a young chinese woman`）
3. 投递训练任务——在 NAS 建目录即可：
   ```
   /mnt/nas_comfyui/AI-Tool-Studio/comfyui/training/jobs/meimei_v1/
     dataset/        # 图 + .txt
     job.env         # 可选：EPOCHS=20 NETWORK_DIM=32 RESOLUTION=1328 SWAP_BLOCKS=16
   ```
4. 当晚 23:30 自动开训（GPU 忙会等空闲），产出：
   `models/loras/digital_humans/meimei_v1.safetensors`，日志在任务目录 `train.log`
5. **回炉迭代**：挂 v1 LoRA 批量出 200 张 → face_qc 打分 → 人工挑 top 30 → 建 `meimei_v2` 任务再训。两三轮后达到商用一致性。

## 流程 3：日常生产 + 质检闸门

```bash
# 197 上跑（CPU 推理，约 0.5 秒/张）
~/face_qc_env/bin/python ~/face_qc.py \
  --ref /path/to/定妆参考照目录 \
  --candidates /path/to/当批产出 \
  --threshold 0.45 \
  --report report.json \
  --sort-into /path/to/分拣目录   # pass/ fail/ 自动分拣
```

阈值口径：同一身份 >0.55，不同身份 <0.30。先用 0.45，跑过第一批真实数据后按分布回调。

## 注意事项

- **合规**：发布平台需按《人工智能生成合成内容标识办法》打 AI 标识；定妆主脸务必留训练来源档案。
- **许可**：主力链路（Qwen-Image / Wan / Z-Image）均 Apache 2.0；Flux 系仅用于内部辅助，商用输出前核对 license。
- 195 训练时显存 fp8_base 模式约占 24G+；如 OOM，在 job.env 加 `SWAP_BLOCKS=16`。
- 夜训脚本判定 GPU 空闲的阈值是占用 <4GB；ComfyUI 常驻模型不卸载会卡住训练，必要时夜间先在工作台释放显存。
