# Submit a fix as a Radicle patch

Fix an open bounty's issue, seal the fix on-chain and open it as a Radicle patch; if the validators' panel passes it,
claim it and merge it. Everything here runs on the Sepolia testnet with the project's **test coin, POFTEST, which has
no value** ([intended use](../../README.md#intended-use)).

You need the tools in [Before you start](../take-part.md#before-you-start): git, Python 3.9 or later,
Radicle 1.10.3 (`rad`, `radicle-node`) and Foundry's `cast` (only to create your key) on your `PATH`, your own Sepolia
JSON-RPC endpoint, and about 0.01 Sepolia ETH.

<!-- test: values -->
```bash
export POFCTL_RPC=https://<your Sepolia JSON-RPC endpoint: Infura, Alchemy or your own>
export RID=rad:zyZXC9NqVuse8nXdpv7iYRScDHsN           # proof-of-fix on Radicle
export RECORD=contracts/deployments/sepolia-v3.json   # the deployment record, on the branch sepolia-v3 (step 1)
export BOUNTY=<the bounty's number, from its issue's comments>
```

## 1. Your Radicle node, the code and your key

```bash
rad auth --alias "$(whoami)"                 # once: your Radicle key (it asks for a passphrase)
```

<!-- test: radicle-config -->
```bash
rad node start
```

A new node doesn't know yet which seeds hold the repository, so a plain `rad clone` stops with "no candidate seeds
were found". Connect to the project's seed and clone from it:

<!-- test: skip (the devnet's node dials its peers from the config the radicle-config step wrote) -->
```bash
rad node connect z6MkveoyyXuC4S2BKidHiE1qz1RbcKLDfe4hxLTHAhaGdNem@77.113.144.207:8776   # the project's seed
```

<!-- test: radicle-peers -->
```bash
rad clone --seed z6MkveoyyXuC4S2BKidHiE1qz1RbcKLDfe4hxLTHAhaGdNem --timeout 2min "$RID" proof-of-fix && cd proof-of-fix
```

The canonical `main` moves only through the race (a fix reaches it when it's final and merged), so it's older than
the code the deployment runs and has no deployment record. Take the current code, the organiser's branch `sepolia-v3`,
to run pofctl from (your fix itself goes on `Heads.head`, step 2):

<!-- test: skip (the devnet's repository has the program and the record on its main) -->
```bash
rad remote add z6Mkjgv8wBE6A963vtYC9VCBcxBPn6TBTKxjfMqgk6VFubdq --name asclepius --fetch   # the organiser's node
git checkout -b sepolia-v3 asclepius/sepolia-v3
ls "$RECORD"                                 # the deployment record (RaceV3 0xD622…9829, block 12196904)
```

```bash
mkdir -p ~/.proof-of-fix && cast wallet new ~/.proof-of-fix solver    # an encrypted keystore: asks for a password,
                                                                       # then prints the keystore's address
printf '{"record": "%s", "keystore": "%s"}\n' "$RECORD" ~/.proof-of-fix/solver > pofctl.json
field() { python3 -c 'import json, sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"; }   # one field of --json
POFCTL="$PWD/scripts/pofctl"                 # this checkout's pofctl, with your pofctl.json, from any directory
ME=$("$POFCTL" --json --v3 status | field solver) && echo "your address $ME"   # asks for the password, once
printf '{"record": "%s", "keystore": "%s", "address": "%s"}\n' "$RECORD" ~/.proof-of-fix/solver "$ME" > pofctl.json
```

cast's keystore doesn't name its address, so the first `status` decrypts it once to find it; with the address in
`pofctl.json` (or `--address 0x…`), `status` reads only the chain and asks for no password. Every command that sends
a transaction decrypts the keystore and asks for its password at the terminal, and fails where there's none (a
script, a CI job, a shell without a TTY). For a scripted run, put the password in a file only you can read and name it
in `POFCTL_KEYSTORE_PASSWORD_FILE` (never the password itself in the environment). pofctl never prints the key.
`pofctl.json` holds two paths and your address, no secret; don't commit it.

Send about **0.01 Sepolia ETH** (plenty for every step here) to your address from any Sepolia faucet: it pays the gas.
Check it arrived, then take test coins for the fix's deposit:

<!-- test: gas -->
```bash
"$POFCTL" --v3 status | grep ETH             # "ETH  0.010000 for gas" once the faucet's ETH is in; no password
"$POFCTL" faucet                             # 20 test coins, once every 2 hours per address
"$POFCTL" --v3 status                        # your cap and room, your ETH, and the deposit a fix posts
```

**A newcomer's ceiling.** A new identity may have claims open up to 50 coins (`REP_BASE`; the cap grows with
reputation), and a fix whose claim would take you over it is refused before anything is sent. The claim is the
bounty's price: at the record's opening share (50 %) and finder's fee (17.65 %), a bounty holding more than about
117.6 coins (its funds less the registration fee) can't be claimed by a newcomer. Pledges made after you start still
raise the claim: the bounty's first attempt locks the share, not the funds. So record the attempt first, as soon as you start
work (free on Sepolia: `attemptFee` is 0), and check `pofctl status`' room before you commit:

<!-- test: skip (an optional step; the devnet's newcomer submits at once; the Radicle set runs `attempt`) -->
```bash
"$POFCTL" --v3 attempt --bounty "$BOUNTY"    # checks the bounty is open and its claim fits your room, then sends it
"$POFCTL" --v3 status | grep room            # "room for … more": the claim at commit must fit in it
```

`attempt` refuses, with nothing sent, a bounty that isn't open or whose claim at the price on offer is already over your
room (the commit would be refused). It approves the fee coin only if the deployment charges an attempt fee, and prints
the transaction and the next step.

## 2. Fix it on top of `Heads.head`

A fix must be based on the commit `Heads.head` names on-chain. Make it in its own worktree beside the checkout, so
`$POFCTL` keeps running `sepolia-v3`'s pofctl whatever that commit holds:

```bash
rad sync --fetch
"$POFCTL" --v3 verify-head                   # Radicle's canonical main is the head on-chain
git worktree add -b "fix-$BOUNTY" "../fix-$BOUNTY" "$("$POFCTL" --json --v3 status | field head)"
cd "../fix-$BOUNTY"
```

Make your change and its test, then:

<!-- test: make-fix -->
```bash
git add -A && git commit -q -m "median() of an empty list raises ValueError (bounty $BOUNTY)"
```

The repository's `.pof/check.json` names the tests the validators run, and the paths a fix can't change.

## 3. Seal it and open the patch

```bash
SUB=~/.proof-of-fix/submit-$BOUNTY.json      # keep it: its salt opens your seal
"$POFCTL" --json --v3 submit --bounty "$BOUNTY" --patch "$(git rev-parse HEAD)" > "$SUB"
sh -c "$(field patchCommand < "$SUB")"       # git push rad <commit>:refs/patches, with the claim in its description
rad sync --announce
```

`submit` seals the commit, its base and a fresh salt on-chain with the fix's deposit. A panel of validators, each
taking the patch from its own Radicle node, runs the tests twice and judges the fix. A validator's keeper draws the
panel within minutes; if no validator draws it within 10 minutes, any key with gas may:

<!-- test: skip (the devnet's keepers draw every check at once; pofctl's own tests cover `draw`) -->
```bash
"$POFCTL" --v3 draw "$(field submission < "$SUB")"
```

On v3 the verdict comes about 2–3 hours after the draw: the 2-hour seal window, then the reveal (up to an hour) and
the count. On v3.1 the reveal opens as soon as every seat has sealed, so it takes minutes.

## 4. Claim, merge, withdraw

<!-- test: wait-verdict -->
```bash
"$POFCTL" --v3 status | grep "submission $(field submission < "$SUB")"
"$POFCTL" --v3 claim --bounty "$BOUNTY" --patch "$(field fix < "$SUB")" --base "$(field base < "$SUB")" \
  --salt "$(field salt < "$SUB")"
```

The claim opens your seal; a passed fix can still be challenged until its verdict is final, about a day later on
Sepolia once 7 or more validators are active. At launch, while fewer than 7 validators are active, a panel has one
judge: its verdict waits 7 days for challenges and is held until 6–7 validators with room can judge one
(design L16), so expect days, not hours.

<!-- test: wait-final -->
```bash
"$POFCTL" --v3 merge --bounty "$BOUNTY"      # anyone may; refused, with the time left, before finality
```

<!-- test: wait-main -->
```bash
rad sync --fetch && "$POFCTL" --v3 verify-head   # canonical main is now your fix
"$POFCTL" --v3 withdraw --role solver            # your credit in the race: refunds and instalments so far
```

## 5. If your fix's base went stale: rebase in place

Two fixes judged on the same head can't both merge as they are: once the first one moves `Heads.head`, the second's
`merge` is refused as stale (its base isn't the head any more). On v3.1 the winner then rebases its fix onto the new
head in place: the award keeps its place, its epoch and its price, and nothing waits for the merge deadline. `merge`
and `status` tell you when this applies.

<!-- test: skip (the rebase in place runs in the devnet's scenario r, tests/integration/scenarios_v3.py, with these commands) -->
```bash
rad sync --fetch
git checkout "fix-$BOUNTY" && git rebase "$(scripts/pofctl --json --v3 status | field head)"   # resolve, re-run the tests
REB=~/.proof-of-fix/rebase-$BOUNTY.json
scripts/pofctl --json --v3 rebase --bounty "$BOUNTY" --patch "$(git rev-parse HEAD)" \
  --patch-id "<your fix's Radicle patch id>" > "$REB"
sh -c "$(field patchCommand < "$REB")"       # a new revision of the same patch, with the rebase check's claim lines
rad sync --announce
```

What happens next:

- **The check.** `rebase` opens the rebased commit as a new check, with the same deposit as a fix (its judges are paid
  by the meter, the rest comes back) and a claim at the bounty your fix was judged at, which replaces your original
  claim. A fresh panel runs the tests with the new head's protected paths, so the first fix's tests must pass too, and
  compares your rebase with the approved fix: anything beyond adapting the fix to the new base fails it.
- **The merge.** It has a full challenge window of its own. Once both verdicts are final, `scripts/pofctl --v3 merge
  --bounty "$BOUNTY"` moves the head to the rebased commit (the original commit never becomes the head), and your
  instalments count from the later of the two finalities. With panels of 3 at level A that's about one cycle, 27 hours
  plus the time you took to rebase, after the first fix merged.
- **If it fails** while its base is still the head, your award closes with nothing paid and the bounty reopens at
  once; you may appeal that check once in the reopened bounty. If the head moved again during the check, only that
  check ends: rebase again onto the new head.
- **If you don't.** A day after the head moved, anyone may rebase your fix. The award stays yours; a rebase by someone
  else that merges is paid 10 % of the price, from the pot's rest, and their checks back. Nobody rebasing or
  merging it within 3 days (`mergeDays`) of the latest passing verdict closes the award, and the bounty reopens.
