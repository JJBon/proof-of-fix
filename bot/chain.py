"""The chain side of the loop: cast and forge run inside the loop's foundry container, where a throwaway anvil
listens on the container's own loopback (scripts/bounty-loop.sh starts it with no network at all), or inside the
private devnet's container (`bounty-loop.sh --devnet`, #93), whose anvil enforces EIP-170 and has its own chain id."""

from __future__ import annotations

import json
import os
import subprocess

from .logic import script_values

RPC = "http://127.0.0.1:8545"


# On the devnet, the oracle keys reach forge scripts through the environment (from OpenBao; never on a command line).
PASSED_ENV = ("ORACLE_KEYS", "ORACLE_QUORUM")


class Chain:
    def __init__(self, container: str, chain_id: str = "31337") -> None:
        self.container = container
        self.chain_id = chain_id

    def _run(self, *argv: str, key: str | None = None) -> str:
        """Runs a command in the chain's container. A `key` goes through the environment by name only (never on the
        host's docker command line) and is substituted for the KEY argument inside the container."""
        env = [arg for name in PASSED_ENV if os.environ.get(name) for arg in ("-e", name)]
        run_env = None
        if key is not None:
            run_env = {**os.environ, "LOOP_PK": key}
            env += ["-e", "LOOP_PK"]
            argv = ("sh", "-c", 'for a; do [ "$a" = KEY ] && a=$LOOP_PK; set -- "$@" "$a"; shift; done; exec "$@"',
                    "sh", *argv)
        out = subprocess.run(["docker", "exec", *env, "-w", "/work", self.container, *argv],
                             capture_output=True, text=True, timeout=600, env=run_env)
        if out.returncode:
            raise RuntimeError(f"{argv[0]} {argv[1] if len(argv) > 1 else ''} failed:\n{out.stdout}\n{out.stderr}")
        return out.stdout

    def cast(self, *args: str) -> str:
        return self._run("cast", *args).strip()

    def address(self, key: str) -> str:
        return self._run("cast", "wallet", "address", "--private-key", "KEY", key=key).strip()

    def call(self, to: str, sig: str, *args: str) -> list:
        return json.loads(self.cast("call", "--rpc-url", RPC, "--json", to, sig, *args))

    def uint(self, to: str, sig: str, *args: str) -> int:
        return int(self.call(to, sig, *args)[0])

    def send(self, key: str, to: str, sig: str, *args: str) -> dict:
        receipt = json.loads(self._run("cast", "send", "--rpc-url", RPC, "--private-key", "KEY", "--json", to, sig, *args,
                                       key=key))
        if receipt.get("status") not in ("0x1", 1, "1"):
            raise RuntimeError(f"{sig} reverted: {receipt}")
        return receipt

    def script(self, key: str, contract: str, sig: str, *args: str) -> dict[str, str]:
        """A function of a forge script, broadcast from `key`; returns the NAME=value lines it logs."""
        return script_values(self._run("forge", "script", contract, "--sig", sig, *args, "--rpc-url", RPC,
                                       "--broadcast", "--private-key", "KEY", key=key))

    def quote(self, race: str, bounty: int, coin: str) -> str:
        """Task 3.2's quote, as a solver reads it before trying."""
        out = self._run("forge", "script", "script/Quote.s.sol", "--sig", "quote(address,uint256,address)", race,
                        str(bounty), coin, "--rpc-url", RPC)
        return out[out.index("== Logs ==") + len("== Logs =="):].strip() if "== Logs ==" in out else out

    def keccak(self, text: str) -> str:
        return self.cast("keccak", text)

    def commitment(self, fix: str, salt: str, solver: str) -> str:
        """A sealed submission: keccak256(abi.encode(fix hash, salt, solver)), as the contract's tests seal it."""
        return self.cast("keccak", self.cast("abi-encode", "f(bytes32,bytes32,address)", fix, salt, solver))

    def warp(self, days: int) -> None:
        self.cast("rpc", "--rpc-url", RPC, "evm_increaseTime", str(days * 86_400))
        self.cast("rpc", "--rpc-url", RPC, "evm_mine")

    def ready(self) -> bool:
        try:
            return self.cast("chain-id", "--rpc-url", RPC) == self.chain_id
        except RuntimeError:
            return False
