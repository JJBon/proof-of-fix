// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {console} from "forge-std/Test.sol";
import {IValidators} from "../../src/v3/IValidators.sol";
import {Panels} from "../../src/v3/Panels.sol";
import {Status, Kind, Submission, Panel} from "../../src/v3/PanelsBase.sol";
import {RaceV3Base} from "../../src/v3/RaceV3Base.sol";
import {RaceV3Setup} from "./helpers/RaceV3Setup.sol";
import {PanelsSetup} from "./helpers/PanelsSetup.sol";

/// proof-of-fix#251, contract batch 2, task 3.13 (design L19; specs/panel-liveness): a panel that can't complete is
/// released, a waiting submission is redrawn with a fresh seed, and a check that can't be judged is refunded, on the
/// real Panels, FeesV3 and RaceV3. Each scenario of the spec is tested under its name.
contract PanelLivenessV3Test is RaceV3Setup {
    bytes32 constant FIX = keccak256("fix");

    function setUp() public {
        _deployRace(2); // the genesis validator and two more: a panel of 3 seats every eligible validator
    }

    /// A drawn round of check `id` where two judges seal and the third stays silent: the silent seat is slashed and
    /// can't be replaced (every eligible validator already sat), then the round is released STUCK_GRACE after its
    /// reveal deadline. Returns the panel.
    function _stuckRound(uint256 id) internal returns (uint256 pid) {
        if (pn.submission(id).status == Status.Waiting) {
            vm.warp(pn.submission(id).retryAt);
            _draw(id); // re-targets: a fresh seed block and snapshot
        }
        pid = _draw(id);
        require(pid != 0, "no panel");
        address[] memory js = pn.judges(pid);
        _seal(pid, js[0], true);
        _seal(pid, js[1], true);
        vm.warp(pn.panel(pid).sealBy + 1);
        pn.advance(pid);
        assertEq(pn.panel(pid).seats, 2); // replacements exhausted
        vm.warp(pn.panel(pid).revealBy + pn.STUCK_GRACE());
        vm.expectRevert(Panels.NothingDue.selector); // not before the reveal deadline plus STUCK_GRACE
        pn.release(pid);
        vm.warp(pn.panel(pid).revealBy + pn.STUCK_GRACE() + 1);
        pn.release(pid);
    }

    // ---------- A panel that can't complete is released ----------

    /// Scenario "Replacements exhausted": a drawn judge stays silent and every eligible validator has already been
    /// drawn; at the reveal deadline plus STUCK_GRACE the round ends, the silent seat is slashed, and the submission is
    /// waiting with a redraw scheduled. The judges who sealed are closed with no slash.
    function test_replacementsExhausted() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        uint256 pid = _draw(id);
        address[] memory js = pn.judges(pid);
        uint256[3] memory bonds = [_bond(js[0]), _bond(js[1]), _bond(js[2])];
        _seal(pid, js[0], true);
        _seal(pid, js[1], true);
        vm.warp(pn.panel(pid).sealBy + 1);
        pn.advance(pid);
        assertEq(_bond(js[2]), bonds[2] - 5e6); // silence, as for any silence
        assertEq(pn.panel(pid).seats, 2);
        vm.expectRevert(Panels.NotReady.selector); // nobody left to replace it
        pn.refill(pid);
        assertEq(reg.validator(js[0]).openVerdicts, 1);
        vm.warp(pn.panel(pid).revealBy + pn.STUCK_GRACE() + 1);
        vm.expectEmit(true, true, false, true);
        emit Panels.Released(id, pid, 1);
        pn.release(pid);
        Submission memory s = pn.submission(id);
        assertEq(uint256(s.status), uint256(Status.Waiting));
        assertEq(s.redraws, 1);
        assertEq(s.pid, 0);
        assertEq(s.retryAt, block.timestamp + pn.RETRY_DELAY()); // the scheduled redraw
        assertTrue(pn.panel(pid).closed);
        for (uint256 i; i < 2; ++i) {
            assertEq(_bond(js[i]), bonds[i]); // sealed, couldn't reveal: no slash
            assertEq(reg.validator(js[i]).openVerdicts, 0); // and their verdicts closed
        }
        vm.expectRevert(Panels.NotOpen.selector); // released once
        pn.release(pid);
        vm.expectRevert(Panels.NotOpen.selector);
        pn.advance(pid);
        // the race: nothing decided, nothing refunded yet
        assertEq(uint256(rc.submission(id).outcome), uint256(RaceV3Base.Outcome.None));
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Open));
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.release(id);
    }

    /// A panel whose seats are all filled isn't stuck (silence there is `advance`'s), and a shadow panel is never
    /// released.
    function test_onlyAnExhaustedPanelIsReleased() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        uint256 pid = _draw(id);
        vm.warp(pn.panel(pid).revealBy + pn.STUCK_GRACE() + 1);
        vm.expectRevert(Panels.NothingDue.selector);
        pn.release(pid);
    }

    /// Scenario "Redrawn when validators join": a submission waiting after a released round is drawn again with a
    /// fresh seed once a new validator becomes eligible, before RETRY_DELAY has passed.
    function test_redrawnWhenValidatorsJoin() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        uint256 pid = _stuckRound(id);
        bytes32 oldSeed = pn.panel(pid).seed;
        vm.expectRevert(Panels.NothingChanged.selector); // nothing changed, and RETRY_DELAY hasn't passed
        pn.draw(id);
        _network(1, FAMILIES, 3); // a new validator becomes eligible
        assertLt(block.timestamp, pn.submission(id).retryAt);
        uint256 seedBlock = pn.submission(id).seedBlock;
        pn.draw(id); // re-targets: a fresh seed block and snapshot
        assertEq(uint256(pn.submission(id).status), uint256(Status.Sealed));
        assertGt(pn.submission(id).seedBlock, seedBlock);
        uint256 again = _draw(id);
        assertTrue(again != 0 && again != pid);
        assertTrue(pn.panel(again).seed != oldSeed);
        assertEq(pn.submission(id).redraws, 1);
    }

    /// With no change in the registry, the redraw comes at RETRY_DELAY.
    function test_redrawnAfterRetryDelay() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        _stuckRound(id);
        vm.warp(pn.submission(id).retryAt - 1);
        vm.expectRevert(Panels.NothingChanged.selector);
        pn.draw(id);
        vm.warp(pn.submission(id).retryAt);
        pn.draw(id);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Sealed));
        assertTrue(_draw(id) != 0);
    }

    // ---------- A bounty that can't be judged is refunded ----------

    /// Scenario "Too many released rounds": after MAX_REDRAWS released rounds the bounty is refunded to its funders,
    /// and the solver's deposit returns whole: no failed verdict, no charge, no slash.
    function test_tooManyReleasedRounds() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        uint256 deposit = rc.submission(id).deposit;
        uint256 stake = rc.issue(rc.bounty(b).issue).stake;
        uint256 owedSolver = _owed(solver1);
        uint256 owedReporter = _owed(reporter);
        for (uint256 r = 1; r < pn.MAX_REDRAWS(); ++r) {
            _stuckRound(id);
            assertEq(uint256(pn.submission(id).status), uint256(Status.Waiting));
            assertEq(pn.submission(id).redraws, r);
        }
        _stuckRound(id); // the MAX_REDRAWS-th: Panels.Refunded
        assertEq(uint256(pn.submission(id).status), uint256(Status.Released));
        vm.expectRevert(Panels.WrongStatus.selector); // never drawn again
        pn.draw(id);
        vm.prank(makeAddr("anyone"));
        rc.release(id);
        RaceV3Base.Submission memory s = rc.submission(id);
        assertEq(uint256(s.outcome), uint256(RaceV3Base.Outcome.Released));
        assertEq(s.charged, 0);
        assertTrue(s.done);
        assertEq(_owed(solver1), owedSolver + deposit); // the solver's claim released whole
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Refunded));
        assertEq(uint256(rc.issue(rc.bounty(b).issue).state), uint256(RaceV3Base.IssueState.Returned));
        assertEq(_owed(reporter), owedReporter + stake);
        vm.prank(alice);
        rc.claimRefund(b, address(usd)); // the funders get their pledges back
        assertEq(rc.held(b, address(usd)), 0);
        vm.expectRevert(RaceV3Base.Refused.selector); // once
        rc.release(id);
        _assertBooks();
    }

    /// The bounty's deadline (RaceV3's resultDays after the commitment): a submission parked after a released round is
    /// refunded then, without waiting for MAX_REDRAWS; the old time-out is refused for it.
    function test_refundedAtTheDeadline() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        _stuckRound(id);
        uint256 deadline = rc.submission(id).day + _config().resultDays;
        _toDay(deadline - 1);
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.release(id);
        _toDay(deadline);
        vm.expectRevert(RaceV3Base.Refused.selector); // a check with a released round ends by `release`
        rc.timeOut(id);
        rc.release(id);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Released));
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Refunded));
        _assertBooks();
    }

    /// Only the race abandons a submission, and only a parked one with a released round.
    function test_abandonIsTheRacesAndOnlyForAParkedCheck() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        vm.expectRevert(Panels.NotRace.selector);
        pn.abandon(id);
        _toDay(rc.day() + 30);
        vm.expectRevert(RaceV3Base.NotYet.selector); // never released: the ordinary time-out applies
        rc.release(id);
        rc.timeOut(id);
        assertEq(uint256(rc.submission(id).outcome), uint256(RaceV3Base.Outcome.TimedOut));
    }

    /// A registration check that can't be judged: its issue is returned (stake and deposit back), as when it's
    /// withdrawn.
    function test_aRegistrationCheckThatCantBeJudged() public {
        uint256 i = _register();
        uint256 check = rc.issue(i).check;
        uint256 back = rc.issue(i).stake + rc.submission(check).deposit;
        uint256 owed = _owed(reporter);
        for (uint256 r; r < pn.MAX_REDRAWS(); ++r) {
            _stuckRound(check);
        }
        rc.release(check);
        assertEq(uint256(rc.issue(i).state), uint256(RaceV3Base.IssueState.Returned));
        assertEq(_owed(reporter), owed + back);
        _assertBooks();
    }

    /// Audits too (L19's audits paragraph): a claimed k = 1 pass whose audits no validator can take (those outside its
    /// panel are its parties, or paused their capacity) is released after STUCK_GRACE, drawn again from a fresh audit
    /// block, and refunded at the MAX_REDRAWS-th round: the award closes with nothing earned, the bounty is refunded,
    /// its judge's verdict closes, and the paused validators are never slashed.
    function test_anAuditThatCantBeDrawnIsReleased() public {
        uint256 b = _openBounty();
        for (uint256 v = 1; v <= 2; ++v) {
            _pledge(reg.validator(reg.validatorAt(v)).operator, b, C / 10); // parties: never its judges or auditors
        }
        uint256 id = _commit(solver1, b, FIX);
        uint256 pid = _draw(id);
        assertEq(pn.panel(pid).k, 1);
        _judge(pid, _votes(1, 1));
        _reportAll(pid);
        rc.result(id);
        rc.claim(b, FIX, _head(), "salt");
        assertEq(uint256(pn.submission(id).status), uint256(Status.Held));
        // while held, its audits find nobody either, but the hold, not the audits, keeps it from finality: no release
        _tryAudits(id);
        assertGt(pn.submission(id).auditStuckAt, 0);
        vm.warp(pn.submission(id).auditStuckAt + pn.STUCK_GRACE() + 1);
        vm.expectRevert(Panels.WrongStatus.selector);
        pn.releaseAudits(id);
        address[] memory fresh = _network(3, FAMILIES, 3);
        for (uint256 i; i < 3; ++i) {
            vm.prank(fresh[i]);
            pn.setCapacity(fresh[i], 0); // paused, from CAP_DELAY blocks on
        }
        pn.startWindow(id); // its three challengers have room until then
        assertEq(pn.submission(id).auditStuckAt, block.timestamp); // the stuck clock restarts with the window
        vm.roll(vm.getBlockNumber() + pn.CAP_DELAY());
        _tryAudits(id);
        Submission memory s = pn.submission(id);
        assertEq(s.auditsDrawn, 0);
        assertGe(s.auditsDue, 2); // K1_AUDITS, and maybe the random one
        assertGt(s.auditStuckAt, 0);
        vm.expectRevert(Panels.NothingDue.selector); // not before STUCK_GRACE
        pn.releaseAudits(id);
        for (uint256 r = 1; r <= pn.MAX_REDRAWS(); ++r) {
            vm.warp(pn.submission(id).auditStuckAt + pn.STUCK_GRACE() + 1);
            pn.releaseAudits(id);
            if (r < pn.MAX_REDRAWS()) {
                assertEq(pn.submission(id).redraws, r);
                _tryAudits(id);
            }
        }
        assertEq(uint256(pn.submission(id).status), uint256(Status.Released));
        vm.expectRevert(Panels.WrongStatus.selector);
        pn.finalize(id);
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.merge(b); // never final: never merged
        rc.release(id);
        assertEq(uint256(rc.submission(id).outcome), uint256(RaceV3Base.Outcome.Released));
        assertTrue(rc.award(b, 1).closed);
        assertEq(rc.award(b, 1).earned, 0);
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Refunded));
        for (uint256 i; i < 3; ++i) {
            assertEq(_bond(fresh[i]), FULL_BOND); // paused: skipped, never slashed
            assertEq(reg.progress(fresh[i]).misses, 0);
        }
        assertEq(reg.validator(genesisKey).openVerdicts, 0);
        _assertBooks();
    }

    /// The gas of L19's calls (call frame only), for reports/contract-v3.md.
    function test_gasLiveness() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        for (uint256 r = 1; r <= pn.MAX_REDRAWS(); ++r) {
            if (pn.submission(id).status == Status.Waiting) {
                vm.warp(pn.submission(id).retryAt);
                uint256 g0 = gasleft();
                pn.draw(id);
                if (r == 2) console.log("draw, a waiting submission re-targeted at its retryAt:", g0 - gasleft());
            }
            uint256 pid = _draw(id);
            address[] memory js = pn.judges(pid);
            _seal(pid, js[0], true);
            _seal(pid, js[1], true);
            vm.warp(pn.panel(pid).sealBy + 1);
            pn.advance(pid);
            vm.warp(pn.panel(pid).revealBy + pn.STUCK_GRACE() + 1);
            uint256 g = gasleft();
            pn.release(pid);
            console.log(r < pn.MAX_REDRAWS() ? "Panels.release (k = 3, two sealed seats closed; back to waiting):"
                                              : "Panels.release (the MAX_REDRAWS-th: Released):", g - gasleft());
        }
        uint256 g1 = gasleft();
        rc.release(id);
        console.log("RaceV3.release (deposit back, bounty refunded, issue returned):", g1 - gasleft());
    }

    /// drawAudits from its audit block until it waits for the registry to change (the contract refuses until then).
    function _tryAudits(uint256 id) internal {
        for (uint256 t; t < 3; ++t) {
            Submission memory s = pn.submission(id);
            if (s.auditDecided && s.auditsDrawn == s.auditsDue) return;
            if (s.auditWaits && reg.epoch() + 1 == s.auditEpoch) return;
            if (!s.auditWaits) _rollPast(s.auditBlock);
            pn.drawAudits(id);
        }
    }
}

