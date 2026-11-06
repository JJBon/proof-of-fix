#!/usr/bin/env bash
# Starts and stops the model servers for the determinism experiment (proof-of-fix#125), on 127.0.0.1 only.
# Everything lives outside the repository: the environments under $ENV_DIR, the weights under $MODELS.
#
#   serve.sh vllm [bi] [nopc]     vLLM, bf16, port 8000 (bi: VLLM_BATCH_INVARIANT=1; nopc: prefix caching off)
#   serve.sh llama-cpu <threads> <q8_0|q4_k_m> [extra llama-server flags...]   CPU-only build, port 8080
#   serve.sh llama-gpu <q8_0|q4_k_m> [extra flags...]                          CUDA build, all layers on the GPU
#   serve.sh stop                 stops whatever this script started, and waits for the GPU to be free
set -euo pipefail

ENV_DIR=${ENV_DIR:-$HOME/pof-125-env}
MODELS=${MODELS:-$HOME/models}
RUN=$ENV_DIR/run
LOGS=$ENV_DIR/logs
mkdir -p "$RUN" "$LOGS"
HF_MODEL=$MODELS/Qwen2.5-7B-Instruct
GGUF_DIR=$MODELS/Qwen2.5-7B-Instruct-GGUF

wait_ready() {  # url, pid, log
  for _ in $(seq 1 600); do
    if curl -sf "$1" >/dev/null 2>&1; then return 0; fi
    if ! kill -0 "$2" 2>/dev/null; then echo "server exited; see $3" >&2; tail -30 "$3" >&2; return 1; fi
    sleep 1
  done
  echo "server not ready after 600 s; see $3" >&2
  return 1
}

gguf() {
  case "$1" in
    q8_0) echo "$GGUF_DIR/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf" ;;
    q4_k_m) echo "$GGUF_DIR/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf" ;;
    *) echo "unknown quant $1" >&2; exit 2 ;;
  esac
}

case "${1:-}" in
  vllm)
    bi=0; pc=--enable-prefix-caching
    for opt in "${@:2}"; do
      case "$opt" in bi) bi=1 ;; nopc) pc=--disable-prefix-caching ;; *) echo "unknown option $opt" >&2; exit 2 ;; esac
    done
    log=$LOGS/vllm-$(date +%Y%m%dT%H%M%S)-bi$bi$pc.log
    # VLLM_USE_FLASHINFER_SAMPLER=0: FlashInfer's sampler JIT-compiles with nvcc at startup, and this machine has no
    # CUDA toolkit for it (nor its prebuilt kernels); vLLM's own sampler is used instead. Greedy and seeded requests
    # never use FlashInfer's sampler anyway (vllm/v1/worker/gpu/sample/sampler.py).
    VLLM_BATCH_INVARIANT=$bi VLLM_USE_FLASHINFER_SAMPLER=0 HF_HUB_OFFLINE=1 VLLM_NO_USAGE_STATS=1 DO_NOT_TRACK=1 \
      nohup "$ENV_DIR/vllm/bin/vllm" serve "$HF_MODEL" --served-model-name qwen2.5-7b-instruct \
      --host 127.0.0.1 --port 8000 --dtype bfloat16 --max-model-len 8192 --gpu-memory-utilization 0.85 \
      --max-num-seqs 64 $pc >"$log" 2>&1 &
    echo $! >"$RUN/server.pid"
    wait_ready http://127.0.0.1:8000/v1/models $! "$log"
    echo "vLLM ready (batch invariant: $bi, $pc), log $log"
    ;;
  llama-cpu)
    threads=$2; quant=$3; shift 3
    log=$LOGS/llama-cpu-$(date +%Y%m%dT%H%M%S)-t$threads-$quant.log
    nohup "$ENV_DIR/llama-cpu/bin/llama-server" -m "$(gguf "$quant")" --host 127.0.0.1 --port 8080 \
      -t "$threads" -tb "$threads" -c 8192 -np 1 --alias qwen2.5-7b-instruct "$@" >"$log" 2>&1 &
    echo $! >"$RUN/server.pid"
    wait_ready http://127.0.0.1:8080/v1/models $! "$log"
    echo "llama-server (CPU, $threads threads, $quant) ready, log $log"
    ;;
  llama-gpu)
    quant=$2; shift 2
    log=$LOGS/llama-gpu-$(date +%Y%m%dT%H%M%S)-$quant.log
    LD_LIBRARY_PATH=$ENV_DIR/cuda/lib:${LD_LIBRARY_PATH:-} nohup "$ENV_DIR/llama-cuda/bin/llama-server" \
      -m "$(gguf "$quant")" --host 127.0.0.1 --port 8080 -ngl 99 -c 8192 -np 1 --alias qwen2.5-7b-instruct \
      "$@" >"$log" 2>&1 &
    echo $! >"$RUN/server.pid"
    wait_ready http://127.0.0.1:8080/v1/models $! "$log"
    echo "llama-server (CUDA, $quant) ready, log $log"
    ;;
  stop)
    if [ -f "$RUN/server.pid" ]; then
      pid=$(cat "$RUN/server.pid")
      kill "$pid" 2>/dev/null || true
      for _ in $(seq 1 60); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
      kill -9 "$pid" 2>/dev/null || true
      rm -f "$RUN/server.pid"
    fi
    pkill -u "$USER" -f "$ENV_DIR/vllm/bin/" 2>/dev/null || true  # vLLM's engine core child, if it outlived its parent
    for _ in $(seq 1 30); do
      pgrep -u "$USER" -f "VLLM::EngineCore|$ENV_DIR/(vllm|llama-cpu|llama-cuda)/" >/dev/null || break
      sleep 1
    done
    echo "stopped"
    ;;
  *)
    sed -n 2,9p "$0"; exit 2 ;;
esac
