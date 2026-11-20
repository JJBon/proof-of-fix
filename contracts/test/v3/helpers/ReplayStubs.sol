// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {IValidators} from "../../../src/v3/IValidators.sol";
import {Status, Kind, Submission, Panel, Seat} from "../../../src/v3/PanelsBase.sol";

/// The registry as the replay needs it (task 3.5): the active validators the simulation had at each period's close, and
/// each one's family. A validator is its own operator (paid at its key). Statements are signed over a plain digest.
contract ReplayRegistry {
    mapping(address => bool) public isActive;
    mapping(address => bytes32) public familyOf;
    address[] internal _active;

    function setFamily(address key, bytes32 family) external {
        familyOf[key] = family;
    }

    /// The active set, replaced whole.
    function setActive(address[] calldata keys) external {
        for (uint256 i; i < _active.length; ++i) {
            isActive[_active[i]] = false;
        }
        _active = keys;
        for (uint256 i; i < keys.length; ++i) {
            isActive[keys[i]] = true;
        }
    }

    function activeCount() external view returns (uint256) {
        return _active.length;
    }

    function validator(address key) external view returns (IValidators.Validator memory v) {
        v.key = key;
        v.operator = key;
        v.family = familyOf[key];
        v.state = isActive[key] ? IValidators.State.Active : IValidators.State.Candidate;
    }

    function statementDigest(bytes32 subject, bytes32 content) external pure returns (bytes32) {
        return keccak256(abi.encode(subject, content));
    }
}

/// Panels as the replay scripts it: the simulation draws its own panels (from its own seeds; the contract would draw
/// from block hashes the simulation can't know), so each panel the simulation paid is set here as it was: its kind, its
/// judges (each revealed with a receipt), and its submission's status. RaceV3 and FeesV3 are the real contracts.
contract ReplayPanels {
    uint256 public constant BOUNTY_MAX = 625e6;
    uint256 public constant APPEAL_WINDOW = 72 hours; // the production windows' (#251 batch 3)
    uint256 public constant ACTIVE_WINDOW = 26 weeks;
    address public immutable fees;
    address public immutable coin;
    address public immutable pool;
    address public immutable validators;
    address public race;
    uint256 public panelCount;
    mapping(uint256 => Submission) internal _subs;
    mapping(uint256 => Panel) internal _panels;
    mapping(uint256 => address[]) internal _keys;

    constructor(address fees_, address coin_, address pool_, address validators_) {
        fees = fees_;
        coin = coin_;
        pool = pool_;
        validators = validators_;
    }

    function bind() external {
        race = msg.sender;
    }

    function open(uint256 id, bytes32 commitment, uint256 bounty) external {
        _subs[id].commitment = commitment;
        _subs[id].bounty = uint128(bounty);
        _subs[id].status = Status.Sealed;
    }

    function openHidden(uint256 id, bytes32 commitment, uint256 bounty) external {
        this.open(id, commitment, bounty);
        _subs[id].teeOnly = true;
    }

    function withdraw(uint256 id) external {
        _subs[id].status = Status.Withdrawn;
    }

    function setStatus(uint256 id, Status status, bool pass, uint256 pid) external {
        Submission storage s = _subs[id];
        s.status = status;
        s.pass = pass;
        s.pid = uint64(pid);
        s.finalAt = uint64(block.timestamp);
    }

    /// A new panel of `kind` for submission `id`, its judges `keys` revealed with their receipts (counted unless
    /// `stalled`, which seats nobody in its one seat).
    function newPanel(uint256 id, Kind kind, address[] calldata keys, bool stalled) external returns (uint256 pid) {
        pid = ++panelCount;
        Panel storage p = _panels[pid];
        p.id = id;
        p.kind = kind;
        p.k = uint8(stalled ? 1 : keys.length);
        p.seats = uint8(keys.length);
        p.counted = !stalled;
        p.revealBy = uint64(block.timestamp);
        _keys[pid] = keys;
    }

    function submission(uint256 id) external view returns (Submission memory) {
        return _subs[id];
    }

    function panel(uint256 pid) external view returns (Panel memory) {
        return _panels[pid];
    }

    function judges(uint256 pid) external view returns (address[] memory keys) {
        keys = new address[](_panels[pid].k);
        address[] storage ks = _keys[pid];
        for (uint256 i; i < ks.length && i < keys.length; ++i) {
            keys[i] = ks[i];
        }
    }

    function seat(uint256 pid, uint256 slot) external view returns (Seat memory x) {
        address[] storage ks = _keys[pid];
        if (slot >= ks.length) return x;
        x.key = ks[slot];
        x.hasSeal = true;
        x.revealed = true;
        x.receipted = true;
        x.receipt = keccak256(abi.encode("receipt", pid, x.key));
    }
}
