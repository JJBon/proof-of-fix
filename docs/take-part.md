# Take part in proof-of-fix on Sepolia

proof-of-fix pays for fixes that validators check and the chain counts. It runs on the **Sepolia testnet with a
test coin, POFTEST, that has no value** ([intended use](../README.md#intended-use)). Your gas is Sepolia ETH from
a faucet; if you run a validator, your AWS and model costs are real.

## What's live

| | |
|---|---|
| **Repository** | `rad:zyZXC9NqVuse8nXdpv7iYRScDHsN` on Radicle (name `asclepius`); the project's seed `z6MkveoyyXuC4S2BKidHiE1qz1RbcKLDfe4hxLTHAhaGdNem@77.113.144.207:8776`, and public seeds replicate it |
| **Contracts** | Sepolia (chain 11155111), first block 12196904: RaceV3 `0xD622adB4CbC82fF51d5D2ddbD56681b5f2d89829`, the record [`contracts/deployments/sepolia-v3.json`](../contracts/deployments/sepolia-v3.json) |
| **Validators** | one so far, the genesis validator (AMD SEV-SNP, Claude): 7 to 15 are planned |
| **Model family seated** | `anthropic.claude` |

## Pick a role

| You want to… | Guide | You need |
|---|---|---|
| Put a bug up for fixing, and back it with test coins | [Fund an issue](guides/fund-an-issue.md) | git, Python 3.9+, Radicle 1.10.3, Foundry's `cast`, a Sepolia RPC endpoint |
| Fix a bug and get paid for it | [Submit a fix](guides/submit-a-fix.md) | the same |
| Check other people's fixes and get paid per check | [Run a validator](guides/run-a-validator.md) | an AWS account (SEV-SNP instances), Bedrock access to a Claude model, OpenTofu, Docker |

Any Sepolia JSON-RPC endpoint works (Infura, Alchemy or your own). Each guide starts from a clean machine.

## What to expect at launch

- **Fixes merge slowly until there are 7 validators.** With fewer, a panel has one judge, a passed fix waits 7 days
  for challenges, and its verdict is held until enough validators are active to judge one. Every validator who joins
  shortens that; with 7 or more a fix is final in about a day.
- **The repository's `main` moves only through the race.** Its Radicle delegates are the validators seated on-chain,
  so a fix reaches `main` when it is final and merged, not when someone with commit rights pushes it.
- **Pledges wait for 3 active solvers.** Until 3 solvers have had a fix merged, bounties are raced unfunded.
- **The bond for a validator (250 POFTEST)** comes from the organiser, because the faucet's 20 coins every 2 hours
  would take days: ask on a Radicle issue, as [Run a validator](guides/run-a-validator.md#33-the-signing-key-gas-and-the-bond)
  shows.

## Questions and problems

Open a Radicle issue on the repository (`rad issue open`, then `rad sync --announce`). Say which guide and step,
and paste the command and its output (never a key, a keystore password or an RPC URL with a key in it).
