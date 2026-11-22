# Spec Delta

## Purpose
The bounty bot: a service that does a bounty's role-free steps on the devnet with nobody typing commands. It links an opened bounty to the issue that claims its registration, settles a bounty whose outcome is final, calls the contract's due deadlines (`timeOut`, `mergeExpired`, `sunset`), closes the issue once its bounty ends, and hints once on an unclaimed labelled issue. It never acts for a reporter, funder, solver, judge or maintainer. It holds only its own key and token, keeps no state of its own, and runs on the on-demand seats host, which a watcher starts for its work.

## ADDED Requirements

### Requirement: The bot does only role-free steps
The bot SHALL only link, hint, settle, call due housekeeping and close. It SHALL NOT register, sign or relay any check or verdict, pledge, attempt, seal, merge, challenge, claim, withdraw or warp. Its only transactions SHALL be `settle`, `timeOut`, `mergeExpired` and `sunset`. It SHALL hold no reporter's, funder's, solver's or seat's key, and SHALL refuse to start if its key is an active oracle key or the deployer's.

#### Scenario: A labelled issue with no registration
- **WHEN** a `bounty`-labelled issue names no registration
- **THEN** the bot registers nothing and opens nothing for it

#### Scenario: A seat's key
- **WHEN** the bot is started with a key that is an active oracle key
- **THEN** it exits with code 2 before sending or writing anything

#### Scenario: What it sends
- **WHEN** a full loop runs with the bot
- **THEN** every transaction from the bot's address is a call to `settle`, `timeOut`, `mergeExpired` or `sunset`

### Requirement: The reporter's registration is a manual step
Registering an issue SHALL stay the reporter's own step, from the reporter's wallet. Done SHALL mean that a labelled issue goes to paid and closed with only the reporter's, funder's and solver's own steps, the maintainer's merge and, on the devnet, the clock's warps.

#### Scenario: The steps a person takes
- **WHEN** a bounty goes from a labelled issue to paid and closed on the devnet
- **THEN** the only commands people ran are the reporter's registration, the funder's pledge, the solver's attempt and seal, the maintainer's merge and the warps

### Requirement: An issue claims its registration, and the first valid claim wins
An issue SHALL claim on-chain issue N with a `Registration: N` line and a `Reporter wallet:` line in its body. The claim SHALL be valid only if the issue is labelled `bounty`, N's reporter is that wallet, N's repository is the configured repository's id, and no lower-numbered issue on that repository validly claims N. The seats' check and the bot SHALL apply this same rule.

#### Scenario: The wrong wallet
- **WHEN** an issue claims registration 7 with a wallet that isn't registration 7's reporter
- **THEN** the claim is invalid: the seats don't check it and the bot doesn't link it

#### Scenario: Two claimants
- **WHEN** issues #12 and #15 both validly claim registration 7
- **THEN** only #12 is linked to its bounty

### Requirement: The bot links an opened bounty to its claiming issue
For an open labelled issue with a valid claim on registration N, once N has a bounty, the bot SHALL comment the bounty's link with its marker, once. It SHALL re-read the issue's comments immediately before writing, and SHALL NOT comment if a link marker for this race is already there.

#### Scenario: Opened by the seats
- **WHEN** the seats' check opens bounty 4 for registration 7, which issue #12 claims
- **THEN** within two passes the bot comments bounty 4's link on #12, and no other issue gets it

#### Scenario: Already linked
- **WHEN** issue #12 already has bounty 4's link marker
- **THEN** the bot writes nothing to it

### Requirement: The bot hints once on an unclaimed labelled issue
For an open labelled issue with no link and no valid claim, at least `HINT_GRACE` old, the bot SHALL comment one hint with a hidden marker. The hint explains the `Registration: N` and `Reporter wallet: 0x…` lines and gives the reason the claim is invalid, if any. The bot SHALL NOT post a second hint on that issue, whatever later edits, restarts or relabelling happen.

#### Scenario: No lines
- **WHEN** a labelled issue without the two lines is older than `HINT_GRACE`
- **THEN** the bot comments one hint naming both lines

#### Scenario: Still invalid after an edit
- **WHEN** the reporter edits the issue and the claim is still invalid, and the bot restarts
- **THEN** no second hint is posted

#### Scenario: A valid claim in time
- **WHEN** the reporter adds a valid claim before `HINT_GRACE` has passed
- **THEN** no hint is posted, and the link follows once the bounty opens

### Requirement: The bot settles a bounty once its outcome is final
The bot SHALL call `settle` for any bounty on its race that is `Merged` with `earned(b, epoch)` at least the configured instalments, or `Paid`, `Unsolved` or `Refunded`. It calls it for the record's coin and then each other fee coin not yet `settled` whose pot holds something. It SHALL NOT call `settle` for a bounty whose outcome isn't final.

#### Scenario: Not due yet
- **WHEN** a bounty is `Merged` with 3 of 4 instalments earned
- **THEN** the bot sends nothing for it

#### Scenario: Due
- **WHEN** the clock reaches the release that earns its 4th instalment
- **THEN** the bot's next pass settles it, and it's `Paid`

