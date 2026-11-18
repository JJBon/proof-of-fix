"""A zkTLS prover for the model call of a node without a TEE (proof-of-fix#139, task 4.1 of #132; design D10, D11).

Task 1.9 (#135, reports/zktls-spike-v1.md) chose TLSNotary: `tlsn` v0.1.0-alpha.15, with the spike's three small
tools (experiments/zktls/rust: `pof_prove`, `pof_verify`, `pof_notary`) and a receipt, `pof-zktls-receipt/1`, that
pure Python checks offline (experiments/zktls/receipt_check.py). The spike's answer was "not yet": no independent
notary signs proofs today, the request is limited to about 4 KB in MPC mode, and the software is alpha. Level C is
therefore off at launch (zkTLS isn't on the genesis list), and this module is as much as can honestly be built now:

- `Prover`: the interface. `call` makes one HTTPS request through a zkTLS session and returns the provider's reply
  with a `Proof` of it. It has the shape of oracle/models.py's `http_request`, so the direct judge's client takes a
  prover in its place (`ProvingRequest`) and nothing else about the judge changes.
- `check`: what a node checks of a proof before it seals on it, and a judge of another's level C receipt: the
  notary's signature, the signed commitments and every revealed byte (receipt_check), the TLS version, the server's
  name, and that the reply the judge read is the reply proven. Offline, pure Python.
- `TlsnProver`: STUB. It is written against the spike's tools' command lines (`pof_prove --attest`, then
  `pof_verify --receipt`), but it has never been run from this module: the tools need the pinned Rust build
  (experiments/zktls/build.sh), a notary that answers, and a real, paid model call, and none of those is available
  to this repository's checks. Without ORACLE_ZKTLS_BIN it refuses with `Unavailable`. Until someone runs it against
  the pinned build, treat every line of it as unproven.

What a proof doesn't show is in the report: answer shopping (D10), and that a validator's own notary proves nothing."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .crypto import keccak256

ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = "tlsn v0.1.0-alpha.15"  # task 1.9's choice; a receipt names it, since alpha releases differ
FORMAT = "pof-zktls-receipt/1"
TLS_VERSION = "V1_2"  # all tlsn speaks (the report, "TLS 1.3")
HIDE = ("authorization", "x-api-key", "x-goog-api-key", "x-amz-security-token")  # credentials, never revealed


class Unavailable(RuntimeError):
    """No prover here: the pinned build, a notary or the tools' path is missing."""


class ProofError(ValueError):
    """A proof that doesn't show what it must."""


@dataclass(frozen=True)
class Proof:
    receipt: dict  # pof-zktls-receipt/1: the notary's signed attestation and the revealed transcript
    notary: str  # the notary's address, as the constitution's list names it

    def to_bytes(self) -> bytes:
        """The proof's bytes: the receipt's canonical JSON. Their keccak256 is the on-chain receipt's `proof`."""
        return json.dumps(self.receipt, sort_keys=True, separators=(",", ":")).encode()

    def hash(self) -> bytes:
        return keccak256(self.to_bytes())