/// proof-of-fix#251, contract batch 2, task 3.14 and the on-chain pause (design L16; #253's spending controls):
/// MAX_CHECKS_PER_HOUR per validator over a trailing hour, a full or paused validator skipped with no slash, no room
/// anywhere makes a submission wait, and a pause can't dodge a draw whose seed is already known.
contract CapacityV3Test is PanelsSetup {
    uint256 internal nextId = 1;

    function setUp() public {
        _deployVersion(3, false);
    }

    function _id() internal returns (uint256) {
        return nextId++;
    }

    /// The defaults: 5 checks a trailing hour, a ceiling of 16, the repository cap off.
    function test_theDefaults() public view {
        assertEq(pn.CHECKS_DEFAULT(), 5);
        assertEq(pn.CHECKS_CEILING(), 16);
        assertEq(pn.REPO_CHECKS_PER_HOUR(), 0);
        assertEq(pn.CAP_DELAY(), 256 + pn.SEED_DELAY() + 1);
        (uint256 checks, uint256 next, uint256 from, bool room) = pn.capacity(genesisKey);
        assertEq(checks, 5);
        assertEq(next, 5);
        assertEq(from, 0);
        assertTrue(room);
    }

    /// A validator that took MAX_CHECKS_PER_HOUR seats in the trailing hour is skipped, never slashed; it has room
    /// again once its oldest of them is an hour old. With no room anywhere the submission waits, and is retried after
    /// the capacity's window.
    function test_aFullValidatorIsSkippedAndNoRoomWaits() public {
        _network(6, FAMILIES, 3); // seven validators: each draw of k = 7 seats them all
        for (uint256 i; i < 5; ++i) {
            uint256 pid = _openAndDraw(_id(), 40e6);
            assertEq(pn.panel(pid).k, 7);
        }
        (,,, bool room) = pn.capacity(genesisKey);
        assertFalse(room);
        uint256 bond = _bond(genesisKey);
        uint256 id = _id();
        assertEq(_openAndDraw(id, 40e6), 0); // nobody has room: it waits
        Submission memory s = pn.submission(id);
        assertEq(uint256(s.status), uint256(Status.Waiting));
        assertEq(s.retryAt, block.timestamp + pn.CAP_WINDOW()); // retried when the capacity frees, not RETRY_DELAY
        assertEq(_bond(genesisKey), bond); // skipped, not slashed
        assertEq(reg.progress(genesisKey).misses, 0);
        vm.expectRevert(Panels.NothingChanged.selector);
        pn.draw(id);
        vm.warp(s.retryAt);
        pn.draw(id); // re-targets
        assertTrue(_draw(id) != 0);
        assertEq(pn.panel(pn.submission(id).pid).k, 7);
    }

    /// A panel that busy validators leave short waits for them (at most the capacity's window) rather than stepping
    /// down to a smaller k: three validators, the genesis one busy, and a check that the network can judge with 3.
    function test_busyValidatorsMakeItWaitNotShrink() public {
        address[] memory ks = _network(2, FAMILIES, 3);
        for (uint256 i; i < 5; ++i) {
            uint256 id = _id();
            race.setParty(id, reg.validator(ks[0]).operator, true);
            race.setParty(id, reg.validator(ks[1]).operator, true);
            uint256 pid = _openAndDraw(id, 40e6); // parties leave only the genesis validator: k = 1, held
            assertEq(pn.judges(pid)[0], genesisKey);
        }
        (,,, bool room) = pn.capacity(genesisKey);
        assertFalse(room);
        uint256 id = _id();
        assertEq(_openAndDraw(id, 40e6), 0); // k = 3 can't fill while the genesis validator is busy: it waits
        assertEq(pn.submission(id).retryAt, block.timestamp + pn.CAP_WINDOW());
        vm.warp(pn.submission(id).retryAt);
        pn.draw(id);
        uint256 again = _draw(id);
        assertEq(pn.panel(again).k, 3);
    }

    /// One full validator among others: the draw seats the others.
    function test_oneFullValidatorIsSkipped() public {
        address[] memory ks = _network(8, FAMILIES, 3); // nine: each draw of 7 leaves two out
        address full;
        for (uint256 n; n < 20 && full == address(0); ++n) {
            _openAndDraw(_id(), 40e6);
            for (uint256 i; i < ks.length; ++i) {
                (,,, bool room) = pn.capacity(ks[i]);
                if (!room) full = ks[i];
            }
        }
        assertTrue(full != address(0));
        uint256 pid = _openAndDraw(_id(), 40e6);
        if (pid != 0) assertFalse(_contains(pn.judges(pid), full));
        _nextCapWindow();
        (,,, bool again) = pn.capacity(full);
        assertTrue(again);
    }

    /// The on-chain pause (#253): capacity 0, from CAP_DELAY blocks on; meanwhile still drawn; then skipped like a full
    /// validator, with no slash; and back.
    function test_aPausedValidatorIsSkippedWithNoSlash() public {
        address[] memory ks = _network(6, FAMILIES, 3);
        address v = ks[0];
        uint256 from = vm.getBlockNumber() + pn.CAP_DELAY();
        vm.expectEmit(true, false, false, true);
        emit Panels.CapacitySet(v, 0, from);
        vm.prank(v);
        pn.setCapacity(v, 0);
        (uint256 checks, uint256 next,,) = pn.capacity(v);
        assertEq(checks, 5); // still in force
        assertEq(next, 0);
        uint256 pid = _openAndDraw(_id(), 40e6);
        assertTrue(_contains(pn.judges(pid), v)); // a draw before the delay still takes it
        vm.roll(vm.getBlockNumber() + pn.CAP_DELAY());
        _nextCapWindow();
        (checks,,,) = pn.capacity(v);
        assertEq(checks, 0);
        pid = _openAndDraw(_id(), 40e6);
        assertEq(pn.panel(pid).k, 5); // six with room: the panel steps down
        assertFalse(_contains(pn.judges(pid), v));
        assertEq(_bond(v), FULL_BOND);
        assertEq(reg.progress(v).misses, 0);
        // unpaused by its operator
        vm.prank(reg.validator(v).operator);
        pn.setCapacity(v, 5);
        vm.roll(vm.getBlockNumber() + pn.CAP_DELAY());
        _nextCapWindow();
        pid = _openAndDraw(_id(), 40e6);
        assertTrue(_contains(pn.judges(pid), v));
    }

    /// A pause can't dodge a draw whose seed is already known: the change takes effect CAP_DELAY blocks later, after
    /// any draw from a seed block already past (it re-targets after 256 blocks), and no second change is accepted
    /// while one is pending (so a pending unpause can't be cancelled to dodge either).
    function test_aPauseCantDodgeADrawAlreadyMade() public {
        address[] memory ks = _network(6, FAMILIES, 3);
        uint256 id = _id();
        _open(id, 40e6);
        uint256 sb = pn.submission(id).seedBlock;
        _rollPast(sb); // the seed is known now
        (, , address[] memory keys,) = pn.sample(id, _seedFor(id));
        address v = keys[0] == genesisKey ? keys[1] : keys[0];
        vm.prank(v);
        pn.setCapacity(v, 0); // too late for this draw
        vm.roll(sb + 256); // the last block the seed block's hash is still there
        vm.setBlockhash(sb, keccak256(abi.encode("block", sb)));
        pn.draw(id);
        uint256 pid = pn.submission(id).pid;
        assertTrue(_contains(pn.judges(pid), v));
        vm.prank(v);
        vm.expectRevert(Panels.Busy.selector); // one change at a time
        pn.setCapacity(v, 5);
        // the seat already given is judged or slashed as usual
        vm.warp(pn.panel(pid).sealBy + 1);
        uint256 bond = _bond(v);
        pn.advance(pid);
        assertEq(_bond(v), bond - 5e6);
        ks;
    }

    /// The gas of a capacity change, and of a draw that skips paused validators (call frame only).
    function test_gasCapacity() public {
        address[] memory ks = _network(6, FAMILIES, 3);
        vm.prank(ks[0]);
        uint256 g = gasleft();
        pn.setCapacity(ks[0], 0);
        console.log("setCapacity (a first change):", g - gasleft());
        vm.roll(vm.getBlockNumber() + pn.CAP_DELAY());
        vm.prank(ks[0]);
        g = gasleft();
        pn.setCapacity(ks[0], 5);
        console.log("setCapacity (a later change):", g - gasleft());
    }

    /// Only the validator's key or its operator sets its capacity, at most CHECKS_CEILING.
    function test_onlyItsKeyOrOperatorSetsIt() public {
        vm.prank(makeAddr("stranger"));
        vm.expectRevert(Panels.NotYours.selector);
        pn.setCapacity(genesisKey, 0);
        vm.prank(genesisKey);
        vm.expectRevert(Panels.BadParams.selector);
        pn.setCapacity(genesisKey, 17);
        vm.prank(genesisKey);
        pn.setCapacity(genesisKey, 16);
        vm.roll(vm.getBlockNumber() + pn.CAP_DELAY());
        (uint256 checks,,,) = pn.capacity(genesisKey);
        assertEq(checks, 16);
    }

    /// A paused validator isn't counted among a k = 1 verdict's challengers: a hold doesn't end on validators that
    /// couldn't take its challenge.
    function test_pausedValidatorsArentChallengers() public {
        address[] memory ks = _network(3, FAMILIES, 3);
        for (uint256 i; i < 3; ++i) {
            vm.prank(ks[i]);
            pn.setCapacity(ks[i], 0);
        }
        vm.roll(vm.getBlockNumber() + pn.CAP_DELAY());
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 40e6);
        assertEq(pn.panel(pid).k, 1); // only the genesis validator has room
        _judge(pid, _votes(1, 1));
        assertEq(uint256(pn.submission(id).status), uint256(Status.Held));
        vm.expectRevert(Panels.NotReady.selector);
        pn.startWindow(id);
        for (uint256 i; i < 3; ++i) {
            vm.prank(ks[i]);
            pn.setCapacity(ks[i], 5);
        }
        vm.roll(vm.getBlockNumber() + pn.CAP_DELAY());
        pn.startWindow(id);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Window));
    }
}
