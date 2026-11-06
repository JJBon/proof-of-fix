# Design

## Context

The simulation (`pof/`) is the reference: every rule of the race lives in `pof/market.py`, with its tests and acceptance runs. The contract reproduces it on-chain, with the owner's decisions on #15, #56 and #59. It's a prototype, never deployed outside a local chain.

## Decisions

### D1. Toolchain and layout
- **Foundry:** forge for build and tests, anvil as the chain. Run from the official Foundry image, pinned by digest at task 1.1, in a container with the repository mounted. Nothing is installed on the host.
- **Libraries:** forge-std, plus OpenZeppelin's audited ERC-20 helpers (`SafeERC20`) and ECDSA. Vendored at pinned commits under `contracts/lib/`, so builds don't fetch anything.
- **Layout:**

| Contract | Role |
|---|---|
| `contracts/src/Baskets.sol` | per-coin escrow, received-amount accounting, pull payouts, the invariants and withdraw-only mode, caps |
| `contracts/src/Race.sol` | registration, the rising price, attempts, commit-reveal submissions, results, appeals, merge, instalments, clawback |
| `contracts/src/Oracles.sol` | registered oracle keys and the quorum check on signed results |
| `contracts/test/` | Foundry tests: unit tests, an invariant (fuzz) suite, and the replay of simulation events |
| `contracts/test/mocks/` | mock coins: plain, frozen, fee-on-transfer, and a stand-in for the contract token |

### D2. Numbers
- Amounts are integers in each coin's smallest unit. The simulation's micro-credits map to a mock coin with 6 decimals, so replayed amounts are identical.
- Shares are basis points, as in `pof` (BPS = 10,000), with the same rounding (down, the remainder to the last party). The replay test catches any drift.
- Days come from block timestamps: day = (timestamp − deployment) / 86,400.

