#!/usr/bin/env python3
"""The Radicle publication record (#251 task 6.2), the one place the seed takes proof-of-fix's RID from.

Written at the publish (`rad init` of the scrubbed snapshot, task 6.2), never before:

    {"format": "pof-radicle-publication/1", "rid": "rad:z…", "rootCommit": "<40-hex SHA-1>",
     "nodeId": "z6Mk…", "radicle": "1.10.3"}

seed/terraform reads the same file (`publication_record`) with the same rules, and the seed test on the internal
Docker network (tests/integration/seed_radicle.py) writes one after its own publish and reads it through here.

    python3 seed/publication.py rid <record>      prints the RID, or refuses the record (exit 2)

Standard library only (Python 3.9)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

FORMAT = "pof-radicle-publication/1"
RID_RE = re.compile(r"^rad:z[1-9A-HJ-NP-Za-km-z]+$")
NID_RE = re.compile(r"^z6Mk[1-9A-HJ-NP-Za-km-z]+$")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
RADICLE = "1.10.3"  # spikes/radicle/Dockerfile's release; seed/terraform pins the same


class Refused(ValueError):
    pass


def check(record: dict) -> dict:
    """The record, if it is a publication record the seed may use; Refused otherwise."""
    if not isinstance(record, dict) or record.get("format") != FORMAT:
        raise Refused(f"not a {FORMAT} record")
    for key, rx in (("rid", RID_RE), ("rootCommit", SHA1_RE), ("nodeId", NID_RE)):
        if not isinstance(record.get(key), str) or not rx.match(record[key]):
            raise Refused(f"the record's {key} is missing or malformed")
    if record.get("radicle") != RADICLE:
        raise Refused(f"the record's Radicle release is {record.get('radicle')!r}, not the pinned {RADICLE}")
    return record


def rid(path) -> str:
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Refused(f"can't read the record: {e}") from e
    return check(record)["rid"]


def main(argv: list) -> int:
    if len(argv) != 3 or argv[1] != "rid":
        print(__doc__.split("\n\n")[4], file=sys.stderr)
        return 2
    try:
        print(rid(argv[2]))
    except Refused as e:
        print(f"publication: refused: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
