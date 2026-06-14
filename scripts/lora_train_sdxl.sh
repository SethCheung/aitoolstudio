#!/usr/bin/env bash
# Juggernaut XL (SDXL) 角色 LoRA 训练（sd-scripts/kohya）。复用 ria 锁定数据集。
# 用法（195，musubi_env 可复用）：  ~/lora_train_sdxl.sh
# 数据集结构： training/jobs/ria_sdxl/<repeats>_ria/  (图+同名.txt)
# 产出： NAS models/loras/digital_humans/ria_sdxl*.safetensors
set -uo pipefail

NAS=/mnt/nas_comfyui/AI-Tool-Studio/comfyui
SD=~/sd-scripts
PY=~/musubi_env/bin/python
ACC=~/musubi_env/bin/accelerate
WORK=~/lora_work/ria_sdxl
LORA_OUT=$NAS/models/loras/digital_humans

CKPT=$NAS/models/checkpoints/juggernautXL_version6Rundiffusion.safetensors
VAE=$NAS/models/vae/sdxl_vae.safetensors
DATA=$NAS/training/jobs/ria_sdxl

mkdir -p "$WORK/out" "$LORA_OUT"
cd "$SD" || exit 1

"$ACC" launch --num_processes=1 --num_machines=1 --mixed_precision=bf16 --dynamo_backend=no \
  sdxl_train_network.py \
  --pretrained_model_name_or_path "$CKPT" \
  --vae "$VAE" \
  --train_data_dir "$DATA" \
  --caption_extension ".txt" \
  --resolution 1024,1024 --enable_bucket --min_bucket_reso 768 --max_bucket_reso 1280 \
  --network_module networks.lora --network_dim 16 --network_alpha 16 \
  --train_batch_size 1 --max_train_epochs 10 --save_every_n_epochs 2 \
  --learning_rate 1e-4 --unet_lr 1e-4 --text_encoder_lr 5e-5 \
  --optimizer_type AdamW8bit --lr_scheduler constant_with_warmup --lr_warmup_steps 50 \
  --mixed_precision bf16 --save_precision bf16 \
  --sdpa --gradient_checkpointing --cache_latents --cache_latents_to_disk \
  --no_half_vae --seed 42 \
  --output_dir "$WORK/out" --output_name ria_sdxl \
  && cp "$WORK/out/ria_sdxl"*.safetensors "$LORA_OUT/" \
  && echo "[sdxl] ria_sdxl 完成，LoRA 入库 $LORA_OUT/"