def _receipt_check():
    """experiments/zktls/receipt_check.py, loaded by path (it's the spike's, kept where task 1.9 put it)."""
    path = ROOT / "experiments" / "zktls" / "receipt_check.py"
    if not path.exists():  # the node's image doesn't carry the spike's files yet: level C is off
        raise Unavailable(f"no zkTLS receipt checker at {path}")
    spec = importlib.util.spec_from_file_location("pof_zktls_receipt_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(receipt: dict, server: str = "", body: bytes | None = None, notaries=None) -> dict:
    """Checks a zkTLS receipt offline and returns what it proves ({"notary", "sent", "recv", ...}). Raises ProofError.

    `server`: the provider's host the call must have gone to (the receipt's name is only as good as the Rust
    verifier's run that exported it: receipt_check doesn't check the certificate chain). `body`: the reply the judge
    read; it must be the proven reply's body. `notaries`: the addresses accepted (the constitution's list); None
    skips that check, for a node looking at its own proof before the list exists."""
    rc = _receipt_check()
    try:
        out = rc.check(receipt)
    except (rc.ReceiptError, KeyError, TypeError, ValueError) as e:
        raise ProofError(f"the zkTLS receipt doesn't verify: {e}") from e
    if receipt.get("implementation") != IMPLEMENTATION:
        raise ProofError(f"the receipt is from {receipt.get('implementation')!r}, not {IMPLEMENTATION}")
    if out["tls_version"] != TLS_VERSION:
        raise ProofError(f"the receipt's TLS version is {out['tls_version']}")
    if server and receipt.get("server_name") != server:
        raise ProofError(f"the receipt is for {receipt.get('server_name')!r}, not {server}")
    if notaries is not None and out["notary"].lower() not in {n.lower() for n in notaries}:
        raise ProofError(f"the notary {out['notary']} isn't on the list")
    if out["recv_revealed"] != len(out["recv"]):
        raise ProofError("the receipt hides part of the provider's reply")
    if body is not None and out["recv"].split(b"\r\n\r\n", 1)[-1] != body:
        raise ProofError("the proven reply isn't the reply the judge read")
    return out


class Prover:
    """The interface: one HTTPS request made through a zkTLS session."""

    def call(self, method: str, url: str, headers: dict, body: bytes | None, timeout: float) -> tuple:
        """(oracle.models.Reply, Proof). Raises Unavailable when there's no prover, OSError when the session fails
        (the model client treats that as a call that may have run)."""
        raise NotImplementedError


class ProvingRequest:
    """A prover as the direct judge's `request` (oracle/models.py's Client): every model call goes through the zkTLS
    session, and the proof of the last answered call waits in `take()` for the receipt."""

    def __init__(self, prover: Prover) -> None:
        self.prover, self._last = prover, None

    def __call__(self, method: str, url: str, headers: dict, body, timeout: float):
        reply, proof = self.prover.call(method, url, headers, body, timeout)
        check(proof.receipt, server=urlsplit(url).hostname or "", body=reply.body)  # before anything is sealed on it
        self._last = proof
        return reply

    def take(self) -> Proof | None:
        proof, self._last = self._last, None
        return proof


class TlsnProver(Prover):
    """STUB (see the module's docstring): the spike's tools, driven as experiments/zktls/run_spike.py drives them.

    ORACLE_ZKTLS_BIN     the directory of the pinned build's `pof_prove` and `pof_verify`
    ORACLE_ZKTLS_NOTARY  the notary, host:port (one on the constitution's list; a validator's own proves nothing)
    ORACLE_ZKTLS_MODE    "mpc" (the default; requests up to about 4 KB) or "proxy" (up to about 20 KB)"""

    def __init__(self, bin_dir: str = "", notary: str = "", mode: str = "mpc", max_sent: int = 4096,
                 max_recv: int = 16384, run=subprocess.run) -> None:
        self.bin, self.notary, self.mode = Path(bin_dir) if bin_dir else None, notary, mode
        self.max_sent, self.max_recv, self.run = max_sent, max_recv, run

    @classmethod
    def from_env(cls, env) -> "TlsnProver":
        return cls(env.get("ORACLE_ZKTLS_BIN", ""), env.get("ORACLE_ZKTLS_NOTARY", ""),
                   env.get("ORACLE_ZKTLS_MODE", "mpc"))

    def call(self, method: str, url: str, headers: dict, body: bytes | None, timeout: float) -> tuple:
        from .models import Reply

        if self.bin is None or not (self.bin / "pof_prove").exists() or not self.notary:
            raise Unavailable("no zkTLS prover: set ORACLE_ZKTLS_BIN to the pinned tlsn build "
                              "(experiments/zktls/build.sh) and ORACLE_ZKTLS_NOTARY to a listed notary")
        u = urlsplit(url)
        path = u.path + (f"?{u.query}" if u.query else "")
        head = {"Host": u.hostname, **headers, "Content-Length": str(len(body or b"")), "Connection": "close"}
        request = (f"{method} {path} HTTP/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in head.items())
                   + "\r\n").encode() + (body or b"")
        if len(request) > self.max_sent:
            raise OSError(f"the request is {len(request)} bytes; this zkTLS mode takes {self.max_sent}")
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "call")
            cmd = [str(self.bin / "pof_prove"), "--verifier", self.notary, "--mode", self.mode, "--server-name",
                   u.hostname, "--max-sent", str(self.max_sent), "--max-recv", str(self.max_recv), "--attest",
                   "--out", out]
            for h in HIDE:
                cmd += ["--hide", h]
            p = self.run(cmd, input=request, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout)
            if p.returncode != 0:
                raise OSError("the zkTLS session failed")
            v = self.run([str(self.bin / "pof_verify"), f"{out}.presentation.tlsn", "--receipt", f"{out}.json",
                          "--expect-server", u.hostname], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         timeout=120)
            if v.returncode != 0:
                raise OSError("the zkTLS proof didn't verify")
            receipt = json.loads(Path(f"{out}.json").read_text())
        proven = check(receipt, server=u.hostname)
        head_, _, reply_body = proven["recv"].partition(b"\r\n\r\n")
        lines = head_.decode("latin-1").split("\r\n")
        status = int(lines[0].split(" ")[1])
        reply_headers = {k.strip().lower(): v.strip() for k, _, v in (line.partition(":") for line in lines[1:])}
        return Reply(status, reply_headers, reply_body), Proof(receipt, proven["notary"])