### D3. One signed result per submission
- The oracle network checks CI, the constitution's gates and the juries off-chain, with the prompt-injection defenses (free text stripped, structured inputs, three providers agreeing). It posts one result: (bounty, submission hash, passed, reason), signed by registered oracle keys, at least the published quorum.
- One aggregated signature set per result keeps the gas per submission low (#56 item 10).
- Merges, upheld challenges and appeal verdicts arrive the same way.
- **As built (task 3.1):**
  - **The keys:** the oracle keys and the quorum are constructor arguments, fixed for the version (D15). The quorum must be more than half the keys, so two conflicting results can't both reach it.
  - **Who relays:** anyone. There's no oracle address any more; the signatures are what count.
  - **What's signed:** an EIP-712 digest over the domain (name, version, chain id, this contract), the action's type, every argument (fees and their recipients included) and a nonce the oracles choose.
    - A result names its submission and that submission's bounty.
    - A merge names the winning submission, so a merge signed for an earlier winner can't merge a later one.
    - An upheld challenge names its award's epoch.
  - **Taken once:** each digest is marked used.
  - **The signatures:** ordered by signer address, strictly increasing, so no key counts twice. OpenZeppelin's ECDSA refuses malleable signatures.
  - **Gas:** about 38,000 more per result at 2-of-3, of which about 22,000 is marking the digest used; each further signature adds about 8,100. A result costs about 189,000 at 2-of-3 and 197,000 at 3-of-5.

### D4. Ordering by commitment
- A solver commits `keccak256(fix hash, salt, solver)`, paying the attempt fee. This is the race's attempt; the first commitment locks the price.
- It reveals to the oracles off-chain, and its result names the commitment.
- **The winner is the passing submission with the earliest commitment.** Results that arrive out of order don't change that: the bounty is won only once every earlier commitment has a result or has timed out.

### D5. Baskets
- Each bounty keeps `balance[coin]`. A pledge is credited with the balance difference measured around the transfer; less than sent is refused (fee-on-transfer, rebasing).
- **The price is a share of every coin,** so the race needs no price feed.
- **The market chooses the coins (owner, 2026-10-26):** it's in the poster's and funders' interest to put up a reward coin solvers want, and the contract token's emission (#58) adds its own incentive. The contract has no rule about which coins a bounty should hold or which bounties matter: solvers prioritize, and what nobody takes sunsets (D11). The only coin rules are mechanical safety (received amounts, decimals for the caps, per-coin withdraw-only).
- **Payouts and refunds** are credits per (recipient, coin), pulled with `withdraw(coin)`. A failed transfer leaves the credit in place.
- **A coin that can't pay out (owner, 2026-10-26, replacing "a funder can take back or swap it"):** a credit is pulled to any address its owner names, so an address frozen by an issuer names another. A coin paused for everyone stays claimable, and anyone (a funder, usually) can offer the credit's owner another coin for it; the owner accepts or not (`offerSwap`, `acceptSwap`). No price feed, and no contract rule deciding that a coin "can't pay".
- **Nothing loops over a bounty's coins or funders:** the race pays exact amounts out of a pot, and refunds are pulled per coin (`claimRefund`). Each funder gets its share rounded down; the funder with the highest address gets the remainder once every funder is refunded, as in pof's `_refund_inputs` (the replay assigns addresses in the simulation's name order). So junk coins and dust pledges can't run a payout out of gas.
- **Caps count whole coins** (scaled by each coin's decimals): without a price feed they can't count value. A coin without `decimals()`, or with more than 30, is refused.
- **The contract token:** in phase 1, a mock ERC-20 accepted like any coin. Minting comes with #58.
- **Fee coins (owner, 2026-10-26):** the race's fees and deposits (registration, attempt, late fee, check deposits) are amounts, not shares, so they're paid in fee coins: a short list fixed at deployment (stablecoins the oracle networks accept), any of them at the payer's choice, amounts in whole coins. No admin changes the list; a new list is a new deployment.

### D6. Safety without a key
- **The invariant:** for every coin, the contract's balance ≥ the sum of credits owed plus the open bounties' balances. It's checked before any payout, and by an anyone-can-call `check()`.
- **On failure, that coin's** `withdrawOnly[coin]` is set forever (owner, 2026-10-26, replacing contract-wide): pledges, fees and payouts in it are refused, its pots refund to their funders, its credits are still pulled, and the other coins carry on. With any coin allowed, a hostile issuer can break its own coin's invariant; per coin, that stops only its coin.
- **Caps** are fixed at deployment, per bounty and in total. For the prototype: the mock coins' equivalent of 1,000 and 100,000 credits.
- **The invariant suite** (Foundry fuzzing over random sequences of calls) checks that solvency never breaks without the mode switching on.

### D7. Replaying the simulation
- **Exporter:** `python3 -m pof.sim market run --export-events` writes a run's race events in ledger order as JSON. Each event has its day, kind, accounts, amounts and outcomes, with oracle outcomes resolved by the simulation.
- **Replay:** a Foundry test reads that file with `vm.readFile` and `vm.parseJson`, replays it with test keys signing the oracle results, and compares every account's balances with the simulation's. Small seeds and short runs keep it fast.
- **The criterion is exact equality.** A mismatch names the first event where the balances diverge.
- **As built (task 2.6):**
  - **The command** is `python3 -m pof.sim market run --weeks 2 --seed N --export-events > contracts/test/data/race-N.json`. It prints to stdout, like every report, because `pof/` opens no files.
  - **Recording:** the exporter (`pof/sim/export.py`) wraps the market's methods during the run. Each call that moves money, or that the contract tracks (an attempt that stops), becomes one event with the ledger entries it made. A submission and its same-day result are one event, with its oracle fees as `Fee[]`. A merge is emitted on the day pof moves the escrow.
  - **Columns:** every table is one array of numbers per field, because `vm.parseJson` doesn't decode an object's fields in a dependable order.
  - **What's compared:**
    - each account's wallet plus credits, against pof's entries in scope;
    - each pot, against pof's bounty account plus its escrow;
    - the race's deposits, against the issue stakes and submissions.
  - **Left out:** validator stakes, checkers' bonds and reputation, which the contract doesn't have.
  - **Unmapped flows:** any money movement the exporter can't map raises.
  - **Result:** seeds 1, 2, 3, 4, 8, 9, 10, 15 and 60 replay to identical balances. Seed 8 has late submissions, 10 has three appealed split rejections, 15 an appealed failure, and 60 a duplicate and its appeal.
- **Rule alignment (owner, 2026-10-29),** from the differences the replay found:
  - **A split rejection is appealable on-chain**, like a failure, once (`Race.appeal`). In the simulation 70 % of split rejections were good fixes, and an appeal saved half of them (40 seeds); without it, about 7 % of paid bounties' fixes would go unpaid to their authors.
  - **A late or duplicate submission needs the whole fee:** the simulation refuses it, nothing charged, when the solver can't cover the evaluation fee (late) or the check deposit (rejected unchecked), as the contract does. It took what the solver had before.
  - **A duplicate doesn't restart the idle clock:** on-chain, a commit ends its attempt without restarting it, and a checked failure (`Fail` or `Split`) restarts it with its result, as in the simulation. Repeating a duplicate can't keep a dead bounty from its sunset.
  - **Attempts don't restart it either:** the clock counts from the bounty's opening, reopening or last checked submission. On-chain, `sunset` ignores attempts in progress and a stop never restarts the clock (`attemptDays` and `lastAttempt` are gone); in the simulation, `close_idle` ignores attempts and `race_stop` leaves the clock alone, and an attempt finishing after the sunset is refused, as the contract refuses its commit. Before, an attempt every 14 days for the 0.5 fee kept a bounty open forever. No exported seed in 1-120 changes; the unit tests on both sides cover it.
  - **With no treasury (`CONTRACT`), an issue nobody pledged for opens at once**, as the registration check opens it on-chain, and sunsets if nobody funds or attempts it; before, it waited for a treasury that isn't there and its stake returned at 14 days. A bundle, which the contract doesn't have, still waits. The default runs (with a treasury) are unchanged: a 2-seed `market accept` is byte-identical to main.

### D8. Phases
1. Money (Baskets, Race without signatures: a mock oracle contract stands in), with unit, invariant and replay tests.
2. Signed results (Oracles), with the quorum.
3. `quote()` and a CLI (`contracts/script/quote`).
4. The contract's own repo as its first bounty target, against a local Forgejo test repository, with a small bot that opens bounties from labelled issues.
5. The token and migration (D15).

**As built, phase 3 (task 3.2):**
- **`Quoter.quote(race, bounty, coin)`** is a separate lens with no state, not a function of Race. Race was already 26,394 bytes after phase 2, above EIP-170's 24,576, and the lens reads only Race's public views, so anyone can deploy their own copy. It returns:
  - the state, the share on offer (rising, or locked by the first attempt), the cap and the price;
  - the instalments, with the last one's remainder;
  - the finder's fee, the attempts in progress, and the sunset day (D11);
  - the fees in micro-units of a fee coin.
- **Matched to the simulation:** pof's `Market.quote` is the same reading. The exporter records it after every event of the replay runs, and `Replay.t.sol` checks it against the lens on all the replay seeds, to the micro-credit.
- **The CLI:** `scripts/contracts.sh quote` runs `contracts/script/Quote.s.sol` in the offline container. With no arguments it's a demo on a throwaway chain; `--sig 'quote(address,uint256,address)'` reads a deployed Race over `--rpc-url`. Nothing is broadcast.
- **Open:** Race has to fit under EIP-170 before it can be deployed on any public chain. Today only forge's own simulation and an anvil without the size limit take it.

**As built, phase 4 (task 3.3):** `scripts/bounty-loop.sh` runs one issue through the whole loop on this machine, then removes its containers.
- **Local only (rule 1):**
  - a throwaway anvil runs in the pinned Foundry image with no network at all, and the bot reaches it with `docker exec`;
  - a throwaway Forgejo 11 LTS (pinned by digest) is bound to 127.0.0.1, offline, with registration, federation, mail and update checks off;
  - fixes are tested in a pinned Python image with no network, read-only;
  - every key is one of anvil's public test keys.

  The anvil lifts EIP-170's size limit, as above.
- **The loop (`bot/`):**
  - the maintainer labels an issue `bounty`, and the bot registers it from the reporter's wallet;
  - the oracle stand-in (task 3.1's test keys, quorum 2 of 3) signs the registration check, and a funder pledges;
  - a first solver reads the quote, attempts, commits a sealed submission and opens a pull request; the stand-in runs the repository's tests plus the issue's hidden acceptance test, and signs a failing result, so the bounty stays open;
  - a second solver's fix passes, the protocol merges its pull request (solved = merged), and the signed merge starts its award;
  - after the window and the four instalments, the bounty settles, and the issue is closed with a comment linking the bounty;
  - the close is recorded with the Token (deployed with its Race, its only recorder), with the two signed importance estimates; once the period ends, anyone claims its tokens for the solver and the reporter, and the founder's share.
- **Checked:**
  - every account's coins (wallet plus credit) to the micro-coin, and every token holder's balance and the supply to the micro-token, against the contracts' arithmetic restated in `bot/logic.py`;
  - that the coins add up;
  - that the winning pull request is merged and the failed one closed unmerged.
- **The bot settles on time (owner, 2026-10-30):** it checks its merged bounties once a day and calls `settle` the day the last instalment is released (`bot/logic.py` `due_to_settle`, which follows `Race.earned`). The close is then recorded in that period, before its grace window ends, so nobody loses tokens to a late close. In the loop the last release is on day 35, and the bot settles that day.
- **The bot is a convenience:** it links an issue to its bounty and a pull request to its sealed submission, and settles merged bounties on time; anyone can call the contract directly.
- **Tests:** `tests/test_bot.py` covers the bot's logic without Docker, and checks that the loop's images are pinned and its Forgejo is loopback-only.

### D9. What the race covers on-chain (owner, 2026-10-26)
- **On-chain, a bounty's money end to end:**
  - the registration fee, pledges and top-ups;
  - the rising price and its lock;
  - the attempt fee;
  - the submission's stake and check deposit, with oracle fees paid from the deposit;
  - the late and duplicate fees, and both appeals;
  - the merge, instalments and clawback;
  - the issue stake and finder's fee;
  - refunds by input.
- **In the simulation only:**
  - treasury bounties and matching (a treasury budget doesn't belong in an immutable contract);
  - reputation (stakes without the trust discount; attempts published as counted).
- **No market fee:** `market_fee_bps = 0` on-chain, as the owner decided on #15 (funding from grants and the contract improving itself). Checks are paid from the solver's deposit, so nothing needs a cut. The upstream author's share comes from release payouts, not bounties.
- **The replay's configuration:** the replay runs the simulation with this contract's shape (no treasury or matching, no trust discount, no market fee) and compares every account to the micro-credit.
  - It's `pof.params.CONTRACT`: also no race stake, and challenges with no appeal, so each is decided by one final result.
  - With no target (D12), every pledged bounty opens at once, so a 2-week contract-shaped run already includes paid bounties.

- **No stake (owner, 2026-10-26):** the simulation's race stake (40 % of the cap × risk) is an amount, but prices are shares of coins with no price feed. In the race a failed attempt gets its stake back anyway, and fake attempts are deterred by the attempt fee. So submissions post only the check deposit, and the winner's unpaid instalments are the bond. The contract-shaped simulation sets the race stake to 0 (task 2.3).
- **A clawback reopens the bounty (as pof):** what's unpaid stays in the bounty and it reopens at its locked price; the spec delta's earlier "returns to the funders" was a mistake.
- **Payouts computed per coin, lazily:**
  - a pot's amount at the lock and each award's price are snapshotted on the pot's first change after them;
  - instalments, the finder's fee and the registration refund are paid when someone touches that pot (`claimInstalments`, `settle`, `claimRefund`);
  - an award's price leaves out what earlier awards earned and haven't pulled (`unpaidBefore`), as the simulation's bounty never holds them.
- **Phase 1 timing:** challenges arrive as one signed upheld result, with no open period, so instalments don't pause and the window isn't extended (the simulation's contract configuration has to match, task 2.3). Releases fall on days divisible by `releaseEveryDays`, counted from deployment.

### D10. One fix, one payout (owner, 2026-10-26)
- **A fix paid once can't win again:** the oracle's similarity check rejects a fix it recognizes as already paid on another bounty, as it does a failed fix's duplicate (unchecked, for the evaluation fee, appealable).
- **The contract also keeps the exact case:** a registry of paid fix hashes (`paidFix`). A result naming a fix hash already paid is refused whatever the oracles say.
- With one open bounty per issue (D12), "another bounty" is a later one for a similar issue (a regression, say), or a different issue the same change claims to fix.

### D11. The market retires idle bounties (owner, 2026-10-26)
- An open bounty closes unsolved `idle_days` (28: the simulation's 4 empty rounds × 7 days) after it opened, reopened or last had a submission checked, and its funds return by input.
- Anyone can call `sunset(bounty)` once the time has passed. There's no keeper and no admin.
- Attempts don't hold it open (owner, 2026-10-29, amended; before, an attempt in progress did, until its window ran out, so an attempt every 14 days for its fee kept a bounty alive forever). Attempts in progress end with it.

### D12. Anyone opens a bounty, the market funds it (owner, 2026-10-26)
Replaces targets and twin bounties in `race` and `claim` (the auction keeps its targets, for comparison).
- **No target, no pledging phase:** whoever registers an issue pays the registration fee and the issue stake, and nothing else. The bounty opens as soon as the registration check accepts the issue; anyone pledges any coin while it's open, and the rising price works on whatever it holds. Funders and solvers set the value; a bounty nobody funds or attempts sunsets (D11).
- **One open bounty per issue:** the registration check refuses an issue similar to one whose bounty is open, won or being paid. The fee stays spent on the check; the stake returns. Funders add to the open bounty instead. Once it's closed, a new one may open, and D10 keeps its paid fix from winning again.
- **On-chain:** `register` is open to anyone; the check's result is an oracle call, `accept(issue)` (opens the bounty) or `refuseSimilar(issue, openBounty)` (the open bounty must be Open, Won or Merged). Before the check answers, the reporter can withdraw the issue and its stake. `openBounty`, the target, the pledging deadline and `expire` are gone.
- **In the simulation:** `open_bounty` refuses a target in `race` and `claim`, and an issue whose key matches a live bounty (`similar_open`). Matching (simulation only) matches bounties whose price isn't locked yet, capped at `match_cap_bps` of their pledges.
- **The match farm's counterfactual:** before, the single-account farmer pledged the whole value, what it needed to reach the target alone, against 60 % from fakes plus a match. With no target both open at once, so the single account now pledges the same 60 %, and only the match differs. Kept as before, the comparison showed a "saving" of +20.7 ± 3.7 per own fix that was only the 40 % less funding; like for like, +4.1 ± 2.3 (100 seeds, not significant).
- **Effect:** see [`reports/acceptance-modes-v4.md`](../../../reports/acceptance-modes-v4.md).

### D13. The reporter's and the solver's split (owner's request, 2026-10-26)
The owner asked that both the issue's creator and its solver benefit from the market, and whether 50/50 is the right split. **Decision: 15 % to the reporter, 85 % to the solver** (`finder_fee_bps = 1765`: 17.65 % of the price, which is 15 % of the payout; 4.8 % before).
- **Measured** (`python3 -m pof.sim market split --seeds 40`, [`reports/split-v1.md`](../../../reports/split-v1.md)):
  - In the contract's shape, reporters lose money below about 12.5 % (the registration fee spent on issues nobody funds) and earn from 15 % (+4.2 ± 0.6). Bounties fixed don't change significantly up to 15 % (17.8 to 17.1 per run); from 20 % they fall, and at 50/50 by 40 % (10.6), at 27 % more cost per fix, with solvers earning a fifth as much.
  - In the simulation's default (treasury and market fee), 15 % costs about 9 % of fixes (38.9 to 35.5 per run) and raises reporters from +3.7 to +26.1.
- **Why not 50/50:** fixing is the bottleneck (most open bounties sunset unfixed while issues keep arriving), so moving money from solvers to reporters buys fewer fixes. Junk doesn't gain (a reporter is paid only when a real fix is merged and survives its challenges): the flood loses the same at every share. But the match farm, whose own issues pay it as reporter, loses less as the share grows, nearly breaking even at 50/50 (−29 ± 15 against −207 at 5 %).
- **What the simulation can't show:** reporting more because it pays more (issue arrivals are fixed). If real data shows reporting is the bottleneck, the share can be raised at a new deployment; it's a parameter.
- With a treasury and a market fee (the simulation's default), the finder's fee stays below the market fee (17.65 % against 20 % of the price), so #34's self-dealing rule holds.

### D14. Fixes from the contract review (owner, 2026-10-27)
- **A reveal deadline:** a submission with no result after `resultDays` (7; most likely never revealed to the oracles) can be timed out by anyone (`timeOut`). It fails, its deposit pays the evaluation fee, and the queue moves on. Before, an unrevealed commitment held up every later submission, and the sunset, until the oracle answered for it.
- **The first attempt still locks the price (measured, then kept):** the review proposed locking on the first submission, since an attempt costs only its fee and a funder's sock could lock its own bounty low. On 100 seeds that change made the price rise to the full cap while solvers built (funders paid 162 a fix against 125, for the same fixes), and fake attempts started to pay (+51 ± 25: socks scare honest solvers off while the price keeps rising), which fails acceptance. With the share locked (below), a funder that locks its own bounty low gains nothing unless solvers accept that price; otherwise the bounty sunsets and the funds return. The numbers of that run are in the v5 report.
- **The share is locked, not the amount:** the winner is paid the locked share of the pot at its win. Pledges after the lock raise the price, and every funder pays the same fraction, so refunds by input stay fair. Before, a late funder's pledge sat in the pot and paid part of a price locked before it arrived. On-chain this also drops the snapshot of the pot at the lock.
- **Effect:** see [`reports/acceptance-modes-v5.md`](../../../reports/acceptance-modes-v5.md) and [`reports/split-v2.json`](../../../reports/split-v2.json).

### D15. Keyless upgrades by migration (owner, 2026-10-29)
The system improves without anyone holding a key, the way Bitcoin's rules change only when its users choose to run a new version.
- **The token:** its rules are fixed at deployment and no function changes them: the emission per period, its decay (1 % a period), the founder's share (1 % for 208 periods, to an address published at deployment; #58), and no genesis. Its only minter is its own Race, fixed at deployment, which mints each period's emission to the bounties that closed paid in it, by weight (#58 D1-D3).
- **A new version** is a new Token and Race that anyone can deploy. The new Token swaps the previous version's tokens 1:1, burning them, and the swap stays open forever. It continues the same schedule from the same start time.
- **No double emission while versions overlap:** in each period the new version mints only what the schedule leaves after the previous version's mint in that period, read from it on-chain. As the old version's bounties close, it mints nothing and the new one gets the whole emission.
- **The market decides:** no multisig, no minter-change key, no pause. Which version is "the" token is what holders swap into. A version with a fake oracle can mint its own token, but nobody has to swap into it.
- **Oracle keys are fixed per version** (D3). Changing the oracle set is a new version. The oracle quorum is the trust point that remains.
- **Bugs:** caps per bounty start low and are raised only in later versions (D6). Funds in an old version keep their refund paths. Security bugs go through a private reporting channel with a paid bug bounty, never a public race, which would publish the exploit before it's fixed.
- **Alternatives rejected:** an upgradeable proxy, a timelocked multisig, and a key that changes the token's minter. Each makes the project depend on a few people, and a stolen key could change the rules.

**As built, the token (task 3.4):**
- **`Token.sol`** is pof's `TokenBook` on-chain, an ERC-20 with 6 decimals (micro-tokens, as the simulation counts them). A period is one of its Race's releases (`race.day() / releaseEveryDays`). Its rules are immutables: the first emission, the decay (100 bps a period, rounded down as pof), the founder's share (100 bps for 208 periods, to the address fixed at deployment, at most `MAX_FOUNDER_BPS` = 500, rule 3), the reporter's share (1,500 bps) and the inflation tolerance (300 %). There's no genesis, admin or pause. The only account that records a close is its Race, whose address is fixed at deployment (the Race checks it's the token's recorder and that their periods match).
- **The weights are signed:** `accept` carries the registration check's estimate, and `merged` the merge's, both inside their EIP-712 digests. When the bounty closes paid (on `settle`), the Race records the close with both estimates; the token keeps the smaller, and an inflated registration forfeits the reporter's tokens to the solver. It tells the Race, which forfeits the reporter's finder's fee too (it stays in the pot, refunded by input). The issue stake and the registration refund still return.
- **A close's period is fixed by date (owner, 2026-10-30):** it's the period of the bounty's last instalment's release, which the Race knows from the merge day, the window and the instalments, whenever `settle` is called; settling later can't move it into a quieter period. pof's `TokenBook` records at the same release (`_finish`), so the periods match. A period's claims open `graceDays` (7) after it ends, so its closes can be recorded first: anyone can settle a bounty from its last instalment's release, two weeks in all. A close recorded after its period's claims have opened is refused and mints nothing: crediting it to a later period would let its solver choose that period by waiting, and refusing keeps the supply within the schedule. Its coin is paid as ever.
- **Minting is pulled:** once a period's claims are open, anyone calls `claim(period, close)` (the tokens go to the close's solver and reporter) and `claimFounder(period)`. No call loops over a period's closes. A close gets the pool times its weight over the period's weight, rounded down; the first close with the largest weight gets the remainder, so its claim waits for the others (anyone can claim them). Claimed in full, a period mints exactly its emission, or nothing if nothing weighed in it. `minted(period)` is public, for the migration (task 3.5).
- **Rule alignment with the simulation:** a fix with no coin reward (a bounty of 0 coin) still runs its 4 instalments, its clawback period, before it closes paid, as on-chain (`zero_reward_instalments`). First in the contract shape only; since 2026-10-30 (owner) pof's own market does the same, so its token runs follow the contract (`reports/tokens-v4`). Runs without tokens have no 0-coin bounty and are unchanged. With the emission on and no treasury, a bundle still doesn't open, since the contract has none. Default runs are unchanged (a 2-seed `market accept` is byte-identical to main).
- **The replay** (`--export-events --tokens`: pof's TOKENS on the contract's shape, solvers valuing a token at 0.05) checks, besides every coin balance, that each period minted what `TokenBook` minted, from as many closes, and that every holder's balance and the supply match to the micro-token. Seeds 1, 5, 7 and 15 have bounties of 0 coin that closed paid; 15 has an inflated registration.
- **Size:** Race grew from 26,394 to 27,079 bytes (the weights, the forfeit flag, the close's period and the call to the token); the weighing, the periods' grace and the minting live in the token (6,121 bytes). Race still has to fit under EIP-170 (D8, open).

**As built, the migration (task 3.5):**
- **A new version is the same `Token` and `Race`, deployed again by anyone,** with the Token naming the version it continues (`previous`). Nothing else links them: no key on the old version is involved, and the old version doesn't know the new one exists.
- **The same schedule, from the same start:** the new Token's constructor refuses a different first emission, decay, founder, founder's share or founder's periods, period length or grace. Its `start` is the previous version's, and its Race counts its days from the token's `start` (not its own deployment), so every version's day, period and release fall on the same dates. Only the version's own close rules may differ: the reporter's share and the inflation tolerance. Chained versions (v3 continuing v2 continuing v1) work the same way.
- **The swap:** `swap(amount)` burns the holder's previous-version tokens (the holder approves the new token first; `Token` has `burn` and `burnFrom`, OpenZeppelin's `ERC20Burnable` written out, as only the vendored ERC-20 files are pinned) and mints the same number of new ones. It's open forever and isn't emission: `minted` doesn't count it (`swapped` does). The versions' supplies together never exceed what was minted.
- **No double emission:** a version's pool in period p is `available(p)`, the emission less the previous version's `committed(p)`. `committed(p)` is what a version will mint in p once everything is claimed: what's available to it if anything of weight closed in it, else nothing.
  - **Committed, not minted (decided in the build):** claims are pulled and open forever, so the previous version's running `minted(p)` can still grow after the new version claims; reading it would let the two together mint more than the schedule. A version records no close for p once p's claims open, and the grace and periods are the same in every version, so `committed(p)` is final when the new version's claims for p open.
  - **The effect:** each period's emission goes, whole, to the oldest version with a close of weight in it. A newer version's closes in that period are recorded and claim nothing; their coin is paid as ever. As the old version's bounties close out, the new one gets the whole emission.
- **The founder's share follows the emission:** each version takes its share of what's available to it, so one share of each period's emission is minted, by whichever version mints it, for the same 208 periods in all.
- **The old version keeps paying:** its pending closes are claimed in it as before, before or after holders swap, and before or after the new version's claims.
- **Tests:** `contracts/test/Migration.t.sol` runs the versions side by side: the swap and its burn, the swap through a chain, the swap years later, two versions closing in the same period and in different ones (claimed in either order), the founder's share across versions, the schedule checks, a fuzzed six-period run across two versions, and two real Races, the second deployed 3 days after the first, sharing its days and periods.
- **Size:** Token is 7,022 bytes (6,121 before); Race is unchanged at 27,079.

## Risks

- **Rounding drift** between Python and Solidity. The replay test makes it visible; rounding follows `pof` exactly.
- **Gas:** measured per step in the tests (`forge test --gas-report`), and reported, since it's a known risk (#56 item 10).
- **Fee-on-transfer coins** are refused only when the fee is non-zero on that transfer: a transfer small enough that its fee rounds to 0 gets in whole. The books stay exact either way, since the contract counts what arrived and its own balance falls by exactly what it sends (the invariant suite).
- **A prototype isn't audited:** no real funds, ever, until an external audit and the go-live checklist (#15).
- **Migration (D15):** two versions can split the token's value for a while, and holders who never swap stay on the old token. Each version's swap stays open forever, so no holder loses by waiting. While the old version still has a close in a period, it takes that period's whole emission, so anyone who keeps closing bounties there delays the new version's emission; it can't add to the supply, and closing a bounty is open to everyone in either version.
