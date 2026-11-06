#!/usr/bin/env bash
# The determinism experiment's runs (proof-of-fix#125), stage by stage, exactly as reports/determinism-v1.md was made.
# Each stage starts its server (serve.sh), runs its calls (run.py, results/<tag>.jsonl), and stops the server.
#
#   campaign.sh vllm <d|bi>          one server: sequential repeats, batching with fillers, seeded sampling,
#                                    and (d only) the answer-shopping samples
#   campaign.sh vllm-nopc            the default mode with prefix caching off: repeats and batching
#   campaign.sh vllm-nonce           batch-invariant greedy, 20 check IDs (markers) per case
#   campaign.sh vllm-restart <d|bi> <n>   a fresh server: the cases once cold, once warm, and seeded once
#   campaign.sh llama-cpu <threads> <q8_0|q4_k_m> <reps> <cache on|off> [seeded reps] [case ids]
#   campaign.sh llama-cpu-seed <threads> <q8_0|q4_k_m> <reps> [case ids]   seeded sampling, cache off
#   campaign.sh llama-gpu <q8_0|q4_k_m> <reps> [seeded reps]   (cache on, then off)
#   campaign.sh all-after-vllm-d     every later stage, in the order the report used
set -euo pipefail
cd "$(dirname "$0")"
V=http://127.0.0.1:8000/v1
L=http://127.0.0.1:8080/v1
run() { python3 run.py "$@"; }

