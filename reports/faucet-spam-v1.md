# Spam that pays the judges' fee in faucet USDC, v1: Circle's Sepolia faucet as the identity cost (proof-of-fix#251 task 3.15, #132 task 13.7; 2026-11-18)

**Status: post hoc relative to [report v6](open-validators-measured-v6.md), confirmatory on its own rule.** The switch was proposed after v6's results (its section "Post hoc: the newcomer lane" found that identities must cost something). This report's rule, rows and criterion (section 3.1) were committed before its 40-seed runs, which use **fresh seeds 41–80** as #132 task 13.7 asks; every earlier round used 1–40. Every ± is two standard errors of the mean over the seeds. No model call: judges' verdicts are replayed from `data/judges/verdicts-v2.matrix.json` (#160).

**Commands:** `python3 -m pof.sim.openval.capacity --only faucet --seed0 41 --seeds 40 --jobs 14 --out DIR` runs the table; `--render DIR` prints it (section 3.4).

**Why:** the owner chose Circle's Sepolia USDC as the fee coin (launch design L17) so that bonds, pledges and the judges' fee (D30) cost USDC that only a rate-limited faucet hands out. Report v6 found that, without such a cost, junk from free identities floods honest fixes once it exceeds the network's capacity, and that newcomers' fixes are the ones lost. This report checks the faucet's limits at the source (part 1), prices each actor in faucet requests (part 2), and simulates spam whose rate is bounded by its faucet income (part 3).

## In brief
- **Circle's public faucet** (read 2026-11-18): **20 USDC a request, one request every 2 hours per address and per blockchain, no account, reCAPTCHA**, Ethereum Sepolia supported; more on request on Circle's Discord. That caps one address at 240 USDC a day on one chain. Addresses are free. **The Developer Console faucet** (account-gated, funds only Circle Wallets addresses) has no readable page any more: its documentation redirects to the public faucet. Its old values (20 USDC a day per testnet) are unconfirmed.
- **Validator bonds can't realistically come from the faucet:** 7–15 bonds of $1,250 take 438–938 requests (five days of requests every two hours on 7–15 addresses). Ask Circle on Discord, or lower the testnet bond to $250 (13 requests) with bounties up to $125.
- **Honest actors pay little:** a newcomer's first fix is one request (the $5.03 fee); a funder's median pledge is 5.
- **Spam (40 seeds, 41–80, rule fixed before the runs):** the queue holds for every honest fix and every newcomer's at 7 and 15 validators up to **two addresses at the limit** (about 4 junk fixes an hour), with reputation first or FIFO. **Five addresses** (60 reCAPTCHAs a day, or one address bridging from five testnets with CCTP) withdraw 9–11 % of honest fixes at 7 validators, 83–85 % of newcomers'. At 15 they make 61–68 % of newcomers' fixes wait over a day. A newcomer lane of 25 % is worse than none.
- **The budget doesn't hold:** one address at the limit costs the owner **$214–1,328 a month** in model calls, against $30–50. Only an account-gated income (20 USDC a day) stays under $50, and only at the cheapest call. The owner can't choose it: spammers use the public faucet.
- **Recommendation:** the faucet stops casual spam from blocking honest fixes. It doesn't protect the model budget and doesn't stop a determined spammer. On Sepolia: a judges' fee of $20–40 in test USDC (one or two requests a submission), no lane, bonds via Discord or $250, and heavy spam (a stall when the budget stop binds) named as a risk in the README and the paper. The owner decides whether that is enough.

## Part 1: Circle's faucet limits, from Circle's own pages (read 2026-11-18)

