// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Validators} from "../../src/v3/Validators.sol";
import {IValidators} from "../../src/v3/IValidators.sol";
import {IFeesV3Scores} from "../../src/v3/IFeesV3.sol";
import {Panels} from "../../src/v3/Panels.sol";
import {PanelScores} from "../../src/v3/PanelScores.sol";
import {Status, Tier, Kind, Submission, Panel} from "../../src/v3/PanelsBase.sol";
import {PanelsSetup} from "./helpers/PanelsSetup.sol";
import {TDX, SEV_SNP, NITRO} from "./helpers/ValidatorsSetup.sol";

/// proof-of-fix#138, task 3.2 of #132, milestone B: shadows, audits, challenge panels and the frozen window, scores
/// at finality, the constitution tier, and the draw's snapshot against grinding. Each scenario of specs/judge-panels,
/// specs/judge-scores and the shadow scenarios of specs/validator-admission is tested by its spec name.
contract PanelsV3BTest is PanelsSetup {
    uint256 internal nextId = 1000;
    address internal challenger = makeAddr("challenger");
    address internal author = makeAddr("adr author");

    function setUp() public {
        _deployVersion(3, false);
        usd.mint(address(race), 10_000e6);
    }

    function _id() internal returns (uint256) {
        return nextId++;
    }

    // ---------- helpers ----------

    /// Seals `votes` on panel `pid` and `svotes` on shadow panel `spid` (0: none) in the seal window, then reveals
    /// both with receipts.
    function _judgeBoth(uint256 pid, bool[] memory votes, uint256 spid, bool[] memory svotes) internal {
        address[] memory js = pn.judges(pid);
        for (uint256 i; i < js.length; ++i) {
            _seal(pid, js[i], votes[i]);
        }
        address[] memory ss = spid == 0 ? new address[](0) : pn.judges(spid);
        for (uint256 i; i < ss.length && i < svotes.length; ++i) {
            _seal(spid, ss[i], svotes[i]);
        }
        vm.warp(pn.panel(pid).sealBy + 1);
        for (uint256 i; i < js.length; ++i) {
            _reveal(pid, js[i]);
            _receipt(pid, js[i]);
        }
        for (uint256 i; i < ss.length && i < svotes.length; ++i) {
            _reveal(spid, ss[i]);
            _receipt(spid, ss[i]);
        }
    }

    function _judgeMasks(uint256 pid, bool[] memory votes, uint8 mask) internal {
        address[] memory js = pn.judges(pid);
        for (uint256 i; i < js.length; ++i) {
            _sealMask(pid, js[i], votes[i], mask);
        }
        vm.warp(pn.panel(pid).sealBy + 1);
        for (uint256 i; i < js.length; ++i) {
            _reveal(pid, js[i]);
            _receipt(pid, js[i]);
        }
    }

    function _same(uint256 k, bool v) internal pure returns (bool[] memory out) {
        out = new bool[](k);
        for (uint256 i; i < k; ++i) {
            out[i] = v;
        }
    }

    /// Files a challenge and draws its panel (0 if it waits).
    function _challenge(uint256 id, address who) internal returns (uint256) {
        race.challenge(id, who, keccak256("evidence"));
        return _drawChallenge(id);
    }

    function _drawChallenge(uint256 id) internal returns (uint256) {
        _rollPast(pn.submission(id).challengeBlock);
        pn.drawChallenge(id);
        return pn.submission(id).challengePid;
    }

    /// The audit panels drawn for `id` (in order).
    function _auditPanels(uint256 id) internal view returns (uint256[] memory out) {
        uint256 n = pn.panelCount();
        out = new uint256[](n);
        uint256 m;
        for (uint256 q = 1; q <= n; ++q) {
            Panel memory p = pn.panel(q);
            if (p.kind == Kind.Audit && p.id == id) out[m++] = q;
        }
        assembly ("memory-safe") {
            mstore(out, m)
        }
    }

    /// drawAudits from the current audit block, retrying once from a re-targeted block and snapshot.
    function _drawAudits(uint256 id) internal {
        for (uint256 t; t < 2; ++t) {
            Submission memory s = pn.submission(id);
            if (s.auditDecided && s.auditsDrawn == s.auditsDue) return;
            _rollPast(s.auditBlock);
            pn.drawAudits(id);
        }
    }

    function _judgeOne(uint256 pid, bool vote) internal {
        bool[] memory v = new bool[](1);
        v[0] = vote;
        _judge(pid, v);
    }

    /// A lone (k = 1) verdict by the genesis validator, held, then `extra` validators of their own families added.
    function _heldLoneVerdict(bool vote, uint256 extra) internal returns (uint256 id, uint256 pid) {
        id = _id();
        pid = _openAndDraw(id, 40e6);
        _judgeOne(pid, vote);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Held));
        _network(extra, 7, 3);
    }

    // ---------- A receipt challenge (judge-panels) ----------

    /// Scenarios "A verdict through a gateway" and "A model of another family": a challenge panel of 3 finds the
    /// lone judge's receipt false; the judge loses its whole bond (half to the challenger), and the panel's majority
    /// decides the fix in place of that verdict.
    function test_aVerdictThroughAGateway() public {
        (uint256 id,) = _heldLoneVerdict(true, 3);
        uint256 cpid = _challenge(id, challenger);
        assertEq(pn.panel(cpid).k, 3);
        assertFalse(_contains(pn.judges(cpid), genesisKey));
        _judgeMasks(cpid, _same(3, false), 1); // every challenge judge: the receipt is false, the fix fails
        assertEq(_bond(genesisKey), 0);
        assertEq(reg.owed(challenger), FULL_BOND / 2);
        Submission memory s = pn.submission(id);
        assertTrue(s.lastUpheld);
        assertFalse(s.pass);
        assertFalse(s.challengeOpen);
    }

    function test_aModelOfAnotherFamily() public {
        test_aVerdictThroughAGateway();
    }

    /// Scenario "A zkTLS validator lies about the tests": a level C lone judge's receipt (test results a fresh panel
    /// doesn't reproduce) is upheld as false.
    function test_aZkTlsValidatorLiesAboutTheTests() public {
        _deployVersion(3, true);
        address pc = _add(keccak256("pc"), _family(1), 0, 3, FULL_BOND);
        vm.prank(genesisKey);
        reg.leave(genesisKey);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 10e6); // level C's k = 1 limit
        assertEq(pn.judges(pid)[0], pc);
        _judgeOne(pid, true);
        for (uint256 i = 2; i <= 4; ++i) {
            _add(keccak256(abi.encode("pc", i)), _family(i), 0, 3, FULL_BOND);
        }
        uint256 cpid = _challenge(id, challenger);
        _judgeMasks(cpid, _votes(3, 1), 1); // 2 of 3: the tests fail, the receipt is false
        assertEq(_bond(pc), 0);
        assertTrue(pn.submission(id).lastUpheld);
        assertFalse(pn.submission(id).pass);
    }

    // ---------- A challenge is judged by a larger, fresh panel ----------

    /// Scenario "A lone validator passes a bad fix": a fresh panel of 3 upholds the challenge; the fix doesn't pass,
    /// and it stays unpaid (final as failed).
    function test_aLoneValidatorPassesABadFix() public {
        (uint256 id,) = _heldLoneVerdict(true, 3);
        uint256 cpid = _challenge(id, challenger);
        _judge(cpid, _same(3, false));
        assertTrue(pn.submission(id).lastUpheld);
        assertFalse(pn.submission(id).pass);
        assertEq(_bond(genesisKey), FULL_BOND); // a wrong verdict with a valid receipt isn't slashed
        pn.startWindow(id);
        _finalize(id);
        assertFalse(pn.submission(id).pass);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Final));
    }

    /// Scenario "A challenge with too few validators": against a panel of 3 with only 3 others eligible, the challenge
    /// waits for a panel of 5, the verdict isn't final and its window doesn't run out; two more validators let it draw.
    function test_aChallengeWithTooFewValidators() public {
        _network(2, 3, 3);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 100e6);
        assertEq(pn.submission(id).k, 3);
        _network3(3);
        _judge(pid, _same(3, true));
        Submission memory s = pn.submission(id);
        uint256 left = s.finalAt - vm.getBlockTimestamp();
        assertEq(_challenge(id, challenger), 0);
        vm.warp(s.finalAt + 30 days);
        vm.expectRevert(Panels.NotReady.selector);
        pn.finalize(id);
        vm.expectRevert(Panels.NothingChanged.selector);
        pn.drawChallenge(id);
        _network3(2);
        pn.drawChallenge(id); // the registry changed: a fresh seed block and snapshot
        uint256 cpid = _drawChallenge(id);
        assertEq(pn.panel(cpid).k, 5);
        _judge(cpid, _same(5, true));
        assertFalse(pn.submission(id).lastUpheld);
        assertEq(pn.submission(id).finalAt, vm.getBlockTimestamp() + left); // the window resumes where it froze
    }

    function _network3(uint256 n) internal {
        for (uint256 i; i < n; ++i) {
            _addSpread(100 + nextId++, 7, 3);
        }
    }

    // ---------- An upheld receipt challenge ----------

    /// Scenario "A lone judge's false receipt on a bad fix": the whole bond, the verdict reversed, nothing paid.
    function test_aLoneJudgesFalseReceiptOnABadFix() public {
        (uint256 id,) = _heldLoneVerdict(true, 3);
        uint256 cpid = _challenge(id, challenger);
        _judgeMasks(cpid, _same(3, false), 1);
        assertEq(_bond(genesisKey), 0);
        assertFalse(pn.submission(id).pass);
    }

    /// Scenario "A false receipt on a fix the panel passes": the whole bond, and the verdict stands; a second dispute
    /// may still challenge it.
    function test_aFalseReceiptOnAFixThePanelPasses() public {
        (uint256 id,) = _heldLoneVerdict(true, 3);
        uint256 cpid = _challenge(id, challenger);
        _judgeMasks(cpid, _same(3, true), 1);
        assertEq(_bond(genesisKey), 0);
        Submission memory s = pn.submission(id);
        assertTrue(s.pass);
        assertTrue(s.lastUpheld);
        race.challenge(id, makeAddr("second auditor"), keccak256("dispute"));
        assertTrue(pn.submission(id).challengeOpen);
    }

    // ---------- Random audits re-check a share of verdicts ----------

    /// Finds a submission on a panel of 3 drawn for a random audit (AUDIT_RATE: 1 in 10); returns it with its audit
    /// panel, before the auditor judges.
    function _randomlyAudited() internal returns (uint256 id, uint256 apid) {
        _network(3, 4, 3);
        for (uint256 t; t < 80; ++t) {
            id = _id();
            uint256 pid = _openAndDraw(id, 100e6);
            _judge(pid, _same(3, true));
            _drawAudits(id);
            if (pn.submission(id).auditsDrawn == 1) return (id, pn.panelCount());
        }
        revert("no random audit in 80 draws");
    }

    /// Scenario "Nobody is watching": a wrong verdict nobody challenges is re-checked by its random audit, whose
    /// mismatch opens a challenge (no stake) before the window ends, freezing it.
    function test_nobodyIsWatching() public {
        (uint256 id, uint256 apid) = _randomlyAudited();
        address auditor = pn.judges(apid)[0];
        assertFalse(_contains(pn.judges(pn.submission(id).pid), auditor));
        _judgeOne(apid, false);
        Submission memory s = pn.submission(id);
        assertTrue(s.challengeOpen);
        assertEq(s.challenger, auditor);
        assertLt(vm.getBlockTimestamp(), s.finalAt);
        assertGt(s.frozenLeft, 0);
    }

    /// Scenario "An audit agrees": nothing changes, and the verdict becomes final.
    function test_anAuditAgrees() public {
        (uint256 id, uint256 apid) = _randomlyAudited();
        _judgeOne(apid, true);
        assertFalse(pn.submission(id).challengeOpen);
        assertEq(pn.submission(id).auditsDone, 1);
        _finalize(id);
        assertTrue(pn.submission(id).pass);
    }

    /// A panel's audit is decided by a block after its count, so its judges can't know when they vote whether it's
    /// audited; a k ≥ 3 verdict can't become final before the decision.
    function test_anAuditIsDecidedAfterTheCount() public {
        _network(3, 4, 3);
        uint256 id = _id();
        _judge(_openAndDraw(id, 100e6), _same(3, true));
        Submission memory s = pn.submission(id);
        assertFalse(s.auditDecided);
        assertEq(s.auditBlock, vm.getBlockNumber() + 5);
        vm.warp(s.finalAt);
        vm.expectRevert(Panels.NotReady.selector);
        pn.finalize(id);
    }

    // ---------- Every lone verdict is audited twice ----------

    /// Scenario "Validators qualify after the genesis": each held verdict is audited by the second and then by the
    /// third validator; a mismatch opens a challenge that waits for a fresh panel of 3.
    function test_validatorsQualifyAfterTheGenesis() public {
        (uint256 id,) = _heldLoneVerdict(true, 0);
        assertEq(pn.submission(id).auditsDue, 2);
        _drawAudits(id);
        assertEq(_auditPanels(id).length, 0); // nobody to audit yet
        address second = _addSpread(2, 7, 3);
        _drawAudits(id);
        uint256[] memory aps = _auditPanels(id);
        assertEq(aps.length, 1);
        assertEq(pn.judges(aps[0])[0], second);
        _judgeOne(aps[0], true);
        address third = _addSpread(3, 7, 3);
        _drawAudits(id);
        aps = _auditPanels(id);
        assertEq(aps.length, 2);
        assertEq(pn.judges(aps[1])[0], third);
        _judgeOne(aps[1], false);
        assertTrue(pn.submission(id).challengeOpen);
        assertEq(_drawChallenge(id), 0); // the genesis judge and both auditors sit out: it waits for 3 others
        assertEq(uint256(pn.submission(id).status), uint256(Status.Held));
    }

    /// Scenario "One auditor misses a bad fix": one auditor agrees, the other's mismatch opens a challenge before the
    /// verdict can be final.
    function test_oneAuditorMissesABadFix() public {
        bytes32 host = keccak256("host-genesis");
        for (uint256 i = 1; i <= 5; ++i) {
            _add(host, _family(i), _tee(i % 3), 1, FULL_BOND); // one host: k steps down to 1, challengers exist
        }
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 40e6);
        assertEq(pn.submission(id).k, 1);
        _judgeOne(pid, true);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Window));
        _drawAudits(id);
        uint256[] memory aps = _auditPanels(id);
        assertGe(aps.length, 2);
        address a0 = pn.judges(aps[0])[0];
        address a1 = pn.judges(aps[1])[0];
        assertTrue(a0 != a1 && a0 != pn.judges(pid)[0] && a1 != pn.judges(pid)[0]);
        _sealMask(aps[0], a0, true, 0);
        _sealMask(aps[1], a1, false, 0);
        vm.warp(pn.panel(aps[1]).sealBy + 1);
        _reveal(aps[0], a0);
        _receipt(aps[0], a0);
        _reveal(aps[1], a1);
        _receipt(aps[1], a1);
        assertTrue(pn.submission(id).challengeOpen);
        vm.warp(pn.submission(id).finalAt + 1);
        vm.expectRevert(Panels.NotReady.selector);
        pn.finalize(id);
    }

    // ---------- Every split level C pass is audited ----------

    /// Scenario "A split level C pass": a panel of 7 at level C passing 4 to 3 is audited before it can be final.
    function test_aSplitLevelCPass() public {
        _deployVersion(3, true);
        for (uint256 i = 1; i <= 8; ++i) {
            _add(keccak256(abi.encode("pc", i)), _family(i % 7), 0, 3, FULL_BOND);
        }
        vm.prank(genesisKey);
        reg.leave(genesisKey);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 100e6);
        assertEq(pn.submission(id).k, 7);
        _judge(pid, _votes(7, 4));
        Submission memory s = pn.submission(id);
        assertTrue(s.pass);
        assertEq(s.level, 3);
        assertGe(s.auditsDue, 1);
        vm.warp(s.finalAt);
        vm.expectRevert(Panels.NotReady.selector);
        pn.finalize(id);
        _finalize(id);
    }

    // ---------- The constitution tier ----------

    function _grown(uint256 eligible) internal {
        _network(eligible - 1, 7, 3);
        assertEq(reg.eligibleCount(1), eligible);
    }

    function _openAdr(uint256 id, Tier tier) internal {
        race.openConstitution(id, keccak256(abi.encode("adr", id)), tier, tier == Tier.Escalated ? 100e6 : 0, author);
    }

    /// Scenario "An ADR on a grown network": K_MAX are drawn and it needs the constitution threshold (5) of them.
    function test_anAdrOnAGrownNetwork() public {
        _grown(21);
        uint256 a = _id();
        _openAdr(a, Tier.Adr);
        uint256 pa = _draw(a);
        assertEq(pn.panel(pa).k, 7);
        _assertCapsOf(pa);
        _judge(pa, _votes(7, 5));
        assertTrue(pn.submission(a).pass);
        uint256 b = _id();
        _openAdr(b, Tier.Adr);
        _judge(_draw(b), _votes(7, 4)); // a majority of 7, but not the threshold
        assertFalse(pn.submission(b).pass);
    }

    /// Scenarios "An adding ADR on a small network" and "An ADR that expires": with 18 eligible it expires unjudged,
    /// nobody is drawn, and its deposit is refunded.
    function test_anAddingAdrOnASmallNetwork() public {
        _grown(18);
        uint256 a = _id();
        _openAdr(a, Tier.Adr);
        assertEq(uint256(pn.submission(a).status), uint256(Status.Expired));
        assertEq(usd.balanceOf(author), 15e6);
        assertEq(pn.panelCount(), 0);
        vm.expectRevert(Panels.WrongStatus.selector);
        pn.draw(a);
    }

    /// Scenario "A removal on a small network": an ADR that only removes is drawn from 15 eligible (14 needed).
    function test_aRemovalOnASmallNetwork() public {
        _grown(15);
        uint256 a = _id();
        _openAdr(a, Tier.Removal);
        uint256 pa = _draw(a);
        assertEq(pn.panel(pa).k, 7);
        _judge(pa, _votes(7, 6));
        assertEq(pn.submission(a).finalAt, vm.getBlockTimestamp() + 48 hours); // REMOVAL_WINDOW
    }

    /// Scenario "An ADR that removes and adds": it isn't a removal, so it needs 21 and expires from 15.
    function test_anAdrThatRemovesAndAdds() public {
        _grown(15);
        uint256 a = _id();
        _openAdr(a, Tier.Adr); // the race reads the ADR's operations: not all removals
        assertEq(uint256(pn.submission(a).status), uint256(Status.Expired));
    }

    /// Scenario "The network reaches the threshold": no earlier adding ADR is drawn when the twenty-first validator
    /// becomes eligible; only those submitted from then on.
    function test_theNetworkReachesTheThreshold() public {
        _grown(20);
        uint256 early = _id();
        _openAdr(early, Tier.Adr);
        _network3(1);
        assertEq(reg.eligibleCount(1), 21);
        vm.expectRevert(Panels.WrongStatus.selector);
        pn.draw(early);
        uint256 late = _id();
        _openAdr(late, Tier.Adr);
        assertGt(_draw(late), 0);
    }

    /// Scenario "A rejected ADR": its $15 deposit goes to the sponsors' pool.
    function test_aRejectedAdr() public {
        _grown(21);
        uint256 a = _id();
        _openAdr(a, Tier.Adr);
        _judge(_draw(a), _votes(7, 2));
        uint256 poolBefore = usd.balanceOf(address(pool));
        _finalize(a);
        assertEq(usd.balanceOf(address(pool)), poolBefore + 15e6);
        assertEq(usd.balanceOf(author), 0);
    }

    /// Scenario "A rejected escalated fix": the deposit goes to the sponsors' pool, not to the issue's funder or
    /// reporter (the race).
    function test_aRejectedEscalatedFix() public {
        _grown(21);
        uint256 a = _id();
        _openAdr(a, Tier.Escalated);
        assertEq(pn.submission(a).bounty, 100e6);
        _judge(_draw(a), _votes(7, 4));
        uint256 raceBefore = usd.balanceOf(address(race));
        uint256 poolBefore = usd.balanceOf(address(pool));
        _finalize(a);
        assertEq(usd.balanceOf(address(pool)), poolBefore + 15e6);
        assertEq(usd.balanceOf(address(race)), raceBefore);
        assertEq(usd.balanceOf(author), 0);
    }

    /// Scenario "An ADR that takes effect": passed, and its full window over with no challenge upheld: refunded.
    function test_anAdrThatTakesEffect() public {
        _grown(21);
        uint256 a = _id();
        _openAdr(a, Tier.Adr);
        _judge(_draw(a), _votes(7, 7));
        assertEq(pn.submission(a).finalAt, vm.getBlockTimestamp() + 14 days);
        _finalize(a);
        assertEq(usd.balanceOf(author), 15e6);
    }

    /// Scenario "An ADR passed by a mostly level C panel": it takes effect after the full window, whatever the level.
    function test_anAdrPassedByAMostlyLevelCPanel() public {
        _deployVersion(3, true);
        usd.mint(address(race), 1_000e6);
        for (uint256 i = 1; i <= 20; ++i) {
            _add(keccak256(abi.encode("pc", i)), _family(i % 7), 0, 3, FULL_BOND);
        }
        uint256 a = _id();
        _openAdr(a, Tier.Adr);
        _judge(_draw(a), _votes(7, 6));
        Submission memory s = pn.submission(a);
        assertEq(s.level, 3);
        assertEq(s.finalAt, vm.getBlockTimestamp() + 14 days);
    }

    // ---------- shadows (validator-admission, judge-panels) ----------

    /// Scenario "A candidate copies the counted judges": a shadow's seal window is the counted panel's; once it
    /// closes the counted judges reveal, and a late shadow seal is refused (a miss).
    function test_aCandidateCopiesTheCountedJudges() public {
        address cand = _addCandidate(keccak256("ch"), _family(2), SEV_SNP, 1, 100e6);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 40e6);
        uint256 spid = pn.submission(id).shadowPid;
        assertEq(pn.judges(spid)[0], cand);
        assertEq(pn.panel(spid).sealBy, pn.panel(pid).sealBy);
        _seal(pid, genesisKey, true);
        vm.warp(pn.panel(pid).sealBy + 1);
        _reveal(pid, genesisKey);
        bytes32 c = pn.commitmentOf(spid, cand, true, 0, _salt(spid, cand));
        bytes memory sig = _stmt(cand, pn.SEAL_TAG(), spid, c);
        vm.expectRevert(Panels.TooLate.selector);
        pn.seal(spid, cand, c, sig);
        vm.warp(pn.panel(spid).revealBy + 1);
        pn.settleShadows(spid);
        assertEq(reg.progress(cand).shadowDraws, 1);
        assertEq(reg.progress(cand).shadowReveals, 0);
    }

    /// Scenario "A submission waits for a panel": the published number of candidates are drawn as its shadows.
    function test_aSubmissionWaitsForAPanel() public {
        for (uint256 i = 1; i <= 4; ++i) {
            _addCandidate(keccak256(abi.encode("c", i)), _family(i), _tee(i % 3), 1, 100e6);
        }
        uint256 id = _id();
        assertEq(_openAndDraw(id, 100e6), 0);
        uint256 spid = pn.submission(id).shadowPid;
        assertEq(pn.panel(spid).k, 3);
        assertEq(uint256(pn.panel(spid).kind), uint256(Kind.Shadow));
        assertEq(pn.panel(spid).ex, 0);
    }

    /// Scenario "A waiting submission": three shadows, two vote fail; each is scored against the fail majority, the
    /// one that voted pass as disagreeing. Scenario "A silent shadow" too: a fourth draw's silent shadow loses nothing.
    function test_aWaitingSubmission() public {
        address[] memory cs = new address[](3);
        for (uint256 i; i < 3; ++i) {
            cs[i] = _addCandidate(keccak256(abi.encode("c", i)), _family(i + 1), _tee(i), 1, 100e6);
        }
        uint256 id = _id();
        _openAndDraw(id, 100e6);
        uint256 spid = pn.submission(id).shadowPid;
        address[] memory ss = pn.judges(spid);
        bool[3] memory v = [true, false, false];
        for (uint256 i; i < 3; ++i) {
            _seal(spid, ss[i], v[i]);
        }
        vm.warp(pn.panel(spid).sealBy + 1);
        for (uint256 i; i < 3; ++i) {
            _reveal(spid, ss[i]);
            _receipt(spid, ss[i]);
        }
        vm.warp(pn.panel(spid).revealBy + 1);
        pn.settleShadows(spid);
        assertEq(reg.progress(ss[0]).scored, 1);
        assertEq(reg.progress(ss[0]).agreed, 0);
        assertEq(reg.progress(ss[1]).agreed, 1);
        assertEq(reg.progress(ss[2]).agreed, 1);
        assertEq(reg.progress(ss[0]).shadowReveals, 1);
        bytes32 c = pn.commitmentOf(spid, ss[0], true, 0, bytes32(0));
        bytes memory sig = _stmt(ss[0], pn.SEAL_TAG(), spid, c);
        vm.expectRevert(Panels.NotOpen.selector); // settled: closed
        pn.seal(spid, ss[0], c, sig);
    }

    /// Scenario "A silent shadow": it loses nothing from its bond, and the miss counts toward its reveal rate.
    function test_aSilentShadow() public {
        address cand = _addCandidate(keccak256("c"), _family(2), SEV_SNP, 1, 100e6);
        uint256 id = _id();
        _openAndDraw(id, 100e6);
        uint256 spid = pn.submission(id).shadowPid;
        vm.warp(pn.panel(spid).revealBy + 1);
        vm.expectRevert(Panels.NothingDue.selector);
        pn.advance(spid); // shadows aren't replaced
        pn.settleShadows(spid);
        assertEq(_bond(cand), 100e6);
        assertEq(reg.progress(cand).shadowDraws, 1);
        assertEq(reg.progress(cand).shadowReveals, 0);
        assertEq(reg.progress(cand).scored, 0); // fewer than 3 revealed: not scored
    }

    /// Scenarios "A colluding genesis validator" and "A held verdict becomes final": the lone validator passes; two
    /// honest candidates shadowing vote fail. Held at its count, the shadows are scored once against the majority of
    /// the sealed verdicts (fail), not by the lone verdict, and not again when it becomes final.
    function test_aColludingGenesisValidator() public {
        address c1 = _addCandidate(keccak256("c1"), _family(2), SEV_SNP, 1, 100e6);
        address c2 = _addCandidate(keccak256("c2"), _family(3), NITRO, 1, 100e6);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 40e6);
        uint256 spid = pn.submission(id).shadowPid;
        assertEq(pn.panel(spid).k, 2); // SHADOW_PER_DRAW_SMALL while fewer than 7 are active
        _judgeBoth(pid, _same(1, true), spid, _same(2, false));
        assertTrue(pn.submission(id).heldAtCount);
        vm.warp(pn.panel(spid).revealBy + 1);
        pn.settleShadows(spid);
        assertEq(reg.progress(c1).agreed, 1);
        assertEq(reg.progress(c2).agreed, 1);
        assertEq(reg.progress(c1).scored, 1);
        // later the verdict becomes final: the shadows aren't scored again
        _network(3, 7, 3);
        pn.startWindow(id);
        _finalize(id);
        assertEq(reg.progress(c1).scored, 1);
        vm.expectRevert(Panels.NothingDue.selector);
        pn.settleShadows(spid);
    }

    /// Scenario "Challengers already eligible": a k = 1 verdict whose window starts at its reveal scores its shadows
    /// against its final outcome.
    function test_challengersAlreadyEligible() public {
        bytes32 host = keccak256("host-genesis");
        for (uint256 i = 1; i <= 4; ++i) {
            _add(host, _family(i), _tee(i % 3), 1, FULL_BOND);
        }
        address c1 = _addCandidate(keccak256("c1"), _family(5), SEV_SNP, 1, 100e6);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 40e6);
        assertEq(pn.submission(id).k, 1);
        uint256 spid = pn.submission(id).shadowPid;
        assertTrue(_contains(pn.judges(spid), c1));
        bool[] memory sv = new bool[](pn.panel(spid).k);
        _judgeBoth(pid, _same(1, true), spid, sv); // shadows vote fail; the outcome will be a pass
        assertFalse(pn.submission(id).heldAtCount);
        vm.warp(pn.panel(spid).revealBy + 1);
        pn.settleShadows(spid); // closed, but not scored before finality
        assertEq(reg.progress(c1).scored, 0);
        _finalize(id);
        assertEq(reg.progress(c1).scored, 1);
        assertEq(reg.progress(c1).agreed, 0);
    }

    // ---------- judge-scores ----------

    function _scoresBoundHere() internal returns (PanelScores s) {
        s = new PanelScores();
        s.bind();
    }

    /// Scenario "A judge that always votes pass": 78 % passed outcomes, every pass agreed, every fail not: 50 %.
    function test_aJudgeThatAlwaysVotesPass() public {
        PanelScores s = _scoresBoundHere();
        bytes32 f = keccak256("herder");
        for (uint256 i; i < 100; ++i) {
            bool passed = i % 50 < 39; // 78 of 100
            s.recordCounted(f, passed, passed);
        }
        (IFeesV3Scores.ScoreState st, uint256 score) = s.familyScore(f);
        assertEq(score, 0.5e18);
        assertEq(uint256(st), uint256(IFeesV3Scores.ScoreState.Barred)); // below SCORE_MIN over 50 or more
    }

    /// Scenario "Only one kind of outcome": the agreement on that kind.
    function test_onlyOneKindOfOutcome() public {
        PanelScores s = _scoresBoundHere();
        bytes32 f = keccak256("f");
        for (uint256 i; i < 60; ++i) {
            s.recordCounted(f, true, i % 10 != 0);
        }
        (, uint256 score) = s.familyScore(f);
        assertEq(score, 0.9e18);
    }

    /// Scenario "Recomputing a score": the window of the last 200, balanced, recomputed from the recorded verdicts.
    function test_recomputingAScore() public {
        PanelScores s = _scoresBoundHere();
        bytes32 f = keccak256("f");
        bool[] memory passed = new bool[](260);
        bool[] memory agreed = new bool[](260);
        for (uint256 i; i < 260; ++i) {
            uint256 r = uint256(keccak256(abi.encode(i)));
            passed[i] = r % 100 < 75;
            agreed[i] = (r >> 8) % 100 < (passed[i] ? 92 : 85);
            s.recordCounted(f, passed[i], agreed[i]);
        }
        uint256 pn_;
        uint256 pa;
        uint256 fn;
        uint256 fa;
        for (uint256 i = 60; i < 260; ++i) {
            if (passed[i]) {
                ++pn_;
                if (agreed[i]) ++pa;
            } else {
                ++fn;
                if (agreed[i]) ++fa;
            }
        }
        (, uint256 score) = s.familyScore(f);
        assertEq(score, (pa * 1e18 / pn_ + fa * 1e18 / fn) / 2);
        assertEq(s.family(f).n, 200);
    }

    /// Scenario "Shadow verdicts don't lift a score": a scored family's shadow verdicts leave its score unchanged.
    function test_shadowVerdictsDontLiftAScore() public {
        PanelScores s = _scoresBoundHere();
        bytes32 f = keccak256("f");
        for (uint256 i; i < 60; ++i) {
            s.recordCounted(f, i % 4 != 0, i % 5 != 0);
        }
        (IFeesV3Scores.ScoreState st0, uint256 before) = s.familyScore(f);
        for (uint256 i; i < 300; ++i) {
            s.recordShadow(f, true, true);
        }
        (IFeesV3Scores.ScoreState st1, uint256 afterwards) = s.familyScore(f);
        assertEq(afterwards, before);
        assertEq(uint256(st1), uint256(st0));
    }

    /// Scenario "A weak model": barred, its validators are drawn only as shadow judges.
    function test_aWeakModel() public {
        _network(4, 2, 3); // families 0 and 1
        bytes32 weak = _family(1);
        vm.startPrank(address(pn));
        for (uint256 i; i < 50; ++i) {
            scores.recordCounted(weak, i % 2 == 0, i % 10 < 6); // 60 %
        }
        vm.stopPrank();
        assertTrue(scores.isBarred(weak));
        for (uint256 r; r < 4; ++r) {
            uint256 id = _id();
            uint256 pid = _openAndDraw(id, 40e6);
            if (pid != 0) {
                address[] memory js = pn.judges(pid);
                for (uint256 i; i < js.length; ++i) {
                    assertTrue(reg.validator(js[i]).family != weak);
                }
            }
            uint256 spid = pn.submission(id).shadowPid;
            if (spid != 0) {
                address[] memory ss = pn.judges(spid);
                for (uint256 i; i < ss.length; ++i) {
                    assertEq(reg.validator(ss[i]).family, weak); // no candidates: only the barred family shadows
                }
            }
        }
    }

    /// Scenario "A model that gets better": a fresh block of 100 shadow verdicts at 85 % recovers it; paid the minimum
    /// factor until 50 new counted verdicts, then by its new score.
    function test_aModelThatGetsBetter() public {
        bytes32 f = _family(2);
        vm.startPrank(address(pn));
        for (uint256 i; i < 50; ++i) {
            scores.recordCounted(f, true, i % 10 < 6);
        }
        assertTrue(scores.isBarred(f));
        for (uint256 i; i < 100; ++i) {
            scores.recordShadow(f, i % 2 == 0, i % 20 < 17); // 85 %
        }
        (IFeesV3Scores.ScoreState st,) = scores.familyScore(f);
        assertEq(uint256(st), uint256(IFeesV3Scores.ScoreState.Recovering));
        assertEq(scores.barredCount(), 0);
        assertEq(fees.factorOf(f), 0.5e18);
        for (uint256 i; i < 49; ++i) {
            scores.recordCounted(f, i % 2 == 0, i % 20 < 17);
        }
        (st,) = scores.familyScore(f);
        assertEq(uint256(st), uint256(IFeesV3Scores.ScoreState.Recovering));
        scores.recordCounted(f, true, true);
        vm.stopPrank();
        (st,) = scores.familyScore(f);
        assertEq(uint256(st), uint256(IFeesV3Scores.ScoreState.Scored));
        assertGt(fees.factorOf(f), 0.5e18);
    }

    /// Scenario "A weak model's lucky streak": 50 shadow verdicts at 74 % inside a block of 100 at 71 %: still barred.
    function test_aWeakModelsLuckyStreak() public {
        bytes32 f = _family(2);
        vm.startPrank(address(pn));
        for (uint256 i; i < 50; ++i) {
            scores.recordCounted(f, true, i % 10 < 6);
        }
        for (uint256 i; i < 50; ++i) {
            scores.recordShadow(f, true, i < 37); // 74 %
        }
        assertTrue(scores.isBarred(f));
        for (uint256 i; i < 50; ++i) {
            scores.recordShadow(f, true, i < 34); // the block: 71 of 100
        }
        vm.stopPrank();
        assertTrue(scores.isBarred(f));
        assertEq(scores.family(f).bPassN, 0); // the block was judged once, and a fresh one started
    }

    /// Scenario "A newly released open model": no verdicts yet, drawn normally and paid 1 ×.
    function test_aNewlyReleasedOpenModel() public {
        (IFeesV3Scores.ScoreState st,) = scores.familyScore(keccak256("newlab/model"));
        assertEq(uint256(st), uint256(IFeesV3Scores.ScoreState.Neutral));
        assertFalse(scores.isBarred(keccak256("newlab/model")));
        assertEq(fees.factorOf(_family(5)), 1e18);
    }

    /// Scenario "A better model earns more": with the real scores, the family scored higher has the higher factor.
    function test_aBetterModelEarnsMore() public {
        vm.startPrank(address(pn));
        for (uint256 i; i < 60; ++i) {
            scores.recordCounted(_family(1), i % 2 == 0, i % 20 < 19); // 95 %
            scores.recordCounted(_family(2), i % 2 == 0, i % 20 < 16); // 80 %
        }
        vm.stopPrank();
        assertGt(fees.factorOf(_family(1)), fees.factorOf(_family(2)));
    }

    /// Scenarios "A reversal counts as the truth" and "A high-score family in the minority": a panel passes 2 to 1, a
    /// challenge reverses it; at finality the judge that voted fail is scored as agreeing, the two others as not.
    function test_aReversalCountsAsTheTruth() public {
        _network(2, 3, 3);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 100e6);
        address[] memory js = pn.judges(pid);
        _network3(6);
        bool[] memory v = new bool[](3);
        v[0] = true;
        v[1] = true;
        _judge(pid, v);
        assertTrue(pn.submission(id).pass);
        uint256 cpid = _challenge(id, challenger);
        _judge(cpid, _same(pn.panel(cpid).k, false));
        assertFalse(pn.submission(id).pass);
        _finalize(id);
        bytes32 fFail = reg.validator(js[2]).family;
        bytes32 fPass = reg.validator(js[0]).family;
        assertEq(scores.family(fFail).failAgree, 1);
        assertEq(scores.family(fPass).failN, 1);
        assertEq(scores.family(fPass).failAgree, 0);
    }

    /// Scenario "A high-score family in the minority": one vote of a top family passes, two fail: the fix fails.
    function test_aHighScoreFamilyInTheMinority() public {
        _network(2, 3, 3);
        vm.startPrank(address(pn));
        for (uint256 i; i < 60; ++i) {
            scores.recordCounted(_family(0), i % 2 == 0, true); // 100 %
        }
        vm.stopPrank();
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 100e6);
        address[] memory js = pn.judges(pid);
        bool[] memory v = new bool[](3);
        for (uint256 i; i < 3; ++i) {
            v[i] = reg.validator(js[i]).family == _family(0);
        }
        _judge(pid, v);
        assertFalse(pn.submission(id).pass);
    }

    // ---------- the snapshot: the draw doesn't follow changes made after its seed is fixed ----------

    /// An attacker who sees the seed block's hash leaves with one validator and tops another up across a tier (and
    /// registers and qualifies a third) in the draw's block: the panel is the one the snapshot gave.
    function test_aDrawIgnoresRegistryChangesAfterItsSnapshot() public {
        _network(14, 7, 3);
        address[] memory ks = new address[](4);
        for (uint256 i; i < 4; ++i) {
            // bonded $700: eligible for the $300 bounty's tier ($312.50), one bucket below the top
            ks[i] = _add(keccak256(abi.encode("mid", i)), _family(i), _tee(i % 3), 1, 700e6);
        }
        address low = _add(keccak256("low"), _family(6), NITRO, 1, 100e6); // below the $300 bounty's tier
        uint256 id = _id();
        _open(id, 300e6);
        uint256 sb = pn.submission(id).seedBlock;
        _rollPast(sb);
        (uint256 k,, address[] memory expected,) = pn.sample(id, _seedFor(id));
        assertEq(k, 7);
        // the attacker's moves, after the hash is known
        address leaver;
        address topper;
        for (uint256 i; i < ks.length && (leaver == address(0) || topper == address(0)); ++i) {
            if (_contains(expected, ks[i])) continue;
            if (topper == address(0)) topper = ks[i];
            else leaver = ks[i];
        }
        assertTrue(leaver != address(0) && topper != address(0));
        vm.prank(leaver);
        reg.leave(leaver);
        usd.mint(address(this), 2_000e6);
        usd.approve(address(reg), type(uint256).max);
        reg.topUp(topper, 600e6); // $700 → $1,300: across a tier, into the top bucket
        reg.topUp(low, 1_200e6); // now bonded for the bounty: an addition the snapshot doesn't see
        _addSpread(77, 7, 3); // a newcomer qualified in the draw's block
        assertTrue(reg.eligibleCount(300e6) != pn.submission(id).snap.nLive); // the live set did change
        pn.draw(id);
        address[] memory js = pn.judges(pn.submission(id).pid);
        assertEq(js.length, expected.length);
        for (uint256 i; i < js.length; ++i) {
            assertEq(js[i], expected[i]);
        }
    }

    /// A drawn validator that leaves in the draw's block only removes itself: the others keep their seats, and its
    /// seat goes to the next one in the sample, as for a silent judge.
    function test_aLeaverOnlyRemovesItself() public {
        _deployVersion(5, false); // 15 validators, 3 of each TEE type and at most 3 of a family: no cap binds at k = 7
        _network(14, 7, 5);
        uint256 id = _id();
        _open(id, 300e6);
        _rollPast(pn.submission(id).seedBlock);
        (,, address[] memory expected,) = pn.sample(id, _seedFor(id));
        address gone = expected[3];
        vm.prank(gone);
        reg.leave(gone);
        pn.draw(id);
        address[] memory js = pn.judges(pn.submission(id).pid);
        assertFalse(_contains(js, gone));
        for (uint256 i; i < expected.length; ++i) {
            if (expected[i] != gone) assertTrue(_contains(js, expected[i]));
        }
    }

    /// The audit draw reads the snapshot fixed at the count: a validator registered after it isn't an auditor until
    /// a re-targeted attempt, whose snapshot is taken before its own seed block.
    function test_anAuditDrawIgnoresChangesAfterItsSnapshot() public {
        (uint256 id,) = _heldLoneVerdict(true, 0);
        _addSpread(5, 7, 3); // after the count's snapshot
        _rollPast(pn.submission(id).auditBlock);
        pn.drawAudits(id);
        assertEq(_auditPanels(id).length, 0);
        assertGt(pn.submission(id).auditBlock, vm.getBlockNumber()); // re-targeted, with a fresh snapshot
        _rollPast(pn.submission(id).auditBlock);
        pn.drawAudits(id);
        assertEq(_auditPanels(id).length, 1);
    }

    /// The rosters hold every drawable validator of each tier (Validators, #138).
    function test_theRostersCoverTheDrawableValidators() public {
        _network(6, 7, 3);
        _add(keccak256("small"), _family(3), SEV_SNP, 1, 100e6);
        for (uint256 t; t < 7; ++t) {
            uint256 len = reg.rosterLength(t);
            uint256 live;
            for (uint256 i; i < len; ++i) {
                (,, uint8 bucket) = reg.rosterEntry(t, i);
                if (bucket > t) ++live;
            }
            assertEq(live, reg.eligibleCount(reg.tierStep(t)));
        }
    }

    // ---------- sizes ----------

    /// Every contract of Panels' split stays under EIP-170 (forge's size table leaves some linked libraries out).
    function test_everyPanelsContractFitsEip170() public view {
        string[6] memory names = ["Panels", "PanelsJudge", "PanelsVerdict", "PanelsDraw", "PanelScores", "Validators"];
        for (uint256 i; i < names.length; ++i) {
            string memory json = vm.readFile(string.concat("out/", names[i], ".sol/", names[i], ".json"));
            // linked code holds library placeholders, so count hex digits rather than parse bytes
            uint256 size = (bytes(vm.parseJsonString(json, ".deployedBytecode.object")).length - 2) / 2;
            assertLt(size, 24_577, names[i]);
            assertGt(size, 0, names[i]);
        }
    }

    // ---------- helpers ----------

    function _assertCapsOf(uint256 pid) internal view {
        address[] memory js = pn.judges(pid);
        uint256 cap = (js.length - 1) / 2;
        for (uint256 i; i < js.length; ++i) {
            uint256 fams;
            uint256 hosts;
            for (uint256 j; j < js.length; ++j) {
                if (reg.validator(js[j]).family == reg.validator(js[i]).family) ++fams;
                if (reg.validator(js[j]).host == reg.validator(js[i]).host) ++hosts;
            }
            assertLe(fams, cap);
            assertLe(hosts, cap);
        }
    }
}
