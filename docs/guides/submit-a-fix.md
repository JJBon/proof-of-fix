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
ME=$("$POFCTL" --json --v3 status | field solver) && echo "your address $ME"   # asks for the password
```

pofctl decrypts the keystore for every command, `status` included, so each asks for its password at the terminal,
and fails where there's none (a script, a CI job, a shell without a TTY). For a scripted run, put the password in a
file only you can read and name it in `POFCTL_KEYSTORE_PASSWORD_FILE` (never the password itself in the
environment). pofctl never prints the key. `pofctl.json` holds two paths, no secret; don't commit it.

Send about **0.01 Sepolia ETH** (plenty for every step here) to your address from any Sepolia faucet: it pays the gas.
Check it arrived, then take test coins for the fix's deposit:

<!-- test: gas -->
```bash
cast balance "$ME" --rpc-url "$POFCTL_RPC" --ether   # 0.010000000000000000 once the faucet's ETH is in
"$POFCTL" faucet                             # 20 test coins, once every 2 hours per address
"$POFCTL" --v3 status                        # your cap, and the deposit a fix posts (the rest comes back)
```

A new identity may have claims open up to $50 (the cap grows with reputation); a fix whose bounty would take you over
it is refused before anything is sent.

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
taking the patch from its own Radicle node, runs the tests twice and judges the fix.

## 4. Claim, merge, withdraw

<!-- test: wait-verdict -->
```bash
"$POFCTL" --v3 status | grep "submission $(field submission < "$SUB")"
"$POFCTL" --v3 claim --bounty "$BOUNTY" --patch "$(field fix < "$SUB")" --base "$(field base < "$SUB")" \
  --salt "$(field salt < "$SUB")"
```

The claim opens your seal; a passed fix can still be challenged until its verdict is final, about a day later on
Sepolia once 7 or more validators are active. At launch, while fewer than 7 validators are active, a panel has one
judge: its verdict waits 7 days for challenges and is held until enough validators are active to judge one
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
