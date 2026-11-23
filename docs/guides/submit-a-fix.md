# Submit a fix as a Radicle patch

Fix an open bounty's issue, seal the fix on-chain and open it as a Radicle patch; if the validators' panel passes it,
claim it and merge it. Everything here runs on the Sepolia testnet with the project's **test coin, POFTEST, which has
no value** ([intended use](../../README.md#intended-use)).

You need: git, Python 3.9 or later, [Radicle 1.10.3](https://radicle.xyz) (`rad`, `radicle-node`), Foundry's `cast`
(only to create your key), and a Sepolia JSON-RPC endpoint.

<!-- test: values -->
```bash
export POFCTL_RPC=https://<your Sepolia JSON-RPC endpoint: Infura, Alchemy or your own>
export RID=rad:zyZXC9NqVuse8nXdpv7iYRScDHsN           # proof-of-fix on Radicle
export RECORD=contracts/deployments/sepolia-v3.json   # the deployment record (RaceV3 0xD622…9829, block 12196904)
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

<!-- test: radicle-peers -->
```bash
rad clone "$RID" proof-of-fix && cd proof-of-fix
mkdir -p ~/.proof-of-fix && cast wallet new ~/.proof-of-fix solver    # an encrypted keystore (it asks for a password)
printf '{"record": "%s", "keystore": "%s"}\n' "$RECORD" ~/.proof-of-fix/solver > pofctl.json
field() { python3 -c 'import json, sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"; }   # one field of --json
scripts/pofctl --json --v3 status | field solver                       # your address
```

Send a little Sepolia ETH to your address from any Sepolia faucet (gas), then take test coins for the fix's deposit.

<!-- test: gas -->
```bash
scripts/pofctl faucet                        # 20 test coins, once every 2 hours per address
scripts/pofctl --v3 status                   # your cap, and the deposit a fix posts (the rest comes back)
```

A new identity may have claims open up to $50 (the cap grows with reputation); a fix whose bounty would take you over
it is refused before anything is sent.

## 2. Fix it on top of `Heads.head`

```bash
rad sync --fetch
scripts/pofctl --v3 verify-head              # Radicle's canonical main is the head on-chain
git checkout -b "fix-$BOUNTY" "$(scripts/pofctl --json --v3 status | field head)"
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
scripts/pofctl --json --v3 submit --bounty "$BOUNTY" --patch "$(git rev-parse HEAD)" > "$SUB"
sh -c "$(field patchCommand < "$SUB")"       # git push rad <commit>:refs/patches, with the claim in its description
rad sync --announce
```

`submit` seals the commit, its base and a fresh salt on-chain with the fix's deposit. A panel of validators, each
taking the patch from its own Radicle node, runs the tests twice and judges the fix.

## 4. Claim, merge, withdraw

<!-- test: wait-verdict -->
```bash
scripts/pofctl --v3 status | grep "submission $(field submission < "$SUB")"
scripts/pofctl --v3 claim --bounty "$BOUNTY" --patch "$(field fix < "$SUB")" --base "$(field base < "$SUB")" \
  --salt "$(field salt < "$SUB")"
```

The claim opens your seal; a passed fix can still be challenged until its verdict is final, about a day later on
Sepolia once 7 or more validators are active. At launch, while fewer than 7 validators are active, a panel has one judge: its verdict waits 7 days for
challenges and is held until enough validators are active to judge one (design L16), so expect days, not hours.

<!-- test: wait-final -->
```bash
scripts/pofctl --v3 merge --bounty "$BOUNTY"     # anyone may; refused, with the time left, before finality
```

<!-- test: wait-main -->
```bash
rad sync --fetch && scripts/pofctl --v3 verify-head   # canonical main is now your fix
scripts/pofctl --v3 withdraw --role solver            # your credit in the race: refunds and instalments so far
```