| # | Fact | Source (read 2026-11-18) |
|---|---|---|
| 1 | **The public faucet gives 20 USDC a request**, "every 2 hours, per address, and per blockchain". The banner: "Limit: One request per pairing of asset and test network every 2 hours". So **one address can collect at most 240 USDC a day on one chain** (12 requests, one every 2 hours around the clock). | https://faucet.circle.com/ |
| 2 | **No account:** "There's no account required". **reCAPTCHA:** "This site is protected by reCAPTCHA". Nothing on the page says the limit is per IP. | https://faucet.circle.com/ |
| 3 | **Ethereum Sepolia is supported** (the dropdown lists 38 testnets, among them Ethereum Sepolia, Base Sepolia, Arbitrum Sepolia, OP Sepolia, Avalanche Fuji, Solana Devnet). The FAQ says a testnet not listed can be reached by moving USDC from Ethereum Sepolia with CCTP. | https://faucet.circle.com/ |
| 4 | **More than the limit:** "If you need more, you can submit a request on Circle's Discord" (https://discord.com/invite/buildoncircle). No amount or criterion is given. | https://faucet.circle.com/ |
| 5 | **The Developer Console faucet** (account-gated): the faucet page's FAQ says it also gives native tokens (ETH, POL) and **"only funds Circle Wallets addresses"**. **Its own documentation could not be read:** `developers.circle.com/wallets/developer-console-faucet`, `/w3s/developer-console-faucet`, `/w3s/docs/developer-console-faucet` and `/wallets/fund-a-testnet-wallet` all answer 307 to https://faucet.circle.com/. The amounts below come only from a search engine's index of those pages (older versions), so they are **not confirmed**: 20 USDC a request (an older version: 10), **one USDC request every 24 hours per testnet**, and **10 requests per developer account or team every 24 hours** across assets and testnets. | redirects checked 2026-11-18; values from the search index of https://developers.circle.com/wallets/developer-console-faucet |
| 6 | **Circle's faucet API** `POST /v1/faucet/drips` (body: `blockchain` such as `ETH-SEPOLIA`, `address`, `usdc`/`eurc`/`native`) needs an API key, and the page says calling it "requires upgrading to mainnet". It states no amounts or rate limits. | https://developers.circle.com/api-reference/wallets/programmable-wallets/request-testnet-tokens.md |
| 7 | **Automated use:** the faucet page has no terms of its own beyond Google's reCAPTCHA terms, and links Circle's Developer Terms and Service Terms. The Developer Terms (last updated 2026-09-16, §1(d)) say use is "subject to certain limitations on access, calls and use" and address attempts "to exceed or circumvent these limitations". The Console Service Terms (revised 2025-04-01, §2(a)(v)) forbid use "that circumvents a contractual usage limit" or works around "technical limitations of the Services". **Neither mentions the faucet, bots or scripts by name**; whether farming many addresses breaches them is Circle's reading, not stated. | https://console.circle.com/legal/developer-terms, https://console.circle.com/legal/service-terms |
| 8 | The Sepolia USDC contract is `0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238`; Circle says testnet USDC has no financial value. | https://developers.circle.com/stablecoins/usdc-contract-addresses |

**Where sources disagree:**
- The secondary guide L17 cites (eco.com, written 2026-10-19 from sources fetched 2026-10-13) gives the public faucet's limit as Circle's page does (20 USDC every 2 hours per address and chain, no account). It says the Console faucet's amount is not published and that it funds only Circle Wallets addresses. **Circle's live page agrees on the public faucet.** https://eco.com/support/en/articles/17593747-usdc-testnet-faucets-2026-sepolia-base-sepolia-arc-solana-devnet
- L17's "10–20 USDC a day" for the Console faucet is the old docs' 10 or 20 a request, one a day per testnet. It can't be checked today because the page redirects.
- One third-party list (seen only in search results) gives a one-hour interval for the same faucet. Circle's page says 2 hours.

**What the facts mean for spam:**
- **The limit is per address and per chain, not per person.** Addresses are free, so a spammer's income is 240 USDC a day times the addresses it runs, bounded only by the reCAPTCHA and its time. **One address can also collect on several testnets and move the USDC to Sepolia with CCTP** (fact 3), which multiplies the per-address limit without new addresses. This is inferred from Circle's page and was not tried.
- **The account-gated faucet funds only Circle Wallets addresses** (fact 5). That gates who requests, not where the USDC ends up: a Circle wallet can transfer USDC to any address. Developer accounts cost an email each.
- **USDC moves freely between addresses.** So a faucet limit bounds the spammer's money, not its identities: junk can still come from a fresh identity each time, funded from one wallet.

## Part 2: what the faucet costs each actor

The repository's values: `BOND_FLOOR` $100; the bond for a bounty is `BOND_FACTOR` (2) × its tier, the smallest step of the k table at or above it ($10, $25, $50, $125, $250, $312.50, $625; `pof/sim/openval/params.py`, #132 D2); the simulations bond every launch validator at **$1,250** (2 × $625, the largest bounty a panel of 5 or 7 judges at level A; `World.initial_bond`); the judges' fee D30 is **$5.03 a submission** (`nodeposit.JUDGE_FEE`); D29's reputation cap starts at $50 (reputation, not money: it costs nothing); the world's bounties have a median of $86 and a 90th percentile of $184, at most $625. One request = 20 USDC; one address, at most 12 requests a day (240 USDC); one Console account, 1 request a day (20 USDC, not confirmed, Part 1 fact 5).

| Actor | Needs (USDC) | Faucet requests | One address, at the limit (every 2 h, around the clock) | Notes |
|---|---|---|---|---|
| **Launch validator, bond $1,250** (the simulations' bond) | 1,250 | 63 | **5.3 days** (8 days at 8 requests a day, waking hours) | Can judge every bounty up to $625 |
| 7 validators at $1,250 | 8,750 | 438 | 5.3 days if each validator's address requests in parallel: 84 reCAPTCHAs a day | |
| **15 validators at $1,250** | 18,750 | 938 | 5.3 days in parallel: **180 reCAPTCHAs a day** | |
| Validator, bond $500 | 500 | 25 | 2.1 days | Bounties up to $250 |
| Validator, bond $250 | 250 | 13 | 1.1 days | Bounties up to $125 (about the world's 70th percentile) |
| Validator, `BOND_FLOOR` $100 | 100 | 5 | 10 hours | Bounties up to $50 only |
| **Honest newcomer's first fix** | 5.03 (the judges' fee) | **1** (covers 3 fixes) | at once | No deposit (#132: no solver's deposit); D29's $50 cap is reputation |
| **Funder's pledge**, the median bounty $86 | 86 | 5 | 10 hours | p90 $184: 10 requests (20 h); the largest $625: 32 (2.7 days) |
| **Spammer, 1 junk fix an hour** | 121 a day | **6 a day** | **one address**, at half its limit | Account-gated: 6 accounts |
| **Spammer, 10 junk fixes an hour** | 1,207 a day | **60 a day** | **6 addresses** at the limit (60 reCAPTCHAs a day), or one address on 6 testnets bridged by CCTP | Account-gated: 61 accounts |
| What one address yields at the limit | 240 a day | 12 a day | **2.0 junk fixes an hour** (48 a day) | |
| What one Console account yields | 20 a day | 1 a day | **0.17 junk fixes an hour** (4 a day) | |

Every actor also needs Sepolia ETH for gas, from other faucets; it isn't counted here.

**Can the faucet fund the launch validators' bonds? Not realistically at $1,250.** 7–15 bonds need 438–938 requests: five days of requests every two hours, around the clock, on 7–15 addresses (84–180 reCAPTCHAs a day), or a script that solves them, which Circle's terms arguably forbid (Part 1, fact 7). **The realistic routes are Circle's Discord** (the faucet's own answer for larger amounts, no amount promised), **or a lower testnet bond.** A lower bond is a lower bounty ceiling: at $250 a validator judges bounties up to $125, at the $100 floor only up to $50, so the deployment must keep its bounties under that (funders pay their pledges from the same faucet, so testnet bounties will be small anyway). On test coins a bond deters nothing either way (open problems 7.6); its testnet job is to exercise the flow.

**What a spammer's faucet request costs the owner.** Each junk fix is judged by a panel of 7 (k = 7 at 7 and 15 validators), and at the judges' fee of $5.03 one 20-USDC request buys 4 junk fixes, so **28 checks: $0.56–3.34 of the owner's real model money** at $0.02–0.12 a check (`validator-kit/COSTS.md`), against one reCAPTCHA for the spammer. The owner's model budget is $30–50 a month for all launch validators (#251), about $1.00–1.67 a day. **At the dearest call the honest load alone already exceeds it** (about 28 checks a day in v6's world, $101 a month). **At the cheapest call, 1–2 faucet requests a day by a spammer use up what the honest load leaves** ($13–33 a month). The faucet bounds the spam's rate; it doesn't make spam cost the spammer what it costs the validators.

## Part 3: simulation

### 3.1 The rule, the rows and the criterion, fixed before the 40-seed runs

**The switch** (`Spammer(usdc_day=...)` in `pof/sim/openval/capacity.py`, off (None) by default; it needs `JUDGE_FEE`): every submission pays the judges' fee ($5.03), honest ones included, as in v6's fee rows. The spammer pays it from a wallet that the faucet fills at `usdc_day` USDC a day, continuously, from 0 at the start (no stockpile). At each of its slots (Poisson at the intended rate), it picks an issue as before. If its wallet holds less than the fee, it skips the slot. So **the spam's rate is min(intended rate, income / fee)**, and the wallet carries over between slots. Junk still comes from a fresh identity each time: USDC moves freely, so the faucet limits money, not identities.

**The rows** (table `faucet`, 96 rows): the testnet's launch: **one repository, no repository cap** (L16, #132 task 13.8), capacity `MAX_CHECKS_PER_HOUR` = 5, **7 and 15 validators**, **Opus 5.5 and GPT-6.1 seated**. Three orders: **reputation first** (D32), **reputation first with a newcomer lane of 25 %** (#132 task 13.7 asks for 0 and 25 %), and **arrival order (FIFO)**. Spam intended at 1 and 10 junk fixes an hour, plus none. The spammer's faucet income, USDC a day:

| Income | Stands for | Junk an hour at $5.03 | Run at intended rate |
|---|---|---|---|
| 20 | **account-gated**: one Developer Console account (1 request a day) | 0.17 | 1 and 10 |
| 240 | **one address** at the public faucet's limit (12 requests a day) | 1.99 | 1 (doesn't bind: 1 an hour needs 121) and 10 |
| 480 | 2 addresses | 3.98 | 10 |
| 1,200 | 5 addresses | 9.94 | 10 |
| no limit | 6 or more addresses, or CCTP from other testnets (v6's fee rows) | 10 | 10 |

The fee and income enter only as their ratio, so the rows also read for other fees: at a fee of $20 (one request a submission), one address's 240 USDC gives 0.5 junk fixes an hour, between the first two rows.

**The world:** v6's A.1 world (`capacity.world`): report v5's base network, 30 honest fixes a week, 40 established honest solvers ($5,000 of reputation) and 10 newcomers (none), D29's cap, every validator bonded $1,250, 13 weeks, honest solvers withdraw after 14 days; junk is rejected by every judge and claims at most $50 under D29.

**Measured** (v6's metrics, plus): honest fixes' waits (median, p90), shares over 24 hours and withdrawn, for all and for newcomers apart; the junk's realised rate and the faucet requests a day it took (junk × $5.03 / 20); each validator's checks a day; **the owner's model spend a month**, every validator's checks together × 30 days × $0.02 and × $0.12 (the launch validators are all the owner's); whether the queue cleared in the last week.

**The criterion, v6's (fixed before its runs):** a cell **holds** when honest fixes waiting more than 24 hours are at most 5 % (mean + 2 SE) and those withdrawn at most 1 % (mean + 2 SE). It is judged for all honest fixes, and for the newcomers' apart (the question of #132 task 13.7).
- **An income level is enough for the queue** when, under reputation first (no lane), every cell at that income holds for all honest fixes and for newcomers: both seats, 7 and 15 validators, and each intended rate it is run at. The lane of 25 % is judged the same way, separately. FIFO is reported beside them.
- **An income level is within the owner's budget** when the owner's spend a month at $0.02 a check is at most $50 in every cell at that income. The spend at $0.12 is reported beside it.
- **The recommendation** names the largest income that is enough for the queue and within the budget, and translates it into the faucet's terms (accounts, addresses); if none is, it says so.

**What the arithmetic expects, written before the runs:** 7 validators at 5 an hour can draw 35 checks an hour, 5 panels of 7; 15 validators 10.7 panels. Honest fixes take about 0.2 panels an hour, audits and challenges a little more. **The queue should hold at 0.17, 1 and 2 junk fixes an hour everywhere, probably at 4 (80 % of 7 validators' capacity), and fail at 9.9–10 at 7 validators** (as v6), holding narrowly or not at all at 15. **The budget should fail at every income but the account-gated one:** the honest load alone is about 28–30 checks a day ($17 a month at $0.02, $101 at $0.12); each junk fix adds 7 checks, so 0.17 an hour adds about $17 a month at $0.02 (about $34 in all), one address's 2 an hour about $200.

**Seen before this section was fixed:** a smoke run of five rows on seed 1 (outside 41–80), to time the runs and check that the realised junk rate is income / fee. Nothing from seeds 41–80 was seen.

### 3.2 Results (40 seeds, 41–80; written after the runs)

**Headline: the faucet's limit keeps the queue moving against a spammer with up to two addresses at the limit, but no faucet income except the account-gated one keeps the owner's model spend within $50 a month.**

**The queue** (reputation first, no lane; the full table is in 3.4):

| Faucet income (USDC a day) | Stands for | Junk an hour | 7 validators: all / newcomers | 15 validators: all / newcomers |
|---|---|---|---|---|
| 20 | one Console account | 0.17 | holds / holds (nothing waits) | holds / holds |
| 240 | one address at the limit | 1.0 (intended 1) and 1.99 (intended 10) | holds / holds (nothing waits) | holds / holds |
| 480 | two addresses | 3.98 | holds / holds (newcomers' p90 wait 0.4–0.7 h) | holds / holds |
| 1,200 | five addresses | 9.90 | **fails / fails**: 9.4 ± 1.1 % (Opus 5.5) and 10.9 ± 1.1 % (GPT-6.1) of honest fixes withdrawn, 83–85 % of newcomers' | holds for all (2.5 ± 0.3 % and 3.7 ± 0.4 % over 24 h, none withdrawn) / **fails** for newcomers: 61–68 % wait over 24 h (median 31–35 h), none withdrawn |
| no limit | six or more addresses | 9.98 | **fails / fails** (as v6's grid, on fresh seeds: 9.7 ± 1.1 % and 11.2 ± 1.1 % withdrawn) | holds / **fails** (70–76 % of newcomers over 24 h, none withdrawn) |

- **By the rule fixed in 3.1, the largest income enough for the queue is 480 USDC a day** (both seats, 7 and 15 validators, both intended rates, all honest fixes and newcomers'). At the judges' fee of $5.03 that is about 4 junk fixes an hour, or 24 faucet requests a day: **two addresses requesting every two hours around the clock.** Five addresses (60 requests a day) fail at 7 validators.
- **Arrival order (FIFO) gives the same verdicts up to 480:** below the network's capacity nothing waits in either order. At 1,200 and above, FIFO fails for everyone (7 validators: 100 % over 24 hours, 89 % withdrawn; 15: 84–89 % over 24 hours, none withdrawn), as in v6.
- **The newcomer lane of 25 % is worse than no lane** (#132 task 13.7 asked for it), as v6's post hoc run found. It holds at 20 USDC a day only. At 7 validators it fails from one address (240 a day: 4.9 ± 0.8 % / 6.3 ± 0.9 % of honest fixes withdrawn, 58–63 % of newcomers'), and at 15 it fails from two (480). A lane of 25 % at 5 an hour draws 0.5 panels an hour at 7 validators, below one address's 2 junk fixes an hour, and newcomers queue in it behind the junk.
- **Established solvers never wait in any row** (0 % over 24 hours everywhere under reputation first).
- **The realised junk rate is income ÷ fee,** as designed: 0.17, 1.99, 3.98 and 9.90 junk fixes an hour for 20, 240, 480 and 1,200 USDC a day; 1.00 at the intended 1 an hour with 240 (it doesn't bind).

**The owner's model spend** (every validator's checks a day × 30 × $0.02 and × $0.12; all launch validators are the owner's):

| Faucet income (USDC a day) | Junk an hour | Owner's spend a month, 7 validators | 15 validators | Each validator's checks a day (7 / 15) |
|---|---|---|---|---|
| none (no spam) | 0 | **$17–105** | $18–109 | 4 / 2 |
| 20 (one Console account) | 0.17 | **$34–203** | $35–210 | 8 / 4 |
| 240 (one address), intended 1 an hour | 1.0 | $116–695 | $120–720 | 28 / 13 |
| 240 (one address) | 1.99 | $214–1,282 | $221–1,328 | 51 / 25 |
| 480 (two addresses) | 3.98 | $410–2,461 | $425–2,547 | 98 / 47 |
| 1,200 or no limit | 9.9–10 | $496–2,978 (capacity 5 binds: 118 a validator a day) | $972–5,834 | 118 / 108 |

- **By the rule fixed in 3.1, only the account-gated income is within the budget** ($34–35 a month at $0.02, under $50), and only at the cheapest model call. **One address at the public faucet costs the owner $214–221 a month at the cheapest call** and $1,282–1,328 at the dearest. **At $0.12 a check nothing is within the budget,** not even the honest load alone ($105–109 a month in this world of 30 honest fixes a week).
- **The lane caps spend** (33 checks a validator a day at 7 validators, $138–837 a month) by leaving the junk unjudged, and newcomers with it.
- **Capacity 5 is the only ceiling:** $496–2,978 a month at 7 validators and $972–5,834 at 15. More validators raise the ceiling, because each brings its own 5 an hour.

**So, by the rule fixed in 3.1:** the largest income that is enough for the queue **and** within the budget is **20 USDC a day, one account-gated identity.** No income from the public faucet is, since one address at its limit already costs the owner about four times the budget at the cheapest call.

### 3.3 What this recommends

**Is the faucet's cost enough for the launch?**
- **For keeping honest fixes moving: yes, against a casual spammer.** Up to two addresses at the limit (24 reCAPTCHAs a day, about 4 junk fixes an hour) leave every honest fix and every newcomer's fix served at 7 and 15 validators, with reputation first or FIFO. **No, against a determined one:** five addresses, or one address collecting on five testnets and bridging with CCTP (60 reCAPTCHAs a day, or a script), floods newcomers at 7 validators and makes them wait over a day at 15. That spammer pays nothing but time and reCAPTCHAs.
- **For the owner's model budget: no.** The faucet bounds the spam's rate, but each 20-USDC request buys about 28 checks of real model money ($0.56–3.34). One address at the limit costs the owner $214–1,328 a month against a budget of $30–50. The budget stop on each node is what will actually bind. When it binds, the owner's validators stop judging, and every fix waits. That is a stall, not a drain, but it is a stall that one person with one address can cause.
- **The account-gated case is not something the deployment can choose.** The public faucet needs no account and funds any address. The Console faucet funds only Circle Wallets addresses, and USDC moves freely between addresses. A spammer will use the public faucet.

**What bond and fee values on Sepolia make it work better** (the income and the fee enter only as their ratio, so these follow from the rows above without new runs):
- **A higher judges' fee on Sepolia: $20, one faucet request a submission.** One address then gives 0.5 junk fixes an hour (12 a day). The queue holds against up to about 8 addresses at the limit (4 an hour, the 480 row). One address costs the owner about 12 × 7 × $0.02 × 30 = **$50 a month at the cheapest call**, on top of the honest load's $17: about $67, over the budget. An honest newcomer's first fix still costs one request. **A fee of $40 (two requests a submission)** halves the spam again: one address adds $25 a month, about $42 in all, **within $50 at the cheapest call only**. A newcomer then needs two requests (two hours apart) for a first fix. The fee is paid to the validators in test USDC, so it does nothing for their real costs; it only lowers the spam's rate. Whether the deployment can set a fee other than D30's measured $5.03 is the owner's choice: on a test coin, D30's "fee covers the judges' cost" has no meaning anyway.
- **No newcomer lane at the launch** (it fails earlier than no lane here, as in v6).
- **A spend ceiling the budget can hold:** capacity 5 an hour allows $496–2,978 a month at 7 validators. The node's budget stop is the real ceiling. Nothing in D31 is a per-day or per-month cap. The owner should either accept the stall when the budget stop binds (named in the README and the paper) or fund a larger budget during the launch weeks, and watch the queue (L16).
- **Validator bonds:** the faucet can't realistically fund 7–15 bonds of $1,250 (438–938 requests). **Ask Circle on Discord** for 8,750–18,750 USDC (the faucet's own route, nothing promised), **or lower the testnet bond to $250** (13 requests, about a day for one address) and keep testnet bounties at or under $125, which the bond tiers then require. Funders pay pledges from the same faucet (5 requests for the median bounty), so small bounties are what a testnet will see anyway.

**Plainly:** the faucet makes casual spam cost something and keeps the queue moving against it. It does not protect the owner's model budget, and it does not stop a determined spammer with a handful of addresses. Even with a $40 fee on Sepolia, one address's spam fits the budget only at the cheapest model call, and two addresses don't. Heavy spam stays a named risk in the README and the paper (task 3.15's fallback). Whether that is enough for the launch is the owner's decision.

### Assumptions (in addition to v6's A.1)
- **The faucet income is continuous and starts at 0:** **chosen.** A real faucet pays 20 USDC every two hours per address and chain. **A stockpile is not simulated:** a spammer who farms before the launch can burst. Arithmetic: 10 addresses for a week give 16,800 USDC, about 3,300 junk fixes at $5.03. At 7 validators that is 3,300 × 7 / 35 ≈ 670 hours of capacity, so newcomers' fixes would queue behind it for about four weeks, past the 14-day withdrawal. Established solvers aren't affected under reputation first.
- **The income levels are assumed stand-ins:** 20 for a Console account (its value unconfirmed, Part 1 fact 5), 240 per address at the limit (Circle's page). A human requesting during waking hours gets about 160 a day per address. A script gets 240 per address per chain. CCTP from other testnets (inferred, not tried) multiplies it.
- **Every submission pays $5.03,** honest ones included (v6's fee rows). Honest solvers' faucet needs (one request covers three fixes) aren't simulated: they never bind.
- **The owner runs every launch validator,** so the owner's spend is every validator's checks. Model cost $0.02–0.12 a check (`validator-kit/COSTS.md`). The honest load is v6's world (30 fixes a week); the launch may see far fewer, which lowers the base but not the spam's cost.
- **Junk is rejected by every judge** and claims at most $50 under D29, from a fresh identity each time: as v6.

### What is not done
- **The faucet itself was not used,** and nothing was requested from it. The limits are what Circle's page states. Whether reCAPTCHA or other anti-abuse checks stop one person from running many addresses, and whether CCTP from other testnets works as inferred, are untested.
- **The Developer Console faucet's current limits:** its documentation redirects to the public faucet; the values are from a search index (Part 1, fact 5).
- **A fee other than $5.03, a stockpile, a lower bond, or a per-day spend cap:** argued from the rows (the income/fee ratio) or by arithmetic, not run.
- **The node's budget stop** (what happens when the owner's validators stop judging): not simulated. Every row here assumes the validators keep judging up to their capacity.

### 3.4 Appendix: the full table (mean ± 2 SE over seeds 41–80)
Printed by `--render` from the 40-seed results. "Faucet requests /day" is the junk × $5.03 / 20. The owner's spend is every validator's checks a day × 30 × $0.02 and × $0.12. "Holds" applies v6's criterion (mean + 2 SE) to all honest fixes and to newcomers' apart; a newcomer's wait is a lower bound when the fix was withdrawn (336 hours = 14 days). Junk an hour is the realised rate.

#### Table `faucet` (mean ± 2 SE over 40 seeds)

| Seat | Validators | Order | Spam intended /h | Faucet USDC /day | Junk /h | Faucet requests /day | All > 24 h (%) | All withdrawn (%) | Newcomers > 24 h / withdrawn (%) | Newcomers wait median / p90 (h) | Established > 24 h (%) | Checks / validator / day | Owner's spend $/month (all validators) | Cleared (% of seeds) | Holds: all / newcomers |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Opus 5.5 | 7 | reputation | 0 | – | 0.00 ± 0.00 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 4 ± 0 | 17–105 | 100 ± 0 | yes / yes |
| Opus 5.5 | 7 | reputation | 1 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 8 ± 0 | 34–203 | 100 ± 0 | yes / yes |
| Opus 5.5 | 7 | reputation | 1 | 240 | 1.00 ± 0.01 | 6.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 28 ± 0 | 116–695 | 100 ± 0 | yes / yes |
| Opus 5.5 | 7 | reputation | 10 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 8 ± 0 | 34–203 | 100 ± 0 | yes / yes |
| Opus 5.5 | 7 | reputation | 10 | 240 | 1.99 ± 0.00 | 12.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 51 ± 0 | 214–1,282 | 100 ± 0 | yes / yes |
| Opus 5.5 | 7 | reputation | 10 | 480 | 3.98 ± 0.00 | 24.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.7 ± 0.5 | 0.0 ± 0.0 | 98 ± 0 | 410–2,461 | 100 ± 0 | yes / yes |
| Opus 5.5 | 7 | reputation | 10 | 1,200 | 9.90 ± 0.01 | 59.8 ± 0.1 | 11.0 ± 1.1 | 9.4 ± 1.1 | 100.0 ± 0.0 / 83.4 ± 3.9 | 335.2 ± 1.7 / 336.0 ± 0.0 | 0.0 ± 0.0 | 118 ± 0 | 496–2,978 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | reputation | 10 | no limit | 9.98 ± 0.02 | 60.2 ± 0.1 | 11.2 ± 1.1 | 9.7 ± 1.1 | 100.0 ± 0.0 / 84.4 ± 3.8 | 335.4 ± 1.2 / 336.2 ± 0.4 | 0.0 ± 0.0 | 118 ± 0 | 496–2,978 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | reputation, lane 25 % | 0 | – | 0.00 ± 0.00 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 4 ± 0 | 17–105 | 100 ± 0 | yes / yes |
| Opus 5.5 | 7 | reputation, lane 25 % | 1 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.1 ± 0.1 | 0.0 ± 0.0 | 8 ± 0 | 34–203 | 100 ± 0 | yes / yes |
| Opus 5.5 | 7 | reputation, lane 25 % | 1 | 240 | 1.00 ± 0.01 | 6.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 1.0 ± 0.2 / 4.4 ± 0.8 | 0.0 ± 0.0 | 28 ± 0 | 116–695 | 100 ± 0 | yes / yes |
| Opus 5.5 | 7 | reputation, lane 25 % | 10 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.1 | 0.0 ± 0.0 | 8 ± 0 | 34–203 | 100 ± 0 | yes / yes |
| Opus 5.5 | 7 | reputation, lane 25 % | 10 | 240 | 1.99 ± 0.00 | 12.0 ± 0.0 | 7.8 ± 0.9 | 4.9 ± 0.8 | 100.0 ± 0.0 / 58.3 ± 5.4 | 320.5 ± 12.4 / 335.6 ± 0.9 | 0.0 ± 0.0 | 33 ± 0 | 139–837 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | reputation, lane 25 % | 10 | 480 | 3.98 ± 0.00 | 24.0 ± 0.0 | 14.6 ± 1.2 | 14.6 ± 1.2 | 100.0 ± 0.0 / 100.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 0.0 ± 0.0 | 33 ± 0 | 138–830 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | reputation, lane 25 % | 10 | 1,200 | 9.90 ± 0.01 | 59.8 ± 0.1 | 18.3 ± 0.9 | 18.3 ± 0.9 | 100.0 ± 0.0 / 100.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 0.0 ± 0.0 | 33 ± 0 | 138–827 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | reputation, lane 25 % | 10 | no limit | 9.98 ± 0.02 | 60.2 ± 0.1 | 18.4 ± 0.9 | 18.4 ± 0.9 | 100.0 ± 0.0 / 100.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 0.0 ± 0.0 | 33 ± 0 | 138–827 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | FIFO | 0 | – | 0.00 ± 0.00 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 4 ± 0 | 17–105 | 100 ± 0 | yes / – |
| Opus 5.5 | 7 | FIFO | 1 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 8 ± 0 | 34–203 | 100 ± 0 | yes / – |
| Opus 5.5 | 7 | FIFO | 1 | 240 | 1.00 ± 0.01 | 6.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 28 ± 0 | 116–695 | 100 ± 0 | yes / – |
| Opus 5.5 | 7 | FIFO | 10 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 8 ± 0 | 34–203 | 100 ± 0 | yes / – |
| Opus 5.5 | 7 | FIFO | 10 | 240 | 1.99 ± 0.00 | 12.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 51 ± 0 | 214–1,282 | 100 ± 0 | yes / – |
| Opus 5.5 | 7 | FIFO | 10 | 480 | 3.98 ± 0.00 | 24.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 98 ± 0 | 410–2,461 | 100 ± 0 | yes / – |
| Opus 5.5 | 7 | FIFO | 10 | 1,200 | 9.90 ± 0.01 | 59.8 ± 0.1 | 100.0 ± 0.0 | 88.7 ± 0.5 | – | – | – | 118 ± 0 | 496–2,978 | 0 ± 0 | **no** / – |
| Opus 5.5 | 7 | FIFO | 10 | no limit | 9.98 ± 0.02 | 60.2 ± 0.1 | 100.0 ± 0.0 | 89.3 ± 0.5 | – | – | – | 118 ± 0 | 496–2,978 | 0 ± 0 | **no** / – |
| Opus 5.5 | 15 | reputation | 0 | – | 0.00 ± 0.00 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 2 ± 0 | 18–109 | 100 ± 0 | yes / yes |
| Opus 5.5 | 15 | reputation | 1 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 4 ± 0 | 35–210 | 100 ± 0 | yes / yes |
| Opus 5.5 | 15 | reputation | 1 | 240 | 1.00 ± 0.01 | 6.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 13 ± 0 | 120–720 | 100 ± 0 | yes / yes |
| Opus 5.5 | 15 | reputation | 10 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 4 ± 0 | 35–210 | 100 ± 0 | yes / yes |
| Opus 5.5 | 15 | reputation | 10 | 240 | 1.99 ± 0.00 | 12.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 25 ± 0 | 221–1,328 | 100 ± 0 | yes / yes |
| Opus 5.5 | 15 | reputation | 10 | 480 | 3.98 ± 0.00 | 24.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 47 ± 0 | 425–2,547 | 100 ± 0 | yes / yes |
| Opus 5.5 | 15 | reputation | 10 | 1,200 | 9.90 ± 0.01 | 59.8 ± 0.1 | 2.5 ± 0.3 | 0.0 ± 0.0 | 60.8 ± 5.0 / 0.0 ± 0.0 | 31.0 ± 3.2 / 69.1 ± 7.0 | 0.0 ± 0.0 | 108 ± 0 | 972–5,833 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | reputation | 10 | no limit | 9.98 ± 0.02 | 60.2 ± 0.1 | 2.9 ± 0.4 | 0.0 ± 0.0 | 70.3 ± 5.5 / 0.0 ± 0.0 | 38.2 ± 4.9 / 81.2 ± 9.2 | 0.0 ± 0.0 | 108 ± 0 | 972–5,834 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | reputation, lane 25 % | 0 | – | 0.00 ± 0.00 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 2 ± 0 | 18–109 | 100 ± 0 | yes / yes |
| Opus 5.5 | 15 | reputation, lane 25 % | 1 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 4 ± 0 | 35–210 | 100 ± 0 | yes / yes |
| Opus 5.5 | 15 | reputation, lane 25 % | 1 | 240 | 1.00 ± 0.01 | 6.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.3 ± 0.1 | 0.0 ± 0.0 | 13 ± 0 | 120–720 | 100 ± 0 | yes / yes |
| Opus 5.5 | 15 | reputation, lane 25 % | 10 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 4 ± 0 | 35–210 | 100 ± 0 | yes / yes |
| Opus 5.5 | 15 | reputation, lane 25 % | 10 | 240 | 1.99 ± 0.00 | 12.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 | 25 ± 0 | 221–1,328 | 100 ± 0 | yes / yes |
| Opus 5.5 | 15 | reputation, lane 25 % | 10 | 480 | 3.98 ± 0.00 | 24.0 ± 0.0 | 7.4 ± 0.8 | 4.5 ± 0.7 | 100.0 ± 0.0 / 57.4 ± 4.6 | 318.2 ± 12.1 / 336.0 ± 0.0 | 0.0 ± 0.0 | 31 ± 0 | 275–1,650 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | reputation, lane 25 % | 10 | 1,200 | 9.90 ± 0.01 | 59.8 ± 0.1 | 16.0 ± 1.2 | 16.0 ± 1.2 | 100.0 ± 0.0 / 100.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 0.0 ± 0.0 | 30 ± 0 | 274–1,644 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | reputation, lane 25 % | 10 | no limit | 9.98 ± 0.02 | 60.2 ± 0.1 | 16.2 ± 1.2 | 16.2 ± 1.2 | 100.0 ± 0.0 / 100.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 0.0 ± 0.0 | 30 ± 0 | 274–1,644 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | FIFO | 0 | – | 0.00 ± 0.00 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 2 ± 0 | 18–109 | 100 ± 0 | yes / – |
| Opus 5.5 | 15 | FIFO | 1 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 4 ± 0 | 35–210 | 100 ± 0 | yes / – |
| Opus 5.5 | 15 | FIFO | 1 | 240 | 1.00 ± 0.01 | 6.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 13 ± 0 | 120–720 | 100 ± 0 | yes / – |
| Opus 5.5 | 15 | FIFO | 10 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 4 ± 0 | 35–210 | 100 ± 0 | yes / – |
| Opus 5.5 | 15 | FIFO | 10 | 240 | 1.99 ± 0.00 | 12.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 25 ± 0 | 221–1,328 | 100 ± 0 | yes / – |
| Opus 5.5 | 15 | FIFO | 10 | 480 | 3.98 ± 0.00 | 24.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 47 ± 0 | 425–2,547 | 100 ± 0 | yes / – |
| Opus 5.5 | 15 | FIFO | 10 | 1,200 | 9.90 ± 0.01 | 59.8 ± 0.1 | 84.4 ± 1.3 | 0.0 ± 0.0 | – | – | – | 108 ± 0 | 972–5,831 | 0 ± 0 | **no** / – |
| Opus 5.5 | 15 | FIFO | 10 | no limit | 9.98 ± 0.02 | 60.2 ± 0.1 | 88.8 ± 1.7 | 0.0 ± 0.0 | – | – | – | 108 ± 0 | 972–5,832 | 0 ± 0 | **no** / – |
| GPT-6.1 | 7 | reputation | 0 | – | 0.00 ± 0.00 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 4 ± 0 | 17–105 | 100 ± 0 | yes / yes |
| GPT-6.1 | 7 | reputation | 1 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 8 ± 0 | 34–203 | 100 ± 0 | yes / yes |
| GPT-6.1 | 7 | reputation | 1 | 240 | 1.00 ± 0.01 | 6.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 28 ± 0 | 116–695 | 100 ± 0 | yes / yes |
| GPT-6.1 | 7 | reputation | 10 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 8 ± 0 | 34–203 | 100 ± 0 | yes / yes |
| GPT-6.1 | 7 | reputation | 10 | 240 | 1.99 ± 0.00 | 12.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 51 ± 0 | 214–1,282 | 100 ± 0 | yes / yes |
| GPT-6.1 | 7 | reputation | 10 | 480 | 3.98 ± 0.00 | 24.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.4 ± 0.0 | 0.0 ± 0.0 | 98 ± 0 | 410–2,461 | 100 ± 0 | yes / yes |
| GPT-6.1 | 7 | reputation | 10 | 1,200 | 9.90 ± 0.01 | 59.8 ± 0.1 | 12.6 ± 1.1 | 10.9 ± 1.1 | 100.0 ± 0.0 / 85.1 ± 3.1 | 336.0 ± 0.0 / 336.0 ± 0.0 | 0.0 ± 0.0 | 118 ± 0 | 496–2,978 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | reputation | 10 | no limit | 9.98 ± 0.02 | 60.2 ± 0.1 | 12.9 ± 1.1 | 11.2 ± 1.1 | 100.0 ± 0.0 / 86.2 ± 2.9 | 336.0 ± 0.0 / 336.0 ± 0.0 | 0.0 ± 0.0 | 118 ± 0 | 496–2,978 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | reputation, lane 25 % | 0 | – | 0.00 ± 0.00 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 4 ± 0 | 17–105 | 100 ± 0 | yes / yes |
| GPT-6.1 | 7 | reputation, lane 25 % | 1 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.1 ± 0.1 | 0.0 ± 0.0 | 8 ± 0 | 34–203 | 100 ± 0 | yes / yes |
| GPT-6.1 | 7 | reputation, lane 25 % | 1 | 240 | 1.00 ± 0.01 | 6.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 1.0 ± 0.2 / 4.1 ± 0.5 | 0.0 ± 0.0 | 28 ± 0 | 116–695 | 100 ± 0 | yes / yes |
| GPT-6.1 | 7 | reputation, lane 25 % | 10 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.1 | 0.0 ± 0.0 | 8 ± 0 | 34–203 | 100 ± 0 | yes / yes |
| GPT-6.1 | 7 | reputation, lane 25 % | 10 | 240 | 1.99 ± 0.00 | 12.0 ± 0.0 | 9.6 ± 0.9 | 6.3 ± 0.9 | 100.0 ± 0.0 / 63.2 ± 4.5 | 327.6 ± 9.2 / 336.0 ± 0.1 | 0.0 ± 0.0 | 33 ± 0 | 139–835 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | reputation, lane 25 % | 10 | 480 | 3.98 ± 0.00 | 24.0 ± 0.0 | 15.9 ± 1.1 | 15.9 ± 1.1 | 100.0 ± 0.0 / 100.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 0.0 ± 0.0 | 33 ± 0 | 138–829 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | reputation, lane 25 % | 10 | 1,200 | 9.90 ± 0.01 | 59.8 ± 0.1 | 18.5 ± 0.9 | 18.5 ± 0.9 | 100.0 ± 0.0 / 100.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 0.0 ± 0.0 | 33 ± 0 | 138–826 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | reputation, lane 25 % | 10 | no limit | 9.98 ± 0.02 | 60.2 ± 0.1 | 18.6 ± 0.9 | 18.6 ± 0.9 | 100.0 ± 0.0 / 100.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 0.0 ± 0.0 | 33 ± 0 | 138–826 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | FIFO | 0 | – | 0.00 ± 0.00 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 4 ± 0 | 17–105 | 100 ± 0 | yes / – |
| GPT-6.1 | 7 | FIFO | 1 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 8 ± 0 | 34–203 | 100 ± 0 | yes / – |
| GPT-6.1 | 7 | FIFO | 1 | 240 | 1.00 ± 0.01 | 6.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 28 ± 0 | 116–695 | 100 ± 0 | yes / – |
| GPT-6.1 | 7 | FIFO | 10 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 8 ± 0 | 34–203 | 100 ± 0 | yes / – |
| GPT-6.1 | 7 | FIFO | 10 | 240 | 1.99 ± 0.00 | 12.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 51 ± 0 | 214–1,282 | 100 ± 0 | yes / – |
| GPT-6.1 | 7 | FIFO | 10 | 480 | 3.98 ± 0.00 | 24.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 98 ± 0 | 410–2,461 | 100 ± 0 | yes / – |
| GPT-6.1 | 7 | FIFO | 10 | 1,200 | 9.90 ± 0.01 | 59.8 ± 0.1 | 100.0 ± 0.0 | 88.7 ± 0.5 | – | – | – | 118 ± 0 | 496–2,978 | 0 ± 0 | **no** / – |
| GPT-6.1 | 7 | FIFO | 10 | no limit | 9.98 ± 0.02 | 60.2 ± 0.1 | 100.0 ± 0.0 | 89.3 ± 0.5 | – | – | – | 118 ± 0 | 496–2,978 | 0 ± 0 | **no** / – |
| GPT-6.1 | 15 | reputation | 0 | – | 0.00 ± 0.00 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 2 ± 0 | 18–109 | 100 ± 0 | yes / yes |
| GPT-6.1 | 15 | reputation | 1 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 4 ± 0 | 35–210 | 100 ± 0 | yes / yes |
| GPT-6.1 | 15 | reputation | 1 | 240 | 1.00 ± 0.01 | 6.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 13 ± 0 | 120–720 | 100 ± 0 | yes / yes |
| GPT-6.1 | 15 | reputation | 10 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 4 ± 0 | 35–210 | 100 ± 0 | yes / yes |
| GPT-6.1 | 15 | reputation | 10 | 240 | 1.99 ± 0.00 | 12.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 25 ± 0 | 221–1,328 | 100 ± 0 | yes / yes |
| GPT-6.1 | 15 | reputation | 10 | 480 | 3.98 ± 0.00 | 24.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 47 ± 0 | 425–2,547 | 100 ± 0 | yes / yes |
| GPT-6.1 | 15 | reputation | 10 | 1,200 | 9.90 ± 0.01 | 59.8 ± 0.1 | 3.7 ± 0.4 | 0.0 ± 0.0 | 67.9 ± 4.7 / 0.0 ± 0.0 | 35.3 ± 3.6 / 78.9 ± 6.8 | 0.0 ± 0.0 | 108 ± 0 | 972–5,833 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 15 | reputation | 10 | no limit | 9.98 ± 0.02 | 60.2 ± 0.1 | 4.2 ± 0.4 | 0.0 ± 0.0 | 75.6 ± 4.9 / 0.0 ± 0.0 | 42.9 ± 4.7 / 91.5 ± 8.6 | 0.0 ± 0.0 | 108 ± 0 | 972–5,834 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 15 | reputation, lane 25 % | 0 | – | 0.00 ± 0.00 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 2 ± 0 | 18–109 | 100 ± 0 | yes / yes |
| GPT-6.1 | 15 | reputation, lane 25 % | 1 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 4 ± 0 | 35–210 | 100 ± 0 | yes / yes |
| GPT-6.1 | 15 | reputation, lane 25 % | 1 | 240 | 1.00 ± 0.01 | 6.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.1 | 0.0 ± 0.0 | 13 ± 0 | 120–720 | 100 ± 0 | yes / yes |
| GPT-6.1 | 15 | reputation, lane 25 % | 10 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 4 ± 0 | 35–210 | 100 ± 0 | yes / yes |
| GPT-6.1 | 15 | reputation, lane 25 % | 10 | 240 | 1.99 ± 0.00 | 12.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 | 25 ± 0 | 221–1,328 | 100 ± 0 | yes / yes |
| GPT-6.1 | 15 | reputation, lane 25 % | 10 | 480 | 3.98 ± 0.00 | 24.0 ± 0.0 | 9.2 ± 0.8 | 5.9 ± 0.8 | 100.0 ± 0.0 / 61.9 ± 4.1 | 325.2 ± 10.2 / 336.0 ± 0.0 | 0.0 ± 0.0 | 31 ± 0 | 275–1,649 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | reputation, lane 25 % | 10 | 1,200 | 9.90 ± 0.01 | 59.8 ± 0.1 | 16.7 ± 1.2 | 16.7 ± 1.2 | 100.0 ± 0.0 / 100.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 0.0 ± 0.0 | 30 ± 0 | 274–1,643 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | reputation, lane 25 % | 10 | no limit | 9.98 ± 0.02 | 60.2 ± 0.1 | 16.8 ± 1.2 | 16.8 ± 1.2 | 100.0 ± 0.0 / 100.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 0.0 ± 0.0 | 30 ± 0 | 274–1,643 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | FIFO | 0 | – | 0.00 ± 0.00 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 2 ± 0 | 18–109 | 100 ± 0 | yes / – |
| GPT-6.1 | 15 | FIFO | 1 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 4 ± 0 | 35–210 | 100 ± 0 | yes / – |
| GPT-6.1 | 15 | FIFO | 1 | 240 | 1.00 ± 0.01 | 6.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 13 ± 0 | 120–720 | 100 ± 0 | yes / – |
| GPT-6.1 | 15 | FIFO | 10 | 20 | 0.17 ± 0.00 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 4 ± 0 | 35–210 | 100 ± 0 | yes / – |
| GPT-6.1 | 15 | FIFO | 10 | 240 | 1.99 ± 0.00 | 12.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 25 ± 0 | 221–1,328 | 100 ± 0 | yes / – |
| GPT-6.1 | 15 | FIFO | 10 | 480 | 3.98 ± 0.00 | 24.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | – | – | 47 ± 0 | 425–2,547 | 100 ± 0 | yes / – |
| GPT-6.1 | 15 | FIFO | 10 | 1,200 | 9.90 ± 0.01 | 59.8 ± 0.1 | 84.4 ± 1.3 | 0.0 ± 0.0 | – | – | – | 108 ± 0 | 972–5,831 | 0 ± 0 | **no** / – |
| GPT-6.1 | 15 | FIFO | 10 | no limit | 9.98 ± 0.02 | 60.2 ± 0.1 | 88.8 ± 1.7 | 0.0 ± 0.0 | – | – | – | 108 ± 0 | 972–5,832 | 0 ± 0 | **no** / – |
