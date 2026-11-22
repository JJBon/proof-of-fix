// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {console} from "forge-std/Test.sol";
import {Panels} from "../../src/v3/Panels.sol";
import {Status, Kind, Submission, Panel} from "../../src/v3/PanelsBase.sol";
import {RaceV3Base} from "../../src/v3/RaceV3Base.sol";
import {PanelRulesLib} from "../../src/v3/PanelRules.sol";
import {RaceV3Setup} from "./helpers/RaceV3Setup.sol";
import {TEST_REPO} from "./helpers/SuiteWindows.sol";

/// proof-of-fix#251, contract batch 4 (design L24, L25; specs/panel-liveness, "A lapsed challenge leaves the verdict and
/// returns the stake"; specs/judge-panels, "The largest issue-tier panel is set per deployment"), on the real race: a
/// check's deposit and a challenge's cover priced for the deployment's panels, a lapsed challenge's or test dispute's
/// stake and cover returned whole with no reward, and a released challenge panel's revealed seats paid.
contract ChallengesEndV3Test is RaceV3Setup {
    bytes32 constant FIX = keccak256("fix");

    function _judgeFee() internal pure override returns (uint256) {
        return 0; // the Sepolia launch's taxi fare: a fix posts FeesV3's worst-case deposit
    }

    /// A pass on a deployment where its challenge can't be drawn: 3 validators (a panel of 3, nobody outside it) and
    /// three families seated, so neither a fresh panel nor D27's second draw.
    function _unchallengeablePass() internal returns (uint256 b, uint256 id) {
        _deployRace(2);
        _knowFamilies(3);
        b = _openBounty();
        id = _commit(solver1, b, FIX);
        _judgeCheck(id, true);
    }

    /// Scenario "No panel by the deadline", at the race: the challenger posted its stake and cover; the challenge lapses
    /// at CHALLENGE_DEADLINE, and `settleLapse` returns both whole. The verdict stands, nothing goes to the accused, and
    /// the challenge's panel can't be settled as if it had been judged.
    function test_aLapsedChallengeReturnsTheStakeAndCover() public {
        (uint256 b, uint256 id) = _unchallengeablePass();
        _fund(bob, 100 * C);
        uint256 before = usd.balanceOf(bob);
        vm.prank(bob);
        rc.challenge(id, keccak256("evidence"));
        RaceV3Base.Challenge memory c = rc.challengeOf(id);
        assertEq(before - usd.balanceOf(bob), c.stake + c.cover);
        assertEq(c.cover, fees.depositFor(id, TEST_REPO, 7), "the defaults: the cover for 7");
        _rollPast(pn.submission(id).challengeBlock);
        pn.drawChallenge(id);
        assertEq(pn.submission(id).challengePid, 0, "it waits");
        vm.expectRevert(RaceV3Base.Refused.selector); // not lapsed yet
        rc.settleLapse(id);
        vm.warp(pn.submission(id).challengeBy + 1);
        pn.lapseChallenge(id);
        assertTrue(pn.submission(id).filedLapsed);
        uint256 owed = _owed(bob);
        vm.expectEmit(true, true, false, true);
        emit RaceV3Base.ChallengeLapsed(id, bob, c.stake + c.cover);
        uint256 g = gasleft();
        rc.settleLapse(id);
        console.log("settleLapse (stake and cover back):", g - gasleft());
        assertEq(_owed(bob), owed + c.stake + c.cover, "stake and cover back whole");
        assertEq(rc.challengeOf(id).challenger, address(0));
        vm.expectRevert(RaceV3Base.Refused.selector); // once
        rc.settleLapse(id);
        assertTrue(pn.submission(id).pass, "the verdict stands");
        assertEq(uint256(rc.submission(id).outcome), uint256(RaceV3Base.Outcome.Pass));
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Won));
        _assertBooks();
    }

    /// Scenario "A test dispute lapses": the pass stands, the disputer gets its stake (D21's) and cover back, and no
    /// reward is paid.
    function test_aTestDisputeLapses() public {
        (uint256 b, uint256 id) = _unchallengeablePass();
        _fund(bob, 100 * C);
        uint256 before = usd.balanceOf(bob);
        vm.prank(bob);
        rc.dispute(id, TEST);
        RaceV3Base.Challenge memory c = rc.challengeOf(id);
        assertTrue(c.test);
        assertEq(before - usd.balanceOf(bob), c.stake + c.cover);
        vm.warp(pn.submission(id).challengeBy + 1);
        pn.lapseChallenge(id);
        vm.recordLogs();
        rc.settleLapse(id);
        assertEq(_owed(bob), c.stake + c.cover);
        assertEq(usd.balanceOf(bob) + _owed(bob), before, "nothing lost, nothing gained: no reward");
        assertFalse(book.isActive(bob));
        assertTrue(pn.submission(id).pass);
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Won));
        _assertBooks();
    }

    /// The race's settlement follows Panels: a filed challenge that lapsed isn't settled as judged, and a challenge can be
    /// filed again (up to MAX_REDRAWS lapses) once the lapse is settled.
    function test_aLapseIsSettledOnlyAsALapse() public {
        (, uint256 id) = _unchallengeablePass();
        _fund(bob, 1_000 * C);
        for (uint256 i; i < pn.MAX_REDRAWS(); ++i) {
            vm.prank(bob);
            rc.challenge(id, keccak256("evidence"));
            vm.prank(bob);
            vm.expectRevert(RaceV3Base.Refused.selector); // one at a time, until its lapse is settled
            rc.challenge(id, keccak256("evidence"));
            vm.warp(pn.submission(id).challengeBy + 1);
            pn.lapseChallenge(id);
            rc.settleLapse(id);
        }
        vm.prank(bob);
        vm.expectRevert(Panels.TooManyLapses.selector);
        rc.challenge(id, keccak256("evidence"));
        _assertBooks();
    }

    /// L24 at the race: on the launch's rules (`kTop` 3, `Same`) a fix's deposit is FeesV3's worst case for 3 judges and
    /// a challenge's cover for 3, not 7; with the defaults both are for 7.
    function test_depositsAndCoversArePricedForKTop() public {
        rules = PanelRulesLib.launch();
        _deployRace(6);
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        assertEq(rc.submission(id).deposit, fees.maxDeposit(TEST_REPO, 3), "the deposit for kTop judges");
        assertLt(fees.maxDeposit(TEST_REPO, 3), fees.maxDeposit(TEST_REPO, 7));
        uint256 pid = _judgeCheck(id, true);
        assertEq(pn.panel(pid).k, 3);
        _fund(bob, 100 * C);
        vm.prank(bob);
        rc.dispute(id, TEST);
        assertEq(rc.challengeOf(id).cover, fees.depositFor(id, TEST_REPO, 3), "the cover for kTop judges");
        rules = PanelRulesLib.strict();
        _deployRace(6);
        b = _openBounty();
        id = _commit(solver1, b, FIX);
        assertEq(rc.submission(id).deposit, fees.maxDeposit(TEST_REPO, 7));
    }

    /// A released challenge panel's seats that revealed with receipts are paid as an upheld challenge's panel is, from
    /// the check's deposit and the pool, never from the cover; its silent seat is slashed; the challenge, released before
    /// its deadline, waits for a redraw.
    function test_aReleasedChallengePanelsRevealedSeatsArePaid() public {
        rules = PanelRulesLib.launch();
        _deployRace(6); // 7 validators: a panel of 3, 4 outside it
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        uint256 pid = _judgeCheck(id, true);
        b;
        _fund(bob, 100 * C);
        vm.prank(bob);
        rc.challenge(id, keccak256("evidence"));
        _rollPast(pn.submission(id).challengeBlock);
        pn.drawChallenge(id);
        uint256 cpid = pn.submission(id).challengePid;
        require(cpid != 0, "a challenge panel");
        // the one validator outside both panels pauses: nobody can replace a missed reveal
        address[] memory cj = pn.judges(cpid);
        address[] memory oj = pn.judges(pid);
        address spare;
        uint256 n = reg.eligibleCount(1);
        for (uint256 i; i < n && spare == address(0); ++i) {
            address k = reg.eligibleAt(1, i);
            if (!_contains(cj, k) && !_contains(oj, k)) spare = k;
        }
        require(spare != address(0), "one validator outside both panels");
        vm.prank(spare);
        pn.setCapacity(spare, 0);
        vm.roll(vm.getBlockNumber() + pn.CAP_DELAY() + 1);
        for (uint256 i; i < 3; ++i) {
            _seal(cpid, cj[i], true);
        }
        vm.warp(pn.panel(cpid).sealBy + 1);
        for (uint256 i; i < 2; ++i) {
            _reveal(cpid, cj[i]);
            _receipt(cpid, cj[i]);
            _reportSeat(cpid, cj[i]);
        }
        vm.warp(pn.panel(cpid).revealBy + 1);
        pn.advance(cpid); // the third missed its reveal: slashed, and nobody can take its seat
        assertEq(pn.panel(cpid).seats, 2);
        vm.warp(pn.panel(cpid).revealBy + pn.STUCK_GRACE() + 1);
        pn.release(cpid);
        assertTrue(pn.panel(cpid).closed);
        assertTrue(pn.submission(id).challengeOpen, "before the deadline: it waits for a redraw");
        uint256 cover = rc.challengeOf(id).cover;
        uint256 deposit = rc.submission(id).deposit;
        uint256 op0 = _owed(reg.validator(cj[0]).operator);
        if (vm.getBlockTimestamp() <= pn.panel(cpid).revealBy + 1 days) vm.warp(pn.panel(cpid).revealBy + 1 days + 1);
        rc.payPanel(cpid);
        assertGt(_owed(reg.validator(cj[0]).operator), op0, "a revealed seat paid");
        assertLt(rc.submission(id).deposit, deposit, "from the check's deposit");
        assertEq(rc.challengeOf(id).cover, cover, "not from the cover");
        vm.expectRevert(RaceV3Base.Refused.selector); // once
        rc.payPanel(cpid);
        _assertBooks();
    }

}
