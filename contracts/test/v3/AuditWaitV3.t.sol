// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Panels} from "../../src/v3/Panels.sol";
import {Status, Submission} from "../../src/v3/PanelsBase.sol";
import {RaceV3Setup} from "./helpers/RaceV3Setup.sol";

/// proof-of-fix#336: a held verdict's audits stalled after validators paused and resumed. A lone verdict counted
/// during an outage (every validator but the genesis one paused) decides its audits, finds no auditor, and waits
/// (`auditWaits`, #251 task 3.10). Un-pausing (`Panels.setCapacity`) doesn't move the registry's epoch, so before the
/// fix every `drawAudits` was refused (`NothingChanged`) until some unrelated registry event, however long: on a quiet
/// network the hold, its audits and their challenge stalled (integration scenario x, 1 run in 3).
contract AuditWaitV3Test is RaceV3Setup {
    address[] internal ks;

    function setUp() public {
        _deployRace(0);
        ks = _network(6, FAMILIES, 3);
    }

    /// Every validator but the genesis one at `checks` an hour, in force.
    function _capacity(uint256 checks) internal {
        for (uint256 i; i < ks.length; ++i) {
            vm.prank(ks[i]);
            pn.setCapacity(ks[i], checks);
        }
        vm.roll(vm.getBlockNumber() + pn.CAP_DELAY() + 1);
    }

    /// The outage: a lone verdict counted and held, its audits decided and none drawn (on main they wait for the
    /// registry to change, `auditWaits`).
    function _heldAuditsWaiting() internal returns (uint256 id) {
        _capacity(0);
        id = rc.issue(_register()).check;
        uint256 pid = _draw(id);
        assertEq(pn.panel(pid).k, 1, "the outage: the genesis validator judges alone");
        _judge(pid, _votes(1, 1));
        _reportAll(pid);
        vm.prank(relayer);
        rc.result(id);
        Submission memory s = pn.submission(id);
        assertTrue(s.status == Status.Held, "held: nobody could judge its challenge");
        for (uint256 t; t < 2 && !s.auditWaits; ++t) {
            _rollPast(s.auditBlock);
            pn.drawAudits(id);
            s = pn.submission(id);
        }
        assertTrue(s.auditDecided && s.auditsDue > 0 && s.auditsDrawn == 0, "its audits decided, none drawn");
    }

    /// A keeper's tries, every `step` seconds (one block each, so the audit block's hash stays readable), until `end`
    /// or every audit is drawn. Returns how many calls were refused and how many fresh audit blocks were rolled.
    function _keep(uint256 id, uint256 step, uint256 end) internal returns (uint256 refused, uint256 rerolls) {
        uint256 block0 = pn.submission(id).auditBlock;
        while (vm.getBlockTimestamp() < end) {
            Submission memory s = pn.submission(id);
            if (s.auditsDrawn == s.auditsDue) break;
            if (s.auditBlock != block0) {
                ++rerolls;
                block0 = s.auditBlock;
            }
            if (!s.auditWaits) _rollPast(s.auditBlock);
            try pn.drawAudits(id) {}
            catch (bytes memory err) {
                assertEq(bytes4(err), Panels.NothingChanged.selector, "refused, as waiting");
                ++refused;
            }
            vm.warp(vm.getBlockTimestamp() + step);
            vm.roll(vm.getBlockNumber() + 1);
        }
    }

    /// The regression: the validators back, the registry unchanged, the audits are drawn within a RETRY_DELAY (and a
    /// capacity window). Before the fix they stayed refused for good.
    function test_resumedValidatorsDrawAWaitingHeldVerdictsAudits() public {
        uint256 id = _heldAuditsWaiting();
        uint256 epoch = reg.epoch();
        _capacity(pn.CHECKS_DEFAULT()); // the outage ends: setCapacity doesn't move the registry's epoch
        uint256 end = vm.getBlockTimestamp() + pn.RETRY_DELAY() + pn.CAP_WINDOW() + 1;
        (uint256 refused,) = _keep(id, pn.CAP_WINDOW(), end); // a try a capacity window, as the keeper
        assertEq(reg.epoch(), epoch, "no registry change");
        Submission memory s = pn.submission(id);
        assertTrue(s.status == Status.Held, "still held: nothing else moved it");
        assertEq(
            s.auditsDrawn,
            s.auditsDue,
            string.concat("drawn once the validators were back (refused NothingChanged ", vm.toString(refused), " times)")
        );
    }

    /// Nobody can roll fresh audit blocks at will while the audits find no auditor: tries six times a capacity window
    /// for two RETRY_DELAYs re-target at most once a RETRY_DELAY.
    function test_waitingAuditsCantBeRerolledAtWill() public {
        uint256 id = _heldAuditsWaiting();
        uint256 span = 2 * pn.RETRY_DELAY();
        (, uint256 rerolls) = _keep(id, pn.CAP_WINDOW() / 6, vm.getBlockTimestamp() + span);
        Submission memory s = pn.submission(id);
        assertEq(s.auditsDrawn, 0, "nobody to draw");
        assertLe(rerolls, span / pn.RETRY_DELAY(), "at most one fresh audit block a RETRY_DELAY");
    }
}
