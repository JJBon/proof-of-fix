"""Tests that can't run in the validator's sandbox (#251 task 4.8): the one place they say so.

The sandbox (oracle/sandbox.py) runs proof-of-fix's own suite, `.pof/check.json`'s command, for every fix to
proof-of-fix: no network, a read-only root, no capabilities, its limits, and POF_SANDBOX=1 in the environment. Its test
image has Python, git and bash (oracle/test-image/Dockerfile), and the tests' TMPDIR allows running a script a test
wrote. A test that needs more than that (Docker, the network, the host) skips there with `outside_sandbox(reason)`,
and nowhere else: on a developer's machine and in CI it runs as before.

Never silently: each skip states its reason in unittest's output ("in the sandbox: <reason>"), and EXPECTED below is
how many there are, which tests/test_sandbox_env.py holds the test files to. A new one changes that number in the same
pull request, so a reviewer sees it."""

from __future__ import annotations

import os
import unittest

IN_SANDBOX = os.environ.get("POF_SANDBOX") == "1"

# How many `outside_sandbox` uses the test files hold (tests/test_sandbox_env.py counts them).
EXPECTED = 18  # 13, and 5 in test_deploy_sepolia.py for the panel rules (#251 contract batch 4)


def outside_sandbox(reason: str):
    """Skips a test or a class inside the validator's sandbox, saying why; runs it everywhere else."""
    if not reason.strip():
        raise ValueError("a test skipped in the sandbox needs a reason")
    return unittest.skipIf(IN_SANDBOX, f"in the sandbox: {reason}")