#### Scenario: Sunset
- **WHEN** a bounty becomes `Unsolved`
- **THEN** the bot settles it once, so its funders' refunds open

### Requirement: The bot calls the contract's deadlines once they are due
The bot SHALL call `timeOut` for a submission with no outcome once `day()` reaches its day plus `resultDays`. It SHALL call `mergeExpired` for a `Won` bounty once `day()` passes its `mergeBy`, and `sunset` for an `Open` bounty with no submission waiting once `day()` reaches `idleSince` plus `idleDays`. It SHALL call them in that order within a pass, never before they are due, and at most once each. A revert because someone did it first counts as done.

#### Scenario: A submission never revealed
- **WHEN** a sealed submission has no result and its `resultDays` have passed
- **THEN** the bot times it out once, and its deposit less the evaluation fee returns to the solver

#### Scenario: A winner never merged
- **WHEN** a `Won` bounty's `mergeBy` has passed
- **THEN** the bot calls `mergeExpired` once, and the bounty is `Open` again

#### Scenario: An idle bounty
- **WHEN** an `Open` bounty has had no submission waiting for `idleDays`
- **THEN** the bot sunsets it once, and it is `Unsolved`

#### Scenario: A day early
- **WHEN** a deadline falls due tomorrow
- **THEN** the bot sends nothing for it today

#### Scenario: Someone else first
- **WHEN** another account times out a submission between the bot's read and its transaction, and the bot's call reverts
- **THEN** the bot counts it as done and doesn't retry it

### Requirement: The bot closes an ended bounty's issue
For an open labelled issue linked to a bounty on its race that has ended, the bot SHALL comment once and then close the issue, whoever ended the bounty. For `Paid` the comment names the payout transaction; for `Unsolved` or `Refunded` it states the outcome and its transaction. The bot SHALL leave alone issues whose bounty hasn't ended, closed issues, and issues without the `bounty` label.

#### Scenario: Settled by someone else
- **WHEN** a person settles bounty 4 with `pofctl`, and issue #12 is linked to it
- **THEN** the bot comments the payout transaction on #12 and closes it

#### Scenario: Unsolved
- **WHEN** bounty 5 sunsets, and issue #13 is linked to it
- **THEN** the bot comments once that it ended unsolved, naming the sunset's transaction, and closes #13

#### Scenario: Not ended
- **WHEN** issue #12's bounty is `Won`
- **THEN** the bot leaves #12 open and writes nothing to it

#### Scenario: Reopened by a person
- **WHEN** a person reopens a closed issue and removes its `bounty` label
- **THEN** the bot doesn't close it again

### Requirement: Every action happens once, from the chain's and the forge's state
The bot SHALL keep no local database. It SHALL decide each step from the chain and the forge, re-read just before it writes. A restart at any point SHALL repeat no comment and send no transaction whose effect has already happened. After a crash between sending a transaction and its receipt, the bot SHALL send nothing new from its account while it has a pending transaction, for up to 10 minutes.

#### Scenario: A crash after the payout comment
- **WHEN** the bot stops after commenting a payout and before closing the issue, and starts again
- **THEN** it closes the issue without a second comment

#### Scenario: A crash after sending settle
- **WHEN** the bot stops after sending `settle` and before reading its receipt, and starts again
- **THEN** it waits for the pending transaction, sees `Paid`, and goes on to close

#### Scenario: A crash after sending sunset
- **WHEN** the bot stops after sending `sunset`, and starts again
- **THEN** it sees the bounty `Unsolved` and sends no second `sunset`

### Requirement: The bot uses only its own key and token, read once from files
The bot SHALL sign with its own devnet key, role `bot-service`, never the `bot` key people use with `pofctl`. It SHALL reach the devnet with its own API key and the forge with a token limited to issues on its repository. It SHALL read each from a file named by `POF_BOT_KEY_FILE`, `POF_BOT_RPC_AUTH_FILE` or `POF_BOT_FORGE_TOKEN_FILE`, once at start, and SHALL refuse a missing file or a chain other than the devnet's or anvil's.

#### Scenario: A public chain
- **WHEN** the RPC answers a chain ID other than 7193 or 31337
- **THEN** the bot exits with code 2 before sending or writing anything

#### Scenario: The token's reach
- **WHEN** the bot's forge token is used to push a branch or merge a pull request
- **THEN** the forge refuses it

### Requirement: No secret on a command line or in output
No option of `pofctl bot watch` SHALL take a key, token or credential, and an RPC URL with user info SHALL be refused. The bot's output and logs SHALL contain no key, token or credential, including in error texts from its HTTP and RPC clients, which SHALL be redacted against every secret read at start.

#### Scenario: An error carrying the token
- **WHEN** a forge error's text includes the request's token
- **THEN** the logged line shows it redacted

#### Scenario: The process list
- **WHEN** the bot runs on the host
- **THEN** its command line and environment hold file paths, not secret values

