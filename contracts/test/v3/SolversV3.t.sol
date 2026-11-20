// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Test, console} from "forge-std/Test.sol";
import {Panels} from "../../src/v3/Panels.sol";
import {Status, Kind} from "../../src/v3/PanelsBase.sol";
import {RaceV3} from "../../src/v3/RaceV3.sol";
import {RaceV3Base} from "../../src/v3/RaceV3Base.sol";
import {SolverBook} from "../../src/v3/SolverBook.sol";
import {RaceV3Setup} from "./helpers/RaceV3Setup.sol";
import {TEST_REPO} from "./helpers/SuiteWindows.sol";

/// proof-of-fix#251 contract batch 3: the launch's solver-side rules on the real race, Panels and FeesV3 (no mocked
/// view: the minimum of active solvers is reached by merged fixes). By spec name:
/// - specs/bounty-market (launch): "Every submission pays the judges' fee", "What makes a solver active", "No pledges
///   before three active solvers" (task 3.3; #132 D30, launch L6);
/// - specs/reputation (launch): "A solver's open claims are capped by its reputation", "Reputation is what an
///   identity's fixes earned and kept", "A reversal costs twice its bounty" (#132 D29, task 12.5);
/// - #132's judge-panels: "A failing test reverses a pass", "What a test dispute pays and costs" (D21, task 10.4), "The
///   seated families decide an appeal", "An appeal needs a test and a stake", "What an appeal stakes" (D24, task 11.4);
///   a challenge among one family closed by its second draw (D27); #132's bounty-market "No solver's deposit".
/// Values: ADR 0007 (REP_BASE $50, REP_MULT 1, a reversal 2 × its bounty; the stakes the larger of $5 and 10 %; the
/// reward 1,000 bps; ACTIVE_SOLVERS_MIN 3, ACTIVE_WINDOW 26 weeks) and the launch's JUDGE_FEE ($40).
contract SolversV3Test is RaceV3Setup {
    address internal carol = makeAddr("carol");
    address internal dave = makeAddr("dave");
    address internal erin = makeAddr("erin");
    address internal funder = makeAddr("funder");
    uint256 internal fixes;

    function setUp() public {
        gateOpen = false;
        _deployRace(19); // twenty validators of seven families: a challenge of a panel of 7 draws a fresh panel of 7
    }

    // ---------- helpers ----------

    function _nextFix() internal returns (bytes32) {
        return keccak256(abi.encode("a fix", ++fixes));
    }

    /// A registered issue whose check passed and is final: its bounty open, unfunded.
    function _unfunded() internal returns (uint256 b) {
        uint256 i = _register();
        _check(rc.issue(i).check, true);
        b = rc.openBounty(i);
    }

    /// The pledge that puts a fresh bounty's price on offer (day 0, 50 %) at about `target` micro-coins.
    function _pledgeFor(uint256 target) internal pure returns (uint256) {
        return 2 * C + target * 2 * (10_000 + FINDER) / 10_000 + 1;
    }

    /// An unfunded bounty, then funded to about `target` on offer (the minimum of active solvers must be met).
    function _funded(uint256 target) internal returns (uint256 b) {
        b = _unfunded();
        _pledge(funder, b, _pledgeFor(target));
    }

    /// `who`'s fix to bounty `b`, passed, claimed, final and merged.
    function _merged(address who, uint256 b) internal returns (uint256 id) {
        bytes32 fix = _nextFix();
        id = _commit(who, b, fix);
        _judgeCheck(id, true);
        rc.claim(b, fix, _head(), "salt");
        _finalAndMerge(b, id);
    }

    /// Three solvers made active by unfunded fixes: the testnet's way to open pledges.
    function _threeActive() internal {
        _merged(solver1, _unfunded());
        _merged(solver2, _unfunded());
        _merged(carol, _unfunded());
        assertEq(book.activeCount(), 3);
    }

    /// `who` disputes check `id`'s pass with a test; the challenge panel votes it fails (`fails`) or passes, reports,
    /// and the dispute is settled.
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

    // ---------- values ----------

    function test_valuesAsAdr0007() public view {
        assertEq(book.REP_BASE(), 50 * C);
        assertEq(book.REP_MULT(), 1);
        assertEq(book.REP_LOSS_X(), 2);
        assertEq(book.ACTIVE_SOLVERS_MIN(), 3);
        assertEq(book.ACTIVE_WINDOW(), pn.ACTIVE_WINDOW());
        assertEq(rc.getConfig().judgeFee, 40 * C);
        assertEq(book.race(), address(rc));
        // the production windows: 26 weeks and 72 h (minutes: every hour a minute)
        assertTrue(pn.ACTIVE_WINDOW() == 26 weeks || pn.ACTIVE_WINDOW() == 26 weeks / 60);
        assertTrue(pn.APPEAL_WINDOW() == 72 hours || pn.APPEAL_WINDOW() == 72 minutes);
    }

    // ---------- bounty-market: no pledges before three active solvers (task 3.3) ----------

    /// Scenario "The testnet's first weeks": while only two solvers are active, a pledge reverts with the count and no
    /// coin moves; issues are still registered and fixed with no funds, and those fixes count.
    function test_theTestnetsFirstWeeks() public {
        assertEq(book.activeCount(), 0);
        _merged(solver1, _unfunded());
        _merged(solver2, _unfunded());
        assertEq(book.activeCount(), 2);
        assertFalse(book.pledgesOpen());
        uint256 b = _unfunded();
        _fund(funder, 100 * C);
        uint256 bal = usd.balanceOf(funder);
        vm.prank(funder);
        vm.expectRevert(abi.encodeWithSelector(RaceV3Base.TooFewActiveSolvers.selector, 2));
        rc.pledge(b, 10 * C);
        assertEq(usd.balanceOf(funder), bal);
        assertEq(rc.held(b, address(usd)), 0);
        _merged(carol, b); // the unfunded bounty is still raced, and its fix counts
        assertTrue(book.pledgesOpen());
        uint256 b2 = _unfunded();
        _pledge(funder, b2, 10 * C);
        assertEq(rc.held(b2, address(usd)), 10 * C);
    }

    /// Scenario "Activity lapses with funded bounties open": the count falls from 3 to 2 while two bounties hold
    /// pledges: they stay open, keep their funds and can be won; only new pledges are refused until the count is back.
    function test_activityLapsesWithFundedBountiesOpen() public {
        _threeActive();
        uint256 b1 = _funded(20 * C); // $40 on offer once the price has risen to the whole
        uint256 b2 = _funded(20 * C);
        uint256 h1 = rc.held(b1, address(usd));
        vm.warp(book.solverOf(solver1).lastActive + book.ACTIVE_WINDOW() + 1);
        assertEq(book.activeCount(), 2);
        assertEq(uint256(rc.bounty(b1).state), uint256(RaceV3Base.State.Open));
        assertEq(uint256(rc.bounty(b2).state), uint256(RaceV3Base.State.Open));
        assertEq(rc.held(b1, address(usd)), h1);
        _fund(funder, 100 * C);
        vm.prank(funder);
        vm.expectRevert(abi.encodeWithSelector(RaceV3Base.TooFewActiveSolvers.selector, 2));
        rc.pledge(b2, 10 * C);
        uint256 id = _merged(solver2, b1); // won and merged: solver2 counts again, and so does the count
        assertEq(uint256(rc.bounty(b1).state), uint256(RaceV3Base.State.Merged));
        assertTrue(rc.award(b1, 1).merged);
        assertEq(rc.award(b1, 1).sub, id);
        assertGe(book.activeCount(), 2);
        _merged(solver1, _unfunded()); // solver1 is back: three again
        assertEq(book.activeCount(), 3);
        _pledge(funder, b2, 10 * C);
    }

    // ---------- bounty-market: what makes a solver active ----------

    /// Scenario "A solver whose last fix is old": its only merged fix is older than ACTIVE_WINDOW, no dispute since.
    function test_aSolverWhoseLastFixIsOld() public {
        _merged(solver1, _unfunded());
        assertTrue(book.isActive(solver1));
        uint256 at = book.solverOf(solver1).lastActive;
        vm.warp(at + book.ACTIVE_WINDOW());
        assertTrue(book.isActive(solver1));
        vm.warp(at + book.ACTIVE_WINDOW() + 1);
        assertFalse(book.isActive(solver1));
        assertEq(book.activeCount(), 0);
        assertTrue(book.solverOf(solver1).hasFix); // still a solver of the repository: a later upheld test counts
    }

    /// Scenario "A solver who found a bad fix": an identity with a merged fix whose failing-test dispute against another
    /// pass is upheld counts as active for ACTIVE_WINDOW from then.
    function test_aSolverWhoFoundABadFix() public {
        _threeActive();
        uint256 merged1 = book.solverOf(solver1).lastActive;
        uint256 b = _funded(40 * C);
        uint256 id = _commit(dave, b, _nextFix());
        _judgeCheck(id, true);
        _dispute(solver1, id, true);
        assertEq(book.solverOf(solver1).lastActive, block.timestamp);
        assertGt(block.timestamp, book.solverOf(carol).lastActive); // the last merge was before the dispute
        vm.warp(block.timestamp + book.ACTIVE_WINDOW());
        assertGt(block.timestamp, merged1 + book.ACTIVE_WINDOW()); // its merge alone would have lapsed
        assertTrue(book.isActive(solver1));
        assertFalse(book.isActive(solver2));
        assertFalse(book.isActive(carol));
        assertEq(book.activeCount(), 1);
    }

    /// Scenario "A disputer from outside the repository": an identity with no merged fix has a failing-test dispute
    /// upheld: it is paid as any disputer is, but it doesn't count as active.
    function test_aDisputerFromOutsideTheRepository() public {
        _threeActive();
        uint256 b = _funded(40 * C);
        uint256 id = _commit(dave, b, _nextFix());
        _judgeCheck(id, true);
        uint256 judged = rc.submission(id).judged;
        uint256 owed0 = _owed(erin);
        _dispute(erin, id, true);
        assertEq(_owed(erin) - owed0, _stake(id) + fees.depositFor(id, TEST_REPO, 7) + judged / 10);
        assertFalse(book.isActive(erin));
        assertEq(book.solverOf(erin).lastActive, 0);
        assertEq(book.activeCount(), 3);
    }

    // ---------- bounty-market: the judges' fee (D30) and no deposit ----------

    /// Scenario "A rejected fix": it has paid JUDGE_FEE and nothing more, and the fee isn't returned; the bounty stays
    /// as it was for the next solver (#132 "No solver's deposit": "A bad fix rejected").
    function test_aRejectedFix() public {
        _threeActive();
        uint256 b = _funded(40 * C);
        uint256 held0 = rc.held(b, address(usd));
        _fund(dave, 100 * C);
        uint256 bal = usd.balanceOf(dave);
        bytes32 fix = _nextFix();
        bytes32 c = _commitment(fix, dave);
        vm.prank(dave);
        uint256 id = rc.commit(b, c);
        assertEq(bal - usd.balanceOf(dave), 40 * C);
        assertEq(rc.submission(id).deposit, 40 * C);
        uint256 pooled = pn.pool() == address(pool3) ? pool3.held(address(usd)) : 0;
        _judgeCheck(id, false);
        RaceV3Base.Submission memory s = rc.submission(id);
        assertLe(s.charged, 40 * C); // the judges are paid from the fee: nothing more is charged on rejection
        _final(id);
        vm.warp(block.timestamp + 1 days + 1);
        rc.finish(id);
        assertEq(_owed(dave), 0);
        assertEq(bal - usd.balanceOf(dave), 40 * C);
        assertGe(pool3.held(address(usd)), pooled + 40 * C - s.charged);
        assertEq(rc.held(b, address(usd)), held0); // no deposit added to the bounty
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Open));
        assertEq(book.openClaims(dave), 0); // its claim closed with the deposit's return
        vm.expectRevert(RaceV3Base.NotYet.selector); // nothing left to close
        rc.close(id);
    }

    /// Scenario "A withdrawn submission": no panel seated; the fee isn't returned and no per-check charge is made.
    function test_aWithdrawnSubmission() public {
        uint256 b = _unfunded();
        uint256 id = _commit(dave, b, _nextFix());
        uint256 pooled = pool3.held(address(usd));
        vm.prank(dave);
        rc.withdraw(id);
        assertEq(_owed(dave), 0);
        assertEq(rc.submission(id).charged, 0);
        assertEq(pool3.held(address(usd)), pooled + 40 * C);
        assertEq(book.openClaims(dave), 0);
    }

    /// No solver's deposit: the contracts have no deposit parameter, and a good fix is paid the bounty with nothing
    /// else involved ("A good fix paid"); a fix never judged gets its fee back (L19's refund, a time-out).
    function test_noSolversDeposit() public {
        string memory json = vm.readFile("out/RaceV3.sol/RaceV3.json");
        assertFalse(vm.keyExistsJson(json, ".methodIdentifiers.SOLVER_DEPOSIT_BPS()"));
        string memory jb = vm.readFile("out/SolverBook.sol/SolverBook.json");
        assertFalse(vm.keyExistsJson(jb, ".methodIdentifiers.SOLVER_DEPOSIT_BPS()"));
        _threeActive();
        uint256 b = _funded(40 * C);
        uint256 id = _merged(dave, b);
        assertEq(rc.award(b, 1).winner, dave);
        assertEq(rc.submission(id).deposit + rc.submission(id).charged, 40 * C); // only the fee was ever taken
    }

    // ---------- reputation (D29, task 12.5) ----------

    /// Scenario "A new identity": a fix to a $40 bounty is accepted ($40 of a $50 cap); another to a $30 bounty while
    /// the first isn't final is refused, with no fee taken.
    function test_aNewIdentity() public {
        _threeActive();
        uint256 b1 = _funded(40 * C);
        uint256 b2 = _funded(30 * C);
        uint256 id = _commit(dave, b1, _nextFix());
        uint256 j1 = rc.submission(id).judged;
        assertApproxEqAbs(j1, 40 * C, 2);
        assertEq(book.openClaims(dave), j1);
        assertEq(book.capOf(dave), 50 * C);
        _fund(dave, 100 * C);
        uint256 bal = usd.balanceOf(dave);
        bytes32 c = _commitment(_nextFix(), dave);
        uint256 j2 = rc.lockedPrice(b2);
        vm.prank(dave);
        vm.expectRevert(abi.encodeWithSelector(SolverBook.OverCap.selector, dave, j1, 50 * C));
        rc.commit(b2, c);
        assertApproxEqAbs(j2, 30 * C, 2);
        assertEq(usd.balanceOf(dave), bal); // no fee taken
        assertEq(rc.submissionsOf(b2).length, 0);
    }

    /// Scenario "An established identity": $200 of reputation and no open claims: a fix to a $240 bounty is accepted,
    /// since its cap is $50 + 1 × $200 = $250.
    function test_anEstablishedIdentity() public {
        _threeActive();
        _reputation(dave, 200 * C);
        assertEq(book.capOf(dave), 250 * C);
        uint256 b = _funded(240 * C);
        uint256 id = _commit(dave, b, _nextFix());
        assertApproxEqAbs(rc.submission(id).judged, 240 * C, 2);
        assertEq(book.openClaims(dave), rc.submission(id).judged);
    }

    /// Scenario "A fix paid": an identity's fix to an $80 bounty becomes final and merged (its award starts): its
    /// reputation rises by $80, and its claim closes.
    function test_aFixPaid() public {
        _threeActive();
        _reputation(dave, 30 * C); // room for an $80 claim
        uint256 b = _funded(80 * C);
        uint256 id = _merged(dave, b);
        uint256 judged = rc.submission(id).judged;
        assertApproxEqAbs(judged, 80 * C, 2);
        assertEq(book.reputation(dave), 30 * C + judged);
        assertEq(book.openClaims(dave), 0);
        assertTrue(book.isActive(dave));
    }

    /// Scenario "An honest mistake reversed": $500 of reputation, a $60 fix reversed by a failing test: reputation
    /// falls to $380 and the cap to $430; a reversal never resets it, and is recorded once.
    function test_anHonestMistakeReversed() public {
        _threeActive();
        _reputation(dave, 500 * C);
        uint256 b = _funded(60 * C);
        uint256 id = _commit(dave, b, _nextFix());
        uint256 judged = rc.submission(id).judged;
        assertApproxEqAbs(judged, 60 * C, 2);
        _judgeCheck(id, true);
        _dispute(solver1, id, true);
        assertEq(book.reputation(dave), 500 * C - 2 * judged);
        assertEq(book.capOf(dave), 550 * C - 2 * judged);
        assertTrue(book.penalized(id));
        rc.sync(id); // again: nothing more
        assertEq(book.reputation(dave), 500 * C - 2 * judged);
        assertEq(book.openClaims(dave), judged); // its claim closes at finality
        _final(id);
        rc.close(id);
        assertEq(book.openClaims(dave), 0);
    }

    /// A reversal takes the reputation to zero, not below; claims released when the network can't judge cost nothing.
    function test_reversalFloorsAtZero() public {
        _threeActive();
        _reputation(dave, 10 * C);
        uint256 b = _funded(40 * C);
        uint256 id = _commit(dave, b, _nextFix());
        _judgeCheck(id, true);
        _dispute(solver1, id, true);
        assertEq(book.reputation(dave), 0);
        assertEq(book.capOf(dave), 50 * C);
    }

    /// Reputation is never transferred by any function: the book's only writers are the race's calls.
    function test_reputationIsntTransferable() public {
        vm.expectRevert(SolverBook.NotRace.selector);
        book.paid(1, dave, 1);
        vm.expectRevert(SolverBook.NotRace.selector);
        book.openClaim(1, dave, 1);
        vm.expectRevert(SolverBook.NotRace.selector);
        book.reversed(1, dave, 1);
        vm.expectRevert(SolverBook.NotRace.selector);
        book.disputeUpheld(dave);
        vm.expectRevert(SolverBook.NotRace.selector);
        book.closeClaim(1);
    }

    // ---------- the test dispute (D21, task 10.4) ----------

    /// Scenario "A contender's test": the fix isn't paid (its award is clawed back, the bounty reopens), the disputer
    /// gets its stake back and EVIDENCE_REWARD_BPS (1,000) of the bounty, from the pot.
    function test_aContendersTest() public {
        _threeActive();
        uint256 b = _funded(40 * C);
        bytes32 fix = _nextFix();
        uint256 id = _commit(dave, b, fix);
        _judgeCheck(id, true);
        rc.claim(b, fix, _head(), "salt");
        uint256 judged = rc.submission(id).judged;
        uint256 held0 = rc.held(b, address(usd));
        uint256 owed0 = _owed(erin);
        _dispute(erin, id, true);
        assertFalse(pn.submission(id).pass);
        assertTrue(rc.award(b, 1).closed);
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Open));
        assertEq(_owed(erin) - owed0, _stake(id) + fees.depositFor(id, TEST_REPO, 7) + judged / 10);
        assertEq(held0 - rc.held(b, address(usd)), judged / 10); // from the bounty, never from the solver
        _assertBooks();
    }

    /// Scenario "A test that passes" / "A test for something the issue didn't ask": the panel keeps the pass; the
    /// stake goes to the solver, and the verdict stands.
    function test_aTestThatPasses() public {
        _threeActive();
        uint256 b = _funded(40 * C);
        uint256 id = _commit(dave, b, _nextFix());
        _judgeCheck(id, true);
        uint256 owedDave = _owed(dave);
        _dispute(erin, id, false);
        assertTrue(pn.submission(id).pass);
        assertEq(_owed(dave) - owedDave, _stake(id));
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Won));
        assertEq(book.reputation(dave), 0);
        assertFalse(book.penalized(id));
    }

    /// Scenario "A disputer without evidence": a party disputing passes with tests that pass loses its stakes to the
    /// solvers, and no verdict changes.
    function test_aDisputerWithoutEvidence() public {
        _threeActive();
        _reputation(dave, 100 * C); // three open claims of $20
        uint256 owedDave = _owed(dave);
        uint256 lost;
        for (uint256 i; i < 3; ++i) {
            uint256 b = _funded(20 * C);
            uint256 id = _commit(dave, b, _nextFix());
            _judgeCheck(id, true);
            uint256 bal = _owed(erin);
            uint256 before = usd.balanceOf(erin) + 500 * C;
            _dispute(erin, id, false);
            assertTrue(pn.submission(id).pass);
            lost += before - (usd.balanceOf(erin) + _owed(erin) - bal);
            vm.warp(block.timestamp + 2 hours);
        }
        assertEq(_owed(dave) - owedDave, 3 * 5 * C); // three $5 stakes to the solver (10 % of $20 is below $5)
        assertGt(lost, 3 * 5 * C); // and the three panels' checks, from the cover
    }

    /// Disputes take a test and target a pass; a receipt challenge stays as it was.
    function test_disputeRules() public {
        _threeActive();
        uint256 b = _funded(40 * C);
        uint256 id = _commit(dave, b, _nextFix());
        _judgeCheck(id, false);
        _fund(erin, 100 * C);
        vm.prank(erin);
        vm.expectRevert(RaceV3Base.Refused.selector); // not a pass
        rc.dispute(id, TEST);
        uint256 id2 = _commit(solver2, b, _nextFix());
        _judgeCheck(id2, true);
        vm.prank(erin);
        vm.expectRevert(RaceV3Base.Refused.selector); // no test
        rc.dispute(id2, bytes32(0));
        vm.prank(erin);
        rc.dispute(id2, TEST);
        assertTrue(rc.challengeOf(id2).test);
        assertEq(rc.challengeOf(id2).stake, _stake(id2));
        vm.prank(erin);
        vm.expectRevert(RaceV3Base.Refused.selector); // one at a time
        rc.dispute(id2, TEST);
    }

    // ---------- the appeal (D24, task 11.4) ----------

    /// Scenario "A good fix wrongly rejected": rejected, appealed with a test and the stake; a fresh draw passes it; its
    /// window runs as any pass's, it is paid when final; the stake returns.
    function test_aGoodFixWronglyRejected() public {
        _threeActive();
        uint256 b = _funded(40 * C);
        bytes32 fix = _nextFix();
        uint256 id = _commit(dave, b, fix);
        _judgeCheck(id, false);
        assertEq(book.openClaims(dave), rc.submission(id).judged);
        vm.prank(dave);
        uint256 again = rc.appeal(id, TEST);
        assertEq(book.openClaims(dave), rc.submission(again).judged); // the claim moved to the appeal
        assertEq(rc.submission(again).commitment, rc.submission(id).commitment);
        assertEq(rc.submission(again).deposit, 40 * C); // the appellant pays the appeal panel's checks
        _judgeCheck(again, true);
        assertEq(rc.bounty(b).winner, again);
        rc.claim(b, fix, _head(), "salt");
        _finalAndMerge(b, again);
        assertEq(book.openClaims(dave), 0);
        assertGt(book.reputation(dave), 0);
    }

    /// Scenario "A second appeal": refused; and so is an appeal of an appeal.
    function test_aSecondAppeal() public {
        _threeActive();
        uint256 b = _funded(40 * C);
        uint256 id = _commit(dave, b, _nextFix());
        _judgeCheck(id, false);
        vm.prank(dave);
        uint256 again = rc.appeal(id, TEST);
        _judgeCheck(again, false);
        vm.prank(dave);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.appeal(id, TEST);
        vm.prank(dave);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.appeal(again, TEST);
    }

    /// Scenario "An appeal with no evidence": no test, refused with no panel, nothing taken. Another's fix can't be
    /// appealed, nor one past APPEAL_WINDOW.
    function test_anAppealWithNoEvidence() public {
        _threeActive();
        uint256 b = _funded(40 * C);
        uint256 id = _commit(dave, b, _nextFix());
        uint256 pid = _judgeCheck(id, false);
        _fund(dave, 100 * C);
        uint256 bal = usd.balanceOf(dave);
        vm.prank(dave);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.appeal(id, bytes32(0));
        assertEq(usd.balanceOf(dave), bal);
        vm.prank(erin);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.appeal(id, TEST);
        vm.warp(pn.panel(pid).revealBy + pn.APPEAL_WINDOW() + 1);
        vm.prank(dave);
        vm.expectRevert(RaceV3Base.AppealClosed.selector);
        rc.appeal(id, TEST);
    }

    /// A failed appeal costs only its panel's checks (owner, 2026-11-19: no appeal stake): nothing goes to the sponsors'
    /// pool, the rejection is final, and the claim closes at finality.
    function test_aFailedAppealCostsOnlyItsChecks() public {
        _threeActive();
        _reputation(dave, 200 * C);
        uint256 b = _funded(200 * C);
        uint256 id = _commit(dave, b, _nextFix());
        _judgeCheck(id, false);
        _fund(dave, 100 * C);
        uint256 bal = usd.balanceOf(dave);
        uint256 pooled = pool3.held(address(usd));
        vm.prank(dave);
        uint256 again = rc.appeal(id, TEST);
        assertEq(bal - usd.balanceOf(dave), 2 * C + rc.submission(again).deposit); // the appeal fee and its checks
        _judgeCheck(again, false);
        vm.expectRevert(RaceV3Base.NotYet.selector); // not final yet
        rc.close(again);
        _final(again);
        rc.close(again);
        assertEq(book.openClaims(dave), 0);
        assertEq(pool3.held(address(usd)), pooled); // no stake lost to the pool (the flat fee's rest goes at `finish`)
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.close(again);
    }


    // ---------- the second draw among few families (D27) ----------

    /// A challenge among one family, closed by its second draw: every validator is one family's, a dispute can't draw
    /// a larger fresh panel, a second draw of the original size (the original judges not excluded) decides it, and the
    /// pass becomes final.
    function test_aChallengeAmongOneFamilyClosedByItsSecondDraw() public {
        _deployRaceWithOneFamily();
        _threeActive();
        uint256 b = _funded(40 * C);
        uint256 id = _commit(dave, b, _nextFix());
        uint256 pid = _judgeCheck(id, true);
        uint256 k = pn.panel(pid).k;
        assertTrue(scores.fewFamilies());
        uint256 cpid = _dispute(erin, id, false);
        assertEq(pn.panel(cpid).k, k, "a second draw of the original size");
        assertTrue(pn.submission(id).pass);
        _final(id);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Final));
    }

    function _deployRaceWithOneFamily() internal {
        _deployRace(0);
        _network(6, 1, 3); // seven validators, all of the genesis family
        _knowFamilies(1);
    }

    // ---------- gas ----------

    function test_gasSolvers() public {
        uint256 g;
        _merged(solver1, _unfunded());
        _merged(solver2, _unfunded());
        uint256 b0 = _unfunded();
        bytes32 fix = _nextFix();
        _fund(carol, 100 * C);
        bytes32 c = _commitment(fix, carol);
        vm.prank(carol);
        g = gasleft();
        uint256 id = rc.commit(b0, c);
        console.log("commit (the judges' fee, the claim against the cap):", g - gasleft());
        _judgeCheck(id, true);
        rc.claim(b0, fix, _head(), "salt");
        _final(id);
        g = gasleft();
        rc.merge(b0);
        console.log("merge (the head, the reputation, the active list):", g - gasleft());
        uint256 b = _unfunded();
        _fund(funder, 100 * C);
        vm.prank(funder);
        g = gasleft();
        rc.pledge(b, 60 * C);
        console.log("pledge (the gate: three active solvers read):", g - gasleft());
        uint256 id2 = _commit(dave, b, _nextFix());
        _judgeCheck(id2, true);
        _fund(erin, 100 * C);
        vm.prank(erin);
        g = gasleft();
        rc.dispute(id2, TEST);
        console.log("dispute (stake and cover held, Panels.challenge):", g - gasleft());
        _rollPast(pn.submission(id2).challengeBlock);
        pn.drawChallenge(id2);
        uint256 cpid = pn.submission(id2).challengePid;
        uint256 kc = pn.panel(cpid).k;
        _judge(cpid, _votes(kc, 0));
        _reportAll(cpid);
        g = gasleft();
        rc.settleChallenge(id2, cpid);
        console.log("settleChallenge (a test dispute upheld: reward, reputation, activity):", g - gasleft());
        uint256 b3 = _funded(20 * C);
        uint256 id3 = _commit(solver2, b3, _nextFix());
        _judgeCheck(id3, false);
        _fund(solver2, 100 * C);
        vm.prank(solver2);
        g = gasleft();
        uint256 again = rc.appeal(id3, TEST);
        console.log("appeal (no stake: a new submission and claim):", g - gasleft());
        _judgeCheck(again, false);
        _final(again);
        g = gasleft();
        rc.close(again);
        console.log("close (a failed appeal's claim closed at finality):", g - gasleft());
    }
}

