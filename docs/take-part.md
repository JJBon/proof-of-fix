# Take part in proof-of-fix on Sepolia

proof-of-fix pays for fixes that validators check and the chain counts. It runs on the **Sepolia testnet with a
test coin, POFTEST, that has no value** ([intended use](../README.md#intended-use)). Your gas is Sepolia ETH from
a faucet; if you run a validator, your AWS and model costs are real.

## What's live

| | |
|---|---|
| **Repository** | `rad:z2whCPbrSKbtyvwYjHXPZhN9ZkK5z` on Radicle (name `asclepius`); the project's seed `z6MkveoyyXuC4S2BKidHiE1qz1RbcKLDfe4hxLTHAhaGdNem@77.113.144.207:8776`, and public seeds replicate it |
| **Contracts** | v3.1 on Sepolia (chain 11155111), first block 12211341: RaceV3 `0xC02F191a82f9459FB4C003B68245c872a256a790`, registry `0xbF7138DAA5DC0b0796e56C79DA2Ed0F480b06B94`, the record [`contracts/deployments/sepolia-v3.1.json`](../contracts/deployments/sepolia-v3.1.json) |
| **Validators** | one so far, the genesis validator (AMD SEV-SNP, Claude): 7 to 15 are planned |
| **Model family seated** | `anthropic/claude` (the `provider/line` form every receipt uses) |
| **Validator disk** | image digest `0xd0960af213994a2370424e77475f41f3654cab29dc76131e0efd6153e3e7c50a` (root hash `ddfdf368532d37484c7f92e1c577d520cd678ca30da105ef77e331dfe1ed26f5`), the one image v3.1's plan lists |

**Earlier deployments (history only).** v3 (RaceV3 `0xD622adB4CbC82fF51d5D2ddbD56681b5f2d89829`, block 12196904,
[`sepolia-v3.json`](../contracts/deployments/sepolia-v3.json)) is superseded by v3.1. Its repository,
`rad:zyZXC9NqVuse8nXdpv7iYRScDHsN`, is frozen at `81505595`: its only delegate's key was lost when the genesis
validator's SEV-SNP host was replaced, so its `main` can't move again. v3 seated the family under the dotted name
`anthropic.claude`, and its nodes posted only families already priced (`ORACLE_LIST_PRICES = "{}"`, since v3 can't
seat a new one). Don't start anything new on v3; the project's seed host still runs its keeper, so what was already
there settles.

## Pick a role

| You want to… | Guide | You need |
|---|---|---|
| Put a bug up for fixing, and back it with test coins | [Fund an issue](guides/fund-an-issue.md) | git, Python 3.9+, Radicle 1.10.3, Foundry's `cast`, a Sepolia RPC endpoint, 0.01 Sepolia ETH |
| Fix a bug and get paid for it | [Submit a fix](guides/submit-a-fix.md) | the same |
| Check other people's fixes and get paid per check | [Run a validator](guides/run-a-validator.md) | an AWS account (SEV-SNP instances), a Claude model on Bedrock or an Anthropic API key, OpenTofu, Docker |

Each guide starts from a clean Linux machine (x86-64) once you've done [Before you start](#before-you-start).

## Before you start

**Tools.** git, Python 3.9 or later, curl and xz (on Debian or Ubuntu:
`sudo apt-get install -y git python3 curl xz-utils ca-certificates`), then Radicle 1.10.3, checked against its
SHA-256:

```bash
TAR=radicle-1.10.3-x86_64-unknown-linux-musl.tar.xz
curl -fsSLO "https://files.radicle.dev/releases/1.10.3/$TAR"
echo "3d78e3ffc17f9e6eca7fcd3acc439f2252060532eb457cf17f2747fed4cc6751  $TAR" | sha256sum --check   # "…: OK"
mkdir -p ~/.radicle && tar -xJf "$TAR" -C ~/.radicle --strip-components=1
export PATH="$HOME/.radicle/bin:$PATH"       # rad, radicle-node and git-remote-rad
rad --version                                # rad 1.10.3 (7e1cb40…)
```

and Foundry's `cast` (the funder and the solver need it to create their key):

```bash
curl -L https://foundry.paradigm.xyz | bash  # installs foundryup into ~/.foundry/bin
export PATH="$HOME/.foundry/bin:$PATH"
foundryup --install v1.8.5
cast --version
```

Both `~/.radicle/bin` and `~/.foundry/bin` must be on your `PATH` in every shell you follow a guide in: add the two
`export PATH=…` lines to your `~/.bashrc` (foundryup adds its own; check it's there).

**A Sepolia JSON-RPC endpoint.** Any works (Infura, Alchemy or your own node). Use **your own key** or provider:
Infura's free plan answers some calls with HTTP 429 at times (pofctl and the node retry them), and several people or
validators on one key soon hit its daily quota. Never paste an RPC URL with a key in it into an issue.

**Sepolia ETH for gas.** About 0.01 Sepolia ETH, from any Sepolia faucet, is plenty for every step of the funder's or
the solver's guide. Each guide shows how to check it arrived.

**Which code.** The repository's canonical `main` on Radicle starts at the public snapshot of the commit v3.1 was
deployed from (`bc68e00…`) and moves only through the race (below), so it has neither the deployment record nor these
guides. Each guide checks out the organiser's branch `sepolia-v3.1` after cloning: it holds the current code and the
record (`contracts/deployments/sepolia-v3.1.json`), the same tree as the GitHub mirror's branch `snapshot`
([github.com/JJBon/proof-of-fix](https://github.com/JJBon/proof-of-fix/tree/snapshot)).

## What to expect at launch

- **Fixes merge slowly until there are 7 validators.** With fewer, a panel has one judge, a passed fix waits 7 days
  for challenges, and its verdict is held until enough validators are active to judge one. Every validator who joins
  shortens that; with 7 or more a fix is final in about a day.
- **How long a verdict takes.** Minutes, once every seat has sealed: on v3.1 the reveal opens as soon as every seat
  has sealed. A seat that doesn't seal makes it at most about 2–3 hours from the draw: the 2-hour seal window, then the
  reveal (up to an hour) and the count. Then a lone verdict (one judge) is held until 6–7 validators with room can
  judge a challenge (below).
- **What a held verdict needs.** Six eligible validators outside its panel before its audits are drawn (seven in
  all, with the judge), then three outside the judge and its auditors after (six in all, with two auditors). Each must
  be bonded for the bounty, not a party, and have room under its k = 1 limit now. Below that every lone verdict stays
  held; at exactly the threshold, one validator pausing or filling up holds them all.
- **A newcomer's ceiling.** A new solver may have claims open up to 50 coins (`REP_BASE`; it grows with reputation).
  At the record's opening share (50 %) and finder's fee (17.65 %), a bounty holding more than about 117.6 coins (its
  funds less the registration fee) can't be claimed by a newcomer. Pledges made after you start still raise the claim:
  the bounty's first attempt locks the share, not the funds. So record the attempt first, and check
  `pofctl status`' room before you commit.
- **The repository's `main` moves only through the race.** Its Radicle delegates are the validators seated on-chain,
  so a fix reaches `main` when it is final and merged, not when someone with commit rights pushes it.
- **Pledges wait for 3 active solvers.** Until 3 solvers have had a fix merged, bounties are raced unfunded.
- **Anyone can keep.** The race moves forward only when someone sends its keeper calls (drawing panels, starting
  windows, counting, paying). Validators' nodes do it, and so can anyone with a plain key that pays gas only, no bond
  and no registration: `python3 -m oracle.keeper run` (and `python3 -m oracle.keeper info` to check the key, its ETH
  and the deployment), from a checkout of the current code. The project's seed host runs one;
  [the kit's runbook](../validator-kit/runbook.md#run-a-keeper) has its settings and cost. A check nobody drew is
  also drawn by a validator's watcher (its draw duty), or by you: `pofctl --v3 draw <check>`.
- **The bond for a validator (250 POFTEST)** comes from the organiser, because the faucet's 20 coins every 2 hours
  would take days: ask on a Radicle issue, as
  [Run a validator](guides/run-a-validator.md#33-the-signing-key-gas-and-the-bond) shows.

## Questions and problems

Open a Radicle issue on the repository (`rad issue open`, then `rad sync --announce`). Say which guide and step,
and paste the command and its output (never a key, a keystore password or an RPC URL with a key in it).
