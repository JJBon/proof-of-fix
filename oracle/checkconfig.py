"""The repository's own test command (proof-of-fix#166 item 3).

A check ran only `python -m unittest` at the fix's root, which finds the issue's acceptance test but none of a
repository's own tests in a folder that isn't a package (pof-sandbox's `bot/sample/test_stats.py`, its `tests/`). A
repository now names its tests in `.pof/check.json`:

    {"commands": [["python", "-m", "unittest", "discover", "-s", "bot/sample", "-t", "bot/sample", "-q"]]}

- **Read at the pull request's base, never from the fix.** The node fetches the base commit itself and reads the file
  there (oracle/fetch.py `Fetcher.file_at`), so a fix can't weaken its own check. The base is what the verdict signs,
  and the head on-chain moves only on a verdict whose base is that head (contracts/src/v2/Heads.sol, S1), so a pull
  request against another branch with a weaker file can't be merged on that verdict.
- **The acceptance test always runs too,** after the repository's commands, as before: `python -m unittest` at the
  root. A repository can't leave it out.
- **Argument lists, never a shell.** Inside the sandbox one fixed runner (RUNNER, below) starts each command in turn
  and stops at the first that fails, so every guarantee of the sandbox (oracle/sandbox.py) holds for all of them under
  its one time limit. The receipt records the runner and the commands, so a verdict shows what ran.
- **No file: nothing changes.** The command is the sandbox's own, as before, and so are the results' hashes.
- **A file that isn't valid fails closed** (the node's `refusal`): no model call, and the fix isn't passed. A
  repository can fix its file; skipping its tests instead would pass fixes on less than it asked for."""

from __future__ import annotations

import json
from typing import Tuple

from .sandbox import COMMAND

PATH = ".pof/check.json"
MAX_BYTES = 8_192
MAX_COMMANDS = 8
MAX_ARGS = 64
MAX_ARG_CHARS = 1_024

# Runs each command (an argument list, never through a shell) and exits with the first non-zero code.
RUNNER = ("import json, subprocess, sys\n"
          "for argv in json.loads(sys.argv[1]):\n"
          "    print('$ ' + ' '.join(argv), flush=True)\n"
          "    code = subprocess.call(argv)\n"
          "    if code:\n"
          "        sys.exit(code)\n")

Commands = Tuple[Tuple[str, ...], ...]


class Invalid(ValueError):
    """The file isn't a valid test command: the check fails closed."""


def parse(data: bytes) -> Commands:
    """The repository's commands from the file's bytes. Raises Invalid with a reason that names no content."""
    if len(data) > MAX_BYTES:
        raise Invalid(f"it's larger than {MAX_BYTES:,} bytes")
    try:
        doc = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise Invalid("it isn't JSON in UTF-8") from None
    if not isinstance(doc, dict) or set(doc) != {"commands"}:
        raise Invalid('it must be an object with one key, "commands"')
    commands = doc["commands"]
    if not isinstance(commands, list) or not 1 <= len(commands) <= MAX_COMMANDS:
        raise Invalid(f'"commands" must be a list of 1 to {MAX_COMMANDS} commands')
    out = []
    for i, argv in enumerate(commands, 1):
        if not isinstance(argv, list) or not 1 <= len(argv) <= MAX_ARGS:
            raise Invalid(f"command {i} must be a list of 1 to {MAX_ARGS} arguments")
        for arg in argv:
            if not isinstance(arg, str) or not arg or len(arg) > MAX_ARG_CHARS or "\0" in arg:
                raise Invalid(f"command {i} has an argument that isn't a non-empty string of at most "
                              f"{MAX_ARG_CHARS:,} characters")
        out.append(tuple(argv))
    return tuple(out)


def command(project: Commands = ()) -> Tuple[str, ...]:
    """What the sandbox runs: the sandbox's own command when the repository names none; else the runner with the
    repository's commands, then the acceptance test."""
    if not project:
        return COMMAND
    return ("python", "-c", RUNNER, json.dumps([list(c) for c in project] + [list(COMMAND)], separators=(",", ":")))
