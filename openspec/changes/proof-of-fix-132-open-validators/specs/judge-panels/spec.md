# Spec Delta

## Purpose
How each check's judges are chosen in v3, and when their verdict is final:
- the odd panel size k from the eligible validators and the bounty;
- the draw and its seed;
- replacement of silent judges;
- the proof a counted verdict must carry;
- challenge windows by panel size, and the hold on a lone judge's verdict;
- audits, two of them for a lone judge's verdict;
- the constitution tier's fixed size, the network it waits for, and the deposit a rejected ADR forfeits.

It replaces v2's fixed "3 of 7" and "all 7" for v3 only.

## ADDED Requirements

### Requirement: The panel is the largest odd number the network allows
For each submission, the panel size k SHALL be the largest odd number not above the smaller of:
- the number of eligible validators: active, bonded for that bounty, not leaving, not a party, within the caps;
- the version's K_MAX.

The panel SHALL pass a fix with a majority of k, that is (k + 1) / 2. When no validator is eligible, the submission SHALL wait.

#### Scenario: One validator
- **WHEN** exactly one validator is eligible and a solver submits a fix to a bounty within k = 1's limit
- **THEN** that validator alone judges it, and its verdict decides under k = 1's hold and window

#### Scenario: Two validators
- **WHEN** two validators are eligible
- **THEN** k is 1, never 2, so there is never a tie

#### Scenario: Six validators
- **WHEN** six validators are eligible and K_MAX is 7
- **THEN** k is 5, and 3 passing verdicts pass the fix

#### Scenario: A large network
- **WHEN** forty validators are eligible and K_MAX is 7
- **THEN** k is 7, and 4 passing verdicts pass the fix

### Requirement: A bounty's size limits who may judge it
A validator SHALL be eligible for a bounty only if its bond is at least the bond factor (2) times the bounty's tier: the smallest bounty limit of the k table, at any level, at or above the bounty. Each panel size and proof level SHALL have a published largest bounty. A submission above the current k's limit SHALL wait until enough validators are eligible; its solver MAY withdraw it, refunded less charges metered.

#### Scenario: A small bond, a small bounty
- **WHEN** a validator bonded at $100 is active, and bounties of $40 and $400 receive submissions
- **THEN** it may be drawn for the $40 bounty, and isn't counted as eligible for the $400 one

#### Scenario: A bounty between two tiers
- **WHEN** a $60 bounty receives a submission and the k table's limits include $50 and $125
- **THEN** its tier is $125, and only validators bonded at $250 or more are eligible for it

#### Scenario: A big bounty on a small network
- **WHEN** a solver submits to a bounty above k = 1's limit while only one validator is eligible
- **THEN** the submission waits, no judge is drawn, and the solver may withdraw it with the deposit refunded

#### Scenario: The network grows
- **WHEN** a waiting submission's bounty fits the limit of the k that the eligible validators now allow
- **THEN** it is drawn with that k, without the solver doing anything

### Requirement: k is fixed at the draw and silent judges are replaced
Once drawn, a submission's k SHALL NOT change. A drawn judge that doesn't seal within the seal window, or doesn't reveal within the reveal window, SHALL be replaced by the next eligible validator in the same shuffle. The replacement SHALL get a fresh window. When the shuffle is exhausted, the submission SHALL wait for the next eligible validator. A judge's silence SHALL NOT lower k or the majority needed.

#### Scenario: A judge goes silent to change the outcome
- **WHEN** one of 3 drawn judges, seeing the others' seals, stays silent hoping for a smaller panel
- **THEN** the next validator in the shuffle replaces it, k stays 3, and 2 passing verdicts are still needed

### Requirement: The draw's seed is fixed after the submission and recomputable
A panel SHALL be drawn by a shuffle of the eligible validators driven by a seed. The seed SHALL be derived from:
- the sealed submission;
- the bounty;
- a source of randomness from a block after the block that sealed the submission.

Neither the solver nor any single validator SHALL be able to choose the seed. Anyone SHALL be able to recompute the panel from the recorded seed and the registry's state at the draw.

