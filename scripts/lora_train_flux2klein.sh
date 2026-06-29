#!/usr/bin/env bash
# FLUX.2-klein-9B 角色 LoRA 训练（musubi）。用小 Qwen3-4B TE（避开 dev 的 24B Mistral，
# 后者 ~48GB 装不进 195 的 32G 内存）。复用 ria 锁定数据集。
# 用法（195，musubi_env）：  ~/lora_train_flux2klein.sh
# 产出： NAS models/loras/digital_humans/ria_flux2k*.safetensors
set -uo pipefail

NAS=/mnt/nas_comfyui/AI-Tool-Studio/comfyui
MUSUBI=~/musubi-tuner
PY=~/musubi_env/bin/python
WORK=~/lora_work/ria_flux2k
LORA_OUT=$NAS/models/loras/digital_humans
DATASET=$NAS/training/jobs/ria_v4/dataset_face

DIT=$NAS/models/diffusion_models/flux-2-klein-base-9b.safetensors
VAE=$NAS/models/vae/flux2-vae.safetensors
TE=$NAS/models/text_encoders/qwen_3_4b.safetensors
MODEL_VER=klein-base-9b

DIM=${DIM:-16}; ALPHA=${ALPHA:-16}; EPOCHS=${EPOCHS:-10}; SAVE_EVERY=${SAVE_EVERY:-2}
LR=${LR:-1e-4}; REPEATS=${REPEATS:-6}; RES=${RES:-1024}; SWAP=${SWAP:-20}

mkdir -p "$WORK/cache" "$WORK/out" "$LORA_OUT"
cat > "$WORK/dataset.toml" <<EOF
[general]
resolution = [$RES, $RES]
caption_extension = ".txt"
batch_size = 1
enable_bucket = true
bucket_no_upscale = false

[[datasets]]
image_directory = "$DATASET"
cache_directory = "$WORK/cache"
num_repeats = $REPEATS
EOF

echo "[flux2k] === ria_flux2k 开始 (dim=$DIM alpha=$ALPHA epochs=$EPOCHS swap=$SWAP) ==="
cd "$MUSUBI" || exit 1
$PY src/musubi_tuner/flux_2_cache_latents.py \
  --dataset_config "$WORK/dataset.toml" --vae "$VAE" --model_version "$MODEL_VER" || exit 1
$PY src/musubi_tuner/flux_2_cache_text_encoder_outputs.py \
  --dataset_config "$WORK/dataset.toml" --text_encoder "$TE" --model_version "$MODEL_VER" --batch_size 4 || exit 1
$PY src/musubi_tuner/flux_2_train_network.py \
  --dit "$DIT" --vae "$VAE" --text_encoder "$TE" --model_version "$MODEL_VER" \
  --dataset_config "$WORK/dataset.toml" \
  --sdpa --mixed_precision bf16 --fp8_base --fp8_scaled \
  --timestep_sampling flux2_shift --weighting_scheme none \
  --optimizer_type adamw8bit --learning_rate "$LR" \
  --gradient_checkpointing --blocks_to_swap "$SWAP" \
  --network_module networks.lora_flux_2 --network_dim "$DIM" --network_alpha "$ALPHA" \
  --max_train_epochs "$EPOCHS" --save_every_n_epochs "$SAVE_EVERY" \
  --seed 42 --output_dir "$WORK/out" --output_name ria_flux2k || exit 1

cp "$WORK/out/ria_flux2k"*.safetensors "$LORA_OUT/" && \
  echo "[flux2k] ria_flux2k 完成，LoRA 入库 $LORA_OUT/"
