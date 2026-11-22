"""tests/sandbox_env.py: the tests skipped in the validator's sandbox are counted and each states a reason."""

from __future__ import annotations

import ast
import io
import unittest
from pathlib import Path
from unittest import mock

import sandbox_env

TESTS = Path(__file__).resolve().parent


def uses() -> list:
    """Every `outside_sandbox(...)` call in the test files: (file, line, reason)."""
    found = []
    for path in sorted(TESTS.rglob("*.py")):
        if path.name in ("sandbox_env.py", "test_sandbox_env.py"):  # the helper and its own tests
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        named = {}  # the module's string constants, so a reason shared by several tests can be named once
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                try:
                    value = ast.literal_eval(node.value)
                except ValueError:
                    continue
                if isinstance(value, str):
                    named[node.targets[0].id] = value
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                if name == "outside_sandbox":
                    arg = node.args[0] if node.args else None
                    reason = (arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                              else named.get(arg.id) if isinstance(arg, ast.Name) else None)
                    found.append((path.relative_to(TESTS).as_posix(), node.lineno, reason))
    return found


class Count(unittest.TestCase):
    def test_the_count_is_kept(self):
        found = uses()
        self.assertEqual(len(found), sandbox_env.EXPECTED,
                         f"tests/sandbox_env.py EXPECTED is {sandbox_env.EXPECTED}, the test files have "
                         f"{len(found)}: {found}")

    def test_each_states_its_reason(self):
        for where, line, reason in uses():
            self.assertTrue(reason and reason.strip(), f"{where}:{line}: outside_sandbox needs a reason in the file")


class Helper(unittest.TestCase):
    def test_skips_only_in_the_sandbox_and_says_why(self):
        def make():
            @sandbox_env.outside_sandbox("needs Docker")
            class T(unittest.TestCase):
                def test_x(self):
                    pass
            return unittest.TextTestRunner(stream=io.StringIO()).run(T("test_x"))

        for flag, skipped in (("1", [("test_x", "in the sandbox: needs Docker")]), ("", [])):
            with mock.patch.object(sandbox_env, "IN_SANDBOX", flag == "1"):
                result = make()
            self.assertEqual([(t._testMethodName, why) for t, why in result.skipped], skipped)
            self.assertTrue(result.wasSuccessful())

    def test_a_reason_is_required(self):
        with self.assertRaises(ValueError):
            sandbox_env.outside_sandbox(" ")