case "$1" in
  vllm)
    m=$2; if [ "$m" = bi ]; then ./serve.sh vllm bi; else ./serve.sh vllm; fi
    trap './serve.sh stop' EXIT
    run --base $V --engine vllm --tag vllm-$m-seq --setup "vllm $m" --reps $([ "$m" = bi ] && echo 5 || echo 10)
    run --base $V --engine vllm --tag vllm-$m-c8 --setup "vllm $m" --reps 3 --concurrency 8 --fillers 60 --shuffle-seed 8
    run --base $V --engine vllm --tag vllm-$m-c32 --setup "vllm $m" --reps 3 --concurrency 32 --fillers 120 \
      --shuffle-seed 32
    run --base $V --engine vllm --tag vllm-$m-seed-seq --setup "vllm $m" --sampling qwen --seed 1234 --reps 3
    run --base $V --engine vllm --tag vllm-$m-seed-c32 --setup "vllm $m" --sampling qwen --seed 1234 --reps 3 \
      --concurrency 32 --fillers 120 --shuffle-seed 132
    if [ "$m" = d ]; then
      # Answer shopping: the node's request as sent today (no sampling fields: the model's generation_config applies),
      # 20 independent calls per case, no seed.
      run --base $V --engine vllm --tag vllm-d-shop --setup "vllm d" --sampling server-default --reps 20 \
        --concurrency 16
      run --base $V --engine vllm --tag vllm-d-shop-t1 --setup "vllm d" --sampling t=1.0 --reps 20 --concurrency 16
    fi
    ;;
  vllm-nopc)
    # The default mode with prefix caching off: does a cold and a warm call then agree, and under batching?
    ./serve.sh vllm nopc
    trap './serve.sh stop' EXIT
    run --base $V --engine vllm --tag vllm-dnopc-seq --setup "vllm d, prefix caching off" --reps 5
    run --base $V --engine vllm --tag vllm-dnopc-c32 --setup "vllm d, prefix caching off" --reps 3 --concurrency 32 \
      --fillers 120 --shuffle-seed 32
    ;;
  vllm-nonce)
    # Greedy in batch-invariant mode, but each call with its own check ID, as a live check draws one: how often do
    # different untrusted-text markers alone change the verdict? (The markers are the only free part of the prompt.)
    ./serve.sh vllm bi
    trap './serve.sh stop' EXIT
    run --base $V --engine vllm --tag vllm-bi-nonce --setup "vllm bi, a new check ID per call" --vary-id --reps 20 \
      --concurrency 16
    ;;
  vllm-restart)
    m=$2; n=$3; if [ "$m" = bi ]; then ./serve.sh vllm bi; else ./serve.sh vllm; fi
    trap './serve.sh stop' EXIT
    run --base $V --engine vllm --tag vllm-$m-restart$n --setup "vllm $m, fresh process $n" --reps 2
    run --base $V --engine vllm --tag vllm-$m-restart$n-seed --setup "vllm $m, fresh process $n" --sampling qwen \
      --seed 1234 --reps 1
    ;;
  llama-cpu)
    # cache: on = llama-server's default (cache_prompt: reuse the KV cache of an earlier prompt's common prefix);
    # off = cache_prompt false in every request. seedreps: seeded-sampling repeats (cache off). ids: a subset.
    t=$2; q=$3; reps=$4; cache=$5; seedreps=${6:-0}; ids=${7:-}
    ./serve.sh llama-cpu "$t" "$q"
    trap './serve.sh stop' EXIT
    if [ "$cache" = on ]; then
      run --base $L --engine llama --tag llama-cpu-t$t-$q --setup "llama.cpp cpu t=$t $q" --reps "$reps" --ids "$ids"
    else
      run --base $L --engine llama --tag llama-cpu-t$t-$q-nocache --setup "llama.cpp cpu t=$t $q cache_prompt=false" \
        --reps "$reps" --ids "$ids" --extra '{"cache_prompt": false}'
    fi
    if [ "$seedreps" -gt 0 ]; then
      run --base $L --engine llama --tag llama-cpu-t$t-$q-seed --setup "llama.cpp cpu t=$t $q cache_prompt=false" \
        --sampling qwen --seed 1234 --reps "$seedreps" --ids "$ids" --extra '{"cache_prompt": false}'
    fi
    ;;
  llama-cpu-seed)
    # seeded sampling only (cache off): <threads> <quant> <reps> [case ids]
    t=$2; q=$3; reps=$4; ids=${5:-}
    ./serve.sh llama-cpu "$t" "$q"
    trap './serve.sh stop' EXIT
    run --base $L --engine llama --tag llama-cpu-t$t-$q-seed --setup "llama.cpp cpu t=$t $q cache_prompt=false" \
      --sampling qwen --seed 1234 --reps "$reps" --ids "$ids" --extra '{"cache_prompt": false}'
    ;;
  llama-gpu)
    q=$2; reps=$3; seedreps=${4:-0}
    ./serve.sh llama-gpu "$q"
    trap './serve.sh stop' EXIT
    run --base $L --engine llama --tag llama-gpu-$q --setup "llama.cpp cuda $q" --reps "$reps"
    run --base $L --engine llama --tag llama-gpu-$q-nocache --setup "llama.cpp cuda $q cache_prompt=false" \
      --reps "$reps" --extra '{"cache_prompt": false}'
    if [ "$seedreps" -gt 0 ]; then
      run --base $L --engine llama --tag llama-gpu-$q-seed --setup "llama.cpp cuda $q cache_prompt=false" \
        --sampling qwen --seed 1234 --reps "$seedreps" --extra '{"cache_prompt": false}'
    fi
    ;;
  all-after-vllm-d)
    # The order the report used, after `campaign.sh vllm d`. A first CPU stage at 16 threads was stopped after one
    # call: with the PC's other work (an editor's server, a test run) on 2 of the 16 logical CPUs, llama.cpp's 16
    # threads waited on each other and made 1.2 tokens a second (88 s for one call). 8 threads (one per core) became the
    # CPU reference, and 16 and 1 thread ran on subsets of the cases.
    T10=01-median-good,02-slugify-good,03-duration-good,04-pages-bad,05-backoff-bad,06-lru-bad,07-config-borderline
    T10=$T10,08-money-borderline,09-csv-borderline,10-urls-borderline
    T5=01-median-good,02-slugify-good,04-pages-bad,07-config-borderline,09-csv-borderline
    "$0" vllm-restart d 1
    "$0" vllm-restart d 2
    "$0" vllm-nopc
    "$0" vllm bi
    "$0" vllm-restart bi 1
    "$0" llama-gpu q8_0 3 2
    "$0" llama-gpu q4_k_m 1
    "$0" vllm-nonce
    "$0" llama-cpu 8 q8_0 2 off
    "$0" llama-cpu-seed 8 q8_0 2 "$T10"
    "$0" llama-cpu 8 q8_0 2 on 0 "$T10"
    "$0" llama-cpu 16 q8_0 1 off 0 "$T10"
    "$0" llama-cpu 8 q4_k_m 1 off
    "$0" llama-cpu 1 q8_0 1 off 0 "$T5"
    ;;
  *)
    sed -n 2,14p "$0"; exit 2 ;;
esac
