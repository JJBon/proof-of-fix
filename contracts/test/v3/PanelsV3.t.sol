// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {console} from "forge-std/Test.sol";
import {Vm} from "forge-std/Vm.sol";
import {Validators} from "../../src/v3/Validators.sol";
import {IValidators} from "../../src/v3/IValidators.sol";
import {Panels} from "../../src/v3/Panels.sol";
import {Status, Tier, Kind, Submission, Panel} from "../../src/v3/PanelsBase.sol";
import {IPanelsRegistry, IPanelScores} from "../../src/v3/IPanels.sol";
import {PanelScores} from "../../src/v3/PanelScores.sol";
import {PanelsSetup, MockRace, IBM_SE} from "./helpers/PanelsSetup.sol";
import {TDX, SEV_SNP, NITRO, SGX} from "./helpers/ValidatorsSetup.sol";

/// A registry whose TEE-type list is shortened directly (test-only; PanelsLevelsV3 removes types by ADR).
contract ValidatorsWithRemoval is Validators {
    constructor(Genesis memory g) Validators(g) {}

    function removeTeeType(bytes32 t) external {
        _delist(_tees[t]);
        --teeTypeCount;
        _group(t, false);
    }
}

/// proof-of-fix#138, task 3.2 of #132, milestone A: the draw, seals, reveals and receipts on-chain, replacement and
/// finality, against specs/judge-panels (and the validator-admission scenarios the draw decides). Each scenario is
/// tested by its spec name. Milestone B adds shadows, audits, scores, challenge panels and the constitution tier.
contract PanelsV3Test is PanelsSetup {
    uint256 internal nextId = 1;

    function setUp() public {
        _deployVersion(3, false);
    }

    function _id() internal returns (uint256) {
        return nextId++;
    }

    // ---------- The panel is the largest odd number the network allows ----------

    /// Scenario "One validator": the genesis validator alone judges, under k = 1's hold.
    function test_oneValidator() public {
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 40e6);
        assertEq(pn.submission(id).k, 1);
        assertEq(pn.judges(pid)[0], genesisKey);
        _judge(pid, _votes(1, 1));
        Submission memory s = pn.submission(id);
        assertTrue(s.pass);
        assertEq(uint256(s.status), uint256(Status.Held));
    }

    /// Scenario "Two validators": k is 1, never 2.
    function test_twoValidators() public {
        _network(1, 2, 2);
        for (uint256 i; i < 5; ++i) {
            uint256 id = _id();
            _openAndDraw(id, 40e6);
            assertEq(pn.submission(id).k, 1);
        }
    }

    /// Scenario "Six validators": k is 5, and 3 passing verdicts pass the fix (2 don't).
    function test_sixValidators() public {
        _network(5, 3, 3);
        uint256 a = _id();
        uint256 pa = _openAndDraw(a, 100e6);
        assertEq(pn.submission(a).k, 5);
        _judge(pa, _votes(5, 3));
        assertTrue(pn.submission(a).pass);
        assertEq(uint256(pn.submission(a).status), uint256(Status.Window));
        uint256 b = _id();
        uint256 pb = _openAndDraw(b, 100e6);
        assertEq(pn.submission(b).k, 5);
        _judge(pb, _votes(5, 2));
        assertFalse(pn.submission(b).pass);
    }

    /// Scenario "A large network": forty eligible, k is 7, 4 passing verdicts pass; no cap is broken.
    function test_aLargeNetwork() public {
        _network(39, 7, 3);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 300e6);
        assertEq(pn.submission(id).k, 7);
        _assertCaps(pid);
        _judge(pid, _votes(7, 4));
        assertTrue(pn.submission(id).pass);
        uint256 id2 = _id();
        _judge(_openAndDraw(id2, 300e6), _votes(7, 3));
        assertFalse(pn.submission(id2).pass);
    }

    // ---------- A bounty's size limits who may judge it ----------

    /// Scenario "A small bond, a small bounty": a $100 bond is eligible for $40, not for $400.
    function test_aSmallBondASmallBounty() public {
        _network(4, 3, 3);
        address small = _add(keccak256("small host"), _family(3), NITRO, 1, 100e6);
        assertEq(reg.eligibleCount(40e6), 6);
        assertEq(reg.eligibleCount(400e6), 5);
        for (uint256 i; i < 4; ++i) {
            uint256 id = _id();
            uint256 pid = _openAndDraw(id, 400e6);
            assertEq(pn.submission(id).k, 5);
            assertFalse(_contains(pn.judges(pid), small));
        }
    }

    /// Scenario "A bounty between two tiers": $60's tier is $125, so only bonds of $250 or more are eligible.
    function test_aBountyBetweenTwoTiers() public {
        assertEq(reg.tierStep(reg.tierOf(60e6)), 125e6);
        address under = _add(keccak256("h1"), _family(1), SEV_SNP, 1, 250e6 - 1);
        address atTier = _add(keccak256("h2"), _family(2), NITRO, 1, 250e6);
        assertEq(reg.eligibleCount(60e6), 2); // the genesis and `atTier`
        assertEq(reg.eligibleCount(50e6), 3);
        // a $60 bounty needs k = 3 (k = 1's limit is $50): it waits while two are eligible
        assertEq(_openAndDraw(_id(), 60e6), 0);
        _add(keccak256("h3"), _family(3), TDX, 1, 300e6);
        for (uint256 i; i < 3; ++i) {
            uint256 pid = _openAndDraw(_id(), 60e6);
            address[] memory js = pn.judges(pid);
            assertEq(js.length, 3);
            assertFalse(_contains(js, under));
            assertTrue(_contains(js, atTier) && _contains(js, genesisKey));
        }
    }

    /// Scenario "A big bounty on a small network": above k = 1's limit with one validator, it waits, nobody is drawn,
    /// and the solver may withdraw it.
    function test_aBigBountyOnASmallNetwork() public {
        uint256 id = _id();
        assertEq(_openAndDraw(id, 100e6), 0);
        Submission memory s = pn.submission(id);
        assertEq(uint256(s.status), uint256(Status.Waiting));
        assertEq(pn.panelCount(), 0);
        assertEq(reg.validator(genesisKey).openVerdicts, 0);
        race.withdraw(id);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Withdrawn));
        vm.expectRevert(Panels.WrongStatus.selector);
        pn.draw(id);
    }

    /// Scenario "The network grows": once enough validators are eligible, anyone draws the waiting submission with the
    /// k they now allow, from a fresh seed block.
    function test_theNetworkGrows() public {
        uint256 id = _id();
        _openAndDraw(id, 100e6);
        vm.expectRevert(Panels.NothingChanged.selector);
        pn.draw(id);
        _network(2, 3, 3);
        vm.prank(makeAddr("anyone"));
        pn.draw(id); // re-targets
        Submission memory s = pn.submission(id);
        assertEq(uint256(s.status), uint256(Status.Sealed));
        assertEq(s.seedBlock, vm.getBlockNumber() + 5);
        assertGt(_draw(id), 0);
        assertEq(pn.submission(id).k, 3);
    }

    // ---------- k is fixed at the draw and silent judges are replaced ----------

    /// Scenario "A judge goes silent to change the outcome": the next validator in the sample replaces it, k stays 3,
    /// and 2 passing verdicts are still needed. The silent judge loses $5 and counts a miss.
    function test_aJudgeGoesSilentToChangeTheOutcome() public {
        _network(3, 4, 3);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 100e6);
        address[] memory js = pn.judges(pid);
        assertEq(js.length, 3);
        _seal(pid, js[0], true);
        _seal(pid, js[1], false);
        address silent = js[2];
        uint256 bond = _bond(silent);
        vm.warp(pn.panel(pid).sealBy + 1);
        _revealReverts(pid, js[0], Panels.TooEarly.selector); // nobody reveals while a seat could still seal
        pn.advance(pid);
        assertEq(_bond(silent), bond - 5e6);
        assertEq(reg.progress(silent).misses, 1);
        address[] memory now_ = pn.judges(pid);
        assertTrue(now_[2] != silent && now_[2] != address(0));
        assertEq(pn.panel(pid).k, 3);
        assertEq(pn.submission(id).k, 3);
        _seal(pid, now_[2], true);
        vm.warp(pn.panel(pid).sealBy + 1);
        for (uint256 i; i < 3; ++i) {
            _reveal(pid, now_[i]);
            _receipt(pid, now_[i]);
        }
        assertTrue(pn.submission(id).pass); // 2 of 3
        assertEq(pn.panel(pid).passes, 2);
    }

    // ---------- The draw's seed is fixed after the submission and recomputable ----------

    /// Scenario "Grinding the seed": the seed comes from a block after the seal, each resubmission is a new draw, and
    /// the solver's own validator is recused as a party every time.
    function test_grindingTheSeed() public {
        address[] memory ks = _network(3, 4, 3);
        address solver = makeAddr("solver");
        address mine = ks[0];
        for (uint256 i; i < 6; ++i) {
            uint256 id = _id();
            race.setParty(id, solver, true);
            race.setParty(id, reg.validator(mine).operator, true); // the solver runs it
            _open(id, 100e6);
            assertEq(pn.submission(id).seedBlock, vm.getBlockNumber() + 5);
            vm.expectRevert(Panels.TooEarly.selector);
            pn.draw(id);
            uint256 pid = _draw(id);
            assertEq(pn.submission(id).k, 3);
            assertFalse(_contains(pn.judges(pid), mine));
        }
    }

    /// Scenario "The owner's validator and the owner's fix" (validator-admission): the owner's validator is skipped as
    /// a party, and the next eligible validator in the sample takes its place.
    function test_theOwnersValidatorAndTheOwnersFix() public {
        _network(2, 3, 3);
        uint256 id = _id();
        race.setParty(id, genesisKey, true); // the owner runs the genesis validator and solved the bounty
        _open(id, 40e6);
        (uint256 k,, address[] memory keys,) = pn.sample(id, bytes32(uint256(1)));
        assertEq(k, 1);
        assertTrue(keys[0] != genesisKey);
        uint256 pid = _draw(id);
        assertTrue(pn.judges(pid)[0] != genesisKey);
    }

    /// Scenario "Recomputing a panel": the view gives the recorded panel, from the recorded seed, at the recorded epoch.
    function test_recomputingAPanel() public {
        _network(12, 5, 3);
        for (uint256 i; i < 5; ++i) {
            uint256 id = _id();
            _open(id, 300e6);
            uint256 sb = pn.submission(id).seedBlock;
            vm.roll(sb + 1);
            vm.setBlockhash(sb, keccak256(abi.encode("block", sb)));
            bytes32 seed = _seedFor(id);
            (uint256 k, uint8 level, address[] memory keys, uint256 counter) = pn.sample(id, seed);
            pn.draw(id);
            Submission memory s = pn.submission(id);
            Panel memory p = pn.panel(s.pid);
            assertEq(p.seed, seed);
            assertEq(p.k, k);
            assertEq(p.counter, counter);
            assertEq(p.snap.blockNo, sb - 5); // the snapshot, fixed at the opening
            assertEq(p.snap.nLive, reg.eligibleCount(300e6));
            assertEq(level, 1);
            address[] memory js = pn.judges(s.pid);
            assertEq(js.length, keys.length);
            for (uint256 j; j < js.length; ++j) {
                assertEq(js[j], keys[j]);
            }
            // anyone recomputing it later at the same registry state gets the same validators in the same order
            (, , address[] memory again,) = pn.sample(id, seed);
            for (uint256 j; j < js.length; ++j) {
                assertEq(again[j], js[j]);
            }
        }
    }

    /// D3: a draw more than 256 blocks after the seed block re-targets to the current block + SEED_DELAY.
    function test_theSeedReTargetsAfter256Blocks() public {
        uint256 id = _id();
        _open(id, 40e6);
        uint256 sb = pn.submission(id).seedBlock;
        vm.roll(sb + 257);
        vm.expectEmit(true, false, false, true);
        emit Panels.Retargeted(id, vm.getBlockNumber() + 5);
        pn.draw(id);
        assertEq(pn.submission(id).seedBlock, vm.getBlockNumber() + 5);
        assertEq(pn.panelCount(), 0);
        assertGt(_draw(id), 0);
    }

    // ---------- A panel too weak for its bounty waits ----------

    /// Scenario "A level C majority on a large bounty": a $200 bounty draws a panel of 3 whose level is C (limit $50):
    /// nobody is seated, it waits, and it's drawn again with a new seed after the next registry change.
    function test_aLevelCMajorityOnALargeBounty() public {
        _deployVersion(3, true);
        for (uint256 i = 1; i <= 3; ++i) {
            _add(keccak256(abi.encode("pc", i)), _family(i), 0, 3, FULL_BOND);
        }
        uint256 id = _id();
        _open(id, 200e6);
        uint256 sb = pn.submission(id).seedBlock;
        vm.roll(sb + 1);
        vm.setBlockhash(sb, keccak256(abi.encode("block", sb)));
        vm.expectEmit(true, false, false, true);
        emit Panels.Waited(id, 3, 3);
        pn.draw(id);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Waiting));
        assertEq(pn.panelCount(), 0);
        _add(keccak256("pc4"), _family(4), 0, 3, FULL_BOND);
        pn.draw(id);
        assertEq(pn.submission(id).seedBlock, vm.getBlockNumber() + 5); // a fresh seed block
    }

    // ---------- A counted verdict carries proof that the check ran ----------

    /// Scenario "A verdict with no receipt": it doesn't count; the judge is treated as having sealed and not revealed
    /// ($5, a miss) and, since the revealed votes are split (no majority yet), the next validator replaces it.
    function test_aVerdictWithNoReceipt() public {
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
        _reveal(pid, js[2]); // no receipt
        assertEq(pn.panel(pid).done, 2);
        assertFalse(pn.panel(pid).counted);
        uint256 bond = _bond(js[2]);
        vm.warp(pn.panel(pid).revealBy + 1);
        vm.expectEmit(true, true, false, true);
        emit Panels.Missed(pid, js[2], true);
        pn.advance(pid);
        assertEq(_bond(js[2]), bond - 5e6);
        assertEq(reg.validator(js[2]).openVerdicts, 0);
        address repl = pn.judges(pid)[2];
        assertTrue(repl != js[2] && repl != address(0));
        _seal(pid, repl, false);
        vm.warp(pn.panel(pid).sealBy + 1);
        _reveal(pid, repl);
        _receipt(pid, repl);
        assertTrue(pn.panel(pid).counted);
        assertEq(pn.panel(pid).passes, 1);
    }

    /// Scenario "A sealed vote not revealed" (validator-admission): $5, a miss, and, with the revealed votes split,
    /// replaced (PanelsLevelsV3 tests the case where the revealed votes already decide).
    function test_aSealedVoteNotRevealed() public {
        _network(3, 4, 3);
        uint256 pid = _openAndDraw(_id(), 100e6);
        address[] memory js = pn.judges(pid);
        _seal(pid, js[0], true);
        _seal(pid, js[1], false);
        _seal(pid, js[2], true);
        vm.warp(pn.panel(pid).sealBy + 1);
        _reveal(pid, js[0]);
        _receipt(pid, js[0]);
        _reveal(pid, js[1]);
        _receipt(pid, js[1]);
        uint256 bond = _bond(js[2]);
        vm.warp(pn.panel(pid).revealBy + 1);
        pn.advance(pid);
        assertEq(_bond(js[2]), bond - 5e6);
        assertEq(reg.progress(js[2]).misses, 1);
        assertTrue(pn.judges(pid)[2] != js[2] && pn.judges(pid)[2] != address(0));
    }

    /// Scenarios "An honest outage" and "Bonds of different sizes" (validator-admission): a $100 and a $1,250 bond each
    /// lose the same $5 for silence; with nobody left to draw, the seats wait.
    function test_bondsOfDifferentSizesLoseTheSameForSilence() public {
        _network(3, 3, 3);
        address small = _add(keccak256("small"), _family(4), NITRO, 1, 100e6);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 40e6);
        address[] memory js = pn.judges(pid);
        assertEq(js.length, 5);
        assertTrue(_contains(js, small) && _contains(js, genesisKey));
        vm.warp(pn.panel(pid).sealBy + 1);
        vm.expectEmit(true, false, false, true);
        emit Panels.Stalled(pid, 5);
        pn.advance(pid);
        assertEq(_bond(small), 95e6);
        assertEq(_bond(genesisKey), FULL_BOND - 5e6);
        assertEq(pn.panel(pid).seats, 0);
        assertEq(pn.panel(pid).k, 5);
        vm.expectRevert(Panels.NotReady.selector); // the sample yields nobody: everyone eligible already sat
        pn.refill(pid);
    }

    // ---------- seals, reveals and receipts: early, mismatched, replayed, late ----------

    function test_anEarlyRevealIsRefused() public {
        _network(2, 3, 3);
        uint256 pid = _openAndDraw(_id(), 100e6);
        address[] memory js = pn.judges(pid);
        for (uint256 i; i < 3; ++i) {
            _seal(pid, js[i], true);
        }
        _revealReverts(pid, js[0], Panels.TooEarly.selector); // the seal window is still open
        _receiptReverts(pid, js[0], Panels.TooEarly.selector);
        vm.warp(pn.panel(pid).sealBy);
        _revealReverts(pid, js[0], Panels.TooEarly.selector); // its last second
        vm.warp(pn.panel(pid).sealBy + 1);
        _reveal(pid, js[0]);
    }

    /// A reveal that doesn't match its seal: the whole bond (Fault.Mismatch), the seat replaced, the call succeeds.
    function test_aMismatchedRevealIsAFault() public {
        _network(3, 4, 3);
        uint256 pid = _openAndDraw(_id(), 100e6);
        address[] memory js = pn.judges(pid);
        for (uint256 i; i < 3; ++i) {
            _seal(pid, js[i], true);
        }
        vm.warp(pn.panel(pid).sealBy + 1);
        address liar = js[1];
        bytes32 salt = _salt(pid, liar);
        bytes memory sig = _stmt(liar, pn.REVEAL_TAG(), pid, keccak256(abi.encode(false, uint8(0), salt)));
        vm.expectEmit(true, true, false, false);
        emit Panels.Mismatch(pid, liar);
        pn.reveal(pid, liar, false, 0, salt, sig); // sealed true, reveals false
        assertEq(_bond(liar), 0);
        assertEq(reg.validator(liar).slashed, FULL_BOND);
        address repl = pn.judges(pid)[1];
        assertTrue(repl != liar && repl != address(0));
        sig = _stmt(liar, pn.REVEAL_TAG(), pid, keccak256(abi.encode(true, uint8(0), salt)));
        vm.expectRevert(Panels.NotSeated.selector);
        pn.reveal(pid, liar, true, 0, salt, sig);
    }

    /// A replayed reveal: the same reveal twice, a reveal signed for another panel, and one signed by another key.
    function test_aReplayedRevealIsRefused() public {
        _network(4, 5, 3);
        uint256 p1 = _openAndDraw(_id(), 100e6);
        uint256 p2 = _openAndDraw(_id(), 100e6);
        address[] memory js = pn.judges(p1);
        for (uint256 i; i < js.length; ++i) {
            _seal(p1, js[i], true);
        }
        vm.warp(pn.panel(p1).sealBy + 1);
        _reveal(p1, js[0]);
        _revealReverts(p1, js[0], Panels.AlreadyRevealed.selector);
        // a reveal signed for panel p2 (its subject differs) doesn't verify on p1
        bytes32 salt = _salt(p1, js[1]);
        bytes memory other = _stmt(js[1], pn.REVEAL_TAG(), p2, keccak256(abi.encode(true, uint8(0), salt)));
        vm.expectRevert(Panels.BadSignature.selector);
        pn.reveal(p1, js[1], true, 0, salt, other);
        // a seal's signature isn't a reveal's
        bytes memory sealSig = _stmt(js[1], pn.SEAL_TAG(), p1, keccak256(abi.encode(true, uint8(0), salt)));
        vm.expectRevert(Panels.BadSignature.selector);
        pn.reveal(p1, js[1], true, 0, salt, sealSig);
        // another judge's signature
        bytes memory byOther = _stmt(js[2], pn.REVEAL_TAG(), p1, keccak256(abi.encode(true, uint8(0), salt)));
        vm.expectRevert(Panels.BadSignature.selector);
        pn.reveal(p1, js[1], true, 0, salt, byOther);
        // a second receipt, and a second seal
        _receipt(p1, js[0]);
        _receiptReverts(p1, js[0], Panels.AlreadyReceipted.selector);
        bytes32 c = pn.commitmentOf(p1, js[1], false, 0, salt);
        bytes memory s2 = _stmt(js[1], pn.SEAL_TAG(), p1, c);
        vm.expectRevert(Panels.AlreadySealed.selector);
        pn.seal(p1, js[1], c, s2);
        // a validator not seated can't post anything
        address outsider = makeAddr("outsider");
        vm.expectRevert(Panels.NotSeated.selector);
        pn.seal(p1, outsider, c, s2);
    }

    /// The missed deadlines: a late seal, a late reveal and a late receipt are refused, and count as misses.
    function test_aMissedDeadlineIsSilence() public {
        _network(3, 4, 3);
        uint256 pid = _openAndDraw(_id(), 100e6);
        address[] memory js = pn.judges(pid);
        _seal(pid, js[0], true);
        _seal(pid, js[1], true);
        vm.warp(pn.panel(pid).sealBy + 1);
        bytes32 c = pn.commitmentOf(pid, js[2], true, 0, _salt(pid, js[2]));
        bytes memory sig = _stmt(js[2], pn.SEAL_TAG(), pid, c);
        vm.expectRevert(Panels.TooLate.selector);
        pn.seal(pid, js[2], c, sig);
        pn.advance(pid); // the silent seat is replaced
        vm.expectRevert(Panels.NothingDue.selector); // and nothing else is due until the new seal window ends
        pn.advance(pid);
        address repl = pn.judges(pid)[2];
        _seal(pid, repl, true);
        vm.warp(pn.panel(pid).revealBy + 1);
        _revealReverts(pid, js[0], Panels.TooLate.selector);
        _receiptReverts(pid, js[0], Panels.TooLate.selector);
        pn.advance(pid);
        // all three missed their reveal: each lost $5; every eligible validator has sat, so the seats wait
        assertEq(pn.panel(pid).seats, 0);
        assertEq(reg.progress(js[0]).misses, 1);
        assertEq(reg.progress(repl).misses, 1);
    }

    // ---------- A panel's proof level is its majority's weakest ----------

    /// Scenario "A mixed panel of 3": A, B and C judges make a level B panel (with level B's window).
    function test_aMixedPanelOf3() public {
        _deployVersion(3, true);
        _add(keccak256("b host"), _family(1), SEV_SNP, 2, FULL_BOND);
        _add(keccak256("c host"), _family(2), 0, 3, FULL_BOND);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 100e6);
        assertEq(pn.submission(id).k, 3);
        _judge(pid, _votes(3, 3));
        assertEq(pn.submission(id).level, 2);
        assertEq(pn.submission(id).finalAt, vm.getBlockTimestamp() + 48 hours);
    }

    /// Scenarios "A network of ordinary PCs" and "A level C panel": panels still form at level C, with level C's
    /// limits, and become final only after level C's longer window for k = 3 (72 h).
    function test_aNetworkOfOrdinaryPCs() public {
        _deployVersion(3, true);
        for (uint256 i = 1; i <= 3; ++i) {
            _add(keccak256(abi.encode("pc", i)), _family(i), 0, 3, FULL_BOND);
        }
        vm.prank(genesisKey);
        reg.leave(genesisKey);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 50e6);
        assertEq(pn.submission(id).k, 3);
        // a split level C pass is always audited (D10): a fourth PC, outside the panel, audits it
        _add(keccak256("pc auditor"), _family(4), 0, 3, FULL_BOND);
        _judge(pid, _votes(3, 2));
        assertEq(pn.submission(id).auditsDue, 1);
        Submission memory s = pn.submission(id);
        assertEq(s.level, 3);
        assertEq(s.finalAt, vm.getBlockTimestamp() + 72 hours);
        vm.warp(s.finalAt - 1);
        vm.expectRevert(Panels.TooEarly.selector);
        pn.finalize(id);
        _finalize(id);
        // above level C's k = 3 limit, the same network voids the draw
        uint256 big = _id();
        assertEq(_openAndDraw(big, 51e6), 0);
    }

    // ---------- Weaker panels wait longer; a lone judge's verdict is held ----------

    /// Scenario "A large panel's quick finality": a k = 7 level A pass is final after 6 hours, and its judges'
    /// verdicts close in the registry.
    function test_aLargePanelsQuickFinality() public {
        _network(39, 7, 3);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 300e6);
        address[] memory js = pn.judges(pid);
        for (uint256 i; i < 7; ++i) {
            assertEq(reg.validator(js[i]).openVerdicts, 1);
        }
        _judge(pid, _votes(7, 7));
        Submission memory s = pn.submission(id);
        assertEq(s.finalAt, vm.getBlockTimestamp() + 6 hours);
        _finalize(id);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Final));
        for (uint256 i; i < 7; ++i) {
            assertEq(reg.validator(js[i]).openVerdicts, 0);
        }
    }

    /// Scenario "The genesis validator's first verdicts": held, unpaid, until three other validators eligible for its
    /// challenge are active; only then does its 7-day window start.
    function test_theGenesisValidatorsFirstVerdicts() public {
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 40e6);
        _judge(pid, _votes(1, 1));
        assertEq(uint256(pn.submission(id).status), uint256(Status.Held));
        vm.expectRevert(Panels.NotReady.selector);
        pn.startWindow(id);
        _network(2, 3, 3);
        vm.expectRevert(Panels.NotReady.selector);
        pn.startWindow(id);
        address third = _addSpread(3, 3, 3);
        race.setParty(id, reg.validator(third).operator, true); // a party isn't a challenger
        vm.expectRevert(Panels.NotReady.selector);
        pn.startWindow(id);
        _addSpread(4, 3, 3);
        pn.startWindow(id);
        Submission memory s = pn.submission(id);
        assertEq(uint256(s.status), uint256(Status.Window));
        assertEq(s.finalAt, vm.getBlockTimestamp() + 168 hours);
        assertEq(pn.k1Pending(genesisKey), 1);
        assertEq(_runAudits(id, true), 2); // both audits, by validators outside the panel
        vm.warp(s.finalAt);
        pn.finalize(id);
        assertEq(pn.k1Pending(genesisKey), 0);
        assertEq(reg.validator(genesisKey).openVerdicts, 0);
    }

    /// Scenario "The network already has challengers": a k = 1 verdict (k stepped down by the host cap) given while
    /// three other validators are eligible for its challenge starts its window at once.
    function test_theNetworkAlreadyHasChallengers() public {
        bytes32 host = keccak256("host-genesis");
        for (uint256 i = 1; i <= 3; ++i) {
            _add(host, _family(i), _tee(i % 3), 1, FULL_BOND); // one host: no panel of 3
        }
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 40e6);
        assertEq(pn.submission(id).k, 1);
        _judge(pid, _votes(1, 0));
        Submission memory s = pn.submission(id);
        assertEq(uint256(s.status), uint256(Status.Window));
        assertEq(s.finalAt, vm.getBlockTimestamp() + 168 hours);
    }

    // ---------- A validator's pending lone verdicts are capped ----------

    /// Scenario "A lone validator at the cap": with 10 held k = 1 verdicts, the genesis validator isn't drawn at
    /// k = 1, and the submission waits.
    function test_aLoneValidatorAtTheCap() public {
        for (uint256 i; i < 10; ++i) {
            _judge(_openAndDraw(_id(), 40e6), _votes(1, 1));
        }
        assertEq(pn.k1Pending(genesisKey), 10);
        uint256 id = _id();
        assertEq(_openAndDraw(id, 40e6), 0);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Waiting));
        assertEq(reg.validator(genesisKey).openVerdicts, 10);
    }

    // ---------- the caps (validator-admission) ----------

    /// Scenario "Ten nodes on one cloud": the panel holds no more of one host than the host cap allows.
    function test_tenNodesOnOneCloud() public {
        bytes32 cloud = keccak256("one cloud");
        for (uint256 i; i < 10; ++i) {
            _add(cloud, _family(i % 7), _tee(i % 3), 1, FULL_BOND);
        }
        _network(4, 7, 3);
        for (uint256 r; r < 4; ++r) {
            uint256 id = _id();
            uint256 pid = _openAndDraw(id, 300e6);
            uint256 k = pn.submission(id).k;
            assertGe(k, 5);
            address[] memory js = pn.judges(pid);
            uint256 onCloud;
            for (uint256 i; i < js.length; ++i) {
                if (reg.validator(js[i]).host == cloud) ++onCloud;
            }
            assertLe(onCloud, (k - 1) / 2);
            _assertCaps(pid);
        }
    }

    /// Scenario "Too few distinct hosts": k follows the validators the caps leave, not the active count.
    function test_tooFewDistinctHosts() public {
        bytes32 h = keccak256("host-genesis");
        bytes32 h2 = keccak256("second host");
        _add(h, _family(1), SEV_SNP, 1, FULL_BOND);
        _add(h2, _family(2), NITRO, 1, FULL_BOND);
        _add(h2, _family(3), TDX, 1, FULL_BOND);
        _add(h, _family(4), SEV_SNP, 1, FULL_BOND);
        assertEq(reg.eligibleCount(40e6), 5);
        uint256 id = _id();
        _openAndDraw(id, 40e6);
        assertEq(pn.submission(id).k, 1); // two hosts: no panel of 5 (2 each) nor of 3 (1 each)
        _add(keccak256("third host"), _family(5), NITRO, 1, FULL_BOND);
        uint256 id2 = _id();
        _openAndDraw(id2, 40e6);
        assertEq(pn.submission(id2).k, 5);
    }

    /// Scenario "Two of one TEE type in a panel of 3": with three accepted types the TEE cap starts at k = 5.
    function test_twoOfOneTeeTypeInAPanelOf3() public {
        assertEq(pn.teeCapFrom(), 5);
        _add(keccak256("h1"), _family(1), TDX, 1, FULL_BOND);
        _add(keccak256("h2"), _family(2), TDX, 1, FULL_BOND);
        uint256 id = _id();
        _openAndDraw(id, 100e6);
        assertEq(pn.submission(id).k, 3); // three TDX judges
        // five TDX validators can't make a panel of 5 (2 per type at k = 5): it steps down to 3
        _add(keccak256("h3"), _family(3), TDX, 1, FULL_BOND);
        _add(keccak256("h4"), _family(4), TDX, 1, FULL_BOND);
        uint256 id2 = _id();
        _openAndDraw(id2, 100e6);
        assertEq(pn.submission(id2).k, 3);
        _add(keccak256("h5"), _family(5), SEV_SNP, 1, FULL_BOND);
        _add(keccak256("h6"), _family(6), SEV_SNP, 1, FULL_BOND);
        _add(keccak256("h7"), _family(1), NITRO, 1, FULL_BOND);
        uint256 id3 = _id();
        uint256 p3 = _openAndDraw(id3, 100e6);
        assertEq(pn.submission(id3).k, 5);
        _assertCaps(p3);
    }

    /// Scenarios "Five TEE types accepted" and "One vendor's two types on a panel of three": the TEE cap applies from
    /// k = 3, and SGX and TDX are two types.
    function test_fiveTeeTypesAccepted() public {
        _deployVersion(5, false);
        assertEq(pn.teeCapFrom(), 3);
        _add(keccak256("h1"), _family(1), TDX, 1, FULL_BOND);
        _add(keccak256("h2"), _family(2), TDX, 1, FULL_BOND);
        _add(keccak256("h3"), _family(3), SGX, 1, FULL_BOND);
        _add(keccak256("h4"), _family(4), SEV_SNP, 1, FULL_BOND);
        for (uint256 r; r < 5; ++r) {
            uint256 id = _id();
            uint256 pid = _openAndDraw(id, 100e6);
            assertEq(pn.submission(id).k, 3);
            address[] memory js = pn.judges(pid);
            uint256 tdx;
            for (uint256 i; i < 3; ++i) {
                if (reg.validator(js[i]).teeType == TDX) ++tdx;
            }
            assertLe(tdx, 1);
        }
    }

    /// Scenario "A type is removed": from the next draw the TEE cap applies only from k = 5.
    function test_aTypeIsRemoved() public {
        _deployCoinAndPool();
        address g0 = _newKey("genesis2");
        IValidators.Registration[] memory gs = new IValidators.Registration[](1);
        gs[0] = _reg(g0, makeAddr("genesis operator 2"), keccak256("hg"), _family(0));
        Validators.Genesis memory g = _genesis(false, gs, FULL_BOND);
        g.teeTypes = new bytes32[](5);
        for (uint256 i; i < 5; ++i) {
            g.teeTypes[i] = _tee(i);
        }
        vm.prank(deployer);
        ValidatorsWithRemoval r = new ValidatorsWithRemoval(g);
        Panels p = new Panels(IPanelsRegistry(address(r)), pn.fees(), IPanelScores(address(new PanelScores())), g.teeTypes);
        assertEq(p.teeCapFrom(), 3);
        r.removeTeeType(IBM_SE);
        assertEq(p.teeCapFrom(), 5);
    }

    // ---------- open families (D19) ----------

    /// A validator of a family FeesV3 hasn't priced isn't drawn, and the draw announces its family.
    function test_anUnpricedFamilyIsntDrawn() public {
        bytes32 fresh = keccak256("newlab/model");
        address a = _add(keccak256("h1"), fresh, SEV_SNP, 1, FULL_BOND);
        _add(keccak256("h2"), _family(2), NITRO, 1, FULL_BOND);
        assertFalse(fees.isPriced(fresh));
        bool announced;
        for (uint256 r; r < 4; ++r) {
            uint256 id = _id();
            uint256 pid = _openAndDraw(id, 40e6);
            if (pid != 0) assertFalse(_contains(pn.judges(pid), a));
            bytes32[] memory pending = fees.pendingFamilies();
            for (uint256 i; i < pending.length; ++i) {
                if (pending[i] == fresh) announced = true;
            }
        }
        // three validators, one unpriced: never a panel of 3
        assertTrue(announced);
    }

    // ---------- k: odd, at most K_MAX, never changed after the draw ----------

    /// Fuzz: whatever the network (size, hosts, families, TEE types, bonds) and the seed, k is odd, at most K_MAX, at
    /// most the eligible count, within its limit, and doesn't change through the replacement of silent judges.
    function testFuzz_kIsOddBoundedAndFixed(uint8 n, uint8 hosts, uint8 families, uint256 bounty, bytes32 hash)
        public
    {
        n = uint8(bound(n, 0, 11));
        hosts = uint8(bound(hosts, 1, 6));
        families = uint8(bound(families, 1, 5));
        bounty = bound(bounty, 1, 625e6);
        for (uint256 i; i < n; ++i) {
            _add(
                keccak256(abi.encode("h", i % hosts)), _family(i % families), _tee(i % 3), 1, i % 4 == 0 ? 100e6 : FULL_BOND
            );
        }
        uint256 id = _id();
        _open(id, bounty);
        uint256 sb = pn.submission(id).seedBlock;
        vm.roll(sb + 1);
        vm.setBlockhash(sb, hash);
        pn.draw(id);
        Submission memory s = pn.submission(id);
        if (s.status != Status.Judging) {
            assertEq(s.k, 0);
            return;
        }
        uint256 k = s.k;
        assertEq(k % 2, 1);
        assertLe(k, 7);
        assertLe(k, reg.eligibleCount(bounty));
        assertLe(bounty, pn.limitOf(k, s.level));
        _assertCaps(s.pid);
        // every judge silent, twice: the seats are replaced (or wait), k never moves
        for (uint256 r; r < 2; ++r) {
            vm.warp(pn.panel(s.pid).sealBy + 1);
            if (pn.panel(s.pid).seats == 0) break;
            pn.advance(s.pid);
            assertEq(pn.panel(s.pid).k, k);
            assertEq(pn.submission(id).k, k);
        }
    }

    // ---------- wiring, keys and the registry's side ----------

    function test_theRaceAndTheRegistryAreBoundOnce() public {
        vm.expectRevert(Panels.AlreadyBound.selector);
        pn.bind();
        vm.expectRevert(Validators.AlreadyBound.selector);
        reg.bind();
        assertEq(reg.panels(), address(pn));
        vm.expectRevert(Panels.NotRace.selector);
        pn.open(99, bytes32(0), 1e6);
        vm.expectRevert(Panels.NotRace.selector);
        pn.withdraw(99);
        vm.expectRevert(Panels.BadBounty.selector);
        race.open(99, bytes32(0), 625e6 + 1);
        vm.expectRevert(Panels.BadBounty.selector);
        race.open(99, bytes32(0), 0);
    }

    /// No owner, admin or setter: every external function of the compiled ABI is a constant, a view, the race's two
    /// calls, the binding, or an action anyone takes under the rules; none takes a parameter's value.
    function test_noFunctionChangesAParameter() public view {
        string memory json = vm.readFile("out/Panels.sol/Panels.json");
        string[] memory allowed = vm.split(
            string.concat(
                // the race (bound once by itself): open, withdraw and challenge a submission
                "bind,open,openHidden,openConstitution,withdraw,challenge,",
                // anyone, under the rules: the draws, the judges' signed statements, deadlines, shadows, finality
                "draw,drawAudits,drawChallenge,seal,reveal,receipt,advance,refill,settleShadows,startWindow,finalize,",
                // views
                "sample,submission,panel,seat,judges,seedOf,commitmentOf,subjectOf,statementDigest,limitOf,windowOf,",
                "challengeK,teeCapFrom,validators,fees,scores,coin,pool,race,panelCount,k1Pending,",
                // the parameters: constants
                "K_MAX,DRAW_TRIES,SEED_DELAY,SEAL_WINDOW,REVEAL_WINDOW,K1_PENDING_MAX,TEE_CAP_K3_TYPES,BOUNTY_MAX,",
                "SHADOW_PER_DRAW,SHADOW_PER_DRAW_SMALL,SHADOW_PER_WAITING,AUDIT_RATE_BPS,K1_AUDITS,CONSTITUTION_QUORUM,",
                "CONSTITUTION_MIN_ELIGIBLE,REMOVAL_MIN_ELIGIBLE,ADR_DEPOSIT,ADR_WINDOW,REMOVAL_WINDOW,",
                "SEAL_TAG,REVEAL_TAG,RECEIPT_TAG"
            ),
            ","
        );
        uint256 n;
        for (uint256 i;; ++i) {
            string memory key = string.concat(".abi[", vm.toString(i), "]");
            if (!vm.keyExistsJson(json, key)) break;
            if (keccak256(bytes(vm.parseJsonString(json, string.concat(key, ".type")))) != keccak256("function")) {
                continue;
            }
            string memory name = vm.parseJsonString(json, string.concat(key, ".name"));
            bool ok;
            for (uint256 j; j < allowed.length && !ok; ++j) {
                ok = keccak256(bytes(name)) == keccak256(bytes(allowed[j]));
            }
            assertTrue(ok, string.concat("unexpected external function: ", name));
            ++n;
        }
        assertEq(n, allowed.length);
    }

    /// Panels' statements are the registry's: a judge that signs two seals for one panel is provably equivocating.
    function test_twoSealsForOnePanelAreEquivocation() public {
        uint256 pid = _openAndDraw(_id(), 40e6);
        bytes32 subject = pn.subjectOf(pn.SEAL_TAG(), pid, genesisKey);
        bytes32 a = pn.commitmentOf(pid, genesisKey, true, 0, bytes32("x"));
        bytes32 b = pn.commitmentOf(pid, genesisKey, false, 0, bytes32("x"));
        assertEq(pn.statementDigest(subject, a), reg.statementDigest(subject, a));
        bytes memory sa = _stmt(genesisKey, pn.SEAL_TAG(), pid, a);
        pn.seal(pid, genesisKey, a, sa);
        reg.proveEquivocation(genesisKey, subject, a, sa, b, _stmt(genesisKey, pn.SEAL_TAG(), pid, b));
        assertEq(_bond(genesisKey), 0);
    }

    /// Validators.familyOf (for FeesV3): candidates included, 0 for a key never registered.
    function test_familyOf() public {
        address c = _addCandidate(keccak256("h"), _family(3), SEV_SNP, 1, 100e6);
        assertEq(reg.familyOf(c), _family(3));
        assertEq(reg.familyOf(genesisKey), _family(0));
        assertEq(reg.familyOf(makeAddr("nobody")), bytes32(0));
    }

    /// Gas (call frames: without the transaction's 21,000 base and calldata) for reports/contract-v3.md: the draw at
    /// each k, one judge's seal, reveal and receipt, the receipt that counts the panel, a replacement and finality.
    function test_gas() public {
        uint8[4] memory others = [0, 3, 5, 39];
        uint256[4] memory bounty = [uint256(40e6), 100e6, 300e6, 300e6];
        for (uint256 r; r < 4; ++r) {
            _deployVersion(3, false);
            _network(others[r], 7, 3);
            uint256 id = _id();
            _open(id, bounty[r]);
            uint256 sb = pn.submission(id).seedBlock;
            vm.roll(sb + 1);
            vm.setBlockhash(sb, keccak256(abi.encode("block", sb)));
            pn.draw(id);
            uint256 drawGas = vm.lastFrameGas().gasTotalUsed;
            uint256 pid = pn.submission(id).pid;
            address[] memory js = pn.judges(pid);
            uint256 k = js.length;
            console.log("k", k, "eligible", reg.eligibleCount(bounty[r]));
            console.log("  draw", drawGas);
            uint256 sealGas;
            uint256 revealGas;
            uint256 receiptGas;
            for (uint256 i; i < k; ++i) {
                _seal(pid, js[i], true);
                sealGas += vm.lastFrameGas().gasTotalUsed;
            }
            vm.warp(pn.panel(pid).sealBy + 1);
            for (uint256 i; i < k; ++i) {
                _reveal(pid, js[i]);
                revealGas += vm.lastFrameGas().gasTotalUsed;
                _receipt(pid, js[i]);
                if (i + 1 < k) receiptGas += vm.lastFrameGas().gasTotalUsed;
            }
            console.log("  receipt that counts the panel", vm.lastFrameGas().gasTotalUsed);
            console.log("  seal (mean)", sealGas / k);
            console.log("  reveal (mean)", revealGas / k);
            if (k > 1) console.log("  receipt (mean, before the last)", receiptGas / (k - 1));
            if (k == 7) {
                _runAudits(id, true);
                if (vm.getBlockTimestamp() < pn.submission(id).finalAt) vm.warp(pn.submission(id).finalAt);
                pn.finalize(id);
                console.log("  finalize", vm.lastFrameGas().gasTotalUsed);
                // a replacement: one silent judge on a fresh panel
                uint256 id2 = _id();
                uint256 p2 = _openAndDraw(id2, 300e6);
                address[] memory j2 = pn.judges(p2);
                for (uint256 i = 1; i < 7; ++i) {
                    _seal(p2, j2[i], true);
                }
                vm.warp(pn.panel(p2).sealBy + 1);
                pn.advance(p2);
                console.log("  advance (one silent seat replaced)", vm.lastFrameGas().gasTotalUsed);
                // an audit decision and a challenge panel of 7 on a fresh verdict
                uint256 id3 = _id();
                _judge(_openAndDraw(id3, 300e6), _votes(7, 7));
                _rollPast(pn.submission(id3).auditBlock);
                pn.drawAudits(id3);
                console.log("  drawAudits (the decision, and an auditor if due)", vm.lastFrameGas().gasTotalUsed);
                race.challenge(id3, makeAddr("challenger"), bytes32(0));
                console.log("  challenge (opened by the race)", vm.lastFrameGas().gasTotalUsed);
                _rollPast(pn.submission(id3).challengeBlock);
                pn.drawChallenge(id3);
                console.log("  drawChallenge (k = 7, fresh)", vm.lastFrameGas().gasTotalUsed);
            }
        }
    }

    // ---------- helpers ----------

    /// No two judges share an operator; at most (k − 1) / 2 share a host or a family (from k = 3), or a TEE type
    /// (from teeCapFrom).
    function _assertCaps(uint256 pid) internal view {
        address[] memory js = pn.judges(pid);
        uint256 k = js.length;
        uint256 cap = (k - 1) / 2;
        for (uint256 i; i < k; ++i) {
            IValidators.Validator memory a = reg.validator(js[i]);
            uint256 hosts;
            uint256 fams;
            uint256 tees;
            for (uint256 j; j < k; ++j) {
                if (i == j) continue;
                IValidators.Validator memory b = reg.validator(js[j]);
                assertTrue(a.operator != b.operator);
                if (a.host == b.host) ++hosts;
                if (a.family == b.family) ++fams;
                if (a.teeType != 0 && a.teeType == b.teeType) ++tees;
            }
            if (k >= 3) {
                assertLe(hosts + 1, cap);
                assertLe(fams + 1, cap);
            }
            if (k >= pn.teeCapFrom() && a.teeType != 0) assertLe(tees + 1, cap);
        }
    }
}
