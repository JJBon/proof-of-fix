"""Task 2.3: nothing in pof/ can open a connection, run a program or read keys (specs/ledger, "No external
connection"; openspec/config.yaml rule 1). Checked on the source, so it also covers code paths tests don't run."""

import ast
import tempfile
import unittest
from pathlib import Path

FORBIDDEN = {"socket", "http", "urllib", "ssl", "subprocess", "ftplib", "smtplib", "requests", "httpx", "asyncio"}
PACKAGE = Path(__file__).resolve().parent.parent / "pof"


def imports(path: Path) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and getattr(node.func, "id", "") in {"__import__", "open", "eval", "exec"}:
            found.add(node.func.id)
    return found


class TestNoNetwork(unittest.TestCase):
    def test_package_imports_nothing_that_reaches_out(self):
        files = sorted(PACKAGE.rglob("*.py"))
        self.assertTrue(files)
        for path in files:
            bad = imports(path) & (FORBIDDEN | {"__import__", "open", "eval", "exec"})
            self.assertFalse(bad, f"{path.relative_to(PACKAGE.parent)} uses {sorted(bad)}")

    def test_the_check_catches_an_offender(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "offender.py"
            sample.write_text("import socket\nfrom urllib.request import urlopen\nopen('/etc/key')\n", encoding="utf-8")
            self.assertEqual(imports(sample) & (FORBIDDEN | {"open"}), {"socket", "urllib", "open"})


if __name__ == "__main__":
    unittest.main()
