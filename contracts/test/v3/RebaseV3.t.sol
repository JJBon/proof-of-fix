// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Panel, Status} from "../../src/v3/PanelsBase.sol";
import {RaceV3Base} from "../../src/v3/RaceV3Base.sol";
import {SolverBook} from "../../src/v3/SolverBook.sol";
import {Heads} from "../../src/v2/Heads.sol";
import {Windows} from "../../src/v3/Windows.sol";
import {Vm} from "forge-std/Vm.sol";
import {RaceV3Setup} from "./helpers/RaceV3Setup.sol";
import {TEST_REPO, TEST_GENESIS_HEAD, suiteWindows} from "./helpers/SuiteWindows.sol";

/// proof-of-fix#310, rebase in place (openspec/changes/proof-of-fix-310-rebase-in-place: design RB1-RB13, the deltas to
/// bounty-market, checking, challenges, contribution-lifecycle and reputation): a claimed, unmerged award whose base
/// went stale is re-submitted rebased onto the head as a new check, keeps its place, and merges once both verdicts are
/// final passes. On the real Panels, FeesV3 and RaceV3, under the taxi fare and v3.1's `mergeDays` of 3 (O4), with the
/// suite's windows (production by default: the done-when's timing is asserted in them).
contract RebaseV3Test is RaceV3Setup {
    bytes32 constant FIX1 = keccak256("fix 1");
    bytes32 constant FIX2 = keccak256("fix 2");
    bytes32 constant FIX2B = keccak256("fix 2, another solver's");
    bytes32 constant FIX3 = keccak256("fix 3");
    bytes32 constant REB = keccak256("fix 2 rebased");
    bytes32 constant REB2 = keccak256("fix 2 rebased again");
    address internal carol = makeAddr("carol"); // a third party
    address internal dave = makeAddr("dave"); // a newcomer
    address internal erin = makeAddr("erin"); // a disputer

    function setUp() public {
        _deployRace(3);
    }

    function _judgeFee() internal pure override returns (uint256) {
        return 0;
    }

    /// The v3.1 plan's race configuration: the Sepolia deploy script's (no attempt, evaluation or appeal fee) with
    /// `mergeDays` 3 (O4).
    function _config() internal view override returns (RaceV3Base.Config memory c) {
        c = super._config();
        c.attemptFee = 0;
        c.evaluationFee = 0;
        c.appealFee = 0;
        c.mergeDays = 3;
    }

    // ---------- helpers ----------

    function _heads() internal view returns (Heads h) {
        (,,,, h,,) = rc.contracts();
    }

    function _start() internal view returns (uint256 st) {
        (,,,,,, st) = rc.contracts();
    }

    function _dayOf(uint256 t) internal view returns (uint256) {
        return (t - _start()) / 1 days;
    }

    /// Bounty 1's fix and bounty 2's, both sealed on the genesis head and both passed by panels of three; bounty 1's
    /// is claimed, final and merged (the head moves to FIX1), and bounty 2's is claimed; its verdict is made final if
    /// `final2`, else its panel is counted after the merge, so it is still in its window.
    function _stale(bool final2) internal returns (uint256 b1, uint256 s1, uint256 b2, uint256 s2) {
        b1 = _openBounty();
        s1 = _commit(solver1, b1, FIX1);
        b2 = _openBounty();
        s2 = _commit(solver2, b2, FIX2);
        _judgeCheck(s1, true);
        rc.claim(b1, FIX1, TEST_GENESIS_HEAD, "salt");
        if (final2) {
            _judgeCheck(s2, true);
            rc.claim(b2, FIX2, TEST_GENESIS_HEAD, "salt");
        }
        _finalAndMerge(b1, s1);
        if (!final2) {
            _judgeCheck(s2, true);
            rc.claim(b2, FIX2, TEST_GENESIS_HEAD, "salt");
        } else {
            _final(s2);
        }
        assertEq(_head(), FIX1);
    }

    function _rebase(address who, uint256 b, bytes32 fix) internal returns (uint256 r) {
        _fund(who, 100 * C);
        bytes32 h = _head();
        vm.prank(who);
        r = rc.rebase(b, fix, h, "salt");
    }

    /// A third bounty's fix, sealed on the head now, passed, claimed, final and merged: the head moves to `fix`.
    function _mergeAnother(bytes32 fix) internal returns (uint256 b, uint256 id) {
        b = _openBounty();
        id = _commit(solver1, b, fix);
        _judgeCheck(id, true);
        rc.claim(b, fix, _head(), "salt");
        _finalAndMerge(b, id);
        assertEq(_head(), fix);
    }

    /// `who` disputes check `id`'s pass with a test; the challenge panel fails the fix (`fails`) or passes it.
    function _dispute(address who, uint256 id, bool fails) internal returns (uint256 cpid) {
        _fund(who, 500 * C);
        vm.prank(who);
        rc.dispute(id, TEST);
        _rollPast(pn.submission(id).challengeBlock);
        pn.drawChallenge(id);
        cpid = pn.submission(id).challengePid;
        require(cpid != 0, "no challenge panel");
        uint256 kc = pn.panel(cpid).k;
        _judge(cpid, fails ? _votes(kc, 0) : _votes(kc, kc));
        _reportAll(cpid);
        rc.settleChallenge(id, cpid);
    }

    function _stake(uint256 id) internal view returns (uint256) {
        uint256 p = rc.submission(id).judged / 10;
        return p > 5 * C ? p : 5 * C;
    }

    // ---------- bounty-market: a stale winner is rebased in place ----------

    /// Task 2.1, the issue's done-when (contribution-lifecycle, "The launch's production windows"; bounty-market, "Two
    /// fixes judged on the same head"): two fixes judged on the same head; the first merges; the second's merge is
    /// stale; its solver rebases onto the new head an hour later; the rebase check passes and becomes final; the
    /// second merges about one cycle after the first: within seal + reveal + the k = 3, level A window + the hour (28 h
    /// with the production windows), against at least mergeDays (14 on v3) + a fresh cycle without a rebase.
    function test_twoFixesOnTheSameHeadMergeOneCycleApart() public {
        (uint256 b1,, uint256 b2, uint256 s2) = _stale(true);
        uint256 t1 = block.timestamp; // the first merge
        assertEq(_heads().head(TEST_REPO).bounty, b1);
        vm.expectRevert(abi.encodeWithSelector(Heads.StaleVerdict.selector, TEST_REPO, TEST_GENESIS_HEAD, FIX1));
        rc.merge(b2);
        Windows memory w = suiteWindows();
        uint256 r = w.reveal; // the solver's time to rebase: an hour in production
        vm.warp(block.timestamp + r);
        uint256 price = rc.priceOf(b2, 1);
        uint256 judged = rc.submission(s2).judged;
        _fund(solver2, 100 * C);
        vm.expectEmit(true, true, false, true, address(rc)); // the check's id is checked below
        emit RaceV3Base.Rebased(b2, s2, 0, REB, FIX1);
        vm.prank(solver2);
        uint256 rid = rc.rebase(b2, REB, FIX1, "salt");
        // the award keeps its place, its epoch and its price
        assertEq(uint256(rc.bounty(b2).state), uint256(RaceV3Base.State.Merged));
        assertEq(rc.bounty(b2).epoch, 1);
        assertEq(rc.bounty(b2).winner, s2);
        assertEq(rc.priceOf(b2, 1), price);
        assertEq(rc.award(b2, 1).rebase, rid);
        RaceV3Base.Submission memory rs = rc.submission(rid);
        assertEq(rs.rebaseOf, s2);
        assertEq(rs.fix, REB);
        assertEq(rs.base, FIX1);
        assertEq(rs.judged, judged); // at the original's judged bounty
        assertEq(rs.commitment, keccak256(abi.encode(REB, FIX1, bytes32("salt"), solver2)));
        assertEq(rs.deposit, fees.maxDeposit(TEST_REPO, 7)); // the same deposit as a fix
        uint256 pid = _judgeCheck(rid, true);
        Panel memory p = pn.panel(pid);
        assertEq(p.k, 3, "a panel of three");
        vm.expectRevert(RaceV3Base.NotYet.selector); // its own window runs
        rc.merge(b2);
        _final(rid);
        vm.prank(makeAddr("anyone"));
        rc.merge(b2);
        uint256 t2 = block.timestamp;
        assertLe(t2 - t1, w.seal + w.reveal + w.challenge[0][1] + r, "about one cycle after the first");
        if (w.reveal == 1 hours) assertLe(t2 - t1, 28 hours);
        // the head is the rebased commit, a fast-forward of the first fix, and records the rebase check's verdict
        Heads.Head memory h = _heads().head(TEST_REPO);
        assertEq(h.commit, REB);
        assertEq(h.bounty, b2);
        assertEq(h.submission, s2);
        assertEq(h.verdict, keccak256(abi.encode(address(pn), rid)));
        assertTrue(rc.award(b2, 1).merged);
        assertEq(rc.award(b2, 1).fix, REB);
        assertTrue(rc.paid(FIX2));
        assertTrue(rc.paid(REB));
        // the bounty joins the winner's reputation once; its claims are closed
        assertEq(book.reputation(solver2), judged);
        assertEq(book.openClaims(solver2), 0);
        _assertBooks();
    }

    /// Scenario "A rebase onto an old head": refused, and nothing is charged.
    function test_aRebaseOntoAnOldHead() public {
        (,, uint256 b2,) = _stale(true);
        _fund(solver2, 100 * C);
        uint256 bal = usd.balanceOf(solver2);
        vm.prank(solver2);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.rebase(b2, REB, TEST_GENESIS_HEAD, "salt");
        vm.prank(solver2);
        vm.expectRevert(RaceV3Base.Refused.selector); // nor onto a commit that was never the head
        rc.rebase(b2, REB, keccak256("elsewhere"), "salt");
        assertEq(usd.balanceOf(solver2), bal);
    }

    /// Scenario "A rebase of a mergeable fix": the award's base is still the head, so it can merge as it is.
    function test_aRebaseOfAMergeableFix() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX1);
        _judgeCheck(id, true);
        rc.claim(b, FIX1, TEST_GENESIS_HEAD, "salt");
        _fund(solver1, 100 * C);
        vm.prank(solver1);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.rebase(b, REB, TEST_GENESIS_HEAD, "salt");
        // nor a bounty that isn't claimed and unmerged
        _finalAndMerge(b, id);
        vm.prank(solver1);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.rebase(b, REB, FIX1, "salt");
        uint256 open = _openBounty();
        vm.prank(solver1);
        vm.expectRevert(abi.encodeWithSelector(RaceV3Base.WrongState.selector, open, RaceV3Base.State.Open));
        rc.rebase(open, REB, FIX1, "salt");
    }

    /// A rebase of a commit already paid, or of the approved commit itself, is refused.
    function test_aRebaseOfAPaidCommit() public {
        (,, uint256 b2,) = _stale(true);
        _fund(solver2, 100 * C);
        vm.startPrank(solver2);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.rebase(b2, FIX1, FIX1, "salt"); // FIX1 is paid (and the head)
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.rebase(b2, FIX2, FIX1, "salt"); // the approved commit
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.rebase(b2, bytes32(0), FIX1, "salt");
        vm.stopPrank();
    }

    /// Scenario "Two rebases at once": the second is refused while the first is undecided, by anyone; a passed one on
    /// the head can't be replaced either.
    function test_twoRebasesAtOnce() public {
        (,, uint256 b2,) = _stale(true);
        uint256 rid = _rebase(solver2, b2, REB);
        _fund(solver2, 100 * C);
        vm.prank(solver2);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.rebase(b2, REB2, FIX1, "salt");
        vm.warp(block.timestamp + 1 days);
        _fund(carol, 100 * C);
        vm.prank(carol);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.rebase(b2, REB2, FIX1, "salt");
        _judgeCheck(rid, true);
        vm.prank(carol);
        vm.expectRevert(RaceV3Base.Refused.selector); // passed, on the head: it merges at its finality
        rc.rebase(b2, REB2, FIX1, "salt");
    }

    // ---------- bounty-market: who may rebase, and who is paid ----------

    /// Scenario "A third party within the grace period": refused until REBASE_GRACE (1 day) after the head moved; the
    /// winning solver may rebase at once.
    function test_aThirdPartyWithinTheGracePeriod() public {
        (,, uint256 b2,) = _stale(true);
        uint256 moved = _heads().head(TEST_REPO).movedAt;
        _fund(carol, 100 * C);
        uint256 bal = usd.balanceOf(carol);
        vm.warp(moved + 1 days - 1);
        vm.prank(carol);
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.rebase(b2, REB, FIX1, "salt");
        assertEq(usd.balanceOf(carol), bal);
        vm.warp(moved + 1 days);
        vm.prank(carol);
        uint256 rid = rc.rebase(b2, REB, FIX1, "salt");
        assertEq(rc.submission(rid).solver, carol);
        assertEq(rc.award(b2, 1).winner, solver2); // the award stays the winner's
    }

    /// Scenario "A third party's rebase merges" (bounty-market; reputation): the winner keeps the award and its
    /// reputation rises by the bounty; the rebaser's claim closes with no reputation; at the bounty's payment the
    /// rebaser gets REBASE_SHARE_BPS (10 %) of the price and its metered checks (S6), the winner its instalments and
    /// its own checks. The original solver is a party to the rebase check (recused).
    function test_aThirdPartysRebaseMerges() public {
        (,, uint256 b2, uint256 s2) = _stale(true);
        vm.warp(block.timestamp + 1 days);
        uint256 rid = _rebase(carol, b2, REB);
        assertTrue(rc.isParty(rid, solver2), "the original solver is a party");
        assertTrue(rc.isParty(rid, carol));
        assertTrue(rc.isParty(rid, reporter));
        assertFalse(rc.isParty(rid, dave));
        uint256 judged = rc.submission(s2).judged;
        assertEq(book.claimOf(rid).amount, judged);
        assertEq(book.openClaims(solver2), judged); // the winner's own claim stays until the merge
        _judgeCheck(rid, true);
        _final(rid);
        rc.merge(b2);
        assertEq(book.reputation(solver2), judged);
        assertEq(book.reputation(carol), 0);
        assertEq(book.openClaims(carol), 0);
        assertEq(book.openClaims(solver2), 0);
        assertFalse(book.isActive(carol)); // O3: no activity for a rebaser
        // the instalments, then the payment
        uint256 price = rc.priceOf(b2, 1);
        _toDay(rc.day() + 7 * 5);
        rc.finish(rid);
        uint256 carol0 = _owed(carol);
        uint256 solver0 = _owed(solver2);
        assertTrue(rc.settle(b2));
        assertEq(uint256(rc.bounty(b2).state), uint256(RaceV3Base.State.Paid));
        uint256 share = price * 1_000 / 10_000;
        assertEq(_owed(carol) - carol0, share + rc.submission(rid).charged, "the share and the rebase's checks");
        assertEq(_owed(solver2) - solver0, price + rc.submission(s2).charged, "the award and the fix's checks");
        _assertBooks();
    }

    /// The winning solver's own rebase that merges: no share (it is the winner's), both checks refunded at the
    /// payment (S6); reputation scenario "The solver rebases its own fix": the original claim closes as the rebase's
    /// opens, so the bounty counts once against the cap.
    function test_theSolverRebasesItsOwnFix() public {
        (,, uint256 b2, uint256 s2) = _stale(true);
        uint256 judged = rc.submission(s2).judged;
        assertEq(book.openClaims(solver2), judged);
        uint256 rid = _rebase(solver2, b2, REB);
        assertEq(book.openClaims(solver2), judged);
        assertEq(book.claimOf(s2).solver, address(0));
        assertEq(book.claimOf(rid).amount, judged);
        _judgeCheck(rid, true);
        _final(rid);
        rc.merge(b2);
        assertEq(book.openClaims(solver2), 0);
        assertEq(book.reputation(solver2), judged);
        uint256 price = rc.priceOf(b2, 1);
        _toDay(rc.day() + 7 * 5);
        uint256 owed0 = _owed(solver2);
        assertTrue(rc.settle(b2));
        assertEq(
            _owed(solver2) - owed0, price + rc.submission(s2).charged + rc.submission(rid).charged, "no share, both checks"
        );
        _assertBooks();
    }

    /// Reputation scenario "A newcomer rebases a large bounty": refused over its cap, nothing charged.
    function test_aNewcomerRebasesALargeBounty() public {
        _reputation(solver1, 1_000 * C);
        _reputation(solver2, 1_000 * C);
        uint256 b1 = _openBounty();
        uint256 s1 = _commit(solver1, b1, FIX1);
        uint256 b2 = _openBounty();
        _pledge(bob, b2, 300 * C);
        uint256 s2 = _commit(solver2, b2, FIX2);
        _judgeCheck(s1, true);
        _judgeCheck(s2, true);
        rc.claim(b1, FIX1, TEST_GENESIS_HEAD, "salt");
        rc.claim(b2, FIX2, TEST_GENESIS_HEAD, "salt");
        _finalAndMerge(b1, s1);
        assertGt(rc.submission(s2).judged, book.capOf(dave));
        vm.warp(block.timestamp + 1 days);
        _fund(dave, 100 * C);
        uint256 bal = usd.balanceOf(dave);
        uint256 cap = book.capOf(dave);
        vm.prank(dave);
        vm.expectRevert(abi.encodeWithSelector(SolverBook.OverCap.selector, dave, 0, cap));
        rc.rebase(b2, REB, FIX1, "salt");
        assertEq(usd.balanceOf(dave), bal);
    }

    // ---------- bounty-market: a failed rebase reopens at once ----------

    /// Task 2.2, scenario "The solver's rebase fails": counted as a fail while its base is the head, anyone reopens the
    /// bounty at once (no deadline), the award closes with nothing earned, and a pass waiting behind it wins.
    function test_theSolversRebaseFails() public {
        uint256 b1 = _openBounty();
        uint256 s1 = _commit(solver1, b1, FIX1);
        uint256 b2 = _openBounty();
        uint256 s2 = _commit(solver2, b2, FIX2);
        uint256 s2b = _commit(bob, b2, FIX2B); // behind it in the queue
        _judgeCheck(s1, true);
        _judgeCheck(s2, true);
        _judgeCheck(s2b, true);
        rc.claim(b1, FIX1, TEST_GENESIS_HEAD, "salt");
        rc.claim(b2, FIX2, TEST_GENESIS_HEAD, "salt");
        _finalAndMerge(b1, s1);
        uint256 rid = _rebase(solver2, b2, REB);
        vm.expectRevert(RaceV3Base.NotYet.selector); // undecided
        rc.mergeExpired(b2);
        _judgeCheck(rid, false);
        assertEq(uint256(rc.submission(rid).outcome), uint256(RaceV3Base.Outcome.Fail));
        // the solver can't dodge it with another rebase
        _fund(solver2, 100 * C);
        vm.prank(solver2);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.rebase(b2, REB2, FIX1, "salt");
        vm.prank(makeAddr("anyone"));
        rc.mergeExpired(b2); // at once: s2's verdict isn't even final
        assertTrue(rc.award(b2, 1).closed);
        assertEq(rc.award(b2, 1).earned, 0);
        assertEq(book.claimOf(s2).solver, address(0));
        assertEq(uint256(rc.bounty(b2).state), uint256(RaceV3Base.State.Won));
        assertEq(rc.bounty(b2).winner, s2b, "the pass waiting behind wins");
        assertEq(book.reputation(solver2), 0); // a fail isn't a reversal: nothing lost
        assertFalse(book.penalized(rid));
        _assertBooks();
    }

    /// Task 2.2: the solver's failed rebase is appealed once under D24 in the reopened bounty: a new submission with the
    /// same commitment, in the queue, judged on the head it named.
    function test_theSolversFailedRebaseIsAppealed() public {
        (,, uint256 b2,) = _stale(true);
        uint256 rid = _rebase(solver2, b2, REB);
        _judgeCheck(rid, false);
        rc.mergeExpired(b2);
        assertEq(uint256(rc.bounty(b2).state), uint256(RaceV3Base.State.Open));
        _fund(solver2, 100 * C);
        vm.prank(solver2);
        uint256 again = rc.appeal(rid, TEST);
        RaceV3Base.Submission memory a = rc.submission(again);
        assertEq(a.commitment, rc.submission(rid).commitment);
        assertEq(a.rebaseOf, 0); // an ordinary submission now
        uint256[] memory q = rc.submissionsOf(b2);
        assertEq(q[q.length - 1], again);
        _judgeCheck(again, true);
        assertEq(rc.bounty(b2).winner, again);
        rc.claim(b2, REB, FIX1, "salt"); // its base is the head
        _finalAndMerge(b2, again);
        assertEq(_head(), REB);
    }

    /// Scenario "A stranger's rebase fails": the award stays claimed, and the solver or anyone may rebase again.
    function test_aStrangersRebaseFails() public {
        (,, uint256 b2,) = _stale(true);
        vm.warp(block.timestamp + 1 days);
        uint256 rid = _rebase(carol, b2, REB);
        _judgeCheck(rid, false);
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.mergeExpired(b2);
        assertEq(uint256(rc.bounty(b2).state), uint256(RaceV3Base.State.Merged));
        uint256 again = _rebase(solver2, b2, REB2);
        assertEq(rc.award(b2, 1).rebase, again);
        _judgeCheck(again, true);
        _final(again);
        rc.merge(b2);
        assertEq(_head(), REB2);
    }

    /// Scenario "The head moved during the check": the solver's rebase failed as stale (its base went stale before its
    /// panel judged it) only frees the slot; the solver rebases again onto the new head.
    function test_theHeadMovedDuringTheCheck() public {
        (,, uint256 b2,) = _stale(true);
        uint256 rid = _rebase(solver2, b2, REB);
        _mergeAnother(FIX3);
        _judgeCheck(rid, false); // the judges refuse a base that isn't the head
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.mergeExpired(b2);
        uint256 again = _rebase(solver2, b2, REB2);
        assertEq(rc.submission(again).base, FIX3);
        _judgeCheck(again, true);
        _final(again);
        rc.merge(b2);
        assertEq(_head(), REB2);
    }

    // ---------- contribution-lifecycle and challenges: timing ----------

    /// Task 2.3, challenges scenario "A rebase submitted late in the original window": a rebase counted shortly before
    /// the original becomes final can't merge before its own full window has passed.
    function test_aRebaseCountedLateCantMergeBeforeItsWindow() public {
        (,, uint256 b2, uint256 s2) = _stale(false);
        uint256 origFinal = pn.submission(s2).finalAt;
        vm.warp(origFinal - suiteWindows().seal - 2 * suiteWindows().reveal);
        uint256 rid = _rebase(solver2, b2, REB);
        _judgeCheck(rid, true);
        assertLt(block.timestamp, origFinal);
        _final(s2);
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.merge(b2);
        assertGt(pn.submission(rid).finalAt, origFinal + suiteWindows().challenge[0][1] - 4 * suiteWindows().reveal);
        _final(rid);
        rc.merge(b2);
        assertEq(_head(), REB);
    }

    /// Task 2.3, contribution-lifecycle scenario "The rebase is final first": merging is refused until the original is
    /// final as well.
    function test_aRebaseFinalBeforeTheOriginalWaits() public {
        (,, uint256 b2, uint256 s2) = _stale(false);
        uint256 rid = _rebase(solver2, b2, REB);
        _judgeCheck(rid, true);
        _final(rid); // warps past the original's finality, which nobody posted
        assertEq(uint256(pn.submission(rid).status), uint256(Status.Final));
        assertEq(uint256(pn.submission(s2).status), uint256(Status.Window));
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.merge(b2);
        _final(s2);
        rc.merge(b2);
        assertEq(_head(), REB);
    }

    /// Task 2.3, scenario "A rebase merged a week late": instalments count from the later finality, so nothing is
    /// earned for the days the rebased commit sat outside the head.
    function test_instalmentsCountFromTheLaterFinality() public {
        (,, uint256 b2, uint256 s2) = _stale(true);
        _toDay(rc.day() + 7); // nobody rebases for a week (nobody expires it either)
        uint256 rid = _rebase(solver2, b2, REB);
        _judgeCheck(rid, true);
        _final(rid);
        rc.merge(b2);
        uint256 origDay = _dayOf(pn.submission(s2).finalAt);
        uint256 rebDay = _dayOf(pn.submission(rid).finalAt);
        assertGe(rebDay, origDay + 7);
        assertEq(rc.earned(b2, 1), 0, "nothing for the days outside the head");
        _toDay((rebDay / 7 + 1) * 7); // the first release after the rebase's finality
        assertEq(rc.earned(b2, 1), 1);
        assertGt(rc.day() / 7 - origDay / 7, 1); // counted from the original it would be more
    }

    // ---------- bounty-market: the merge deadline follows the latest rebase ----------

    /// Scenario "Nobody rebases": mergeDays (3) after the finality, anyone closes it with nothing earned.
    function test_nobodyRebases() public {
        (,, uint256 b2, uint256 s2) = _stale(true);
        uint256 deadline = _dayOf(pn.submission(s2).finalAt) + 3;
        _toDay(deadline);
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.mergeExpired(b2);
        _toDay(deadline + 1);
        rc.mergeExpired(b2);
        assertEq(uint256(rc.bounty(b2).state), uint256(RaceV3Base.State.Open));
        assertEq(rc.award(b2, 1).earned, 0);
    }

    /// The deadline counts from the latest passing rebase's finality, also once a later rebase (here a third party's
    /// failed one) took its slot.
    function test_theDeadlineFollowsTheLatestPassingRebase() public {
        (,, uint256 b2, uint256 s2) = _stale(true);
        vm.warp(block.timestamp + 2 days); // the solver rebases two days on (its finality a later day, in any windows)
        uint256 rid = _rebase(solver2, b2, REB);
        _judgeCheck(rid, true);
        _mergeAnother(FIX3); // REB's base goes stale too
        _final(rid);
        vm.expectRevert(abi.encodeWithSelector(Heads.StaleVerdict.selector, TEST_REPO, FIX1, FIX3));
        rc.merge(b2);
        uint256 deadline = _dayOf(pn.submission(rid).finalAt) + 3;
        assertGt(deadline, _dayOf(pn.submission(s2).finalAt) + 3);
        vm.warp(block.timestamp + 1 days);
        uint256 other = _rebase(carol, b2, REB2); // replaces the passed, stale one
        assertEq(rc.award(b2, 1).lastPass, rid);
        _judgeCheck(other, false);
        _toDay(deadline);
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.mergeExpired(b2);
        _toDay(deadline + 1);
        rc.mergeExpired(b2);
        assertEq(uint256(rc.bounty(b2).state), uint256(RaceV3Base.State.Open));
    }

    /// Scenario "A rebase in flight at the deadline": submitted by the deadline and still judged, the award doesn't
    /// expire; once it passes, not until mergeDays after its finality. One submitted after the deadline holds nothing.
    function test_aRebaseInFlightAtTheDeadline() public {
        (,, uint256 b2, uint256 s2) = _stale(true);
        uint256 deadline = _dayOf(pn.submission(s2).finalAt) + 3;
        _toDay(deadline);
        uint256 rid = _rebase(solver2, b2, REB);
        _toDay(deadline + 2);
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.mergeExpired(b2);
        _judgeCheck(rid, true);
        vm.expectRevert(RaceV3Base.NotYet.selector); // passed, not final
        rc.mergeExpired(b2);
        _final(rid);
        uint256 later = _dayOf(pn.submission(rid).finalAt) + 3;
        _toDay(later);
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.mergeExpired(b2);
        rc.merge(b2); // in time
        assertEq(_head(), REB);
    }

    function test_aRebaseAfterTheDeadlineHoldsNothing() public {
        (,, uint256 b2, uint256 s2) = _stale(true);
        uint256 deadline = _dayOf(pn.submission(s2).finalAt) + 3;
        _toDay(deadline + 1); // expirable; nobody expired it yet
        uint256 rid = _rebase(solver2, b2, REB);
        rc.mergeExpired(b2);
        assertTrue(rc.award(b2, 1).closed);
        // the late rebase check is still judged and paid by the meter; its deposit's rest returns
        _judgeCheck(rid, true);
        _final(rid);
        vm.warp(block.timestamp + 1 days + 1);
        uint256 owed0 = _owed(solver2);
        rc.finish(rid);
        assertGt(_owed(solver2), owed0);
        _assertBooks();
    }

    // ---------- challenges: D21 disputes against a rebase ----------

    /// Task 2.5, challenges scenario "A failing test against the rebased tree": an upheld dispute reverses the rebase;
    /// its submitter's reputation pays (not the winner's); the disputer gets its stake, its panel's cover and the
    /// dispute reward from the pot; the award stays claimed for another rebase.
    function test_aFailingTestAgainstTheRebasedTree() public {
        (,, uint256 b2, uint256 s2) = _stale(true);
        _reputation(carol, 100 * C);
        _reputation(solver2, 100 * C);
        vm.warp(block.timestamp + 1 days);
        uint256 rid = _rebase(carol, b2, REB);
        _judgeCheck(rid, true);
        _network(5, FAMILIES, 3);
        uint256 judged = rc.submission(rid).judged;
        uint256 held0 = rc.held(b2, address(usd));
        uint256 owed0 = _owed(erin);
        uint256 stake = _stake(rid);
        uint256 cover = fees.depositFor(rid, TEST_REPO, 7);
        _dispute(erin, rid, true);
        assertFalse(pn.submission(rid).pass);
        assertEq(uint256(rc.submission(rid).outcome), uint256(RaceV3Base.Outcome.Fail));
        assertTrue(book.penalized(rid));
        assertEq(book.reputation(carol), 100 * C - 2 * judged, "the rebaser's reputation pays");
        assertEq(book.reputation(solver2), 100 * C, "not the winner's");
        assertEq(_owed(erin) - owed0, stake + cover + judged / 10, "stake, cover and the reward");
        assertEq(held0 - rc.held(b2, address(usd)), judged / 10, "the reward, from the pot");
        assertGe(rc.held(b2, address(usd)), rc.priceOf(b2, 1), "the pot still covers the award");
        assertEq(uint256(rc.bounty(b2).state), uint256(RaceV3Base.State.Merged));
        assertFalse(rc.award(b2, 1).closed);
        // its counted panel passed it, so the solver's later reversal isn't a fail-fast; another rebase is taken
        uint256 again = _rebase(solver2, b2, REB2);
        _judgeCheck(again, true);
        _final(again);
        rc.merge(b2);
        assertEq(_head(), REB2);
        s2;
        _assertBooks();
    }

    /// A rejected dispute of a rebase: its stake goes to the rebaser, whose delay it was.
    function test_aRejectedDisputeOfARebasePaysTheRebaser() public {
        (,, uint256 b2,) = _stale(true);
        vm.warp(block.timestamp + 1 days);
        uint256 rid = _rebase(carol, b2, REB);
        _judgeCheck(rid, true);
        _network(5, FAMILIES, 3);
        uint256 owed0 = _owed(carol);
        uint256 stake = _stake(rid);
        _dispute(erin, rid, false);
        assertTrue(pn.submission(rid).pass);
        assertEq(_owed(carol) - owed0, stake);
        assertEq(uint256(rc.bounty(b2).state), uint256(RaceV3Base.State.Merged));
    }

    /// Task 2.5, challenges scenario "The original reversed while its rebase is judged": the award is clawed back and
    /// the bounty reopens as today; the rebase check is still paid by the meter, its deposit's rest returns, and its
    /// pass never merges nor wins the reopened bounty.
    function test_theOriginalReversedWhileItsRebaseIsJudged() public {
        (,, uint256 b2, uint256 s2) = _stale(false);
        uint256 rid = _rebase(solver2, b2, REB);
        _network(5, FAMILIES, 3);
        _fund(bob, 1_000 * C);
        vm.prank(bob);
        rc.challenge(s2, keccak256("evidence"));
        _rollPast(pn.submission(s2).challengeBlock);
        pn.drawChallenge(s2);
        uint256 cpid = pn.submission(s2).challengePid;
        _judge(cpid, _votes(pn.panel(cpid).k, 0));
        _reportAll(cpid);
        rc.settleChallenge(s2, cpid);
        assertTrue(rc.award(b2, 1).closed);
        assertEq(uint256(rc.bounty(b2).state), uint256(RaceV3Base.State.Open));
        uint256 dep = rc.submission(rid).deposit;
        _judgeCheck(rid, true);
        uint256 charged = rc.submission(rid).charged;
        assertGt(charged, 0, "its judges paid by the meter");
        assertEq(uint256(rc.bounty(b2).state), uint256(RaceV3Base.State.Open), "a rebase never wins the queue");
        rc.sync(rid);
        assertEq(uint256(rc.bounty(b2).state), uint256(RaceV3Base.State.Open));
        _final(rid);
        vm.expectRevert(abi.encodeWithSelector(RaceV3Base.WrongState.selector, b2, RaceV3Base.State.Open));
        rc.merge(b2);
        vm.warp(block.timestamp + 1 days + 1);
        uint256 owed0 = _owed(solver2);
        rc.finish(rid);
        assertEq(_owed(solver2) - owed0, dep - charged, "its deposit's rest returns");
        assertEq(_head(), FIX1);
        _assertBooks();
    }

    // ---------- gas (task 1.7): `forge test --gas-report --match-contract RebaseV3` ----------

    /// The three new paths, each a transaction of its own for the gas report: `rebase`, `merge` through a rebase, and
    /// `mergeExpired`'s reopening after the solver's failed rebase.
    function test_gasRebasePaths() public {
        (,, uint256 b2,) = _stale(true);
        _fund(solver2, 100 * C);
        vm.prank(solver2);
        uint256 g = gasleft();
        uint256 rid = rc.rebase(b2, REB, FIX1, "salt");
        emit log_named_uint("rebase gas", g - gasleft());
        _judgeCheck(rid, true);
        _final(rid);
        g = gasleft();
        rc.merge(b2);
        emit log_named_uint("merge through a rebase gas", g - gasleft());
        (,, uint256 b4,) = _staleAgain();
        uint256 r2 = _rebase(solver2, b4, REB2);
        _judgeCheck(r2, false);
        g = gasleft();
        rc.mergeExpired(b4);
        emit log_named_uint("mergeExpired reopening gas", g - gasleft());
    }

    /// Task 1.7 under EIP-8037, as close as local tooling allows (pinned Foundry 1.8.5 doesn't model it; Sepolia is
    /// out of this change's scope): each transaction's gas under the old rules (execution measured here, plus the
    /// intrinsic 21,000 and its calldata), and the storage slots it creates (zero at its start, nonzero at its end,
    /// from the state diff). reports/glamsterdam-runtime-v1.md measured a new slot at 110,028 gas as `gasleft()` sees it
    /// (97,920 state + 12,108 execution) against 22,100 before, so each adds 87,928: the estimate printed. `register` is
    /// the calibration: the report measured 639,079 under the old rules and 2,416,879 on Sepolia.
    function test_gasUnderEip8037() public {
        _fund(reporter, 100 * C);
        bytes memory cd = abi.encodeCall(rc.register, (TEST_REPO, false));
        vm.prank(reporter);
        _measure("register", address(rc), cd);
        (,, uint256 b2,) = _stale(true);
        _fund(solver2, 100 * C);
        cd = abi.encodeCall(rc.rebase, (b2, REB, FIX1, bytes32("salt")));
        vm.prank(solver2);
        uint256 rid = abi.decode(_measure("rebase", address(rc), cd), (uint256));
        _judgeCheck(rid, true);
        _final(rid);
        _measure("merge through a rebase", address(rc), abi.encodeCall(rc.merge, (b2)));
        (,, uint256 b4,) = _staleAgain();
        uint256 r2 = _rebase(solver2, b4, REB2);
        _judgeCheck(r2, false);
        _measure("mergeExpired reopening", address(rc), abi.encodeCall(rc.mergeExpired, (b4)));
    }

    function _measure(string memory what, address to, bytes memory cd) internal returns (bytes memory ret) {
        vm.startStateDiffRecording();
        uint256 g = gasleft();
        bool ok;
        (ok, ret) = to.call(cd);
        g -= gasleft();
        Vm.AccountAccess[] memory acc = vm.stopAndReturnStateDiff();
        require(ok, what);
        uint256 calldataGas;
        for (uint256 i; i < cd.length; ++i) {
            calldataGas += cd[i] == 0 ? 4 : 16;
        }
        uint256 old = g + 21_000 + calldataGas;
        uint256 created = _createdSlots(acc);
        emit log_named_string("transaction", what);
        emit log_named_uint("  gas, old rules (execution + 21,000 + calldata)", old);
        emit log_named_uint("  storage slots created", created);
        emit log_named_uint("  estimate under EIP-8037 (+87,928 a new slot)", old + created * 87_928);
    }

    /// Slots zero at the transaction's start and nonzero at its end (its writes, in order, not reverted).
    function _createdSlots(Vm.AccountAccess[] memory acc) internal pure returns (uint256 n) {
        uint256 total;
        for (uint256 i; i < acc.length; ++i) {
            total += acc[i].storageAccesses.length;
        }
        address[] memory who = new address[](total);
        bytes32[] memory slot = new bytes32[](total);
        bytes32[] memory first = new bytes32[](total);
        bytes32[] memory last = new bytes32[](total);
        uint256 m;
        for (uint256 i; i < acc.length; ++i) {
            for (uint256 j; j < acc[i].storageAccesses.length; ++j) {
                Vm.StorageAccess memory x = acc[i].storageAccesses[j];
                if (!x.isWrite || x.reverted) continue;
                uint256 k;
                while (k < m && (who[k] != x.account || slot[k] != x.slot)) ++k;
                if (k == m) {
                    (who[m], slot[m], first[m]) = (x.account, x.slot, x.previousValue);
                    ++m;
                }
                last[k] = x.newValue;
            }
        }
        for (uint256 k; k < m; ++k) {
            if (first[k] == 0 && last[k] != 0) ++n;
        }
    }

    /// Another stale award on the head now: a pair of fixes sealed on it, the first merged.
    function _staleAgain() internal returns (uint256 b1, uint256 s1, uint256 b2, uint256 s2) {
        bytes32 base = _head();
        b1 = _openBounty();
        s1 = _commit(solver1, b1, FIX3);
        b2 = _openBounty();
        s2 = _commit(solver2, b2, keccak256("fix 4"));
        _judgeCheck(s1, true);
        _judgeCheck(s2, true);
        rc.claim(b1, FIX3, base, "salt");
        rc.claim(b2, keccak256("fix 4"), base, "salt");
        _finalAndMerge(b1, s1);
        _final(s2);
    }
}
