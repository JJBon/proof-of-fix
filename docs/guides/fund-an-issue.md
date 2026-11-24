# Fund an issue

Register a Radicle issue of proof-of-fix as a bounty and pledge test coins to it. Everything here runs on the Sepolia
testnet with the project's **test coin, POFTEST, which has no value** ([intended use](../../README.md#intended-use)).

You need the tools in [Before you start](../take-part.md#before-you-start): git, Python 3.9 or later,
Radicle 1.10.3 (`rad`, `radicle-node`) and Foundry's `cast` (only to create your key) on your `PATH`, your own Sepolia
JSON-RPC endpoint, and about 0.01 Sepolia ETH.

<!-- test: values -->
```bash
export POFCTL_RPC=https://<your Sepolia JSON-RPC endpoint: Infura, Alchemy or your own>
export RID=rad:zyZXC9NqVuse8nXdpv7iYRScDHsN           # proof-of-fix on Radicle
export RECORD=contracts/deployments/sepolia-v3.json   # the deployment record, on the branch sepolia-v3 (step 1)
```

## 1. Your Radicle node and the code

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
the code the deployment runs and has no deployment record. Take the current code, the organiser's branch `sepolia-v3`:

<!-- test: skip (the devnet's repository has the program and the record on its main) -->
```bash
rad remote add z6Mkjgv8wBE6A963vtYC9VCBcxBPn6TBTKxjfMqgk6VFubdq --name asclepius --fetch   # the organiser's node
git checkout -b sepolia-v3 asclepius/sepolia-v3
ls "$RECORD"                                 # the deployment record (RaceV3 0xD622…9829, block 12196904)
```

## 2. Your key

```bash
mkdir -p ~/.proof-of-fix && cast wallet new ~/.proof-of-fix funder    # an encrypted keystore: asks for a password,
                                                                       # then prints the keystore's address
printf '{"record": "%s", "keystore": "%s"}\n' "$RECORD" ~/.proof-of-fix/funder > pofctl.json
field() { python3 -c 'import json, sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"; }   # one field of --json
ME=$(scripts/pofctl --json --v3 status | field solver) && echo "your address $ME"   # asks for the password
```

pofctl decrypts the keystore for every command, `status` included, so each asks for its password at the terminal,
and fails where there's none (a script, a CI job, a shell without a TTY). For a scripted run, put the password in a
file only you can read and name it in `POFCTL_KEYSTORE_PASSWORD_FILE` (never the password itself in the
environment). pofctl never prints the key. `pofctl.json` holds two paths, no secret; don't commit it.

Send about **0.01 Sepolia ETH** (plenty for every step here) to your address from any Sepolia faucet: it pays the gas.
Check it arrived, then take test coins:

<!-- test: gas -->
```bash
cast balance "$ME" --rpc-url "$POFCTL_RPC" --ether   # 0.010000000000000000 once the faucet's ETH is in
scripts/pofctl faucet                        # 20 test coins, once every 2 hours per address
```

Registering takes about 14 POFTEST: the registration fee (2), the issue's stake (5) and its check's deposit (about 7;
the unused part comes back). One faucet claim of 20 covers it and leaves enough for the pledge in step 4.

## 3. Open and register the issue

```bash
ISSUE=$(rad issue open --title "median() of an empty list raises" \
  --description "median([]) raises IndexError; it should raise ValueError." \
  | awk '!id && $1 == "│" && $2 == "Issue" {id = $3} END {print id}')
echo "issue $ISSUE"
rad sync --announce
REG=$(scripts/pofctl --json --v3 issue register --rad-issue "$ISSUE" --comment | field issue)
echo "registration $REG"
```

`rad issue open` (Radicle 1.10.3) prints the new issue in a box, and its row `│ Issue   <40 hex digits> │` holds
the id: the `awk` takes that row only, not any other 40-hex string the box may show. If `ISSUE` comes out empty,
find your issue's short id with `rad issue list`; `rad issue show <short id>` prints the full id in the same row.

`issue register` pays the registration fee, stakes the issue and posts its registration check's deposit (the unused
part comes back), then comments your signed claim on the Radicle issue. Validators check that the issue is a genuine,
in-scope bug report. On Sepolia the check is final about a day later (a panel of 3's windows) once 7 or more
validators are active. At launch, while fewer than 7 validators are active, a panel has one judge: its verdict waits
7 days for challenges and is held until enough validators are active to judge one (design L16), so expect days, not
hours.

<!-- test: wait-registration -->
```bash
BOUNTY=$(scripts/pofctl --json --v3 issue open --issue "$REG" | field bounty)   # refused until the check is final
echo "bounty $BOUNTY"
```

## 4. Pledge

```bash
scripts/pofctl --v3 status | grep 'active solvers'
scripts/pofctl --v3 pledge --bounty "$BOUNTY" --amount 5
```

Pledges are refused, with nothing sent, while fewer than 3 solvers are active (a solver is active for 26 weeks after
one of its fixes is merged); unfunded bounties are still raced. The first fix that passes and is merged wins the
bounty's price. pofctl approves the race to spend your test coins (unlimited) the first time, and says so.
