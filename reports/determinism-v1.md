# Determinism, v1: can anyone re-run an open-weight judge and get the same answer? (proof-of-fix#125; 2026-11-03)

> **Issue #125's experiment**, for v3's level C (design D10, D13 and D14 of `openspec/changes/proof-of-fix-132-open-validators`). One open-weight model, two engines, the owner's own PC, 30 judge cases through the node's real judge path. Every number below comes from a run on 2026-11-03; the commands are in [Reproduce](#reproduce). Findings are for the owner and for #138's receipt; nothing in the protocol changes here.

## The answer

### Within one setup: yes in vLLM's batch-invariant mode; otherwise only if the server's history repeats
- **vLLM with `VLLM_BATCH_INVARIANT=1` gave the same tokens on every call: 600 of 600.** That covers greedy and seeded sampling; one request at a time, 8 and 32 in flight among filler requests; the prefix cache cold and warm; and a fresh process.
  - The price: 2.5 times the GPU time. 4.3 s a call alone against 1.7 s; 0.42 s against 0.17 s a call at 16 in flight.
- **vLLM's default mode is not reproducible token for token.** An answer depends on the server's history and on its other traffic:
  - **The prefix cache:** a case's first call and its later calls differ in 13 of 30 cases. Only 183 of 300 sequential calls match the case's first call.
  - **Batching:** with 32 requests in flight, 60 of 90 calls match the same call made alone (67 of 90 with 8 in flight). With the prefix cache off, repeats one at a time match (150 of 150), but batching still changes 48 of 90.
  - **The same history replays exactly.** Two fresh processes given the same requests in the same order matched each other on every call, greedy and seeded, and matched the first run's greedy calls (60 of 60 cold, 60 of 60 warm). Their seeded calls didn't match the first run's (48 of 60), which had come after batched rounds.
  - **Verdicts mostly survive:** 1 of 90 calls at 32 in flight changed its verdict, and 1 case of 30 in each restart's seeded calls.
- **llama.cpp is reproducible on one machine if its prompt cache is off** (`cache_prompt: false` in each request). On the GPU, 90 of 90 repeats matched; on the CPU (8 threads), 60 of 60. **The CPU thread count is part of the setup:** 16 threads matched 8 threads in only 8 of 10 cases (1 thread matched in 5 of 5), with the same verdicts. With its default prompt cache on, only 57 of 90 GPU calls matched with Q8_0, and 12 of 30 with Q4_K_M, where one verdict flipped. llama-server's own documentation warns of this.

### Across setups: the tokens differ, and the verdict usually survives, but not always
- **vLLM batch-invariant against vLLM default** (same weights, same GPU): 19 of 30 answers identical, 30 of 30 verdicts identical.
- **vLLM bf16 against llama.cpp's Q8_0 on the GPU:** 2 of 30 answers identical, **25 of 30 verdicts identical**. 3 cases changed the model's opinion (all bad fixes, in both directions); 2 more lost their verdict to broken JSON.
- **llama.cpp on the CPU against CUDA, the same Q8_0 file:** 19 of 30 answers identical, 29 of 30 verdicts identical (one bad fix changed opinion).
- **Q8_0 against Q4_K_M:** 1 of 30 answers identical, 25–26 of 30 verdicts identical.
- **So a re-run proves something only on the same engine, build, weights, quantization, flags and (until a cross-GPU run says otherwise) GPU type.** Different setups disagreed on up to 5 of 30 verdicts, and up to 3 of 30 opinions. That is honest disagreement, not proof of a false verdict.

