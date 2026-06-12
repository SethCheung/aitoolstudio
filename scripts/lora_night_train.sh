#!/usr/bin/env bash
# 195 夜间 LoRA 无人值守训练（Qwen-Image 角色 LoRA / musubi-tuner）
#
# 任务投递方式：在 NAS 上建一个目录即可
#   /mnt/nas_comfyui/AI-Tool-Studio/comfyui/training/jobs/<任务名>/
#     dataset/         # 训练图 + 同名 .txt 打标文件
#     job.env          # 可选覆盖参数，如 EPOCHS=20 / NETWORK_DIM=32 / RESOLUTION=1328
#
# 状态标记（任务目录下）：.running / .done / .failed，日志在 train.log
# 产出 LoRA 写到 NAS models/loras/digital_humans/<任务名>.safetensors
#
# 部署：scp 到 195:~/lora_night_train.sh，crontab 加
#   30 23 * * * ~/lora_night_train.sh >> ~/lora_night_train.cron.log 2>&1
set -uo pipefail

NAS_ROOT=/mnt/nas_comfyui/AI-Tool-Studio/comfyui
JOBS_DIR=$NAS_ROOT/training/jobs
LORA_OUT_DIR=$NAS_ROOT/models/loras/digital_humans
MUSUBI=~/musubi-tuner
PY=~/musubi_env/bin/python
LOCAL_WORK=~/lora_work

DIT=$NAS_ROOT/models/diffusion_models/qwen_image_bf16.safetensors
VAE=$NAS_ROOT/models/vae/qwen_image_vae.safetensors
TE=$NAS_ROOT/models/text_encoders/qwen_2.5_vl_7b.safetensors

GPU_BUSY_MB=4000          # 显存占用超过此值视为 ComfyUI 在忙
DEADLINE_HOUR=6           # 早上 6 点后不再开新任务

# 进度推送（可选）：在 195 的 ~/.lora_notify.env 里配置，支持三种通道（可同时配多个）
#   TG_BOT_TOKEN=123456:ABC...     # Telegram 机器人 token（BotFather 创建）
#   TG_CHAT_ID=123456789           # 你与机器人的会话 chat_id
#   WEBHOOK_URL=https://...        # 企业微信/钉钉群机器人 webhook
#   WEBHOOK_STYLE=wecom            # wecom(企微/钉钉同格式) 或 feishu
[ -f ~/.lora_notify.env ] && . ~/.lora_notify.env

log() { echo "[$(date '+%F %T')] $*"; }

notify() {
  local msg="[LoRA夜训] $*"
  if [ -n "${TG_BOT_TOKEN:-}" ] && [ -n "${TG_CHAT_ID:-}" ]; then
    curl -s -m 15 "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
      --data-urlencode "chat_id=${TG_CHAT_ID}" \
      --data-urlencode "text=${msg}" >/dev/null 2>&1 || true
  fi
  if [ -n "${WEBHOOK_URL:-}" ]; then
    local payload
    if [ "${WEBHOOK_STYLE:-wecom}" = "feishu" ]; then
      payload=$(printf '{"msg_type":"text","content":{"text":"%s"}}' "$msg")
    else
      payload=$(printf '{"msgtype":"text","text":{"content":"%s"}}' "$msg")
    fi
    curl -s -m 15 -H 'Content-Type: application/json' -d "$payload" "$WEBHOOK_URL" >/dev/null 2>&1 || true
  fi
}

gpu_used_mb() {
  nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1
}

wait_for_idle_gpu() {
  while true; do
    used=$(gpu_used_mb)
    [ "$used" -lt "$GPU_BUSY_MB" ] && return 0
    hour=$(date +%H)
    if [ "$hour" -ge "$DEADLINE_HOUR" ] && [ "$hour" -lt 22 ]; then
      log "GPU 一直被占用且已过截止时间，今晚放弃"
      return 1
    fi
    log "GPU 占用 ${used}MiB，等待空闲..."
    sleep 300
  done
}

