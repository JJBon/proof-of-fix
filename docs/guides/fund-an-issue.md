# Fund an issue

Register a Radicle issue of proof-of-fix as a bounty and pledge test coins to it. Everything here runs on the Sepolia
testnet with the project's **test coin, POFTEST, which has no value** ([intended use](../../README.md#intended-use)).

You need: git, Python 3.9 or later, [Radicle 1.10.3](https://radicle.xyz) (`rad`, `radicle-node`), Foundry's `cast`
(only to create your key), and a Sepolia JSON-RPC endpoint.

<!-- test: values -->
```bash
export POFCTL_RPC=https://<your Sepolia JSON-RPC endpoint>
export RID=<proof-of-fix's Radicle id, rad:z…, from the deployment record>
export RECORD=contracts/deployments/sepolia-v3.json   # the deployment record
```

Until the deployment record is in the repository ([L15](../../openspec/changes/proof-of-fix-251-testnet-launch/design.md)),
save it from the Radicle issue that announces the deployment and set `RECORD` to that file.

## 1. Your Radicle node and the code

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
```

## 2. Your key

```bash
mkdir -p ~/.proof-of-fix && cast wallet new ~/.proof-of-fix funder    # an encrypted keystore (it asks for a password)
printf '{"record": "%s", "keystore": "%s"}\n' "$RECORD" ~/.proof-of-fix/funder > pofctl.json
field() { python3 -c 'import json, sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"; }   # one field of --json
scripts/pofctl --json --v3 status | field solver                       # your address
```

pofctl asks for the keystore's password when it signs, and never prints the key. Send a little Sepolia ETH to your
address from any Sepolia faucet: it pays the gas.

<!-- test: gas -->
```bash
scripts/pofctl faucet                        # 20 test coins, once every 2 hours per address
```

## 3. Open and register the issue

```bash
ISSUE=$(rad issue open --title "median() of an empty list raises" \
  --description "median([]) raises IndexError; it should raise ValueError." | grep -oE '[0-9a-f]{40}')
rad sync --announce
REG=$(scripts/pofctl --json --v3 issue register --rad-issue "$ISSUE" --comment | field issue)
echo "registration $REG"
```

`issue register` pays the registration fee, stakes the issue and posts its registration check's deposit (the unused
part comes back), then comments your signed claim on the Radicle issue. Validators check that the issue is a genuine,
in-scope bug report. On Sepolia the check is final about a day later (a panel of 3's windows).

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
