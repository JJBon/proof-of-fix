# ADR 0001: Self-healing decentralized code under a constitution

- **Status:** proposed. This is the genesis decision: it takes effect with the constitution at genesis, without the constitution tier, which doesn't exist before then.
- **Date:** 2026-10-30
- **Author:** the owner of proof-of-fix (genesis act, disclosed below)
- **Constitution articles changed:** all. This ADR establishes the constitution.
- **Protected paths touched:** `CONSTITUTION.md`, `docs/adr/`

## Problem
The race on-chain (#56) pays a fix on merge with no admin key, but two points of control remain:
- **The git host's admin** can still change the code. Whoever holds the merge right controls the project.
- **The rules can wear down:** a stream of passing fixes, each reasonable, can still erode the project's rules, and nothing protects the rules themselves.

The owner's goal (#85, 2026-10-30) is self-healing decentralized code: "No one controls the code, not even maintainers (AI is for that)."

## Options
1. **Keep things as they are:** the protocol's bot merges what the oracle quorum passes, and the host's admin holds the merge right. The admin can still override the code, and the rules have no special protection.
2. **Maintainers keep the merge** (#84): the AI checks, a maintainer approves, and maintainers are paid the same to say no. This suits projects with human maintainers. But a person stays in control, which isn't the goal for proof-of-fix itself. Superseded.
3. **AI-appointed, replaceable maintainers:** maintainers are chosen and removed by the AI on their record. Dropped: people stay in control, and "forks exist for a reason".
4. **Chosen: no human control.**
   - the judges' verdicts, recorded on-chain, are the only way the code changes;
   - two tiers of judges: 3 for fixes, 7 for the constitution;
   - a constitution that changes only through ADRs;
   - three entrenched articles that change only by a new version.

## Decision
Option 4, with the owner's accepted defaults (2026-10-30):
- **The judges:**
  - the issue tier is 3 judges drawn from 7, 2 to pass;
  - the constitution tier is all 7, 5 to pass;
  - one model family and one independent operator per judge.
- **ADRs:** a 14-day public challenge window before an ADR takes effect.
- **Entrenched:** no human control (Article 2), the judges (Article 3) and the amendment procedure (Article 9).
- **The head:** the canonical head is recorded on-chain, and a bot anyone can run keeps the mirrors on it.
- **Money:**
  - no token emission: the token is parked, and a later version may enable it by migration;
  - no protocol fee;
  - judges are paid by check fees, with the winner's checks refunded at merge.
- **Self-healing:** system issues paid by a sponsors' pool.
- **Outside projects:** projects with human maintainers receive verified fixes as one pull request, and are never governed.

The full rules are in `CONSTITUTION.md` and `openspec/changes/proof-of-fix-85-self-healing`.

## Evidence
- **The simulations:**
  - the race passes every acceptance criterion without a token (reports `tokens-v1` to `v3`: "without tokens, every criterion");
  - the token helped only when it traded at 0.05 coin or more, a price nothing in the model supports.
- **The contracts:**
  - the keyless design (D15) and the signed quorum (D3) are built and tested on the local chain (`scripts/contracts.sh test`);
  - so is the migration (#83).
- **Still to measure,** before any version records this constitution (tasks 2 to 4 of the change):
  - the judges' accuracy;
  - their agreement between model families;
  - prompt injection;
  - the cost per check with 3 judges and with 7;
  - the attackers in the simulation.

## Consequences
- **Maintainers:** proof-of-fix has none. Nobody can merge, including the owner.
- **Speed:** a fix that passes the issue tier is merged at once; challenges and reverts happen during its clawback period.
- **Cost:** the constitution is expensive to change (7 verdicts and 14 days), and the entrenched articles can't be changed at all without a new version. Stability is bought with that cost.
- **The remaining trust point** is 5 of the 7 operators colluding. It's countered by:
  - a public log of every verdict;
  - challenges;
  - operators in different organisations and families;
  - migration to an honest version.
- **The owner's interests (genesis disclosure, openspec rule 3):**
  - the owner writes this first constitution, a one-time act;
  - after genesis the owner may operate at most one judge, paid check fees like any operator, and recusing as a party;
  - the owner may solve and fund bounties like anyone;
  - the owner takes no share of bounties, and has no founder's share or token.

## Challenge window
None at genesis. Every later change goes through Article 9.
