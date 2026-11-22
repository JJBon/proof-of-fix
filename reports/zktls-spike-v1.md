# zkTLS spike v1: can a level C validator prove its model call today?

proof-of-fix#135, task 1.9 of `openspec/changes/proof-of-fix-132-open-validators`. Run on 2026-11-03 with the owner's approval (a few cents of model calls, anonymous contact with outside notaries).

## The answer

**Not yet.** The cryptography works, and it's fast and small. What's missing is the network of notaries around it, and room for a real judge's prompt.

- **What works.** We proved 13 real model calls on AWS Bedrock (Anthropic, OpenAI and Google models), with TLSNotary. Each proof took 2 to 6 seconds with our own notary, and 8 to 22 seconds with the TLSNotary project's public verifier. A signed proof is about 6 KB. It verifies offline in milliseconds, with no network. It hides the AWS credentials and reveals the prompt and the answer.
- **Blocker 1: no independent notary signs proofs today.** The TLSNotary project's public notary (`notary.pse.dev`) is gone, and its notary server was removed from the code in alpha.13. The project's public service now only *verifies* a session live and signs nothing, so it leaves no proof anyone else can check. Our own notaries do sign, but a validator's own notary proves nothing.
- **Blocker 2: the request is limited to 4 KB in the default (MPC) mode.** At 8 KB and above the session fails. The signed request already uses 1.8 KB, 1.3 KB of it credentials. A judge's prompt, with a diff and its tests, won't fit. Proxy mode took 20 KB but hung at 40 KB.
- **Blocker 3: maturity.** TLSNotary is alpha software ("should not be used in production"), with breaking changes in each release. It speaks only TLS 1.2, with "no immediate plans" for TLS 1.3. Bedrock still accepts TLS 1.2 today.

**Recommendation:** keep level C off. Re-run this spike when an independent party runs a signing notary for a current release, or when we can recruit several, and when MPC mode takes a 32 KB request. Proxy mode is the better candidate: 30 times less traffic, 3 times faster.

## What was run

- **Implementation:** TLSNotary `tlsn` **v0.1.0-alpha.15** (commit `47aee45`, 2026-05-21), the latest release. We built it with Rust 1.95.0, which the release requires (`experiments/zktls/build.sh`). Our three small tools are added as examples of the release's own examples crate, so its `Cargo.lock` pins every dependency. TLSNotary could do the job, so we didn't try another implementation.
- **Notaries and verifiers:**

  | Name | Run by | Signs a proof? | Independent? |
  |---|---|---|---|
  | **Notary A** | us, on 127.0.0.1, same release (`pof_notary`) | yes: secp256k1 "eth" scheme, address `0xCA5064d5dA7A391f1FEd7dAbE591d502B59d7944` | no |
  | **Notary B** | us, on 127.0.0.1, a different key | yes, address `0xD7B0e480b067dA399043F341171D6b2a52cf9b3b` | no |
  | **PSE demo verifier** | the TLSNotary project (PSE), `wss://demo.tlsnotary.org`, tlsn 0.1.0-alpha.15 (tlsn-extension commit `d446234`) | **no**: it verifies live and returns an unsigned JSON result | **yes** |

  We found no public notary that signs. `notary.pse.dev` doesn't resolve anymore. The demo verifier's documentation says its built-in proxy removes the need for `notary.pse.dev`'s. We contacted only `demo.tlsnotary.org`, anonymously, over its WebSocket API: 7 sessions in all. We created no account and posted nothing.
- **Provider:** AWS Bedrock, `bedrock-runtime.us-east-1.amazonaws.com`, the Converse API, one HTTPS endpoint for every model. The prompt: "Answer with one word, PASS or FAIL: does the Python test `assert 2 + 2 == 4` pass?", with `maxTokens` 20. Requests were signed in-process (SigV4, botocore) with temporary SSO credentials. Each proof hides the values of `Authorization` and `X-Amz-Security-Token`.
- **Models:** Claude Haiku 4.5 (`us.anthropic.claude-haiku-4-5-20251001-v1:0`), gpt-oss-20b (`openai.gpt-oss-20b-1:0`), GPT-5.6 Terra (`us.openai.gpt-5.6-terra`) and Gemma 3 4B (`google.gemma-3-4b-it`). All four answered; none was "not enabled".
- **Not run:** the OpenAI and Gemini APIs directly (no key on this PC), and Gemini itself, which isn't on Bedrock. We also didn't use the company's model gateway as a target, on purpose. A proof there would only show what our own gateway answered, not what the provider answered.

## Results: provider × notary

