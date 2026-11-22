#!/usr/bin/env bash
# Records every version the determinism experiment ran on (proof-of-fix#125) into results/versions.txt.
set -uo pipefail
cd "$(dirname "$0")"
ENV_DIR=${ENV_DIR:-$HOME/pof-125-env}
MODELS=${MODELS:-$HOME/models}
{
  echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "== machine"
  nvidia-smi --query-gpu=name,driver_version,compute_cap,memory.total --format=csv,noheader
  nvidia-smi | grep -o "CUDA UMD Version: [0-9.]*"
  grep -m1 "model name" /proc/cpuinfo
  echo "logical CPUs: $(nproc)"
  echo "kernel: $(uname -r)"
  free -g | sed -n 2p
  echo "== vLLM environment ($ENV_DIR/vllm)"
  "$ENV_DIR/vllm/bin/python" -I - <<'EOF'
import importlib.metadata as md, platform, torch
print("python", platform.python_version())
for p in ("vllm", "torch", "triton", "flashinfer-python", "transformers", "xgrammar", "nvidia-cublas", "nvidia-cuda-runtime",
          "nvidia-cudnn-cu13", "nvidia-nccl-cu13"):
    try:
        print(p, md.version(p))
    except md.PackageNotFoundError:
        pass
print("torch CUDA runtime", torch.version.cuda, "cuDNN", torch.backends.cudnn.version())
print("device", torch.cuda.get_device_name(0), "capability", torch.cuda.get_device_capability(0))
EOF
  echo "== llama.cpp"
  echo "source: $(git -C "$ENV_DIR/llama.cpp-src" describe --tags 2>/dev/null) $(git -C "$ENV_DIR/llama.cpp-src" rev-parse HEAD)"
  "$ENV_DIR/llama-cpu/bin/llama-server" --version 2>&1 | tail -2
  grep -E "^(GGML_NATIVE|GGML_CUDA|CMAKE_BUILD_TYPE|CMAKE_CUDA_ARCHITECTURES|GGML_AVX512)[^_]*:" \
    "$ENV_DIR/llama-cpu/CMakeCache.txt" | sed 's/^/cpu build: /'
  grep -E "^(GGML_NATIVE|GGML_CUDA|CMAKE_BUILD_TYPE|CMAKE_CUDA_ARCHITECTURES)[^_]*:" \
    "$ENV_DIR/llama-cuda/CMakeCache.txt" | sed 's/^/cuda build: /'
  "$ENV_DIR/cuda/bin/nvcc" --version | tail -1 | sed 's/^/nvcc (conda-forge, for the llama.cpp CUDA build): /'
  ls "$ENV_DIR/cuda/lib/" | grep -E "^libcublas\.so\.[0-9.]+$|^libcudart\.so\.[0-9.]+$" | sed 's/^/runtime lib: /'
  echo "== weights"
  echo "Qwen/Qwen2.5-7B-Instruct revision a09a35458c702b33eeacc393d103063234e8bc28 (bf16 safetensors)"
  echo "Qwen/Qwen2.5-7B-Instruct-GGUF revision bb5d59e06d9551d752d08b292a50eb208b07ab1f"
  cat "$ENV_DIR/weights.sha256"
  echo "== disk"
  for d in "$MODELS"/Qwen2.5-7B-Instruct "$MODELS"/Qwen2.5-7B-Instruct-GGUF "$ENV_DIR"/vllm "$ENV_DIR"/cuda \
    "$ENV_DIR"/llama.cpp-src "$ENV_DIR"/llama-cpu "$ENV_DIR"/llama-cuda "$ENV_DIR"; do
    du -sh "$d" 2>/dev/null  # one at a time: du counts a directory once per call
  done
} > results/versions.txt 2>&1
cat results/versions.txt
