// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Validators} from "../../../src/v3/Validators.sol";
import {IValidators} from "../../../src/v3/IValidators.sol";
import {Pool} from "../../../src/v2/Pool.sol";
import {MockCoin} from "../../mocks/MockCoin.sol";
import {ValidatorsSetup, PanelsHarness, TDX, SEV_SNP, NITRO, FAMILY_A, FAMILY_B} from "./ValidatorsSetup.sol";

/// Random runs over the registry (task 3.1): registrations, top-ups, shadow and counted draws, scores, verdicts and
/// challenges opened and closed, faults, equivocations, leaving, withdrawals and time. The handler keeps what each
/// validator deposited and withdrew, and what the faults it reported should have slashed; disagreements (a shadow
/// scored as disagreeing, a counted verdict revealed, a challenge closed with no fault) are checked to slash nothing.
contract ValidatorsHandler is ValidatorsSetup {
    uint256 internal constant KEYS = 8;
    address[] public keys; // the genesis key, then KEYS candidates-to-be
    mapping(address => uint256) public deposited;
    mapping(address => uint256) public withdrawn;
    mapping(address => uint256) public expectedSlashed;
    uint256 public disagreementSlashes; // must stay 0
    uint256 public slashesAboveBond; // must stay 0
    uint256 public calls;

    constructor(Validators reg_, PanelsHarness panels_, MockCoin usd_, address genesisKey) {
        reg = reg_;
        panels = panels_;
        usd = usd_;
        keys.push(genesisKey);
        deposited[genesisKey] = reg_.validator(genesisKey).bond;
        _newKey("genesis"); // the same name, so the same key and secret as the test's
        for (uint256 i; i < KEYS; ++i) {
            keys.push(_newKey(string.concat("handler-key", vm.toString(i))));
        }
    }

    function keyCount_() external view returns (uint256) {
        return keys.length;
    }

    /// A registered key (the genesis one at least), from the seed.
    function _pick(uint256 seed) internal view returns (address) {
        uint256 n = keys.length;
        for (uint256 i; i < n; ++i) {
            address k = keys[(seed + i) % n];
            if (reg.validator(k).state != IValidators.State.None) return k;
        }
        return keys[0];
    }

    function _any(uint256 seed) internal view returns (address) {
        return keys[seed % keys.length];
    }

    // ---------- actions ----------

    function register(uint256 seed, uint256 bond, uint8 tee, bool levelB) external {
        address key = _any(seed);
        if (reg.validator(key).state != IValidators.State.None) return;
        bond = bound(bond, 100e6, 1_500e6);
        IValidators.Registration memory r =
            _reg(key, makeAddr(string.concat("handler-op", vm.toString(seed % 3))), keccak256(abi.encode(seed % 4)), seed % 2 == 0 ? FAMILY_A : FAMILY_B);
        r.teeType = tee % 3 == 0 ? TDX : tee % 3 == 1 ? SEV_SNP : NITRO;
        r.level = levelB ? 2 : 1;
        _register(r, bond, address(this));
        deposited[key] += bond;
        ++calls;
    }

    function topUp(uint256 seed, uint256 amount) external {
        address key = _pick(seed);
        IValidators.State st = reg.validator(key).state;
        if (st != IValidators.State.Candidate && st != IValidators.State.Active) return;
        amount = bound(amount, 1, 700e6);
        usd.mint(address(this), amount);
        usd.approve(address(reg), amount);
        reg.topUp(key, amount);
        deposited[key] += amount;
        ++calls;
    }

    /// A shadow draw's deadline, and its score when revealed: a disagreement never slashes.
    function shadow(uint256 seed, bool revealed, bool agreed) external {
        address key = _pick(seed);
        uint256 before = reg.validator(key).slashed;
        panels.recordShadow(key, revealed);
        if (revealed) panels.scoreShadow(key, agreed);
        if (reg.validator(key).slashed != before) ++disagreementSlashes;
        ++calls;
    }

    /// Qualifies a candidate quickly (20 agreeing shadow verdicts), so runs reach active validators.
    function qualify(uint256 seed) external {
        address key = _pick(seed);
        for (uint256 i; i < 20; ++i) {
            panels.recordShadow(key, true);
            panels.scoreShadow(key, true);
        }
        ++calls;
    }

    /// A counted draw's deadline: revealed (agreeing or not, it's never a fault) or missed (the flat slash).
    function counted(uint256 seed, bool hasSeal, bool revealed) external {
        address key = _pick(seed);
        uint256 bond = reg.validator(key).bond;
        uint256 slashedBefore = reg.validator(key).slashed;
        panels.recordCounted(key, hasSeal, revealed);
        uint256 took = reg.validator(key).slashed - slashedBefore;
        if (revealed) {
            if (took != 0) ++disagreementSlashes;
        } else {
            uint256 want = bond < 5e6 ? bond : 5e6;
            expectedSlashed[key] += want;
        }
        if (took > bond) ++slashesAboveBond;
        ++calls;
    }

    function verdict(uint256 seed, bool open) external {
        address key = _pick(seed);
        uint256 before = reg.validator(key).slashed;
        if (open) panels.verdictOpened(key);
        else panels.verdictFinal(key);
        if (reg.validator(key).slashed != before) ++disagreementSlashes;
        ++calls;
    }

    /// A challenge opened, or closed with no fault proven (a reversal by the challenge panel is a disagreement).
    function challenge(uint256 seed, bool open) external {
        address key = _pick(seed);
        uint256 before = reg.validator(key).slashed;
        if (open) panels.challengeOpened(key);
        else panels.challengeClosed(key);
        if (reg.validator(key).slashed != before) ++disagreementSlashes;
        ++calls;
    }

    function fault(uint256 seed, uint8 kind, bool withChallenger) external {
        address key = _pick(seed);
        uint256 bond = reg.validator(key).bond;
        IValidators.Fault f = IValidators.Fault(kind % 3);
        uint256 bps = f == IValidators.Fault.Availability ? 2_000 : 10_000;
        panels.slashFault(key, f, withChallenger ? makeAddr("handler-challenger") : address(0));
        uint256 took = bond - reg.validator(key).bond;
        expectedSlashed[key] += bond * bps / 10_000;
        if (took > bond) ++slashesAboveBond;
        ++calls;
    }

    function equivocate(uint256 seed, uint256 subjectSeed) external {
        address key = _pick(seed);
        bytes32 subject = keccak256(abi.encode(subjectSeed % 5));
        uint256 bond = reg.validator(key).bond;
        bytes memory a = _signDigest(key, reg.statementDigest(subject, "a"));
        bytes memory b = _signDigest(key, reg.statementDigest(subject, "b"));
        reg.proveEquivocation(key, subject, "a", a, "b", b);
        expectedSlashed[key] += bond;
        ++calls;
    }

    function leave(uint256 seed) external {
        address key = _pick(seed);
        vm.prank(key);
        reg.leave(key);
        ++calls;
    }

    function withdraw(uint256 seed) external {
        address key = _pick(seed);
        uint256 bond = reg.validator(key).bond;
        reg.withdraw(key);
        withdrawn[key] += bond;
        ++calls;
    }

    function warp(uint256 dt) external {
        vm.warp(block.timestamp + bound(dt, 1 hours, 30 days));
        ++calls;
    }
}
