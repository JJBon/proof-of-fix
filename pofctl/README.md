# pofctl: play every role of proof-of-fix (#104)

`pofctl` drives the race on a devnet as each role would: the **funder**, the **reporter**, the **solver**, the
**validator**, and the **bot**. Validators run their own nodes (`python3 -m oracle run`, the validator kit) and join
as v2 seats with their own keys; on a devnet the **stub quorum** can also sign, with the devnet's seat keys: the
registration check, and a submission's verdict signed by whichever of them are drawn.

- **Standard library only:** it talks JSON-RPC to the chain and signs transactions itself, with the oracle node's
  vendored, pinned secp256k1 and keccak (`oracle/vendor`). No cast, forge or Docker is needed to use it.
- **v2 by default** (`RaceV2`, coin only), and v1 with `--v1`.
- **Money is the devnet's test coin.** POF is parked and appears nowhere.

## Setup

Run it from a checkout of this repository: `scripts/pofctl ...` (or `python3 -m pofctl ...`).

| What | Default | Override |
|---|---|---|
| The chain's RPC | `http://127.0.0.1:8546` (`scripts/devnet.sh up`) | `--rpc`, `POFCTL_RPC`, or `rpc` in the config |
| The API key of a remote chain (#104's chain on AWS) | none | the URL's user info, `https://<handle>:<key>@…` (sent as HTTP Basic, as `keys.sh show` prints it), or `POFCTL_RPC_TOKEN` sent as `POFCTL_RPC_AUTH` says: `Authorization` (Bearer, the default), `Basic` (a `<handle>:<key>` token) or another header's name. Never put it in the config |
| The deployment | `contracts/deployments/devnet-v2.json` (`scripts/devnet.sh deploy-v2`) | `--record`, or `record` in the config; `--v1` reads `devnet.json` |
| Keys | **OpenBao**, `secret/proof-of-fix/devnet/<role>`: sign in with `bao login -method=oidc role=admin -no-print` | `DEVNET_KEYS=insecure-local` (anvil's public mnemonic: throwaway devnets only), or `env` with `POFCTL_KEY_<ROLE>`. Whatever the source, `POFCTL_KEY_<ROLE>` set for a role wins: an engineer's own key is `POFCTL_KEY_ENGINEER` with `--as engineer` |
| Which key plays a role | funder→`funder`, reporter→`reporter`, solver→`solver-a`, validator→`oracle-0`, bot and the stub quorum's relayer→`bot` | `--as ROLE` for one command (e.g. `--as solver-b`), or `profiles` in the config |
| Repositories | GitHub (`api.github.com`), with `GITHUB_TOKEN` (a fine-grained token) or `GITHUB_APP_TOKEN` | `repos` in the config, per repository: `{"host": "github" or "forgejo", "api": "..."}` |

A config file is optional: `--config`, `$POFCTL_CONFIG`, or `./pofctl.json`:
```json
{"rpc": "http://127.0.0.1:8546", "keys": "openbao",
 "profiles": {"solver": "solver-b"},
 "repos": {"acme/demo": {"host": "github"}}}
```

Every command takes `--json` for machine-readable output.

## Walkthrough: one bounty, every role

The demo repository is `acme/demo` on GitHub here; use your own. The devnet is up, and v2 is deployed.

```bash
scripts/pofctl status                                   # chain, contract day, oracle quorum, key source
scripts/pofctl coin mint --to funder --amount 1000      # the devnet's test coin, for each player
scripts/pofctl coin mint --to reporter && scripts/pofctl coin mint --to solver-a && scripts/pofctl coin mint --to solver-b
```

**1. Reporter:** opens an issue on GitHub with the `bounty` label and a line `Reporter wallet: 0x…`, then registers it
on-chain. That pays the registration fee and stakes the issue stake.
```bash
scripts/pofctl reporter register                        # -> on-chain issue 1
```

**2. The registration check** opens the bounty (the stub quorum here; real validators later), and **the bot** links it
on the GitHub issue:
```bash
scripts/pofctl oracle accept --issue 1                  # -> bounty 1
scripts/pofctl bot link --repo acme/demo --issue 7 --bounty 1
```

**3. Funder:** pledges. The price is a share of what's pledged, and it **rises daily until the first attempt locks it**.
```bash
scripts/pofctl funder fund --bounty 1 --amount 100
scripts/pofctl devnet warp --days 2                     # the devnet's clock; the share rises 10 points a day
```

**4. Solver:** reads the quote (the **rates**), attempts, and seals a fix.
```bash
scripts/pofctl solver quote --bounty 1                  # price, instalments, finder's fee, attempt fee; the check
                                                        # deposit (the meter's maximum), the service fee, the CI profile
scripts/pofctl solver attempt --bounty 1                # locks the share (70 % after 2 days)
scripts/pofctl solver submit --bounty 1 --commit <the fix's commit sha> --issue 7
```
`submit` posts the check deposit (the meter's worst case for 3 judges at the caps), prints the 3 judges drawn for the
submission, and prints the pull request's body: the bounty, the submission, the salt and the solver's wallet. Open
the pull request with it. The salt is what lets the judges open the seal.

**5. The checks.** The 3 validators drawn for the submission check it: their nodes (`python3 -m oracle run`) find the
pull request, open the seal against its head commit, run the tests in the sandbox, judge it, **report their measured
usage to the meter**, and sign the verdict v2; one relays it. The meter charges each counted judge its usage (tokens,
sandbox vCPU-seconds and GB-seconds, storage) plus the **$0.05 service fee**, repays the relayer's gas, and returns the
rest of the deposit to the solver. On a devnet without nodes, the stub quorum does the same with the devnet's seat keys
(stub usage), and refuses a pull request that doesn't open the seal:
```bash
scripts/pofctl oracle result --submission 1 --outcome pass --repo acme/demo --pr 8
#   the drawn judges ... reported their usage and signed submission 1: Pass
#   the meter charged 0.31... of the 1.08... deposit (usage plus the service fee per judge, and the relay's gas)
```

**6. Merge:** solved = merged. Merge the pull request on GitHub; the same drawn judges sign the merge (their nodes see
it merged, or the stub quorum: it's refused until GitHub says the pull request is merged). The winner's check fees
come back from the pot at settlement.
```bash
scripts/pofctl oracle merged --bounty 1 --repo acme/demo --pr 8
```

**7. The bot** settles once the instalments are released (after the challenge window and the releases), the funder
claims the leftover, and everyone withdraws their credit.
```bash
scripts/pofctl devnet warp --days 7 && scripts/pofctl bot settle --bounty 1   # repeat until it says Paid
scripts/pofctl funder claim --bounty 1
scripts/pofctl withdraw --role solver-a && scripts/pofctl withdraw --role reporter
```

**8. Look around:**
```bash
scripts/pofctl balances                                 # wallets and credit: roles, infrastructure, every oracle
scripts/pofctl --as oracle-0 validator status           # seat, draws, verdicts, usage reports, fees earned
scripts/pofctl history                                  # every event, decoded
```

**A failed fix:** `oracle result --outcome fail`. The bounty stays open, the solver gets its deposit back less the
checks' fees, and the idle clock restarts.

## A validator joins: an engineer's own key takes a vacant seat

The engineer holds their key (never the owner); the owner's devnet seat keys co-sign. The contract checks both.
```bash
export POFCTL_KEY_ENGINEER=…                            # the engineer's own key (from their secret store, not a file)
scripts/pofctl --as engineer validator join --seat 6    # the digest from Verdicts, signed with that key: a request
# the owner, on the devnet, co-signs it with the quorum of the other seats' keys and sends it:
scripts/pofctl validator publish --seat 6 --key 0x… --nonce 0x… --sig 0x…
#   (the same with forge: scripts/devnet.sh join-v2 6 --key 0x… --sig 0x… --nonce 0x…)
scripts/pofctl devnet warp --days 7                     # KEY_ROTATION_DELAY: anyone activates it after 7 days
scripts/pofctl validator activate --seat 6
scripts/pofctl --as engineer validator status           # seat 6, active; draws, verdicts, usage reports, fees earned
scripts/pofctl --as engineer validator withdraw         # pull the check fees to the wallet
```
The engineer's node runs with the same key (`ORACLE_KEYS=env`, `ORACLE_PRIVATE_KEY`): see `validator-kit/runbook.md`.
It acts only for the submissions its seat is drawn for, and earns its fee for each check the meter counts;
`python3 -m oracle withdraw-fees` pulls them too.

## Run the whole story automatically

```bash
scripts/demo-e2e.sh      # the engineers' demo: a join, real nodes, metered fees, withdrawals
scripts/pofctl-e2e.sh    # every role through pofctl alone, the stub quorum signing
```
Both start a throwaway devnet beside any other (their own name, port, state and records; `demo-e2e` on 8553,
`pofctl-e2e` on 8549, never the owner's 8546), deploy v2 with anvil's public keys, play against a fake GitHub on the
loopback, check the balances exactly, and remove the devnet.

`demo-e2e.sh` deploys 7 seats with 2 vacant: the owner fills seat 5 (`devnet.sh join-v2 5 joiner-0`), and a new
engineer's own key joins seat 6 through pofctl (join, publish, 7 days, activate). Then bounties, each with two bad
fixes and a good one: seven real node processes (`python3 -m oracle run --until-idle`, the fake judge, the tests in
the Docker sandbox) judge them, and only the 3 drawn for each submission act: they report their usage, seal, reveal,
sign, and one relays. The pull request merges on the fake GitHub; the judges sign the merge; the bounty settles.
Bounties repeat until the engineer's seat has been drawn. Every validator then withdraws its fees with the node's
`withdraw-fees`. Checked exactly: each result's deposit = charged + refunded (read at the result's block); what the
meter charged = what the judges and the relayer were credited; each withdrawal = the credit; everything charged was
withdrawn; 3 usage reports per check.

## What's not here yet

| Comes with | What changes in pofctl |
|---|---|
| #85 task 5.8: seat bonds | `validator status` shows the bond; `validator join` posts it |
| #94: receipts published, and the aggregator service | `history` links the receipts; nodes on separate machines exchange seals through it (the demo's nodes share a directory) |

**Safety:**
- The stub quorum and `devnet warp` refuse any chain but the devnet's (7193) and anvil's (31337).
- Keys are devnet keys: never use one on a public chain (rule 1).
- pofctl never prints a key.
