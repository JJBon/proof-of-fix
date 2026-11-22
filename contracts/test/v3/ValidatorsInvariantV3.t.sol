// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Validators} from "../../src/v3/Validators.sol";
import {IValidators} from "../../src/v3/IValidators.sol";
import {ValidatorsSetup, TDX, SEV_SNP, NITRO, FAMILY_A, FAMILY_B} from "./helpers/ValidatorsSetup.sol";
import {ValidatorsHandler} from "./helpers/ValidatorsHandler.sol";

/// The registry's counters against a full recount (design D2: the tier counters are kept on every change, so k is
/// read without a pass over the registry; a recount must always agree). And L5 (#251): `activeCount` never counts a
/// validator below the bond floor; every Active validator is bonded at least BOND_FLOOR, every BelowFloor one below it.
abstract contract Recount is ValidatorsSetup {
    function _assertRecount() internal view {
        uint256[7] memory eligible;
        uint256 active;
        uint256 candidates;
        uint256 n = reg.validatorCount();
        for (uint256 i; i < n; ++i) {
            address key = reg.validatorAt(i);
            IValidators.Validator memory v = reg.validator(key);
            bool drawable = v.state == IValidators.State.Active && v.bond >= reg.BOND_FLOOR();
            assertEq(reg.isDrawable(key), drawable, "isDrawable");
            if (v.state == IValidators.State.Active) {
                ++active;
                assertGe(v.bond, reg.BOND_FLOOR(), "Active below the floor");
                assertTrue(reg.isActive(key), "isActive");
            }
            if (v.state == IValidators.State.BelowFloor) {
                assertLt(v.bond, reg.BOND_FLOOR(), "BelowFloor at the floor");
                assertFalse(reg.isActive(key), "a BelowFloor validator counted active");
            }
            if (v.state == IValidators.State.Candidate) ++candidates;
            if (!drawable) continue;
            for (uint256 t; t < 7; ++t) {
                if (v.bond >= 2 * reg.tierStep(t)) ++eligible[t];
            }
        }
        assertEq(reg.activeCount(), active, "activeCount");
        assertEq(reg.candidateCount(), candidates, "candidateCount");
        for (uint256 t; t < 7; ++t) {
            uint256 step = reg.tierStep(t);
            assertEq(reg.eligibleCount(step), eligible[t], "tier counter");
            // every indexed validator is eligible for the tier, and none twice
            for (uint256 j; j < eligible[t]; ++j) {
                address a = reg.eligibleAt(step, j);
                assertTrue(reg.isDrawable(a), "indexed but not drawable");
                assertGe(reg.validator(a).bond, 2 * step, "indexed below the tier");
                for (uint256 k; k < j; ++k) {
                    assertTrue(reg.eligibleAt(step, k) != a, "indexed twice");
                }
            }
        }
        // the buckets add up to the lowest tier's counter
        bytes32[] memory gs = reg.groups();
        uint256 sum;
        for (uint256 g; g < gs.length; ++g) {
            for (uint256 b; b < 7; ++b) {
                sum += reg.bucketSize(gs[g], b);
            }
        }
        assertEq(sum, eligible[0], "buckets");
        uint256 cs = reg.candidateCount();
        for (uint256 i; i < cs; ++i) {
            assertEq(uint256(reg.validator(reg.candidateAt(i)).state), uint256(IValidators.State.Candidate));
        }
    }
}

contract ValidatorsCountersV3Test is Recount {
    address internal genesisKey;

    function setUp() public {
        _deployCoinAndPool();
        genesisKey = _newKey("genesis");
        _deploy(genesisKey);
    }

    /// Fuzz: any sequence of registrations, qualifications, top-ups, misses, faults, suspensions and leavings leaves
    /// the tier counters equal to a full recount.
    function testFuzz_tierCountersEqualAFullRecount(uint256[32] calldata ops) public {
        address[] memory ks = new address[](7);
        ks[0] = genesisKey;
        for (uint256 i; i < ops.length; ++i) {
            uint256 op = ops[i];
            address key = ks[(op >> 8) % 7];
            uint256 kind = op % 9;
            if (kind == 0 || key == address(0)) {
                uint256 slot = 1 + (op >> 16) % 6;
                if (ks[slot] != address(0)) continue;
                ks[slot] = _nextKey();
                IValidators.Registration memory r =
                    _reg(ks[slot], makeAddr("op"), keccak256(abi.encode(op % 3)), op % 2 == 0 ? FAMILY_A : FAMILY_B);
                r.teeType = (op >> 24) % 3 == 0 ? TDX : (op >> 24) % 3 == 1 ? SEV_SNP : NITRO;
                _register(r, bound(op >> 32, 100e6, 1_500e6), address(this));
            } else if (kind == 1) {
                _qualify(key);
            } else if (kind == 2) {
                uint256 amount = bound(op >> 32, 1, 900e6);
                usd.mint(address(this), amount);
                usd.approve(address(reg), amount);
                try reg.topUp(key, amount) {} catch {}
            } else if (kind == 3) {
                panels.recordCounted(key, (op >> 40) % 2 == 0, false);
            } else if (kind == 4) {
                for (uint256 m; m < 6; ++m) {
                    panels.recordCounted(key, false, false); // suspended
                }
            } else if (kind == 5) {
                panels.slashFault(key, IValidators.Fault((op >> 40) % 3), address(0));
            } else if (kind == 6) {
                vm.prank(key);
                try reg.leave(key) {} catch {}
            } else if (kind == 7) {
                vm.warp(block.timestamp + 600 hours);
                try reg.withdraw(key) {} catch {}
            } else {
                panels.recordCounted(key, true, true);
            }
        }
        _assertRecount();
    }
}

/// #85 5.8's invariant for v3: no slash exceeds a validator's bond, and none follows a mere disagreement. Also: every
/// validator's bond, slashes and withdrawals add up to what it deposited; the registry holds exactly the bonds, the
/// challengers' shares and the pool's; the counters equal a full recount.
contract ValidatorsInvariantV3Test is Recount {
    ValidatorsHandler internal handler;

    function setUp() public {
        _deployCoinAndPool();
        address genesisKey = _newKey("genesis");
        _deploy(genesisKey);
        handler = new ValidatorsHandler(reg, panels, usd, genesisKey);
        targetContract(address(handler));
    }

    function invariant_noSlashExceedsTheBondOrFollowsADisagreement() public view {
        assertEq(handler.disagreementSlashes(), 0);
        assertEq(handler.slashesAboveBond(), 0);
        uint256 n = handler.keyCount_();
        for (uint256 i; i < n; ++i) {
            address key = handler.keys(i);
            IValidators.Validator memory v = reg.validator(key);
            // only the faults the handler reported slashed, each by what D16 names, capped by the bond
            assertEq(v.slashed, handler.expectedSlashed(key));
            assertEq(uint256(v.bond) + v.slashed + handler.withdrawn(key), handler.deposited(key));
            assertLe(v.slashed, handler.deposited(key));
        }
    }

    function invariant_theRegistryHoldsWhatItOwes() public view {
        assertEq(usd.balanceOf(address(reg)), reg.totalBonds() + reg.totalOwed() + reg.poolOwed());
    }

    function invariant_countersEqualARecount() public view {
        _assertRecount();
    }
}
