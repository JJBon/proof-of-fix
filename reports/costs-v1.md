# Running costs, v1 (proof-of-fix#82 B2, for #85; 2026-10-30)

**Command:** `python3 -m pof.costs` prints the tables below. `python3 -m pof.costs --measure 20` re-measures the counts per paid fix in the simulated market, which takes about 2 seconds. The model is `pof/costs.py`: every input is data there, with its source.

**What it costs:** #85's judges, in US dollars.
- **A check:** each submission's tests run on 2 attested runners, plus one review by each of the 3 issue-tier judges (Anthropic, OpenAI and Google).
- **An escalation:** the same fix reviewed again by the 7 constitution-tier judges, one family each (adding DeepSeek, Qwen, Mistral and Llama).
- **A registration:** an issue's check by the 3 judges.
- **An ADR:** the 7 judges, its evidence's test runs, and one signed result on-chain.
- **Gas:** every transaction a paid fix carries, on a layer-2 chain.

## Headline (prompt cache on, a quiet layer-2 chain)

| | Judge-grade models | Cheap models |
|---|---|---|
| **One check**, medium fix (~200 lines): tests and 3 judges | **$0.37** | **$0.05** |
| One check, small fix to large fix | $0.15 to $0.90 | $0.02 to $0.11 |
| **One paid fix**, at the assumed size mix | **$1.96** | **$0.81** |
| Gas's share of a paid fix | 35 % ($0.69) | 84 % ($0.69) |
| **One ADR** (7 judges) | **$1.26** | **$0.26** |

- **Cheap.** A paid fix costs about $2 to run with judge-grade models. In the simulated market a funder pays about 120 credits per paid fix. If a credit were a dollar, the checks and gas would be **1.6 %** of it (judge-grade) or 0.7 % (cheap).
- **The simulation's fees already cover it.** The market's parameters charge 2 credits per registration, and about 2.1 credits per submission's check (2 runs at 0.3 and 3 verdicts at 0.5). At a dollar a credit, that's at least 5× the cost of a medium check.
- **Gas is the largest single item** with cheap models, and a third of the total with judge-grade ones.

## Inputs

### Models (list prices per million tokens, 2026-10-30 unless noted)
| Family | Judge-grade model | Input / cached / output | Cheap model | Input / cached / output | Source |
|---|---|---|---|---|---|
| Anthropic | Claude Opus 5.5 | 4.00 / 0.20 / 20.00 | Claude Haiku 5.5 | 0.10 / 0.01* / 0.50 | Anthropic price list (cached 2026-10-06) |
| OpenAI | gpt-6.1-sol | 2.00 / 0.10 / 10.00 | gpt-6-luna | 0.10 / 0.01 / 0.50 | developers.openai.com/api/docs/pricing |
| Google | gemini-3.1-pro-preview | 2.00 / 0.20 / 12.00 | gemini-3.1-flash-lite | 0.25 / 0.025 / 1.50 | ai.google.dev/gemini-api/docs/pricing |
| DeepSeek | deepseek-v4-pro (peak) | 1.32 / 0.044 / 3.96 | deepseek-flash (peak) | 0.30 / 0.006 / 1.20 | api-docs.deepseek.com (off-peak is half) |
| Qwen | Qwen3.7-Max (Together) | 1.50 / 1.50* / 4.50 | Qwen3.7-Plus (Together) | 0.32 / 0.32* / 1.28 | together.ai/pricing |
| Mistral | Mistral Large | 0.50 / 0.05* / 1.50 | the same (no other price listed) | | mistral.ai/pricing (version not named) |
| Llama | Llama 4 Maverick (Groq) | 0.50 / 0.50* / 0.77 | Llama 3 8B Instruct Lite (Together) | 0.14 / 0.14* / 0.14 | Maverick: third-party aggregators, **unverified**; 8B: together.ai/pricing |

\* Assumed: Haiku's cache read at 0.1× input, Mistral's at 0.1× ("up to 90 %"), and no cache discount for Qwen and Llama.

**Other notes on the prices:**
- Gemini's 3.6 and 3.8 Flash prices double on 2027-01-01. The 3.1 Flash-Lite used here isn't affected.
- Output prices also pay for thinking tokens. The model assumes the same output length for both grades, which flatters the judge-grade models a little.

