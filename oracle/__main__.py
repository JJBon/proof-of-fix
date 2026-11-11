"""The node's command line (proof-of-fix#94 phase 1; v2 for #104).

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
    python3 -m oracle model-check          one small PAID call to the direct judge's model (ORACLE_JUDGE=direct:...),
                                           at most 64 tokens out, no retry; prints the answer, the provider's usage, the
                                           endpoint and the request ID. Needs no chain

Configuration (environment):
    ORACLE_RPC       the chain's JSON-RPC URL; user info in it (https://<handle>:<key>@host) is sent as HTTP Basic
    ORACLE_RPC_TOKEN or RPC_API_KEY
                     the chain's API key, in ORACLE_RPC_API_KEY_HEADER: "Authorization" (Bearer, the default),
                     "Basic" (a "<handle>:<key>" key, the demo chain's) or another header name (the raw key)
    ORACLE_RPC_RETRIES  retries of a call the chain didn't answer (connection errors, timeouts, HTTP 429, 502, 503, 504),
                     with backoff up to 15 s; only calls safe to repeat, and never a revert (default 5)
    ORACLE_RACE      the Race contract (RaceV2 for v2: Verdicts and the meter are read from it)
    ORACLE_VERSION   1 or 2 for info (default 1); run and withdraw-fees are v2
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
                     folder, http, onchain (task 5.5, not built yet), p2p (interface only), or several comma-separated
                     (posted to each, read from all: none is required). Default: http with ORACLE_EXCHANGE_URL, else folder
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
    ORACLE_ROUND_TIMEOUT  seconds a round waits for the other drawn judges (default 60)
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
    try:
        node.radicle = radicle.from_env(env)  # the merge as canonical main on Radicle (#201), or the forge's (None)
    except ValueError as e:
        raise SystemExit(f"oracle run: {e}") from None
    rpc.log = node.log  # the retries of a chain that didn't answer (#166)
    if hasattr(judge, "log"):
        judge.log = node.log  # retries and refusals of a direct model call
    return node


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