pick_job() {
  for d in "$JOBS_DIR"/*/; do
    [ -d "$d" ] || continue
    name=$(basename "$d")
    if [ -e "$d/.done" ] || [ -e "$d/.running" ] || [ -e "$d/.failed" ]; then continue; fi
    if [ ! -d "$d/dataset" ] && [ ! -f "$d/dataset.toml" ]; then continue; fi
    echo "$name"
    return 0
  done
  return 1
}

train_job() {
  local name=$1
  local job_dir=$JOBS_DIR/$name
  local work=$LOCAL_WORK/$name
  local logf=$job_dir/train.log

  # 默认参数，可被 job.env 覆盖
  NETWORK_DIM=16
  EPOCHS=16
  SAVE_EVERY=4
  LR=1e-4
  RESOLUTION=1024
  SWAP_BLOCKS=0
  SEED=42
  NUM_REPEATS=1
  [ -f "$job_dir/job.env" ] && . "$job_dir/job.env"

  touch "$job_dir/.running"
  mkdir -p "$work/cache" "$work/out" "$LORA_OUT_DIR"

  # 任务目录里自带 dataset.toml 时优先使用（精细配比/多数据块场景）
  if [ -f "$job_dir/dataset.toml" ]; then
    cp "$job_dir/dataset.toml" "$work/dataset.toml"
  else
  cat > "$work/dataset.toml" <<EOF
[general]
resolution = [$RESOLUTION, $RESOLUTION]
caption_extension = ".txt"
batch_size = 1
enable_bucket = true
bucket_no_upscale = false

[[datasets]]
image_directory = "$job_dir/dataset"
cache_directory = "$work/cache"
num_repeats = $NUM_REPEATS
EOF
  fi

  local swap_args=()
  [ "$SWAP_BLOCKS" -gt 0 ] && swap_args=(--blocks_to_swap "$SWAP_BLOCKS")

  {
    log "=== 任务 $name 开始 (dim=$NETWORK_DIM epochs=$EPOCHS lr=$LR res=$RESOLUTION) ==="
    cd "$MUSUBI" &&
    $PY src/musubi_tuner/qwen_image_cache_latents.py \
      --dataset_config "$work/dataset.toml" --vae "$VAE" &&
    $PY src/musubi_tuner/qwen_image_cache_text_encoder_outputs.py \
      --dataset_config "$work/dataset.toml" --text_encoder "$TE" --batch_size 4 &&
    $PY src/musubi_tuner/qwen_image_train_network.py \
      --dit "$DIT" --vae "$VAE" --text_encoder "$TE" \
      --dataset_config "$work/dataset.toml" \
      --sdpa --mixed_precision bf16 --fp8_base --fp8_scaled --fp8_vl \
      --timestep_sampling shift --discrete_flow_shift 2.2 \
      --optimizer_type adamw8bit --learning_rate "$LR" \
      --gradient_checkpointing "${swap_args[@]}" \
      --network_module networks.lora_qwen_image --network_dim "$NETWORK_DIM" \
      --max_train_epochs "$EPOCHS" --save_every_n_epochs "$SAVE_EVERY" \
      --seed "$SEED" \
      --output_dir "$work/out" --output_name "$name"
  } >> "$logf" 2>&1

  local rc=$?
  rm -f "$job_dir/.running"
  if [ $rc -eq 0 ] && ls "$work/out/$name"*.safetensors >/dev/null 2>&1; then
    cp "$work/out/$name"*.safetensors "$LORA_OUT_DIR/"
    touch "$job_dir/.done"
    log "任务 $name 完成，LoRA 已写入 $LORA_OUT_DIR/" | tee -a "$logf"
    notify "✅ $name 训练完成，LoRA 已入库 models/loras/digital_humans/"
  else
    touch "$job_dir/.failed"
    log "任务 $name 失败 (exit=$rc)，详见 $logf" | tee -a "$logf"
    notify "❌ $name 训练失败 (exit=$rc)，日志: training/jobs/$name/train.log"
  fi
  return $rc
}

main() {
  mkdir -p "$JOBS_DIR" "$LOCAL_WORK"
  if [ ! -f "$DIT" ]; then
    log "训练权重缺失: $DIT"
    exit 1
  fi
  while true; do
    name=$(pick_job) || { log "没有待训任务，退出"; break; }
    touch "$JOBS_DIR/$name/.running"   # 立刻认领，防止双机抢同一任务
    if ! wait_for_idle_gpu; then rm -f "$JOBS_DIR/$name/.running"; break; fi
    train_job "$name" || true
    hour=$(date +%H)
    if [ "$hour" -ge "$DEADLINE_HOUR" ] && [ "$hour" -lt 22 ]; then
      log "已过截止时间，剩余任务明晚继续"
      break
    fi
  done
}

main "$@"
