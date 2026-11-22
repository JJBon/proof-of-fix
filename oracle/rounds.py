"""A judge node's rounds on disk (#216): what a restarted node needs to finish a round it already judged.

A node keeps each round in memory (oracle/node_v2.py's Check). Its salt is what opens its seal, and once the seal is
on the exchange, a node that lost the salt can't reveal; judging again would only pay for a second verdict the round
can't take. With a store, the node writes its round after every step it completes (the salt is written with the first
step, long before the seal leaves the node), and a restarted node picks the round up where it stopped: the same salt,
outcome and receipt, no second call to the judge.

One JSON file per round, `<root>/<chain id>-<race>/<seat>/<submission>.json`, mode 600 in directories of mode 700,
written whole (a temporary file renamed over the old one). The salt only needs to stay secret until the reveal, which
publishes it; the file is the seat's, on the seat's own disk (the seats host: /var/lib/pof-seats/<seat>/rounds).
A finished round's file is removed."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

FIELDS = ("submission", "bounty", "judges", "pull", "outcome", "receipt_hash", "salt", "reported", "sealed_at",
          "revealed_at", "signed", "merge_signed", "note", "usage")
USAGE_FIELDS = ("receipt", "input", "cached", "output", "vcpu_seconds", "gb_seconds", "storage_mb")


def _plain(value):
    """JSON for a round's values: bytes as {"hex": ...}, everything else as it is."""
    if isinstance(value, bytes):
        return {"hex": value.hex()}
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _back(value):
    if isinstance(value, dict):
        if set(value) == {"hex"}:
            return bytes.fromhex(value["hex"])
        return {k: _back(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_back(v) for v in value]
    return value


class Store:
    def __init__(self, root: Path, chain_id: int, race: str, seat: str) -> None:
        self.dir = Path(root) / f"{chain_id}-{race.lower()}" / seat.lower()

    def _path(self, submission: int) -> Path:
        return self.dir / f"{int(submission)}.json"

    def save(self, check) -> None:
        data = {f: getattr(check, f) for f in FIELDS}
        if check.usage is not None:
            data["usage"] = {f: getattr(check.usage, f) for f in USAGE_FIELDS}
        self._write(self._path(check.submission), data)

    def _write(self, path: Path, data: dict) -> None:
        old = os.umask(0o077)
        try:
            self.dir.mkdir(mode=0o700, parents=True, exist_ok=True)  # new parents too: 700 under this umask
            fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=".round-", suffix=".json")
        finally:
            os.umask(old)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(_plain(data), f, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    # v3 (oracle/node_v3.py): a validator's round is per panel, not per submission (it may sit on several panels of
    # one submission), and keeps other fields; the files and their modes are the same.

    def put(self, name: str, data: dict) -> None:
        """Writes a round under a name of the node's choosing (v3: "panel-<pid>"), whole, as `save` does."""
        self._write(self.dir / f"{name}.json", data)

    def get(self, name: str):
        try:
            return _back(json.loads((self.dir / f"{name}.json").read_text()))
        except FileNotFoundError:
            return None

    def drop(self, name: str) -> None:
        (self.dir / f"{name}.json").unlink(missing_ok=True)

    def load(self, submission: int, check_type):
        """The round this seat saved for the submission, as a `check_type` (node_v2.Check), or None."""
        from .v2 import Usage

        try:
            data = _back(json.loads(self._path(submission).read_text()))
        except FileNotFoundError:
            return None
        usage = data.pop("usage", None)
        c = check_type(**{f: data[f] for f in FIELDS if f in data and f != "usage"})
        c.usage = Usage(**usage) if usage else None
        return c

    def remove(self, submission: int) -> None:
        self._path(submission).unlink(missing_ok=True)
