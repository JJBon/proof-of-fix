# Award modes compared, v4: the market funds bounties (proof-of-fix#56, 2026-10-26)

**Command:** `python3 -m pof.sim market modes --seeds 100 --sweep-seeds 20 > reports/acceptance-modes-v4.json` (about 25 minutes). The baseline is modes v3 ([`acceptance-modes-v3.md`](acceptance-modes-v3.md)).

**What changed since v3** (owner, 2026-10-26; design D12 and D13 of `proof-of-fix-56-local-contract`):
1. **Anyone opens a bounty, the market funds it.** In race and claim a bounty has no target and no pledging deadline. It opens as soon as the registration check accepts the issue, and anyone pledges to it while it's open. Whoever opened it doesn't have to fund it.
2. **One open bounty per issue:** the registration check refuses an issue similar to one whose bounty is still open or being paid.
3. **The reporter's share is 15 % of the payout, the solver's 85 %** (a finder's fee of 17.65 % of the price; it was 5 %). See [`split-v1.md`](split-v1.md) for why not 50/50.
4. **The match farm's comparison is like for like:** with no target, the single-account farmer pledges the same 60 % as its fake accounts do (it used to pledge the whole value, what it needed to reach the target alone).

## Result

| Mode (100 seeds) | v3 | **v4** |
|---|---|---|
| **race** (default) | ✅ every criterion | ✅ **every criterion passes** |
| auction | ✅ | ✅ (unchanged rules) |
| claim | ❌ 2 | ❌ 1: proven solvers don't lock less (a comparison only); "discoverers earn" now passes |

| Race | v3 | **v4** |
|---|---|---|
| Bounties paid / unsolved per run | 32.7 / 47.6 | **36.3** / 59.4 |
| Days to fix | 12.9 | 12.4 |
| Mean price | 117 | 109 |
| Funders' cost per paid bounty | 121 ± 3 | 125 ± 2 |
| Honest solvers' net per run | +73 ± 3 | +67 ± 3 |
| **Reporters' net per run** | +1.5 ± 0.2 | **+27.1 ± 0.6** |
| Junk reporters (the flood) | −494 | −495 |
| Accepted fixes at the quality bar | 97 % | 97 % |
| Wasted effort | 51 % | 51 % |

**11 % more bounties are fixed,** because every pledged bounty now opens, even one funded below the issue's value. More are also left unsolved, because nothing stops a thinly funded bounty from opening, and it sunsets after 28 idle days with its funds returned. **Reporters now earn** (+27 a run, against +1.5). Solvers give up a little (−6) to pay for it.

## Matching matters less
Matching used to be how pledged bounties reached their target. In v3 it raised the share of pledged bounties funded by 45 points. With no target, every bounty opens anyway, and a match only raises an unlocked bounty's price. It now raises the share of pledged bounties fixed by **6.4 ± 1.0 points**. That is still significant over 100 seeds, so the criterion passes, but it's too small to show on the 20-seed sweeps: two sweep rows fail it (false duplicates at 20 %, gate bar 0.8) on noise.

## Attacks on the race (against their honest twins)

| Attack | v3 | **v4** |
|---|---|---|
| Fake attempts (two socks) | +12.9 ± 15.6 | −3.4 ± 14.7 |
| Variant from a second account | −6.0 ± 14.9 | −9.5 ± 16.3 |
| Padded tests | −162 ± 21 | −170 ± 20 |
| Inflated estimates | −309 ± 28 | −419 ± 27 |
| Rings of 2 / 3 / 4 / 6 | +3 / −28 / −27 / −9 | −9 / −2 / −6 / −18, none significant |
| Match farming (saving per own fix) | (none) | +4.1 ± 2.3, not significant |

**Match farming, measured the old way,** gave +20.7 ± 3.7 per own fix: the single account still pledged the whole value while the fakes pledged 60 %. With no target, that difference is just less money, so the comparison now holds the money equal (design D12).

## Sweeps (race, 20 seeds)

| Sweep | Honest solvers | Bounties paid | Finding |
|---|---|---|---|
| Attempt fee 0.1 / 0.5 / 2 | +65 / +62 / +49 | 37.5 / 37.5 / 37.3 | every value passes |
| False duplicates 0 % / 5 % / 20 % | +65 / +62 / +71 | 36.9 / 37.5 / 36.7 | 20 % fails only the matching criterion (noise, above); 3.3 of 3.5 flagged fixes per run win on appeal |
| Duplicate appeal jury 3 / 5 | +62 / +63 | 37.5 / 37.3 | both pass |
| Attempt cost (cost per line) 0.1 / 0.5 / 1 / 2 | +282 / +107 / +62 / +31 | 70 / 51 / 37 / 23 | every value passes (v3: at double the cost, discoverers stopped earning) |
| Gate bar 0.6 / 0.7 / 0.8 | +82 / +62 / +6 | 38 / 37 / 30 | at 0.8, honest solvers barely earn, as in v3 |
| Registration fee 0.5 / 2 / 5 | +64 / +62 / +58 | 38.5 / 37.5 / 37.0 | every value passes |
| Top-ups per week 0 / 10 % | +62 / +63 | 37.5 / 38.1 | both pass |

## Next
The contract follows the same rules (`Race.sol`: `accept`, `refuseSimilar`, pledges while open, no target). The replay (task 2.5) runs the contract-shaped simulation (`pof.params.CONTRACT`) and compares every balance.
