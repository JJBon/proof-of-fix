"""The verdict on the Radicle issue (proof-of-fix#251, v3.1 polish VP18; the live smoke test's S4: the verdict was
visible only on-chain).

After a verdict is counted, the node of the counted panel's first revealed seat comments a short receipt on the
bounty's (or the registration's) Radicle issue, through its own Radicle node:

- the outcome (pass or fail), k and the passes, the verdict's state (held, window, final) with the times that apply,
  the counting transaction (Panels' `Counted` event) and a marker line `pof-verdict: <chainId>/<race>/<check>`, so the
  comment is made once: a node that finds the marker on the issue skips it, and a restart doesn't repeat it;
- the reason, this node's judge's one-line answer, only where it reveals no sealed evidence (the `checking` rule
  "Evidence sealed until the bounty settles"): for a registration check whose registration isn't `hidden`, in the same
  comment; for a fix check, once its bounty is paid, refunded or closed unsolved, as a second comment (marker
  `pof-verdict-reason: …`); never for a `hidden` registration (hidden tests) or a fix on one.

Only a node with a Radicle node and its issues comments (ORACLE_FIX_SOURCE=radicle: oracle/radicle_v3.py `attach`); the
keeper-only node never does. `step` runs once a pass after the seat steps and never raises: a failure (the Radicle node
or the chain not answering) is logged and retried with backoff, 30 s doubling to an hour, per panel. What it watches is
kept in the node's rounds store (`verdict-comments`), so a restarted node goes on where it stopped."""

from __future__ import annotations

import datetime
import time

from . import v3

MARKER, REASON_MARKER = "pof-verdict", "pof-verdict-reason"
BACKOFF_BASE_S, BACKOFF_MAX_S = 30.0, 3600.0  # the keeper's backoff (VP6)
CHECK_EVERY_S = 60.0  # between two reads of a watched panel that isn't counted yet
SETTLE_EVERY_S = 600.0  # between two reads of a fix check's bounty that hasn't settled yet
REASON_CHARS = 400
STATE = "verdict-comments"  # the name of its state in the node's rounds store
SETTLED = (v3.PAID, v3.REFUNDED, v3.UNSOLVED)  # a bounty paid or closed unsolved: its evidence is no longer sealed


def reason_of(response: str) -> str:
    """The judge's one-line reason from its raw answer ("" when it gave none), whitespace folded, at most
    REASON_CHARS characters."""
    from .judge import _json_object

    v = _json_object(response or "")
    line = " ".join(str((v or {}).get("reason") or "").split()) if isinstance(v, dict) else ""
    return line if len(line) <= REASON_CHARS else line[:REASON_CHARS - 1] + "…"


def marker_line(chain_id: int, race: str, check: int, kind: str = MARKER) -> str:
    return f"{kind}: {chain_id}/{race.lower()}/{check}"


def has_marker(issue: dict, line: str) -> bool:
    return any(line == x.strip() for c in issue.get("comments") or [] for x in c.get("body", "").splitlines())


