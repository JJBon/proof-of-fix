// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {Validators} from "../../src/v3/Validators.sol";
import {IValidators} from "../../src/v3/IValidators.sol";
import {FeeCoin} from "../mocks/FeeCoin.sol";
import {Pool} from "../../src/v2/Pool.sol";
import {
    ValidatorsSetup,
    PanelsHarness,
    ValidatorsWithZkTls,
    TDX,
    SEV_SNP,
    NITRO,
    SGX,
    IMAGE,
    OTHER_IMAGE,
    FAMILY_A,
    FAMILY_B
} from "./helpers/ValidatorsSetup.sol";

/// proof-of-fix#138, task 3.1 of #132: the open validator registry against specs/validator-admission. Each scenario
/// the registry decides is tested here by its spec name; for the parts that belong to the draw or to the lists, this
/// file checks the registry's side (what it records and counts), and the scenario itself is left to its task:
/// - Panels (3.2): "A candidate copies the counted judges" (the seal window), "A submission waits for a panel", the
///   four shadow-scoring scenarios (what a shadow is scored against, once), "Ten nodes on one cloud" and "Too few
///   distinct hosts" (the caps in the draw), the three TEE-type-cap scenarios, "One vendor's two types on a panel of
///   three", and "The owner's validator and the owner's fix" (recusal of parties);
/// - the constitution's lists (3.4, in ValidatorsLevelsV3 and PanelsLevelsV3): "A notary that isn't listed", "A notary
///   removed while verdicts are in flight", "Switching zkTLS on", "A flaw is patched", "An exploit is published for a
///   TEE type", "Removing the last accepted type" and "A new TEE type proposed".
contract ValidatorsV3Test is ValidatorsSetup {
    address internal genesisKey;
    address internal stranger = makeAddr("stranger");

    function setUp() public {
        _deployCoinAndPool();
        genesisKey = _newKey("genesis");
        _deploy(genesisKey);
    }

    // ---------- Anyone may register a validator ----------

    /// Scenario "A newcomer registers": no co-signature from anyone, the owner (the deployer) included.
    function test_aNewcomerRegisters() public {
        address key = _nextKey();
        address newcomer = makeAddr("newcomer with no relation to the project");
        _register(_reg(key, newcomer, keccak256("host-x"), FAMILY_A), 100e6, newcomer);
        assertEq(uint256(_state(key)), uint256(IValidators.State.Candidate));
        assertEq(_bond(key), 100e6);
        assertTrue(reg.canShadow(key));
        assertFalse(reg.isActive(key));
        assertFalse(reg.isDrawable(key));
        assertEq(reg.candidateCount(), 1);
        assertEq(reg.candidateAt(0), key);
        assertEq(usd.balanceOf(address(reg)), 1_250e6 + 100e6);
    }

    /// Scenario "An image not on the list".
    function test_anImageNotOnTheList() public {
        address key = _nextKey();
        IValidators.Registration memory r = _reg(key, stranger, keccak256("h"), FAMILY_A);
        r.image = OTHER_IMAGE;
        bytes memory sig = _sign(reg, key, r);
        _fund(stranger, 100e6);
        vm.prank(stranger);
        vm.expectRevert(Validators.ImageNotAllowed.selector);
        reg.register(r, 100e6, sig);
    }

    /// Scenario "Too small a bond": below the floor, and below it once a coin's transfer fee is taken.
    function test_tooSmallABond() public {
        address key = _nextKey();
        IValidators.Registration memory r = _reg(key, stranger, keccak256("h"), FAMILY_A);
        bytes memory sig = _sign(reg, key, r);
        _fund(stranger, 100e6);
        vm.prank(stranger);
        vm.expectRevert(Validators.BondTooSmall.selector);
        reg.register(r, 100e6 - 1, sig);
    }

    function test_aBondCountsWhatArrives() public {
        FeeCoin fee = new FeeCoin();
        address[] memory coins = new address[](1);
        coins[0] = address(fee);
        Pool p = new Pool(coins);
        Validators.Genesis memory g = _genesis(false, new IValidators.Registration[](0), 0);
        g.coin = address(fee);
        g.pool = address(p);
        Validators v = _create(g);
        address key = _nextKey();
        IValidators.Registration memory r = _reg(key, stranger, keccak256("h"), FAMILY_A);
        bytes memory sig = _sign(v, key, r);
        fee.mint(stranger, 200e6);
        vm.startPrank(stranger);
        fee.approve(address(v), type(uint256).max);
        vm.expectRevert(Validators.BondTooSmall.selector); // 1 % burned: 99 arrive
        v.register(r, 100e6, sig);
        v.register(r, 102e6, sig);
        vm.stopPrank();
        assertEq(v.validator(key).bond, 102e6 - 1_020_000);
        assertEq(fee.balanceOf(address(v)), v.totalBonds());
    }

    /// Scenario "Someone else's key": the key named didn't sign.
    function test_someoneElsesKey() public {
        address key = _nextKey();
        address other = _nextKey();
        IValidators.Registration memory r = _reg(key, stranger, keccak256("h"), FAMILY_A);
        bytes memory sig = _sign(reg, other, r);
        _fund(stranger, 100e6);
        vm.prank(stranger);
        vm.expectRevert(Validators.BadSignature.selector);
        reg.register(r, 100e6, sig);
        // a signature over other fields than those registered is refused too
        sig = _sign(reg, key, r);
        r.family = FAMILY_B;
        vm.prank(stranger);
        vm.expectRevert(Validators.BadSignature.selector);
        reg.register(r, 100e6, sig);
    }

    function test_aKeyRegistersOnce() public {
        address key = _candidate(100e6);
        IValidators.Registration memory r = _reg(key, stranger, keccak256("h2"), FAMILY_B);
        bytes memory sig = _sign(reg, key, r);
        _fund(stranger, 100e6);
        vm.prank(stranger);
        vm.expectRevert(Validators.KeyTaken.selector);
        reg.register(r, 100e6, sig);
    }

    function test_aRegistrationNamesItsHostFamilyAndOperator() public {
        address key = _nextKey();
        IValidators.Registration memory r = _reg(key, address(0), keccak256("h"), FAMILY_A);
        _expectRegisterRevert(r, Validators.BadRegistration.selector);
        r = _reg(key, stranger, bytes32(0), FAMILY_A);
        _expectRegisterRevert(r, Validators.BadRegistration.selector);
        r = _reg(key, stranger, keccak256("h"), bytes32(0));
        _expectRegisterRevert(r, Validators.BadRegistration.selector);
        r = _reg(key, stranger, keccak256("h"), FAMILY_A);
        r.attestation = bytes32(0);
        _expectRegisterRevert(r, Validators.NoAttestation.selector);
        r = _reg(key, stranger, keccak256("h"), FAMILY_A);
        r.teeType = SGX; // not on the launch list (D6)
        _expectRegisterRevert(r, Validators.TeeTypeNotAccepted.selector);
        r = _reg(key, stranger, keccak256("h"), FAMILY_A);
        r.level = 3; // a TEE declares A or B
        _expectRegisterRevert(r, Validators.BadLevel.selector);
    }

    // ---------- A registration records what the caps need ----------

    /// Scenario "Reading a validator's host".
    function test_readingAValidatorsHost() public {
        address key = _nextKey();
        address op = makeAddr("operator");
        IValidators.Registration memory r = _reg(key, op, keccak256("cloud-1/eu-west"), FAMILY_B);
        r.teeType = SEV_SNP;
        r.level = 2;
        _register(r, 250e6, op);
        IValidators.Validator memory v = reg.validator(key);
        assertEq(v.key, key);
        assertEq(v.proofType, reg.PROOF_TEE());
        assertEq(v.teeType, SEV_SNP);
        assertEq(v.host, keccak256("cloud-1/eu-west"));
        assertEq(v.family, FAMILY_B);
        assertEq(v.operator, op);
        assertEq(v.attestation, r.attestation);
        assertEq(v.image, IMAGE);
        assertEq(v.level, 2);
        assertFalse(v.genesis);
        assertEq(v.registeredAt, block.timestamp);
    }

    // ---------- A validator's model family is fixed by its registration ----------

    /// Scenario "Switching to the top model": no function changes a family; a new key with the other family registers
    /// and qualifies as a shadow before it's drawn; the old one may leave.
    function test_switchingToTheTopModel() public {
        address old = _active(100e6);
        assertEq(reg.validator(old).family, FAMILY_A);
        address op = reg.validator(old).operator;
        address fresh = _nextKey();
        _register(_reg(fresh, op, keccak256("host-fresh"), FAMILY_B), 100e6, op);
        assertEq(uint256(_state(fresh)), uint256(IValidators.State.Candidate));
        assertFalse(reg.isDrawable(fresh)); // not drawn for counted panels before it qualifies
        _qualify(fresh);
        assertTrue(reg.isDrawable(fresh));
        assertEq(reg.validator(fresh).family, FAMILY_B);
        vm.prank(op);
        reg.leave(old);
        assertEq(uint256(_state(old)), uint256(IValidators.State.Leaving));
        assertEq(reg.validator(old).family, FAMILY_A);
    }

    // ---------- Accepted proof types, zkTLS among them; Level C is off at launch ----------

    /// Scenario "zkTLS before it is switched on".
    function test_zkTlsBeforeItIsSwitchedOn() public {
        address key = _nextKey();
        IValidators.Registration memory r = _zk(key);
        _expectRegisterRevert(r, Validators.ProofTypeNotAccepted.selector);
        assertFalse(reg.acceptedProofType(reg.PROOF_ZKTLS()));
    }

    /// Level C is off at launch: a genesis list naming zkTLS is refused.
    function test_aGenesisListingZkTlsIsRefused() public {
        Validators.Genesis memory g = _genesis(false, new IValidators.Registration[](0), 0);
        g.proofTypes = new bytes32[](2);
        g.proofTypes[0] = keccak256("tee");
        g.proofTypes[1] = keccak256("zktls");
        vm.expectRevert(Validators.BadParams.selector);
        _create(g);
    }

    /// Scenario "A verifier that isn't in the code": a proof type the code has no path for can't be listed.
    function test_aVerifierThatIsntInTheCode() public {
        Validators.Genesis memory g = _genesis(false, new IValidators.Registration[](0), 0);
        g.proofTypes[0] = keccak256("open-model-rerun");
        vm.expectRevert(Validators.BadParams.selector);
        _create(g);
    }

    /// Scenarios "A validator on ordinary hardware" and "An ordinary PC", and the code path "Switching zkTLS on" uses:
    /// with zkTLS on the list (as an adding ADR puts it, stood in for by a test-only constructor), a zkTLS key registers
    /// as a level C candidate with no TEE type and qualifies by the same rules.
    function test_aValidatorOnOrdinaryHardware() public {
        Validators.Genesis memory g = _genesis(false, new IValidators.Registration[](0), 0);
        vm.prank(deployer);
        Validators zk = new ValidatorsWithZkTls(g);
        PanelsHarness h = new PanelsHarness(zk);
        address key = _nextKey();
        IValidators.Registration memory r = _zk(key);
        bytes memory sig = _sign(zk, key, r);
        _fund(stranger, 100e6);
        vm.startPrank(stranger);
        usd.approve(address(zk), 100e6);
        zk.register(r, 100e6, sig);
        vm.stopPrank();
        IValidators.Validator memory v = zk.validator(key);
        assertEq(uint256(v.state), uint256(IValidators.State.Candidate));
        assertEq(v.level, zk.LEVEL_C());
        assertEq(v.teeType, bytes32(0));
        for (uint256 i; i < 20; ++i) {
            h.recordShadow(key, true);
            h.scoreShadow(key, true);
        }
        assertTrue(zk.isDrawable(key));
        assertEq(zk.eligibleCount(50e6), 1);
        assertEq(zk.eligibleAt(50e6, 0), key);
        // a zkTLS registration names no TEE type
        address key2 = _nextKey();
        r = _zk(key2);
        r.teeType = TDX;
        sig = _sign(zk, key2, r);
        _fund(stranger, 100e6);
        vm.startPrank(stranger);
        usd.approve(address(zk), 100e6);
        vm.expectRevert(Validators.BadRegistration.selector);
        zk.register(r, 100e6, sig);
        vm.stopPrank();
    }

    // ---------- Each validator has a proof level ----------

    /// Scenario "A confidential VM in a cloud".
    function test_aConfidentialVmInACloud() public {
        address key = _nextKey();
        IValidators.Registration memory r = _reg(key, stranger, keccak256("azure/westeurope"), FAMILY_A);
        r.level = 1;
        _register(r, 100e6, stranger);
        assertEq(reg.validator(key).level, reg.LEVEL_A());
    }

    /// Scenario "A TEE server at home".
    function test_aTeeServerAtHome() public {
        address key = _nextKey();
        IValidators.Registration memory r = _reg(key, stranger, keccak256("home"), FAMILY_A);
        r.teeType = SEV_SNP;
        r.level = 2;
        _register(r, 100e6, stranger);
        assertEq(reg.validator(key).level, reg.LEVEL_B());
    }

    // ---------- The simulated proof type (D18) ----------

    /// `simulated` is listed only on a devnet chain id, and refused on every other.
    function test_simulatedIsRefusedOnAnyOtherChain() public {
        uint256[4] memory ids = [uint256(1), 10, 8453, 11155111];
        for (uint256 i; i < ids.length; ++i) {
            vm.chainId(ids[i]);
            Validators.Genesis memory g = _genesis(true, new IValidators.Registration[](0), 0);
            vm.expectRevert(Validators.BadParams.selector);
            _create(g);
        }
    }

    function testFuzz_simulatedIsRefusedOnAnyOtherChain(uint64 id) public {
        vm.assume(id != 31_337 && id != 7_193 && id != 0);
        vm.chainId(id);
        Validators.Genesis memory g = _genesis(true, new IValidators.Registration[](0), 0);
        vm.expectRevert(Validators.BadParams.selector);
        _create(g);
    }

    /// On anvil and on the AWS devnet, `simulated` registers at level A, even as the genesis.
    function test_simulatedCountsAsLevelAOnDevnets() public {
        uint256[2] memory ids = [uint256(31_337), 7_193];
        for (uint256 i; i < ids.length; ++i) {
            vm.chainId(ids[i]);
            address key = _nextKey();
            IValidators.Registration[] memory gs = new IValidators.Registration[](1);
            gs[0] = _reg(key, stranger, keccak256("seats host"), FAMILY_A);
            gs[0].proofType = keccak256("simulated");
            gs[0].level = 2; // whatever it declares
            Validators v = _create(_genesis(true, gs, 100e6));
            assertEq(v.validator(key).level, v.LEVEL_A());
            assertTrue(v.acceptedProofType(v.PROOF_SIMULATED()));
            assertEq(v.genesisKey(), key);
        }
    }

    // ---------- Activation by the qualification thresholds, with no vote ----------

    /// Scenario "A candidate qualifies": every shadow verdict revealed, agreeing at least 80 %.
    function test_aCandidateQualifies() public {
        address key = _candidate(100e6);
        for (uint256 i; i < 19; ++i) {
            panels.recordShadow(key, true);
            panels.scoreShadow(key, i >= 4); // 4 disagreements of 20: exactly 80 %
        }
        assertEq(uint256(_state(key)), uint256(IValidators.State.Candidate));
        panels.recordShadow(key, true);
        uint256 e = reg.epoch();
        panels.scoreShadow(key, true);
        assertEq(uint256(_state(key)), uint256(IValidators.State.Active));
        assertTrue(reg.isActive(key));
        assertTrue(reg.isDrawable(key));
        assertEq(reg.activeCount(), 2);
        assertEq(reg.candidateCount(), 0);
        assertGt(reg.epoch(), e);
    }

    function test_aCandidateBelowTheAgreementCoolsOff() public {
        address key = _candidate(100e6);
        for (uint256 i; i < 20; ++i) {
            panels.recordShadow(key, true);
            panels.scoreShadow(key, i >= 5); // 75 %
        }
        assertEq(uint256(_state(key)), uint256(IValidators.State.Candidate));
        assertFalse(reg.canShadow(key));
        assertEq(reg.progress(key).cooldownUntil, block.timestamp + 7 days);
        // shadow verdicts in the cooling-off period don't count
        panels.recordShadow(key, true);
        panels.scoreShadow(key, true);
        assertEq(reg.progress(key).scored, 0);
        vm.warp(block.timestamp + 7 days);
        assertTrue(reg.canShadow(key));
        _qualify(key);
        assertTrue(reg.isActive(key));
        assertEq(_bond(key), 100e6); // a failed attempt costs nothing
    }

    /// Scenario "A candidate that never answers": its reveal rate stays below the threshold; it isn't activated and
    /// its bond is untouched.
    function test_aCandidateThatNeverAnswers() public {
        address key = _candidate(100e6);
        for (uint256 i; i < 100; ++i) {
            panels.recordShadow(key, false);
        }
        assertEq(uint256(_state(key)), uint256(IValidators.State.Candidate));
        assertEq(_bond(key), 100e6);
        // and one that reveals 20 of 22 (91 %) and agrees every time still fails the attempt
        address late = _candidate(100e6);
        for (uint256 i; i < 20; ++i) {
            if (i % 10 == 0) panels.recordShadow(late, false);
            panels.recordShadow(late, true);
            panels.scoreShadow(late, true);
        }
        assertEq(uint256(_state(late)), uint256(IValidators.State.Candidate));
        assertFalse(reg.canShadow(late));
        assertEq(_bond(late), 100e6);
    }

    function test_aRevealRateAtTheThresholdQualifies() public {
        address key = _candidate(100e6);
        panels.recordShadow(key, false); // 20 of 21 revealed: 95.2 %
        _qualify(key);
        assertTrue(reg.isActive(key));
    }

    // ---------- No account adds, removes or blocks a validator ----------

    /// Scenario "The owner tries to admit a friend": no function activates a candidate, the deployer's account and
    /// every other included; the hooks answer only the bound consumer, and only qualification activates.
    function test_theOwnerTriesToAdmitAFriend() public {
        address friend = _candidate(100e6);
        vm.expectRevert(Validators.NotPanels.selector);
        reg.scoreShadow(friend, true);
        vm.expectRevert(Validators.NotPanels.selector);
        reg.recordShadow(friend, true);
        vm.expectRevert(Validators.AlreadyBound.selector);
        reg.bind();
        vm.prank(genesisKey);
        vm.expectRevert(Validators.AlreadyBound.selector);
        reg.bind();
        assertEq(uint256(_state(friend)), uint256(IValidators.State.Candidate));
    }

    /// Scenario "A DAO funds the project": a DAO's validator registers and qualifies like any other.
    function test_aDaoFundsTheProject() public {
        address dao = makeAddr("dao");
        address key = _nextKey();
        _register(_reg(key, dao, keccak256("dao host"), FAMILY_A), 100e6, dao);
        assertEq(uint256(_state(key)), uint256(IValidators.State.Candidate));
        vm.prank(dao);
        vm.expectRevert(Validators.NotPanels.selector);
        reg.slashFault(genesisKey, IValidators.Fault.FalseVerdict, dao);
        vm.prank(dao);
        vm.expectRevert(Validators.NotAllowed.selector);
        reg.leave(genesisKey);
    }

    /// No function changes a parameter: every external function of the compiled ABI is a constant, a view, a hook
    /// for the bound consumer, or one of the registry's own actions; none takes a parameter's value.
    function test_noFunctionChangesAParameter() public view {
        string memory json = vm.readFile("out/Validators.sol/Validators.json");
        string[] memory allowed = vm.split(
            string.concat(
                // anyone: registration, bonds, leaving, faults, payouts; the consumer binds once
                "register,topUp,leave,withdraw,proveEquivocation,claim,payPool,bind,",
                // anyone, under the constitution's lists: re-attest, re-check standing, apply a passed ADR (task 3.4)
                "reattest,recheck,applyAdr,",
                // the bound consumer's hooks: counters, scores, finality, faults (no parameter among their inputs)
                "recordShadow,scoreShadow,recordCounted,verdictOpened,verdictFinal,challengeOpened,challengeClosed,",
                "slashFault,adrPassed,",
                // views
                "isActive,isDrawable,canShadow,validator,progress,familyOf,validatorCount,validatorAt,candidateCount,",
                "candidateAt,tierStep,tierOf,eligibleCount,eligibleAt,rosterLength,rosterEntry,bucketSize,groups,domainSeparator,",
                "registrationDigest,statementDigest,coin,pool,panels,epoch,activeCount,totalBonds,totalOwed,poolOwed,",
                "genesisKey,owed,acceptedProofType,acceptedTeeType,allowedImage,equivocationProven,",
                "inStanding,acceptedNotary,minFirmware,notaryCounts,adr,adrCommitment,isRemoval,receiptHash,",
                "reattestationDigest,teeTypeCount,imageCount,notaryCount,",
                // the parameters: constants, readable and never written
                "BPS,BOND_FLOOR,BOND_FACTOR,TIERS,QUALIFY_VERDICTS,QUALIFY_REVEAL_BPS,QUALIFY_AGREE_BPS,",
                "QUALIFY_COOLDOWN,ACTIVE_REVEAL_WINDOW,ACTIVE_MISSES_MAX,UNBONDING_DELAY,GENESIS_MAX,",
                "FALSE_VERDICT_SLASH_BPS,EQUIVOCATION_SLASH_BPS,DA_FAIL_SLASH_BPS,SILENCE_SLASH,SEALED_NO_REVEAL_SLASH,",
                "CHALLENGE_REWARD_BPS,LEVEL_A,LEVEL_B,LEVEL_C,PROOF_TEE,PROOF_ZKTLS,PROOF_SIMULATED,LOCAL_CHAIN_ID,",
                "DEVNET_CHAIN_ID,REGISTRATION_TYPEHASH,STATEMENT_TYPEHASH,REATTESTATION_TYPEHASH,RECEIPT_TYPEHASH,ADR_TAG"
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

    /// The parameters read back as the design's and ADR 0004's values, before and after every kind of action.
    function test_parametersAreTheAdrs() public {
        _checkParameters();
        address key = _active(500e6);
        panels.recordCounted(key, false, false);
        panels.slashFault(key, IValidators.Fault.Availability, stranger);
        vm.prank(key);
        reg.leave(key);
        vm.warp(block.timestamp + 504 hours);
        reg.withdraw(key);
        _checkParameters();
    }

    function _checkParameters() internal view {
        assertEq(reg.BOND_FLOOR(), 100e6);
        assertEq(reg.BOND_FACTOR(), 2);
        assertEq(reg.QUALIFY_VERDICTS(), 20);
        assertEq(reg.QUALIFY_REVEAL_BPS(), 9_500);
        assertEq(reg.QUALIFY_AGREE_BPS(), 8_000);
        assertEq(reg.QUALIFY_COOLDOWN(), 7 days);
        assertEq(reg.ACTIVE_REVEAL_WINDOW(), 50);
        assertEq(reg.ACTIVE_MISSES_MAX(), 5);
        assertEq(reg.UNBONDING_DELAY(), 504 hours);
        assertEq(reg.GENESIS_MAX(), 1);
        assertEq(reg.FALSE_VERDICT_SLASH_BPS(), 10_000);
        assertEq(reg.EQUIVOCATION_SLASH_BPS(), 10_000);
        assertEq(reg.DA_FAIL_SLASH_BPS(), 2_000);
        assertEq(reg.SILENCE_SLASH(), 5e6);
        assertEq(reg.SEALED_NO_REVEAL_SLASH(), 5e6);
        assertEq(reg.CHALLENGE_REWARD_BPS(), 5_000);
        uint256[7] memory steps = [uint256(10e6), 25e6, 50e6, 125e6, 250e6, 312_500_000, 625e6];
        for (uint256 t; t < 7; ++t) {
            assertEq(reg.tierStep(t), steps[t]);
        }
        assertTrue(reg.acceptedProofType(reg.PROOF_TEE()));
        assertFalse(reg.acceptedProofType(reg.PROOF_ZKTLS()));
        assertFalse(reg.acceptedProofType(reg.PROOF_SIMULATED()));
        assertTrue(reg.acceptedTeeType(TDX) && reg.acceptedTeeType(SEV_SNP) && reg.acceptedTeeType(NITRO));
        assertTrue(reg.allowedImage(IMAGE));
        assertEq(reg.panels(), address(panels));
    }

    // ---------- A validator stops being drawn when it can't serve ----------

    /// Scenario "A validator goes offline": more than 5 misses in its last 50 counted draws; it's no longer drawn and
    /// re-qualifies to return.
    function test_aValidatorGoesOffline() public {
        address key = _active(1_250e6);
        for (uint256 i; i < 50; ++i) {
            panels.recordCounted(key, true, true);
        }
        for (uint256 i; i < 5; ++i) {
            panels.recordCounted(key, false, false);
        }
        assertTrue(reg.isActive(key)); // 45 of 50: 90 %, not below
        assertEq(reg.progress(key).misses, 5);
        panels.recordCounted(key, false, false);
        assertEq(uint256(_state(key)), uint256(IValidators.State.Candidate));
        assertFalse(reg.isDrawable(key));
        assertEq(reg.validator(key).suspensions, 1);
        assertTrue(reg.canShadow(key));
        assertEq(reg.activeCount(), 1);
        _qualify(key);
        assertTrue(reg.isDrawable(key));
        assertEq(reg.progress(key).misses, 0);
    }

    /// Misses leave the window after 50 draws.
    function test_oldMissesLeaveTheWindow() public {
        address key = _active(1_250e6);
        for (uint256 i; i < 5; ++i) {
            panels.recordCounted(key, false, false);
        }
        for (uint256 i; i < 50; ++i) {
            panels.recordCounted(key, true, true);
        }
        assertEq(reg.progress(key).misses, 0);
        for (uint256 i; i < 5; ++i) {
            panels.recordCounted(key, false, false);
        }
        assertTrue(reg.isActive(key));
    }

    /// Scenario "A new validator misses early": before 50 draws, more than 5 misses suspend, as if its earlier draws
    /// had all been revealed.
    function test_aNewValidatorMissesEarly() public {
        address key = _active(1_250e6);
        for (uint256 i; i < 5; ++i) {
            panels.recordCounted(key, false, false);
        }
        assertTrue(reg.isActive(key));
        panels.recordCounted(key, true, false);
        assertFalse(reg.isActive(key));
    }

    // ---------- Slashing only for provable faults ----------

    /// Scenario "A false verdict": the whole bond; not drawn until its bond is back at the floor.
    function test_aFalseVerdict() public {
        address key = _active(500e6);
        address challenger = makeAddr("challenger");
        assertEq(reg.eligibleCount(250e6), 2);
        panels.slashFault(key, IValidators.Fault.FalseVerdict, challenger);
        assertEq(_bond(key), 0);
        assertEq(reg.validator(key).slashed, 500e6);
        assertTrue(reg.isActive(key));
        assertFalse(reg.isDrawable(key));
        assertEq(reg.eligibleCount(250e6), 1);
        assertEq(reg.owed(challenger), 250e6);
        assertEq(reg.poolOwed(), 250e6);
        _topUp(key, 99e6);
        assertFalse(reg.isDrawable(key));
        _topUp(key, 1e6);
        assertTrue(reg.isDrawable(key));
        assertEq(reg.eligibleCount(50e6), 2);
        assertEq(reg.eligibleCount(125e6), 1); // a $100 bond covers bounties up to $50
        // the challenger and the pool are paid
        vm.prank(challenger);
        reg.claim();
        assertEq(usd.balanceOf(challenger), 250e6);
        reg.payPool();
        assertEq(pool.held(address(usd)), 250e6);
        assertEq(usd.balanceOf(address(reg)), reg.totalBonds());
    }

    /// Scenario "A sealed vote not revealed": the flat $5, a miss, to the pool.
    function test_aSealedVoteNotRevealed() public {
        address key = _active(1_250e6);
        panels.recordCounted(key, true, false);
        assertEq(_bond(key), 1_245e6);
        assertEq(reg.progress(key).misses, 1);
        assertEq(reg.poolOwed(), 5e6);
    }

    /// Scenario "An honest mistake": a verdict overturned with a valid receipt isn't slashed. Nothing the consumer
    /// reports about agreement or a reversal touches a bond: only the fault hooks do.
    function test_anHonestMistake() public {
        address key = _active(250e6);
        address shadow = _candidate(100e6);
        panels.verdictOpened(key);
        panels.recordCounted(key, true, true);
        panels.challengeOpened(key);
        panels.challengeClosed(key); // reversed by the challenge panel, no fault proven
        panels.verdictFinal(key);
        panels.recordShadow(shadow, true);
        panels.scoreShadow(shadow, false); // a disagreeing shadow
        assertEq(_bond(key), 250e6);
        assertEq(_bond(shadow), 100e6);
        assertEq(reg.validator(key).slashed, 0);
    }

    function test_mismatchAndAvailabilityFaults() public {
        address key = _active(1_000e6);
        panels.slashFault(key, IValidators.Fault.Availability, address(0));
        assertEq(_bond(key), 800e6); // v2's share: 20 %
        assertEq(reg.poolOwed(), 200e6);
        panels.slashFault(key, IValidators.Fault.Mismatch, stranger);
        assertEq(_bond(key), 0);
        assertEq(reg.owed(stranger), 400e6);
    }

    /// Equivocation, checked by the registry: two contents signed for one subject, the whole bond, once.
    function test_equivocation() public {
        address key = _active(500e6);
        bytes32 subject = keccak256("seal: submission 7, round 0");
        bytes memory a = _statementSig(key, subject, keccak256("pass"));
        bytes memory b = _statementSig(key, subject, keccak256("fail"));
        vm.expectRevert(Validators.NotConflicting.selector);
        reg.proveEquivocation(key, subject, keccak256("pass"), a, keccak256("pass"), a);
        vm.expectRevert(Validators.BadSignature.selector);
        reg.proveEquivocation(genesisKey, subject, keccak256("pass"), a, keccak256("fail"), b);
        vm.expectRevert(Validators.BadSignature.selector); // statements on different subjects aren't equivocation
        reg.proveEquivocation(key, keccak256("other"), keccak256("pass"), a, keccak256("fail"), b);
        vm.prank(stranger);
        reg.proveEquivocation(key, subject, keccak256("pass"), a, keccak256("fail"), b);
        assertEq(_bond(key), 0);
        assertEq(reg.owed(stranger), 250e6);
        _topUp(key, 100e6);
        vm.expectRevert(Validators.AlreadyProven.selector);
        reg.proveEquivocation(key, subject, keccak256("fail"), b, keccak256("pass"), a);
        assertEq(_bond(key), 100e6);
    }

    // ---------- Silence costs a flat amount ----------

    /// Scenario "An honest outage": a counted judge that never seals loses $5 and counts a miss.
    function test_anHonestOutage() public {
        address key = _active(250e6);
        panels.recordCounted(key, false, false);
        assertEq(_bond(key), 245e6);
        assertEq(reg.progress(key).misses, 1);
        assertTrue(reg.isActive(key));
    }

    /// Scenario "Bonds of different sizes": $100 and $1,250 each lose the same $5.
    function test_bondsOfDifferentSizes() public {
        address small = _active(100e6);
        address large = _active(1_250e6);
        panels.recordCounted(small, false, false);
        panels.recordCounted(large, false, false);
        assertEq(_bond(small), 95e6);
        assertEq(_bond(large), 1_245e6);
        assertFalse(reg.isDrawable(small)); // below the floor until topped up
        assertEq(reg.validator(small).slashed, reg.validator(large).slashed);
    }

    /// Scenario "A silent shadow": nothing from its bond; the miss counts toward its qualification's reveal rate.
    function test_aSilentShadow() public {
        address key = _candidate(100e6);
        panels.recordShadow(key, false);
        assertEq(_bond(key), 100e6);
        assertEq(reg.progress(key).shadowDraws, 1);
        assertEq(reg.progress(key).shadowReveals, 0);
        assertEq(reg.poolOwed(), 0);
    }

    /// A slash never exceeds the bond: a flat slash on a bond under $5 takes what's left.
    function test_aFlatSlashStopsAtTheBond() public {
        address key = _active(100e6);
        panels.slashFault(key, IValidators.Fault.FalseVerdict, address(0));
        panels.recordCounted(key, false, false);
        assertEq(_bond(key), 0);
        assertEq(reg.validator(key).slashed, 100e6);
    }

    // ---------- Leaving with an unbonding delay ----------

    /// Scenario "Leave, then a fault is proven": slashed during the delay as if active; the rest withdrawable after.
    function test_leaveThenAFaultIsProven() public {
        address key = _active(500e6);
        address op = reg.validator(key).operator;
        bytes32 subject = keccak256("reveal: submission 3");
        bytes memory a = _statementSig(key, subject, keccak256("x"));
        bytes memory b = _statementSig(key, subject, keccak256("y"));
        panels.verdictOpened(key);
        vm.prank(key);
        reg.leave(key);
        assertFalse(reg.isDrawable(key));
        assertEq(reg.eligibleCount(10e6), 1);
        panels.slashFault(key, IValidators.Fault.Availability, address(0)); // 20 %
        assertEq(_bond(key), 400e6);
        panels.verdictFinal(key);
        vm.warp(block.timestamp + 504 hours - 1);
        vm.expectRevert(Validators.TooEarly.selector);
        reg.withdraw(key);
        reg.proveEquivocation(key, subject, keccak256("x"), a, keccak256("y"), b);
        vm.warp(block.timestamp + 1);
        reg.withdraw(key);
        assertEq(usd.balanceOf(op), 0); // the whole bond was taken
        assertEq(uint256(_state(key)), uint256(IValidators.State.Exited));
    }

    function test_leaveAndWithdrawWhatRemains() public {
        address key = _active(500e6);
        address op = reg.validator(key).operator;
        panels.recordCounted(key, true, false); // $5
        vm.prank(op);
        reg.leave(key);
        _fund(stranger, 1e6);
        vm.prank(stranger);
        vm.expectRevert(Validators.WrongState.selector);
        reg.topUp(key, 1e6);
        vm.warp(block.timestamp + 504 hours);
        vm.prank(stranger); // anyone triggers it; the operator is paid
        reg.withdraw(key);
        assertEq(usd.balanceOf(op), 495e6);
        vm.expectRevert(Validators.WrongState.selector);
        reg.withdraw(key);
        vm.prank(op);
        vm.expectRevert(Validators.WrongState.selector);
        reg.leave(key);
    }

    /// Scenario "Leave while a challenge waits": the bond stays locked past the delay until the challenge is judged,
    /// and is slashed if it's upheld; every verdict must be final too.
    function test_leaveWhileAChallengeWaits() public {
        address key = _active(500e6);
        panels.verdictOpened(key);
        panels.verdictOpened(key);
        panels.challengeOpened(key);
        vm.prank(key);
        reg.leave(key);
        vm.warp(block.timestamp + 600 hours);
        vm.expectRevert(Validators.Locked.selector);
        reg.withdraw(key);
        panels.verdictFinal(key);
        panels.verdictFinal(key);
        vm.expectRevert(Validators.Locked.selector); // the frozen challenge still waits
        reg.withdraw(key);
        panels.slashFault(key, IValidators.Fault.FalseVerdict, stranger); // upheld
        panels.challengeClosed(key);
        reg.withdraw(key);
        assertEq(reg.validator(key).bond, 0);
        assertEq(reg.owed(stranger), 250e6);
    }

    function test_aCandidateMayLeave() public {
        address key = _candidate(100e6);
        vm.prank(stranger);
        vm.expectRevert(Validators.NotAllowed.selector);
        reg.leave(key);
        vm.prank(key);
        reg.leave(key);
        assertEq(reg.candidateCount(), 0);
        assertFalse(reg.canShadow(key));
        // hooks on a leaving validator are no-ops for qualification, and it's never activated
        _qualify(key);
        assertEq(uint256(_state(key)), uint256(IValidators.State.Leaving));
    }

    // ---------- One party's presence is capped; each attestation scheme is its own TEE type ----------

    /// Scenario "Ten nodes on one cloud" and "Too few distinct hosts", the registry's side: every validator's host is
    /// recorded for the draw's caps (Panels, 3.2), and the counters count every drawable validator; the caps then
    /// lower k in the draw.
    function test_tenNodesOnOneCloud() public {
        address party = makeAddr("one party");
        for (uint256 i; i < 10; ++i) {
            address key = _nextKey();
            _register(_reg(key, party, keccak256("one cloud"), FAMILY_A), 100e6, party);
            _qualify(key);
            assertEq(reg.validator(key).host, keccak256("one cloud"));
            assertEq(reg.validator(key).operator, party);
        }
        assertEq(reg.eligibleCount(50e6), 11);
    }

    /// Scenarios "Two technologies from one vendor", "One technology in two clouds" and "A confidential GPU", the
    /// registry's side: SGX and TDX are two TEE types (SGX not on the launch list); TDX in two clouds is one type on
    /// two hosts; a GPU isn't a type, so its validator registers under its CPU's.
    function test_eachAttestationSchemeIsItsOwnType() public {
        assertTrue(reg.acceptedTeeType(TDX));
        assertFalse(reg.acceptedTeeType(SGX));
        address a = _nextKey();
        address b = _nextKey();
        _register(_reg(a, stranger, keccak256("cloud-1"), FAMILY_A), 100e6, stranger);
        _register(_reg(b, stranger, keccak256("cloud-2"), FAMILY_B), 100e6, stranger);
        assertEq(reg.validator(a).teeType, reg.validator(b).teeType);
        assertTrue(reg.validator(a).host != reg.validator(b).host);
        address gpu = _nextKey();
        IValidators.Registration memory r = _reg(gpu, stranger, keccak256("cloud-3"), FAMILY_A);
        r.teeType = keccak256("nvidia-cc-gpu");
        _expectRegisterRevert(r, Validators.TeeTypeNotAccepted.selector);
        r.teeType = SEV_SNP;
        _register(r, 100e6, stranger);
        assertEq(reg.validator(gpu).teeType, SEV_SNP);
    }

    // ---------- At most one genesis validator, so the network can start ----------

    /// Scenario "A launch with one validator": active from the start, drawable at k = 1, with candidates to shadow.
    function test_aLaunchWithOneValidator() public {
        IValidators.Validator memory v = reg.validator(genesisKey);
        assertTrue(v.genesis);
        assertEq(uint256(v.state), uint256(IValidators.State.Active));
        assertEq(reg.genesisKey(), genesisKey);
        assertEq(reg.activeCount(), 1);
        assertEq(reg.eligibleCount(50e6), 1);
        assertEq(reg.eligibleCount(625e6), 1); // $1,250 covers the largest tier
        assertEq(reg.eligibleAt(50e6, 0), genesisKey);
        assertEq(v.bond, 1_250e6);
        assertEq(usd.balanceOf(address(reg)), 1_250e6);
        address c = _candidate(100e6);
        assertTrue(reg.canShadow(c));
    }

    /// Scenario "Two genesis validators".
    function test_twoGenesisValidators() public {
        IValidators.Registration[] memory gs = new IValidators.Registration[](2);
        gs[0] = _reg(_nextKey(), stranger, keccak256("h1"), FAMILY_A);
        gs[1] = _reg(_nextKey(), stranger, keccak256("h2"), FAMILY_B);
        Validators.Genesis memory g = _genesis(false, gs, 100e6);
        vm.expectRevert(Validators.BadParams.selector);
        _create(g);
    }

    /// Scenario "A genesis on an ordinary PC": a level C (zkTLS) genesis is refused; so is an unbonded or unsigned one.
    function test_aGenesisOnAnOrdinaryPc() public {
        IValidators.Registration[] memory gs = new IValidators.Registration[](1);
        gs[0] = _zk(_nextKey());
        Validators.Genesis memory g = _genesis(false, gs, 100e6);
        vm.expectRevert(Validators.ProofTypeNotAccepted.selector);
        _create(g);
        gs[0] = _reg(_nextKey(), stranger, keccak256("h"), FAMILY_A);
        g = _genesis(false, gs, 99e6);
        vm.expectRevert(Validators.BondTooSmall.selector);
        _create(g);
        g = _genesis(false, gs, 100e6);
        g.signatures[0] = _signDigest(genesisKey, bytes32(uint256(1)));
        vm.expectRevert(Validators.BadSignature.selector);
        _create(g);
    }

    function test_aLaunchWithNoGenesis() public {
        Validators v = _create(_genesis(false, new IValidators.Registration[](0), 0));
        assertEq(v.activeCount(), 0);
        assertEq(v.genesisKey(), address(0));
        assertEq(v.eligibleCount(10e6), 0);
    }

    function test_badGenesisLists() public {
        Validators.Genesis memory g = _genesis(false, new IValidators.Registration[](0), 0);
        g.images = new bytes32[](0);
        vm.expectRevert(Validators.BadParams.selector);
        _create(g);
        g = _genesis(false, new IValidators.Registration[](0), 0);
        g.teeTypes[0] = bytes32(0);
        vm.expectRevert(Validators.BadParams.selector);
        _create(g);
        g = _genesis(false, new IValidators.Registration[](0), 0);
        g.pool = address(0);
        vm.expectRevert(Validators.BadParams.selector);
        _create(g);
    }

    // ---------- tiers ----------

    function test_tiers() public view {
        assertEq(reg.tierOf(0), 0);
        assertEq(reg.tierOf(10e6), 0);
        assertEq(reg.tierOf(10e6 + 1), 1);
        assertEq(reg.tierOf(50e6), 2);
        assertEq(reg.tierOf(312_500_000), 5);
        assertEq(reg.tierOf(312_500_001), 6);
        assertEq(reg.tierOf(625e6), 6);
        assertEq(reg.eligibleCount(625e6 + 1), 0);
    }

    function test_aBountyAboveTheLargestTier() public {
        vm.expectRevert(Validators.BountyTooLarge.selector);
        reg.tierOf(625e6 + 1);
        vm.expectRevert(Validators.BountyTooLarge.selector);
        reg.eligibleAt(625e6 + 1, 0);
        vm.expectRevert(Validators.OutOfRange.selector);
        reg.eligibleAt(625e6, 1);
    }

    function test_bondTiersFollowTheBond() public {
        address a = _active(250e6); // covers $125
        address b = _active(625e6); // covers $312.50
        assertEq(reg.eligibleCount(125e6), 3);
        assertEq(reg.eligibleCount(250e6), 2);
        assertEq(reg.eligibleCount(312_500_000), 2);
        assertEq(reg.eligibleCount(625e6), 1);
        _topUp(a, 1_000e6);
        assertEq(reg.eligibleCount(625e6), 2);
        panels.recordCounted(b, false, false); // $620: back to $250's tier
        assertEq(reg.eligibleCount(312_500_000), 2);
        assertEq(reg.eligibleCount(250e6), 3);
    }

    // ---------- helpers ----------

    function _zk(address key) internal view returns (IValidators.Registration memory r) {
        r = _reg(key, stranger, keccak256("a home PC"), FAMILY_A);
        r.proofType = keccak256("zktls");
        r.teeType = bytes32(0);
        r.level = 0;
        r.attestation = bytes32(0);
    }

    function _fund(address who, uint256 amount) internal {
        usd.mint(who, amount);
        vm.prank(who);
        usd.approve(address(reg), amount);
    }

    function _topUp(address key, uint256 amount) internal {
        _fund(stranger, amount);
        vm.prank(stranger);
        reg.topUp(key, amount);
    }

    function _expectRegisterRevert(IValidators.Registration memory r, bytes4 sel) internal {
        bytes memory sig = _sign(reg, r.key, r);
        _fund(stranger, 100e6);
        vm.prank(stranger);
        vm.expectRevert(sel);
        reg.register(r, 100e6, sig);
    }
}
