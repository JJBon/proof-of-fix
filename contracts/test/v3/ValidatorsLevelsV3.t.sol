// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {Validators} from "../../src/v3/Validators.sol";
import {IValidators} from "../../src/v3/IValidators.sol";
import {
    ValidatorsSetup,
    PanelsHarness,
    TDX,
    SEV_SNP,
    NITRO,
    SGX,
    IMAGE,
    OTHER_IMAGE,
    FAMILY_A,
    FAMILY_B
} from "./helpers/ValidatorsSetup.sol";

/// proof-of-fix#138, task 3.4 of #132 (design D6, D10, D11, D18): the constitution's lists on the registry's side.
/// An ADR's operations take effect only once Panels reports it passed and final (`adrPassed`, stood in for here by the
/// harness; PanelsLevelsV3 runs the whole path through the constitution tier). Each proof-level, firmware and removal
/// scenario of specs/validator-admission is tested by its spec name.
contract ValidatorsLevelsV3Test is ValidatorsSetup {
    bytes32 internal constant NOTARY_1 = keccak256("notary-1");
    bytes32 internal constant NOTARY_2 = keccak256("notary-2");
    bytes32 internal constant NEW_IMAGE = keccak256("the next checker release");
    uint32 internal constant FW = 5;

    address internal genesisKey;
    address internal stranger = makeAddr("stranger");
    uint256 internal adrId;

    function setUp() public {
        _deployCoinAndPool();
        genesisKey = _newKey("genesis");
        IValidators.Registration[] memory gs = new IValidators.Registration[](1);
        gs[0] = _reg(genesisKey, makeAddr("genesis operator"), keccak256("host-genesis"), FAMILY_A);
        gs[0].firmware = FW;
        Validators.Genesis memory g = _genesis(false, gs, 1_250e6);
        g.firmware = new uint32[](3);
        g.firmware[0] = FW; // TDX
        g.firmware[1] = FW; // SEV-SNP
        g.firmware[2] = FW; // Nitro
        reg = _create(g);
        panels = new PanelsHarness(reg);
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

    function _two(IValidators.Change memory a, IValidators.Change memory b)
        internal
        pure
        returns (IValidators.Change[] memory cs)
    {
        cs = new IValidators.Change[](2);
        cs[0] = a;
        cs[1] = b;
    }

    /// Panels reports the ADR passed and final; returns its id and text.
    function _passed(IValidators.Change[] memory cs, bool removal) internal returns (uint256 id, bytes32 text) {
        id = ++adrId;
        text = keccak256(abi.encode("adr text", id));
        panels.adrPassed(id, removal, reg.adrCommitment(text, cs));
    }

    /// A passed ADR, applied.
    function _apply(IValidators.Change[] memory cs, bool removal) internal returns (uint256 id) {
        bytes32 text;
        (id, text) = _passed(cs, removal);
        reg.applyAdr(id, text, cs);
    }

    function _applyReverts(IValidators.Change[] memory cs, bool removal, bytes4 err) internal returns (uint256 id) {
        bytes32 text;
        (id, text) = _passed(cs, removal);
        vm.expectRevert(err);
        reg.applyAdr(id, text, cs);
    }

    /// An active validator of TEE type `tee` at firmware `fw`, on its own host and operator.
    function _active(bytes32 tee, uint32 fw, uint256 bond) internal returns (address key) {
        key = _nextKey();
        IValidators.Registration memory r = _reg(key, makeAddr(string.concat("op-", vm.toString(key))), keccak256(abi.encode(key)), FAMILY_A);
        r.teeType = tee;
        r.firmware = fw;
        _register(r, bond, key);
        _qualify(key);
    }

    function _zk(address key) internal view returns (IValidators.Registration memory r) {
        r = _reg(key, stranger, keccak256(abi.encode("a home PC", key)), FAMILY_B);
        r.proofType = keccak256("zktls");
        r.teeType = bytes32(0);
        r.level = 0;
        r.attestation = bytes32(0);
        r.firmware = 0;
    }

    function _expectRegisterRevert(IValidators.Registration memory r, bytes4 sel) internal {
        bytes memory sig = _sign(reg, r.key, r);
        usd.mint(stranger, 100e6);
        vm.startPrank(stranger);
        usd.approve(address(reg), 100e6);
        vm.expectRevert(sel);
        reg.register(r, 100e6, sig);
        vm.stopPrank();
    }

    function _reattest(address key, bytes32 image, uint32 fw) internal {
        bytes32 att = keccak256(abi.encode("re-attestation", key, image, fw));
        bytes memory sig = _signDigest(key, reg.reattestationDigest(key, att, image, fw));
        reg.reattest(key, att, image, fw, sig);
    }

    /// Every validator's standing re-checked, then the tier counters equal a full recount of the drawable ones.
    function _recheckAndRecount() internal {
        uint256 n = reg.validatorCount();
        address[] memory keys = new address[](n);
        for (uint256 i; i < n; ++i) {
            keys[i] = reg.validatorAt(i);
        }
        reg.recheck(keys);
        _assertRecount();
    }

    function _assertRecount() internal view {
        uint256 n = reg.validatorCount();
        for (uint256 t; t < 7; ++t) {
            uint256 step = reg.tierStep(t);
            uint256 eligible;
            for (uint256 i; i < n; ++i) {
                address key = reg.validatorAt(i);
                IValidators.Validator memory v = reg.validator(key);
                bool drawable =
                    v.state == IValidators.State.Active && v.bond >= reg.BOND_FLOOR() && reg.inStanding(key);
                if (t == 0) assertEq(reg.isDrawable(key), drawable, "isDrawable");
                if (drawable && v.bond >= 2 * step) ++eligible;
            }
            assertEq(reg.eligibleCount(step), eligible, "tier counter");
            for (uint256 j; j < eligible; ++j) {
                assertTrue(reg.isDrawable(reg.eligibleAt(step, j)), "indexed but not drawable");
            }
        }
    }

    // ---------- the lists at deployment ----------

    /// The deployment record names each TEE type's firmware minimum (D10), and lists each entry once.
    function test_theGenesisNamesTheFirmwareMinimums() public {
        assertEq(reg.minFirmware(TDX), FW);
        assertEq(reg.minFirmware(SEV_SNP), FW);
        assertEq(reg.teeTypeCount(), 3);
        assertEq(reg.imageCount(), 1);
        assertEq(reg.notaryCount(), 0);
        assertEq(reg.validator(genesisKey).firmware, FW);
        Validators.Genesis memory g = _genesis(false, new IValidators.Registration[](0), 0);
        g.firmware = new uint32[](2); // not one per type
        vm.expectRevert(Validators.BadParams.selector);
        _create(g);
        g = _genesis(false, new IValidators.Registration[](0), 0);
        g.teeTypes[1] = TDX; // twice
        vm.expectRevert(Validators.BadParams.selector);
        _create(g);
        g = _genesis(false, new IValidators.Registration[](0), 0);
        g.images = new bytes32[](2);
        g.images[0] = IMAGE;
        g.images[1] = IMAGE;
        vm.expectRevert(Validators.BadParams.selector);
        _create(g);
        g = _genesis(false, new IValidators.Registration[](0), 0);
        g.teeTypes[2] = keccak256("zktls"); // a proof type isn't a TEE type
        vm.expectRevert(Validators.BadParams.selector);
        _create(g);
    }

    // ---------- TEE attestations meet the minimum firmware level ----------

    /// A registration below its type's minimum firmware is refused; at the minimum it's accepted.
    function test_aRegistrationBelowTheMinimumFirmware() public {
        address key = _nextKey();
        IValidators.Registration memory r = _reg(key, stranger, keccak256("h"), FAMILY_A);
        r.firmware = FW - 1;
        _expectRegisterRevert(r, Validators.FirmwareTooOld.selector);
        r.firmware = FW;
        _register(r, 100e6, stranger);
        assertEq(reg.validator(key).firmware, FW);
        assertTrue(reg.inStanding(key));
    }

    /// Scenario "A flaw is patched": an ADR raises TDX's minimum. TDX validators on the old firmware stop being drawn,
    /// keep their bonds and their state; one that updates and attests again returns without a new qualification.
    function test_aFlawIsPatched() public {
        address oldFw = _active(TDX, FW, 1_250e6);
        address newFw = _active(TDX, FW + 2, 1_250e6);
        address other = _active(SEV_SNP, FW, 1_250e6);
        assertEq(reg.eligibleCount(625e6), 4);
        IValidators.Change[] memory cs = _one(IValidators.Op.RaiseFirmware, TDX, FW + 1);
        assertTrue(reg.isRemoval(cs)); // raising a minimum is judged as a removal (D7, D11)
        _apply(cs, true);
        assertEq(reg.minFirmware(TDX), FW + 1);
        // the draw skips them at once, before any re-check
        assertFalse(reg.isDrawable(oldFw));
        assertFalse(reg.isDrawable(genesisKey));
        assertTrue(reg.isDrawable(newFw) && reg.isDrawable(other));
        for (uint256 t; t < 7; ++t) {
            for (uint256 i; i < reg.rosterLength(t); ++i) {
                (address k,, uint8 bucket) = reg.rosterEntry(t, i);
                if (k == oldFw || k == genesisKey) assertEq(bucket, 0);
            }
        }
        // bonds and states kept
        assertEq(_bond(oldFw), 1_250e6);
        assertEq(uint256(_state(oldFw)), uint256(IValidators.State.Active));
        // a re-check moves them out of the counters
        _recheckAndRecount();
        assertEq(reg.eligibleCount(625e6), 2);
        // attesting again on the old firmware is refused; on the patched one it returns, active, unqualified again
        bytes32 att = keccak256("still old");
        bytes memory sig = _signDigest(oldFw, reg.reattestationDigest(oldFw, att, IMAGE, FW));
        vm.expectRevert(Validators.FirmwareTooOld.selector);
        reg.reattest(oldFw, att, IMAGE, FW, sig);
        vm.roll(vm.getBlockNumber() + 3);
        _reattest(oldFw, IMAGE, FW + 1);
        assertTrue(reg.isDrawable(oldFw));
        assertEq(uint256(_state(oldFw)), uint256(IValidators.State.Active));
        assertEq(reg.progress(oldFw).scored, 0); // no new qualification
        assertEq(reg.validator(oldFw).firmware, FW + 1);
        assertEq(reg.validator(oldFw).reattestations, 1);
        assertEq(reg.eligibleCount(625e6), 3);
        // it left the draws whose snapshot is older (as a top-up does): it rose at this block
        (address k0, uint64 raisedAt,) = _rosterOf(oldFw);
        assertEq(k0, oldFw);
        assertEq(raisedAt, vm.getBlockNumber());
        _assertRecount();
    }

    function _rosterOf(address key) internal view returns (address, uint64, uint8) {
        for (uint256 i; i < reg.rosterLength(0); ++i) {
            (address k, uint64 r, uint8 b) = reg.rosterEntry(0, i);
            if (k == key) return (k, r, b);
        }
        return (address(0), 0, 0);
    }

    /// A raised minimum never lowers one: a later, lower "raise" changes nothing; lowering is an adding operation.
    function test_firmwareMovesOnlyTheWayItsOperationSays() public {
        _apply(_one(IValidators.Op.RaiseFirmware, TDX, FW + 3), true);
        _apply(_one(IValidators.Op.RaiseFirmware, TDX, FW + 1), true);
        assertEq(reg.minFirmware(TDX), FW + 3);
        IValidators.Change[] memory lower = _one(IValidators.Op.LowerFirmware, TDX, FW);
        assertFalse(reg.isRemoval(lower));
        _applyReverts(lower, true, Validators.NotARemoval.selector);
        _apply(lower, false);
        assertEq(reg.minFirmware(TDX), FW);
        assertTrue(reg.isDrawable(genesisKey)); // back in standing
    }

    /// A candidate below a raised minimum isn't drawn as a shadow either, and keeps its qualification progress when it
    /// attests again.
    function test_aCandidateBelowARaisedMinimum() public {
        address key = _nextKey();
        IValidators.Registration memory r = _reg(key, stranger, keccak256("h-c"), FAMILY_A);
        r.firmware = FW;
        _register(r, 100e6, stranger);
        for (uint256 i; i < 5; ++i) {
            panels.recordShadow(key, true);
            panels.scoreShadow(key, true);
        }
        _apply(_one(IValidators.Op.RaiseFirmware, TDX, FW + 1), true);
        assertFalse(reg.canShadow(key));
        _reattest(key, IMAGE, FW + 1);
        assertTrue(reg.canShadow(key));
        assertEq(reg.progress(key).scored, 5);
    }

    /// A re-attestation is the key's own and used once: replayed, signed by another key, for a validator that left, or
    /// showing an image off the list, it's refused.
    function test_aReattestationIsTheKeysOwnAndUsedOnce() public {
        address key = _active(TDX, FW, 500e6);
        bytes32 att = keccak256("att-1");
        bytes memory sig = _signDigest(key, reg.reattestationDigest(key, att, IMAGE, FW + 1));
        reg.reattest(key, att, IMAGE, FW + 1, sig);
        vm.expectRevert(Validators.BadSignature.selector); // the nonce moved on
        reg.reattest(key, att, IMAGE, FW + 1, sig);
        bytes memory other = _signDigest(genesisKey, reg.reattestationDigest(key, att, IMAGE, FW + 2));
        vm.expectRevert(Validators.BadSignature.selector);
        reg.reattest(key, att, IMAGE, FW + 2, other);
        sig = _signDigest(key, reg.reattestationDigest(key, att, OTHER_IMAGE, FW + 2));
        vm.expectRevert(Validators.ImageNotAllowed.selector);
        reg.reattest(key, att, OTHER_IMAGE, FW + 2, sig);
        sig = _signDigest(key, reg.reattestationDigest(key, bytes32(0), IMAGE, FW + 2));
        vm.expectRevert(Validators.NoAttestation.selector);
        reg.reattest(key, bytes32(0), IMAGE, FW + 2, sig);
        vm.prank(key);
        reg.leave(key);
        sig = _signDigest(key, reg.reattestationDigest(key, att, IMAGE, FW + 2));
        vm.expectRevert(Validators.WrongState.selector);
        reg.reattest(key, att, IMAGE, FW + 2, sig);
    }

    // ---------- A broken type is removed faster than a new one is added ----------

    /// Scenario "An exploit is published for a TEE type": a removal ADR delists Nitro. Its validators stop being drawn
    /// at once (their group leaves the counters), keep their bonds, and may register again with an accepted type,
    /// qualifying again.
    function test_anExploitIsPublishedForATeeType() public {
        address n1 = _active(NITRO, FW, 1_250e6);
        address n2 = _active(NITRO, FW, 500e6);
        _active(SEV_SNP, FW, 1_250e6);
        assertEq(reg.eligibleCount(10e6), 4);
        _apply(_one(IValidators.Op.RemoveTeeType, NITRO, 0), true);
        assertFalse(reg.acceptedTeeType(NITRO));
        assertEq(reg.teeTypeCount(), 2);
        assertEq(reg.eligibleCount(10e6), 2); // no re-check needed
        assertFalse(reg.isDrawable(n1) || reg.isDrawable(n2));
        assertEq(_bond(n1), 1_250e6);
        assertEq(_bond(n2), 500e6);
        _assertRecount();
        // a slash or a top-up while delisted doesn't count it twice
        panels.recordCounted(n2, false, false);
        _assertRecount();
        // a new Nitro registration is refused; the operator registers a new key on an accepted type, as a candidate
        address fresh = _nextKey();
        IValidators.Registration memory r = _reg(fresh, stranger, keccak256("moved"), FAMILY_A);
        r.teeType = NITRO;
        r.firmware = FW;
        _expectRegisterRevert(r, Validators.TeeTypeNotAccepted.selector);
        r.teeType = SEV_SNP;
        _register(r, 100e6, stranger);
        assertEq(uint256(_state(fresh)), uint256(IValidators.State.Candidate));
        // its old key can't come back by attesting again
        bytes memory sig = _signDigest(n1, reg.reattestationDigest(n1, keccak256("a"), IMAGE, FW + 1));
        vm.expectRevert(Validators.TeeTypeNotAccepted.selector);
        reg.reattest(n1, keccak256("a"), IMAGE, FW + 1, sig);
        // it leaves and withdraws its whole bond
        vm.prank(n1);
        reg.leave(n1);
        vm.warp(vm.getBlockTimestamp() + 504 hours);
        reg.withdraw(n1);
        assertEq(usd.balanceOf(reg.validator(n1).operator), 1_250e6);
        _assertRecount();
    }

    /// A type removed and listed again by a later adding ADR brings its validators back into the counters, and they
    /// leave the draws whose snapshot is older.
    function test_aTypeListedAgain() public {
        address n1 = _active(NITRO, FW, 1_250e6);
        _apply(_one(IValidators.Op.RemoveTeeType, NITRO, 0), true);
        vm.roll(vm.getBlockNumber() + 10);
        _apply(_one(IValidators.Op.AddTeeType, NITRO, FW), false);
        assertTrue(reg.isDrawable(n1));
        assertEq(reg.eligibleCount(625e6), 2);
        (, uint64 raisedAt,) = _rosterOf(n1);
        assertEq(raisedAt, vm.getBlockNumber());
        _assertRecount();
    }

    /// Scenario "Removing the last accepted type": an ADR that would leave no TEE type, or no image digest, can't take
    /// effect; once a replacement has been added, it can. Nor can the TEE proof type, every TEE type at once, be removed.
    function test_removingTheLastAcceptedType() public {
        IValidators.Change[] memory all = new IValidators.Change[](3);
        all[0] = _ch(IValidators.Op.RemoveTeeType, TDX, 0);
        all[1] = _ch(IValidators.Op.RemoveTeeType, SEV_SNP, 0);
        all[2] = _ch(IValidators.Op.RemoveTeeType, NITRO, 0);
        (uint256 id, bytes32 text) = _passed(all, true);
        vm.expectRevert(Validators.LastOne.selector);
        reg.applyAdr(id, text, all);
        assertEq(reg.teeTypeCount(), 3); // nothing changed
        // a replacement first, then the removal takes effect
        _apply(_one(IValidators.Op.AddTeeType, SGX, 1), false);
        reg.applyAdr(id, text, all);
        assertEq(reg.teeTypeCount(), 1);
        assertTrue(reg.acceptedTeeType(SGX));
        // the last image
        IValidators.Change[] memory img = _one(IValidators.Op.RemoveImage, IMAGE, 0);
        (id, text) = _passed(img, true);
        vm.expectRevert(Validators.LastOne.selector);
        reg.applyAdr(id, text, img);
        _apply(_one(IValidators.Op.AddImage, NEW_IMAGE, 0), false);
        reg.applyAdr(id, text, img);
        assertFalse(reg.allowedImage(IMAGE));
        assertEq(reg.imageCount(), 1);
        _applyReverts(_one(IValidators.Op.RemoveProofType, reg.PROOF_TEE(), 0), true, Validators.LastOne.selector);
    }

    /// Scenario "A new TEE type proposed": adding is never a removal, so it can't take the short path; passed as an
    /// adding ADR it takes effect, with its own minimum, and counts as its own type.
    function test_aNewTeeTypeProposed() public {
        IValidators.Change[] memory add = _one(IValidators.Op.AddTeeType, SGX, 7);
        assertFalse(reg.isRemoval(add));
        _applyReverts(add, true, Validators.NotARemoval.selector);
        _apply(add, false);
        assertTrue(reg.acceptedTeeType(SGX));
        assertEq(reg.minFirmware(SGX), 7);
        assertEq(reg.teeTypeCount(), 4);
        address s = _active(SGX, 7, 100e6);
        assertEq(reg.validator(s).teeType, SGX);
        assertTrue(reg.validator(s).teeType != TDX); // its own type beside Intel's other one (D6)
        // a proof type's id is never a TEE type
        _applyReverts(_one(IValidators.Op.AddTeeType, reg.PROOF_ZKTLS(), 0), false, Validators.BadChange.selector);
    }

    /// An ADR that removes one thing and adds another isn't a removal (D7): it can't take effect from the removal path.
    function test_anAdrThatRemovesAndAddsIsntARemoval() public {
        IValidators.Change[] memory cs =
            _two(_ch(IValidators.Op.RemoveNotary, NOTARY_1, 0), _ch(IValidators.Op.AddNotary, NOTARY_2, 0));
        assertFalse(reg.isRemoval(cs));
        _applyReverts(cs, true, Validators.NotARemoval.selector);
        assertFalse(reg.isRemoval(new IValidators.Change[](0)));
    }

    /// An image removed: its validators stop being drawn; on the next release (added by ADR) they attest again and
    /// return without qualifying again.
    function test_aRemovedImage() public {
        address v1 = _active(SEV_SNP, FW, 1_250e6);
        _apply(_one(IValidators.Op.AddImage, NEW_IMAGE, 0), false);
        _apply(_one(IValidators.Op.RemoveImage, IMAGE, 0), true);
        assertFalse(reg.isDrawable(v1) || reg.isDrawable(genesisKey));
        _recheckAndRecount();
        assertEq(reg.eligibleCount(10e6), 0);
        _reattest(v1, NEW_IMAGE, FW);
        assertTrue(reg.isDrawable(v1));
        assertEq(reg.validator(v1).image, NEW_IMAGE);
        assertEq(uint256(_state(v1)), uint256(IValidators.State.Active));
        _assertRecount();
    }

    // ---------- applying an ADR ----------

    /// Only a passed ADR applies, once, with the operations its commitment bound; only Panels reports one passed.
    function test_onlyAPassedAdrApplies() public {
        IValidators.Change[] memory cs = _one(IValidators.Op.AddImage, NEW_IMAGE, 0);
        bytes32 text = keccak256("text");
        vm.expectRevert(Validators.NotPassed.selector);
        reg.applyAdr(77, text, cs);
        bytes32 commitment = reg.adrCommitment(text, cs);
        vm.expectRevert(Validators.NotPanels.selector);
        reg.adrPassed(77, false, commitment);
        panels.adrPassed(77, false, commitment);
        IValidators.Change[] memory other = _one(IValidators.Op.AddImage, OTHER_IMAGE, 0);
        vm.expectRevert(Validators.NotTheAdr.selector);
        reg.applyAdr(77, text, other);
        vm.expectRevert(Validators.NotTheAdr.selector);
        reg.applyAdr(77, keccak256("another text"), cs);
        reg.applyAdr(77, text, cs);
        assertTrue(reg.adr(77).applied);
        vm.expectRevert(Validators.AlreadyApplied.selector);
        reg.applyAdr(77, text, cs);
        // a second report of the same id changes nothing
        panels.adrPassed(77, true, bytes32(uint256(1)));
        assertEq(reg.adr(77).commitment, commitment);
    }

    /// No function changes a list except `applyAdr`: the lists are what the genesis and passed ADRs made them.
    function test_theListsMoveOnlyByAdr() public {
        uint256 e0 = reg.epoch();
        address[] memory none = new address[](0);
        reg.recheck(none);
        assertEq(reg.epoch(), e0 + 1);
        assertEq(reg.teeTypeCount(), 3);
        assertTrue(reg.allowedImage(IMAGE));
        assertFalse(reg.acceptedProofType(reg.PROOF_ZKTLS()));
    }

    // ---------- Level C: off at launch, switched on by an adding ADR ----------

    /// Scenario "Switching zkTLS on": an adding ADR lists zkTLS and its notaries; from then on validators register at
    /// level C, with no new contract. zkTLS can't be listed without a notary.
    function test_switchingZkTlsOn() public {
        address key = _nextKey();
        _expectRegisterRevert(_zk(key), Validators.ProofTypeNotAccepted.selector);
        _applyReverts(_one(IValidators.Op.AddProofType, reg.PROOF_ZKTLS(), 0), false, Validators.NoNotary.selector);
        IValidators.Change[] memory on =
            _two(_ch(IValidators.Op.AddProofType, reg.PROOF_ZKTLS(), 0), _ch(IValidators.Op.AddNotary, NOTARY_1, 0));
        _apply(on, false);
        assertTrue(reg.acceptedProofType(reg.PROOF_ZKTLS()));
        assertTrue(reg.acceptedNotary(NOTARY_1));
        _register(_zk(key), 100e6, stranger);
        assertEq(reg.validator(key).level, reg.LEVEL_C());
        _qualify(key);
        assertTrue(reg.isDrawable(key));
        // a zkTLS validator attests nothing: firmware stays 0
        IValidators.Registration memory r = _zk(_nextKey());
        r.firmware = 1;
        _expectRegisterRevert(r, Validators.BadRegistration.selector);
        _assertRecount();
    }

    /// Scenario "A verifier that isn't in the code": an ADR adding a proof type with no verifier path can't take
    /// effect; a new verifier needs a migration (D15).
    function test_aVerifierThatIsntInTheCodeByAdr() public {
        _applyReverts(
            _one(IValidators.Op.AddProofType, keccak256("open-model-rerun"), 0), false, Validators.NoVerifier.selector
        );
    }

    /// Scenarios "A notary that isn't listed" and "A notary removed while verdicts are in flight": a proof counts only
    /// from a notary listed when it was revealed; verdicts revealed before the removal took effect still count.
    function test_notariesAndTheirRemoval() public {
        assertFalse(reg.notaryCounts(NOTARY_2, vm.getBlockTimestamp())); // never listed
        IValidators.Change[] memory on = new IValidators.Change[](3);
        on[0] = _ch(IValidators.Op.AddProofType, reg.PROOF_ZKTLS(), 0);
        on[1] = _ch(IValidators.Op.AddNotary, NOTARY_1, 0);
        on[2] = _ch(IValidators.Op.AddNotary, NOTARY_2, 0);
        _apply(on, false);
        uint256 listedAt = vm.getBlockTimestamp();
        assertTrue(reg.notaryCounts(NOTARY_1, listedAt));
        assertFalse(reg.notaryCounts(NOTARY_1, listedAt - 1)); // before it was listed
        vm.warp(listedAt + 1 days);
        uint256 inFlight = vm.getBlockTimestamp();
        vm.warp(listedAt + 2 days);
        _apply(_one(IValidators.Op.RemoveNotary, NOTARY_1, 0), true);
        assertFalse(reg.acceptedNotary(NOTARY_1));
        assertTrue(reg.notaryCounts(NOTARY_1, inFlight)); // revealed before the removal took effect
        assertFalse(reg.notaryCounts(NOTARY_1, vm.getBlockTimestamp()));
        assertTrue(reg.notaryCounts(NOTARY_2, vm.getBlockTimestamp()));
        // the last notary can't go while zkTLS is listed; with zkTLS, it can
        _applyReverts(_one(IValidators.Op.RemoveNotary, NOTARY_2, 0), true, Validators.NoNotary.selector);
        _apply(
            _two(_ch(IValidators.Op.RemoveProofType, reg.PROOF_ZKTLS(), 0), _ch(IValidators.Op.RemoveNotary, NOTARY_2, 0)),
            true
        );
        assertEq(reg.notaryCount(), 0);
    }

    /// zkTLS switched off again by a removal: its validators leave the counters at once, keep their bonds, and come
    /// back if an adding ADR lists it again.
    function test_zkTlsSwitchedOffAndOnAgain() public {
        _apply(
            _two(_ch(IValidators.Op.AddProofType, reg.PROOF_ZKTLS(), 0), _ch(IValidators.Op.AddNotary, NOTARY_1, 0)),
            false
        );
        address pc = _nextKey();
        _register(_zk(pc), 100e6, stranger);
        _qualify(pc);
        assertEq(reg.eligibleCount(10e6), 2);
        _apply(_one(IValidators.Op.RemoveProofType, reg.PROOF_ZKTLS(), 0), true);
        assertEq(reg.eligibleCount(10e6), 1);
        assertFalse(reg.isDrawable(pc));
        assertEq(_bond(pc), 100e6);
        _assertRecount();
        _apply(_one(IValidators.Op.AddProofType, reg.PROOF_ZKTLS(), 0), false);
        assertTrue(reg.isDrawable(pc));
        _assertRecount();
    }

    // ---------- the simulated proof type (D18) ----------

    /// No ADR lists `simulated` off a devnet: on any chain id but 31337 and 7193 it's refused as a verifier this
    /// deployment hasn't got.
    function testFuzz_noAdrListsSimulatedOffADevnet(uint64 chain) public {
        vm.assume(chain != 31_337 && chain != 7_193 && chain != 0);
        vm.chainId(chain);
        _applyReverts(_one(IValidators.Op.AddProofType, reg.PROOF_SIMULATED(), 0), false, Validators.NoVerifier.selector);
        assertFalse(reg.acceptedProofType(reg.PROOF_SIMULATED()));
    }

    /// A deployment on any chain id but 31337 and 7193 refuses `simulated` (D18; the same rule as the genesis check).
    function testFuzz_aDeploymentOffADevnetRefusesSimulated(uint64 chain) public {
        vm.assume(chain != 31_337 && chain != 7_193 && chain != 0);
        vm.chainId(chain);
        Validators.Genesis memory g = _genesis(true, new IValidators.Registration[](0), 0);
        vm.expectRevert(Validators.BadParams.selector);
        _create(g);
    }

    /// On a devnet an adding ADR may list `simulated`, and it still counts as level A; a removal takes it off, and its
    /// validators stop being drawn.
    function test_simulatedByAdrOnADevnet() public {
        assertEq(block.chainid, 31_337);
        _apply(_one(IValidators.Op.AddProofType, reg.PROOF_SIMULATED(), 0), false);
        address key = _nextKey();
        IValidators.Registration memory r = _reg(key, stranger, keccak256("dstack"), FAMILY_A);
        r.proofType = keccak256("simulated");
        r.level = 2;
        r.firmware = FW;
        _register(r, 1_250e6, stranger);
        _qualify(key);
        assertEq(reg.validator(key).level, reg.LEVEL_A());
        assertTrue(reg.isDrawable(key));
        _apply(_one(IValidators.Op.RemoveProofType, reg.PROOF_SIMULATED(), 0), true);
        assertFalse(reg.isDrawable(key));
        _recheckAndRecount();
    }

    // ---------- receipts name their proof ----------

    /// The receipt's hash covers its proof type, notary, model and weights, image, seed, prompt, answer, tests and
    /// proof (D11, owner 2026-11-03): changing any one changes the hash.
    function test_receiptsNameTheirProof() public view {
        IValidators.Receipt memory r = IValidators.Receipt(
            reg.PROOF_TEE(),
            bytes32(0),
            keccak256("anthropic/claude-x"),
            bytes32(0),
            IMAGE,
            keccak256("seed"),
            keccak256("prompt"),
            keccak256("answer"),
            keccak256("tests"),
            keccak256("quote")
        );
        bytes32 h = reg.receiptHash(r);
        assertEq(
            h,
            keccak256(
                abi.encode(
                    keccak256(
                        "Receipt(bytes32 proofType,bytes32 notary,bytes32 model,bytes32 weights,bytes32 image,bytes32 seed,bytes32 prompt,bytes32 answer,bytes32 tests,bytes32 proof)"
                    ),
                    r
                )
            )
        );
        r.proofType = reg.PROOF_ZKTLS();
        assertTrue(reg.receiptHash(r) != h);
        r.proofType = reg.PROOF_TEE();
        r.weights = keccak256("weights");
        assertTrue(reg.receiptHash(r) != h);
    }

    // ---------- counters ----------

    /// Fuzz: any sequence of list ADRs (types, minimums, images, zkTLS), registrations, re-attestations and
    /// re-checks leaves the tier counters equal to a full recount once every validator is re-checked, and the
    /// lists never empty.
    function testFuzz_theCountersFollowTheLists(uint256[24] calldata ops) public {
        _apply(
            _two(_ch(IValidators.Op.AddProofType, reg.PROOF_ZKTLS(), 0), _ch(IValidators.Op.AddNotary, NOTARY_1, 0)),
            false
        );
        bytes32[4] memory tees = [TDX, SEV_SNP, NITRO, SGX];
        bytes32[2] memory images = [IMAGE, NEW_IMAGE];
        address[] memory ks = new address[](8);
        uint256 nk;
        for (uint256 i; i < ops.length; ++i) {
            uint256 op = ops[i];
            uint256 kind = op % 9;
            bytes32 tee = tees[(op >> 8) % 4];
            uint32 fw = uint32((op >> 16) % 4) + FW - 1;
            if (kind == 0 && nk < ks.length) {
                if (!reg.acceptedTeeType(tee) || fw < reg.minFirmware(tee) || !reg.allowedImage(IMAGE)) continue;
                ks[nk++] = _active(tee, fw, (op >> 24) % 2 == 0 ? 100e6 : 1_250e6);
            } else if (kind == 1 && nk < ks.length) {
                if (!reg.allowedImage(IMAGE) || !reg.acceptedProofType(reg.PROOF_ZKTLS())) continue;
                address pc = _nextKey();
                _register(_zk(pc), 300e6, stranger);
                _qualify(pc);
                ks[nk++] = pc;
            } else if (kind == 2) {
                if (reg.teeTypeCount() > 1) _apply(_one(IValidators.Op.RemoveTeeType, tee, 0), true);
            } else if (kind == 3) {
                _apply(_one(IValidators.Op.AddTeeType, tee, fw), false);
            } else if (kind == 4) {
                if (reg.acceptedTeeType(tee)) _apply(_one(IValidators.Op.RaiseFirmware, tee, fw), true);
            } else if (kind == 5) {
                if (reg.acceptedTeeType(tee)) _apply(_one(IValidators.Op.LowerFirmware, tee, fw), false);
            } else if (kind == 6) {
                bytes32 im = images[(op >> 8) % 2];
                if (reg.allowedImage(im)) {
                    if (reg.imageCount() > 1) _apply(_one(IValidators.Op.RemoveImage, im, 0), true);
                } else {
                    _apply(_one(IValidators.Op.AddImage, im, 0), false);
                }
            } else if (kind == 7) {
                IValidators.Op o = reg.acceptedProofType(reg.PROOF_ZKTLS())
                    ? IValidators.Op.RemoveProofType
                    : IValidators.Op.AddProofType;
                _apply(_one(o, reg.PROOF_ZKTLS(), 0), o == IValidators.Op.RemoveProofType);
            } else if (nk != 0) {
                address key = ks[(op >> 8) % nk];
                IValidators.Validator memory v = reg.validator(key);
                bytes32 im = reg.allowedImage(NEW_IMAGE) ? NEW_IMAGE : IMAGE;
                if (v.teeType == bytes32(0)) {
                    _reattest(key, im, 0);
                } else if (reg.acceptedTeeType(v.teeType)) {
                    _reattest(key, im, reg.minFirmware(v.teeType) + 1);
                }
            }
            assertGe(reg.teeTypeCount(), 1);
            assertGe(reg.imageCount(), 1);
        }
        _recheckAndRecount();
    }
}