#### Scenario: Grinding the seed
- **WHEN** a solver resubmits the same fix repeatedly hoping to draw its own validator
- **THEN** each submission's seed depends on a later block it can't predict, every attempt pays the attempt fee and the check deposit, and the solver's own validator is recused as a party

#### Scenario: Recomputing a panel
- **WHEN** anyone recomputes a past panel from its recorded seed and the registry at that block
- **THEN** they get the same validators in the same order

### Requirement: A panel too weak for its bounty waits
When a drawn panel's proof level may not judge the submission's bounty, the draw SHALL be void and the submission SHALL wait. It SHALL be drawn again, with a fresh seed, when the registry changes.

#### Scenario: A level C majority on a large bounty
- **WHEN** a $200 bounty draws a panel of 3 whose level is C, and level C's limit at k = 3 is $50
- **THEN** no judge is seated, the submission waits, and it is drawn again with a new seed after the next registry change

### Requirement: A counted verdict carries proof that the check ran
A verdict SHALL count only if it is signed by an active validator's key, registered under an accepted proof type, was sealed and revealed on-chain in its windows, and its receipt is bound to the verdict and posted on-chain in the reveal window. A judge whose verdict lacks that proof SHALL be treated as not having revealed, and the next validator in the shuffle SHALL replace it.

#### Scenario: A verdict with no receipt
- **WHEN** a judge reveals a verdict but posts no receipt in the reveal window
- **THEN** the verdict doesn't count, and the judge is treated as having sealed and not revealed

### Requirement: The receipt shows the sandbox and a direct model call
A counted verdict's receipt SHALL show the tests' output hash from the official sandbox image, and a model call to the provider's own endpoint with the provider's request ID, token usage and a model of the validator's declared family. For a TEE validator the call SHALL go from inside the TEE; for a zkTLS validator it SHALL carry a listed notary's proof. Otherwise it SHALL be a bad receipt.

#### Scenario: A zkTLS validator lies about the tests
- **WHEN** a zkTLS validator's receipt reports test results (each test's pass or fail) that re-runs of the same commit in the official sandbox, by a fresh panel, don't reproduce
- **THEN** a receipt challenge against it is upheld

#### Scenario: A verdict through a gateway
- **WHEN** a revealed verdict's receipt shows its model call went through a proxy or gateway
- **THEN** a receipt challenge against it is upheld, and the challenge panel's majority decides the fix in place of that verdict

#### Scenario: A model of another family
- **WHEN** a receipt names a model outside the validator's declared family
- **THEN** it is a bad receipt, and a receipt challenge against it is upheld

### Requirement: A panel's proof level is its majority's weakest
A panel's proof level SHALL be the lowest level held by a majority of its judges. Any mix of levels SHALL be allowed, including a panel of level C validators only.

#### Scenario: A mixed panel of 3
- **WHEN** a panel of 3 has one level A, one level B and one level C judge
- **THEN** its proof level is B, because a majority (A and B) holds at least B

#### Scenario: A network of ordinary PCs
- **WHEN** every eligible validator is at level C
- **THEN** panels still form, at level C, with level C's bounty limits and windows

### Requirement: Weaker panels wait longer before their verdicts are final
Each panel size and proof level SHALL have a published challenge window, longer for smaller panels and for weaker levels, and at least 7 days for k = 1. A panel's verdict SHALL become final, and any payment SHALL start, only when its window has passed with no challenge upheld.

#### Scenario: A large panel's quick finality
- **WHEN** a k = 7 level A panel passes a fix and nobody challenges within its window
- **THEN** the verdict is final after that shorter window, and the first instalment starts

#### Scenario: A level C panel
- **WHEN** a panel of 3 level C validators passes a fix
- **THEN** it becomes final only after level C's longer window for k = 3, leaving time for anyone to re-run the tests and challenge

### Requirement: A lone judge's verdict is held until it can be challenged
A k = 1 verdict's window SHALL run only while at least CHALLENGE_K[1] validators are eligible for its challenge panel: active, outside its panel, not a party, and bonded for its bounty. Until then it SHALL NOT be final and no payment SHALL start. The judge's fee SHALL still be paid when its verdict is posted.

