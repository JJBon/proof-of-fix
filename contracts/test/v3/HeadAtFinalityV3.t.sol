// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Panels} from "../../src/v3/Panels.sol";
import {Status} from "../../src/v3/PanelsBase.sol";
import {RaceV3Base} from "../../src/v3/RaceV3Base.sol";
import {Heads} from "../../src/v2/Heads.sol";
import {RaceV3Setup} from "./helpers/RaceV3Setup.sol";
import {TEST_REPO, TEST_GENESIS_HEAD} from "./helpers/SuiteWindows.sol";

/// proof-of-fix#251, contract batch 2, task 3.5 (design L9; specs/canonical-head): the head moves only once the
/// winning verdict is final, by `merge`, which anyone may call; the claim doesn't move it; a stale base is refused at
/// the merge. Each contract scenario of the spec is tested under its name, on the real Panels, FeesV3 and RaceV3.
contract HeadAtFinalityV3Test is RaceV3Setup {
    bytes32 constant FIX = keccak256("fix");
    bytes32 constant FIX2 = keccak256("fix 2");
    uint256 internal _bobsCover;

    function setUp() public {
        _deployRace(3);
    }

    function _heads() internal view returns (Heads h) {
        (,,,, h,,) = rc.contracts();
    }

    /// A won and claimed fix of a fresh bounty, judged by a panel of three: (bounty, submission).
    function _claimed(address solver, bytes32 fix) internal returns (uint256 b, uint256 id) {
        b = _openBounty();
        id = _commit(solver, b, fix);
        _judgeCheck(id, true);
        rc.claim(b, fix, _head(), "salt");
    }

    // ---------- The head moves only when the winning verdict is final ----------

    /// Scenario "A pass that stands": the solver claims, the window ends with no challenge upheld, and anyone may then
    /// move the head to the fix; the head records the bounty, the submission and the verdict.
    function test_aPassThatStands() public {
        (uint256 b, uint256 id) = _claimed(solver1, FIX);
        assertEq(_heads().head(TEST_REPO).commit, TEST_GENESIS_HEAD); // claiming doesn't move it
        vm.expectRevert(RaceV3Base.NotYet.selector); // its window is running
        rc.merge(b);
        _final(id);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Final));
        vm.prank(makeAddr("anyone"));
        rc.merge(b);
        Heads.Head memory h = _heads().head(TEST_REPO);
        assertEq(h.commit, FIX);
        assertEq(h.bounty, b);
        assertEq(h.submission, id);
        assertEq(h.verdict, keccak256(abi.encode(address(pn), id)));
        assertTrue(rc.award(b, 1).merged);
        assertTrue(rc.paid(FIX));
        vm.expectRevert(RaceV3Base.Refused.selector); // once
        rc.merge(b);
    }

    /// Scenario "A pass reversed in its window": a passed and claimed fix is reversed by a challenge before its verdict
    /// is final; the head never moves to it, the award is clawed back and the bounty reopens (#132).
    function test_aPassReversedInItsWindow() public {
        (uint256 b, uint256 id) = _claimed(solver1, FIX);
        _network(5, FAMILIES, 3);
        uint256 cpid = _challengeReversing(id);
        rc.settleChallenge(id, cpid);
        assertTrue(rc.award(b, 1).closed);
        assertEq(rc.award(b, 1).earned, 0);
        assertFalse(rc.award(b, 1).merged);
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Open));
        vm.expectRevert(abi.encodeWithSelector(RaceV3Base.WrongState.selector, b, RaceV3Base.State.Open));
        rc.merge(b);
        // its verdict, now a fail, becomes final: still nothing moves the head to it
        _runAudits(id, true);
        vm.warp(pn.submission(id).finalAt);
        pn.finalize(id);
        assertFalse(pn.submission(id).pass);
        vm.expectRevert(abi.encodeWithSelector(RaceV3Base.WrongState.selector, b, RaceV3Base.State.Open));
        rc.merge(b);
        assertEq(_heads().head(TEST_REPO).commit, TEST_GENESIS_HEAD);
        assertFalse(rc.paid(FIX));
        _assertBooks();
    }

    /// A pass reversed before the claim: the bounty reopens and nothing can be claimed or merged.
    function test_aPassReversedBeforeItsClaim() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        _judgeCheck(id, true);
        _network(5, FAMILIES, 3);
        rc.settleChallenge(id, _challengeReversing(id));
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Open));
        vm.expectRevert(abi.encodeWithSelector(RaceV3Base.WrongState.selector, b, RaceV3Base.State.Open));
        rc.claim(b, FIX, TEST_GENESIS_HEAD, "salt");
        assertEq(_heads().head(TEST_REPO).commit, TEST_GENESIS_HEAD);
    }

    /// Nothing is paid before the merge: an award counts its instalments from the verdict's finality, but pays them
    /// once the head moved; then the ones earned since the finality at once.
    function test_instalmentsWaitForTheMerge() public {
        (uint256 b, uint256 id) = _claimed(solver1, FIX);
        _final(id);
        _toDay(rc.day() + 14);
        assertEq(rc.earned(b, 1), 0);
        rc.claimInstalments(b, 1);
        assertEq(rc.instalmentsPaid(b, 1), 0);
        assertFalse(rc.settle(b));
        rc.merge(b);
        assertGe(rc.earned(b, 1), 1);
        rc.claimInstalments(b, 1);
        assertGt(rc.instalmentsPaid(b, 1), 0);
        _assertBooks();
    }

    // ---------- A stale base is refused at the move ----------

    /// Scenario "Two fixes final in the same window": two bounties' fixes on the same head both become final, and the
    /// first one moves the head; the second move reverts as stale, the winner keeps its place until mergeDays after
    /// its finality, and then its solver may submit the fix rebased on the new head. (Batch 1 refused the second
    /// claim; now both claim, and the second is refused at its merge.)
    function test_twoFixesFinalInTheSameWindow() public {
        (uint256 b1, uint256 s1) = _claimed(solver1, FIX);
        (uint256 b2, uint256 s2) = _claimed(solver2, FIX2);
        assertEq(rc.submission(s2).base, TEST_GENESIS_HEAD);
        _final(s1);
        _final(s2);
        rc.merge(b1);
        assertEq(_heads().head(TEST_REPO).commit, FIX);
        vm.expectRevert(abi.encodeWithSelector(Heads.StaleVerdict.selector, TEST_REPO, TEST_GENESIS_HEAD, FIX));
        rc.merge(b2);
        assertEq(uint256(rc.bounty(b2).state), uint256(RaceV3Base.State.Merged)); // it keeps its place
        assertEq(rc.earned(b2, 1), 0); // and earns nothing unmerged
        (,,,,,, uint256 st) = rc.contracts();
        uint256 deadline = (pn.submission(s2).finalAt - st) / 1 days + _config().mergeDays;
        _toDay(deadline);
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.mergeExpired(b2);
        _toDay(deadline + 1);
        rc.mergeExpired(b2);
        assertEq(uint256(rc.bounty(b2).state), uint256(RaceV3Base.State.Open));
        assertTrue(rc.award(b2, 1).closed);
        assertEq(rc.award(b2, 1).earned, 0);
        // the fix rebased on the new head wins again, and merges
        bytes32 rebased = keccak256("fix 2 rebased");
        uint256 s3 = _commit(solver2, b2, rebased); // committed on the head now: FIX
        _judgeCheck(s3, true);
        rc.claim(b2, rebased, FIX, "salt");
        _finalAndMerge(b2, s3);
        assertEq(_heads().head(TEST_REPO).commit, rebased);
        assertEq(_heads().head(TEST_REPO).submission, s3);
        _assertBooks();
    }

    /// A claimed fix nobody merges by mergeDays after its finality is closed with nothing earned (Solved = merged).
    function test_aFinalFixNotMergedInTimeReopens() public {
        (uint256 b, uint256 id) = _claimed(solver1, FIX);
        vm.expectRevert(RaceV3Base.NotYet.selector); // not final yet
        rc.mergeExpired(b);
        _final(id);
        _toDay(rc.day() + _config().mergeDays + 2);
        rc.mergeExpired(b);
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Open));
        assertEq(_heads().head(TEST_REPO).commit, TEST_GENESIS_HEAD);
        vm.expectRevert(abi.encodeWithSelector(RaceV3Base.WrongState.selector, b, RaceV3Base.State.Open));
        rc.merge(b);
    }

    /// A merged fix can't be merged again, nor expire.
    function test_aMergedFixDoesntExpire() public {
        (uint256 b, uint256 id) = _claimed(solver1, FIX);
        _finalAndMerge(b, id);
        _toDay(rc.day() + 60);
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.mergeExpired(b);
        assertTrue(rc.settle(b));
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Paid));
    }

    /// Merge needs a claim: a won fix not claimed can't be merged.
    function test_mergeNeedsTheClaim() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        _check(id, true);
        vm.expectRevert(abi.encodeWithSelector(RaceV3Base.WrongState.selector, b, RaceV3Base.State.Won));
        rc.merge(b);
    }

    // ---------- helpers ----------

    /// Bob challenges check `id`'s pass; a fresh panel of 5 fails the fix. Returns the challenge panel.
    function _challengeReversing(uint256 id) internal returns (uint256 cpid) {
        _fund(bob, 1_000 * C);
        vm.prank(bob);
        rc.challenge(id, keccak256("evidence"));
        _rollPast(pn.submission(id).challengeBlock);
        pn.drawChallenge(id);
        cpid = pn.submission(id).challengePid;
        _judge(cpid, _votes(pn.panel(cpid).k, 0));
        _reportAll(cpid);
    }
}
