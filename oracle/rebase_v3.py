"""A rebase check as a validator's node judges and keeps it (proof-of-fix#310, rebase in place; design RB3, RB8).

v3.1's race takes a claimed, unmerged fix whose base went stale rebased onto the head (`RaceV3.rebase`): a new check of
the rebased commit (`Submission.rebaseOf` names the original), judged by a fresh panel like any fix. The node finds its
patch revision as it finds any fix's (the claim lines with a salt; a stale base refused), and runs its tests the same
way: protected paths from its base, which is the new head, twice. What differs is the judge's case: it carries the
approved fix's diff (the original's commit and base, revealed at its claim), the rebased diff and their `git
range-diff`, and one more rubric question, whether the rebase is the approved fix adapted to the new base and nothing
else. A "no" fails it whatever the tests say (`checking`, "The judges compare a rebase with the approved fix").

Kept apart from oracle/node_v3.py so that the rebase's additions to the node stay in one place."""

from __future__ import annotations

from . import evidence
from .fetch import DEFAULT_DIFF_BYTES

# The rubric's question for a rebase, in the node's own words (a note: outside the untrusted markers).
RUBRIC = ("This check is a rebase in place: the bounty's winning fix was approved on an older head, and its rebase "
          "onto the current head is judged here before the head may move to it. Besides the issue, answer one more "
          "question: is the rebased diff the approved fix adapted to the new base, with no unrelated change? If it "
          "adds, removes or changes anything beyond what adapting the approved fix to the new base needs, it does not "
          "solve the issue as approved: answer solves = false, even if the tests pass.")
APPROVED_HEADING = "=== The approved fix's diff (the original submission, on its own base) ==="
RANGE_HEADING = "=== git range-diff: the approved fix (left) against this rebase (right) ==="


def sha_of(word) -> str:
    """A commit as the race keeps it (bytes32, or its 0x hex) back to its hex id."""
    raw = bytes.fromhex(word[2:]) if isinstance(word, str) else bytes(word)
    return raw[:20].hex() if raw[20:] == b"\0" * 12 else raw.hex()


def case(base_case: dict, original: int, approved: str, range_diff: str, old: tuple, new: tuple) -> dict:
    """The judge's case for a rebase check: `base_case` (the rebased fix's case, as for any fix) with the approved
    diff and the range-diff after its own diff, and the node's notes saying what is where and the rubric's question.
    `old` and `new`: (base, fix) of the approved fix and of the rebase, as hex commit ids."""
    diff = "\n".join((base_case.get("diff", ""), "", APPROVED_HEADING, approved, "", RANGE_HEADING, range_diff))
    notes = (*base_case.get("notes", ()),
             f"This node's note, not the fix author's: this is a rebase of submission {original}'s approved fix "
             f"(commit {old[1]} on base {old[0]}) onto the head {new[0]} as commit {new[1]}. After the rebased "
             f"diff, the diff section shows the approved fix's diff ({len(approved.encode()):,} bytes) and the "
             f"range-diff of the two ({len(range_diff.encode()):,} bytes), both computed by this node from commits it "
             f"fetched itself.",
             RUBRIC)
    return {**base_case, "diff": diff, "notes": notes}


def judge_case(node, sub: dict, pull: dict, base_case: dict, refusal: str) -> tuple:
    """(the case, why no judge can read this fix, or "") for rebase check `sub`, from the case `node._case` built for
    its rebased commit. A judge that reads only the test run (the fake) gets the case unchanged; otherwise the node
    fetches the approved fix's diff and the range-diff itself (oracle/fetch.py, verified commits). Raises NotReady
    while they can't be fetched just now."""
    if refusal or not getattr(node.judge, "reads_evidence", True):
        return base_case, refusal
    original = node.chain.submission(sub["rebaseOf"])
    old = (sha_of(original["base"]), sha_of(original["fix"]))
    new = (pull.get("base_sha", ""), pull["head_sha"])
    fetcher = getattr(node, "fetcher", None)
    if fetcher is None:
        raise evidence.NotReady("this node doesn't fetch (ORACLE_FETCH=0), so it has no approved diff for a rebase")
    approved = fetcher.diff(node.src_root, old[1], bytes.fromhex(old[1]).ljust(32, b"\0"), old[0],
                            DEFAULT_DIFF_BYTES)
    if approved is None:
        raise evidence.NotReady(f"no diff of the approved fix {old[1][:12]} yet")
    if approved.refusal:
        return base_case, f"the approved fix's diff: {approved.refusal}"
    ranged = fetcher.range_diff(node.src_root, old[0], old[1], new[0], new[1], DEFAULT_DIFF_BYTES)
    if ranged is None:
        raise evidence.NotReady(f"no range-diff of {old[1][:12]} and {new[1][:12]} yet")
    if ranged.refusal:
        return base_case, f"the rebase's range-diff: {ranged.refusal}"
    return case(base_case, sub["rebaseOf"], approved.text, ranged.text, old, new), ""


def merge_target(chain, b: int) -> tuple:
    """(the check whose tree `merge(b)` would move the head to, its record) for bounty `b`'s current award, as
    RaceV3.merge picks it: its latest rebase check while that one stands as a pass, else the original. (0, None) when
    the bounty has no claimed, unmerged award."""
    bt = chain.bounty(b)
    if bt["state"] != 3 or not bt["epoch"]:  # v3.CLAIMED
        return 0, None
    a = chain.award(b, bt["epoch"])
    if a["merged"] or a["closed"]:
        return 0, None
    r = a.get("rebase", 0)
    if r and chain.verdict(r)["pass"]:
        return r, a
    return a["sub"], a
