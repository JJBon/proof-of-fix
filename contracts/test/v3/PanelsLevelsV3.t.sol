// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {console} from "forge-std/Test.sol";
import {Validators} from "../../src/v3/Validators.sol";
import {IValidators} from "../../src/v3/IValidators.sol";
import {Panels} from "../../src/v3/Panels.sol";
import {Status, Tier, Kind, Submission, Panel} from "../../src/v3/PanelsBase.sol";
import {PanelsSetup, IBM_SE} from "./helpers/PanelsSetup.sol";
import {TDX, SEV_SNP, NITRO, SGX, IMAGE} from "./helpers/ValidatorsSetup.sol";

/// proof-of-fix#138, task 3.4 of #132 (design D6, D7, D10, D11, D16, D18) through Panels: the constitution's lists
/// changed only by ADRs the constitution tier passed, after the full window for additions and REMOVAL_WINDOW for
/// removals; firmware minimums in the draw; all-TEE panels for hidden tests and private repositories; the limits and
/// windows per (k, level); and the owner's decision on a reveal missed after the majority revealed (option 2 of #227).
contract PanelsLevelsV3Test is PanelsSetup {
    uint256 internal nextId = 5000;
    address internal author = makeAddr("adr author");
    address internal challenger = makeAddr("challenger");

    function setUp() public {
        _deployVersion(3, false);
        usd.mint(address(race), 1_000e6);
    }

    function _id() internal returns (uint256) {
        return nextId++;
    }

    // ---------- helpers ----------

    function _ch(IValidators.Op op, bytes32 id, uint32 fw) internal pure returns (IValidators.Change memory c) {
        c.op = op;
        c.id = id;
        c.firmware = fw;
    }

    function _one(IValidators.Op op, bytes32 id, uint32 fw) internal pure returns (IValidators.Change[] memory cs) {
        cs = new IValidators.Change[](1);
        cs[0] = _ch(op, id, fw);
    }

    /// Opens an ADR with `cs` at `tier`, bound by its commitment, and has its K_MAX judges vote `passes` of 7.
    function _judgedAdr(IValidators.Change[] memory cs, Tier tier, uint256 passes)
        internal
        returns (uint256 id, bytes32 text)
    {
        id = _id();
        text = keccak256(abi.encode("adr text", id));
        race.openConstitution(id, reg.adrCommitment(text, cs), tier, 0, author);
        uint256 pid = _draw(id);
        assertEq(pn.panel(pid).k, 7);
        _judge(pid, _votes(7, passes));
    }

    /// An ADR passed by the constitution tier, final after its window, and applied.
    function _enact(IValidators.Change[] memory cs, Tier tier) internal returns (uint256 id) {
        bytes32 text;
        (id, text) = _judgedAdr(cs, tier, 7);
        _finalize(id);
        reg.applyAdr(id, text, cs);
    }

    function _reattest(address key, bytes32 image, uint32 fw) internal {
        bytes32 att = keccak256(abi.encode("re-attestation", key, fw));
        bytes memory sig = _signDigest(key, reg.reattestationDigest(key, att, image, fw));
        reg.reattest(key, att, image, fw, sig);
    }

    function _ofType(bytes32 tee) internal view returns (address[] memory out) {
        uint256 n = reg.validatorCount();
        out = new address[](n);
        uint256 m;
        for (uint256 i; i < n; ++i) {
            address key = reg.validatorAt(i);
            if (reg.validator(key).teeType == tee) out[m++] = key;
        }
        assembly ("memory-safe") {
            mstore(out, m)
        }
    }

    function _countType(address[] memory js, bytes32 tee) internal view returns (uint256 n) {
        for (uint256 i; i < js.length; ++i) {
            if (js[i] != address(0) && reg.validator(js[i]).teeType == tee) ++n;
        }
    }

    function _countLevel(address[] memory js, uint8 level) internal view returns (uint256 n) {
        for (uint256 i; i < js.length; ++i) {
            if (js[i] != address(0) && reg.validator(js[i]).level == level) ++n;
        }
    }

    function _openHidden(uint256 id, uint256 bounty) internal returns (uint256) {
        race.openHidden(id, keccak256(abi.encode("commitment", id)), bounty);
        return _draw(id);
    }

    // ---------- A broken type is removed faster than a new one is added ----------

    /// Scenario "A new TEE type proposed", through the constitution tier: an ADR adding Intel SGX and IBM Secure
    /// Execution takes effect only after the full 14-day window; until it's final nothing changes. Then five types
    /// are accepted and the TEE-type cap starts at k = 3, from the next draw.
    function test_anAddingAdrTakesEffectOnlyAfterTheFullWindow() public {
        _network(20, 7, 3);
        IValidators.Change[] memory cs = new IValidators.Change[](2);
        cs[0] = _ch(IValidators.Op.AddTeeType, SGX, 0);
        cs[1] = _ch(IValidators.Op.AddTeeType, IBM_SE, 0);
        (uint256 id, bytes32 text) = _judgedAdr(cs, Tier.Adr, 6);
        Submission memory s = pn.submission(id);
        assertEq(s.finalAt, vm.getBlockTimestamp() + 14 days);
        vm.expectRevert(Validators.NotPassed.selector);
        reg.applyAdr(id, text, cs);
        vm.warp(s.finalAt - 1);
        vm.expectRevert(Panels.TooEarly.selector);
        pn.finalize(id);
        _finalize(id);
        assertEq(pn.teeCapFrom(), 5);
        reg.applyAdr(id, text, cs);
        assertEq(reg.teeTypeCount(), 5);
        assertEq(pn.teeCapFrom(), 3);
        // the new types register, each its own type under the cap
        for (uint256 i; i < 4; ++i) {
            _add(keccak256(abi.encode("new type host", i)), _family(i), i % 2 == 0 ? SGX : IBM_SE, 1, FULL_BOND);
        }
        bool sawNew;
        for (uint256 r; r < 6; ++r) {
            uint256 pid = _openAndDraw(_id(), 100e6);
            address[] memory js = pn.judges(pid);
            bytes32[5] memory ts = [TDX, SEV_SNP, NITRO, SGX, IBM_SE];
            for (uint256 t; t < 5; ++t) {
                assertLe(_countType(js, ts[t]), (js.length - 1) / 2);
            }
            if (_countType(js, SGX) + _countType(js, IBM_SE) > 0) sawNew = true;
        }
        assertTrue(sawNew);
    }

    /// Scenario "An exploit is published for a TEE type", through the constitution tier: a removal is drawn from 14
    /// eligible, takes effect after the 48-hour REMOVAL_WINDOW, and from then on that type's validators aren't drawn and
    /// keep their bonds.
    function test_aRemovalTakesEffectAfterTheRemovalWindow() public {
        _network(13, 7, 3);
        address[] memory nitro = _ofType(NITRO);
        assertGt(nitro.length, 0);
        uint256 eligible = reg.eligibleCount(1);
        (uint256 id, bytes32 text) = _judgedAdr(_one(IValidators.Op.RemoveTeeType, NITRO, 0), Tier.Removal, 6);
        assertEq(pn.submission(id).finalAt, vm.getBlockTimestamp() + 48 hours);
        _finalize(id);
        reg.applyAdr(id, text, _one(IValidators.Op.RemoveTeeType, NITRO, 0));
        assertEq(reg.eligibleCount(1), eligible - nitro.length);
        for (uint256 r; r < 5; ++r) {
            uint256 pid = _openAndDraw(_id(), 100e6);
            assertGt(pid, 0);
            assertEq(_countType(pn.judges(pid), NITRO), 0);
        }
        for (uint256 i; i < nitro.length; ++i) {
            assertEq(_bond(nitro[i]), FULL_BOND);
        }
    }

    /// Scenario "A type is removed", through an ADR: one of five accepted TEE types removed, the TEE-type cap applies
    /// only from k = 5 from the next draw.
    function test_aTypeIsRemovedByAdr() public {
        _deployVersion(5, false);
        usd.mint(address(race), 1_000e6);
        _network(13, 7, 5);
        assertEq(pn.teeCapFrom(), 3);
        _enact(_one(IValidators.Op.RemoveTeeType, IBM_SE, 0), Tier.Removal);
        assertEq(pn.teeCapFrom(), 5);
    }

    /// An ADR drawn by the removal path that adds anything never takes effect, even passed (the race reads its
    /// operations at the opening with `isRemoval`; the registry checks them again when they're applied).
    function test_aRemovalCarryingAnAdditionNeverTakesEffect() public {
        _network(13, 7, 3);
        IValidators.Change[] memory cs = new IValidators.Change[](2);
        cs[0] = _ch(IValidators.Op.RemoveTeeType, NITRO, 0);
        cs[1] = _ch(IValidators.Op.AddImage, keccak256("an image slipped in"), 0);
        assertFalse(reg.isRemoval(cs));
        (uint256 id, bytes32 text) = _judgedAdr(cs, Tier.Removal, 7);
        _finalize(id);
        vm.expectRevert(Validators.NotARemoval.selector);
        reg.applyAdr(id, text, cs);
        assertTrue(reg.acceptedTeeType(NITRO));
    }

    /// A rejected ADR never takes effect.
    function test_aRejectedAdrNeverTakesEffect() public {
        _network(20, 7, 3);
        IValidators.Change[] memory cs = _one(IValidators.Op.AddTeeType, SGX, 0);
        (uint256 id, bytes32 text) = _judgedAdr(cs, Tier.Adr, 4);
        _finalize(id);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Final));
        vm.expectRevert(Validators.NotPassed.selector);
        reg.applyAdr(id, text, cs);
    }

    /// An escalated fix is judged at the constitution tier but changes no list.
    function test_anEscalatedFixChangesNoList() public {
        _network(20, 7, 3);
        uint256 id = _id();
        race.openConstitution(id, keccak256("escalated fix"), Tier.Escalated, 100e6, author);
        _judge(_draw(id), _votes(7, 7));
        _finalize(id);
        assertFalse(reg.adr(id).passed);
    }

    // ---------- TEE attestations meet the minimum firmware level ----------

    /// Scenario "A flaw is patched", through the constitution tier: after the removal window, TDX validators on the
    /// old firmware stop being drawn at once (before any re-check). Those that attest again on the patched firmware
    /// aren't drawn for a submission whose snapshot is older, and return for later ones without a new qualification.
    function test_aFlawIsPatchedThroughTheConstitution() public {
        _network(13, 7, 3);
        address[] memory tdx = _ofType(TDX);
        assertGt(tdx.length, 1);
        _enact(_one(IValidators.Op.RaiseFirmware, TDX, 1), Tier.Removal);
        for (uint256 r; r < 4; ++r) {
            uint256 pid = _openAndDraw(_id(), 100e6);
            assertGt(pid, 0);
            assertEq(_countType(pn.judges(pid), TDX), 0);
        }
        uint256 inFlight = _id();
        _open(inFlight, 100e6);
        vm.roll(vm.getBlockNumber() + 1);
        for (uint256 i; i < tdx.length; ++i) {
            _reattest(tdx[i], IMAGE, 1);
            assertEq(uint256(reg.validator(tdx[i]).state), uint256(IValidators.State.Active));
        }
        uint256 p0 = _draw(inFlight);
        assertEq(_countType(pn.judges(p0), TDX), 0);
        bool back;
        for (uint256 r; r < 6 && !back; ++r) {
            back = _countType(pn.judges(_openAndDraw(_id(), 100e6)), TDX) > 0;
        }
        assertTrue(back);
    }

    // ---------- All-TEE panels for hidden tests and private repositories ----------

    /// Hidden tests and private repositories go only to judges at level A or B (D10): the counted panel, its shadows,
    /// its auditors and its challenge panel. The same network seats level C judges on ordinary submissions.
    function test_hiddenTestsGoOnlyToLevelAOrBJudges() public {
        _deployVersion(3, true);
        usd.mint(address(race), 1_000e6);
        for (uint256 i = 1; i <= 7; ++i) {
            _add(keccak256(abi.encode("tee host", i)), _family(i % 7), _tee(i % 3), i % 2 == 0 ? 1 : 2, FULL_BOND);
        }
        for (uint256 i = 1; i <= 8; ++i) {
            _add(keccak256(abi.encode("pc", i)), _family(i % 7), 0, 3, FULL_BOND);
        }
        for (uint256 i; i < 4; ++i) {
            _addCandidate(keccak256(abi.encode("cand pc", i)), _family(i), 0, 3, 100e6);
            _addCandidate(keccak256(abi.encode("cand tee", i)), _family(i), _tee(i % 3), 1, 100e6);
        }
        bool sawC;
        for (uint256 r; r < 4; ++r) {
            uint256 id = _id();
            uint256 pid = _openHidden(id, 100e6);
            assertGt(pid, 0);
            assertTrue(pn.submission(id).teeOnly);
            assertEq(_countLevel(pn.judges(pid), 3), 0);
            assertLe(pn.submission(id).level, 2);
            uint256 sp = pn.submission(id).shadowPid;
            if (sp != 0) assertEq(_countLevel(pn.judges(sp), 3), 0);
            sawC = sawC || _countLevel(pn.judges(_openAndDraw(_id(), 100e6)), 3) > 0;
        }
        assertTrue(sawC);
        // a challenge of a hidden-test verdict, and its audits, draw level A or B only
        uint256 hid = _id();
        uint256 hp = _openHidden(hid, 100e6);
        _judge(hp, _votes(pn.panel(hp).k, pn.panel(hp).k));
        _runAudits(hid, true);
        for (uint256 q = 1; q <= pn.panelCount(); ++q) {
            Panel memory p = pn.panel(q);
            if (p.id == hid && p.kind == Kind.Audit) assertEq(_countLevel(pn.judges(q), 3), 0);
        }
        if (pn.submission(hid).status == Status.Window && !pn.submission(hid).challengeOpen) {
            race.challenge(hid, challenger, keccak256("evidence"));
            _rollPast(pn.submission(hid).challengeBlock);
            pn.drawChallenge(hid);
            uint256 cp = pn.submission(hid).challengePid;
            if (cp != 0) assertEq(_countLevel(pn.judges(cp), 3), 0);
        }
    }

    /// On a network of ordinary PCs, a hidden-test submission waits: no level C judge may see what it hides, while an
    /// ordinary submission is judged at level C.
    function test_hiddenTestsWaitOnANetworkOfOrdinaryPCs() public {
        _deployVersion(3, true);
        usd.mint(address(race), 1_000e6);
        for (uint256 i = 1; i <= 6; ++i) {
            _add(keccak256(abi.encode("pc", i)), _family(i), 0, 3, FULL_BOND);
        }
        // with the genesis (level A) still there, the hidden one steps down to it alone
        uint256 a = _id();
        uint256 pa = _openHidden(a, 40e6);
        assertEq(pn.submission(a).k, 1);
        assertEq(pn.judges(pa)[0], genesisKey);
        vm.prank(genesisKey);
        reg.leave(genesisKey);
        uint256 b = _id();
        assertEq(_openHidden(b, 40e6), 0);
        assertEq(uint256(pn.submission(b).status), uint256(Status.Waiting));
        uint256 c = _id();
        uint256 pc = _openAndDraw(c, 40e6);
        assertGt(pc, 0);
        assertEq(pn.submission(c).k, 5);
        assertEq(pn.submission(c).level, 3);
    }

    /// A hidden-test k = 1 verdict is held until three level A or B validators could judge its challenge: level C
    /// validators don't count toward its hold.
    function test_aHiddenLoneVerdictWaitsForTeeChallengers() public {
        _deployVersion(3, true);
        usd.mint(address(race), 1_000e6);
        uint256 id = _id();
        uint256 pid = _openHidden(id, 40e6);
        _judge(pid, _votes(1, 1));
        assertEq(uint256(pn.submission(id).status), uint256(Status.Held));
        for (uint256 i = 1; i <= 3; ++i) {
            _add(keccak256(abi.encode("pc", i)), _family(i), 0, 3, FULL_BOND);
        }
        vm.expectRevert(Panels.NotReady.selector);
        pn.startWindow(id);
        for (uint256 i = 1; i <= 3; ++i) {
            _add(keccak256(abi.encode("tee", i)), _family(i + 3), _tee(i % 3), 2, FULL_BOND);
        }
        pn.startWindow(id);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Window));
    }

    // ---------- Limits and windows per (k, level) ----------

    /// ADR 0004's table: the largest bounty and the challenge window for every panel size and proof level.
    function test_theLimitsAndWindowsPerKAndLevel() public view {
        uint256[4] memory ks = [uint256(1), 3, 5, 7];
        uint256[4] memory limA = [uint256(50e6), 250e6, 625e6, 625e6];
        uint256[4] memory limC = [uint256(10e6), 50e6, 125e6, 250e6];
        uint256[4] memory winA = [uint256(168 hours), 24 hours, 12 hours, 6 hours];
        uint256[4] memory winC = [uint256(336 hours), 72 hours, 48 hours, 24 hours];
        for (uint256 i; i < 4; ++i) {
            assertEq(pn.limitOf(ks[i], 1), limA[i]);
            assertEq(pn.limitOf(ks[i], 2), limA[i] / 2);
            assertEq(pn.limitOf(ks[i], 3), limC[i]);
            assertEq(pn.windowOf(ks[i], 1), winA[i]);
            assertEq(pn.windowOf(ks[i], 2), 2 * winA[i]);
            assertEq(pn.windowOf(ks[i], 3), winC[i]);
            // weaker levels never get more, nor wait less (C's limits at most B's, C's windows at least B's)
            assertLe(pn.limitOf(ks[i], 3), pn.limitOf(ks[i], 2));
            assertGe(pn.windowOf(ks[i], 3), pn.windowOf(ks[i], 2));
        }
        assertGe(pn.windowOf(1, 1), 7 days); // k = 1 waits at least 7 days (D4)
    }

    /// A level B panel of 5 judges up to level B's limit for k = 5 ($312.50), with level B's window (24 h); above that
    /// limit the draw is void and the submission waits.
    function test_aLevelBPanelOf5() public {
        _add(keccak256("b1"), _family(1), SEV_SNP, 2, FULL_BOND);
        _add(keccak256("b2"), _family(2), NITRO, 2, FULL_BOND);
        _add(keccak256("b3"), _family(3), SEV_SNP, 2, FULL_BOND);
        _add(keccak256("b4"), _family(4), NITRO, 2, FULL_BOND);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 300e6);
        assertEq(pn.submission(id).k, 5);
        _judge(pid, _votes(5, 5));
        Submission memory s = pn.submission(id);
        assertEq(s.level, 2);
        assertEq(s.finalAt, vm.getBlockTimestamp() + 24 hours);
        uint256 id2 = _id();
        assertEq(_openAndDraw(id2, 400e6), 0);
        assertEq(uint256(pn.submission(id2).status), uint256(Status.Waiting));
    }

    // ---------- A reveal missed after the majority revealed (owner, 2026-11-13, option 2) ----------

    /// A counted judge that sealed but didn't reveal in time, after the revealed votes already hold (k + 1) / 2 on one
    /// side: it's slashed ($5) and counts a miss, but isn't replaced; the verdict counts with the revealed majority.
    /// A challenge and finality then work around its empty seat.
    function test_aMissedRevealAfterAMajorityRevealed() public {
        _network(15, 7, 3);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 100e6);
        address[] memory js = pn.judges(pid);
        assertEq(js.length, 7);
        bool[7] memory votes = [true, true, true, true, false, true, false];
        for (uint256 i; i < 7; ++i) {
            _seal(pid, js[i], votes[i]);
        }
        vm.warp(pn.panel(pid).sealBy + 1);
        for (uint256 i; i < 5; ++i) {
            _reveal(pid, js[i]);
            _receipt(pid, js[i]);
        }
        _reveal(pid, js[5]); // revealed without its receipt: a sealed vote not revealed
        uint256 b5 = _bond(js[5]);
        uint256 b6 = _bond(js[6]);
        uint256 panelsBefore = pn.panelCount();
        vm.warp(pn.panel(pid).revealBy + 1);
        pn.advance(pid);
        assertEq(_bond(js[5]), b5 - 5e6);
        assertEq(_bond(js[6]), b6 - 5e6);
        assertEq(reg.progress(js[5]).misses, 1);
        assertEq(reg.progress(js[6]).misses, 1);
        assertEq(reg.validator(js[6]).openVerdicts, 0);
        // not replaced: the seats are empty and no seal window reopened
        assertEq(pn.judges(pid)[5], address(0));
        assertEq(pn.judges(pid)[6], address(0));
        Panel memory p = pn.panel(pid);
        assertTrue(p.counted);
        assertEq(p.seats, 5);
        assertEq(p.k, 7);
        assertEq(p.passes, 4);
        assertEq(pn.panelCount(), panelsBefore);
        Submission memory s = pn.submission(id);
        assertTrue(s.pass);
        assertEq(s.k, 7);
        assertEq(uint256(s.status), uint256(Status.Window));
        assertEq(s.finalAt, vm.getBlockTimestamp() + 6 hours);
        // a challenge passes over the empty seats; the slashed judges can't sit on it
        race.challenge(id, challenger, keccak256("evidence"));
        _rollPast(pn.submission(id).challengeBlock);
        pn.drawChallenge(id);
        uint256 cp = pn.submission(id).challengePid;
        assertGt(cp, 0);
        address[] memory cj = pn.judges(cp);
        assertFalse(_contains(cj, js[5]) || _contains(cj, js[6]));
        _judge(cp, _votes(cj.length, cj.length));
        assertFalse(pn.submission(id).challengeOpen);
        _finalize(id);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Final));
        assertEq(reg.validator(js[0]).openVerdicts, 0);
    }

    /// With no majority among the revealed votes yet, a missed reveal is replaced as before, k and the majority
    /// unchanged.
    function test_aMissedRevealWithNoMajorityYet() public {
        _network(3, 4, 3);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 100e6);
        address[] memory js = pn.judges(pid);
        _seal(pid, js[0], true);
        _seal(pid, js[1], false);
        _seal(pid, js[2], true);
        vm.warp(pn.panel(pid).sealBy + 1);
        _reveal(pid, js[0]);
        _receipt(pid, js[0]);
        _reveal(pid, js[1]);
        _receipt(pid, js[1]);
        uint256 b2 = _bond(js[2]);
        vm.warp(pn.panel(pid).revealBy + 1);
        pn.advance(pid);
        assertEq(_bond(js[2]), b2 - 5e6);
        assertFalse(pn.panel(pid).counted);
        address repl = pn.judges(pid)[2];
        assertTrue(repl != address(0) && repl != js[2]);
        _seal(pid, repl, true);
        vm.warp(pn.panel(pid).sealBy + 1);
        _reveal(pid, repl);
        _receipt(pid, repl);
        assertTrue(pn.panel(pid).counted);
        assertEq(pn.panel(pid).passes, 2);
        assertTrue(pn.submission(id).pass);
    }

    /// At the constitution tier "decided" means the threshold: 5 passes revealed pass it, 3 fails revealed reject it,
    /// and anything short of either is replaced.
    function test_aMissedRevealAtTheConstitutionTier() public {
        _network(20, 7, 3);
        bool[7] memory five = [true, true, true, true, true, false, false];
        bool[7] memory four = [true, true, true, true, false, false, false];
        bool[7] memory threeFails = [false, false, false, true, true, false, false];
        bool[7][3] memory cases = [five, four, threeFails];
        for (uint256 c; c < 3; ++c) {
            uint256 id = _id();
            race.openConstitution(id, keccak256(abi.encode("adr", id)), Tier.Adr, 0, author);
            uint256 pid = _draw(id);
            address[] memory js = pn.judges(pid);
            for (uint256 i; i < 7; ++i) {
                _seal(pid, js[i], cases[c][i]);
            }
            vm.warp(pn.panel(pid).sealBy + 1);
            for (uint256 i; i < 5; ++i) {
                _reveal(pid, js[i]);
                _receipt(pid, js[i]);
            }
            vm.warp(pn.panel(pid).revealBy + 1);
            pn.advance(pid);
            if (c == 1) {
                assertFalse(pn.panel(pid).counted); // 4 passes, 1 fail: the threshold could still go either way
                assertTrue(pn.judges(pid)[5] != address(0) && pn.judges(pid)[5] != js[5]);
            } else {
                assertTrue(pn.panel(pid).counted);
                assertEq(pn.submission(id).pass, c == 0);
                assertEq(pn.judges(pid)[5], address(0));
            }
        }
    }

    /// A majority revealed by judges too weak for the bounty doesn't decide: the missing level A judge is replaced (or,
    /// with nobody strong enough left, its seat waits), so the verdict never counts at a level that can't judge it.
    function test_aMissedRevealThatWouldWeakenThePanel() public {
        _deployVersion(3, true);
        usd.mint(address(race), 1_000e6);
        _add(keccak256("a2"), _family(1), SEV_SNP, 1, FULL_BOND);
        _add(keccak256("pc1"), _family(2), 0, 3, FULL_BOND);
        _add(keccak256("pc2"), _family(3), 0, 3, FULL_BOND);
        uint256 pid;
        address[] memory js;
        for (uint256 t; t < 40; ++t) {
            pid = _openAndDraw(_id(), 200e6); // level A's k = 3 limit is $250, level C's $50
            if (pid == 0) continue;
            js = pn.judges(pid);
            if (_countLevel(js, 3) == 1) break;
            pid = 0;
        }
        assertGt(pid, 0, "no A-A-C panel drawn");
        uint256 missing = 3;
        for (uint256 i; i < 3; ++i) {
            _seal(pid, js[i], true);
            if (missing == 3 && reg.validator(js[i]).level == 1) missing = i;
        }
        vm.warp(pn.panel(pid).sealBy + 1);
        for (uint256 i; i < 3; ++i) {
            if (i == missing) continue;
            _reveal(pid, js[i]);
            _receipt(pid, js[i]);
        }
        vm.warp(pn.panel(pid).revealBy + 1);
        vm.expectEmit(true, false, false, true);
        emit Panels.Stalled(pid, 1);
        pn.advance(pid);
        assertFalse(pn.panel(pid).counted);
        assertEq(pn.judges(pid)[missing], address(0));
    }

    /// Option 2 is for counted panels: a challenge panel's missed reveal is still replaced.
    function test_aChallengePanelsMissedRevealIsReplaced() public {
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 40e6);
        _judge(pid, _votes(1, 1));
        _network(5, 7, 3);
        race.challenge(id, challenger, keccak256("evidence"));
        _rollPast(pn.submission(id).challengeBlock);
        pn.drawChallenge(id);
        uint256 cp = pn.submission(id).challengePid;
        address[] memory cj = pn.judges(cp);
        assertEq(cj.length, 3);
        for (uint256 i; i < 3; ++i) {
            _seal(cp, cj[i], false);
        }
        vm.warp(pn.panel(cp).sealBy + 1);
        for (uint256 i; i < 2; ++i) {
            _reveal(cp, cj[i]);
            _receipt(cp, cj[i]);
        }
        vm.warp(pn.panel(cp).revealBy + 1);
        pn.advance(cp); // two of three agree, yet the seat is refilled
        assertFalse(pn.panel(cp).counted);
        assertTrue(pn.judges(cp)[2] != cj[2] && pn.judges(cp)[2] != address(0));
    }

    /// A level C pass counted without a missing seat's vote is treated as split, so it's always audited (D10).
    function test_aLevelCPassWithAMissedRevealIsAudited() public {
        _deployVersion(3, true);
        usd.mint(address(race), 1_000e6);
        for (uint256 i = 1; i <= 4; ++i) {
            _add(keccak256(abi.encode("pc", i)), _family(i), 0, 3, FULL_BOND);
        }
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 100e6);
        address[] memory js = pn.judges(pid);
        assertEq(js.length, 5);
        for (uint256 i; i < 5; ++i) {
            _seal(pid, js[i], true);
        }
        vm.warp(pn.panel(pid).sealBy + 1);
        for (uint256 i; i < 4; ++i) {
            _reveal(pid, js[i]);
            _receipt(pid, js[i]);
        }
        vm.warp(pn.panel(pid).revealBy + 1);
        pn.advance(pid);
        Submission memory s = pn.submission(id);
        assertTrue(pn.panel(pid).counted && s.pass);
        assertEq(s.level, 3);
        assertGe(s.auditsDue, 1);
    }

    // ---------- gas ----------

    /// The gas of task 3.4's calls, for reports/contract-v3.md (call frames, without the transaction's base cost).
    function test_gasLevels() public {
        _network(20, 7, 3);
        IValidators.Change[] memory cs = _one(IValidators.Op.RaiseFirmware, TDX, 1);
        (uint256 id, bytes32 text) = _judgedAdr(cs, Tier.Removal, 7);
        _runAudits(id, true);
        vm.warp(pn.submission(id).finalAt);
        pn.finalize(id);
        console.log("finalize (an ADR, with adrPassed)", vm.lastFrameGas().gasTotalUsed);
        reg.applyAdr(id, text, cs);
        console.log("applyAdr (one operation)", vm.lastFrameGas().gasTotalUsed);
        address[] memory tdx = _ofType(TDX);
        reg.recheck(tdx);
        console.log("recheck, per validator", vm.lastFrameGas().gasTotalUsed / tdx.length);
        _reattest(tdx[0], IMAGE, 1);
        console.log("reattest", vm.lastFrameGas().gasTotalUsed);
        IValidators.Change[] memory rm = _one(IValidators.Op.RemoveTeeType, NITRO, 0);
        (id, text) = _judgedAdr(rm, Tier.Removal, 7);
        _finalize(id);
        reg.applyAdr(id, text, rm);
        console.log("applyAdr (a TEE type removed)", vm.lastFrameGas().gasTotalUsed);
        // the draws on a fresh network of 40 (as test_gas's k = 7 row), ordinary and hidden-test
        _deployVersion(3, false);
        _network(39, 7, 3);
        uint256 nid = _id();
        _open(nid, 300e6);
        _rollPast(pn.submission(nid).seedBlock);
        pn.draw(nid);
        console.log("draw (k = 7, 40 eligible)", vm.lastFrameGas().gasTotalUsed);
        uint256 hid = _id();
        race.openHidden(hid, keccak256("h"), 300e6);
        _rollPast(pn.submission(hid).seedBlock);
        pn.draw(hid);
        console.log("draw (hidden tests, k = 7, 40 eligible)", vm.lastFrameGas().gasTotalUsed);
        uint256 pid = pn.submission(hid).pid;
        address[] memory js = pn.judges(pid);
        for (uint256 i; i < js.length; ++i) {
            _seal(pid, js[i], true);
        }
        vm.warp(pn.panel(pid).sealBy + 1);
        for (uint256 i; i < (js.length + 1) / 2; ++i) {
            _reveal(pid, js[i]);
            _receipt(pid, js[i]);
        }
        vm.warp(pn.panel(pid).revealBy + 1);
        pn.advance(pid);
        console.log("advance, a decided panel counted without its missing seats", vm.lastFrameGas().gasTotalUsed);
        assertTrue(pn.panel(pid).counted);
    }
}
