// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Kind, Panel, Status} from "../../src/v3/PanelsBase.sol";
import {RaceV3Base} from "../../src/v3/RaceV3Base.sol";
import {RaceV3Setup} from "./helpers/RaceV3Setup.sol";
import {PanelLivenessV3Test} from "./LivenessV3.t.sol";
import {TEST_REPO} from "./helpers/SuiteWindows.sol";

/// The Sepolia launch's fee mode (owner, 2026-11-19; #132 D30 as ADR 0007 records it for the launch): the pure taxi
/// fare. `Config.judgeFee` is 0: a fix's submission posts FeesV3's worst-case deposit for K_MAX judges, its judges are
/// paid by the meter, and whatever is left returns to the solver, pass or fail, withdrawn, timed out or released; the
/// judges' pay beyond the deposit comes from the sponsors' pool. And a solver pays only the metered validation: the
/// attempt, evaluation (late submission) and appeal fees are 0, as the Sepolia deploy script sets them. The flat fee's
/// behaviour (`judgeFee` above 0) is the rest of the v3 suite's.
contract TaxiV3Test is RaceV3Setup {
    bytes32 constant FIX = keccak256("fix");
    bytes32 constant FIX2 = keccak256("fix2");

    function setUp() public {
        _deployRace(3);
    }

    function _judgeFee() internal pure override returns (uint256) {
        return 0;
    }

    /// The Sepolia deploy script's race configuration: no attempt, evaluation or appeal fee.
    function _config() internal view override returns (RaceV3Base.Config memory c) {
        c = super._config();
        c.attemptFee = 0;
        c.evaluationFee = 0;
        c.appealFee = 0;
    }

    function _fundersAreValidators(uint256 b) internal {
        for (uint256 i = 1; i <= 3; ++i) {
            address key = reg.validatorAt(i);
            _pledge(reg.validator(key).operator, b, C / 10);
        }
    }

    function test_theTaxiFare() public view {
        assertEq(rc.getConfig().judgeFee, 0);
        assertEq(rc.getConfig().attemptFee, 0);
        assertEq(rc.getConfig().evaluationFee, 0);
        assertEq(rc.getConfig().appealFee, 0);
    }

    /// A fix that passes: its deposit is FeesV3's worst case, its judges are paid by the meter, the rest returns.
    function test_aPassRefundsTheRest() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        assertEq(rc.submission(id).deposit, fees.maxDeposit(TEST_REPO, 7));
        _judgeCheck(id, true);
        assertGt(rc.submission(id).charged, 0);
        rc.claim(b, FIX, _head(), "salt");
        _finalAndMerge(b, id);
        vm.warp(block.timestamp + 1 days + 1);
        uint256 owed0 = _owed(solver1);
        uint256 pooled = pool3.held(address(usd));
        uint256 left = rc.submission(id).deposit;
        assertGt(left, 0);
        rc.finish(id);
        assertEq(_owed(solver1), owed0 + left);
        assertEq(pool3.held(address(usd)), pooled); // nothing kept by the pool
        _assertBooks();
    }

    /// A fix that fails: the same; a rejection costs the solver only its checks.
    function test_aFailRefundsTheRest() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        uint256 deposit = rc.submission(id).deposit;
        _judgeCheck(id, false);
        _final(id);
        vm.warp(block.timestamp + 1 days + 1);
        uint256 owed0 = _owed(solver1);
        uint256 pooled = pool3.held(address(usd));
        rc.finish(id);
        RaceV3Base.Submission memory s = rc.submission(id);
        assertEq(_owed(solver1) - owed0, deposit - s.charged);
        assertEq(pool3.held(address(usd)), pooled);
        _assertBooks();
    }

    /// A withdrawn fix: no panel was seated, its whole deposit returns.
    function test_aWithdrawalRefundsTheWholeDeposit() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        uint256 deposit = rc.submission(id).deposit;
        uint256 owed0 = _owed(solver1);
        uint256 pooled = pool3.held(address(usd));
        vm.prank(solver1);
        rc.withdraw(id);
        assertEq(_owed(solver1), owed0 + deposit);
        assertEq(pool3.held(address(usd)), pooled);
        _assertBooks();
    }

    /// A fix no panel took within resultDays: its whole deposit returns.
    function test_aTimeOutRefundsTheWholeDeposit() public {
        _reputation(solver1, 200 * C);
        uint256 b = _openBounty();
        _fundersAreValidators(b);
        _pledge(bob, b, 100 * C);
        uint256 id = _commit(solver1, b, FIX);
        _draw(id); // waits: above k = 1's limit, every other validator a party
        uint256 deposit = rc.submission(id).deposit;
        uint256 owed0 = _owed(solver1);
        _toDay(rc.day() + 7);
        rc.timeOut(id);
        assertEq(_owed(solver1), owed0 + deposit);
        _assertBooks();
    }

    /// The judges' pay beyond the deposit comes from the sponsors' pool: a k = 1 verdict's audits paid after its
    /// deposit's rest went back to the solver are paid by the pool, whole.
    function test_judgesBeyondTheDepositArePaidByThePool() public {
        uint256 b = _openBounty();
        _fundersAreValidators(b);
        uint256 id = _commit(solver1, b, FIX);
        uint256 pid = _draw(id);
        _judge(pid, _votes(1, 1));
        _reportAll(pid);
        rc.result(id);
        _network(3, FAMILIES, 3);
        pn.startWindow(id);
        uint256 before = pn.panelCount();
        _runAudits(id, true);
        uint256[] memory audits = new uint256[](pn.panelCount() - before);
        uint256 n;
        for (uint256 q = before + 1; q <= pn.panelCount(); ++q) {
            Panel memory p = pn.panel(q);
            if (p.kind != Kind.Audit || p.id != id) continue;
            _reportAll(q);
            audits[n++] = q;
        }
        assertEq(n, 2);
        uint256 at = pn.submission(id).finalAt;
        if (vm.getBlockTimestamp() < at) vm.warp(at);
        pn.finalize(id);
        vm.warp(block.timestamp + 1 days + 1);
        uint256 owed0 = _owed(solver1);
        uint256 left = rc.submission(id).deposit;
        rc.finish(id);
        assertEq(_owed(solver1), owed0 + left); // the rest back to the solver first
        usd.mint(address(this), 50 * C);
        usd.approve(address(pool3), 50 * C);
        pool3.fund(address(usd), 50 * C);
        for (uint256 i; i < n; ++i) {
            uint256 pooled = pool3.held(address(usd));
            address op = reg.validator(pn.judges(audits[i])[0]).operator;
            uint256 got0 = usd.balanceOf(op);
            rc.payPanel(audits[i]);
            uint256 got = usd.balanceOf(op) - got0;
            assertGt(got, 0);
            assertEq(pooled - pool3.held(address(usd)), got); // from the pool, not the deposit
        }
        assertEq(rc.submission(id).deposit, 0);
        _assertBooks();
    }

    // ---------- a solver pays only the metered validation (the three fees at 0) ----------

    /// An attempt with a fee of 0: it locks the price, and nothing is charged.
    function test_anAttemptAtZeroFee() public {
        uint256 b = _openBounty();
        uint256 owedInfra = _owed(infra);
        uint256 bal = usd.balanceOf(solver1);
        vm.prank(solver1);
        rc.attempt(b);
        assertTrue(rc.bounty(b).locked);
        assertEq(rc.bounty(b).attempting, 1);
        assertEq(usd.balanceOf(solver1), bal);
        assertEq(_owed(infra), owedInfra);
    }

    /// A late submission with an evaluation fee of 0: it isn't checked, emits TooLate, returns 0, charges nothing.
    function test_aLateCommitAtZeroFee() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        _judgeCheck(id, true);
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Won));
        _fund(solver2, 100 * C);
        uint256 bal = usd.balanceOf(solver2);
        uint256 owedInfra = _owed(infra);
        bytes32 c = _commitment(FIX2, solver2);
        vm.expectEmit(true, true, false, false, address(rc));
        emit RaceV3Base.TooLate(b, solver2);
        vm.prank(solver2);
        assertEq(rc.commit(b, c), 0);
        assertEq(usd.balanceOf(solver2), bal);
        assertEq(_owed(infra), owedInfra);
    }

    /// An appeal with an appeal fee of 0 and no stake (owner, 2026-11-19): the appellant posts the new check's deposit,
    /// nothing more, and gets its rest back after the appeal is judged.
    function test_anAppealAtZeroFee() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        _judgeCheck(id, false);
        _fund(solver1, 100 * C);
        uint256 bal = usd.balanceOf(solver1);
        uint256 owedInfra = _owed(infra);
        vm.prank(solver1);
        uint256 again = rc.appeal(id, TEST);
        uint256 deposit = rc.submission(again).deposit;
        assertEq(bal - usd.balanceOf(solver1), deposit);
        assertEq(deposit, fees.maxDeposit(TEST_REPO, 7));
        assertEq(_owed(infra), owedInfra);
        assertEq(uint256(pn.submission(again).status), uint256(Status.Sealed));
        _judgeCheck(again, false);
        _final(again);
        vm.warp(block.timestamp + 1 days + 1);
        uint256 owed0 = _owed(solver1);
        uint256 pooled = pool3.held(address(usd));
        rc.finish(again);
        assertEq(_owed(solver1) - owed0, deposit - rc.submission(again).charged); // a failed appeal: the rest back
        assertEq(pool3.held(address(usd)), pooled);
    }
}

/// L19's liveness scenarios under the taxi fare: a released check's deposit returns whole to its solver.
contract PanelLivenessV3TaxiTest is PanelLivenessV3Test {
    function _judgeFee() internal pure override returns (uint256) {
        return 0;
    }
}