def _when(ts: int) -> str:
    return datetime.datetime.fromtimestamp(int(ts), datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def state_text(v: dict) -> str:
    st = v["status"]
    if st == v3.HELD:
        return "Held: its challenge window starts once enough validators are active for the hold"
    if st == v3.WINDOW:
        return f"Window: final at {_when(v['finalAt'])} unless challenged"
    if st == v3.FINAL:
        return f"Final since {_when(v['finalAt'])}"
    return v3.STATUS[st] if 0 <= st < len(v3.STATUS) else str(st)


class VerdictComments:
    """`radicle`: this node's oracle/radicle.py `Radicle`; `issues`: its radicle_v3.RadicleIssues; `store`: the node's
    rounds store (oracle/rounds.py), or None to keep the state in memory only."""

    def __init__(self, radicle, issues, log=print, clock=time.time, store=None) -> None:
        self.radicle, self.issues, self.log, self.clock, self.store = radicle, issues, log, clock, store
        self.watch: dict | None = None  # str(pid) -> what this node knows of its counted seat, and where it got

    # ---------- the state ----------

    def _load(self) -> None:
        if self.watch is None:
            saved = self.store.get(STATE) if self.store is not None else None
            self.watch = dict((saved or {}).get("watch") or {})

    def _save(self) -> None:
        if self.store is not None:
            self.store.put(STATE, {"watch": self.watch})

    def remember(self, node, r) -> None:
        """A seat this node is about to let go of (`NodeV3._finish`): kept if it was a judged counted seat, so a panel
        whose seal, reveal and report all fall within one pass (#311's early reveal) still gets its comment."""
        try:
            self._load()
            if self._watch_round(node, r):
                self._save()
        except Exception as err:  # noqa: BLE001 - never in the way of a seat step: the next pass's collect retries
            self.log(f"verdict comments: panel {r.pid} not kept ({err})")

    def _watch_round(self, node, r) -> bool:
        if r.kind != v3.COUNTED or not r.judged or str(r.pid) in self.watch:
            return False
        self.watch[str(r.pid)] = {"s": r.submission, "vote": bool(r.vote), "reason": r.reason or "",
                                  "stage": "count", "n": 0, "at": 0, "from": node.chain.block()}
        return True

    def _collect(self, node) -> bool:
        """The counted seats this node has judged, from its rounds; the done ones it no longer holds are forgotten."""
        changed = False
        held = {str(r.pid) for r in node.seats.values()}
        for r in list(node.seats.values()):
            changed |= self._watch_round(node, r)
        for key in [k for k, e in self.watch.items() if e["stage"] == "done" and k not in held]:
            del self.watch[key]
            changed = True
        return changed

    # ---------- a pass ----------

    def step(self, node, now: int | None = None) -> bool:
        """One pass: each watched panel that is due. Never raises (it must not block a seat step)."""
        progress = changed = False
        try:
            self._load()
            changed = self._collect(node)
        except Exception as err:  # noqa: BLE001 - the chain or the store: next pass
            node._say(("verdict comments", str(err)), f"verdict comments: {err}; trying again")
            return False
        t = self.clock()
        for key, e in sorted(self.watch.items(), key=lambda kv: int(kv[0])):
            if e["stage"] == "done" or e.get("at", 0) > t:
                continue
            changed = True
            try:
                progress |= self._one(node, int(key), e)
                e["n"] = 0
            except Exception as err:  # noqa: BLE001 - Radicle or the chain not answering: backoff, never a stop
                e["n"] = e.get("n", 0) + 1
                wait = min(BACKOFF_BASE_S * 2 ** (e["n"] - 1), BACKOFF_MAX_S)
                e["at"] = t + wait
                self.log(f"panel {key}: the verdict comment on check {e['s']} failed ({err}); trying again in "
                         f"{wait:.0f}s")
        if changed:
            try:
                self._save()
            except OSError as err:
                node._say(("verdict comments save", str(err)), f"verdict comments: not saved ({err})")
        return progress

    def _one(self, node, pid: int, e: dict) -> bool:
        c = node.chain
        if e["stage"] == "count":
            p = c.panel(pid)
            if not p["counted"]:
                if p["closed"]:
                    e["stage"] = "done"  # released, never counted: no verdict to tell
                else:
                    e["at"] = self.clock() + CHECK_EVERY_S
                return False
            slot = next((i for i in range(p["k"]) if c.seat(pid, i)["revealed"]), None)
            judges = c.judges(pid)
            if slot is None or not judges[slot] or judges[slot].lower() != node.address.lower():
                e["stage"] = "done"  # another seat's node tells it
                return False
            sub = c.submission(e["s"])
            onchain = c.issue(c.issue_of(sub))
            e.update(slot=slot, bounty=sub["bounty"], hidden=bool(onchain.get("hidden")))
            issue = self._issue(node, sub, onchain)
            if issue is None:
                e["stage"] = "done"
                return False
            e["issue"] = issue["id"]
            line = marker_line(c.chain_id(), c.race, e["s"])
            reason_now = sub["bounty"] == 0 and not e["hidden"]
            if has_marker(issue, line):
                self.log(f"check {e['s']}: its verdict is already on Radicle issue {issue['id'][:7]}; not again")
            else:
                self.radicle.comment(issue["id"], self._receipt(node, pid, p, e, line, reason_now))
                self.log(f"check {e['s']}: its verdict commented on Radicle issue {issue['id'][:7]}")
            e["stage"] = "reason" if sub["bounty"] and not e["hidden"] and e["reason"] else "done"
            e["at"] = 0
            return True
        # "reason": a fix check's reason, once its bounty settles
        bt = c.bounty(e["bounty"])
        if bt["state"] not in SETTLED:
            e["at"] = self.clock() + SETTLE_EVERY_S
            return False
        issues, _ = self.issues.issues()
        issue = next((i for i in issues if i["id"] == e["issue"]), None)
        if issue is None:
            raise LookupError(f"Radicle issue {e['issue'][:7]} isn't on this node's copy")
        line = marker_line(c.chain_id(), c.race, e["s"], REASON_MARKER)
        if not has_marker(issue, line):
            state = v3.RACE_STATES[bt["state"]].lower()
            self.radicle.comment(issue["id"], "\n".join([
                f"proof-of-fix verdict, the reason: bounty {e['bounty']} is {state}, so check {e['s']}'s evidence is "
                f"no longer sealed.",
                self._reason_line(e), "", line]))
            self.log(f"check {e['s']}: its reason commented on Radicle issue {issue['id'][:7]} (bounty {state})")
        e["stage"] = "done"
        return True

    def _issue(self, node, sub: dict, onchain: dict):
        """The Radicle issue that validly claims the check's registration (the registration's, or the bounty's), as
        radicle_v3.find_claim finds it on this node's copy; None (logged) when none does."""
        from . import radicle_v3 as RV

        c = node.chain
        issues, sync_error = self.issues.issues()
        if sync_error:
            node._say(("rad sync verdict", sync_error), f"verdict comments: Radicle: {sync_error}; reading this "
                                                        f"node's own copy")
        n = c.issue_of(sub)
        want = {"id": n, "reporter": onchain["reporter"], "repo": onchain["repo"]}
        issue, _, _, problems = RV.find_claim(issues, want, node._repo_id(), c.chain_id(), c.race)
        if issue is None:
            self.log(f"registration {n}: no Radicle issue on this node's copy claims it; its check's verdict isn't "
                     f"commented" + (f" ({'; '.join(problems[:2])})" if problems else ""))
        return issue

    def _reason_line(self, e: dict) -> str:
        return f"Reason (seat {e.get('slot', 0)}'s judge, which voted {'pass' if e['vote'] else 'fail'}): {e['reason']}"

    def _receipt(self, node, pid: int, p: dict, e: dict, line: str, reason_now: bool) -> str:
        c, s = node.chain, e["s"]
        v = c.verdict(s)
        passed = bool(v["pass"]) if v.get("pid") == pid else 2 * p["passes"] > p["k"]
        what = f"registration check {s}" if not e["bounty"] else f"check {s} (a fix on bounty {e['bounty']})"
        counted = c.counted_tx(s, pid, e.get("from") or 0) if hasattr(c, "counted_tx") else None
        if counted is None and e.get("from") and hasattr(c, "counted_tx"):
            counted = c.counted_tx(s, pid, 0)  # a restarted node: counted before it watched
        tx = f"Counted in transaction {counted['tx']} (block {counted['block']})." if counted else \
            "Counting transaction: not found by this node."
        lines = [f"proof-of-fix verdict: {what} {'passed' if passed else 'failed'}, {p['passes']} of {p['k']} judges "
                 f"for a pass (k = {p['k']}).",
                 f"State: {state_text(v)}.", tx,
                 f"Chain {c.chain_id()}, RaceV3 {c.race}, panel {pid}; told by {node.address}, its seat {e['slot']}."]
        if reason_now and e["reason"]:
            lines.append(self._reason_line(e))
        elif e["bounty"] and not e["hidden"]:
            lines.append("The reason follows once the bounty is paid or closed: until then the evidence stays sealed.")
        return "\n".join(lines + ["", line])
