"""The simulated ledger (specs/ledger): pseudonymous accounts, append-only entries, exact conservation.

Every balance change is an entry that moves micro-credits from one account to another. Credits enter only by
issuance (release funding or an actor's endowment), so the sum of all balances always equals the total issued.
An entry that would take an account below zero is refused and nothing is recorded. A wrong entry is never edited:
it is reversed by a new entry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

REASONS = frozenset({"stake", "escrow", "reward", "slash", "fee", "payout", "claim", "refund", "bond", "reversal"})
ISSUE_REASONS = frozenset({"release_funding", "endowment"})
_KIND = re.compile(r"^[a-z][a-z_]{0,31}$")


class LedgerError(ValueError):
    """A refused entry; the ledger is unchanged."""


@dataclass(frozen=True)
class Entry:
    seq: int
    time: int  # simulation day
    reason: str
    source: str | None  # None for issuance
    target: str
    amount: int  # micro-credits, > 0
    ref: str  # the contribution, challenge or release it belongs to, e.g. "contribution:12"
    reverses: int | None = None  # seq of the entry this one reverses


@dataclass(frozen=True)
class Event:
    """A record that moves no money: a parameter change, the evidence behind a claim."""

    seq: int
    time: int
    kind: str
    ref: str
    detail: str


class Ledger:
    def __init__(self) -> None:
        self._balances: dict[str, int] = {}
        self._entries: list[Entry] = []
        self._events: list[Event] = []
        self._kinds: dict[str, int] = {}
        self._reversed: set[int] = set()
        self.total_issued = 0

    # ---------- accounts ----------

    def open(self, kind: str) -> str:
        """A new account of a role (actor, stake, escrow, treasury, insurance, ...). Its id is generated
        (`<kind>-<n>`); callers can't name an account, so no real name, handle or address can enter the ledger."""
        if not _KIND.match(kind):
            raise LedgerError(f"account kind must be a lowercase role name, got {kind!r}")
        n = self._kinds.get(kind, 0) + 1
        self._kinds[kind] = n
        account = f"{kind}-{n:05d}"
        self._balances[account] = 0
        return account

    def balance(self, account: str) -> int:
        self._known(account)
        return self._balances[account]

    def accounts(self) -> tuple[str, ...]:
        return tuple(self._balances)

    # ---------- entries ----------

    def issue(self, target: str, amount: int, reason: str, ref: str, time: int) -> Entry:
        """Credits entering the system: release funding or an actor's endowment, the only two sources."""
        if reason not in ISSUE_REASONS:
            raise LedgerError(f"credits are issued only as {sorted(ISSUE_REASONS)}, got {reason!r}")
        self._known(target)
        self._positive(amount)
        entry = self._append(time, reason, None, target, amount, ref)
        self.total_issued += amount
        return entry

    def transfer(self, source: str, target: str, amount: int, reason: str, ref: str, time: int) -> Entry:
        """Move amount from source to target. Refused, with nothing recorded, if source would go below zero."""
        if reason not in REASONS or reason == "reversal":
            raise LedgerError(f"unknown reason {reason!r}")
        self._known(source)
        self._known(target)
        self._positive(amount)
        if source == target:
            raise LedgerError("source and target are the same account")
        if self._balances[source] < amount:
            raise LedgerError(f"{source} has {self._balances[source]}, can't move {amount}")
        return self._append(time, reason, source, target, amount, ref)

    def reverse(self, seq: int, time: int) -> Entry:
        """Undo a transfer with a new entry the other way; the original stays visible."""
        if not 0 <= seq < len(self._entries):
            raise LedgerError(f"no entry {seq}")
        original = self._entries[seq]
        if original.source is None:
            raise LedgerError("issuance can't be reversed")
        if original.reason == "reversal" or seq in self._reversed:
            raise LedgerError(f"entry {seq} is a reversal or is already reversed")
        if self._balances[original.target] < original.amount:
            raise LedgerError(f"{original.target} no longer holds {original.amount}")
        self._reversed.add(seq)
        return self._append(time, "reversal", original.target, original.source, original.amount, original.ref, seq)

    @property
    def entries(self) -> tuple[Entry, ...]:
        return tuple(self._entries)

    def record(self, time: int, kind: str, ref: str, detail: str) -> Event:
        """Append an event (append-only, like entries)."""
        event = Event(len(self._events), int(time), kind, str(ref), str(detail))
        self._events.append(event)
        return event

    @property
    def events(self) -> tuple[Event, ...]:
        return tuple(self._events)

    def entries_for(self, ref: str) -> tuple[Entry, ...]:
        """Every entry about one contribution, challenge or release, in order (auditable settlements)."""
        return tuple(e for e in self._entries if e.ref == ref)

    @staticmethod
    def net(entries: tuple[Entry, ...] | list[Entry]) -> dict[str, int]:
        """Each account's net change over the given entries: recomputes a settlement from its entries alone."""
        out: dict[str, int] = {}
        for e in entries:
            if e.source is not None:
                out[e.source] = out.get(e.source, 0) - e.amount
            out[e.target] = out.get(e.target, 0) + e.amount
        return out

    def conserved(self) -> bool:
        """The sum of all balances equals the credits issued."""
        return sum(self._balances.values()) == self.total_issued

    # ---------- internals ----------

    def _append(self, time, reason, source, target, amount, ref, reverses=None) -> Entry:
        entry = Entry(len(self._entries), int(time), reason, source, target, int(amount), str(ref), reverses)
        if source is not None:
            self._balances[source] -= amount
        self._balances[target] += amount
        self._entries.append(entry)
        return entry

    def _known(self, account: str) -> None:
        if account not in self._balances:
            raise LedgerError(f"unknown account {account!r}")

    @staticmethod
    def _positive(amount: int) -> None:
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise LedgerError(f"amount must be a positive integer of micro-credits, got {amount!r}")
