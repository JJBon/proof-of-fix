"""The panel interface of the integration suite (proof-of-fix#140, task 5.0 of #132; design D18): the one place a
scenario reads who is drawn for a check and what decides it, so a scenario doesn't know whether it runs on v2's fixed
seats or on v3's open validators.

- v2 (`PanelV2`): `Verdicts.drawn` names 3 of the 7 seats by a shuffle; 2 agreeing signatures decide; a silent seat
  isn't replaced, so its usage report is missing.
- v3 (`PanelV3`): `Panels` seats a counted panel of k (1, 3, 5 or 7) from the open registry; the majority of the k
  on-chain reveals decides; a silent seat is replaced from the same sample, so the panel still carries k reports. A
  submission no panel can judge yet has no panel (`drawn` is empty) and waits.

tests/integration/suite.py (v2) and tests/integration/suite_v3.py (v3) both read the draw only through this."""

from __future__ import annotations

from oracle import v3


class PanelV2:
    version = 2

    def __init__(self, chain) -> None:
        self.chain = chain

    def drawn(self, s: int) -> list:
        """The judges whose verdicts count for submission `s`, in the contract's order."""
        sub = self.chain.submission(s)
        return self.chain.drawn(sub["seed"], sub["bounty"], s)[0]

    def size(self, s: int) -> int:
        return len(self.drawn(s))

    def decides(self, s: int) -> int:
        """How many agreeing verdicts decide the check."""
        return self.size(s) // 2 + 1

    def reports(self, s: int, silent: int = 0) -> int:
        """The usage reports a decided check carries when `silent` of its drawn judges never ran: v2 doesn't replace
        a silent seat."""
        return self.size(s) - silent

    def replaces_silent(self) -> bool:
        return False


class PanelV3:
    version = 3

    def __init__(self, chain) -> None:
        self.chain = chain

    def pid(self, s: int) -> int:
        """The counted panel of submission `s` (0: none seated, it waits)."""
        return self.chain.verdict(s)["pid"]

    def drawn(self, s: int) -> list:
        pid = self.pid(s)
        return [k for k in self.chain.judges(pid) if k] if pid else []

    def size(self, s: int) -> int:
        return self.chain.verdict(s)["k"]

    def decides(self, s: int) -> int:
        return self.size(s) // 2 + 1

    def reports(self, s: int, silent: int = 0) -> int:
        """A silent seat is replaced from the same sample (Panels.advance), so the panel still carries k reports."""
        return self.size(s)

    def replaces_silent(self) -> bool:
        return True

    def shadows(self, s: int) -> list:
        """The latest shadow panel's judges for `s` (candidates, unpaid and uncounted)."""
        sp = self.chain.verdict(s)["shadowPid"]
        return [k for k in self.chain.judges(sp) if k] if sp else []

    def waiting(self, s: int) -> bool:
        return self.chain.verdict(s)["status"] == v3.WAITING
