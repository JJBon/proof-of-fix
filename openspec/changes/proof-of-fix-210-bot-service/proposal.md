# Proposal

Ticket: [proof-of-fix#210](https://git.example.com/example-org/proof-of-fix/issues/210). Related:
infra#219 (the on-demand seats host the bot shares), #206 (`pofctl bot settle` and `bot close`), #151 (closing paid
issues), #152 (the integration suite and its AWS target), #160 (the paid AI judge check, which waits for this).

## Why

The owner decided on 2026-11-12 that the end-to-end loop on the AWS devnet should run with nobody typing commands, before
the paid AI judge check (#160). Today these steps happen only when someone runs `pofctl` or `scripts/first_bounty.py`:
- opening a bounty for a labelled issue (the stub quorum's `pofctl oracle accept`, then `pofctl bot link`);
- settling a won bounty once its instalments are released (`pofctl bot settle`);
- closing the paid issue (`pofctl bot close`).

Nothing at all calls the contract's due housekeeping (`timeOut`, `mergeExpired`, `sunset`) or closes an issue whose
bounty ended unpaid.

## What Changes

- **Who does what, from v2's rules** (design D1):
  - **Registering is the reporter's own step.** `register` makes the caller the issue's reporter: it pays the fee and
    the stake, it's paid the finder's fee and the refund, and it's a party to every verdict. The bot never registers,
    with its own key or anyone's, and never holds a reporter's key. **The owner accepted this as a manual step** (PR
    #211): #210's "Done when" reads "with only the reporter's, funder's and solver's own steps", plus the
    maintainer's merge and, on the devnet, the clock's warps.
  - **The registration check is the judges'.** `accept` needs the oracle quorum's signatures (5 of 7 on the devnet).
    The bot never signs one and never holds a seat's key. The six role seats' nodes do the check (the fake judge on
    the devnet) and relay it, as they relay results and merges.
  - **What's left is role-free, and the bot does it:**
    - link the opened bounty to its forge issue;
    - settle a bounty whose outcome is final (`settle`, which anyone may call);
    - call the contract's due housekeeping: `timeOut` for a submission with no result after `resultDays`,
      `mergeExpired` for a won fix not merged by its deadline, and `sunset` for an idle open bounty;
    - close the issue once its bounty ends: paid with #206's payout comment, and unsolved or refunded with a comment
      stating the outcome and its transaction;
    - post one hint on a labelled issue that doesn't validly claim a registration.
  - It never funds, attempts, submits, judges, merges, challenges or claims for anyone.
- **The reporter names the registration in the issue:** a `Registration: <on-chain issue>` line beside the existing
  `Reporter wallet:` line. The seats check only a registration that a `bounty`-labelled issue claims with the matching
  wallet, so the maintainer's label still opts an issue in.
- **The seats' registration check** (new, small): each role seat's node signs `accept` for a claimed registration with
  a fixed devnet weight and a deterministic nonce, and posts its signature to the exchange under the issue. The first
  node to see a quorum relays it. The exchange takes these from any active oracle key.
- **`pofctl bot watch`:** a long-running service with its own key (a new devnet role, `bot-service`) and a scoped
  write token for `pof-sandbox`, both read once at start from files the host provides, never on a command line or in
  output.
  - Each pass reads the chain and the forge and does each role-free step that's due, once.
  - It keeps no local state, so a restart resumes from what the chain and the forge say.
  - It polls every 30 s and makes at most 5 writes a pass and 50 a run, transactions and comments alike.
  - It backs off on forge or RPC errors, and exits when idle so the on-demand host can power off.
- **On infra#219's host:** the bot runs as its own container beside the six nodes, without the Docker socket or any
  seat key, and the host's idle rule counts it. The watcher Lambda (proof-of-fix's kit watcher, which infra#219
  deploys) also starts the host for:
  - a claimed registration waiting for its check;
  - a newly opened bounty;
  - a bounty due to settle;
  - housekeeping that's come due;
  - a bounty that just ended.

  It reads only the chain (design D8). This change hands those as requirements to infra#219.
- **Tests:**
  - unit tests with a fake chain and a fake forge;
  - a new local suite scenario, 10: a labelled issue becomes a bounty, is solved, paid and closed with no `pofctl` call
    by the test for the bot's or the judges' steps;
  - scenario 10's housekeeping parts: a timed-out submission, an expired merge, a sunset and its issue closed, and the
    hint;
  - their `--target aws` versions against the hosted bot.

**Out of scope:**
- **Anything real** (rule 1): the devnet's test coin, the fake judge, `pof-sandbox`. No public chain.
- **A real registration check:** an AI writing acceptance criteria, the size floor, `refuseSimilar`, and how judges
  agree on an estimated weight. The fake check accepts every claimed registration at a fixed weight. A real one comes
  with #160, and #186 replaces per-bounty weights with cycle merit anyway.
- **`claimInstalments`** (paying an award's instalments before the bounty settles): it moves no deadline, and `settle`
  pays the same instalments.
- **GitHub repositories:** the service uses `bot/forge.py`'s `RepoHost`, so a GitHub repository works the same way,
  but the devnet serves only `pof-sandbox`; the engineers' demo (#104) isn't changed.
- **infra#219's own module:** platform builds the host, the secrets' parameters and the watcher's wiring (D9).

**Actors, incentives and attacks affected:**
- **Reporters:** unchanged incentives. They still pay and stake for their own registration and are paid its finder's
  fee, and they add one line to the issue. The hint tells them what to add. Nobody else can take a reporter's fee,
  since the contract pays the registering wallet.
- **Judges (the seats):** they now sign registration checks unattended, on the devnet with the fake judge. A judge that
  signs a check it didn't run is the same risk as today's stub quorum, which the same keys sign.
- **Solvers and funders:** the contract's deadlines now take effect on time instead of when someone remembers.
  - A submission with no result times out, returning its deposit less the evaluation fee.
  - An unmerged winner loses its win.
  - An idle bounty sunsets, so its funders' refunds open.

  These are the contract's own rules, which anyone could already call. The bot only calls them once they're due and
  never chooses whom they favour.
- **The bot:** a relayer with no stake, no seat and no payout. It can't change who is paid what. At worst it fails to
  act, and anyone can still call the same functions and close the issue. Its key can only spend devnet gas.
- **Attacks considered:**
  - a forge issue claiming someone else's registration (design D2: the wallet must match, the first claim wins, and
    the fee still goes to the registering wallet);
  - a bot that repeats an action (markers and chain state before every write, and the per-pass and per-run caps);
  - a leaked bot token (issues on `pof-sandbox` only);
  - a bot that calls housekeeping early (the contract reverts `NotYet`, and the bot reads the same views first).

## Capabilities

### New Capabilities
- `bounty-bot`: the service that does a bounty's role-free steps unattended, and the watcher that starts the
  on-demand host for them. It covers:
  - linking, settling, the due housekeeping, closing ended issues and the one hint;
  - what the bot never does;
  - its keys, idempotency and restarts;
  - polling and limits.
- `registration-check`: the judges' check that opens a bounty for a registration a labelled issue claims, signed by
  the oracle quorum and relayed by a node, with the fake judge on the devnet.

### Modified Capabilities
_None._ The main specs have no bot or node capability yet, and the contracts don't change.

## Impact

- **Code (the tasks after this spec):**
  - `bot/service.py` (new) and `bot/logic.py` (the `Registration:` line, the hint's and the ending's comments);
  - `pofctl/cli.py`: `bot watch`, and `reporter register`'s hint naming both lines;
  - `pofctl/keys.py` and `scripts/devnet-keys.sh`: the `bot-service` role, appended so other roles keep their index;
  - `oracle/node_v2.py`: the registration check;
  - `exchange/service.py` and `oracle/transport.py`: the issue board;
  - `oracle/Dockerfile`: `pofctl/` in the image, so one pinned digest runs the nodes and the bot;
  - `validator-kit/lambda/watcher.py`: the bot's work, behind its own switch;
  - `tests/`: unit tests, suite scenario 10, and its AWS version.
- **infra#219:** a bot container, three more SSM parameters under `/pof-seats/bot/`, the watcher's bot settings,
  and the idle rule counting the bot (design D9). This answers its design's open question about the bot: it shares the
  host (the owner, in #210).
- **The devnet:**
  - a `bot-service` key with devnet gas;
  - a devnet API key, `pof-bot`;
  - a Forgejo user with write on `pof-sandbox`'s issues only.

  On its first run, the hosted bot works through the shared devnet's backlog of stale bounties and submissions, at
  most 50 writes a run (Migration Plan).
- **Contracts:** none.

## Principle exceptions

None. Nothing touches a public chain or real money (rule 1), and the bot holds no one else's key.
