# Constitution of proof-of-fix

> **DRAFT, not in force.** This constitution takes effect only at genesis, when a version of the contracts that records it is deployed, and its hash is recorded on-chain. Until then, everything in proof-of-fix is simulated (openspec rule 1), and this text binds nothing. Spec: `openspec/changes/proof-of-fix-85-self-healing`; decision: [ADR 0001](docs/adr/0001-self-healing-constitution.md).

Articles marked **(entrenched)** can't be changed by an ADR. They change only in a new version, which anyone may deploy and users choose to follow (Article 9).

## Article 1. Purpose
proof-of-fix is self-healing, decentralized code. Its code is repaired and improved by whoever fixes it best, judged by AI judges under this constitution, and paid by whoever funds the fix. Funding open-source work is the means; code that keeps itself healthy with no one in control is the goal.

The same judges also answer questions that other contracts send them, one check domain at a time (Article 12). Those who ask pay for that work, and it never moves the code or a rule.

## Article 2. No human control (entrenched)
1. No person, the author of this constitution and any maintainer included, merges, reverts, declines or rewrites the canonical code.
2. The canonical code is the head recorded on-chain: the commit of each fix the judges passed, bound to the base it was checked on. A git mirror that differs from the recorded head is wrong, whoever administers it.
3. The contracts have no owner, admin, upgrade or pause function, and no key that changes a rule. A rule changes only by an ADR under Article 9 or, for an entrenched article, by a new version.

## Article 3. The judges (entrenched)
1. There are **7 judges.** Each runs a different model family, and each is run by a different, independent operator: **different organisations, jurisdictions and providers, disclosed** with each version. Their operators, families and providers are fixed for a version, and no more than **2 of the 7** rely on the same inference or TEE provider. Each new version chooses its judges by their public record (accuracy, reveals, canaries, uptime). Draws may be weighted by quality in a later version, **never by price.**
   - **A judge's key** may be replaced only by a key whose attestation shows a checker image on the allowed list (Article 7), co-signed by the judge's current key and 5 of the other 6 judges, after 7 days' public notice. A judge that can't sign is suspended; its operator is never replaced except in a new version.
2. **The issue tier:** 3 judges drawn with the verdict's seed from the 7. A fix passes with **2 of 3**.
3. **The constitution tier:** all 7. A change passes with **5 of 7**.
4. Every verdict is signed, names its exact model and version, carries the hash of its receipt (the model, the hashes of the prompt and the response, the measured usage, the checker image, the test results, the commits and the attestation; encoded as COSE_Sign1 after the IETF draft *Attested Inference Receipt*, -02), and is published in the public log. **A judge uses only the model versions allowed for its family** (Article 7); a verdict from any other version is a bad receipt.
   - **A judge runs inside a TEE of an accepted type** (AWS Nitro; Intel TDX, through Phala dstack or self-hosted; AMD SEV-SNP) and runs **the one official checker image,** built reproducibly so every operator's attestation shows the same digest. Each operator otherwise chooses its own infrastructure.
   - **A judge calls its model provider directly from inside the TEE,** over a connection that ends inside it; no proxy or gateway sits in the path of a counted verdict.
5. A judge never judges a bounty or an ADR in which its operator is a party. The author of this constitution operates at most one judge, disclosed.
6. **Verdicts are sealed, then revealed.** A judge that seals and doesn't reveal in time loses a published share of its bond, and the next judge in the draw takes its place.
7. **Judges are slashed only for provable faults:** conflicting signatures, a reveal that doesn't match its seal, a missed reveal, failing to serve code it signed to hold, or a bad receipt (20 % of the bond). A wrong answer given in good faith is never slashed. **Each judge's bond is at least twice the largest bounty its version accepts,** and each version publishes that largest bounty.

## Article 4. Escalation
A fix goes to the constitution tier when:
1. it touches a protected path (Article 7);
2. any issue judge flags it as constitutional; or
3. anyone challenges its verdict with a stake within its clawback period.

A fix that passes the issue tier moves the head at once. If a challenge is then upheld by 5 of 7, the head moves to a revert of the fix, and its unpaid instalments are clawed back.

## Article 5. Invariants
These rules hold for every version. Changing one needs an accepted ADR (Article 9).