Every number comes from the runs in `experiments/zktls/results/` (`python3 experiments/zktls/run_spike.py summarize` prints them all). "Time" runs from connecting to the notary until the proof is ready. "Traffic" is prover ↔ notary. All runs used `max_sent` 4096 and `max_recv` 4096.

| Provider, model | Notary | Mode | Proved? | Time | Traffic up / down | Proof size | TLS | Offline-verifiable? |
|---|---|---|---|---|---|---|---|---|
| Anthropic, Claude Haiku 4.5 | A | MPC | yes, "PASS" | 4.1 s | 62.8 / 4.0 MB | 533 B attestation, 6,117 B presentation | 1.2 | **yes**, with no network |
| Anthropic, Claude Haiku 4.5 | B | MPC | yes, "PASS" | 4.0 s | 62.8 / 4.0 MB | 533 B, 6,117 B | 1.2 | **yes** |
| Anthropic, Claude Haiku 4.5 | A | proxy | yes, "PASS" | 2.2 s | 0.6 / 1.6 MB | 533 B, 6,117 B | 1.2 | **yes** |
| Anthropic, Claude Haiku 4.5 | PSE demo | MPC | yes, "PASS" | 22.1 s | 62.8 / 3.9 MB | none (unsigned) | 1.2 | **no** |
| Anthropic, Claude Haiku 4.5 | PSE demo | proxy | yes, "PASS" | 7.6 s | 0.6 / 1.5 MB | none (unsigned) | 1.2 | **no** |
| OpenAI, gpt-oss-20b | A | MPC | yes (reasoning only, cut at 20 tokens) | 4.1 s | 62.8 / 4.0 MB | 533 B, 6,090 B | 1.2 | **yes** |
| OpenAI, gpt-oss-20b | B | MPC | yes (same) | 6.4 s | 62.8 / 4.0 MB | 533 B, 6,090 B | 1.2 | **yes** |
| OpenAI, gpt-oss-20b | PSE demo | MPC | yes (same) | 20.9 s | 62.7 / 3.9 MB | none | 1.2 | **no** |
| OpenAI, GPT-5.6 Terra | A | MPC | yes, "PASS" | 4.6 s | 62.8 / 4.0 MB | 533 B, 6,095 B | 1.2 | **yes** |
| OpenAI, GPT-5.6 Terra | PSE demo | MPC | yes, "PASS" | 22.3 s | 62.7 / 3.9 MB | none | 1.2 | **no** |
| Google, Gemma 3 4B | A | MPC | yes, "PASS" | 3.8 s | 62.8 / 3.9 MB | 533 B, 5,984 B | 1.2 | **yes** |
| Google, Gemma 3 4B | B | MPC | yes, "PASS" | 4.1 s | 62.8 / 3.9 MB | 533 B, 5,984 B | 1.2 | **yes** |
| Google, Gemma 3 4B | PSE demo | MPC | yes, "PASS" | 21.2 s | 62.7 / 3.9 MB | none | 1.2 | **no** |
| Google, Gemini | – | – | not run: not on Bedrock, no key | | | | | |
| OpenAI API, Gemini API (direct) | – | – | not run: no key | | | | | |

**Notes on the table:**
- **Where the time goes.** Our notaries were on the same PC. The PSE runs crossed the internet: their MPC setup (preprocessing) took 14 to 16 s of the 21 to 22 s.
- **What "offline" means.** `pof_verify` checked each signed proof inside a network namespace with no network (`unshare -rn`), in 2 to 4 ms. It checks the notary's signature, the Merkle root, the server's certificate chain against the Mozilla roots at the connection's time, and every revealed byte. Then `experiments/zktls/receipt_check.py` redid all of it in pure Python except the certificate chain, in 13 to 24 ms.
- **What the public verifier gave back.** Each PSE session ended with `session_completed` and the revealed parts. It has nothing to keep and nothing anyone else can check, so it isn't a proof.
- **The model makes no difference.** All models go to the same endpoint, with the same certificate chain and the same cipher (TLS 1.2, ECDHE with P-256, AES-128-GCM). The model's ID is in the revealed request line. Only the lengths change, with the answer: 391 to 499 bytes received, 5,984 to 6,117 bytes of presentation.

## Size limits

These were tested with free requests: `GET /` or `POST /` to the same Bedrock endpoint, which answers 404 and runs no model.

