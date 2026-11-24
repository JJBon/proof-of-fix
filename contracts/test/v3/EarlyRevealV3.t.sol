// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Panels} from "../../src/v3/Panels.sol";
import {Status, Kind, Submission, Panel} from "../../src/v3/PanelsBase.sol";
import {PanelsSetup} from "./helpers/PanelsSetup.sol";

/// proof-of-fix#311 (openspec/changes/proof-of-fix-311-early-reveal): a judging panel's reveal opens once every seat
/// has sealed, not at `sealBy`; a counted panel's, before its `sealBy`, also once every shadow drawn with it has sealed,
/// so no counted vote is public while a shadow can still seal; a waiting submission's shadows close at the counted draw
/// and those that hadn't sealed count no miss. Each scenario of the change's `challenges` delta is tested by its name,
/// on the suite's windows (production's by default: SEAL_WINDOW 2 h, REVEAL_WINDOW 1 h).
contract EarlyRevealV3Test is PanelsSetup {
    uint256 internal nextId = 5000;

    function setUp() public {
        _deployVersion(3, false);
        usd.mint(address(race), 10_000e6);
    }

    function _id() internal returns (uint256) {
        return nextId++;
    }

    function _candidates(uint256 n) internal returns (address[] memory cs) {
        cs = new address[](n);
        for (uint256 i; i < n; ++i) {
            cs[i] = _addCandidate(keccak256(abi.encode("cand", i)), _family(1 + (i % 6)), _tee(i), 1, 100e6);
        }
    }

    /// "Promptly": a twelfth of the seal window (10 minutes of production's 2 h; 10 s of the minute windows' 120 s).
    function _prompt() internal view returns (uint256) {
        return pn.SEAL_WINDOW() / 12;
    }

    function _revealBoth(uint256 pid, address key) internal {
        _reveal(pid, key);
        _receipt(pid, key);
    }

    // ---------- A panel reveals once every seat has committed ----------

    /// Scenario "Every judge commits promptly": three judges seal a twelfth of the seal window (10 minutes) after the
    /// draw and reveal at once; the verdict is counted, and its window started, then: about SEAL_WINDOW sooner than
    /// before #311.
    function test_everyJudgeCommitsPromptly() public {
        _network(3, 4, 3);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 100e6);
        uint256 drawnAt = vm.getBlockTimestamp();
        Panel memory p = pn.panel(pid);
        assertEq(p.k, 3);
        assertEq(pn.submission(id).shadowPid, 0, "no candidates: no shadows");
        address[] memory js = pn.judges(pid);
        vm.warp(drawnAt + _prompt());
        for (uint256 i; i < 3; ++i) {
            _seal(pid, js[i], i != 2);
        }
        for (uint256 i; i < 3; ++i) {
            _revealBoth(pid, js[i]);
        }
        Submission memory s = pn.submission(id);
        assertEq(uint256(s.status), uint256(Status.Window));
        assertTrue(s.pass); // 2 of 3
        assertEq(s.finalAt, drawnAt + _prompt() + pn.windowOf(3, s.level), "the window starts at the last reveal");
        assertLt(vm.getBlockTimestamp(), p.sealBy, "counted before the seal window would have closed");
        assertEq(p.sealBy - vm.getBlockTimestamp(), pn.SEAL_WINDOW() - _prompt(), "the time saved");
    }

    /// Scenario "A reveal before the panel is full": with two of three sealed, no reveal or receipt is taken.
    function test_aRevealBeforeThePanelIsFull() public {
        _network(3, 4, 3);
        uint256 pid = _openAndDraw(_id(), 100e6);
        address[] memory js = pn.judges(pid);
        _seal(pid, js[0], true);
        _seal(pid, js[1], false);
        _revealReverts(pid, js[0], Panels.TooEarly.selector);
        _receiptReverts(pid, js[1], Panels.TooEarly.selector);
        vm.warp(pn.panel(pid).sealBy + 1);
        _revealReverts(pid, js[0], Panels.TooEarly.selector); // after `sealBy` as well: a seat is still unsealed
    }

    /// Scenario "A silent judge on a panel that could reveal early": nobody reveals until the silent seat is replaced
    /// at `sealBy` and its replacement seals; then the reveal opens at once, before the replacement's new `sealBy`.
    function test_aSilentJudgeOnAPanelThatCouldRevealEarly() public {
        _network(3, 4, 3);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 100e6);
        address[] memory js = pn.judges(pid);
        _seal(pid, js[0], true);
        _seal(pid, js[1], true);
        _revealReverts(pid, js[0], Panels.TooEarly.selector);
        vm.warp(pn.panel(pid).sealBy + 1);
        pn.advance(pid); // the silence is a miss; the next in the sample takes the seat with fresh windows
        assertEq(reg.progress(js[2]).misses, 1);
        address repl = pn.judges(pid)[2];
        assertTrue(repl != js[2] && repl != address(0));
        _revealReverts(pid, js[0], Panels.TooEarly.selector); // the replacement hasn't sealed
        _seal(pid, repl, true);
        assertLt(vm.getBlockTimestamp(), pn.panel(pid).sealBy);
        for (uint256 i; i < 3; ++i) {
            _revealBoth(pid, pn.judges(pid)[i]);
        }
        assertTrue(pn.panel(pid).counted);
    }

    /// A mismatch at an early reveal: the whole bond, the seat refilled, and the reveal closed again until the
    /// replacement seals.
    function test_aMismatchAtAnEarlyRevealClosesTheRevealUntilTheReplacementSeals() public {
        _network(5, 6, 3);
        uint256 pid = _openAndDraw(_id(), 100e6);
        address[] memory js = pn.judges(pid); // k = 5 on six validators: one to replace a seat
        for (uint256 i; i < js.length; ++i) {
            _seal(pid, js[i], true);
        }
        address liar = js[1];
        bytes32 salt = _salt(pid, liar);
        bytes memory sig = _stmt(liar, pn.REVEAL_TAG(), pid, keccak256(abi.encode(false, uint8(0), salt)));
        pn.reveal(pid, liar, false, 0, salt, sig); // sealed true, reveals false, before `sealBy`
        assertEq(reg.validator(liar).slashed, FULL_BOND);
        address repl = pn.judges(pid)[1];
        assertTrue(repl != liar && repl != address(0));
        _revealReverts(pid, js[0], Panels.TooEarly.selector);
        _seal(pid, repl, false);
        for (uint256 i; i < js.length; ++i) {
            _revealBoth(pid, pn.judges(pid)[i]);
        }
        assertTrue(pn.panel(pid).counted);
        assertEq(pn.panel(pid).passes, js.length - 1);
    }

    /// Design E8: audit panels reveal at once too. A lone verdict's two audits (K1_AUDITS), each a one-seat panel, are
    /// revealed and counted right after their seals.
    function test_anAuditRevealsAtOnce() public {
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 40e6);
        _seal(pid, genesisKey, true);
        _revealBoth(pid, genesisKey); // k = 1: full at its one seal
        assertEq(uint256(pn.submission(id).status), uint256(Status.Held));
        _network(6, 7, 3);
        Submission memory s = pn.submission(id);
        for (uint256 t; t < 3 && !(s.auditDecided && s.auditsDrawn == s.auditsDue); ++t) {
            _rollPast(s.auditBlock);
            pn.drawAudits(id);
            s = pn.submission(id);
        }
        assertEq(s.auditsDrawn, 2);
        uint256 n = pn.panelCount();
        uint256 seen;
        for (uint256 q = pid + 1; q <= n; ++q) {
            Panel memory a = pn.panel(q);
            if (a.kind != Kind.Audit) continue;
            address auditor = pn.judges(q)[0];
            _seal(q, auditor, true);
            _revealBoth(q, auditor);
            assertTrue(pn.panel(q).counted);
            assertLt(vm.getBlockTimestamp(), a.sealBy);
            ++seen;
        }
        assertEq(seen, 2);
        assertEq(pn.submission(id).auditsDone, 2);
    }

    /// Design E8: a challenge panel reveals once its judges have all sealed, before its `sealBy`.
    function test_aChallengePanelRevealsAtOnce() public {
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 40e6);
        _seal(pid, genesisKey, true);
        _revealBoth(pid, genesisKey);
        _network(3, 7, 3);
        race.challenge(id, makeAddr("challenger"), keccak256("evidence"));
        _rollPast(pn.submission(id).challengeBlock);
        pn.drawChallenge(id);
        uint256 cpid = pn.submission(id).challengePid;
        assertGt(cpid, 0);
        address[] memory cj = pn.judges(cpid);
        for (uint256 i; i < cj.length; ++i) {
            _seal(cpid, cj[i], false);
        }
        for (uint256 i; i < cj.length; ++i) {
            _revealBoth(cpid, cj[i]);
        }
        assertLt(vm.getBlockTimestamp(), pn.panel(cpid).sealBy);
        assertTrue(pn.panel(cpid).counted);
        assertFalse(pn.submission(id).pass, "the challenge panel's majority decides");
        assertFalse(pn.submission(id).challengeOpen);
    }

    // ---------- No counted vote is public while a shadow can still commit ----------

    /// Scenario "A candidate copies the counted judges": while the shadow hasn't sealed, no counted reveal is taken
    /// before `sealBy`; once its window is over the counted judge reveals and the shadow's seal is refused.
    function test_aCandidateCopiesTheCountedJudges() public {
        address cand = _candidates(1)[0];
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 40e6);
        uint256 spid = pn.submission(id).shadowPid;
        assertEq(pn.judges(spid)[0], cand);
        _seal(pid, genesisKey, true);
        _revealReverts(pid, genesisKey, Panels.TooEarly.selector); // the shadow may still seal
        _receiptReverts(pid, genesisKey, Panels.TooEarly.selector);
        vm.warp(pn.panel(pid).sealBy + 1);
        _revealBoth(pid, genesisKey);
        bytes32 c = pn.commitmentOf(spid, cand, true, 0, _salt(spid, cand));
        bytes memory sig = _stmt(cand, pn.SEAL_TAG(), spid, c);
        vm.expectRevert(Panels.TooLate.selector);
        pn.seal(spid, cand, c, sig);
    }

    /// Scenario "A shadow front-runs a counted reveal": every counted seat sealed, a shadow not yet: no counted reveal
    /// is accepted, so there is none in the mempool to copy; once the shadow seals (its own vote, locked), the counted
    /// reveal opens, and the shadow can't seal again.
    function test_aShadowFrontRunsACountedReveal() public {
        _network(3, 4, 3);
        _candidates(2);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 100e6);
        uint256 spid = pn.submission(id).shadowPid;
        address[] memory js = pn.judges(pid);
        address[] memory ss = pn.judges(spid);
        assertEq(ss.length, 2); // SHADOW_PER_DRAW_SMALL while fewer than K_MAX are active
        for (uint256 i; i < 3; ++i) {
            _seal(pid, js[i], true);
        }
        _seal(spid, ss[0], true);
        _revealReverts(pid, js[0], Panels.TooEarly.selector); // one shadow still unsealed
        _seal(spid, ss[1], false);
        _revealBoth(pid, js[0]); // every shadow sealed: open, before `sealBy`
        bytes32 c = pn.commitmentOf(spid, ss[1], true, 0, _salt(spid, ss[1]));
        bytes memory sig = _stmt(ss[1], pn.SEAL_TAG(), spid, c);
        vm.expectRevert(Panels.AlreadySealed.selector); // a shadow's vote was locked before any counted reveal
        pn.seal(spid, ss[1], c, sig);
    }

    /// Scenario "Counted judges and shadows all commit promptly": counted within minutes; the shadows reveal after
    /// their own window and are scored as before.
    function test_countedJudgesAndShadowsAllCommitPromptly() public {
        _network(3, 4, 3);
        address[] memory cs = _candidates(2);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 100e6);
        uint256 spid = pn.submission(id).shadowPid;
        uint256 drawnAt = vm.getBlockTimestamp();
        vm.warp(drawnAt + _prompt());
        address[] memory ss = pn.judges(spid);
        for (uint256 i; i < ss.length; ++i) {
            _seal(spid, ss[i], true);
        }
        address[] memory js = pn.judges(pid);
        for (uint256 i; i < 3; ++i) {
            _seal(pid, js[i], true);
        }
        for (uint256 i; i < 3; ++i) {
            _revealBoth(pid, js[i]);
        }
        assertEq(uint256(pn.submission(id).status), uint256(Status.Window));
        assertLt(vm.getBlockTimestamp(), pn.panel(pid).sealBy);
        // the shadows reveal after their own `sealBy`, as before #311
        _revealReverts(spid, ss[0], Panels.TooEarly.selector);
        vm.warp(pn.panel(spid).sealBy + 1);
        for (uint256 i; i < ss.length; ++i) {
            _revealBoth(spid, ss[i]);
        }
        _finalize(id);
        assertTrue(pn.panel(spid).scored);
        for (uint256 i; i < cs.length; ++i) {
            assertEq(reg.progress(cs[i]).shadowDraws, 1);
            assertEq(reg.progress(cs[i]).shadowReveals, 1);
            assertEq(reg.progress(cs[i]).agreed, 1);
        }
    }

    /// Scenario "A silent shadow" (of the delta): the counted reveal waits for `sealBy`, today's timing, and the
    /// silent shadow counts a miss.
    function test_aSilentShadowHoldsTheRevealToSealBy() public {
        address cand = _candidates(1)[0];
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 40e6);
        uint256 spid = pn.submission(id).shadowPid;
        _seal(pid, genesisKey, true);
        vm.warp(pn.panel(pid).sealBy);
        _revealReverts(pid, genesisKey, Panels.TooEarly.selector); // the shadow's window's last second
        vm.warp(pn.panel(pid).sealBy + 1);
        _revealBoth(pid, genesisKey);
        vm.warp(pn.panel(spid).revealBy + 1);
        pn.settleShadows(spid);
        assertEq(reg.progress(cand).shadowDraws, 1);
        assertEq(reg.progress(cand).shadowReveals, 0);
    }

    /// A refill of the counted panel after `sealBy` restarts its windows but not its shadows': their window is over,
    /// so the counted reveal opens once the replacement seals, and no shadow can seal then.
    function test_aRefillAfterSealByDoesntReopenTheShadows() public {
        _network(5, 6, 3);
        address cand = _candidates(1)[0];
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 100e6);
        uint256 spid = pn.submission(id).shadowPid;
        assertTrue(_contains(pn.judges(spid), cand));
        address[] memory js = pn.judges(pid);
        uint256 last = js.length - 1;
        for (uint256 i; i < last; ++i) {
            _seal(pid, js[i], true);
        }
        vm.warp(pn.panel(pid).sealBy + 1);
        pn.advance(pid); // the last seat silent: replaced, the counted panel's windows restart
        address repl = pn.judges(pid)[last];
        _seal(pid, repl, true);
        assertLt(vm.getBlockTimestamp(), pn.panel(pid).sealBy);
        assertGt(vm.getBlockTimestamp(), pn.panel(spid).sealBy);
        _revealBoth(pid, js[0]); // the shadows' window is over: no shadow can still seal
        bytes32 c = pn.commitmentOf(spid, cand, true, 0, _salt(spid, cand));
        bytes memory sig = _stmt(cand, pn.SEAL_TAG(), spid, c);
        vm.expectRevert(Panels.TooLate.selector);
        pn.seal(spid, cand, c, sig);
    }

    // ---------- Waiting shadows ----------

    /// Scenarios "A waiting submission's shadows when the panel is drawn" and "A waiting shadow still checking when
    /// the panel is drawn": the counted draw closes the waiting shadows' seal window; the one that had sealed reveals
    /// and counts as before, the ones that hadn't are refused and count no draw.
    function test_aWaitingSubmissionsShadowsWhenThePanelIsDrawn() public {
        address[] memory cs = _candidates(3);
        uint256 id = _id();
        assertEq(_openAndDraw(id, 100e6), 0); // too few eligible for $100: it waits
        uint256 wpid = pn.submission(id).shadowPid;
        Panel memory w = pn.panel(wpid);
        assertEq(uint256(w.kind), uint256(Kind.Shadow));
        assertEq(w.ex, 0);
        assertEq(w.revealBy, w.sealBy + pn.REVEAL_WINDOW());
        address[] memory ws = pn.judges(wpid);
        _seal(wpid, ws[0], true);
        vm.warp(vm.getBlockTimestamp() + _prompt());
        _network(2, 3, 3); // the registry changes: drawn again
        pn.draw(id); // re-targets
        uint256 pid = _draw(id);
        assertGt(pid, 0);
        Panel memory w2 = pn.panel(wpid);
        assertEq(w2.sealBy, vm.getBlockTimestamp() - 1, "the waiting shadows' window closed at the counted draw");
        assertEq(w2.revealBy, w.revealBy, "their reveal deadline unchanged");
        bytes32 c = pn.commitmentOf(wpid, ws[1], true, 0, _salt(wpid, ws[1]));
        bytes memory sig = _stmt(ws[1], pn.SEAL_TAG(), wpid, c);
        vm.expectRevert(Panels.TooLate.selector);
        pn.seal(wpid, ws[1], c, sig);
        _revealBoth(wpid, ws[0]); // a waiting shadow that sealed reveals from the draw on (before: at its sealBy)
        vm.warp(w.revealBy + 1);
        pn.settleShadows(wpid);
        assertEq(reg.progress(ws[0]).shadowDraws, 1);
        assertEq(reg.progress(ws[0]).shadowReveals, 1);
        for (uint256 i = 1; i < 3; ++i) {
            assertEq(reg.progress(ws[i]).shadowDraws, 0, "cut short: no draw, no miss");
            assertEq(reg.progress(ws[i]).shadowReveals, 0);
        }
        assertTrue(_contains(cs, ws[1]));
    }

    /// A waiting shadow panel whose window had already ended before the counted draw isn't touched: its silent shadow
    /// counts a miss as before.
    function test_aWaitingShadowPastItsWindowIsUntouched() public {
        address[] memory cs = _candidates(3);
        uint256 id = _id();
        assertEq(_openAndDraw(id, 100e6), 0);
        uint256 wpid = pn.submission(id).shadowPid;
        Panel memory w = pn.panel(wpid);
        vm.warp(w.sealBy + 1);
        _network(2, 3, 3);
        pn.draw(id);
        assertGt(_draw(id), 0);
        assertEq(pn.panel(wpid).sealBy, w.sealBy);
        vm.warp(w.revealBy + 1);
        pn.settleShadows(wpid);
        for (uint256 i; i < 3; ++i) {
            assertEq(reg.progress(cs[i]).shadowDraws, 1, "a silent shadow with its whole window: a miss");
        }
    }
}
