// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Vm} from "forge-std/Vm.sol";
import {console} from "forge-std/Test.sol";
import {IValidators} from "../../src/v3/IValidators.sol";
import {Panels} from "../../src/v3/Panels.sol";
import {PanelsVerdict} from "../../src/v3/PanelsVerdict.sol";
import {Status, Tier, Kind, Submission, Panel} from "../../src/v3/PanelsBase.sol";
import {IPanelsRegistry, IPanelsFees, IPanelScores} from "../../src/v3/IPanels.sol";
import {PanelScores} from "../../src/v3/PanelScores.sol";
import {PanelRules, PanelRulesLib, Cap, ChallengeSize} from "../../src/v3/PanelRules.sol";
import {Validators} from "../../src/v3/Validators.sol";
import {Windows} from "../../src/v3/Windows.sol";
import {DrawabilitySetup} from "./helpers/DrawabilitySetup.sol";

/// proof-of-fix#251, contract batch 4 (design L23, L24, L25; tasks 3.22-3.24): the panel rules as deployment settings,
/// panels of 3 with same-size fresh challenges, and challenges that always end, on the real Panels. Each scenario of
/// specs/deployment-binding, specs/judge-panels and specs/panel-liveness added by #251's batch 4 is tested under its
/// name, and each hang of reports/challenge-drawability-v1.md section 4 now ends.
contract PanelRulesV3Test is DrawabilitySetup {
    // ---------- L23: the panel caps are set at construction (deployment-binding) ----------

    /// The rules read back as constructed; the defaults are #132's; `kTop` must be odd from 1 to 7.
    function test_thePanelCapsAreSetAtConstruction() public {
        _deployRules(_launch(), _spread());
        PanelRules memory r = pn.panelRules();
        assertEq(uint256(r.operatorCap), uint256(Cap.Off));
        assertEq(uint256(r.hostCap), uint256(Cap.Off));
        assertEq(uint256(r.teeCap), uint256(Cap.Off));
        assertEq(r.kTop, 3);
        assertEq(uint256(r.challengeSize), uint256(ChallengeSize.Same));
        (uint256 top, uint256 min) = pn.challengeRange(3);
        assertEq(top, 3);
        assertEq(min, 3);
        (top, min) = pn.challengeRange(1); // a lone verdict's challenge keeps 3
        assertEq(top, 3);
        assertEq(min, 3);
        _deployRules(_strict(), _spread());
        r = pn.panelRules();
        assertEq(keccak256(abi.encode(r)), keccak256(abi.encode(PanelRulesLib.strict())));
        assertEq(r.kTop, 7);
        (top, min) = pn.challengeRange(3); // D4: CHALLENGE_K[3] = 5
        assertEq(top, 5);
        assertEq(min, 5);
        uint256[5] memory bad = [uint256(0), 2, 4, 8, 9];
        for (uint256 i; i < 5; ++i) {
            PanelRules memory b = _launch();
            b.kTop = bad[i];
            vm.expectRevert(PanelRulesLib.BadRules.selector);
            this.deployPanels(b);
        }
        PanelRules memory five = _launch();
        five.kTop = 5;
        assertEq(this.deployPanels(five).panelRules().kTop, 5);
        assertEq(PanelRulesLib.challengeTop(_launch()), 3);
        assertEq(PanelRulesLib.challengeTop(_strict()), 7);
        PanelRules memory one = _launch();
        one.kTop = 1;
        assertEq(PanelRulesLib.challengeTop(one), 3);
        one.challengeSize = ChallengeSize.Larger;
        one.kTop = 3;
        assertEq(PanelRulesLib.challengeTop(one), 5);
    }

    /// `new Panels` through an external call (Panels links libraries: an expected revert must wrap a call).
    function deployPanels(PanelRules memory r) external returns (Panels) {
        Validators.Genesis memory g = _genesis(false, new IValidators.Registration[](0), 0);
        Validators fresh = _create(g);
        return new Panels(
            IPanelsRegistry(address(fresh)),
            IPanelsFees(address(fees)),
            IPanelScores(address(new PanelScores())),
            g.teeTypes,
            g.windows,
            r
        );
    }

    /// Scenario "The owner's validators fill panels on Sepolia": 7 validators of one operator account, on one host
    /// value and one TEE type, are eligible on a deployment with every cap `Off`: a panel of `kTop` is drawn (3 with
    /// the launch's `kTop`, 7 with the default's).
    function test_theOwnersValidatorsFillPanelsOnSepolia() public {
        Layout memory l = Layout(true, true, true, 0);
        _deployRules(_launch(), l);
        _layout(7, 1, l);
        uint256 pid = _openAndDraw(_id(), 125e6);
        assertEq(pn.panel(pid).k, 3, "kTop 3");
        PanelRules memory off7 = _launch();
        off7.kTop = 7;
        _deployRules(off7, l);
        _layout(7, 1, l);
        pid = _openAndDraw(_id(), 125e6);
        assertEq(pn.panel(pid).k, 7, "every cap off: all 7 of one operator, host and TEE type");
    }

    /// Scenario "No change after deployment" (the caps): no function sets them, and they read back the same after a
    /// verdict, a challenge and its lapse.
    function test_noChangeAfterDeploymentOfTheCaps() public {
        _deployRules(_launch(), _spread());
        _layout(7, 1, _spread());
        bytes32 before = keccak256(abi.encode(pn.panelRules()));
        uint256 id = _id();
        _verdict(id, 125e6, true);
        race.challenge(id, challenger, EVIDENCE);
        vm.warp(pn.submission(id).challengeBy + 1);
        pn.lapseChallenge(id);
        assertEq(keccak256(abi.encode(pn.panelRules())), before);
        string memory json = vm.readFile("out/Panels.sol/Panels.json");
        for (uint256 i;; ++i) {
            string memory key = string.concat(".abi[", vm.toString(i), "]");
            if (!vm.keyExistsJson(json, key)) break;
            if (keccak256(bytes(vm.parseJsonString(json, string.concat(key, ".type")))) != keccak256("function")) {
                continue;
            }
            bytes memory name = bytes(vm.parseJsonString(json, string.concat(key, ".name")));
            bool setter = name.length > 3 && name[0] == "s" && name[1] == "e" && name[2] == "t" && name[3] >= "A"
                && name[3] <= "Z";
            if (keccak256(name) == keccak256("setCapacity")) continue; // a validator's own capacity (L16)
            assertFalse(setter, string(name));
        }
    }

    /// Scenario "The owner's validators on a strict deployment" (requirement "The k = 1 hold counts challengers under
    /// the caps"): 7 validators of one operator account are eligible on a deployment with every cap `Strict`: panels
    /// are k = 1, and a k = 1 verdict stays held, since no challenge panel of 3 could be drawn. The same layout with
    /// the caps `Off` draws a panel of `kTop`.
    function test_theOwnersValidatorsOnAStrictDeployment() public {
        Layout memory l = Layout(true, false, false, 0);
        _deployRules(_strict(), l);
        _layout(7, 1, l);
        uint256 id = _id();
        uint256 pid = _verdict(id, 40e6, true);
        assertEq(pn.panel(pid).k, 1, "one operator: k = 1");
        assertEq(uint256(pn.submission(id).status), uint256(Status.Held));
        vm.expectRevert(Panels.NotReady.selector); // 6 eligible outside it, but all of one operator account
        pn.startWindow(id);
        uint256 big = _id();
        assertEq(_openAndDraw(big, 125e6), 0, "a $125 bounty waits: k = 1's limit is $50");
        assertEq(uint256(pn.submission(big).status), uint256(Status.Waiting));
        _deployRules(_launch(), l);
        _layout(7, 1, l);
        assertEq(pn.panel(_openAndDraw(_id(), 125e6)).k, 3, "caps off: kTop");
    }

    /// The report's one-host layout: every validator but the genesis one on one host value. `Strict`: k = 1, and the
    /// k = 1 hold now counts challengers under the host cap, so it doesn't end while its challenge of 3 can't be drawn
    /// (before batch 4 it ended, and its challenge waited forever). It ends once three could sit together, with room for
    /// its audits (batch 5).
    function test_oneHostLayout() public {
        Layout memory l = Layout(false, true, false, 0);
        _deployRules(_strict(), l);
        address[] memory keys = _layout(7, 7, l);
        uint256 id = _id();
        uint256 pid = _verdict(id, 40e6, true);
        assertEq(pn.panel(pid).k, 1, "one host: k = 1");
        assertEq(uint256(pn.submission(id).status), uint256(Status.Held));
        vm.expectRevert(Panels.NotReady.selector);
        pn.startWindow(id);
        // two validators on hosts of their own: with one of the shared host, three could sit together, but its audits
        // still due would take them (#251 batch 5, #290): the hold counts 3 + 2 + 1 (its random audit undecided) that
        // pairwise fit, so three more
        _addLaid(100, 7, _spread());
        _addLaid(101, 7, _spread());
        vm.expectRevert(Panels.NotReady.selector);
        pn.startWindow(id);
        for (uint256 i = 102; i < 105; ++i) {
            _addLaid(i, 7, _spread());
        }
        pn.startWindow(id);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Window));
        keys;
        _deployRules(_launch(), l);
        _layout(7, 7, l);
        assertEq(pn.panel(_openAndDraw(_id(), 125e6)).k, 3, "caps off: kTop");
    }

    /// The report's one-TEE-type layout: every validator but the genesis one on SEV-SNP. `Strict` (three accepted
    /// types, so the TEE cap starts at k = 5): k = 3, as before. `Off` with `kTop` 7: a panel of 7.
    function test_oneTeeTypeLayout() public {
        Layout memory l = Layout(false, false, true, 0);
        _deployRules(_strict(), l);
        _layout(7, 7, l);
        assertEq(pn.panel(_openAndDraw(_id(), 125e6)).k, 3, "strict: the TEE cap holds k to 3");
        PanelRules memory off7 = _launch();
        off7.kTop = 7;
        _deployRules(off7, l);
        _layout(7, 7, l);
        assertEq(pn.panel(_openAndDraw(_id(), 125e6)).k, 7, "TEE cap off");
    }

    // ---------- L24: panels of 3, same-size challenges (judge-panels) ----------

    /// Scenario "The Sepolia launch at 7 validators": a $125 bounty's fix on a deployment with `kTop` 3 and 7 eligible
    /// validators: its panel is 3, its window CHALLENGE_WINDOW[3, A] (24 h in production), 4 validators remain to
    /// audit or challenge it, and its audit, when due, is drawn from them.
    function test_theSepoliaLaunchAt7Validators() public {
        _deployRules(_launch(), _spread());
        address[] memory keys = _layout(7, 1, _spread());
        uint256 id = _id();
        uint256 pid = _verdict(id, 125e6, true);
        assertEq(pn.panel(pid).k, 3);
        Submission memory s = pn.submission(id);
        assertEq(uint256(s.status), uint256(Status.Window));
        assertEq(s.level, 1);
        assertEq(s.finalAt, vm.getBlockTimestamp() + pn.windowOf(3, 1));
        assertEq(_outside(keys, pid), 4);
        // a random audit isn't due on every verdict: find one that is, and it's drawn from the 4 outside
        uint256 audited;
        for (uint256 t; t < 40 && audited == 0; ++t) {
            uint256 x = _id();
            uint256 xp = _verdict(x, 125e6, true);
            _rollPast(pn.submission(x).auditBlock);
            pn.drawAudits(x);
            Submission memory xs = pn.submission(x);
            if (xs.auditsDue == 0) continue;
            assertEq(xs.auditsDrawn, xs.auditsDue, "an audit due is drawn: 4 are outside the panel");
            audited = pn.panelCount();
            assertEq(uint256(pn.panel(audited).kind), uint256(Kind.Audit));
            assertFalse(_contains(pn.judges(xp), pn.judges(audited)[0]));
        }
        assertTrue(audited != 0, "an audited verdict found");
    }

    /// The same at level B: a panel of 3 judges $125, and its window is CHALLENGE_WINDOW[3, B] (48 h in production).
    function test_aPanelOf3AtLevelB() public {
        _deployRules(_launch(), _spread());
        _layout(7, 1, Layout(false, false, false, 2));
        uint256 id = _id();
        uint256 pid;
        for (uint256 t; t < 10; ++t) {
            pid = _verdict(id, 125e6, true);
            if (pn.submission(id).level == 2) break;
            id = _id(); // the genesis validator (level A) and one level B: level A; try another draw
        }
        assertEq(pn.panel(pid).k, 3);
        assertEq(pn.submission(id).level, 2);
        assertEq(pn.submission(id).finalAt, vm.getBlockTimestamp() + pn.windowOf(3, 2));
        assertEq(pn.windowOf(3, 2), 2 * pn.windowOf(3, 1));
    }

    /// Scenario "A challenge of a panel of 3 at 7 validators": a k = 3 verdict among 7 validators is challenged, or its
    /// pass disputed with a test: a panel of 3 is drawn from the 4 outside it, none of the original judges on it.
    function test_aChallengeOfAPanelOf3At7Validators() public {
        _deployRules(_launch(), _spread());
        address[] memory keys = _layout(7, 1, _spread());
        uint256 id = _id();
        uint256 pid = _verdict(id, 125e6, true);
        uint256 snap = vm.snapshotState();
        bytes32[2] memory evidence = [EVIDENCE, TEST_HASH];
        for (uint256 e; e < 2; ++e) {
            vm.revertToState(snap);
            uint256 cpid = _challenge(id, evidence[e]);
            assertTrue(cpid != 0, "drawn");
            assertEq(pn.panel(cpid).k, 3, "a fresh panel of the verdict's size");
            assertEq(pn.panel(cpid).ex, pid, "fresh: outside the challenged panel");
            address[] memory cj = pn.judges(cpid);
            for (uint256 i; i < 3; ++i) {
                assertFalse(_contains(pn.judges(pid), cj[i]), "no original judge");
                assertTrue(_contains(keys, cj[i]));
            }
            _judge(cpid, _all(3, false)); // the fresh panel fails the fix: the verdict is reversed
            assertFalse(pn.submission(id).pass);
            assertTrue(pn.submission(id).lastUpheld);
        }
    }

    /// The same at 15 validators: 12 stay outside a panel of 3, and its challenge draws 3 of them.
    function test_aChallengeOfAPanelOf3At15Validators() public {
        _deployRules(_launch(), _spread());
        address[] memory keys = _layout(15, 3, _spread());
        _knowFamilies(3);
        uint256 id = _id();
        uint256 pid = _verdict(id, 125e6, true);
        assertEq(pn.panel(pid).k, 3);
        assertEq(_outside(keys, pid), 12);
        uint256 cpid = _challenge(id, TEST_HASH);
        assertEq(pn.panel(cpid).k, 3);
        assertEq(pn.panel(cpid).ex, pid);
        (uint256 ending,) = _endChallenge(id, cpid, true);
        assertEq(ending, 1);
        assertFalse(pn.submission(id).challengeOpen);
    }

    /// Scenario "A lone verdict's challenge keeps 3 judges": a k = 1 verdict challenged on a deployment with `Same`
    /// gets a fresh panel of 3.
    function test_aLoneVerdictsChallengeKeeps3Judges() public {
        _deployRules(_launch(), _spread());
        uint256 id = _id();
        uint256 pid = _verdict(id, 40e6, true); // the genesis validator alone
        assertEq(pn.panel(pid).k, 1);
        _layout(7, 7, _spread());
        uint256 cpid = _challenge(id, EVIDENCE);
        assertEq(pn.panel(cpid).k, 3);
        assertEq(pn.panel(cpid).ex, pid);
        assertFalse(_contains(pn.judges(cpid), genesisKey));
    }

    /// Scenario "An audited verdict's challenge": a k = 3 verdict among 7 validators of one family had one auditor and
    /// is challenged, and the sample misses one of the 3 left (here deterministically: one of them is paused, as a
    /// miss would leave it): a second draw of 3 judges it, the original judges allowed (D27, the fallback).
    function test_anAuditedVerdictsChallenge() public {
        _deployRules(_launch(), _spread());
        address[] memory keys = _layout(7, 1, _spread());
        _knowFamilies(1);
        uint256 id;
        uint256 pid;
        uint256 apid;
        for (uint256 t; t < 60 && apid == 0; ++t) {
            id = _id();
            pid = _verdict(id, 125e6, true);
            _rollPast(pn.submission(id).auditBlock);
            pn.drawAudits(id);
            if (pn.submission(id).auditsDrawn == 1) apid = pn.panelCount();
        }
        require(apid != 0, "an audited verdict");
        _judge(apid, _all(1, true)); // the auditor agrees
        address auditor = pn.judges(apid)[0];
        // of the 3 left outside the panel and its auditor, one can't sit (the sample's miss)
        address missed;
        for (uint256 i; i < keys.length && missed == address(0); ++i) {
            if (!_contains(pn.judges(pid), keys[i]) && keys[i] != auditor) missed = keys[i];
        }
        _pause(missed, 0);
        race.challenge(id, challenger, EVIDENCE);
        _rollPast(pn.submission(id).challengeBlock);
        vm.recordLogs();
        pn.drawChallenge(id);
        uint256 cpid = pn.submission(id).challengePid;
        assertTrue(cpid != 0, "the second draw, not a wait");
        assertEq(pn.panel(cpid).k, 3, "of the same size");
        assertEq(pn.panel(cpid).ex, 0, "the original judges allowed");
        assertTrue(_emitted(PanelsVerdict.SecondDraw.selector));
        assertFalse(_contains(pn.judges(cpid), missed));
    }

    function _emitted(bytes32 topic) internal returns (bool) {
        Vm.Log[] memory logs = vm.getRecordedLogs();
        for (uint256 i; i < logs.length; ++i) {
            if (logs[i].topics.length > 0 && logs[i].topics[0] == topic) return true;
        }
        return false;
    }

    /// Scenario "ADRs keep their size": on a deployment with `kTop` 3 an ADR needs exactly K_MAX judges, and expires
    /// below CONSTITUTION_MIN_ELIGIBLE as before.
    function test_adrsKeepTheirSize() public {
        _deployRules(_launch(), _spread());
        _layout(7, 7, _spread());
        uint256 small = _id();
        race.openConstitution(small, keccak256("adr"), Tier.Adr, 0, challenger);
        assertEq(uint256(pn.submission(small).status), uint256(Status.Expired), "7 eligible: it expires");
        _layout(15, 7, _spread()); // 21 eligible in all
        uint256 id = _id();
        race.openConstitution(id, keccak256("adr 2"), Tier.Adr, 0, challenger);
        uint256 pid = _draw(id);
        assertEq(pn.panel(pid).k, 7, "K_MAX, not kTop");
    }

    /// With `Larger` (the default), D4's larger challenge panel: a k = 3 verdict's challenge draws 5.
    function test_largerDrawsD4sPanel() public {
        _deployRules(_strict(), _spread());
        _layout(4, 7, _spread()); // 4 validators: a panel of 3; the network grows after the verdict
        uint256 id = _id();
        uint256 pid = _verdict(id, 125e6, true);
        assertEq(pn.panel(pid).k, 3);
        for (uint256 i = 10; i < 16; ++i) {
            _addLaid(i, 7, _spread());
        }
        uint256 cpid = _challenge(id, EVIDENCE);
        assertEq(pn.panel(cpid).k, 5, "CHALLENGE_K[3]");
    }

    // ---------- L25: challenges always end (panel-liveness) ----------

    /// Scenario "No panel by the deadline", the report's hang 1 (section 4): 7 validators, three known families, `Larger`
    /// (the defaults): the challenge of a panel of 7 waits, is redrawn by its clock, and lapses past
    /// CHALLENGE_DEADLINE: the verdict stands, its window resumes, the original judges can unbond.
    function test_noPanelByTheDeadline() public {
        _deployRules(_strict(), _spread());
        _layout(7, 3, _spread());
        _knowFamilies(3);
        uint256 id = _id();
        uint256 pid = _verdict(id, 125e6, true);
        assertEq(pn.panel(pid).k, 7);
        uint256 finalAt = pn.submission(id).finalAt;
        vm.warp(vm.getBlockTimestamp() + pn.REVEAL_WINDOW()); // an hour (a minute in the minutes run)
        uint256 left = finalAt - vm.getBlockTimestamp();
        uint256 opened = vm.getBlockTimestamp();
        assertEq(_challenge(id, EVIDENCE), 0, "waits: no 7 fresh, no second draw with 3 families");
        Submission memory s = pn.submission(id);
        assertEq(s.challengeBy, opened + pn.CHALLENGE_DEADLINE());
        assertEq(s.challengeRetryAt, vm.getBlockTimestamp() + pn.RETRY_DELAY());
        address judge0 = pn.judges(pid)[0];
        assertEq(reg.validator(judge0).openChallenges, 1);
        vm.expectRevert(Panels.NothingChanged.selector); // before its retry time, with no registry change
        pn.drawChallenge(id);
        assertEq(_retryChallenge(id), 0, "redrawn by the clock, still no panel");
        vm.expectRevert(Panels.TooEarly.selector);
        pn.lapseChallenge(id);
        vm.warp(s.challengeBy + 1);
        vm.expectRevert(Panels.TooLate.selector); // past the deadline nothing is drawn
        pn.drawChallenge(id);
        vm.expectEmit(true, false, false, true);
        emit Panels.ChallengeLapsed(id, 1);
        pn.lapseChallenge(id);
        s = pn.submission(id);
        assertFalse(s.challengeOpen);
        assertTrue(s.pass, "the verdict stands");
        assertEq(s.lapses, 1);
        assertEq(s.finalAt, vm.getBlockTimestamp() + left, "the window resumes where it froze");
        assertEq(reg.validator(judge0).openChallenges, 0, "the original judges can unbond");
        vm.expectRevert(Panels.WrongStatus.selector); // once
        pn.lapseChallenge(id);
    }

    /// Scenario "A panel completes after the deadline": a challenge panel drawn before CHALLENGE_DEADLINE and judged
    /// after it is counted as any challenge panel.
    function test_aPanelCompletesAfterTheDeadline() public {
        _deployRules(_launch(), _spread());
        _layout(7, 1, _spread());
        uint256 id = _id();
        _verdict(id, 125e6, true);
        race.challenge(id, challenger, EVIDENCE);
        vm.warp(pn.submission(id).challengeBy); // the last moment it may be drawn
        uint256 cpid = _drawChallenge(id);
        assertTrue(cpid != 0);
        vm.expectRevert(Panels.WrongStatus.selector); // a drawn challenge doesn't lapse by the clock
        pn.lapseChallenge(id);
        address[] memory cj = pn.judges(cpid);
        for (uint256 i; i < 3; ++i) {
            _seal(cpid, cj[i], false);
        }
        vm.warp(pn.panel(cpid).sealBy + 1);
        assertGt(vm.getBlockTimestamp(), pn.submission(id).challengeBy);
        for (uint256 i; i < 3; ++i) {
            _reveal(cpid, cj[i]);
            _receipt(cpid, cj[i]);
        }
        Submission memory s = pn.submission(id);
        assertFalse(s.challengeOpen);
        assertFalse(s.pass, "counted: the fresh panel's majority decides");
        assertEq(s.lapses, 0);
    }

    /// Scenario "A silent judge on a challenge panel with no replacement", the report's hang 2 at n = 7: one family,
    /// `Larger`, a panel of 7; its challenge is judged by D27's second draw of all 7, one of whom stays silent. At its
    /// reveal deadline plus STUCK_GRACE the panel is released, the silent seat slashed and the sealed ones closed
    /// unslashed: before CHALLENGE_DEADLINE the challenge waits for a redraw; a second stuck panel released after the
    /// deadline makes it lapse.
    function test_aSilentJudgeOnAChallengePanelWithNoReplacement() public {
        _deployRules(_strict(), _spread());
        _layout(7, 1, _spread());
        _knowFamilies(1);
        uint256 id = _id();
        uint256 pid = _verdict(id, 50e6, true); // $50: a judge slashed for silence ($245) stays eligible
        assertEq(pn.panel(pid).k, 7);
        uint256 cpid = _challenge(id, EVIDENCE);
        assertEq(pn.panel(cpid).ex, 0, "D27's second draw");
        address silent = _stuckChallengePanel(cpid);
        uint256 bond = reg.validator(silent).bond;
        assertEq(bond, BOND - 5e6, "slashed for its silence");
        vm.warp(pn.panel(cpid).revealBy + pn.STUCK_GRACE());
        vm.expectRevert(Panels.NothingDue.selector);
        pn.release(cpid);
        vm.warp(pn.panel(cpid).revealBy + pn.STUCK_GRACE() + 1);
        assertLt(vm.getBlockTimestamp(), pn.submission(id).challengeBy);
        vm.expectEmit(true, true, false, true);
        emit Panels.ChallengeReleased(id, cpid, false);
        pn.release(cpid);
        Submission memory s = pn.submission(id);
        assertTrue(s.challengeOpen, "back to waiting");
        assertEq(s.challengePid, 0);
        assertTrue(s.challengeEpoch != 0);
        assertEq(s.challengeRetryAt, vm.getBlockTimestamp() + pn.RETRY_DELAY());
        assertTrue(pn.panel(cpid).closed);
        address[] memory cj = pn.judges(cpid);
        for (uint256 i; i < cj.length; ++i) {
            if (cj[i] == address(0)) continue;
            assertEq(reg.validator(cj[i]).openVerdicts, 1, "sealed seats closed: only the counted verdict open");
        }
        // drawn again near the deadline, stuck again, released after it: the challenge lapses
        vm.warp(s.challengeBy - pn.REVEAL_WINDOW()); // an hour before it (a minute in the minutes run)
        uint256 again = _retryChallenge(id);
        assertTrue(again != 0 && again != cpid);
        _stuckChallengePanel(again);
        vm.warp(pn.panel(again).revealBy + pn.STUCK_GRACE() + 1);
        assertGt(vm.getBlockTimestamp(), s.challengeBy);
        vm.expectEmit(true, true, false, true);
        emit Panels.ChallengeReleased(id, again, true);
        pn.release(again);
        s = pn.submission(id);
        assertFalse(s.challengeOpen, "lapsed");
        assertEq(s.lapses, 1);
        assertTrue(s.pass);
        assertEq(reg.validator(pn.judges(pid)[0]).openChallenges, 0);
    }

    /// Every judge of challenge panel `cpid` seals but one, which stays silent; the seal deadline passes and no
    /// replacement can be found. Returns the silent one.
    function _stuckChallengePanel(uint256 cpid) internal returns (address silent) {
        address[] memory cj = pn.judges(cpid);
        silent = cj[cj.length - 1];
        if (silent == genesisKey) silent = cj[0];
        for (uint256 i; i < cj.length; ++i) {
            if (cj[i] != silent) _seal(cpid, cj[i], true);
        }
        vm.warp(pn.panel(cpid).sealBy + 1);
        pn.advance(cpid);
        assertEq(pn.panel(cpid).seats, cj.length - 1, "replacements exhausted");
    }

    /// Scenario "A validator un-pauses": a challenge waits because validators were paused; they un-pause with no other
    /// registry change (a capacity change isn't one), and the challenge is drawn again at its RETRY_DELAY with a fresh
    /// seed (L25's retry clock; before batch 4 it waited for a registry change that never came).
    function test_aValidatorUnpauses() public {
        _deployRules(_launch(), _spread());
        address[] memory keys = _layout(7, 3, _spread());
        _knowFamilies(3); // three families seated: no second draw
        uint256 id = _id();
        uint256 pid = _verdict(id, 125e6, true);
        address[2] memory paused;
        uint256 m;
        for (uint256 i; i < keys.length && m < 2; ++i) {
            if (!_contains(pn.judges(pid), keys[i])) paused[m++] = keys[i];
        }
        _pause(paused[0], 0);
        _pause(paused[1], 0);
        uint256 epoch = reg.epoch();
        assertEq(_challenge(id, EVIDENCE), 0, "2 of the 4 outside are paused: no fresh 3");
        bytes32 block0 = keccak256(abi.encode(pn.submission(id).challengeBlock));
        _pause(paused[0], 5);
        _pause(paused[1], 5);
        assertEq(reg.epoch(), epoch, "un-pausing isn't a registry change");
        if (vm.getBlockTimestamp() < pn.submission(id).challengeRetryAt) {
            vm.expectRevert(Panels.NothingChanged.selector);
            pn.drawChallenge(id);
        }
        uint256 cpid = _retryChallenge(id);
        assertTrue(cpid != 0, "drawn at its retry time");
        assertTrue(keccak256(abi.encode(pn.submission(id).challengeBlock)) != block0, "a fresh seed block");
        assertEq(pn.panel(cpid).k, 3);
    }

    /// A verdict accepts at most MAX_REDRAWS lapsed challenges (L25, decided (owner, 2026-11-20)): later ones are
    /// refused, an auditor's mismatch opens none, and the verdict finalizes at its window.
    function test_atMostMaxRedrawsLapses() public {
        _deployRules(_strict(), _spread());
        _layout(7, 3, _spread());
        _knowFamilies(3);
        uint256 id = _id();
        _verdict(id, 125e6, true);
        _rollPast(pn.submission(id).auditBlock);
        pn.drawAudits(id); // decided now (at 7 of 7 nobody could audit it: then L19's audit release applies)
        for (uint256 i; i < pn.MAX_REDRAWS(); ++i) {
            race.challenge(id, challenger, EVIDENCE);
            vm.warp(pn.submission(id).challengeBy + 1);
            pn.lapseChallenge(id);
        }
        assertEq(pn.submission(id).lapses, pn.MAX_REDRAWS());
        vm.expectRevert(Panels.TooManyLapses.selector);
        race.challenge(id, challenger, EVIDENCE);
        Submission memory s = pn.submission(id);
        assertTrue(s.auditDecided);
        if (s.auditsDue == 0) {
            vm.warp(s.finalAt);
            pn.finalize(id);
            assertEq(uint256(pn.submission(id).status), uint256(Status.Final));
        }
    }

    /// The windows: CHALLENGE_DEADLINE is 120 h in production (120 minutes in minutes), and the order check holds it
    /// at least MAX_REDRAWS × RETRY_DELAY + seal + reveal + STUCK_GRACE (99 h).
    function test_theChallengeDeadline() public {
        _deployRules(_launch(), _spread());
        Windows memory w = pn.windows();
        assertEq(pn.CHALLENGE_DEADLINE(), w.challengeDeadline);
        assertGe(w.challengeDeadline, w.maxRedraws * w.retryDelay + w.seal + w.reveal + w.stuckGrace);
        assertTrue(w.challengeDeadline == 120 hours || w.challengeDeadline == 120 minutes);
    }

    /// Gas of batch 4's calls (reports/contract-v3.md).
    function test_gasChallengesEnd() public {
        _deployRules(_strict(), _spread());
        _layout(7, 3, _spread());
        _knowFamilies(3);
        uint256 id = _id();
        _verdict(id, 125e6, true);
        race.challenge(id, challenger, EVIDENCE);
        _rollPast(pn.submission(id).challengeBlock);
        uint256 g = gasleft();
        pn.drawChallenge(id);
        console.log("drawChallenge (strict, k = 7 at 7 of 7, three families: no panel, waits):", g - gasleft());
        vm.warp(pn.submission(id).challengeRetryAt);
        g = gasleft();
        pn.drawChallenge(id);
        console.log("drawChallenge at its retry time (re-targets):", g - gasleft());
        vm.warp(pn.submission(id).challengeBy + 1);
        g = gasleft();
        pn.lapseChallenge(id);
        console.log("lapseChallenge (7 original judges' challenge closed):", g - gasleft());

        _deployRules(_launch(), _spread());
        address[] memory keys = _layout(7, 1, _spread());
        id = _id();
        uint256 pid = _verdict(id, 125e6, true);
        race.challenge(id, challenger, EVIDENCE);
        _rollPast(pn.submission(id).challengeBlock);
        g = gasleft();
        pn.drawChallenge(id);
        console.log("drawChallenge (launch, a fresh panel of 3 of the 4 outside):", g - gasleft());
        uint256 cpid = pn.submission(id).challengePid;
        for (uint256 i; i < keys.length; ++i) {
            if (!_contains(pn.judges(pid), keys[i]) && !_contains(pn.judges(cpid), keys[i])) _pause(keys[i], 0);
        }
        address[] memory cj = pn.judges(cpid);
        _seal(cpid, cj[0], true);
        _seal(cpid, cj[1], true);
        vm.warp(pn.panel(cpid).sealBy + 1);
        pn.advance(cpid);
        vm.warp(pn.panel(cpid).revealBy + pn.STUCK_GRACE() + 1);
        g = gasleft();
        pn.release(cpid);
        console.log("release (a challenge panel of 3, one silent seat slashed, two closed; waits again):", g - gasleft());
    }
}
