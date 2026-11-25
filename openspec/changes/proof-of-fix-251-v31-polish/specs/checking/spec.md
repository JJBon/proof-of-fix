# Spec Delta

## ADDED Requirements

### Requirement: A seated judge's family is payable at its check's prices
A check SHALL be charged at the prices in force when it opened, and a paid seat on it (counted, a replacement, an audit or a challenge seat) SHALL go only to a validator whose model family was priced at or before that opening. So every payment for a check SHALL be computable, whenever its panels were drawn. A shadow seat MAY still go to a family priced later, and is then paid nothing, as before.

#### Scenario: A family priced after the check opened
- **WHEN** a check opens, a new model family gets its first price at the next pricing period, and the check's panel is drawn afterwards (a re-drawn seed, a replacement, an audit or a challenge)
- **THEN** no validator of that family is given a paid seat on that check, and the check's result, its panels' pay and its challenges' settlements all go through

#### Scenario: The same family on a later check
- **WHEN** a check opens after that family's first price
- **THEN** its validators can be drawn for it like any priced family's

#### Scenario: A shadow of a newly priced family
- **WHEN** a validator of a family priced after the check opened is drawn as a shadow on it
- **THEN** it judges and is scored as a shadow, and is paid nothing for that seat

#### Scenario: A rebase check
- **WHEN** a rebase check (#310) opens
- **THEN** it is priced, and its seats drawn, by the prices in force at its own opening

### Requirement: No new family is priced where draws lack the rule
On a deployment whose draws don't apply the rule above, the validators' nodes SHALL NOT give a new family its first price: their tables SHALL price only the families already priced.

#### Scenario: A node's table on the live deployment
- **WHEN** a node posts its price table on a deployment whose draws compare a family's first price with the snapshot, not with the check's opening
- **THEN** the table holds only families already priced, so no new family can be priced there and no check can be locked by one

### Requirement: A pricing period closes in bounded steps
Closing a pricing period SHALL be done in steps anyone may take, each bounded in the work and the new storage it does, so that each step fits well under a block's gas limit and under the per-transaction limit of EIP-8037 at the network's smallest posting quorum. A step's success SHALL NOT depend on how much gas beyond its need the caller sent.

#### Scenario: Many families at the smallest quorum
- **WHEN** a period closes with three counting posters, forty priced families, twenty announced and every price moving
- **THEN** every step's gas, counting EIP-8037's cost of each new storage slot, stays at or under 8 million

#### Scenario: More gas never fails
- **WHEN** a caller takes a step with any gas limit at or above the step's estimate
- **THEN** the step succeeds

### Requirement: One name per model family
A model family SHALL have one name everywhere: the deployment's families, the validators' registrations, the price tables the nodes post, and the guides. The name SHALL be the provider's model line in the form `provider/line` (for example `anthropic/claude`). A deployment plan naming a family in another form SHALL be refused before anything is sent.

#### Scenario: The genesis family is priced by the market
- **WHEN** a deployment seats `anthropic/claude` and validators of other families post tables with that family's list price
- **THEN** the posted prices count toward its median, and its price moves with them

#### Scenario: A plan in another form
- **WHEN** a deployment plan names the family `anthropic.claude`
- **THEN** the deploy script refuses the plan and names the expected form

### Requirement: A sleeping network still draws its checks
A validator's watcher SHALL start its stopped host when a check of the deployment is still undrawn a grace period after its seed block, or still waiting past its retry time, so that the host's node draws it and signals the draw. The wake SHALL be staggered per validator and check, so that usually one validator wakes, not all.

#### Scenario: An idle network gets a new check
- **WHEN** every validator's host is stopped and a reporter registers an issue
- **THEN** within the grace period plus the stagger, one validator's host is started, its node draws the check and signals it, and the drawn judges' hosts are started for their seats

#### Scenario: A keeper is already running
- **WHEN** an always-on keeper draws the check within the grace period
- **THEN** no validator's host is started for the draw

### Requirement: Anyone can keep the clockwork moving without registering
The node SHALL have a keeper-only mode that makes the calls anyone may make (draws, replacements, finality, refunds, pay, the pricing period's steps) with a key that only pays gas, on any chain, with no registration, bond, judge or Radicle seat. In that mode it SHALL never seal, reveal, judge or post a price table.

#### Scenario: A keeper with no bond
- **WHEN** an operator runs the node in keeper-only mode with a key that has gas and no registration
- **THEN** it draws and settles the deployment's checks, and sends no seal, reveal or price table

#### Scenario: A guard on the gas it spends
- **WHEN** the keeper-only node has sent its configured most transactions in an hour
- **THEN** it sends no more until the hour has passed, and says so once

### Requirement: Keepers send a gated call only when it is due
A keeper SHALL send a call anyone may make only when the chain's readable state says it is due; a call whose readiness can't be read SHALL be tried at most a few times per state of what it waits for, with backoff in between.

#### Scenario: A verdict waiting for its final time
- **WHEN** a verdict is final but its report window hasn't ended
- **THEN** the keeper doesn't ask to finish it until the window has ended

#### Scenario: A hold that can't end yet
- **WHEN** a held lone verdict can't start its window because too few challengers are ready
- **THEN** the keeper asks at most a few times per state of the registry and per capacity window, not on every pass

### Requirement: A payment that is only late is never given up
A refusal that only means "not yet" SHALL NOT count toward a keeper giving up a call, and giving up a payment SHALL be a time limit, not a count of attempts.

#### Scenario: One late usage report
- **WHEN** one auditor of a panel never sends its usage report
- **THEN** no keeper asks for the panel's pay before the report window ends; once it has, the pay is sent and succeeds, and the auditors who reported are paid

### Requirement: A rate limit never delays a commit or a reveal
An RPC provider's rate limit SHALL slow the keeper's calls, never a seat's commit, reveal or usage report.

#### Scenario: Rate limited
- **WHEN** the RPC provider answers HTTP 429 during a pass while a seat's reveal is due
- **THEN** the reveal is sent in that pass or the next, and the keeper's calls pause for the provider's Retry-After or a backoff

### Requirement: A call whose success depends on its gas is sent with enough
A keeper SHALL send a call whose outcome depends on the gas it is given with at least a published floor that puts it on its paying branch.

#### Scenario: A shadow's pay
- **WHEN** a keeper pays a finished shadow seat
- **THEN** it sends the call with at least the published gas floor, and the seat is paid in full

### Requirement: A counted verdict is posted on its issue
Once a verdict is counted, one judge's node SHALL comment a short receipt on the Radicle issue of the bounty or registration: the outcome, the panel's size, the verdict's state with its times, and the counting transaction. The judges' reason SHALL be included only where it reveals no sealed evidence: at once for a registration check without hidden tests, and for a fix check only once its bounty is paid or closed unsolved. The comment SHALL be made once per verdict.

#### Scenario: A registration judged a pass
- **WHEN** a registration check without hidden tests is counted as a pass at k = 1
- **THEN** its Radicle issue gets one comment saying it passed, why in one line, that the verdict is held until enough validators can challenge it, and the transaction

#### Scenario: A fix judged before the bounty settles
- **WHEN** a fix check is counted while its bounty is still open
- **THEN** its issue's comment gives the outcome and state only; the reason is posted once the bounty is paid or closed

#### Scenario: Two judges' nodes
- **WHEN** a second judge's node finds the verdict's comment already on the issue
- **THEN** it doesn't comment again

### Requirement: No RPC key appears in a log
No log line of the node, the keeper, the watcher or the participants' tool SHALL contain an RPC provider's key, whether it is in the URL's user info, its path or a header, including in error messages and tracebacks.

#### Scenario: A rate-limited provider with the key in its path
- **WHEN** an RPC URL of the form `https://<provider>/v3/<key>` answers HTTP 429 and the call is retried and then fails
- **THEN** every line logged names the provider's scheme and host only, never any part of the key

### Requirement: A short rate limit is retried, not fatal
A read or a signed transaction's broadcast that an RPC provider refuses with a rate limit SHALL be retried a few times by default, honouring the provider's Retry-After up to a bound, by the node, the keeper and the participants' tool alike. Longer storms SHALL be left to the keeper's backoff and the next pass.

#### Scenario: One 429 during a command
- **WHEN** a participant's command gets HTTP 429 with Retry-After of 2 seconds on a read
- **THEN** it waits, retries and completes, without the participant doing anything

### Requirement: The guides state how long a verdict takes
The guides SHALL state, from the deployment's windows, how long a check takes to a counted verdict and what follows it: on a deployment that waits out the commit window, hours; with early reveal, minutes once every seat has committed; and for a lone verdict, the hold until enough validators can challenge it.

#### Scenario: A reporter on the live deployment
- **WHEN** a reporter registers an issue on v3 and reads the guide
- **THEN** it expects about two to three hours to a verdict, then a hold until six to seven validators with room, and on v3.1 minutes to the verdict
