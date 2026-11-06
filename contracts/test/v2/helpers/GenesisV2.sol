// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {Verdicts} from "../../../src/v2/Verdicts.sol";

// The checker image the test versions allow (task 5.4: the constitution's allowed list, fixed at deployment).
bytes32 constant TEST_IMAGE = keccak256("the official checker image (test)");
// An accepted TEE attestation type for the tests (S14: AWS Nitro), beside Verdicts.NO_ATTESTATION.
bytes32 constant NITRO = keccak256("aws-nitro");

/// A test version's genesis (task 5.4) from the shape the tests used before seats: the keys (0: a vacant seat) and
/// the quorum, the operators' disclosed accounts paired with their seats' keys (a key not in the set maps to no seat,
/// so the constructor refuses it). Each seat gets its own family and provider; the version allows TEST_IMAGE and
/// accepts NITRO and NO_ATTESTATION.
function genesis(address[] memory keys, uint256 q, address[] memory operators, address[] memory operatorKeys)
    pure
    returns (Verdicts.Genesis memory g)
{
    uint256 n = keys.length;
    g.keys = keys;
    g.quorum = q;
    g.operators = operators;
    g.families = new bytes32[](n);
    g.providers = new bytes32[](n);
    for (uint256 i; i < n; ++i) {
        g.families[i] = keccak256(abi.encode("family", i));
        g.providers[i] = keccak256(abi.encode("provider", i));
    }
    g.operatorSeats = new uint256[](operatorKeys.length);
    for (uint256 j; j < operatorKeys.length; ++j) {
        uint256 s = type(uint256).max;
        for (uint256 i; i < n; ++i) {
            if (operatorKeys[j] != address(0) && keys[i] == operatorKeys[j]) s = i;
        }
        g.operatorSeats[j] = s;
    }
    g.images = new bytes32[](1);
    g.images[0] = TEST_IMAGE;
    g.attestationTypes = new bytes32[](2);
    g.attestationTypes[0] = NITRO;
    g.attestationTypes[1] = keccak256("none");
}