### Requirement: The bot polls with bounded writes and backs off on errors
The bot SHALL pass every `POLL_SECONDS` (30 on the host) and make at most 5 writes a pass and 50 a run (then exit 4); every transaction, comment and close counts. It SHALL skip for the rest of the run an item refused 3 times. After a pass that fails to read the chain or the forge, it SHALL wait `POLL_SECONDS` × 2^k up to 300 s, k being the consecutive failed passes, and SHALL honour a `Retry-After` up to 300 s.

#### Scenario: Many due at once
- **WHEN** 8 actions are due, settlements and deadlines together
- **THEN** 5 are done in one pass, in the pass's order, and 3 in the next

#### Scenario: The forge down
- **WHEN** three passes in a row fail to read the forge
- **THEN** the waits before the next passes are 60, 120 and 240 s, and no write is made to the forge until a read succeeds

### Requirement: The bot exits when idle or when its services are away
With `--until-idle S`, the bot SHALL exit 0 after S seconds with no write and nothing waiting. A claimed registration not yet opened, and an unclaimed labelled issue younger than `HINT_GRACE`, SHALL count as waiting, the first for up to 900 s. A deadline or instalment in the future SHALL NOT. If the chain or the forge fails for 1,800 s in a row, it SHALL exit 75.

#### Scenario: Nothing to do
- **WHEN** the only bounty is `Merged` and due in five days
- **THEN** the bot exits 0 after its idle time, so the host can power off

#### Scenario: The devnet's night stop
- **WHEN** the chain stops answering for 30 minutes
- **THEN** the bot exits 75

### Requirement: The watcher starts the host for the bot's work
With `BOT_WORK=true` and `BOT_ENABLED=true`, the watcher SHALL also start the stopped host for: a registration in `BOT_REPO_IDS` still `Posted` with no bounty (again every `PENDING_POLL_MINUTES`, at most `PENDING_MAX_STARTS`); a new `BountyOpened` (once); a new end to `Paid`, `Unsolved` or `Refunded` (once); and anything due (the next requirement). It SHALL read only the chain and share the seats' daily fuse.

#### Scenario: The bot's switch off
- **WHEN** `BOT_ENABLED` is false and the only work is a bounty due to settle
- **THEN** the watcher doesn't start the host, and the seats' work still starts it

#### Scenario: The shared fuse
- **WHEN** the day's `MAX_STARTS_PER_DAY` is reached
- **THEN** the bot's work starts the host no more that day, as for the seats' work

#### Scenario: A labelled issue alone
- **WHEN** a labelled forge issue appears and nothing on the chain is due
- **THEN** the watcher doesn't start the host for it

### Requirement: The watcher starts the host when something falls due
With the bot's work on, the watcher SHALL start the stopped host, and again every `DUE_POLL_MINUTES` while it stays due, for: a `Merged` bounty with every instalment earned; a submission with no outcome past its `resultDays`; a `Won` bounty past its `mergeBy`; an `Open` bounty with no submission waiting past its `idleDays`. It SHALL re-check each with the contract's views, and its result SHALL name the work.

#### Scenario: Due to settle while stopped
- **WHEN** the host is stopped and a `Merged` bounty earns its last instalment
- **THEN** the watcher's next run starts the host, and its result names `settle`

#### Scenario: A deadline while stopped
- **WHEN** the host is stopped and a `Won` bounty passes its `mergeBy`
- **THEN** the watcher's next run starts the host, and its result names `merge-expired`

#### Scenario: No longer due
- **WHEN** someone else sunsets a bounty before the watcher's next run
- **THEN** the watcher drops it and doesn't start the host for it

### Requirement: The bot runs on the seats host beside the nodes
On infra#219's host, the bot SHALL run as its own container from the nodes' pinned image, without the Docker socket. Only its own secrets SHALL be mounted, read-only, as files. No node's secret SHALL be in it, and none of its secrets in a node's container. The host SHALL power off only when every node and the bot have exited, or at its maximum run time.

#### Scenario: The bot's container
- **WHEN** the bot's container is inspected on the host
- **THEN** it has no Docker socket, no seat key, and no secret value in its configuration

#### Scenario: Idle together
- **WHEN** the six nodes have exited and the bot is still settling
- **THEN** the host stays up until the bot exits

### Requirement: The untyped loop is tested locally and on the AWS devnet
The local suite SHALL run scenario 10 with no `pofctl oracle accept`, `bot link`, `bot settle` or `bot close` from the test. In 10a, a labelled, registered issue is solved, paid and closed, and the bot, restarted once, repeats nothing. In 10b, a timeout, an expired merge and a sunset happen, and the issue is closed as unsolved. In 10c there is one hint. With `--target aws --hosted-bot`, the same SHALL run against the hosted seats and bot.

#### Scenario: Local
- **WHEN** `scripts/integration.sh --only 10` runs
- **THEN** each issue has its one link, payout, ending or hint comment, the ended ones are closed, and every bot transaction came from `bot-service`'s address

#### Scenario: On the AWS devnet
- **WHEN** `scripts/integration.sh --target aws --hosted-bot --only 10` runs
- **THEN** the issue on `pof-sandbox` goes to paid and closed with only the reporter's, funder's and solver's own steps, the maintainer's merge and the clock's warps from the suite