### What a receipt must pin for a re-run to be provable
1. **The exact prompt, rebuildable by anyone.** Today the node draws the check ID at random (`oracle/judge.py`, `case_for`), and the ID sets the untrusted-text markers. A different ID alone changed the verdict of 3 bad fixes in 13–15 of 20 tries (below). The ID must come from public data the validator can't choose, for example the panel's seed, and the receipt must name it with the prompt's version.
2. **The weights:** repository, revision, every file's sha256, dtype or quantization (bf16, Q8_0), and so the tokenizer and chat template.
3. **The engine:** name, version and build (vLLM's wheel with its torch, Triton and CUDA runtime; llama.cpp's commit, backend and build flags).
4. **The flags that change the numbers:** `VLLM_BATCH_INVARIANT=1` (required with vLLM), the attention backend, llama.cpp's `cache_prompt: false` and its CPU thread count, and the server's own defaults never left implicit.
5. **The sampling:** `temperature 0` (greedy), or every sampling field plus a seed derived from the chain, never chosen by the validator. Also the answer's token cap.
6. **The hardware class:** at least the GPU model, or compute capability (vLLM's batch-invariant mode runs different kernels on 8.x than on 9.x and 10.x), and the CPU's instruction set for a CPU engine. Whether two different GPUs agree is not measured here.
7. **The answer's tokens** (or their hash), not only the text's hash, and the verdict.

### Answer shopping: a weak judge, but little room per case
- **The node's request today sends no sampling fields,** so the server's defaults apply. For this model vLLM takes them from its `generation_config.json`: temperature 0.7, top_p 0.8, top_k 20, repetition penalty 1.05. Every call is a fresh random draw that nobody can re-run.
- **Measured with that request, 20 independent calls per case:**
  - an honest call passes a **borderline** fix **173 of 200 times (86 %)**, and a clearly **bad** one **77 of 200 times (38 %)**;
  - the simulation assumed 3 in 10 (and 1 in 10). This 7B model is a weak judge: even greedy, it passes 9 of 10 borderline fixes and 3 of 10 bad ones, two of them with failing tests.
- **But the room to shop is small,** because a case's pass rate is nearly all or nothing. 6 borderline cases always pass, 1 never does, 3 pass 17–19 times in 20.
  - **A shopper with 5 calls gains +3.5 points on borderline fixes and +10.7 on bad ones** over one honest call (+8.3 and +14.6 at temperature 1.0).
  - The simulation's 3-in-10 assumption gives a shopper +53 points; its 1-in-10 assumption +31 points, and at 1 in 10 shopping already didn't pay (−$2 ± 14). **The measured room is below both.**
- **Greedy decoding removes sampling as a knob, but not the check ID.** In batch-invariant mode with greedy decoding, 20 different check IDs per case still changed verdicts. Bad fixes passed **101 of 200 times (50 %)**. Three bad fixes that fail with the canonical ID passed with 13, 14 and 15 of 20 others. **Choosing among 5 IDs gains +11.7 points on bad fixes**, as much as sampling does.

### What it means for level C and #138
- **A "re-executable" proof level is possible on one hardware class.** Pin the 7 items above, and a re-run on the same GPU type, engine build and flags gives the same tokens, at every load tried (up to 32 requests in flight). A different answer is then a provable false verdict, not noise.
- **That also closes answer shopping at level C.** With greedy decoding and a check ID from the chain, each check has exactly one valid answer. A shopped answer fails an audit's re-run (D13), so it becomes a slashable fault instead of an undetectable one. Auditors then need the same hardware class.
- **The node must change before that (#139):**
  - the `openai` provider must send the pinned sampling fields (today it sends none);
  - the check ID must come from the chain;
  - the receipt (`oracle/receipt.py`, today the prompt's and answer's hashes, the model ID and the provider's host) must carry items 1–7.
- **#138's receipt format** needs fields for: the check ID and prompt version; the weights' revision and hashes; the quantization; the engine, version, build and flags; the sampling fields and seed; the hardware class; and the token count and hash.
- **Two costs:** batch-invariant mode takes 2.5 times the GPU time; and a level C validator must run exactly the pinned build, so a version bump is a coordinated change (an ADR), like an image digest.
- **What a paid cross-GPU rental would still need to answer:** whether the same vLLM build in batch-invariant mode gives the same tokens on other GPUs. For example, a second RTX 4090 (same type, another machine), an L4 or A10 (other 8.x chips), and an H100 (9.0, where vLLM uses cuBLAS instead of Triton for these matmuls). Also whether driver and CUDA runtime versions matter. If only the same GPU type agrees, the receipt must pin the GPU type and auditors must hold one; if 8.x chips agree, pinning the compute capability is enough.
- **Determinism doesn't make a judge good.** This model passes most borderline fixes on every call. D14's scores, not re-runs, deal with that.

## What was run

### The machine
- The owner's PC: NVIDIA GeForce RTX 4090 (24 GB, compute capability 8.9, driver 617.14), AMD Ryzen 7 9800X3D (8 cores, 16 threads), WSL2 Ubuntu 24.04 (kernel 5.15.167.4-microsoft-standard-WSL2), 22 GB of RAM in WSL.
- Every server listened on 127.0.0.1 only. Nothing outside was used but downloads: Hugging Face weights, PyPI wheels, the llama.cpp source, and conda-forge's CUDA compiler. No account, no token, nothing paid.

### The model
- **Qwen2.5-7B-Instruct** (Apache-2.0, ungated).
  - **GPU, bf16:** `Qwen/Qwen2.5-7B-Instruct` at revision `a09a35458c702b33eeacc393d103063234e8bc28`.
  - **GGUF:** `Qwen/Qwen2.5-7B-Instruct-GGUF` at revision `bb5d59e06d9551d752d08b292a50eb208b07ab1f`: the official Q8_0 (3 files) and Q4_K_M (2 files).
  - Every file's sha256 matches Hugging Face's own LFS hash. The hashes are in `experiments/determinism/results/versions.txt`.

### The engines
| Engine | Version | Settings |
|---|---|---|
| vLLM ("default") | 0.33.0 (pip wheel); torch 2.14.0+cu130, triton 3.8.0, CUDA runtime 13.0.96, cuBLAS 13.1.1.3, Python 3.12.12 | bf16, `--max-model-len 8192 --gpu-memory-utilization 0.85 --max-num-seqs 64`. FLASH_ATTN attention, CUDA graphs, torch.compile, chunked prefill and prefix caching on (all defaults). Prefix caching off only where a row says so. |
| vLLM, batch invariant ("BI") | the same, with `VLLM_BATCH_INVARIANT=1` | The installed version's own mode (`vllm/model_executor/determinism/batch_invariant.py`). On compute capability 8.x it replaces cuBLAS matmuls with Triton persistent kernels, and uses batch-invariant softmax, mean, RMS norm and attention. vLLM warns that sampling without a seed isn't batch invariant. |
| llama.cpp, CPU | release b12070 (commit `00f113eceb2758158582d56f98bf476b2fe3ed32`), built from source with GCC 13.3, `GGML_NATIVE=ON` (AVX-512 on Zen 5), no GPU backend | `llama-server -t N -tb N -c 8192 -np 1`: one slot, so requests are never batched together. |
| llama.cpp, CUDA | the same commit, `GGML_CUDA=ON`, `CMAKE_CUDA_ARCHITECTURES=89`, nvcc 13.0.88 and cuBLAS 13.1.1.3 from conda-forge (no system CUDA toolkit) | `-ngl 99` (every layer on the GPU), `-np 1`. Built in about 4 minutes. |

- **One vLLM flag was forced:** `VLLM_USE_FLASHINFER_SAMPLER=0`. The wheel's default sampler (FlashInfer's) compiles itself with nvcc at startup, and this machine has no CUDA toolkit for it, so vLLM wouldn't start. A home validator installing vLLM with pip hits the same failure. vLLM's own sampler is used instead. Greedy and seeded requests never use FlashInfer's sampler anyway (`vllm/v1/worker/gpu/sample/sampler.py`).

### The cases
- **30 judge cases** in `experiments/determinism/cases/`, written by `build_cases.py`: 10 issues in a made-up library (`local/sample`), each with a clearly good fix, a clearly bad one and a borderline one. No third-party code.
  - **The issues:** the first is the e2e demo's own (`bot/sample/stats.py` and `bot/fixes/`). The other 9 are in the same style: slugify, durations, pagination, backoff, an LRU cache, config parsing, money rounding, CSV fields and URL joining.
  - **Good:** fixes the issue as asked.
  - **Bad:** wrong. 8 fail the tests; 2 pass only by special-casing the acceptance test's inputs.
  - **Borderline:** the tests pass, but the fix is partial (3), has a side effect (5), or only looks like a fix (2: two accented letters special-cased, an epsilon hack). Each borderline case's `note` says what's wrong.
  - **Each test run is real:** the library's tests plus the issue's acceptance test, run with `python -m unittest` (locally, not in the node's sandbox; the prompt's test line says so).
- **The prompts are the node's.** `run.py` sends every case through `oracle.judge.DirectJudge` (so `build_prompt`) and `oracle.models.Client` with the `openai` provider, pointed at the local server. It reads the verdict with `pof.judges.prompt.parse`. Prompts are 782–1,110 tokens long, answers 66–213. All 3,925 case calls stopped on their own; none reached the 1,024-token cap.
- **The only addition is the sampling fields.** Today's provider sends none (see [What the node sends today](#what-the-node-sends-today)). `run.py` pins them per run:
  - **greedy:** `temperature 0, repetition_penalty 1.0`, on both engines, so vLLM and llama.cpp compute the same thing;
  - **seeded:** Qwen's recommended `temperature 0.7, top_p 0.8, top_k 20, repetition_penalty 1.05`, plus `seed 1234`; llama.cpp's `min_p` is set to 0 to match vLLM.
- **What "identical" means.** vLLM returns the generated token IDs (`return_token_ids`), so "token-identical" compares the IDs. llama-server's OpenAI endpoint doesn't, so there it compares the answer's bytes.
- **What a "verdict" is:** the node's. `solves` from the parser; an answer that doesn't parse is **invalid**, which the node counts as "doesn't solve".
- **Batching with fillers.** For 8 or 32 requests in flight, the 30 cases are shuffled among filler requests (`run.py --fillers`, 2 fillers per case at 8 in flight and 4 at 32). Half the fillers are other cases' judge prompts under another check ID (no shared prefix past the first ~100 tokens). Half are short free-text requests of 20–300 words. All are sampled without a seed, so their lengths vary. Each round uses a different shuffle.

## What the node sends today
- `oracle/models.py`'s `OpenAI` provider sends the model, the token cap and the two messages: **no temperature, no seed, no other sampling field.** The server's defaults apply.
- vLLM's default (`--generation-config auto`) is the model's own `generation_config.json`. Its startup log says so: `Default vLLM sampling parameters have been overridden by the model's generation_config.json: {'repetition_penalty': 1.05, 'temperature': 0.7, 'top_k': 20, 'top_p': 0.8}`. llama-server's defaults are temperature 0.8, top_k 40, top_p 0.95, min_p 0.05.
- So today every direct call to an open-weight server is a random draw, and the answer-shopping rows below use exactly that request (`--sampling server-default`).

## Results
Each table counts calls or cases from `experiments/determinism/results/` (`python3 experiments/determinism/analyze.py` prints them all). "Identical" is token-identical for vLLM and byte-identical for llama.cpp. A verdict "flip" is any change between pass, fail and invalid.

### 1. Repeats: the same setup, one call at a time
| Setup | Calls | Calls identical to the case's first call | Verdicts identical | Note |
|---|---|---|---|---|
| vLLM default, greedy, 10 repeats | 300 | 183 of 300 (17 of 30 cases always) | 300 of 300 | the first call runs with a colder prefix cache |
| the same, the 2nd–10th repeats against the 2nd | 270 | **270 of 270** | 270 of 270 | once warm, stable |
| vLLM default, prefix caching off, 5 repeats | 150 | **150 of 150** | 150 of 150 | |
| vLLM default, seeded (0.7, seed 1234), 3 repeats | 90 | **90 of 90** | 90 of 90 | all warm |
| vLLM batch-invariant, greedy, 5 repeats | 150 | **150 of 150** | 150 of 150 | cold and warm alike |
| vLLM batch-invariant, seeded, 3 repeats | 90 | **90 of 90** | 90 of 90 | |
| llama.cpp CUDA Q8_0, greedy, cache off, 3 repeats | 90 | **90 of 90** | 90 of 90 | |
| llama.cpp CUDA Q8_0, greedy, cache on (the default), 3 repeats | 90 | 57 of 90 against the cache-off answer (16 of 30 cases always) | 90 of 90 | |
| llama.cpp CUDA Q4_K_M, greedy, cache on, 1 run | 30 | 12 of 30 against the cache-off answer | 29 of 30 | `03-duration-bad` flipped |
| llama.cpp CUDA Q8_0, seeded, cache off, 2 repeats | 60 | **60 of 60** | 60 of 60 | |
| llama.cpp CPU Q8_0, 8 threads, greedy, cache off, 2 repeats | 60 | **60 of 60** | 60 of 60 | |
| llama.cpp CPU Q8_0, 8 threads, greedy, cache on, 10 cases, 2 repeats | 20 | 19 of 20 against the cache-off answer | 20 of 20 | |
| llama.cpp CPU Q8_0, 8 threads, seeded, cache off, 10 cases, 2 repeats | 20 | **20 of 20** | 20 of 20 | |

- **Why vLLM's first call differs (the likely reason):** with prefix caching on, even a case's first call reuses the cached start of the system prompt, which every case shares up to its markers (about 100 tokens). The rest is computed in a different-sized batch than in a full prefill, and the matmuls round differently. Consistent with that, the first call with caching on matched the call with caching off in only 12 of 30 cases. A later call reuses almost the whole prompt, so it differs again, and then stays the same.

### 2. Batching: the same prompts among other requests (vLLM)
| Setup | Calls | Identical to the same call alone | Verdicts identical | Verdict flips |
|---|---|---|---|---|
| default, 8 in flight (60 fillers a round, 3 rounds) | 90 | 67 of 90 | 90 of 90 | none |
| default, 32 in flight (120 fillers a round, 3 rounds) | 90 | 60 of 90 | 89 of 90 | `07-config-borderline`: a valid "solves: true" became unparseable JSON |
| default, prefix caching off, 32 in flight | 90 | 42 of 90 | 90 of 90 | none |
| default, seeded, 32 in flight | 90 | 66 of 90 | 90 of 90 | none |
| **batch-invariant, 8 in flight** | 90 | **90 of 90** | 90 of 90 | none |
| **batch-invariant, 32 in flight** | 90 | **90 of 90** | 90 of 90 | none |
| **batch-invariant, seeded, 32 in flight** | 90 | **90 of 90** | 90 of 90 | none |

- "The same call alone" is the warm sequential call for the default mode (the batched rounds ran on a warm server), and the first call for batch-invariant mode (where cold and warm agree).
- llama-server ran with one slot (`-np 1`), so its requests were never batched together; its batching wasn't measured.

### 3. Restarts: a fresh process (vLLM)
| Setup | Calls | Identical | Verdicts identical |
|---|---|---|---|
| default, 2 fresh processes, cold calls against the first run's cold calls | 60 | **60 of 60** | 60 of 60 |
| default, 2 fresh processes, warm calls against the first run's warm calls | 60 | **60 of 60** | 60 of 60 |
| default, seeded, fresh process against the first run | 60 | 48 of 60 | 58 of 60 (`10-urls-bad` in both) |
| default, seeded, the two fresh processes against each other | 30 | **30 of 30** | 30 of 30 |
| batch-invariant, fresh process, cold and warm | 60 | **60 of 60** | 60 of 60 |
| batch-invariant, seeded, fresh process | 30 | **30 of 30** | 30 of 30 |

- **A restart isn't what changes answers; history is.** The first run's seeded calls came after batched rounds that had pushed cases out of the prefix cache and back in, computed inside other batches. The fresh processes saw only quiet sequential calls, so they agreed with each other but not with the first run.

### 4. llama.cpp on the CPU: thread counts
| Threads (Q8_0, greedy, cache off) | Cases | Calls | Identical to 8 threads' first call | Verdicts identical |
|---|---|---|---|---|
| 8 (2 repeats) | 30 | 60 | **60 of 60** | 60 of 60 |
| 16 | 10 | 10 | 8 of 10 | 10 of 10 |
| 1 | 5 | 5 | 5 of 5 | 5 of 5 |

- **Each thread count is stable, but they don't all agree.** 16 threads changed the tokens of 2 of 10 cases, not their verdicts. A CPU receipt must pin the thread count, along with the build and the instruction set. 1 thread agreed with 8 on the 5 cases it ran; that's too few to call it safe.

### 5. llama.cpp: GPU against CPU, the same GGUF
| Comparison (cache off) | Calls | Identical to the CPU's first call | Verdicts identical | Verdict flips |
|---|---|---|---|---|
| Q8_0 greedy: CUDA (3 repeats) against CPU, 8 threads | 90 | 57 of 90 (19 of 30 cases) | 87 of 90 | `03-duration-bad` (CUDA fails it, the CPU passes it) |
| Q8_0 seeded: CUDA (2 repeats) against CPU, 10 cases | 20 | 4 of 20 (2 of 10 cases) | 20 of 20 | none |
| Q4_K_M greedy: CUDA against CPU, 8 threads | 30 | 10 of 30 | 28 of 30 | `03-duration-good` (unparseable on the CPU), `07-config-bad` (unparseable on CUDA) |

- **The same GGUF file gives different tokens on the GPU and the CPU**, and once in 30 a different opinion. Each backend is stable on its own.

### 6. Across engines and quantizations (greedy, each setup's first call per case)
| Setup A against setup B | Identical answers | Same verdict (the node's) | Same `solves` as written | Verdicts that differ |
|---|---|---|---|---|
| vLLM default against vLLM batch-invariant | 19 of 30 | 30 of 30 | 30 of 30 | none |
| vLLM default against vLLM with prefix caching off | 12 of 30 | 30 of 30 | 30 of 30 | none |
| vLLM batch-invariant (bf16) against llama.cpp CUDA Q8_0 | 2 of 30 | 25 of 30 | 27 of 30 | `03-duration-bad`, `05-backoff-bad`, `07-config-bad` (opinion); `07-config-borderline`, `10-urls-good` (broken JSON) |
| vLLM batch-invariant against llama.cpp CPU Q8_0 | 1 of 30 | 26 of 30 | 28 of 30 | `05-backoff-bad`, `07-config-bad` (opinion); `07-config-borderline`, `10-urls-good` (broken JSON) |
| vLLM batch-invariant against llama.cpp CUDA Q4_K_M | 0 of 30 | 27 of 30 | 27 of 30 | `05-backoff-bad`, `07-config-bad`, `10-urls-bad` (opinion) |
| vLLM batch-invariant against llama.cpp CPU Q4_K_M | 0 of 30 | 26 of 30 | 27 of 30 | the same 3, and `03-duration-good` (broken JSON) |
| llama.cpp CPU against CUDA, Q8_0 | 19 of 30 | 29 of 30 | 29 of 30 | `03-duration-bad` |
| llama.cpp CPU against CUDA, Q4_K_M | 10 of 30 | 28 of 30 | 30 of 30 | `03-duration-good`, `07-config-bad` (broken JSON) |
| llama.cpp Q8_0 against Q4_K_M, CPU | 1 of 30 | 26 of 30 | 29 of 30 | `10-urls-bad` (opinion); 3 broken JSON |
| llama.cpp Q8_0 against Q4_K_M, CUDA | 1 of 30 | 25 of 30 | 28 of 30 | `03-duration-bad`, `10-urls-bad` (opinion); 3 broken JSON |

- **Every opinion that changed across setups was on a bad fix** (`03-duration-bad`, `05-backoff-bad`, `07-config-bad`, `10-urls-bad`): the cases where the model is unsure, the same ones where sampling and the check ID change its verdict too.
- **"Same `solves` as written"** reads the model's `"solves": true|false` even when the rest of its answer isn't valid JSON. It separates a changed opinion from a lost verdict.
- **Broken JSON is a real source of flips.** `pof.judges.prompt.parse` rejects an answer that isn't valid JSON, and the node counts it as "doesn't solve".
  - 132 of the 3,925 case calls were unparseable: 35 of 600 with the node's request, 42 of 600 at temperature 1.0, 10 of 600 greedy calls with varied check IDs, and 45 across the other runs, greedy and seeded.
  - Most came from quoting code: 72 had unescaped double quotes inside a string (`"note": "Replaced `split("=")` ..."`), 31 an invalid backslash escape (a regex quoted as is). 29 had other slips, such as `"line": 8-11`.
  - Constrained decoding to the verdict's JSON schema (vLLM's structured outputs, llama.cpp's `json_schema`) would remove this. It would then be one more pinned flag.
- **Where answers first differ:** across every greedy setup there are 742 pairs of different answers to the same case.
  - In 488 of them, the two answers were identical up to and including the verdict (the answer's first field); they differ in the evidence or the reason.
  - In 192 more, the first difference is the layout (one line against indented JSON), in the first two characters.
  - That is why verdicts survive far more often than tokens: the verdict is written early, before small numeric differences have grown.

### 7. Seeded sampling (temperature 0.7, top_p 0.8, top_k 20, repetition penalty 1.05, seed 1234)
- **Reproducible where greedy is:** 90 of 90 sequential repeats in vLLM's default mode, 90 of 90 under 32 in flight in batch-invariant mode, 60 of 60 llama.cpp CUDA repeats, and 20 of 20 llama.cpp CPU repeats (10 cases). On another backend the seeded answers differ: CUDA matched the CPU in 4 of 20 calls (verdicts 20 of 20).
- **Not batch invariant in vLLM's default mode:** 66 of 90 calls matched under 32 in flight. A seed fixes the random draws, not the logits they're drawn from.
- **A seed is a knob too.** If the validator picks it, it can shop over seeds as over samples. It must come from the chain, like the check ID.

### 8. Answer shopping
Twenty calls per case, 600 per row; no seed. "Gain" is the mean over the label's cases of P(a pass within 5 calls) minus P(a pass in one call), the extra a shopper with 5 calls gets over one honest call.

| Request | Good: passes | Bad: passes | Borderline: passes | Bad: cases always / never / mixed | Borderline: always / never / mixed | Shopper's gain, bad | Shopper's gain, borderline | Unparseable answers |
|---|---|---|---|---|---|---|---|---|
| **the node's today** (no sampling fields; vLLM applies the model's 0.7 / 0.8 / 20 / 1.05) | 194 of 200 | **77 of 200 (38 %)** | **173 of 200 (86 %)** | 1 / 5 / 4 | 6 / 1 / 3 | +10.7 points | +3.5 points | 35 |
| temperature 1.0, nothing else | 188 of 200 | 68 of 200 (34 %) | 163 of 200 (82 %) | 1 / 3 / 6 | 6 / 1 / 3 | +14.6 points | +8.3 points | 42 |
| **greedy, batch-invariant, a new check ID per call** | 197 of 200 | **101 of 200 (50 %)** | 177 of 200 (88 %) | 2 / 3 / 5 | 7 / 1 / 2 | **+11.7 points** | +1.5 points | 10 |

Per case, against the greedy verdict with the canonical check ID (8 of the 10 bad fixes fail their tests; `05-backoff-bad` and `08-money-bad` pass them by special-casing the acceptance test):

| Case | Greedy verdict | Node's request: passes of 20 | Temperature 1.0 | New check ID each call |
|---|---|---|---|---|
| 01-median-bad | fail | 0 | 0 | 0 |
| 01-median-borderline | pass | 20 | 20 | 20 |
| 02-slugify-bad | fail | 0 | 1 | 0 |
| 02-slugify-borderline | fail | 0 | 0 | 0 |
| 03-duration-bad (its tests fail) | pass | 19 | 19 | 18 |
| 03-duration-borderline | pass | 20 | 18 | 20 |
| 04-pages-bad (its tests fail) | pass | 20 | 20 | 20 |
| 04-pages-borderline | pass | 17 | 11 | 19 |
| 05-backoff-bad | fail | 0 | 4 | **13** |
| 05-backoff-borderline | pass | 20 | 20 | 20 |
| 06-lru-bad | fail | 0 | 0 | 1 |
| 06-lru-borderline | pass | 20 | 20 | 20 |
| 07-config-bad | fail | **10** | 2 | **14** |
| 07-config-borderline | pass | 17 | 14 | 18 |
| 08-money-bad | pass | 19 | 19 | 20 |
| 08-money-borderline | pass | 20 | 20 | 20 |
| 09-csv-bad | fail | 0 | 0 | 0 |
| 09-csv-borderline | pass | 20 | 20 | 20 |
| 10-urls-bad | fail | **9** | 3 | **15** |
| 10-urls-borderline | pass | 19 | 20 | 20 |

- **Against the simulation's assumption** (`reports/open-validators-v1.md`: a borderline bad fix passes an honest call 3 times in 10, independently on each call):
  - **The honest pass rate is far higher here:** 86 % of calls on borderline fixes, 38 % on bad ones. That is a weak judge, and a solver attack on its accuracy, which needs no shopping.
  - **The room a shopper adds is far smaller:** a case's pass rate is mostly 0 or 1, not 0.3 every time. With 5 calls the simulation's shopper gains +53 points at 3 in 10 and +31 points at 1 in 10. Here it gains +3.5 points on borderline fixes and +10.7 on bad ones with today's request.
  - Bad fixes with a coin-flip pass rate (`07-config-bad` 10 of 20, `10-urls-bad` 9 of 20) are where shopping pays: 5 calls pass them 95–97 % of the time.
- **With greedy decoding pinned, the check ID is the remaining knob**, and as strong as sampling: `05-backoff-bad`, `07-config-bad` and `10-urls-bad` fail with the canonical ID and pass with 13–15 of 20 others.
- **This is one 7B model on 30 cases written for this test.** The pass rates are this model's on these cases, not a property of open-weight judges. A stronger model would fail more borderline fixes honestly, and its room to shop could be larger or smaller.

### 9. Speed and cost on this PC
| Setup | Seconds per call | Generation (tokens/s) | Prompt (tokens/s) | GPU power | GPU energy per call |
|---|---|---|---|---|---|
| vLLM default, one at a time | 1.7 | ~54 end to end | (not reported) | 295 W (prefix caching off) | 0.16 Wh |
| vLLM default, 16 in flight (600 calls in 102 s) | 0.17 per call | | | (not logged) | |
| vLLM batch-invariant, one at a time | 4.3 | ~22 end to end | | 232 W | 0.29 Wh |
| vLLM batch-invariant, 16 in flight (600 calls in 254 s) | 0.42 per call | | | 267 W | 0.031 Wh |
| llama.cpp CUDA Q8_0, one at a time | 1.0 | 95 | 12,100 | 285 W | 0.083 Wh |
| llama.cpp CUDA Q4_K_M, one at a time | 0.7 | 147 | 11,400 | 300 W | 0.062 Wh |
| llama.cpp CPU Q8_0, 8 threads | 24.6 | 7.0 | 73 | | |
| llama.cpp CPU Q8_0, 16 threads (10 cases) | 30.4 | 4.6 | 89 | | |
| llama.cpp CPU Q8_0, 1 thread (5 cases) | 86.6 | 3.7 | 14 | | |
| llama.cpp CPU Q4_K_M, 8 threads | 14.5 | 11.7 | 125 | | |

- "GPU energy per call" is the GPU's own draw over the run (nvidia-smi every 2 s, `power.py`), divided by the case calls; the CPU and the rest of the PC aren't counted. The GPU idles at about 27 W.
- **What a home validator needs:** the bf16 weights take 15 GB, so vLLM needs a 24 GB GPU for this model, and then serves 16–32 judges at once. llama.cpp's Q8_0 (8 GB) and Q4_K_M (4.7 GB) fit smaller GPUs. In batch-invariant mode one call costs the GPU 0.03–0.3 Wh, under a hundredth of a cent at $0.15 a kWh. A CPU alone works with llama.cpp: 25 s a call on 8 cores with Q8_0, 15 s with Q4_K_M. Generation is limited by memory bandwidth, so 16 threads were slower than 8 here, and 1 thread only about half as fast at generating.
- **The catch:** vLLM's wheel wants a CUDA toolkit or FlashInfer's prebuilt kernels for its default sampler. Without them it doesn't start, unless `VLLM_USE_FLASHINFER_SAMPLER=0` is set.

## Caveats
- **One GPU, one CPU, one model, one engine version each.** Nothing here says two different GPUs agree. That needs a paid rental (see above).
- **The cases are mine, written for this test**, in one made-up library; 10 per label. Pass rates have wide error bars: 20 calls per case, 10 cases per label.
- **The test runs ran locally** (`python -m unittest` in a temporary directory), not in the node's sandbox image, and the prompt says so.
- **llama.cpp's batching wasn't measured** (one slot). Neither were vLLM's other attention backends, nor any engine on another operating system.
- **CPU timings** were taken with the PC's usual background work running (an editor's server, a local Kubernetes). A first CPU stage at 16 threads was stopped after one call: with about 2 logical CPUs busy elsewhere (that work and another test run), llama.cpp's 16 threads waited on each other and made 1.2 tokens a second (88 s for one call). 8 threads, one per core, became the CPU reference, and 16 and 1 thread ran on subsets.
- **The answers' token IDs** were compared for vLLM only. For llama.cpp, identical bytes stand in for identical tokens.

## Reproduce
Everything outside the repository: `~/pof-125-env/` (the environments, builds and logs) and `~/models/` (the weights).

```bash
# environments (once)
uv venv ~/pof-125-env/vllm --managed-python --python 3.12   # a managed Python: Triton needs Python.h
uv pip install --python ~/pof-125-env/vllm/bin/python vllm==0.33.0 huggingface_hub hf_xet
~/pof-125-env/vllm/bin/hf download Qwen/Qwen2.5-7B-Instruct --revision a09a35458c702b33eeacc393d103063234e8bc28 \
  --local-dir ~/models/Qwen2.5-7B-Instruct
~/pof-125-env/vllm/bin/hf download Qwen/Qwen2.5-7B-Instruct-GGUF --revision bb5d59e06d9551d752d08b292a50eb208b07ab1f \
  qwen2.5-7b-instruct-q8_0-0000{1,2,3}-of-00003.gguf qwen2.5-7b-instruct-q4_k_m-0000{1,2}-of-00002.gguf \
  --local-dir ~/models/Qwen2.5-7B-Instruct-GGUF
git clone --depth 1 --branch b12070 https://github.com/ggml-org/llama.cpp ~/pof-125-env/llama.cpp-src
cmake -S ~/pof-125-env/llama.cpp-src -B ~/pof-125-env/llama-cpu -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON \
  -DLLAMA_CURL=OFF -DLLAMA_OPENSSL=OFF && cmake --build ~/pof-125-env/llama-cpu -j 16 --target llama-server
conda create -p ~/pof-125-env/cuda -c conda-forge --override-channels cuda-nvcc cuda-cudart-dev libcublas-dev \
  cuda-version=13.0
cmake -S ~/pof-125-env/llama.cpp-src -B ~/pof-125-env/llama-cuda -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=ON \
  -DCMAKE_CUDA_ARCHITECTURES=89 -DCUDAToolkit_ROOT=$HOME/pof-125-env/cuda \
  -DCMAKE_CUDA_COMPILER=$HOME/pof-125-env/cuda/bin/nvcc -DLLAMA_CURL=OFF -DLLAMA_OPENSSL=OFF \
  && cmake --build ~/pof-125-env/llama-cuda -j 16 --target llama-server

# the experiment (about 3 hours on this PC)
python3 experiments/determinism/build_cases.py          # the 30 cases (committed; built with Python 3.13, whose
                                                        # version is in each prompt's test line)
experiments/determinism/campaign.sh vllm d              # then:
experiments/determinism/campaign.sh all-after-vllm-d    # every later stage, in the report's order
experiments/determinism/versions.sh                     # results/versions.txt
python3 experiments/determinism/analyze.py              # every table
```

- `serve.sh` starts and stops each server (127.0.0.1 only); `run.py` makes the calls; `analyze.py` reads `results/*.jsonl.gz` (compressed for the commit with `gzip -9n`) and writes `results/summary.json`.
- `tests/test_determinism_cases.py` checks the cases and the pinned request fields without a model or a server.

## Disk used, to delete when done
About 40 GB of the disk's free space went to this experiment (805 GB free before, 765 GB after).

| Path | Size | What |
|---|---|---|
| `~/models/Qwen2.5-7B-Instruct` | 15 GB | the bf16 weights |
| `~/models/Qwen2.5-7B-Instruct-GGUF` | 12 GB | Q8_0 and Q4_K_M |
| `~/pof-125-env/vllm` | 9.0 GB | vLLM's virtual environment (its files are hard links into uv's cache) |
| `~/pof-125-env/cuda` | 2.1 GB | conda-forge's nvcc, CUDA runtime and cuBLAS, for the llama.cpp CUDA build |
| `~/pof-125-env/llama.cpp-src`, `llama-cpu`, `llama-cuda` | 0.6 GB | the llama.cpp source and both builds |
| `~/pof-125-env/logs`, `run` | small | every server's log, the GPU power log, the chain scripts |
| `~/.cache/uv` | 12 GB more | uv's cache of the wheels (shared with any other uv project: `uv cache prune` keeps what's in use) |
| `~/miniconda3/pkgs` (the `cuda-*` and `libcublas*` packages) | 1.6 GB | conda's download cache (`conda clean --all`) |
| `~/.cache/vllm`, `~/.triton`, `~/.local/share/uv/python/cpython-3.12.12-linux-x86_64-gnu` | 0.2 GB | vLLM's compile cache, Triton's kernels, the Python vLLM ran on |

To remove it all: `rm -rf ~/models/Qwen2.5-7B-Instruct ~/models/Qwen2.5-7B-Instruct-GGUF ~/pof-125-env ~/.cache/vllm`, then `uv cache prune` and `conda clean --all`.