| Mode, limit tested | Result |
|---|---|
| MPC, `max_sent` 4096 (actual 3,802 B) | works, 4.3 s |
| MPC, `max_sent` 8192, 16384 or 65536 | **fails** in setup: "maximum number of streams reached" (the session multiplexer's 512-stream limit). Fewer sent records (4) didn't help, and neither did 4 CPUs. |
| MPC, `max_recv` 1 KB, 16 KB, 64 KB | all work, at the same cost: the answer is decrypted after the connection closes, so the limit costs nothing up front. Larger wasn't tested. |
| proxy, actual request 3.8 KB, 16 KB, 20 KB | works: 1.9 s, 4.8 s, 3.7 s; presentation 9 KB, 21 KB, 25 KB |
| proxy, actual request 40 KB or 60 KB | **no response within 180 s**. Bedrock answers the same requests at once without TLSNotary, so the stall is on our side. We didn't investigate. |
| PSE demo verifier | limits are whatever the prover registers. Each session must finish within its 120 s timeout. |
| PSE demo verifier, proxy, actual request 16 KB | the TLS exchange finished, then **no result within 7 minutes**. The same request proved locally in 4.8 s. We didn't investigate. |

**What this means for a judge.** A real validator's prompt carries the issue, a diff and its tests: often 10 to 50 KB. In MPC mode, about 2.4 KB is left for the prompt: 4,096 bytes minus the 1,609 bytes of request line and headers. Proxy mode fits 20 KB. The answer side is fine: a verdict is small, and MPC's answer limit is cheap.

## What a level C receipt would carry

Measured on our runs, in `experiments/zktls/proofs/`:

- **The notary's attestation (533 B):**
  - a **header** of 54 B: an id, a version and the Keccak-256 Merkle root of the body;
  - a **signature** of 65 B: secp256k1, `r || s || v` over `keccak256(header)`;
  - a **body** of 317 B, six fields: the notary's key; the connection's time, TLS version and lengths; the server's ephemeral key; a commitment to its certificate chain; and two SHA-256 commitments, to the request and to the answer.
- **The presentation (about 6 KB):**
  - the request line (with the model's ID), the headers and the body (prompt and `maxTokens`), with the credential values hidden;
  - the whole answer, with its usage counts;
  - the server's certificate chain and handshake signature.
- **What the receipt still needs to add:** the hash of the submission being judged. The prompt is in the revealed request, so the panel can recompute it. It also needs the tlsn version, because proofs from one alpha release may not verify with the next.

As JSON (our `pof-zktls-receipt/1`), each receipt is 6.8 to 7.1 KB.

**What a receipt doesn't prove:**
- **Answer shopping.** It doesn't prove that this was the validator's only call to the model (D10).
- **The server, if only the attestation is checked.** In the attestation flow, the notary never learns the server's name. The name is proven later, in the presentation, by the certificate chain.

## What the contract would verify on-chain

- **The notary's signature.** It's `ecrecover(keccak256(header), v, r, s)`, which must equal an address on the constitution's notary list. The scheme is TLSNotary's `secp256k1eth`, made for exactly this.
  - **Cost (estimated by hand, not measured).** The parts are ecrecover (3,000 gas), Keccak over 54 bytes (about 40), calldata for 119 bytes (about 1,900) and a cold read of the notary list (2,100). With call overhead, that's about **8,000 to 10,000 gas** a receipt. Foundry runs in Docker here, and Docker stays off.
- **Optionally, a field.**
  - A Merkle path into the Keccak root costs about 1,000 to 2,000 gas: six leaves, depth 3, plus the field's own hash.
  - Opening the answer's SHA-256 commitment costs 16 gas a byte of calldata, about 16,000 gas for a 1 KB answer.
  - The two together are **about 20,000 to 30,000 gas** for "this notary signed this answer".
- **Not on-chain: the server's certificate chain.** That's X.509 parsing and an RSA-PSS check, far too costly. The drawn panel checks it off-chain, as D10 already says for all proofs. The contract keeps only the presentation's hash.
- **An alternative.** A notary could require the server's name to be revealed during the session, as the PSE verifier does, and sign it into the attestation. The contract could then check the provider's name too. That needs notary code beyond the release's examples.

## Risks

- **Notary collusion.** A notary that colludes with the validator can sign a forged answer. In MPC it holds half the TLS keys. In proxy mode it relays the traffic.
  - So a validator's own notary is worthless, and level C needs notaries run by others.
  - Asking for several notaries per proof means several model calls, one TLS session each. That adds cost, and more chances to shop for an answer.
- **No independent notary exists today.** PSE's notary is gone. Its demo verifier signs nothing, is a demo, has a 120 s limit and could change any day.
  - The constitution's first list (task 2.1) would be empty unless we recruit operators. Independent validators could run notaries for each other, for instance.
- **TLS 1.3.** TLSNotary speaks only TLS 1.2 (its FAQ: "There are no immediate plans to support TLS 1.3").
  - Bedrock prefers TLS 1.3 with ordinary clients (curl got TLS 1.3) but still accepts TLS 1.2 with ECDHE and AES-128-GCM.
  - A provider that drops TLS 1.2, or P-256, or AES-GCM, ends level C for that provider.
- **Provider changes, and errors that quote secrets.**
  - Our first call failed its signature, because we signed the hop-by-hop `Connection` header. Bedrock's error message quotes the canonical request, **session token included**, and we were revealing the whole response.
  - Nothing left this PC: our local notary sees no plaintext, and we deleted the files before any commit. But part of the token printed in the agent's own session output. It's a temporary STS token, useless without its secret key, and it expires within hours.
  - **The fix is in the prover now:** a non-2xx response reveals only its status line, and any echo of a hidden value is hidden wherever it appears.
  - A level C kit must do the same. A public verifier logs everything revealed.
- **Request size** (above): judges' prompts don't fit in MPC mode, and only up to about 20 KB in proxy mode.
- **Bandwidth.** MPC uploads about 63 MB to the notary for every call, whatever the size of the call. Proxy mode uploads 0.6 MB. A busy notary in MPC mode needs serious bandwidth.
- **Proxy mode trusts the notary's own route to the provider.** The notary connects to the provider itself. A prover who could redirect the notary's DNS or routing could forge an answer.
- **Alpha software.**
  - Expect breaking changes. Alpha.13 removed the notary server, and the attestation crate "will continue to be maintained but will not receive new features".
  - Pin the verifier version in each receipt.
- **What zkTLS can't fix:** answer shopping (D10), and the validator still needs its own provider account.

## Costs of the paid calls

There were 14 signed requests, within the budget of 15. 13 reached a model. 1 was rejected by Bedrock (403) before any model ran, so it wasn't billed.

| Model | Calls | Tokens per call (in / out) | Price (USD per million, in / out) | Cost |
|---|---|---|---|---|
| Claude Haiku 4.5 | 5 | 37 / 5 | 1.10 / 5.50 (us. profile, regional) | $0.000341 |
| gpt-oss-20b | 3 | 93 / 20 | 0.07 / 0.30 | $0.000038 |
| Gemma 3 4B | 3 | 35 / 3 | 0.04 / 0.08 | $0.000005 |
| GPT-5.6 Terra | 2 | 32 / 5 | not published by AWS on 2026-11-03 | unpriced; under $0.0035 even at $30 / $150 per million |
| **Total** | **13** | | | **$0.000383 priced, under $0.004 in all** |

Prices come from AWS's public price list for us-east-1, on demand, read on 2026-11-03.

## What remains to test

- **OpenAI's and Google's own APIs:** not run, since there's no key on this PC. Gemini isn't on Bedrock. We covered OpenAI's models (gpt-oss-20b, GPT-5.6 Terra) and Google's Gemma through Bedrock.
- **A truly independent *signing* notary:** none exists. Our two notaries share an owner. The independent PSE verifier signs nothing.
- **Requests above 4 KB in MPC mode, above 20 KB in proxy mode, and a 16 KB request through the public verifier:** each needs an upstream fix, a newer release, or more investigation.
- **TLS 1.3:** not supported upstream.
- **Answers above about 2 KB:** our largest proved response was 2,208 bytes, the rejected call's 403. It was proved and checked before we deleted it.
- **Several notaries per proof:** each needs its own call. Not tried.

## How to reproduce

- **Build.** Run `experiments/zktls/build.sh`. It clones the pinned tag into `~/pof-135-build` and builds with `nice` and 4 jobs. Then make two keys in `~/pof-135-build/keys/notary-{a,b}.key` (32 random bytes as hex).
- **Run.** `run_spike.py free …` makes the free size tests. `run_spike.py call --model … --notary … --mode …` makes a paid call; it refuses a 16th signed request. `run_spike.py summarize` prints the tables.
- **Check offline.** `tests/test_zktls_receipt.py` runs in CI with no network, Rust or credentials.
  - It checks the recorded Claude Haiku 4.5 proof from notary A in pure Python.
  - It checks that changing any revealed byte, the header, the body, the key or a hidden byte is caught.
  - It checks every recorded receipt, and that nothing recorded looks like a credential.
  - When the pinned Rust verifier is present, it also re-runs it on every presentation. Otherwise that test skips, as on the CI host.
