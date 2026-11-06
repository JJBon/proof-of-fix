// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {Script} from "forge-std/Script.sol";
import {console} from "forge-std/console.sol";
import {Verdicts} from "../src/v2/Verdicts.sol";

/// A seat's key published on the devnet (proof-of-fix#85 task 5.4, design S13; #104's join flow): a vacant seat's first
/// key, or a filled seat's new one. Run it through scripts/devnet.sh join-v2, which passes the keys on stdin, one per
/// line: the sender's, then the co-signing seats' (comma-separated), then the new key's (or an empty line when the new
/// key's owner signed elsewhere and passed JOIN_KEY_SIG). The environment:
///   JOIN_RECORD        the v2 deployment record (under ./deployments)
///   JOIN_SEAT          the seat's index
///   JOIN_KEY           the new key's address (with JOIN_KEY_SIG), else derived from the new key on stdin
///   JOIN_KEY_SIG       optional: the new key's signature over the digest (scripts/devnet.sh digest-v2 prints it)
///   JOIN_IMAGE         optional: the checker image digest (default: the devnet's, keccak256("devnet checker image"))
///   JOIN_TYPE          optional: the attestation type's name (default "none": devnet only)
///   JOIN_ATTESTATION   optional: the attestation's hash (0x + 64 hex; default 0)
///   JOIN_NONCE         the rotation's nonce (0x + 64 hex)
/// The signatures go in increasing signer order. The rotation takes effect after the delay: scripts/devnet.sh warp,
/// then activate-v2.
contract JoinV2Script is Script {
    function run() external {
        string memory record = vm.readFile(string.concat("./", vm.envString("JOIN_RECORD")));
        Verdicts verdicts = Verdicts(vm.parseJsonAddress(record, ".verdicts"));
        uint256 sender = vm.envUint("JOIN_SENDER_PK");
        uint256[] memory cosigners = vm.envUint("JOIN_COSIGNER_PKS", ",");
        uint256 newSecret = vm.envOr("JOIN_KEY_PK", uint256(0));
        uint256 seat = vm.envUint("JOIN_SEAT");
        address key = newSecret != 0 ? vm.addr(newSecret) : vm.envAddress("JOIN_KEY");
        bytes32 image = vm.envOr("JOIN_IMAGE", keccak256("devnet checker image"));
        bytes32 kind = keccak256(bytes(vm.envOr("JOIN_TYPE", string("none"))));
        bytes32 attestation = vm.envOr("JOIN_ATTESTATION", bytes32(0));
        bytes32 nonce = vm.envBytes32("JOIN_NONCE");
        bytes32 digest = verdicts.rotateDigest(seat, key, image, kind, attestation, nonce);

        uint256 n = cosigners.length + 1;
        address[] memory who = new address[](n);
        bytes[] memory sigs = new bytes[](n);
        for (uint256 i; i < cosigners.length; ++i) {
            who[i] = vm.addr(cosigners[i]);
            sigs[i] = _sig(cosigners[i], digest);
        }
        who[n - 1] = key;
        sigs[n - 1] = newSecret != 0 ? _sig(newSecret, digest) : vm.envBytes("JOIN_KEY_SIG");
        for (uint256 i = 1; i < n; ++i) {
            for (uint256 j = i; j > 0 && who[j - 1] > who[j]; --j) {
                (who[j - 1], who[j]) = (who[j], who[j - 1]);
                (sigs[j - 1], sigs[j]) = (sigs[j], sigs[j - 1]);
            }
        }
        vm.startBroadcast(sender);
        verdicts.rotate(seat, key, image, kind, attestation, nonce, sigs);
        vm.stopBroadcast();
        (,,,, uint64 at) = verdicts.pending(seat);
        console.log(string.concat("JOIN seat ", vm.toString(seat), ": key ", vm.toString(key), " published"));
        console.log(string.concat("JOIN takes effect at ", vm.toString(uint256(at)), " (then: devnet.sh activate-v2)"));
    }

    function _sig(uint256 secret, bytes32 digest) internal pure returns (bytes memory) {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(secret, digest);
        return abi.encodePacked(r, s, v);
    }
}