1. **Keyless versions.** A new version is a new deployment that anyone may make. Funds in an old version keep their refund paths, and users move by migration.
2. **Solvency, per coin.** The contract's balance of each coin is at least what it owes in that coin. If that ever fails, the coin goes withdraw-only for good, and the other coins carry on.
3. **Pull payouts.** Payouts and refunds are credits, pulled by their owner to any address the owner names. A failed transfer leaves the credit in place, and nothing loops over a bounty's coins or funders.
4. **Caps.** A per-bounty cap and a total cap, in whole coins, fixed at deployment. Caps start low and rise only in later versions.
5. **Signed verdicts.** Results are EIP-712 digests binding the chain, the contract, the action, every argument and a nonce, each used once, signed by the version's judges at the tier's threshold.
6. **The race:**
   - the price rises from a published start until the first attempt locks its share;
   - pledges after the lock still raise the price;
   - the passing submission with the earliest commitment wins;
   - a submission with no result for 7 days can be timed out by anyone.
7. **The split.** 15 % of each payout to the reporter and 85 % to the solver (a finder's fee of 1,765 basis points of the price).
8. **One fix, one payout.** A fix already paid can't win again.
9. **Payment on merge, in instalments, with clawback.** The clawback period is the challenge window. An upheld challenge claws back what's unpaid and reopens the bounty.
10. **Idle sunset.** An open bounty closes unsolved 28 days after it opened, reopened or last had a submission checked, and its funds return to their funders. Attempts don't hold it open.
11. **No cut.** No protocol fee: nothing of a bounty goes to the author of this constitution, the operators or any fee address. Judges are paid only by check fees:
    - the reporter's registration fee pays the registration check;
    - the solver's deposit pays its attempt's checks;
    - the winner's checks are refunded from the bounty at merge;
    - an outside requester's fee pays its request's checks (Article 12).

    **Check fees: the costs passed through, plus one agreed service fee.**
    - The price table holds **unit prices:** tokens per model family, sandbox vCPU-seconds and GB-seconds, and storage. A counted check is charged its measured usage at those prices (for parts every judge performs, the median of the counted judges' usage), within the per-check caps of this constitution and the repository's CI profile, **plus one service fee per counted check, the same for every judge.** No judge sets a fee of its own.
    - Gas is reimbursed at cost. The solver's deposit is the maximum under the caps; the rest is refunded.
    - The price table and the service fee change only by 5 of 7 judges, each value by at most 25 % per update, after 7 days' notice, **citing the providers' public price lists.** Anyone may challenge an update during its notice with a stake; an upheld challenge cancels it and is paid from the proposing judges' bonds.
    - **Caps, changed only by an ADR:** no entry of the price table above **2× its value at genesis;** the service fee **$0.05** per counted check at genesis, never above **$0.25.**
12. **No token.** This version mints no token. A token can exist only in a version that holders choose to migrate to.
13. **Numbers.** Amounts are integers in each coin's smallest unit, and shares are basis points (10,000). Rounding is down, with the remainder to the last party.

## Article 6. Quality gates
A fix passes only if, measured by the attested runners and the judges:
1. it builds, and every test passes;
2. the bounty's failing test now passes, and the hidden tests pass;
3. no test that guards an invariant is weakened or removed (those tests are protected, Article 7);
4. the changed code meets the published coverage and mutation score;
5. it stays within the published limits on diff size and performance;
6. the judges pass it at its tier.

A fix is judged against the constitution in force when its bounty was registered.

## Article 7. Protected paths
A change to any of these paths goes to the constitution tier, and it needs an accepted ADR that names the path:
- `CONSTITUTION.md` and `docs/adr/`;
- `contracts/src/`;
- `contracts/test/*Invariant*.t.sol` and `contracts/test/Replay.t.sol`, the tests that guard Article 5;
- `openspec/specs/`, the system's behaviour;
- `scripts/check.sh`, `scripts/contracts.sh` and `contracts/foundry.toml`: the check itself and the pinned toolchain;
- the judges' checker, its prompts, **the allowed model versions for each family,** the **allowed list of checker image digests,** **the accepted TEE attestation types,** the per-check caps and **the service fee's cap,** once they exist in this repository;
- `domains/`: the list of open check domains and each domain's definition (Article 12), once they exist in this repository.

## Article 8. Self-healing and the sponsors' pool
1. **Anyone may register, with evidence:**
   - tests failing on the head;
   - a public security advisory for a pinned dependency;
   - a regression.

   If the registration check accepts it, the sponsors' pool pays its registration fee and the watcher is refunded.
2. **These system issues pay no reporter share;** that share goes to the pool.
3. **Anyone may fund the sponsors' pool.** It's spent only on:
   - system issues' registration fees;
   - a published starting amount for each system issue's bounty, while the pool holds it;
   - refunds of accepted ADRs' fees.

   No person directs it.
4. **Undisclosed vulnerabilities** go through a private reporting channel with a paid bug bounty, never a public race.
5. **A head counts only when its code is available:** at least 5 of the 7 judges sign that they hold the fix's code and will serve it for a year, and a permanent copy's receipt is recorded with the head. A judge that can't serve code it signed for loses a published share of its bond.

## Article 9. Amendment (entrenched)
1. **This constitution changes only through an accepted ADR,** a record in `docs/adr/` giving the problem, the options, the decision, the evidence, and the protected paths it touches.
2. **An ADR passes the constitution tier,** 5 of 7, and then a **14-day public challenge window.**
   - Anyone may challenge it with a stake and evidence. The 7 judges then judge it again, and it takes effect only if 5 pass it again.
   - The losing side's stake goes to the winning side.
3. **Fees:** the ADR's author pays the 7 verdict fees, refunded from the sponsors' pool if the ADR takes effect.
4. **An ADR that touches an entrenched article** (Articles 2, 3 and 9) is refused without judging. Those articles change only in a new version, deployed by anyone, with its own constitution, which users choose to follow.
5. **Bounties keep the constitution** they were registered under.

## Article 10. Outside projects and outside requesters
1. **Projects that keep human maintainers are never governed by this constitution.**
   - A bounty on such a project pays on the judges' verdict.
   - The winning fix is offered upstream as one pull request, which the maintainers merge or not.
   - Attempts never appear on their project.
2. **Their licences, notices and attribution are kept** on anything taken from them.
3. **Outside requesters are never governed by this constitution, and govern nothing in it.**
   - A contract or person that asks a question in a check domain (Article 12) gets an answer under that domain's rules. What it does with the answer is its own affair.
   - A request never moves the canonical head, a bounty or a rule.

## Article 11. Genesis and the author's interests
1. This constitution was written by the owner of proof-of-fix, as a one-time act disclosed in ADR 0001, before genesis.
2. **After genesis, the owner can change nothing alone.** Like anyone, the owner may propose ADRs, fund bounties, solve them (the owner's judge recusing), and operate at most one judge, paid by check fees like any operator.
3. **The owner takes no share of bounties and receives no founder's share;** the owner earns tokens only as an ordinary funder, under the same rules as anyone.

## Article 12. Check domains
1. **A check domain is one kind of question the judges answer for outside requesters.** Each is opened, changed and closed only by its own ADR, which fills in every field of the domain template (ADR 0005) and is recorded under `domains/` (Article 7). Nothing is answered outside an open domain.
2. **The shared core, which no domain changes:**
   - every article of this constitution applies to every domain;
   - **one token:** in a version that has a token, every domain's margin (its price less the judges' costs and service fee) is burned in that one token, and paid to no one. A version without a token charges no margin;
   - the judges' costs are charged at the price table's unit prices (Article 5.11), plus one service fee per counted answer, the same for every judge, never above Article 5.11's cap;
   - **each judge's bond is at least twice the largest value any one answer decides.**
3. **In this version (Article 3):**
   - a domain uses only the issue tier and the constitution tier, with all the version's judges at their allowed model versions;
   - a domain is a mode of the one official checker image, on the allowed list of digests (Article 7);
   - no request decides more than the largest bounty the version accepts;
   - a domain's ground truth is a checker (tests, proofs or a reproducible computation) or, once accepted, verifiably fetched sources. Domains judged by opinion wait for a version with larger panels.
4. **A judge whose operator is a party to a request recuses,** as for a bounty. **Each answer's signature binds its domain and its request,** so it can't stand for any other answer or verdict (Article 5.5).
5. **Shadow mode first.** A domain opens in shadow mode: its answers are recorded, published and scored against its ground truth. They are paid at cost plus the service fee by whoever asks, they carry no margin, and no money moves on them. It leaves shadow mode only by an ADR that shows its measured accuracy against the bar its opening ADR published before the shadow phase began.
6. **Challenges.** Anyone may challenge a domain's answer within its window, with the stake its ADR sets. The constitution tier judges the challenge, and the losing side's stake goes to the winning side.
7. **Isolation.** A domain's scores, canaries, fee table, stakes and challenges are its own. **When its suspension rule is met, it takes no new requests, automatically:** the contracts apply the rule from on-chain records alone, and no person, judge or key can trigger it or lift it. Only an ADR reopens or closes the domain, and closing it changes no other domain.
8. **Every domain refuses** the requests its refusal policy names, and any request that tries to instruct the judges through its content.
