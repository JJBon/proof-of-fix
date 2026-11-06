"""scripts/check_openspec.py, the CI host's stand-in for `openspec validate`: deltas and main specs each pass in
their own format and fail in the other's."""

import importlib.util
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_openspec.py"
spec = importlib.util.spec_from_file_location("check_openspec", SCRIPT)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

REQ = """### Requirement: Thing
The system SHALL do the thing.

#### Scenario: Done
- **WHEN** asked
- **THEN** it does the thing
"""
PURPOSE = "## Purpose\nLets the project check that its specification files are well formed before merging.\n\n"
DELTA = "# Spec Delta\n\n" + PURPOSE + "## ADDED Requirements\n\n" + REQ
MAIN = "# thing Specification\n\n" + PURPOSE + "## Requirements\n\n" + REQ


def run(files: dict) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel, text in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        with redirect_stdout(StringIO()):
            return check.main(root)


class TestCheckOpenspec(unittest.TestCase):
    change = {"changes/c/proposal.md": "x", "changes/c/.openspec.yaml": "schema: spec-driven\n",
              "changes/c/tasks.md": "- [ ] 1.1 do it\n"}

    def test_valid_delta_and_main_spec(self):
        self.assertEqual(run({**self.change, "changes/c/specs/thing/spec.md": DELTA, "specs/thing/spec.md": MAIN}), 0)

    def test_main_spec_in_delta_format_fails(self):
        self.assertEqual(run({"specs/thing/spec.md": DELTA}), 1)

    def test_delta_in_main_format_fails(self):
        self.assertEqual(run({**self.change, "changes/c/specs/thing/spec.md": MAIN}), 1)

    def test_requirement_without_scenario_fails(self):
        self.assertEqual(run({"specs/thing/spec.md": MAIN.split("#### Scenario")[0]}), 1)

    def test_removed_requirement_needs_a_reason_not_scenarios(self):
        removed = "## REMOVED Requirements\n\n### Requirement: Old\n**Reason**: replaced.\n**Migration**: use Thing.\n\n"
        ok = "# Spec Delta\n\n" + removed + "## ADDED Requirements\n\n" + REQ
        self.assertEqual(run({**self.change, "changes/c/specs/thing/spec.md": ok}), 0)
        self.assertEqual(run({**self.change, "changes/c/specs/thing/spec.md": ok.replace("**Reason**", "Why")}), 1)


if __name__ == "__main__":
    unittest.main()
