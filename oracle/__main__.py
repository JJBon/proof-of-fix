"""The node's command line (proof-of-fix#94 phase 1; v2 for #104; v3 for #139).

    python3 -m oracle info                 the node's address, chain, attestation kind, and whether its key sits
    python3 -m oracle watch                print sealed submissions as they appear (v1)
    python3 -m oracle run [--until-idle S] [--from-block N]
                                           v2: judge every submission this seat is drawn for (check, report usage to
                                           the meter, seal, reveal, sign, relay; the merge too), and exit after S
                                           seconds without progress (the validator kit's on-demand run). A chain that
                                           isn't answering isn't idleness. Exit 75 (EX_TEMPFAIL): it stayed away, the
                                           run didn't finish; the kit's watcher starts the node again (#166)
    python3 -m oracle withdraw-fees [--to ADDRESS]
                                           v2: pull this key's check fees (its credit in the fee coin) to its address
    python3 -m oracle seat <command>       a role seat on the AWS devnet's seats host (platform#219): the command
                                           with devnet-seats.sh's settings and the seat's secrets from files
                                           (oracle/seat.py)
    python3 -m oracle model-check          one small PAID call to the direct judge's model (ORACLE_JUDGE=direct:...),
                                           at most 64 tokens out, no retry; prints the answer, the provider's usage, the
                                           endpoint and the request ID. Needs no chain

v3 (ORACLE_VERSION=3, ORACLE_RACE the RaceV3: an open validator, #139; oracle/node_v3.py):
    python3 -m oracle register --bond COINS [--proof simulated|tee|zktls] [--family NAME] [--host NAME]
                                    [--tee-type NAME] [--level A|B] [--firmware N] [--operator ADDRESS] [--image ID]
                                    [--rad-node DID|NID|0xKEY|none]
                                           register this key as a candidate, signed by it and bonded from its account.
                                           `simulated` (devnets only, the default) and `tee` attest with a quote from
                                           the key provider: ORACLE_KEYS=dstack, with DSTACK_SIMULATOR_ENDPOINT for
                                           `simulated`. The registration signs this validator's Radicle node key
                                           (#251, L11; on-chain, `radNodeOf`): --rad-node, ORACLE_RAD_NODE, or the
                                           node's own `rad self --did` (through ORACLE_RADICLE_EXEC); `none` registers
                                           without one, and the seat is then never counted as a Radicle delegate. The
                                           node can't be changed later: another node is another registration
    python3 -m oracle leave                announce leaving; `withdraw-bond` after the unbonding delay
    python3 -m oracle run [--until-idle S] [--from-block N]
                                           act on every seat Panels gives this key (counted judge, shadow, auditor,
                                           challenge judge): check, seal, then receipt and reveal on-chain, usage
                                           report; post its cost table each period; make the keeper's calls
    python3 -m oracle challenge SUBMISSION [--force]
                                           re-run a counted verdict's check; if this node disagrees or finds a false
                                           receipt, file a challenge with the evidence (its stake and the panel's cost
                                           come from this key's account)
    python3 -m oracle post-table           post this validator's cost table now

Configuration (environment):
    ORACLE_RPC       the chain's JSON-RPC URL; user info in it (https://<handle>:<key>@host) is sent as HTTP Basic
    ORACLE_RPC_TOKEN or RPC_API_KEY
                     the chain's API key, in ORACLE_RPC_API_KEY_HEADER: "Authorization" (Bearer, the default),
                     "Basic" (a "<handle>:<key>" key, the demo chain's) or another header name (the raw key)
    ORACLE_RPC_RETRIES  retries of a call the chain didn't answer (connection errors, timeouts, HTTP 429, 502, 503, 504),
                     with backoff up to 15 s; only calls safe to repeat, and never a revert (default 5)
    ORACLE_RACE      the Race contract (RaceV2 for v2: Verdicts and the meter are read from it)
    ORACLE_VERSION   1, 2 or 3 (default 1 for info; run and withdraw-fees are v2 unless it says 3)
    ORACLE_KEYS      "dstack" (inside a Phala dstack CVM, or DSTACK_SIMULATOR_ENDPOINT), "env" (ORACLE_PRIVATE_KEY:
                     the validator's own key; devnet chains only) or "local:<i>" (INSECURE, local chains only:
                     forge's makeAddrAndKey("oracle<i>"))
  run only:
    ORACLE_REPO      owner/name of the repository whose pull requests claim the submissions
    ORACLE_REPOS     the repository host config (bot/forge.py's repos.json; GitHub by default, with GITHUB_TOKEN)
    ORACLE_SRC_ROOT  checkouts of the fixes, one directory per head commit (<root>/<sha>); the node fetches each
                     claimed commit there itself, verified and read-only (oracle/fetch.py, #115)
    ORACLE_FETCH     "0": use only checkouts already under ORACLE_SRC_ROOT (default: fetch)
    ORACLE_GIT_URL   the clone URL, "{repo}" for owner/name (default: the host's; https, or file:// locally)
    ORACLE_GIT_TOKEN or ORACLE_GIT_TOKEN_FILE
                     a read-only token for the repository (default: the host's: GITHUB_TOKEN, FORGEJO_TOKEN); sent
                     as a header, never logged
    ORACLE_FETCH_MAX_MB, ORACLE_FETCH_TIMEOUT
                     one fetch's limits (default 200 MB, 120 s)
    ORACLE_SANDBOX   how the fixes' tests are started: "cli" (the Docker CLI) or "api" (the Docker socket,
                     DOCKER_SOCKET, default /var/run/docker.sock); by default the CLI when installed (#116).
                     ORACLE_SANDBOX_USER runs them as that user (e.g. 65534:65534)
    ORACLE_EXCHANGE_TRANSPORT  how the drawn judges exchange seals, reveals and signatures (#117; oracle/transport.py):
                     folder, http, onchain (v3 only: the contracts themselves), p2p (interface only), or several
                     comma-separated (posted to each, read from all: none is required). Default: onchain on v3; on v2
                     http with ORACLE_EXCHANGE_URL, else folder
    ORACLE_EXCHANGE_URL   http: the hosted exchange service, a convenience relay (https://<host>/exchange; its key:
                     the URL's user info, ORACLE_EXCHANGE_TOKEN in ORACLE_EXCHANGE_API_KEY_HEADER, or the RPC's own key
                     when it's on the RPC's host)
    ORACLE_EXCHANGE  folder: the directory the drawn judges share (one machine; default .oracle-exchange)
    ORACLE_RECEIPTS  where receipts are stored (default .oracle-receipts)
    ORACLE_JUDGE     "fake" (the default: deterministic, no model call), "direct:<provider>:<model>" (a counted
                     judge: a PAID call straight to the provider, #118) or "gateway:<family>" (development only, PAID).
                     direct providers: bedrock (Converse, the instance role's credentials via IMDSv2 or AWS_* in the
                     environment, AWS_REGION; ORACLE_MODEL_ALLOW required), anthropic, openai (any OpenAI-compatible
                     server with ORACLE_MODEL_URL), gemini; MODEL_API_KEY or MODEL_API_KEY_FILE, sent as a header only
    ORACLE_MODEL_ALLOW, ORACLE_MODEL_URL, ORACLE_MAX_TOKENS (default 4000 per verdict), ORACLE_MAX_CALLS (20 per run),
    ORACLE_MAX_RUN_TOKENS (500000 per run), ORACLE_MODEL_TIMEOUT (120 s), ORACLE_MODEL_RETRIES (2)
                     the direct judge's allowlist, endpoint and spending guards (oracle/models.py)
    ORACLE_LIE       1: the fake judge inverts its verdict (a dishonest node, for demos)
    ORACLE_MERGE_WEIGHT   the merge's importance estimate in coins (default 100)
    ORACLE_MERGE_VIA      "forge" (the default: sign the merge once the host's pull request is merged) or "radicle"
                     (#201, oracle/radicle.py: push the won fix to this seat's Radicle copy as a delegate and sign once
                     it's canonical main by the delegate threshold, on top of Heads' head); then ORACLE_RADICLE_RID (the
                     repository; its id in Heads is keccak256 of it), ORACLE_RADICLE_EXEC (a command prefix that reaches
                     the seat's Radicle node, e.g. "docker exec -i <container>"; default this machine) and
                     ORACLE_RADICLE_REPO (the delegate's working copy there, default ~/repo)
    ORACLE_REGISTRATION_CHECK  "on": the seats' registration check (#210, oracle/registration.py): sign RaceV2's
                     accept for a registration a `bounty`-labelled issue validly claims, with the fake judge only, and
                     relay it at quorum. Off by default. ORACLE_REGISTER_WEIGHT (coins, default 120), ORACLE_RELAY_GRACE
                     (seconds, default 30), ORACLE_REPO_ID (the repository's id on-chain; default 0x0, outside the
                     registry)
    ORACLE_ROUND_TIMEOUT  seconds a round waits for the other drawn judges (default 60)
    ORACLE_ROUNDS    a directory for the node's rounds on disk (#216, oracle/rounds.py): its salt, verdict and steps,
                     so a restarted node finishes a round it sealed instead of sitting it out. Unset: in memory only
  v3 only:
    ORACLE_FAMILY    the model family this validator registers with and judges as (D19: the provider's model line,
                     e.g. "anthropic/claude"; default "fake", the fake judge's)
    ORACLE_HOST_ID   the infrastructure host it declares (default "local")
    ORACLE_IMAGE     the checker image digest on the registry's list: 0x and 64 hex digits, or a name that's hashed
                     (default: the devnet's)
    ORACLE_COSTS     this validator's own shared-unit costs, JSON or a JSON file: vcpu_second, gb_second, storage_mb
                     (micro-coins per million units) and eth (micro-coins per ETH). A unit left out is posted at the
                     price in force
    ORACLE_LIST_PRICES  a JSON file of the families' public list prices, {name: [input, cached, output]} in
                     micro-coins per million tokens (default: pof/costs.py's)
    ORACLE_KEEPER    "off": don't make the calls anyone may make (draws, replacements, finality, pay, the roll)
    ORACLE_RECEIPT_SOURCES  directories where other validators' receipts are published, comma-separated (a
                     challenge judge reads the original judges' receipts there)
    ORACLE_FIX_SOURCE  "host" (the default: ORACLE_REPO's pull requests, and its labelled issues for the registration
                     checks' claims) or "radicle" (#251 tasks 4.2 and 4.3, oracle/radicle_v3.py: the patches on this
                     validator's Radicle node, the commit fetched from its storage; a fix it can't find or fetch by the
                     seal deadline is sealed as not available; and the Radicle issue that claims a registration, which
                     the judge checks is a genuine bug report in scope, or a failing seal saying why none was read)
    ORACLE_MERGE_VIA      on v3, "radicle" (#251 task 4.1, model (a)): push Heads.head as this node's main when it moves
                     at finality, and keep the identity's delegates equal to the seats, one pending revision at a time.
                     Both Radicle parts take ORACLE_RADICLE_RID (keccak256 of it must be the race's repo()),
                     ORACLE_RADICLE_EXEC and ORACLE_RADICLE_REPO as on v2; ORACLE_SEAT_NODES ("chain", the default:
                     each seat's node key from its registration, Validators.radNodeOf; "bindings", signed bindings in
                     the identity document, the default and only choice for a registry from before that field),
                     ORACLE_SEAT_BINDINGS (bindings only: a JSON file of other validators' bindings to carry),
                     ORACLE_RADICLE_EVERY (seconds between passes, default 30)
    ORACLE_ZKTLS_BIN, ORACLE_ZKTLS_NOTARY, ORACLE_ZKTLS_MODE
                     a level C validator's zkTLS prover (oracle/zktls.py: a stub until the pinned build is run)
    (ORACLE_ROUNDS defaults to .oracle-rounds on v3: a node that loses what it sealed is slashed for not revealing)
    ORACLE_POLL           seconds between the node's passes over the chain (default 2)
    ORACLE_RPC_OUTAGE_LIMIT  with --until-idle: seconds the chain may stay away before the run ends with exit 75 (default
                     1800). Without --until-idle the node keeps trying for as long as it takes, its round in memory"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from .chain import Race, Rpc
from .keys import DstackKeys, EnvKeys, LocalDevKeys
from .rpc import Unavailable, auth_headers


EXIT_UNFINISHED = 75  # EX_TEMPFAIL
DEFAULT_RPC_RETRIES, DEFAULT_OUTAGE_LIMIT_S = 5, 1800.0


def keys_from_env(chain_id: int, race: str):
    spec = os.environ.get("ORACLE_KEYS", "dstack")
    if spec.startswith("local:"):
        return LocalDevKeys(int(spec.split(":", 1)[1]))
    if spec == "env":
        return EnvKeys()
    return DstackKeys(f"pof/oracle/{chain_id}/{race.lower()}")


def rpc_from_env() -> Rpc:
    token = os.environ.get("ORACLE_RPC_TOKEN") or os.environ.get("RPC_API_KEY")
    header = os.environ.get("ORACLE_RPC_API_KEY_HEADER") or "Authorization"
    return Rpc(os.environ["ORACLE_RPC"], headers=auth_headers(token, header),
               retries=int(os.environ.get("ORACLE_RPC_RETRIES") or DEFAULT_RPC_RETRIES))


def v2_node(rpc, race_address: str, keys, env=None):
    """The v2 node, configured from the environment (see the module's docstring)."""
    from bot.forge import load_config, repo_for

    from . import fetch, radicle, receipt, v2
    from .judge import judge_from_env
    from .models import ConfigError
    from .node_v2 import NodeV2
    from .transport import exchange_from_env

    env = os.environ if env is None else env
    chain = v2.Chain(rpc, race_address)
    try:
        judge = judge_from_env(env)
    except (ConfigError, ValueError) as e:
        raise SystemExit(f"oracle run: {e}") from None
    repo = env.get("ORACLE_REPO", "")
    if not repo:
        raise SystemExit("oracle run: set ORACLE_REPO (owner/name)")
    host = repo_for(repo, load_config(env.get("ORACLE_REPOS")))
    me = keys.address()
    exchange = exchange_from_env(env, chain.race, log=lambda m: print(f"[{me[:10]}] {m}", flush=True), chain=chain,
                                 keys=keys)
    store = receipt.Store(Path(env.get("ORACLE_RECEIPTS", ".oracle-receipts")))
    weight = int(round(float(env.get("ORACLE_MERGE_WEIGHT", "100")) * 10**6))
    node = NodeV2(chain, keys, judge, host, repo, Path(env.get("ORACLE_SRC_ROOT", ".oracle-src")), exchange, store,
                  weight, round_timeout=float(env.get("ORACLE_ROUND_TIMEOUT", "60")),
                  log=lambda m: print(f"[{me[:10]}] {m}", flush=True))
    node.fetcher = fetch.from_env(env, repo, host, log=node.log)  # the fix's code, fetched by the node (#115)
    if env.get("ORACLE_ROUNDS"):
        from . import rounds

        node.rounds = rounds.Store(Path(env["ORACLE_ROUNDS"]), chain.chain_id(), chain.race, me)
    try:
        node.radicle = radicle.from_env(env)  # the merge as canonical main on Radicle (#201), or the forge's (None)
    except ValueError as e:
        raise SystemExit(f"oracle run: {e}") from None
    from . import registration

    node.registrations = registration.from_env(env, chain, keys, node.wallet, host, exchange, judge, log=node.log)
    rpc.log = node.log  # the retries of a chain that didn't answer (#166)
    if hasattr(judge, "log"):
        judge.log = node.log  # retries and refusals of a direct model call
    return node


def _json_setting(value: str):
    """A JSON setting given inline or as a file's path."""
    import json

    value = (value or "").strip()
    if not value:
        return None
    return json.loads(value if value.startswith("{") else Path(value).read_text())


def v3_node(rpc, race_address: str, keys, env=None, need_repo: bool = True):
    """The v3 node, configured from the environment (see the module's docstring)."""
    from bot.forge import load_config, repo_for

    from . import fetch, radicle_v3, receipt, rounds, v3, zktls
    from .judge import DirectJudge, judge_from_env
    from .models import ConfigError
    from .node_v3 import NodeV3
    from .rpc import Wallet
    from .transport import exchange_from_env

    env = os.environ if env is None else env
    chain = v3.Chain(rpc, race_address)
    me = keys.address()

    def log(m):
        print(f"[{me[:10]}] {m}", flush=True)

    try:
        judge = judge_from_env(env)
    except (ConfigError, ValueError) as e:
        raise SystemExit(f"oracle: {e}") from None
    repo = env.get("ORACLE_REPO", "")
    if need_repo and not repo:
        raise SystemExit("oracle: set ORACLE_REPO (owner/name)")
    host = repo_for(repo, load_config(env.get("ORACLE_REPOS"))) if repo else None
    wallet = Wallet(rpc, keys.account_secret(), "node")
    exchange = exchange_from_env(env, chain.race, log=log, chain=chain, keys=keys, wallet=wallet)
    prover = None
    if chain.validator(me)["proofType"] == "0x" + v3.PROOF_ZKTLS.hex():
        if not isinstance(judge, DirectJudge):
            raise SystemExit("oracle: a zkTLS (level C) validator proves a direct model call: set "
                             "ORACLE_JUDGE=direct:<provider>:<model>")
        prover = zktls.ProvingRequest(zktls.TlsnProver.from_env(env))
        judge.client.request = prover  # every model call goes through the zkTLS session
    sources = [x for x in env.get("ORACLE_RECEIPT_SOURCES", "").split(",") if x]
    node = NodeV3(chain, keys, judge, host, repo, Path(env.get("ORACLE_SRC_ROOT", ".oracle-src")), exchange,
                  receipt.Store(Path(env.get("ORACLE_RECEIPTS", ".oracle-receipts"))), log=log, wallet=wallet,
                  rounds=rounds.Store(Path(env.get("ORACLE_ROUNDS", ".oracle-rounds")), chain.chain_id(), chain.race,
                                      me),
                  prover=prover, costs=_json_setting(env.get("ORACLE_COSTS", "")),
                  list_prices=_json_setting(env.get("ORACLE_LIST_PRICES", "")),
                  keeper=env.get("ORACLE_KEEPER", "on") != "off", repo_id=env.get("ORACLE_REPO_ID") or v3.ZERO,
                  sources=sources)
    if host is not None:
        node.fetcher = fetch.from_env(env, repo, host, log=node.log)
    try:  # Radicle (#251 tasks 4.1, 4.2): patches as the fix source, and model (a)'s seat on this node's Radicle node
        fixes, rad_fetcher, seat = radicle_v3.from_env(env, chain, me, sign=keys.sign, log=node.log)
    except ValueError as e:
        raise SystemExit(f"oracle: {e}") from None
    if fixes is not None:
        node.fixes = fixes
        node.claims = radicle_v3.RadicleIssues(fixes.radicle)  # the registrations' issues on the same node (task 4.3)
        node.fetcher = rad_fetcher if env.get("ORACLE_FETCH", "1") != "0" else None
    node.radicle_seat = seat
    rpc.log = node.log
    if hasattr(judge, "log"):
        judge.log = node.log
    return node


def command_v3(argv: list, rpc, race_address: str, keys) -> int:
    from . import node_v3, v2, v3
    from .rpc import Wallet

    env, cmd, me = os.environ, argv[1] if len(argv) > 1 else "info", keys.address()
    try:
        if cmd == "info":
            chain = v3.Chain(rpc, race_address)
            val = chain.validator(me)
            print(f"node {me} on chain {chain.chain_id()}, RaceV3 {chain.race}; attestation {keys.quote(b'').kind}; "
                  f"registry state {v3.STATES[val['state']]}, bond {val['bond'] / 10**6:,.2f}, slashed "
                  f"{val['slashed'] / 10**6:,.2f}; fees owed {chain.owed(me) / 10**6:,.6f}")
            return 0
        if cmd == "register":
            ap = argparse.ArgumentParser(prog="oracle register")
            ap.add_argument("--bond", type=float, required=True, help="the bond, in coins (at least the floor)")
            ap.add_argument("--proof", choices=sorted(v3.PROOFS), default="simulated")
            ap.add_argument("--family", default=env.get("ORACLE_FAMILY", "fake"))
            ap.add_argument("--host", default=env.get("ORACLE_HOST_ID", "local"))
            ap.add_argument("--tee-type", default="intel-tdx")
            ap.add_argument("--level", choices=["A", "B"], default="A")
            ap.add_argument("--firmware", type=int, default=0)
            ap.add_argument("--operator", default="", help="the operator account (default: this key)")
            ap.add_argument("--image", default=env.get("ORACLE_IMAGE", ""))
            ap.add_argument("--rad-node", default=env.get("ORACLE_RAD_NODE", ""),
                            help="this validator's Radicle node: did:key:z6Mk…, its Node ID z6Mk… or 0x and 64 hex "
                                 "digits; `none` for no node (default: ORACLE_RAD_NODE, else `rad self --did` on the "
                                 "node ORACLE_RADICLE_EXEC reaches)")
            a = ap.parse_args(argv[2:])
            chain = v3.Chain(rpc, race_address)
            node_v3.register(chain, keys, Wallet(rpc, keys.account_secret(), "node"), int(round(a.bond * 10**6)),
                             Path(env.get("ORACLE_RECEIPTS", ".oracle-receipts")), proof=a.proof, family=a.family,
                             host=a.host, image=v3.name_id(a.image) if a.image else v2.DEVNET_IMAGE,
                             operator=a.operator, tee_type=a.tee_type, level={"A": 1, "B": 2}[a.level],
                             firmware=a.firmware, rad_node=node_v3.rad_node_arg(a.rad_node, env))
            return 0
        if cmd in ("leave", "withdraw-bond"):
            chain = v3.Chain(rpc, race_address)
            fn = node_v3.leave if cmd == "leave" else node_v3.withdraw_bond
            fn(chain, keys, Wallet(rpc, keys.account_secret(), "node"))
            return 0
        if cmd == "post-table":
            v3_node(rpc, race_address, keys, need_repo=False).post_table()
            return 0
        if cmd == "challenge":
            ap = argparse.ArgumentParser(prog="oracle challenge")
            ap.add_argument("submission", type=int)
            ap.add_argument("--force", action="store_true", help="file it even if this node's check agrees")
            a = ap.parse_args(argv[2:])
            filed = v3_node(rpc, race_address, keys).challenge(a.submission, force=a.force)
            return 0 if filed is not None else 3
        if cmd == "run":
            ap = argparse.ArgumentParser(prog="oracle run")
            ap.add_argument("--until-idle", type=float, help="exit after this many seconds without progress")
            ap.add_argument("--from-block", type=int, help="scan from this block (default: the last 5000)")
            a = ap.parse_args(argv[2:])
            node = v3_node(rpc, race_address, keys)
            start = a.from_block if a.from_block is not None else max(rpc.block() - 5000, 0)
            outage = float(env.get("ORACLE_RPC_OUTAGE_LIMIT") or DEFAULT_OUTAGE_LIMIT_S)
            done = node.run(start, a.until_idle, poll=float(env.get("ORACLE_POLL", "2")),
                            outage_limit=outage if a.until_idle is not None else None)
            print(f"node {me}: {done} seat(s) finished", flush=True)
            return 0
    except node_v3.SetupError as e:
        print(f"oracle: {e}", flush=True)
        return 1
    print(__doc__)
    return 2


def model_check(env) -> int:
    """One call through the direct judge's client (oracle/models.py) with a tiny prompt: the operator's check that the
    node reaches its model with its own credentials, before a counted run. Exactly one attempt."""
    import json

    from . import models

    spec = env.get("ORACLE_JUDGE", "")
    if not spec.startswith("direct:"):
        print("oracle model-check: set ORACLE_JUDGE=direct:<provider>:<model>")
        return 2
    env = {**env, "ORACLE_MAX_TOKENS": env.get("ORACLE_MODEL_CHECK_TOKENS", "64"), "ORACLE_MAX_CALLS": "1",
           "ORACLE_MODEL_RETRIES": "0"}
    try:
        done = models.client_from_env(spec, env).complete("You check a connection. Answer with one word.", "Say OK.")
    except (models.ModelError, models.ConfigError) as e:
        print(f"oracle model-check: {e}")
        return 1
    print(json.dumps({"answer": done.text[:200], "usage": done.usage, "inference": done.inference}, indent=1,
                     sort_keys=True))
    return 0


def main(argv: list) -> int:
    if len(argv) > 1 and argv[1] == "seat":  # a role seat on the AWS devnet's seats host (oracle/seat.py, #152)
        from .seat import main as seat_main

        return seat_main(argv[1:], main)
    try:
        return command(argv)
    except Unavailable as e:
        print(f"oracle: {e}; the run didn't finish", flush=True)
        return EXIT_UNFINISHED


def command(argv: list) -> int:
    if len(argv) > 1 and argv[1] == "model-check":
        return model_check(os.environ)
    if "ORACLE_RPC" not in os.environ or "ORACLE_RACE" not in os.environ:
        print(__doc__)
        return 2
    rpc = rpc_from_env()
    chain_id = rpc.chain_id()
    race_address = os.environ["ORACLE_RACE"]
    keys = keys_from_env(chain_id, race_address)
    keys.check_chain(chain_id)
    cmd = argv[1] if len(argv) > 1 else "info"
    if os.environ.get("ORACLE_VERSION", "1") == "3":
        return command_v3(argv, rpc, race_address, keys)
    if cmd == "info" and os.environ.get("ORACLE_VERSION", "1") == "2":
        from . import v2

        chain = v2.Chain(rpc, race_address)
        print(f"node {keys.address()} on chain {chain_id}, RaceV2 {chain.race}; attestation {keys.quote(b'').kind}; "
              f"an active seat's key: {chain.is_oracle(keys.address())} ({len(chain.keys())} active seats); "
              f"fees owed {chain.owed(keys.address()) / 10**6:,.6f}")
        return 0
    if cmd == "info":
        race = Race(rpc, race_address)
        listed = keys.address().lower() in {a.lower() for a in race.oracle_keys()}
        print(f"node {keys.address()} on chain {chain_id}, Race {race.address}; attestation "
              f"{keys.quote(b'').kind}; listed in the oracle set: {listed} (quorum {race.quorum()})")
        return 0
    if cmd == "watch":
        race = Race(rpc, race_address)
        seen, start = set(), max(rpc.block() - 1000, 0)
        while True:
            for s in race.committed_since(start):
                if s["submission"] not in seen:
                    seen.add(s["submission"])
                    print(f"sealed submission {s['submission']} on bounty {s['bounty']} by {s['solver']}", flush=True)
            time.sleep(5)
    if cmd == "run":
        ap = argparse.ArgumentParser(prog="oracle run")
        ap.add_argument("--until-idle", type=float, help="exit after this many seconds without progress")
        ap.add_argument("--from-block", type=int, help="scan from this block (default: the last 5000)")
        a = ap.parse_args(argv[2:])
        node = v2_node(rpc, race_address, keys)
        start = a.from_block if a.from_block is not None else max(rpc.block() - 5000, 0)
        outage = float(os.environ.get("ORACLE_RPC_OUTAGE_LIMIT") or DEFAULT_OUTAGE_LIMIT_S)
        done = node.run(start, a.until_idle, poll=float(os.environ.get("ORACLE_POLL", "2")),
                        outage_limit=outage if a.until_idle is not None else None)
        print(f"node {keys.address()}: {done} check(s) finished", flush=True)
        return 0
    if cmd == "withdraw-fees":
        from . import v2
        from .node_v2 import withdraw_fees

        ap = argparse.ArgumentParser(prog="oracle withdraw-fees")
        ap.add_argument("--to", help="the address paid (default: the key's own)")
        a = ap.parse_args(argv[2:])
        owed = withdraw_fees(v2.Chain(rpc, race_address), keys, a.to)
        print(f"node {keys.address()}: withdrew {owed / 10**6:,.6f} in fees to {a.to or keys.address()}", flush=True)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
