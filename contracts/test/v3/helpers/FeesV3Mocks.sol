// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {IFeesV3Validators, IFeesV3Scores} from "../../../src/v3/IFeesV3.sol";

/// Stands in for Validators (task 3.1) in FeesV3's tests: who is active and each key's family, set by the test.
contract MockValidators is IFeesV3Validators {
    mapping(address => bool) public active;
    mapping(address => bytes32) public familyOf;
    uint256 public activeCount;

    function setFamily(address key, bytes32 family) external {
        familyOf[key] = family;
    }

    function setActive(address key, bool on) external {
        if (active[key] == on) return;
        active[key] = on;
        if (on) ++activeCount;
        else --activeCount;
    }

    function setActiveCount(uint256 n) external {
        activeCount = n;
    }

    function isActive(address key) external view returns (bool) {
        return active[key];
    }
}

/// Stands in for Panels' family scores (task 3.2) in FeesV3's tests.
contract MockScores is IFeesV3Scores {
    mapping(bytes32 => ScoreState) public states;
    mapping(bytes32 => uint256) public scoreOf;

    function set(bytes32 family, ScoreState s, uint256 scoreWad) external {
        states[family] = s;
        scoreOf[family] = scoreWad;
    }

    function familyScore(bytes32 family) external view returns (ScoreState, uint256) {
        return (states[family], scoreOf[family]);
    }
}
