#!/bin/bash
#SBATCH --job-name=sentinel_inference
#SBATCH --partition=public
#SBATCH --qos=class
#SBATCH --constraint=class
#SBATCH --gpus=a100:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --time=00:20:00

set -euo pipefail
umask 077
: "${SENTINEL_MODEL_PATH:?Set an already cached model snapshot}"
SENTINEL_SIF=/packages/apps/simg/vllm-cu129-nightly-0426.sif
SENTINEL_PORT=${SENTINEL_PORT:-8767}
export APPTAINERENV_HF_HUB_OFFLINE=1
export APPTAINERENV_TRANSFORMERS_OFFLINE=1
export APPTAINERENV_VLLM_NO_USAGE_STATS=1
export APPTAINERENV_VLLM_DO_NOT_TRACK=1
printf 'SENTINEL_NODE=%s\nSENTINEL_JOB=%s\n' "$(hostname)" "${SLURM_JOB_ID}"
sha256sum "$SENTINEL_SIF"
sha256sum "$SENTINEL_MODEL_PATH/config.json"
# Loopback only: access requires a user-owned SSH forward to this allocation.
# No candidate code, agent workspace, policy service or protected fixture runs on Sol.
exec apptainer run --nv --bind /scratch "$SENTINEL_SIF" \
  --model "$SENTINEL_MODEL_PATH" --served-model-name sentinel-qwen-coder \
  --host 127.0.0.1 --port "$SENTINEL_PORT" --max-model-len 8192 \
  --max-num-seqs 1 --gpu-memory-utilization 0.35 --enforce-eager
