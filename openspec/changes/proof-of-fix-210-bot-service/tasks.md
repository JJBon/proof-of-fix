# Tasks

## 1. The bot service

- [x] 1.1 The claim (D2) in `bot/logic.py`: parse `Registration: N` beside `Reporter wallet:`, and a pure `first_valid_claim(issues, onchain_issue, repo_id)` used by both the bot and the node. Verify: unit tests for a valid claim, the wrong wallet, the wrong repository, an unlabelled issue, two claimants (the lower number wins), and an edited body after the link.
- [x] 1.2 The new comments and markers (D5) in `bot/logic.py`: `ended_comment` with `pof-ended` (the outcome, its transaction, what opens), and `hint_comment` with `pof-hint` (both lines, `pofctl reporter register`, the reason, and that the bot never registers), with their parsers. Verify: unit tests that each marker round-trips, and that each reason produces its own text.
- [x] 1.3 `pofctl reporter register` prints both lines to paste (`Registration: N` and `Reporter wallet: 0x…`). Verify: a `tests/test_pofctl.py` test of the output's lines.
- [x] 1.4 The `bot-service` role, appended to `scripts/devnet-keys.sh`'s roles and `pofctl/keys.py`'s `ROLES`, so every other role keeps its index. Verify: the existing test that the two lists match, and a test that the indexes of the earlier roles are unchanged.
- [x] 1.5 `bot/service.py`: one pass in D4's order (settle, housekeeping, close, link, hint), behind small chain and forge interfaces, with the re-read before each write, the pending-nonce wait, a revert because the action was already done counted as done, and `--min-bounty`. Verify: unit tests with a fake chain and a fake forge (`tests/test_bot_service.py`):
  - each step happens once over 20 passes;
  - a crash injected after each write, followed by a new service on the same fakes, repeats nothing;
  - the only chain writes are `settle`, `timeOut`, `mergeExpired` and `sunset`.
- [x] 1.6 Housekeeping and endings in `bot/service.py`: `timeOut`, `mergeExpired` and `sunset` from the contract's views and `getConfig()`; settling `Unsolved` and `Refunded` bounties; the `pof-ended` close; the one hint after `HINT_GRACE`. Verify: unit tests that:
  - each deadline is sent once on its due day and not the day before;
  - another account's prior call reverting the bot's counts as done;
  - a timeout that frees a sunset lands in the same pass;
  - an `Unsolved` bounty is settled and its issue gets one ending comment and is closed;
  - a reopened, unlabelled issue stays open;
  - the hint is posted once and never again after an edit, a restart or relabelling;
  - no hint goes to a linked issue or one younger than `HINT_GRACE`.