### Tokens per review (assumptions)
| Review | Input | of which cacheable (prompt and constitution) | Output, thinking included |
|---|---|---|---|
| Small fix (~50 lines) | 14,000 | 7,000 | 2,000 |
| Medium fix (~200 lines) | 28,500 | 7,000 | 4,000 |
| Large fix (~800 lines) | 69,000 | 7,000 | 8,000 |
| Registration | 16,500 | 7,000 | 2,000 |
| ADR (whole constitution, evidence, code) | 56,000 | 15,000 | 12,000 |

- **Input** is: the prompt and rubric (3,000), the constitution excerpt (4,000), the issue, the diff, the nearby code and the test output.
- **The size mix** for a "paid fix" is assumed to be 50 % small, 35 % medium and 15 % large.

### Tests (the sandbox)
- **Runners:** 2 runners per check (the simulation's `ci_runners`).
- **Container:** 2 vCPU and 4 GB at AWS Fargate's on-demand Linux x86 rates in us-east-1: $0.04048 per vCPU-hour and $0.004445 per GB-hour. Those rates are from third-party sources dated up to October 2026 and agree with AWS's page. That's $0.0016 a minute.
- **Minutes, setup included (assumption):** 3 for a small fix, 8 for a medium one, 20 for a large one, and 20 for an ADR.
- **For scale:** this repository's own suite takes 73 s (Python) plus 8 s (contracts) on a laptop.
- **Tests are a small part of a check:** about 7 % with judge-grade models, but up to 58 % with cheap ones.

### Counts per paid fix (simulated market, seeds 1-20, 8 weeks each)
| | Per paid fix |
|---|---|
| Issues registered | 3.30 |
| Attempts started | 2.25 |
| Submissions checked by a jury | 1.54 |
| Escalations to the 7 judges | 0.46 (28 % of checks) |

- **Assumptions:** 1 pledge, 2 withdrawals (the solver and the reporter), and 0.5 refund flows (an unsolved pledged bounty's sunset and refund) per paid fix.
- **The escalation rate** is the simulation's: a split first jury goes to the 7. #85's rule is the same: any one judge flagging a fix sends it up.

### Gas (median gas per call, `forge test --gas-report` on `contracts/test/Race.t.sol`, main 5da2c56)
| Call | Gas | Per paid fix |
|---|---|---|
| `register` | 273,289 | 3.30 |
| `accept` | 149,126 | 3.30 |
| `pledge` | 159,408 | 1 |
| `attempt` | 125,053 | 2.25 |
| `commit` | 295,087 | 1.54 |
| `result` | 205,594 | 1.54 |
| `merged` | 202,838 | 1 |
| `settle` | 391,429 | 1 |
| `claimInstalments` | 104,995 | 1 |
| `withdraw` | 53,800 | 2 |
| `sunset` + `claimRefund` | 90,577 + 169,941 | 0.5 |
| the on-chain head (#85, **not built: assumption**) | 60,000 | 1 |

**Total:** 3.6 million gas in 20 transactions per paid fix.

**Prices:**
- **Execution:** 0.05 gwei, Base's execution base fee on 2026-03-17. No October figure was found, so this is an assumption.
- **ETH:** about $2,700, its price in early October 2026.
- **L1 data fee:** $0.01 per transaction, an assumption inside Base's published range of $0.005–$0.10.

## Results

### Cost per check
| Fix size | Grade | Tests | 3 judges | **Check** | Escalated to the 7 (extra) |
|---|---|---|---|---|---|
| small | judge | $0.0099 | $0.14 | **$0.15** | $0.21 |
| small | cheap | $0.0099 | $0.0085 | **$0.0183** | $0.0291 |
| medium | judge | $0.0263 | $0.34 | **$0.37** | $0.48 |
| medium | cheap | $0.0263 | $0.0200 | **$0.0463** | $0.0672 |
| large | judge | $0.0658 | $0.84 | **$0.90** | $1.17 |
| large | cheap | $0.0658 | $0.0482 | **$0.11** | $0.16 |

**One medium review per family:**

| Family | Judge-grade | Cheap |
|---|---|---|
| Anthropic | $0.167 | $0.0042 |
| OpenAI | $0.084 | $0.0042 |
| Google | $0.092 | $0.0115 |
| DeepSeek | $0.045 | $0.0113 |
| Qwen | $0.061 | $0.0142 |
| Mistral | $0.017 | $0.0171 |
| Llama | $0.017 | $0.0046 |

**The Anthropic seat is half the issue tier's judge cost (49 %) at judge grade.** With Claude Sonnet 5.5 ($2 / $10) in that seat, a medium review costs $0.084 and the medium check drops from $0.37 to $0.28.

### Cost per paid fix
| Fix size | Grade | Registrations | Checks | Escalations | Gas | **Total** | Gas share |
|---|---|---|---|---|---|---|---|
| small | judge | $0.54 | $0.24 | $0.09 | $0.69 | **$1.56** | 44 % |
| small | cheap | $0.03 | $0.03 | $0.01 | $0.69 | **$0.76** | 90 % |
| medium | judge | $0.54 | $0.57 | $0.22 | $0.69 | **$2.02** | 34 % |
| medium | cheap | $0.03 | $0.07 | $0.03 | $0.69 | **$0.82** | 84 % |
| large | judge | $0.54 | $1.39 | $0.54 | $0.69 | **$3.15** | 22 % |
| large | cheap | $0.03 | $0.18 | $0.07 | $0.69 | **$0.97** | 71 % |
| **mix** | judge | $0.54 | $0.53 | $0.21 | $0.69 | **$1.96** | 35 % |
| **mix** | cheap | $0.03 | $0.07 | $0.03 | $0.69 | **$0.81** | 84 % |

- **Registrations cost as much as the checks.** For every paid fix, 3.3 issues are registered, and most are never fixed in the run's 8 weeks. The reporter's registration fee pays for them (#85), but it's still a real cost of the system.
- **Registering is 39 % of the gas:** `register` and `accept`, 3.3 times per paid fix.

### Cost per ADR
| Grade | 7 judges | Tests | Gas | **Total** |
|---|---|---|---|---|
| judge | $1.16 | $0.07 | $0.04 | **$1.26** |
| cheap | $0.16 | $0.07 | $0.04 | **$0.26** |

The constitution tier's cost isn't what protects it: an ADR is cheap to check. Its protection is the 5-of-7 vote and the 14-day challenge window. The ADR's author pays the fee (#85), so a heavy stake, not the fee, must be what stops spam ADRs.

### Fees and an operator's margin (medium fix, judge grade)
| Margin | Check fee (break-even at 0 %) | Anthropic-seat operator's profit per 1,000 verdicts |
|---|---|---|
| 0 % | $0.37 | $0 |
| 20 % | $0.44 | $33 |
| 50 % | $0.55 | $84 |

**An operator seated on every jury** signs 5.3 verdicts per paid fix (3.3 registrations, 1.54 checks, 0.46 escalations):
- **Anthropic seat, judge grade:** that costs it $0.57 per paid fix, so it keeps **$114 per 1,000 paid fixes at a 20 % margin, or $286 at 50 %**.
- **Cheap grade:** $3 or $7.

**Running a judge node is a thin business, as #82 comment 4391 expected.** It pays at volume, or as a way into the services for companies.

### Sensitivity (paid fix at the size mix)
| Case | Judge grade | Cheap grade |
|---|---|---|
| Base (cache on, 0.05 gwei, $0.01 data fee) | $1.96 | $0.81 |
| No prompt cache | $2.24 | $0.83 |
| Busy chain (0.5 gwei, $0.10 data fee) | $8.12 | $6.98 |
| Half the escalations | $1.85 | $0.80 |
| Twice the submissions | $2.62 | $1.01 |

- **The chain is the biggest risk to the cost:** gas goes from $0.69 to $6.86 a fix on a busy chain, while the models change the total by at most about 2.4×.
- **The prompt cache saves 13 %** at judge grade. The fixed part of a prompt (rubric and constitution) is small next to the diff and the code.

## What this means for #85 and the owner
1. **The judges are affordable at judge grade.** About $2 a paid fix, even with 7 judges on escalations. Grade can be chosen for accuracy, which B1 must measure, not for cost.
2. **Cut the gas before cutting the models.** Keep unfunded issues off-chain until a pledge arrives, which removes most of `register` and `accept` (39 % of the gas), and batch withdrawals. This is a design choice for #85's spec.
3. **The fees in the simulation are generous:** about 5× cost if a credit is a dollar. They could fall, or stay as an anti-spam margin.
4. **Operators earn little per check.** The owner's node income (#82 comment 4391, row 3) is small unless volume is large: about $100–$300 per 1,000 paid fixes at judge grade.

## Not modelled
- the AI's accuracy at each grade (B1);
- appeals and challenges, which add juries;
- off-peak discounts (DeepSeek halves its prices off-peak);
- the batch APIs' 50 % discount;
- operators' fixed costs (servers, keys, monitoring);
- the cost of a funder's or solver's own time.
