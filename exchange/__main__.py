"""Runs the exchange service for one RaceV2 (proof-of-fix#117).

    python3 -m exchange

Configuration (environment):
    EXCHANGE_RPC            the chain's JSON-RPC URL, to read the submissions and their draws (user info in it is sent
                            as HTTP Basic); on the devnet host, the local anvil
    EXCHANGE_RPC_TOKEN      or the chain's API key, in EXCHANGE_RPC_API_KEY_HEADER (as the node's ORACLE_RPC_TOKEN)
    EXCHANGE_RACE           the RaceV2 contract
    EXCHANGE_HOST           the address to listen on (default 127.0.0.1; 0.0.0.0 in the container, behind Caddy)
    EXCHANGE_PORT           default 8560
    EXCHANGE_SEAL_WINDOW    seconds after a submission's first seal that seals are taken (default 60: the nodes'
                            ORACLE_ROUND_TIMEOUT); it closes earlier once every drawn judge sealed
    EXCHANGE_REVEAL_WINDOW  seconds after the seal window that reveals are taken (default 600)
    EXCHANGE_RETENTION      seconds a submission's messages are kept after its last one (default 604800: 7 days)
    EXCHANGE_STATE          a file the messages taken are appended to and restored from (default: memory only)"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from oracle import v2
from oracle.rpc import Rpc, auth_headers

from .service import RETENTION, Board, server


def main() -> int:
    env = os.environ
    if not env.get("EXCHANGE_RPC") or not env.get("EXCHANGE_RACE"):
        print(__doc__)
        return 2
    headers = auth_headers(env.get("EXCHANGE_RPC_TOKEN"), env.get("EXCHANGE_RPC_API_KEY_HEADER") or "Authorization")
    chain = v2.Chain(Rpc(env["EXCHANGE_RPC"], headers=headers), env["EXCHANGE_RACE"])
    log = lambda m: print(m, flush=True)  # noqa: E731
    board = Board(chain, seal_window=float(env.get("EXCHANGE_SEAL_WINDOW", "60")),
                  reveal_window=float(env.get("EXCHANGE_REVEAL_WINDOW", "600")),
                  retention=float(env.get("EXCHANGE_RETENTION", str(RETENTION))),
                  state=Path(env["EXCHANGE_STATE"]) if env.get("EXCHANGE_STATE") else None, log=log)
    board.domain()  # refuse to start against a contract whose domain isn't RaceV2's
    srv = server(board, env.get("EXCHANGE_HOST", "127.0.0.1"), int(env.get("EXCHANGE_PORT", "8560")))
    host, port = srv.server_address[:2]
    log(f"exchange: RaceV2 {chain.race} on chain {chain.chain_id()}, listening on {host}:{port} "
        f"(seal window {board.seal_window:.0f}s, reveal window {board.reveal_window:.0f}s)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
