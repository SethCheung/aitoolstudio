#!/usr/bin/env bash
# Z-Image 角色 LoRA 一次性训练（写实底模，治油画感）。复用已锁定的数据集。
# 用法（在 195 上跑，需 musubi_env）：  ~/lora_train_zimage.sh <job名> <数据集目录>
#   例： ~/lora_train_zimage.sh ria_v4z /mnt/nas_comfyui/AI-Tool-Studio/comfyui/training/jobs/ria_v4/dataset_face
# 产出： NAS models/loras/digital_humans/<job名>*.safetensors
set -uo pipefail

NAME=${1:?need job name}
DATASET=${2:?need dataset dir}
NAS=/mnt/nas_comfyui/AI-Tool-Studio/comfyui
LORA_OUT=$NAS/models/loras/digital_humans
MUSUBI=~/musubi-tuner
PY=~/musubi_env/bin/python
WORK=~/lora_work/$NAME

DIT=$NAS/models/diffusion_models/z_image_turbo_bf16.safetensors
VAE=$NAS/models/vae/ae.safetensors
TE=$NAS/models/text_encoders/qwen_3_4b.safetensors

DIM=${DIM:-16}
ALPHA=${ALPHA:-16}
EPOCHS=${EPOCHS:-10}
SAVE_EVERY=${SAVE_EVERY:-2}
LR=${LR:-1e-4}
REPEATS=${REPEATS:-6}
FLOW_SHIFT=${FLOW_SHIFT:-3.0}
RES=${RES:-1024}

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

echo "[zimage] === $NAME 开始 (dim=$DIM alpha=$ALPHA epochs=$EPOCHS shift=$FLOW_SHIFT) ==="
cd "$MUSUBI" || exit 1
$PY src/musubi_tuner/zimage_cache_latents.py \
  --dataset_config "$WORK/dataset.toml" --vae "$VAE" || exit 1
$PY src/musubi_tuner/zimage_cache_text_encoder_outputs.py \
  --dataset_config "$WORK/dataset.toml" --text_encoder "$TE" --batch_size 4 || exit 1
$PY src/musubi_tuner/zimage_train_network.py \
  --dit "$DIT" --vae "$VAE" --text_encoder "$TE" \
  --dataset_config "$WORK/dataset.toml" \
  --sdpa --mixed_precision bf16 --fp8_base --fp8_scaled \
  --timestep_sampling shift --discrete_flow_shift "$FLOW_SHIFT" \
  --optimizer_type adamw8bit --learning_rate "$LR" \
  --gradient_checkpointing \
  --network_module networks.lora_zimage --network_dim "$DIM" --network_alpha "$ALPHA" \
  --max_train_epochs "$EPOCHS" --save_every_n_epochs "$SAVE_EVERY" \
  --seed 42 --output_dir "$WORK/out" --output_name "$NAME" || exit 1

cp "$WORK/out/$NAME"*.safetensors "$LORA_OUT/" && \
  echo "[zimage] $NAME 完成，LoRA 入库 $LORA_OUT/"