/// The invariant of task 3.3: no pledge lands while fewer than ACTIVE_SOLVERS_MIN solvers are active, and the book's
/// count is the count of identities active within ACTIVE_WINDOW. The race and the book are real; activity comes in
/// through the race's own calls into the book (a merge's `paid`, an upheld test's `disputeUpheld`), pranked as the
/// race, so a run reaches every count quickly; pledges go through `RaceV3.pledge`, from any funder, at any time.
contract SolversGateHandler is Test {
    RaceV3 internal rc;
    SolverBook internal book;
    address internal coin;
    uint256[] internal bounties;
    address[] internal actors;
    mapping(address => uint256) internal lastActive;
    mapping(address => bool) internal hasFix;
    uint256 internal fakeId = type(uint128).max;
    uint256 public pledges;
    uint256 public refused;
    uint256 public landedBelowMin;
    uint256 public wrongRefusals;

    constructor(RaceV3 rc_, SolverBook book_, address coin_, uint256[] memory bounties_) {
        rc = rc_;
        book = book_;
        coin = coin_;
        bounties = bounties_;
        for (uint256 i; i < 6; ++i) {
            actors.push(address(uint160(0xA000 + i)));
        }
    }

    function _actor(uint256 seed) internal view returns (address) {
        return actors[seed % actors.length];
    }

    /// The ghost count: identities active within ACTIVE_WINDOW now.
    function ghostCount() public view returns (uint256 n) {
        uint256 w = book.ACTIVE_WINDOW();
        for (uint256 i; i < actors.length; ++i) {
            uint256 t = lastActive[actors[i]];
            if (t != 0 && block.timestamp <= t + w) ++n;
        }
    }

    function merged(uint256 seed) external {
        address a = _actor(seed);
        vm.prank(address(rc));
        book.paid(++fakeId, a, 1);
        lastActive[a] = block.timestamp;
        hasFix[a] = true;
    }

    function disputeUpheld(uint256 seed) external {
        address a = _actor(seed);
        vm.prank(address(rc));
        book.disputeUpheld(a);
        if (hasFix[a]) lastActive[a] = block.timestamp;
    }

    function passTime(uint256 seed) external {
        vm.warp(block.timestamp + seed % (book.ACTIVE_WINDOW() / 3 + 1));
    }

    function pledge(uint256 seed, uint256 amount) external {
        amount = 1 + amount % 1e6;
        address who = address(uint160(0xF000 + seed % 4));
        uint256 b = bounties[seed % bounties.length];
        uint256 n = ghostCount();
        vm.prank(who);
        try rc.pledge(b, amount) {
            ++pledges;
            if (n < 3) ++landedBelowMin;
        } catch (bytes memory err) {
            ++refused;
            bool gate = bytes4(err) == RaceV3Base.TooFewActiveSolvers.selector;
            if (gate != (n < 3)) ++wrongRefusals;
        }
    }
}