#### Scenario: The genesis validator's first verdicts
- **WHEN** the only active validator passes a fix to a $40 bounty
- **THEN** the verdict is held, unpaid, until three other validators eligible for its challenge are active, and only then does its 7-day window start

#### Scenario: The network already has challengers
- **WHEN** a k = 1 verdict is given while three or more other validators are eligible for its challenge panel
- **THEN** its window starts at once, as for any panel

### Requirement: A validator's pending lone verdicts are capped
A validator SHALL NOT be drawn at k = 1 while it has the published maximum number of k = 1 verdicts that aren't final (10 at launch).

#### Scenario: A lone validator at the cap
- **WHEN** the genesis validator has 10 held k = 1 verdicts and another small bounty receives a submission
- **THEN** the submission waits until one of those verdicts is final, and its waiting shadows are drawn meanwhile

### Requirement: A challenge is judged by a larger, fresh panel
Within a verdict's window, anyone MAY challenge it with the published stake and evidence. A fresh panel, drawn without the original judges or any party, SHALL judge it: CHALLENGE_K[k] validators, or fewer if still an odd number larger than k (K_MAX for a panel of K_MAX). Otherwise the challenge SHALL wait, with the window frozen. An upheld challenge SHALL reverse the verdict and pay the challenger; a failed one SHALL pay the stake to the accused.

#### Scenario: A lone validator passes a bad fix
- **WHEN** a k = 1 panel passes a fix, and within k = 1's window a challenger re-runs the check, gets a fail, and challenges with the stake
- **THEN** a fresh panel of 3 judges the challenge; if it upholds it, the fix doesn't merge, no payment starts, and the challenger is paid

#### Scenario: A challenge with too few validators
- **WHEN** a challenge against a panel of 3 is filed while only 3 validators outside it are eligible
- **THEN** the challenge waits for a panel of 5; the verdict stays not final, and the window doesn't expire while it waits

### Requirement: An upheld receipt challenge
When a challenge panel's majority finds a judge's receipt false, the receipt challenge SHALL be upheld and the judge slashed for a false verdict. The challenge panel's own majority on the fix SHALL then decide it: the verdict SHALL be reversed if that majority votes against it, and SHALL otherwise stand, as the larger panel judged it. A disputed verdict SHALL NOT be voided and judged again from the start.

#### Scenario: A lone judge's false receipt on a bad fix
- **WHEN** a challenge panel of 3 finds a k = 1 judge's receipt false, and its majority fails the fix
- **THEN** the judge loses its whole bond, the verdict is reversed, and no payment starts

#### Scenario: A false receipt on a fix the panel passes
- **WHEN** a challenge panel finds a judge's receipt false, but its majority, re-running the check, passes the fix
- **THEN** the judge loses its whole bond, and the verdict stands; a second auditor's dispute on a k = 1 verdict may still challenge it

### Requirement: Random audits re-check a share of verdicts
After each panel reveals, a published share of submissions (10 % at launch) SHALL be drawn for audit by the same seed: one eligible validator outside the panel and not a party SHALL re-run the check and post its own sealed result. A mismatch SHALL open a challenge at no stake to the auditor. Audits SHALL be paid from check fees, and an auditor SHALL share in any slash its audit leads to.

#### Scenario: Nobody is watching
- **WHEN** a panel's verdict is wrong and no one challenges it
- **THEN** it is still re-checked if drawn for audit, and the audit's mismatch opens a challenge before the window ends

#### Scenario: An audit agrees
- **WHEN** an auditor's re-run matches the panel's verdict
- **THEN** nothing changes, and the auditor is paid its metered usage and the service fee

### Requirement: Every lone verdict is audited twice
Besides the random share, every k = 1 verdict SHALL be audited by two different validators outside its panel and not parties, each drawn by its seed as soon as it is eligible, before the verdict becomes final. Each auditor SHALL re-run the check on its own and post its sealed result; a mismatch from either SHALL open a challenge at no stake to that auditor.

