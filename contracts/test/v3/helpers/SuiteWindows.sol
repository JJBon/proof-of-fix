// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Vm} from "forge-std/Vm.sol";
import {Windows, WindowsLib} from "../../../src/v3/Windows.sol";

Vm constant SUITE_VM = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

// The one repository every v3 test deployment serves (#251, L1), and its genesis head.
bytes32 constant TEST_REPO = keccak256("rad:z-test-repository");
bytes32 constant TEST_GENESIS_HEAD = bytes32(bytes20(keccak256("the test repository's genesis commit")));

/// The windows the v3 suite deploys with (#251 task 3.4): ADR 0004's production values by default, or every hour a
/// minute with POF_TEST_WINDOWS=minutes (scripts/contracts.sh passes it into the container). The suite runs once each
/// way; a test that pins a production value deploys `WindowsLib.production()` itself.
function suiteWindows() view returns (Windows memory) {
    string memory kind = SUITE_VM.envOr("POF_TEST_WINDOWS", string("production"));
    if (keccak256(bytes(kind)) == keccak256("minutes")) return WindowsLib.inMinutes();
    if (keccak256(bytes(kind)) != keccak256("production")) revert("POF_TEST_WINDOWS: production or minutes");
    return WindowsLib.production();
}