contract SolversGateInvariantTest is RaceV3Setup {
    SolversGateHandler internal handler;

    function setUp() public {
        gateOpen = false;
        _deployRace(3);
        uint256[] memory bs = new uint256[](2);
        for (uint256 i; i < 2; ++i) {
            uint256 issueId = _register();
            _check(rc.issue(issueId).check, true);
            bs[i] = rc.openBounty(issueId);
        }
        handler = new SolversGateHandler(rc, book, address(usd), bs);
        for (uint256 i; i < 4; ++i) {
            address who = address(uint160(0xF000 + i));
            usd.mint(who, 1e15);
            vm.prank(who);
            usd.approve(address(rc), type(uint256).max);
        }
        targetContract(address(handler));
    }

    /// No pledge lands while fewer than three solvers are active, and none is refused by the gate otherwise.
    function invariant_noPledgeBelowTheMinimum() public view {
        assertEq(handler.landedBelowMin(), 0);
        assertEq(handler.wrongRefusals(), 0);
    }

    /// The book's count is the identities active within ACTIVE_WINDOW, readable by anyone.
    function invariant_countIsTheActiveIdentities() public view {
        assertEq(book.activeCount(), handler.ghostCount());
        assertEq(book.pledgesOpen(), handler.ghostCount() >= 3);
    }

    /// The handler reaches both sides of the gate.
    function test_handlerReachesBothSides() public {
        handler.pledge(0, 5);
        assertEq(handler.refused(), 1);
        handler.merged(0);
        handler.merged(1);
        handler.merged(2);
        handler.pledge(1, 5);
        assertEq(handler.pledges(), 1);
        for (uint256 i; i < 4; ++i) {
            handler.passTime(book.ACTIVE_WINDOW() / 3); // past the window: nobody active
        }
        handler.pledge(2, 5);
        assertEq(handler.refused(), 2);
        assertEq(handler.landedBelowMin(), 0);
        assertEq(handler.wrongRefusals(), 0);
    }
}