#### Scenario: Validators qualify after the genesis
- **WHEN** the genesis validator holds k = 1 verdicts, and a second and then a third validator become active
- **THEN** each held verdict is audited by the second and then by the third, and any mismatch opens a challenge that waits for a fresh panel of 3

#### Scenario: One auditor misses a bad fix
- **WHEN** a k = 1 verdict passes a bad fix, and one auditor's re-run wrongly agrees while the other's disagrees
- **THEN** the second auditor's mismatch opens a challenge before the verdict can become final

### Requirement: Every split level C pass is audited
Besides the random share, every pass by a panel at level C whose judges weren't unanimous SHALL be audited before it becomes final.

#### Scenario: A split level C pass
- **WHEN** a panel of 7 at level C passes a fix by 4 votes to 3
- **THEN** the verdict is audited before it becomes final, whatever the random draw

### Requirement: The constitution tier has a fixed size
ADRs and fixes escalated to the constitution tier SHALL be judged by exactly K_MAX validators drawn under the caps, passing with the version's published constitution threshold. The issue-tier panel SHALL NOT judge them.

#### Scenario: An ADR on a grown network
- **WHEN** an ADR is submitted while at least the published minimum of validators are eligible
- **THEN** K_MAX are drawn and the ADR needs the constitution threshold of them

### Requirement: The constitution tier waits for the network
An ADR that only removes accepted TEE types, proof types, notaries or image digests, or raises a minimum firmware level, SHALL be drawn only while at least the published removal minimum (14) are eligible. Any other ADR, and any escalated fix, SHALL be drawn only while at least the published minimum (21) are eligible. One submitted while fewer are eligible SHALL expire unjudged, with its fees and deposit refunded less charges metered.

#### Scenario: An adding ADR on a small network
- **WHEN** an ADR adding a TEE type is submitted while 18 validators are eligible and K_MAX is 7
- **THEN** it expires unjudged, nobody is drawn for it, and its author may submit it again once 21 are eligible

#### Scenario: A removal on a small network
- **WHEN** an ADR removing a TEE type with a published exploit is submitted while 15 validators are eligible
- **THEN** K_MAX are drawn and judge it, since an ADR that only removes needs 14

#### Scenario: An ADR that removes and adds
- **WHEN** an ADR removes one notary and lists another
- **THEN** it needs 21 eligible validators, as any ADR that adds something

#### Scenario: The network reaches the threshold
- **WHEN** the twenty-first validator becomes eligible
- **THEN** no earlier adding ADR is drawn, because none is waiting; only those submitted from then on are judged

### Requirement: A rejected ADR forfeits its deposit
An ADR's author, and the solver of an escalated fix, SHALL post the published ADR deposit ($15 at launch) with it, beside the verdict fees. The deposit SHALL be refunded when the ADR takes effect or expires unjudged, and SHALL go to the sponsors' pool when the constitution tier rejects the ADR, at its first judging or after a challenge.

#### Scenario: A rejected ADR
- **WHEN** the constitution tier rejects an ADR
- **THEN** its $15 deposit goes to the sponsors' pool, and no account directs it

#### Scenario: A rejected escalated fix
- **WHEN** the constitution tier rejects a fix that was escalated because it touches protected paths or was flagged as constitutional
- **THEN** its $15 deposit goes to the sponsors' pool, not to the issue's funder or reporter

#### Scenario: An ADR that expires
- **WHEN** an ADR expires unjudged because too few validators are eligible
- **THEN** its deposit is refunded

#### Scenario: An ADR that takes effect
- **WHEN** an ADR passes the constitution tier and its challenge window passes with no challenge upheld
- **THEN** its deposit is refunded

### Requirement: An ADR's notice doesn't depend on its judges' levels
An ADR that passes the constitution tier SHALL take effect after the constitution's notice window, or the short removal window for removals, whatever the proof levels of the judges that passed it.

#### Scenario: An ADR passed by a mostly level C panel
- **WHEN** a constitution panel whose level is C passes an ADR adding a notary
- **THEN** the ADR takes effect after the full challenge window, as any addition does
