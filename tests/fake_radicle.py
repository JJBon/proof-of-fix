"""A stand-in for a Radicle node's shell, for `pofctl verify-head --rad-exec` in the Sepolia deploy's tests (#251 task
3.9): whatever script it's given, it prints the snapshot file named by its first argument, as oracle/radicle.py's
SNAPSHOT would on a node; a missing file is a missing repository (exit 3, as `rad inspect` fails). `snapshot(head)`
writes one where a single delegate's `main`, and so the canonical `main`, is `head`."""

import json
import sys
from pathlib import Path

DELEGATE = "z6MkfakeDelegateForTheDeployTests1111111111111"


def snapshot(head: str) -> str:
    identity = json.dumps({"delegates": [f"did:key:{DELEGATE}"], "threshold": 1})
    return (f"@me did:key:{DELEGATE}\n@identity\n{identity}\n@canonical {head}\n@refs\n"
            f"refs/namespaces/{DELEGATE}/refs/heads/main {head}\n@graph\n{head}\n@end\n")


if __name__ == "__main__":
    p = Path(sys.argv[1])
    if not p.is_file():
        sys.stderr.write("rad inspect: repository not found\n")
        sys.exit(3)
    sys.stdout.write(p.read_text(encoding="utf-8"))
