// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Panels} from "../../src/v3/Panels.sol";
import {Status, Kind, Submission, Panel} from "../../src/v3/PanelsBase.sol";
import {DrawabilitySetup} from "./helpers/DrawabilitySetup.sol";

/// proof-of-fix#251, contract batch 5 (#290; design L19 and L25's notes of 2026-11-21): a held verdict's window and the
/// k = 1 hold's count, on the real Panels under the launch's rules (every cap `Off`, `kTop` 3, `Same`) and the strict
/// ones.
///
/// - **`startWindow` waits for an open challenge.** It used to start a held verdict's window while a challenge of it
///   was open; the window's frozen rest (`frozenLeft`) is set only when a challenge opens in the window, so the
///   challenge's lapse or resolution resumed the window with nothing left, and the verdict could be final at once.
///   Anyone may call `startWindow`. Now it's refused while a challenge is open, and the window starts whole after.
/// - **The k = 1 hold keeps room for its audits.** It used to end once three validators outside the panel and its
///   drawn auditors were ready; its two audits (three with a random one) were then drawn from those same validators,
///   each sitting out of the challenge, so honest audits that caught a wrong lone pass left nobody to judge it, and the
///   pass was paid. Now the hold counts one more challenger for each audit still to be drawn (the random one while
///   undecided too).
contract HeldWindowV3Test is DrawabilitySetup {
    // ---------- startWindow and an open challenge (bug 1) ----------

    /// A challenge filed on a held verdict, then the network grows: `startWindow` is refused while the challenge is
    /// open (before batch 5 it started the window unfrozen, and the lapse below resumed it with 0 left: final at once).
    /// After the lapse the window starts whole.
    function test_startWindowWaitsForAnOpenChallenge() public {
        _deployRules(_launch(), _spread());
        uint256 id = _id();
        uint256 pid = _verdict(id, 40e6, true); // the genesis validator alone: k = 1, held
        assertEq(pn.panel(pid).k, 1, "k = 1");
        assertEq(uint256(pn.submission(id).status), uint256(Status.Held), "held: nobody could judge its challenge");
        race.challenge(id, challenger, EVIDENCE); // a challenge of the held verdict, which nobody can judge yet
        _layout(7, 1, _spread()); // six more: three challengers and room for its audits
        assertLt(vm.getBlockTimestamp(), pn.submission(id).challengeBy, "the challenge is still open");
        vm.expectRevert(Panels.NotReady.selector);
        pn.startWindow(id);
        vm.warp(pn.submission(id).challengeBy + 1);
        pn.lapseChallenge(id);
        Submission memory s = pn.submission(id);
        assertEq(uint256(s.status), uint256(Status.Held), "a lapse leaves a held verdict held");
        pn.startWindow(id);
        s = pn.submission(id);
        assertEq(uint256(s.status), uint256(Status.Window));
        assertEq(s.finalAt, vm.getBlockTimestamp() + pn.windowOf(1, s.level), "the window starts whole");
        _runAudits(id, true);
        vm.warp(s.finalAt - 1);
        vm.expectRevert(Panels.TooEarly.selector);
        pn.finalize(id);
        vm.warp(s.finalAt);
        pn.finalize(id);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Final));
    }

    // ---------- the k = 1 hold and its audits (bug 2) ----------

    /// A lone verdict counted while three validators are ready outside its panel: held, since its two audits would
    /// leave its challenge one judge (before batch 5 its window started at once, the audits took two of the three, and
    /// their challenge lapsed). Its audits, drawn while it's held, catch the wrong pass; the challenge waits until the
    /// network grows (and `startWindow` is refused while it's open), then three fresh validators reverse it, and the
    /// window starts whole on the corrected verdict.
    function test_aLoneWrongPassCaughtByItsAuditIsJudged() public {
        _deployRules(_launch(), _spread());
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 40e6); // the genesis validator alone: k = 1
        assertEq(pn.panel(pid).k, 1, "k = 1");
        _layout(4, 1, _spread()); // three join before its count
        _judge(pid, _all(1, true)); // a wrong pass
        Submission memory s = pn.submission(id);
        assertEq(uint256(s.status), uint256(Status.Held), "three ready, but its audits would leave its challenge short");
        vm.expectRevert(Panels.NotReady.selector);
        pn.startWindow(id);
        _runAudits(id, false); // honest auditors: the fix fails
        s = pn.submission(id);
        assertEq(s.auditsDrawn, s.auditsDue, "its audits drawn from the three while it's held");
        assertTrue(s.challengeOpen, "an auditor's mismatch opened a challenge");
        assertEq(_drawChallenge(id), 0, "nobody left outside its panel and its auditors: the challenge waits");
        for (uint256 i = 4; i < 7; ++i) {
            _addLaid(i, 1, _spread()); // the network grows
        }
        vm.expectRevert(Panels.NotReady.selector); // three fresh challengers now, but its challenge is open
        pn.startWindow(id);
        pn.drawChallenge(id); // the registry changed: re-targets
        uint256 cpid = _drawChallenge(id);
        assertTrue(cpid != 0, "drawn");
        address[] memory cj = pn.judges(cpid);
        assertEq(cj.length, 3);
        address[] memory aud = _auditorsOf(id);
        assertGt(aud.length, 0);
        for (uint256 i; i < 3; ++i) {
            assertTrue(cj[i] != genesisKey, "not the lone judge");
            assertFalse(_contains(aud, cj[i]), "nor an auditor");
        }
        _judge(cpid, _all(3, false));
        s = pn.submission(id);
        assertFalse(s.challengeOpen);
        assertFalse(s.pass, "reversed");
        assertTrue(s.lastUpheld);
        assertEq(uint256(s.status), uint256(Status.Held));
        pn.startWindow(id);
        s = pn.submission(id);
        assertEq(s.finalAt, vm.getBlockTimestamp() + pn.windowOf(1, s.level), "the window starts whole");
        vm.warp(s.finalAt);
        pn.finalize(id);
        s = pn.submission(id);
        assertEq(uint256(s.status), uint256(Status.Final));
        assertFalse(s.pass, "final as a fail: the wrong pass isn't paid");
    }

    /// The hold's count: CHALLENGE_K[1] plus each audit still to be drawn, the random audit while undecided too. At its
    /// count (audits undecided) a lone verdict needs 3 + 2 + 1 = 6 ready validators outside its panel: 5 hold it, 6
    /// start its window at once. Once its audits are decided and drawn, the auditors are outside the count and nothing
    /// more is reserved.
    function test_theHoldCountsTheAuditsStillDue() public {
        _deployRules(_launch(), _spread());
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 40e6);
        _layout(6, 1, _spread()); // five ready at its count
        _judge(pid, _all(1, true));
        assertEq(uint256(pn.submission(id).status), uint256(Status.Held), "5 < 3 + 2 audits + the undecided one");
        _runAudits(id, true); // decided and drawn while held
        Submission memory s = pn.submission(id);
        assertTrue(s.auditDecided);
        assertEq(s.auditsDrawn, s.auditsDue);
        if (5 - s.auditsDrawn >= 3) {
            pn.startWindow(id); // two audits: three left, nothing more reserved
        } else {
            vm.expectRevert(Panels.NotReady.selector); // a random third audit left two
            pn.startWindow(id);
            _addLaid(6, 1, _spread());
            pn.startWindow(id);
        }
        assertEq(uint256(pn.submission(id).status), uint256(Status.Window));

        _deployRules(_launch(), _spread());
        id = _id();
        pid = _openAndDraw(id, 40e6);
        _layout(7, 1, _spread()); // six ready at its count
        _judge(pid, _all(1, true));
        assertEq(uint256(pn.submission(id).status), uint256(Status.Window), "6 = 3 + 2 + 1: its window starts at once");
        _runAudits(id, false); // its audits catch it: three fresh are left whatever the random audit decides
        uint256 cpid = _drawChallenge(id);
        assertTrue(cpid != 0, "its challenge is drawn");
        _judge(cpid, _all(3, false));
        assertFalse(pn.submission(id).pass, "reversed");
    }

    /// Under `Strict` caps the hold's count is of validators that pairwise fit a panel of 3 (distinct operators and
    /// hosts here), so that any three left once its auditors are drawn from them could sit together.
    function test_theHoldUnderStrictCapsKeepsRoomForItsAudits() public {
        Layout memory l = Layout(false, true, false, 0);
        _deployRules(_strict(), l);
        _layout(7, 7, l); // six on one host value
        uint256 id = _id();
        uint256 pid = _verdict(id, 40e6, true);
        assertEq(pn.panel(pid).k, 1, "one host: k = 1");
        for (uint256 i = 100; i < 103; ++i) {
            _addLaid(i, 7, _spread()); // three on hosts of their own: four distinct hosts outside its panel
        }
        vm.expectRevert(Panels.NotReady.selector); // 4 < 3 + 2 + 1 that pairwise fit
        pn.startWindow(id);
        _addLaid(103, 7, _spread());
        _addLaid(104, 7, _spread()); // six distinct hosts
        pn.startWindow(id);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Window));
    }

    /// The validators seated on submission `id`'s audit panels.
    function _auditorsOf(uint256 id) internal view returns (address[] memory out) {
        uint256 last = pn.panelCount();
        out = new address[](last);
        uint256 n;
        for (uint256 q = 1; q <= last; ++q) {
            Panel memory p = pn.panel(q);
            if (p.kind == Kind.Audit && p.id == id) out[n++] = pn.judges(q)[0];
        }
        assembly ("memory-safe") {
            mstore(out, n)
        }
    }
}
