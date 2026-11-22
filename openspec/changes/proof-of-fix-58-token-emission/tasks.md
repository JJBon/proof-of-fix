# Tasks

## 1. Mechanism

- [x] 1.1 Token parameters (D2), with validation: the emission and decay are non-negative, and `founder_share_bps` is at most `owner_share_cap_bps`. Verify with tests, including that a founder's share above the cap is refused.
- [x] 1.2 `pof/tokens.py` (D1, D2): the period record and the mint at the next release, by weight, with the founder's share and rounding. Verify with tests for each scenario in the `token-emission` delta: two bounties, nothing closes, activity doesn't inflate, the founder's share ends, and the total minted never exceeds the emission.
- [x] 1.3 The AI weight at registration and at merge (D3), and the mint record when a bounty closes paid (`Market._finish`); nothing for refunded, unsolved or clawed-back fixes, and the reporter's share. Verify with tests for the zero-coin, clawed-back, inflated-estimate and split scenarios.

## 2. Simulation

- [x] 2.1 With the emission on: unpledged issues open as 0-coin bounties, and the treasury tops up open bounties (D4). Verify with tests, and that with the emission off the modes v5 run reproduces byte for byte.
- [x] 2.2 Solvers price tokens at `token_price` from the published rate (D5), and earnings include tokens. Verify with tests.
- [x] 2.3 The scenarios `token_market`, `token_self`, `token_inflate`, `token_launch` and `token_owner` (D6), with the report's token figures and the criteria (D7). Verify with tests for each, including the concentration and the owner criteria.
- [x] 2.4 `python3 -m pof.sim market tokens --seeds N` (D8). Verify with a smoke test on a few seeds.

## 3. Run and report

- [x] 3.1 Run `market tokens --seeds 40` and write `reports/tokens-v1.{json,md}`: each finding per token price, the founder options, and which earlier criteria hold at each price. Verify that the report passes or names each failure.
- [x] 3.2 Post the results on #58 and #56, update `README.md`, and run the check.
- [x] 3.3 The owner's decisions on tokens-v1 (2026-10-29): a 1 % founder's share and no genesis (D2); inflation forfeits the reporter's share (D3, amended); measure who pays for a ring's gain. Run `market tokens --seeds 40` and write `reports/tokens-v2.{json,md}`. Verify with tests that an inflated close forfeits the reporter's coin and tokens, and that one within the tolerance doesn't.
- [x] 3.4 The owner's decisions on tokens-v2 (2026-10-29): a 300 % inflation tolerance (D3), and a ring is judged by what it costs outsiders and funders, not by its own gain (incentive-simulation, MODIFIED). Run `market tokens --seeds 40` and write `reports/tokens-v3.{json,md}`. Verify with tests that the ring criterion reports each ring's cost to others and its own gain.
- [ ] 3.5 The owner's decision of 2026-11-03: no founder's share (design, "Revision 2026-11-03"). Set `founder_share_bps` to 0 in `pof/params.py`, keep the mechanism tested at a non-zero value, re-run `market tokens --seeds 40`, and confirm the token criteria still hold. Verify with tests and the check.
