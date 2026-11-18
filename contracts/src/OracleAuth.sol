// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {MessageHashUtils} from "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";

/// The oracle quorum's signature check (proof-of-fix#56 D3), moved out of Race into an external library (#93) so Race
/// fits EIP-170. Same rules, same errors (same selectors): at least the quorum of distinct oracle keys signed the
/// action's EIP-712 digest, ordered by signer address, and the digest hasn't been used. The library is deployed once
/// and linked: it has no state and no owner, and Race calls it by delegatecall on its own storage.
library OracleAuth {
    error NotOracle();
    error TooFewSignatures();
    error DuplicateSigner();
    error Replayed();

    /// The digest is marked used before the action runs (a revert undoes both).
    function authorize(
        mapping(bytes32 digest => bool) storage usedDigest,
        mapping(address key => bool) storage isOracle,
        uint256 quorum,
        bytes32 domainSeparator,
        bytes32 structHash,
        bytes[] calldata sigs
    ) external {
        bytes32 digest = MessageHashUtils.toTypedDataHash(domainSeparator, structHash);
        if (usedDigest[digest]) revert Replayed();
        usedDigest[digest] = true;
        uint256 n = sigs.length;
        if (n < quorum) revert TooFewSignatures();
        address last;
        for (uint256 i; i < n; ++i) {
            address signer = ECDSA.recover(digest, sigs[i]); // refuses malleable (high-s) signatures
            if (!isOracle[signer]) revert NotOracle();
            if (signer <= last) revert DuplicateSigner();
            last = signer;
        }
    }
}
