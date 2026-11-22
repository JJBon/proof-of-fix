// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {console} from "forge-std/console.sol";
import {Validators} from "../../src/v3/Validators.sol";
import {IValidators} from "../../src/v3/IValidators.sol";
import {ValidatorsSetup, FAMILY_A, FAMILY_B} from "./helpers/ValidatorsSetup.sol";

/// proof-of-fix#251, design L11 condition 1 (owner, 2026-11-20): each validator's Radicle node key is a signed field of
/// its v3 registration, stored on-chain and readable by anyone (specs/radicle-hosting, "A seat maps to one Radicle
/// node key on-chain"). 0 registers no node (the seat is never counted as a delegate); a node key another registration
/// that isn't leaving or exited holds is refused; there is no setter.
contract RadNodeV3Test is ValidatorsSetup {
    address internal genesisKey;
    address internal stranger = makeAddr("stranger");

    event Registered(
        address indexed key,
        address indexed operator,
        bool genesis,
        uint8 level,
        uint256 bond,
        IValidators.Registration r,
        bytes32 indexed radNode
    );

    function setUp() public {
        _deployCoinAndPool();
        genesisKey = _newKey("genesis");
        _deploy(genesisKey);
    }

    /// The genesis validator's node key is in its record, signed with the rest of its registration.
    function test_theGenesisRecordsItsNode() public view {
        assertEq(reg.radNodeOf(genesisKey), radNodeFor(genesisKey));
        assertEq(reg.validator(genesisKey).radNode, radNodeFor(genesisKey));
    }

    /// Scenario "A seat maps to one Radicle node key on-chain": the key is stored, readable by anyone, and announced
    /// by the `Registered` event (its third topic).
    function test_aRegistrationRecordsItsNode() public {
        address key = _nextKey();
        bytes32 node = keccak256("an Ed25519 public key");
        IValidators.Registration memory r = _reg(key, stranger, keccak256("h"), FAMILY_A);
        r.radNode = node;
        bytes memory sig = _sign(reg, key, r);
        _fund(stranger, 100e6);
        vm.expectEmit(address(reg));
        emit Registered(key, stranger, false, 1, 100e6, r, node);
        vm.prank(stranger);
        reg.register(r, 100e6, sig);
        assertEq(reg.radNodeOf(key), node);
        assertEq(reg.validator(key).radNode, node);
        assertEq(reg.radNodeOf(makeAddr("never registered")), bytes32(0));
    }

    /// The node key is signed: a signature over another node key (or none) is refused.
    function test_theNodeKeyIsSigned() public {
        address key = _nextKey();
        IValidators.Registration memory r = _reg(key, stranger, keccak256("h"), FAMILY_A);
        bytes memory sig = _sign(reg, key, r);
        r.radNode = keccak256("another node");
        _fund(stranger, 100e6);
        vm.prank(stranger);
        vm.expectRevert(Validators.BadSignature.selector);
        reg.register(r, 100e6, sig);
        r.radNode = bytes32(0);
        vm.prank(stranger);
        vm.expectRevert(Validators.BadSignature.selector);
        reg.register(r, 100e6, sig);
        assertEq(reg.registrationDigest(r), _registrationDigest(address(reg), r));
    }

    /// Scenario "A seated validator without a node ID": 0 is allowed, for as many validators as register so. The
    /// registry records no node for them; the off-chain rules leave such a seat out of the delegates.
    function test_noNodeIsAllowed() public {
        address a = _nextKey();
        address b = _nextKey();
        IValidators.Registration memory r = _reg(a, stranger, keccak256("h"), FAMILY_A);
        r.radNode = bytes32(0);
        _register(r, 100e6, stranger);
        r = _reg(b, stranger, keccak256("h2"), FAMILY_B);
        r.radNode = bytes32(0);
        _register(r, 100e6, stranger);
        assertEq(reg.radNodeOf(a), bytes32(0));
        assertEq(reg.radNodeOf(b), bytes32(0));
        _qualify(a);
        assertTrue(reg.isDrawable(a)); // it may still be drawn and judge
    }

    /// Two seats never share a node: a key held by a candidate, an active validator, the genesis validator or one
    /// below the floor is refused.
    function test_aNodeHeldByAnotherIsRefused() public {
        address cand = _candidate(100e6);
        _expectNodeTaken(radNodeFor(cand));
        address act = _active(100e6);
        _expectNodeTaken(radNodeFor(act));
        _expectNodeTaken(radNodeFor(genesisKey));
        panels.recordCounted(act, false, false); // silent: slashed below the floor (L5)
        assertEq(uint256(_state(act)), uint256(IValidators.State.BelowFloor));
        _expectNodeTaken(radNodeFor(act));
    }

    /// Changing a node is registering again: the old registration leaves, which frees its node key, and a new key
    /// registers with it (or with another node). A leaving or exited validator holds no node.
    function test_aNodeIsFreedWhenItsValidatorLeaves() public {
        address old = _active(100e6);
        bytes32 node = radNodeFor(old);
        _expectNodeTaken(node);
        vm.prank(old);
        reg.leave(old);
        address moved = _nextKey();
        IValidators.Registration memory r = _reg(moved, stranger, keccak256("moved"), FAMILY_A);
        r.radNode = node;
        _register(r, 100e6, stranger);
        assertEq(reg.radNodeOf(moved), node);
        assertEq(reg.radNodeOf(old), node); // the old record still says what it registered
        _expectNodeTaken(node); // held again, by the new registration
    }

    /// Registering again: the same validator key can't register twice (KeyTaken, unchanged: a registration is never
    /// rewritten); a validator moving to a new node leaves and registers a new key with the new node, after which its
    /// old node key is free for anyone, and the new one is held.
    function test_registeringAgainWithANewNode() public {
        address old = _active(100e6);
        bytes32 oldNode = radNodeFor(old);
        // the same key again, even with its own node: refused as a key already registered, not as a node
        IValidators.Registration memory r = _reg(old, stranger, keccak256("again"), FAMILY_A);
        bytes memory sig = _sign(reg, old, r);
        _fund(stranger, 100e6);
        vm.prank(stranger);
        vm.expectRevert(Validators.KeyTaken.selector);
        reg.register(r, 100e6, sig);
        // a new key on a new node, after leaving with the old one
        vm.prank(old);
        reg.leave(old);
        address moved = _nextKey();
        bytes32 newNode = keccak256("the validator's new node");
        r = _reg(moved, stranger, keccak256("moved"), FAMILY_A);
        r.radNode = newNode;
        _register(r, 100e6, stranger);
        assertEq(reg.radNodeOf(moved), newNode);
        _expectNodeTaken(newNode);
        // the old node is free: another registration may take it
        address other = _nextKey();
        r = _reg(other, stranger, keccak256("other"), FAMILY_B);
        r.radNode = oldNode;
        _register(r, 100e6, stranger);
        assertEq(reg.radNodeOf(other), oldNode);
    }

    /// A seat registered without a node is drawable, and the registry reports no node for it: radNodeOf is 0, which
    /// the node's chain view (oracle/delegates.py ChainSeatNodes) reports as unmapped, never as a delegate.
    function test_aSeatWithoutANodeReadsAsNone() public {
        address key = _nextKey();
        IValidators.Registration memory r = _reg(key, stranger, keccak256("no node"), FAMILY_A);
        r.radNode = bytes32(0);
        _register(r, 100e6, stranger);
        _qualify(key);
        assertTrue(reg.isDrawable(key));
        assertEq(reg.radNodeOf(key), bytes32(0));
        assertEq(reg.validator(key).radNode, bytes32(0));
        // and 0 is never held: a second seat without a node registers too
        address second = _nextKey();
        r = _reg(second, stranger, keccak256("no node 2"), FAMILY_B);
        r.radNode = bytes32(0);
        _register(r, 100e6, stranger);
        assertEq(reg.radNodeOf(second), bytes32(0));
    }

    /// Distinct nonzero keys register side by side; the same one twice never does.
    function testFuzz_oneSeatPerNode(bytes32 a, bytes32 b) public {
        vm.assume(a != bytes32(0) && b != bytes32(0) && a != radNodeFor(genesisKey) && b != radNodeFor(genesisKey));
        address ka = _nextKey();
        IValidators.Registration memory r = _reg(ka, stranger, keccak256("ha"), FAMILY_A);
        r.radNode = a;
        _register(r, 100e6, stranger);
        address kb = _nextKey();
        r = _reg(kb, stranger, keccak256("hb"), FAMILY_B);
        r.radNode = b;
        if (a == b) {
            bytes memory sig = _sign(reg, kb, r);
            _fund(stranger, 100e6);
            vm.prank(stranger);
            vm.expectRevert(Validators.NodeTaken.selector);
            reg.register(r, 100e6, sig);
        } else {
            _register(r, 100e6, stranger);
            assertEq(reg.radNodeOf(kb), b);
        }
        assertEq(reg.radNodeOf(ka), a);
    }

    /// Gas: a registration with a node key (one more signed word, two more storage slots: the record's and the
    /// holder's, and the event's third topic) against one without, after a first registration warms the shared slots.
    function test_gasRegister() public {
        _gasOfRegister(keccak256("a first node"));
        uint256 without = _gasOfRegister(bytes32(0));
        uint256 with_ = _gasOfRegister(keccak256("a node"));
        console.log("Validators.register with a node key:", with_);
        console.log("Validators.register without one:", without);
        assertGt(with_, without);
        assertLt(with_ - without, 50_000);
    }

    // ---------- helpers ----------

    function _gasOfRegister(bytes32 node) internal returns (uint256 used) {
        address key = _nextKey();
        IValidators.Registration memory r = _reg(key, stranger, keccak256(abi.encode("gas", key)), FAMILY_A);
        r.radNode = node;
        bytes memory sig = _sign(reg, key, r);
        _fund(stranger, 100e6);
        vm.prank(stranger);
        uint256 g = gasleft();
        reg.register(r, 100e6, sig);
        used = g - gasleft();
    }

    function _fund(address who, uint256 amount) internal {
        usd.mint(who, amount);
        vm.prank(who);
        usd.approve(address(reg), amount);
    }

    /// A fresh key registering with `node` is refused (NodeTaken).
    function _expectNodeTaken(bytes32 node) internal {
        address key = _nextKey();
        IValidators.Registration memory r = _reg(key, stranger, keccak256(abi.encode("host", key)), FAMILY_A);
        r.radNode = node;
        bytes memory sig = _sign(reg, key, r);
        _fund(stranger, 100e6);
        vm.prank(stranger);
        vm.expectRevert(Validators.NodeTaken.selector);
        reg.register(r, 100e6, sig);
    }
}
