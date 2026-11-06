"""Structural check of OpenSpec files, for hosts without the OpenSpec CLI (the CI host has python3 but no Node).
It covers the rules `openspec validate --strict` enforces that matter most here; the CLI stays the reference
and runs wherever it is installed (scripts/check.sh)."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "openspec"
OPS = re.compile(r"^## (ADDED|MODIFIED|REMOVED|RENAMED) Requirements\s*$", re.M)


def check_spec(path: Path, errors: list[str], main: bool = False) -> None:
    """A change's delta spec needs ADDED/MODIFIED/REMOVED/RENAMED sections; a main spec (openspec/specs) needs a
    Purpose and a Requirements section, and no delta sections left over from a sync."""
    text = path.read_text(encoding="utf-8")
    if main:
        if not re.search(r"^## Purpose\s*$", text, re.M) or not re.search(r"^## Requirements\s*$", text, re.M):
            errors.append(f"{path}: a main spec needs '## Purpose' and '## Requirements'")
        if OPS.search(text):
            errors.append(f"{path}: delta section left in a main spec")
    elif not OPS.search(text):
        errors.append(f"{path}: no '## ADDED|MODIFIED|REMOVED|RENAMED Requirements' section")
    purpose = re.search(r"^## Purpose\s*\n(.*?)(?=^## )", text, re.M | re.S)
    if purpose and len(purpose.group(1).strip()) < 50:
        errors.append(f"{path}: Purpose shorter than 50 characters")
    removed = re.search(r"^## REMOVED Requirements\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if removed:  # a removed requirement needs a reason, not scenarios (as in `openspec validate`)
        for block in re.split(r"^### Requirement: ", removed.group(1), flags=re.M)[1:]:
            if "**Reason**" not in block:
                errors.append(f"{path}: removed requirement '{block.splitlines()[0].strip()}' has no **Reason**")
        text = text.replace(removed.group(0), "")
    blocks = re.split(r"^### Requirement: ", text, flags=re.M)[1:]
    for block in blocks:
        name = block.splitlines()[0].strip()
        body = block.split("\n#### Scenario:", 1)[0]
        description = "\n".join(body.splitlines()[1:]).strip()
        if "#### Scenario:" not in block:
            errors.append(f"{path}: requirement '{name}' has no '#### Scenario:'")
        if "**Reason**" not in block and not re.search(r"\b(SHALL|MUST)\b", description):
            errors.append(f"{path}: requirement '{name}' has no SHALL or MUST")
        if len(description) > 500:
            errors.append(f"{path}: requirement '{name}' description over 500 characters")


def check_tasks(path: Path, errors: list[str]) -> None:
    if not re.search(r"^- \[[ xX]\] \d+\.\d+ ", path.read_text(encoding="utf-8"), re.M):
        errors.append(f"{path}: no '- [ ] N.M' task checkboxes")


def main(root: Path = ROOT) -> int:
    errors: list[str] = []
    changes = [c for c in (root / "changes").glob("*") if c.is_dir() and c.name != "archive"]
    for change in changes:
        if not (change / "proposal.md").is_file():
            errors.append(f"{change}: no proposal.md")
        specs = list(change.glob("specs/**/spec.md"))
        if not specs and "skip_specs: true" not in (change / ".openspec.yaml").read_text(encoding="utf-8"):
            errors.append(f"{change}: no spec deltas and no skip_specs")
        for spec in specs:
            check_spec(spec, errors)
        if (change / "tasks.md").is_file():
            check_tasks(change / "tasks.md", errors)
    for spec in (root / "specs").glob("**/spec.md"):
        check_spec(spec, errors, main=True)
    for error in errors:
        print(f"ERROR {error}")
    print(f"openspec structure: {len(changes)} change(s), {len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
