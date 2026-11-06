# The exchange: how the drawn judges talk (proof-of-fix#117)

For each check, the 3 judges drawn of the 7 seats **seal** their verdicts (a hash), then **reveal** them, then **sign**
the verdict the quorum reached; one of them relays it to `RaceV2.result` (and later `RaceV2.merged`). Their usage
reports go to the meter on-chain (`Fees.report`) and don't pass through here.

**The hosted exchange service is a convenience relay, never a required dependency** (ADR 0003, #121). The target
primary path is **seals, reveals and signatures on-chain** (#122, task 5.5): the contract is the one place every judge
can reach, and no check may depend on a service one party runs. Until #122 lands, the service lets judges on separate
machines meet without a shared folder, and a node always has another way through (below).

## Transports, none of them required

The node's transport is a pluggable interface (`oracle/transport.py`, `ORACLE_EXCHANGE_TRANSPORT`):

| transport | what | status |
|-----------|------|--------|
| `folder`  | a directory the nodes share (`ORACLE_EXCHANGE`) | one machine: the unit tests and the folder demo |
| `http`    | the hosted exchange service (`exchange/`, `ORACLE_EXCHANGE_URL`) | built here: a **convenience relay** |
| `onchain` | seals, reveals and signatures posted to the contracts | interface + TODO: **#122 (task 5.5), the target primary path** |
| `p2p`     | gossip between the judges (libp2p, Waku…) | interface only |

Several at once (`http,onchain` once 5.5 lands; `http,folder` on one machine) fan out: a node posts to each and reads
the union, so no single transport, the hosted service included, is required. The **hosted service is a convenience
relay, never a dependency**: the nodes relay the result themselves, building the verdict from the chain's own data
(the domain, the submission, its seed and the draw) and the signatures they read, and they see on-chain when someone
else relayed. Until 5.5 lets the contracts take the seals themselves, a check with the service down for its whole
length needs a second transport; with `http` alone, a check the service drops out of finishes when it's back (the
nodes post their messages again, even to a service that restarted empty).

Tested paths with the service down: `tests/test_exchange.py` (`http,folder,p2p` with the service never reachable: the
check completes and a node relays it; the service down mid-round and back empty; one judge that can't reach it), and
`scripts/demo-e2e.sh --exchange http-down` (the seven nodes on `http,folder` with nothing listening at the URL).

## Trust model

Nothing is trusted to the service; it can **withhold** a message, never **forge** one:

- every message is signed by its judge's seat key; the service takes it only when the signature recovers to the node
  that posts it and that node is **drawn and not recused** for the submission (`Verdicts.drawn`, read from the chain);
- a reveal is taken only when it **opens that node's seal**; seals and reveals are final once posted (409 otherwise);
- a result or merge signature is taken only over **RaceV2's own EIP-712 digest** for that submission (the service
  checks the contract's domain is v2's before it starts);
- the nodes check everything again when they read (`oracle/node_v2.py`), and the contract checks the signatures, the
  signers' seats and the quorum when the result is relayed;
- the service holds no key and sends no transaction. (The issue allows the service to relay at quorum; it doesn't,
  so it needs no funded key; the nodes' lowest-addressed agreeing judge relays, as with the folder.)

**Deadlines**, per submission, from its first seal: seals until every drawn judge sealed or the seal window closes
(default 60 s, the nodes' `ORACLE_ROUND_TIMEOUT`); reveals only after that (an early one gets **425 Too Early** and the
node sends it again) and until the reveal window closes (default 600 s). The contracts' `SEAL_WINDOW`/`REVEAL_WINDOW`
are still `TODO(5.5)` in `Verdicts.sol`, so the windows are the service's configuration until then.

**Access**: on the devnet host, behind Caddy, under the same per-engineer API keys as the RPC (HTTP Basic). The node
sends the key from the exchange URL's user info, `ORACLE_EXCHANGE_TOKEN`, or the RPC's own key when the exchange is on
the RPC's host (never to another host). Anyone with a key can read; only drawn judges' signed messages are written.

**Limits**: a body up to 64 KiB (413 above); one message per drawn judge and kind; a submission's messages expire a
retention period after its last one (`EXCHANGE_RETENTION`, default 7 days, so the merge's signatures still meet), and
the state file is compacted to the live submissions on start. The service serves one race (another race's path: 404).

## The API

```
POST /v1/<race>/<submission>/<kind>   {"node": "0x…", …the message}   200 | 400 403 404 409 410 424 425 503
GET  /v1/<race>/<submission>/<kind>                                    {node: message}
GET  /healthz
```
Kinds: `seal`, `reveal`, `result`, `merged`; their messages are the node's (see `exchange/service.py`).

## Run it

```
EXCHANGE_RPC=http://127.0.0.1:8546 EXCHANGE_RACE=0x… python3 -m exchange     # standard library only
docker build -f exchange/Dockerfile -t pof-exchange .                          # the pinned image (Python 3.12, Alpine)
ORACLE_EXCHANGE_URL=https://<handle>:<key>@<devnet host>/exchange python3 -m oracle run
scripts/demo-e2e.sh --exchange http      # the demo, 7 nodes sharing no folder, through the service
scripts/demo-e2e.sh --exchange http-down # the demo with the service down: the nodes fall back to the folder
```

## Deploying it on the devnet host (#150, platform-197)

Hosting the relay is optional and lives in the platform repository (`modules/pof_devnet/`):

- an `exchange` service in the host's `compose.yaml`, in an `exchange` profile so it runs only when configured:
  `EXCHANGE_RPC=http://anvil:8545` (the local anvil, never published), `EXCHANGE_RACE`, state on `/data/exchange` (owned by
  10002), user 10002, a read-only root, no capabilities, 128 MB;
- a Caddy route `handle_path /exchange/* → exchange:8560` inside the same site and the same `basic_auth` and 1 MB body cap as
  the RPC (everything else still goes to anvil), so the per-engineer API keys cover it. A body over 64 KiB and under 1 MB gets the
  service's own 413;
- the image: a private ECR repository in the host's account, `exchange_image_digest` (null: not run), a linux/arm64 build the
  owner pushes with `scripts/exchange-image.sh`. While it runs, the host's role may log in to ECR and read that one repository;
- `exchange_race` (the devnet's RaceV2), and **`exchange_seal_window_seconds` = 900, not the service's 60 s default**: an
  on-demand validator seals minutes after a submission's commit, and a seal after the window is refused. A round whose judges all
  sealed closes the window at once, so it costs nothing then.

Nodes use `ORACLE_EXCHANGE_URL=https://<devnet host>/exchange`, and send it their RPC key, reused on the RPC's own host. The kit
sets it from `exchange_url`; ideally `http,onchain` once #122 lands. The first run with it: `validator-kit/runbook.md`, "The
first real run"; on a throwaway copy, `scripts/first-run-e2e.sh`.