- [ ] 1.7 The forge user `pof-bounty-bot` on `pof-sandbox` (owner, with the platform admin): a team with write on issues alone, a `write:issue` token, kept in OpenBao. Verify: with the token, listing and commenting on `pof-sandbox`'s issues works, and pushing a branch, merging a pull request and reading another repository are refused. Record which units the team needed (D6).
- [x] 1.8 `pofctl bot watch` (D6, D7):
  - the secrets read once from the `POF_BOT_*_FILE` files, or `DEVNET_KEYS=insecure-local`;
  - the refusals at start: the chain, an oracle or deployer key, a missing file, an RPC URL with user info;
  - the poll, the write limits counting every transaction, comment and close, backoff, `Retry-After`, `MIN_GAS`, `HINT_GRACE`, `--until-idle` and the exit codes;
  - the JSON lines through a redactor.

  Verify: unit tests with a fake clock for each limit and exit code (8 mixed due actions take two passes in D4's order), and a leak check over all output with known secret values.

## 2. The seats' registration check

- [x] 2.1 The exchange's `accept` kind under `issue/<N>` (`exchange/service.py`), with the folder transport's mirror (`oracle/transport.py`). Verify: `tests/test_exchange.py` tests that it takes a signature from an active oracle key over the right digest, and refuses a non-oracle key (403), a wrong digest, and an issue that's already open.
- [x] 2.2 The node's check (`oracle/node_v2.py`, D3): `ORACLE_REGISTRATION_CHECK`, the claim rule from 1.1, the fake judge only, `ORACLE_REGISTER_WEIGHT`, the deterministic nonce, the relay by the lowest-addressed signer with `ORACLE_RELAY_GRACE`, and the idle rule. Verify: a rig test with the folder transport and five keys:
  - a quorum opens the bounty with one `accept`;
  - an unclaimed registration gets no signature;
  - with the relayer stopped, another relays after the grace;
  - a model judge signs nothing.

## 3. The watcher

- [x] 3.1 The bot's work in `validator-kit/lambda/watcher.py` (D8): `BOT_WORK`, `BOT_ENABLED`, `BOT_REPO_IDS` and `DUE_POLL_MINUTES`.
  - The work: registrations, openings, endings (`Paid`, `Unsolved`, `Refunded`), and what's due (settle, `timeOut`, `mergeExpired`, `sunset`), each re-checked with the views.
  - The candidate lists kept in the state parameter, with `state-full`.
  - The result line naming the work.

  Verify: `tests/test_validator_kit.py`'s watcher tests, with fakes:
  - each kind starts a stopped host;
  - each due kind restarts it every `DUE_POLL_MINUTES` and stops once it isn't due;
  - `PENDING_MAX_STARTS` bounds registrations;
  - an overflowing state keeps the oldest entries and says `state-full`;
  - `BOT_ENABLED=false` leaves only the seats' work, and the fuse is shared;
  - with `BOT_WORK` unset, the kit's results are unchanged.

  The new selectors are checked against keccak256 of their signatures.

## 4. The image and the hand-over to platform#219

- [x] 4.1 `oracle/Dockerfile` copies `pofctl/` (it came with #212), so one digest runs the nodes and the bot. Verify: the built image runs `python3 -m pofctl bot watch --help` and `python3 -m oracle info` (overriding the entrypoint for the first).
- [ ] 4.2 _(the coordinator hands it over with platform PR #221; the settings' names are in bot/service.py's ENV_DOC)_ Hand D9 to platform#219: a comment on platform#219 (or its follow-up issue, if its change has merged) listing the container, the three parameters, the configuration, the idle rule, the watcher's settings with D8's wake conditions, and the log group. Verify: the comment links this change and lists all six items.
- [x] 4.3 `validator-kit/runbook.md`, "The AWS devnet", covers:
  - the bot's keys and token;
  - how the reporter claims a registration;
  - what the bot closes and how to keep an issue open (remove the label);
  - that `pofctl bot settle` and `bot close` by hand still work but aren't needed.

  Verify: the runbook's commands match `pofctl --help`.

## 5. The untyped loop end to end

- [x] 5.1 Local suite scenario 10a (D10): the bot as its own process with the `bot-service` key and `--min-bounty`, the nodes' check on, and the suite's `ctl` recording every call. The paid path runs with the bot killed once after its link and restarted. Verify: `scripts/integration.sh --only 10` passes 10a, with one link and one payout comment and the issue closed.
- [x] 5.2 Scenario 10b, the deadlines on one bounty: a fix sealed with no pull request times out; a passing fix wins and is never merged, and expires; the bounty sunsets; the bot settles it and closes its issue with one ending comment. Verify: the suite asserts each transaction came from `bot-service`'s address, the states (`TimedOut`, `Open`, `Unsolved`), the solver's deposit return less the evaluation fee, and the one `pof-ended` comment naming the sunset's transaction.
- [x] 5.3 Scenario 10c, the hint: a labelled issue with no lines gets exactly one hint, still one after more passes, an edit and a bot restart. Verify: the suite counts the `pof-hint` markers. Then the full suite passes with scenario 10 run last, `close_watcher`, the leaderboard and the books included.
- [ ] 5.4 _(the options, the guard against typing the bot's commands, the preflight, the timed-out books and the cleanup are in; the offline tests pass; the AWS run waits for 6.2)_ `tests/integration/aws.py --hosted-bot`:
  - 10a, 10b and 10c against `pof-sandbox`;
  - every scenario opens its bounty through the seats and the bot, and calls none of the bot's or the stub quorum's commands;
  - waits up to `--bot-timeout`;
  - the end checks expect the bot's housekeeping on the run's other bounties (a timed-out deposit in the books, issues the bot already closed in the cleanup);
  - the preflight checks `bot-service`'s gas and that it isn't an oracle key.

  Verify: `tests/test_integration_targets.py` covers the new options offline; then, once 6.2 is done, `scripts/integration.sh --target aws --hosted-bot --only 10` passes.

## 6. On the devnet (owner)

- [ ] 6.1 `devnet-keys.sh init` for `bot-service`, devnet gas for its address, and `keys.sh add pof-bot`. Verify: `pofctl --as bot-service balances` shows its gas, and its address isn't an oracle key.
- [ ] 6.2 platform#219's host runs the bot (D9), from an image digest that includes groups 1 to 4. Verify: `seats.sh status` shows the bot's container, and a labelled, registered `pof-sandbox` issue is linked with the host started by the watcher. The first runs' backlog of stale deadlines is worked through within the write fuse, and the runs' logs show it.
- [ ] 6.3 #210's last box, as corrected on PR #211: a labelled `pof-sandbox` issue goes to paid and closed with only the reporter's, funder's and solver's own steps (plus the maintainer's merge and the clock's warps). Verify: 5.4's AWS run, and its report linked on #210.

## 7. Check

- [ ] 7.1 Run the check: `bash scripts/check.sh` and `openspec validate proof-of-fix-210-bot-service --strict`.
