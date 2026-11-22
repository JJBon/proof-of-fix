# Design

## Context

- **The v2 path today** (`scripts/first_bounty.py`, `tests/integration/aws.py`, `pofctl/cli.py`):
  1. the reporter registers: `pofctl reporter register --repo registry` (`RaceV2.register(coin, repo)`, from the
     reporter's wallet);
  2. a person opens the forge issue, labelled `bounty`, with `Reporter wallet: 0x…` in its body;
  3. the stub quorum opens the bounty: `pofctl oracle accept` signs `accept` with the devnet oracle keys it can read
     (the seats' keys, from OpenBao) and relays it from the `bot` key;
  4. `pofctl bot link` comments the bounty's marker on the issue;
  5. the funder pledges, the solver attempts, seals and opens the pull request: their own steps;
  6. the drawn seats' nodes judge, and sign the merge once a person merges the pull request;
  7. someone warps the devnet's clock past the instalments, then `pofctl bot settle --repo --issue` settles and closes
     the issue with the payout comment (#206). `pofctl bot close` is the same close as a pass over every labelled issue.

  Nobody calls `timeOut`, `mergeExpired` or `sunset`, and an issue whose bounty ends unpaid stays open.
- **v2's rules** (`contracts/src/v2/RaceV2.sol`, `RaceV2Base.sol`, `RaceV2Annex.sol`):

  | Function | Who may call it | When | Effect on the caller |
  |---|---|---|---|
  | `register(coin, repo)` | anyone | any time | becomes the issue's **reporter**: pays the fee, holds the stake, is paid the finder's fee and the refund, and is a party (`isParty`), so a judge it operates is recused |
  | `accept(issue, weight, auth)` | anyone, **with the oracle quorum's signatures** (`Verdicts.authorize`: 5 of 7 on the devnet) | the issue is `Posted` with no bounty | none: a relay |
  | `pledge`, `attempt`, `commit` | anyone | the bounty is `Open` | becomes a **funder** or a **solver**, with their coin |
  | `result`, `merged`, `challengeUpheld`, `junk` | anyone, with the drawn judges' or the quorum's signatures | per verdict | none: a relay |
  | `settle(b, coin)` | **anyone** | the outcome is final: `Merged` with every instalment earned (it becomes `Paid`), or `Paid`, `Unsolved` or `Refunded` | none: pays what's due and starts refunds; once per coin (`settled`) |
  | `timeOut(s)` | **anyone** | submission `s` has no outcome and `day() >= s.day + resultDays` | none: the deposit pays the evaluation fee, the rest returns to the solver |
  | `mergeExpired(b)` | **anyone** | `Won` and `day() > mergeBy` | none: the bounty reopens |
  | `sunset(b)` | **anyone** | `Open`, no submission waiting for its result, and `day() >= idleSince + idleDays` | none: `Unsolved`, the issue's stake returns |
  | `claimInstalments` | anyone | an award has earned instalments | none |
  | `withdrawIssue`, `claimRefund`, `withdraw` | the reporter, a funder, an account | per function | its own money |

- **infra#219** (its design, open on the `platform-219-pof-seats-host` branch): one c6g.large, normally stopped,
  that runs the six role seats' nodes from a pinned image when a watcher Lambda sees work, and powers off when every
  node is idle. Secrets come from OpenBao into SSM SecureString parameters under `/pof-seats/` by the owner's script,
  under a KMS key only the host's role may decrypt; on the host they're files in a tmpfs runtime directory. Its open
  question, whether the bot shares the host, is answered by the owner in #210: it does.
- **The watcher** is proof-of-fix's `validator-kit/lambda/watcher.py`, which infra#219 deploys (its D11). It reads
  only the chain and starts the host for draws and won bounties.

## Goals / Non-Goals

**Goals:**
- on the devnet, a `bounty`-labelled issue whose reporter registered becomes a bounty, and once it ends, paid or not,
  its issue closes, with nobody running `pofctl` for anything but their own role;
- the contract's deadlines (`timeOut`, `mergeExpired`, `sunset`) take effect once due, unattended;
- every step once, whatever crashes or restarts, with the chain and the forge as the only state;
- the bot holds no key or token but its own, and those never appear on a command line or in output;
- it costs the on-demand host nothing extra while there's no work.

**Non-Goals:**
- a real registration check, or any judging by the bot;
- `claimInstalments`; GitHub repositories on the devnet; real money or chains (rule 1).

## Decisions

### D1. The bot does only role-free steps; registering is the reporter's, opening is the judges'

| Step | Whose | Why (v2) | Who does it after this change |
|---|---|---|---|
| register | **reporter** | the caller pays, stakes, is paid and is a party | the reporter (`pofctl reporter register`): a manual step, accepted by the owner |
| the registration check (sign `accept`) | **judges** | the quorum's signatures | the six role seats' nodes (D3) |
| relay `accept` | anyone | a relay | a seat's node (D3) |
| link the forge issue | anyone | a comment; nothing on-chain | **the bot** |
| the hint on an unclaimed labelled issue | anyone | a comment; nothing on-chain | **the bot** |
| fund, attempt, seal, open the pull request | funder, solver | their coin | them |
| judge, sign the merge | judges | drawn signatures | the seats' nodes |
| merge the pull request | the maintainer | the forge's permission | a person (the suite) |
| settle | anyone | `settle` pays by the contract's rules | **the bot** |
| `timeOut`, `mergeExpired`, `sunset` | anyone | due by the contract's own deadlines; the caller gains nothing | **the bot** |
| close the ended issue (paid, unsolved, refunded) | anyone | a comment and a close | **the bot** |

**Registration: the reporter's own wallet, and the bot only links what the seats opened.** The other choice was the
bot's own reporter identity on the devnet: it would register every labelled issue from its key. Rejected because:
- the contract makes the registering wallet the reporter. The bot would pay every stake, take every finder's fee, and
  be a party to every verdict. The person who found the bug would get nothing, and the loop would never test the
  reporter's own payout, the incentive the paper measures;
- it would let whoever can add a label spend the bot's stake, a behaviour no real deployment could keep;
- it doesn't remove the harder step. `accept` needs the quorum's signatures, so the seats must run the registration
  check (D3) either way.

So the bot never registers, and never holds a reporter's key or a seat's key. The cost is one manual step: the
reporter registers and adds a line to the issue. **The owner accepted this on PR #211.** #210's "Done when" now
reads: "On dev, a labelled `pof-sandbox` issue goes to paid and closed with only the reporter's, funder's and solver's
own steps", plus the maintainer's merge and, on the devnet, the clock's warps.

**Housekeeping is role-free.** `timeOut`, `mergeExpired` and `sunset` move no money to their caller, and each is
refused (`NotYet`) before its deadline. The bot calls them when the contract's own views say they're due, for every
bounty and submission on its race, in the order they fell due. That's the contract's rule taking effect, not a choice
of the bot's.

### D2. An issue claims its registration; the first claim wins

- **The claim:** the issue's body has `Registration: <on-chain issue>` and `Reporter wallet: 0x…` on their own lines
  (`bot/logic.py` parses both; `pofctl reporter register` prints both lines to paste).
- **It's valid when:**
  - the issue is labelled `bounty` (the maintainer's opt-in);
  - on-chain issue N exists and its reporter is that wallet (case-insensitive);
  - N's repository is the configured repository's: its registry id (the record's `repo` for `pof-sandbox`), or 0
    for a project outside the registry;
  - no lower-numbered issue on the same repository, open or closed, claims N validly. Issue numbers only grow, so the
    first claim is stable.
- **One rule, two readers:** the seats' check (D3) and the bot's link use the same function, so the check and the
  link always name the same forge issue.
- **An edited claim** after the link changes nothing. The link comment is the record.
- **A stolen claim** (someone else's registration number in another issue) needs the reporter's wallet in the body.
  If it comes first, the bounty is linked to the wrong issue, but the reporter's fee still goes to the registering
  wallet, and the reporter can open a second registration. On the devnet, `pof-sandbox`'s writers are known. Risks
  names it.
- **No valid claim:** the bot posts the hint (D5), once.

### D3. The seats' registration check, fake on the devnet

- **Trigger:** a node's scan sees `Registered(N, reporter)` for an issue that's still `Posted` with no bounty, and a
  valid claim (D2) on the node's own repository. Off unless `ORACLE_REGISTRATION_CHECK=on`: the seats' host and the
  local suite turn it on; the owner's kit (seat 6) leaves it off, since the quorum is 5 of the host's 6.
- **The check:** the fake judge passes every claimed registration. With any other judge mode the node logs
  "registration check: real judges not supported yet" and signs nothing (#160's follow-up).
- **The digest:** RaceV2's `Accept(issue, weight, nonce)`:
  - `weight` = `ORACLE_REGISTER_WEIGHT`, the same configured value on every seat (devnet: 120 coin, the stub quorum's
    `REGISTERED`, so `inflated` stays false against the merge weight 100);
  - `nonce` = keccak256("pof-accept" ‖ race ‖ word(N)), so every seat signs the same digest without a round.
- **The board:** the node posts `{"weight", "nonce", "sig"}` to the exchange, kind `accept`, under `issue/<N>`. The
  exchange takes it only while N is `Posted` with no bounty, from an active oracle key (`Verdicts.isOracle`), with a
  signature that recovers to that key over that digest. The folder transport mirrors it (`<race>/issue-<N>/`).
- **The relay:** a node that reads a quorum of valid signatures relays `accept`, with the signatures sorted by signer
  address as `pofctl/race.py` does. To avoid six relays, the lowest-addressed signer relays at once and the others
  wait `ORACLE_RELAY_GRACE` (30 s) and relay only if the bounty still isn't open. A `Refused` revert because it opened
  meanwhile is success.
- **Idle:** a claimed registration that isn't open yet keeps the node from idling, up to the round timeout.

### D4. One pass of the service; the chain and the forge are the state

`pofctl bot watch` loops over passes. A pass:
1. **Reads:**
   - the head block, `day()` and `getConfig()`;
   - the open `bounty`-labelled issues of each configured repository and their comments;
   - from the race's logs (`BountyOpened`, `StateChanged`, `Committed`, paged by 2,000 blocks, from the record's
     deployment block at start and from the last head after that), the bounties and submissions that could have
     something due.

   The candidate lists are only a cache. Each candidate is re-checked with the contract's views every pass, and
   `--min-bounty N` (default 0) leaves out bounties numbered below N, and their submissions. The local suite scopes
   its bot this way (D10).
2. **Settles** each bounty whose outcome is final: `Merged` with `earned(b, epoch) >= instalments`, or `Paid`,
   `Unsolved` or `Refunded`. It calls `settle(b, coin)` for the record's coin and then any other fee coin that isn't
   `settled(b, coin)` yet and whose pot holds something.
3. **Housekeeping, in this order:**
   - `timeOut(s)` for each submission with no outcome where `day() >= s.day + resultDays`;
   - `mergeExpired(b)` for each `Won` bounty where `day() > mergeBy`;
   - `sunset(b)` for each `Open` bounty with no submission waiting where `day() >= idleSince + idleDays`.

   Timing out first can decide a bounty, or free it to sunset. Within each kind, the earliest due goes first.
4. **Closes** each open labelled issue linked to a bounty on this race that has ended:
   - `Paid`: the payout comment (#206's, marker `pof-paid`);
   - `Unsolved` or `Refunded`: a comment stating the outcome and the transaction of its `StateChanged`, with what it
     means (the funders' refunds open, and the reporter's stake returns when unsolved; marker `pof-ended`).

   Each comment is written once, by its marker, then the issue is closed.
5. **Links** each open labelled issue with a valid claim (D2) whose on-chain issue has a bounty, and no link marker
   yet: the bounty comment with its marker. To apply D2's first-claim rule it also reads the labelled issues, open and
   closed, numbered below the claimant.
6. **Hints** (D5) on each open labelled issue that has no link marker, no valid claim, no hint marker yet, and is at
   least `HINT_GRACE` old.

The order puts money and deadlines first: a bounty settled or sunset in this pass closes in this pass. Linking and
hints need nothing earlier in the pass.

**No local database.** The only memory is the pass's cache, rebuilt at start. Each step re-reads its own evidence
right before it writes:

| Step | Evidence it's done | A crash in the middle | On restart |
|---|---|---|---|
| link | the `pof-bounty` marker in the issue's comments | before the comment: nothing written. After it, before the response: the comment exists | the marker is there: skipped |
| hint | the `pof-hint` marker | as for link | the marker is there: skipped, for good |
| settle | the bounty's state and `settled(b, coin)` | after sending, before the receipt | if the account's pending nonce is above its latest, it waits up to 10 min and sends nothing new; then it re-reads the state. `settle` again pays nothing twice (the contract's `settled` flag) |
| `timeOut`, `mergeExpired`, `sunset` | the submission's outcome; the bounty's state | after sending, before the receipt | the same pending-nonce wait, then the views: done means not due any more. A revert because someone else did it first (`Refused`, `NotYet`, `WrongState`) counts as done, not as a failure |
| close (paid, ended) | the `pof-paid` or `pof-ended` marker, and the issue's `closed` state | after the comment, before the close | the marker is there, so only the close runs |

Comments are re-read immediately before each write, not reused from the start of the pass.

**A person reopening a closed issue** removes the `bounty` label to keep it open. The bot acts only on labelled issues,
so it won't close it again.

**One instance per race and repository.** Two would at worst both comment in the gap between the re-read and the
write. The host runs one container (D9); the suites run one process.

### D5. The comments and their markers

Every comment ends with a hidden marker that names its kind. The bot reads only markers, never prose.

| Kind | Marker | Written | Says |
|---|---|---|---|
| link | `<!-- pof-bounty race= bounty= issue= -->` (existing) | once, when the bounty opens | the bounty's number and race, and that anyone may call the contract directly |
| paid | `<!-- pof-paid race= bounty= tx= -->` (existing, #206) | once, when `Paid` | the payout transaction |
| ended | `<!-- pof-ended race= bounty= state= tx= -->` | once, when `Unsolved` or `Refunded` | the outcome and its transaction; that the funders' refunds are open (`pofctl funder claim`); for `Unsolved`, that the reporter's stake returned |
| hint | `<!-- pof-hint race= -->` | **once per issue, ever** | what a claim needs: register with `pofctl reporter register`, then add `Registration: N` and `Reporter wallet: 0x…` on their own lines. It gives the reason when there is one (no lines, a wallet that doesn't match, another issue claims it first, another repository), and says that the bot never registers for anyone |

- **The hint is never repeated:** not after an edit that's still invalid, not after a restart, and not after the
  issue is relabelled. Once the claim is valid, the link follows as usual.
- **`HINT_GRACE`** (300 s) leaves a reporter who registers right after opening the issue time to add the lines, so
  they aren't told what they're about to do.

### D6. Keys and tokens: the bot's own, read once from files

| Secret | What it may do | Source on the devnet | On infra#219's host |
|---|---|---|---|
| the bot's signing key, role **`bot-service`** | send transactions from its own address (gas only) | OpenBao `secret/proof-of-fix/devnet/bot-service` (`key`), created by `scripts/devnet-keys.sh init` | `/pof-seats/bot/key` |
| its devnet API key, handle **`pof-bot`** | reach the devnet's RPC | `keys.sh add pof-bot` (platform-197) | `/pof-seats/bot/rpc-auth` (`pof-bot:<key>`) |
| a Forgejo token for user **`pof-bounty-bot`** | issues and comments on `pof-sandbox` only | the owner creates it; stored in OpenBao by platform's script from a hidden prompt | `/pof-seats/bot/repo-token` |

- **Its own key, not `bot`:** people and the suites use the `bot` key with `pofctl`, and two senders on one key clash
  on nonces (infra#219's D12, for seat keys). `bot-service` is appended to `devnet-keys.sh`'s roles, so every
  existing role keeps its mnemonic index.
- **The forge user's reach:**
  - a team on `pof-sandbox` alone, with write on issues and nothing else, or read on code if Forgejo needs it to list
    a private repository's issues (task 1.7 checks);
  - the token scoped `write:issue`.
  - It's neither the seats' read-only `pof-validator-bot` token nor the suite's `FIRST_BOUNTY_TOKEN`.
- **How it reads them:** `POF_BOT_KEY_FILE`, `POF_BOT_RPC_AUTH_FILE` and `POF_BOT_FORGE_TOKEN_FILE` name files. Each is
  read once at start into memory. The environment holds paths, never values. There's no option that takes a secret.
  An RPC URL with user info is refused, so the credential can't end up in a URL or a log.
  - **Throwaway local devnets only:** `DEVNET_KEYS=insecure-local` derives the key from anvil's public mnemonic, as
    `pofctl` does (the local suite).
- **Refusals at start (exit 2):**
  - a chain that isn't the devnet's (7193) or anvil's (31337);
  - a key whose address is an active oracle key or the deployer's: the bot never judges;
  - a missing or empty secret file.
- **Output:** one JSON line per write and per pass, with addresses, numbers, transaction hashes and HTTP statuses.
  Error texts from the HTTP and RPC clients go through a redactor that removes every secret value read at start, as
  the AWS suite's `Secrets` does.

### D7. Polling, limits, backoff and the idle exit

| Name | Value | Rationale | Tested by |
|---|---|---|---|
| `POLL_SECONDS` | 30 (the host), 1 (the suites) | nothing the bot does is urgent; 30 s keeps the forge's calls to a few a minute | unit: the fake clock between passes |
| `MAX_WRITES_PER_PASS` | 5 | every transaction (`settle`, `timeOut`, `mergeExpired`, `sunset`) and every comment or close counts. It bounds a bug that repeats an action to 5 writes before the next re-read; the devnet rarely has more due at once | unit: 8 due actions take two passes, in D4's order |
| `MAX_WRITES_PER_RUN` | 50 | a fuse per host run (60 min at most), about ten times a busy day's actions. Reaching it exits 4, which the run's summary logs. A backlog (the first run on the shared devnet) takes several runs | unit: the 51st write exits 4 |
| `MAX_ITEM_FAILURES` | 3 | a write refused three times (a 4xx, an unexpected revert) is skipped for the rest of the run, so one bad item can't eat the budget; the next run tries again. A revert meaning "already done" isn't a failure (D4) | unit |
| backoff | `POLL_SECONDS` × 2^k, at most `BACKOFF_MAX` = 300 s | k = consecutive passes that failed to read the chain or the forge; reset by a good pass. A `Retry-After` up to 300 s is honoured | unit: the fake clock's waits |
| `AWAY_EXIT` | 1,800 s | the chain or the forge failing that long (the devnet's night stop, an outage) exits 75, as a node does, so the host's run can end | unit |
| `IDLE_SECONDS` | 600 (`--until-idle`, the nodes' value) | a run ends after that long with no write and nothing waiting. A claimed registration not yet opened counts as waiting, up to 900 s (the round timeout), and so does an unclaimed labelled issue younger than `HINT_GRACE`. A deadline in the future doesn't: the watcher starts the host again when it's due | unit; the suite's scenario |
| `HINT_GRACE` | 300 s (the host), 2 s (the suites) | D5 | unit |
| `MIN_GAS` | 0.01 devnet ETH | below it the bot sends no transaction, logs it once per run and keeps doing the forge's steps | unit |

The bot changes no incentive or parameter of the mechanism: it calls the contract's functions when the contract's
views say they're due. So the simulation doesn't model it. These are operational values, tested by the unit tests and
the suites.

**Exit codes:** 0 idle; 2 refused at start; 4 the run's write fuse; 75 the chain or the forge away too long.

### D8. The watcher starts the host for the bot's work

Added to `validator-kit/lambda/watcher.py` behind `BOT_WORK=true` (default off, so the kit's single-seat watcher is
unchanged). It reads only the chain, with the watcher's own API key, and needs no forge token.

**Work for the bot and the seats' registration check:**
1. **A registration waiting for its check:** a `Registered(N, …)` log whose issue is in one of `BOT_REPO_IDS` and is
   still `Posted` with bounty 0. It starts the host, then again every `PENDING_POLL_MINUTES` while that holds, at
   most `PENDING_MAX_STARTS` times. The chain can't show whether a forge issue claims N, so an unclaimed registration
   costs at most that many starts.
2. **A bounty just opened:** a `BountyOpened` log. One start, so the bot links it.
3. **Something due**, re-checked with the views each run, which starts the host and then again every
   `DUE_POLL_MINUTES` (30) while it's still due:
   - a `Merged` bounty with `earned(b, epoch) >= instalments`, so it can settle;
   - a submission with no outcome past `s.day + resultDays` (`timeOut`);
   - a `Won` bounty past `mergeBy` (`mergeExpired`);
   - an `Open` bounty with no submission waiting, past `idleSince + idleDays` (`sunset`).
4. **A bounty just ended:** a `StateChanged` log to `Paid`, `Unsolved` or `Refunded`. One start, so the bot settles
   what's left and closes its issue, whoever ended it.

**What it keeps track of:**
- **The candidate lists** for 3 (merged, won and open bounties, and submissions waiting) are kept in the watcher's
  state parameter, from `StateChanged`, `BountyOpened` and `Committed` logs. An entry is dropped once its state moves
  on.
  - If the lists would overflow the parameter's 4 KB, the oldest entries are kept and the result line says
    `state-full`.
  - The bot rescans the chain on every start, so a dropped entry is still handled whenever the host runs.
- **The reads:** `issue`, `bounty`, `submission`, `submissionsOf`, `earned`, `day` and `getConfig`, checked against
  keccak256 of their signatures as today.
- **Not a reason to start:** a labelled forge issue alone. The hint is posted when the host runs for any other reason.

**The kit's rules still hold:**
- the same fuse (`MAX_STARTS_PER_DAY`), shared with the seats' work;
- its state is saved only after a start was asked for;
- it fails before touching its state when the chain is down;
- a separate switch, `BOT_ENABLED`, turns the bot's work off without touching the seats'.

**Its result line** names which work started the host: `registrations`, `opened`, `settle`, `timeout`, `merge-expired`,
`sunset`, `ended`.

### D9. Requirements handed to infra#219

1. **The bot's container** on the seats' host:
   - from the same image digest as the nodes, with `pofctl/` added to `oracle/Dockerfile`;
   - running `python3 -m pofctl bot watch --until-idle 600`;
   - no Docker socket, no seat key, `restart: on-failure` (at most 3 restarts in a run), and its exit code in the
     run's summary.
2. **Its secrets** (D6):
   - `/pof-seats/bot/key`, `/pof-seats/bot/rpc-auth` and `/pof-seats/bot/repo-token`, copied from OpenBao by the
     owner's script, never by tofu;
   - decryptable only by the host's role;
   - mounted read-only into the bot's container alone, as the files `POF_BOT_*_FILE` name;
   - no node's secret in the bot's container, and no bot secret in a node's.
3. **Configuration** in `/pof-seats/config`:
   - for the bot: the repository, the forge URL, the label, `POLL_SECONDS`, `HINT_GRACE` and the limits;
   - for the nodes: `ORACLE_REGISTRATION_CHECK=on` and `ORACLE_REGISTER_WEIGHT`.
4. **The idle rule:** the host powers off when every node **and the bot** have exited, or at `max_run_minutes`.
5. **The watcher:**
   - `BOT_WORK=true`, `BOT_ENABLED`, `BOT_REPO_IDS` (the record's `repo`) and `DUE_POLL_MINUTES`;
   - no new permission (it already reads the chain and starts this instance).
6. **Logs** in a `/pof-seats/bot` log group with no secrets, and `seats.sh status` showing the bot's container and its
   last line.

### D10. Tests

- **Unit** (`tests/test_bot_service.py`, no Docker, no network):
  - a fake chain (bounties, submissions, issues, logs, `day`, `earned`, `settled`, deadlines, pending nonces, reverts)
    and a fake forge (the `RepoHost` interface, with injectable failures);
  - each step done once over many passes;
  - a crash injected after every write, then a new service on the same fakes: nothing repeated;
  - claims: wallet mismatch, wrong repository, a second claimant, an unlabelled issue;
  - housekeeping:
    - each of `timeOut`, `mergeExpired` and `sunset` sent only once due, not a day before, and once only;
    - a revert because another account did it first counts as done;
    - D4's order (a timeout that frees a sunset in the same pass);
  - closing: the paid and ended comments once each, then the close; an unlabelled reopened issue left open;
  - the hint: once after `HINT_GRACE`, never repeated after edits, restarts or relabelling, its reason, and none on a
    linked issue;
  - the limits (all writes counted), backoff, `Retry-After`, the idle and away exits, `MIN_GAS`, `--min-bounty`;
  - the refusals at start;
  - the only chain writes are `settle`, `timeOut`, `mergeExpired` and `sunset`;
  - a leak check over everything written to output, with known secret values.
- **Watcher** (`tests/test_validator_kit.py`, fakes as today): each of D8's kinds starts a stopped host, and the due
  kinds restart it every `DUE_POLL_MINUTES`; `PENDING_MAX_STARTS`; `state-full`; `BOT_ENABLED` off; the shared fuse;
  the kit's results unchanged without `BOT_WORK`.
- **Node and exchange:** the registration check with the folder transport (three keys of five, a quorum, one relay,
  the grace); the exchange's `accept` kind refusing a non-oracle key, a wrong digest and an opened issue.
- **Local suite scenario 10** (`tests/integration/suite.py`):
  - **Setup.** The suite starts `pofctl bot watch` as its own process, with the `bot-service` key, `--min-bounty` set
    to the scenario's first bounty, `HINT_GRACE` 2 s, and the nodes' check on. Its `ctl` records every call, and the
    scenario fails if the suite calls `pofctl oracle accept`, `bot link`, `bot settle` or `bot close`.
  - **10a, the paid path:**
    - the reporter registers and opens a labelled issue with both lines, and the bot links it;
    - the funder funds, the solver seals and opens the pull request, and the nodes judge;
    - the suite merges, the nodes sign the merge, and the suite warps a day at a time;
    - the bot settles, comments the payout once and closes the issue.
    - The bot is killed once right after its link and started again, and nothing is repeated.
  - **10b, the deadlines, on one bounty:**
    - a sealed fix whose pull request is never opened times out after `resultDays` (`timeOut` from `bot-service`);
    - a passing fix wins and is never merged, and expires after `mergeDays` (`mergeExpired`, back to `Open`);
    - the idle bounty sunsets after `idleDays` (`Unsolved`);
    - the bot settles it and closes its issue with one `pof-ended` comment naming the sunset's transaction.
  - **10c, the hint:** a labelled issue with no lines gets exactly one hint, which stays the only one after more
    passes, an edit and a bot restart.
  - It runs after the other scenarios, and the existing end checks (`close_watcher`, the leaderboard, the books)
    still pass with it.
- **AWS** (`tests/integration/aws.py`, `--target aws --hosted-bot`):
  - 10a, 10b and 10c against `pof-sandbox`, the hosted seats and the hosted bot;
  - it waits for each of the bot's steps up to `--bot-timeout` (default 600 s: a watcher minute, a boot, a pass), and
    warps the shared clock as scenario 1 does;
  - with `--hosted-bot`, every scenario opens its bounty through the seats and the bot, and none calls the bot's or
    the stub quorum's commands, so the hosted bot and the suite never write the same comment;
  - the hosted bot acts on the run's other bounties too: a warp can sunset scenario 2's open bounty and close its
    issue. The end checks expect that: the books count a timed-out deposit as the evaluation fee plus its return, and
    the cleanup counts issues the bot already closed.
  - The preflight checks that `bot-service`'s address has gas and isn't an oracle key.

## Risks / Trade-offs

- **[The reporter still types a step]** → it's the reporter's role by the contract (D1), and the owner accepted it.
  The hint says what to do.
- **[A stolen claim links the wrong issue]** (D2) → the money can't move: the contract pays the registering wallet.
  The real reporter re-registers. A signed claim (the wallet signing the forge issue's URL) would close it, if it
  matters beyond the devnet.
- **[The fake check opens anything claimed]** → it's the devnet's stand-in for the judges, like today's stub quorum,
  signed by the same keys; a real check is #160's.
- **[Housekeeping surprises someone]** (a winner that meant to merge tomorrow; a bounty someone meant to fund) → the
  deadlines are the contract's, published in its config; the bot only stops them from being missed. A test of a
  deadline's length belongs in the simulation, not in the bot.
- **[A crash between send and receipt]** → `settle` and the housekeeping calls are refused or idempotent on-chain
  once done (D4). Waiting on the pending nonce avoids a second transaction.
- **[Two bot instances]** → one container by design; at worst a duplicate comment, which the suites would catch.
- **[The watcher starts the host for nothing]** (unclaimed registrations, an ended bounty already closed) → bounded by
  `PENDING_MAX_STARTS`, one start per opened or ended bounty, `DUE_POLL_MINUTES`, and the shared daily fuse.
- **[A hint goes stale]** (it named a reason that the reporter then fixed differently) → it's posted once by design;
  the link comment that follows a valid claim supersedes it.
- **[The bot's token leaks]** → issues on `pof-sandbox` only; revoked alone.

## Migration Plan

1. Merge this change, then the code tasks: they change nothing on the devnet until deployed.
2. The owner runs `devnet-keys.sh init` (adds `bot-service`), funds it with devnet gas, adds the `pof-bot` API key and
   creates the forge user and its token.
3. infra#219 (or its follow-up) adds D9's container, parameters, configuration and watcher settings, with the image
   digest from a clean commit that includes this change.
4. **The first runs work through the backlog.** The shared devnet has stale open bounties and undecided submissions
   from earlier runs, now past their deadlines. The bot times out, expires and sunsets them at most 50 writes a run,
   and comments only on open labelled issues; earlier runs' issues are already closed by their cleanup.
5. `scripts/integration.sh --target aws --hosted-bot --only 10` passes.

**Rollback:** `BOT_ENABLED=false` and the bot's container removed; the nodes' check off with
`ORACLE_REGISTRATION_CHECK=off`. `pofctl oracle accept`, `bot link`, `bot settle` and `bot close` still work by hand.

## The owner's decisions (PR #211)

1. The reporter's registration is an accepted manual step (D1).
2. The bot also calls `timeOut`, `mergeExpired` and `sunset` when they're due (D1, D4, D8).
3. The bot closes issues whose bounty ends `Unsolved` or `Refunded`, with a comment stating the outcome and its
   transaction, once (D4, D5).
4. The bot posts one hint on a labelled issue with no valid claim, never repeated (D5).

## Open Questions

- **The forge user's name and the team's units** (D6), checked by task 1.7.
