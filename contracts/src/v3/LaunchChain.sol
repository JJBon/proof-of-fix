// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

/// Where a v3 contract may be constructed (proof-of-fix#251, design L2 option 1, decided by the owner on 2026-11-18;
/// specs/deployment-binding, "Sepolia only"): Sepolia, and the two local test chains already named in Validators
/// (anvil's 31337 and the devnet's 7193), for tests and local devnets only. On any other chain, mainnet included, each
/// v3 constructor reverts. The `simulated` proof type stays refused off the two local ids (Validators, D18).
///
/// This binds this deployment's bytecode, not the open code: a fork removes the check with a one-line change. The
/// Sepolia deploy script (task 3.9) refuses the local ids for anything but a local endpoint.
library LaunchChain {
    uint256 internal constant SEPOLIA = 11_155_111;
    uint256 internal constant LOCAL = 31_337;
    uint256 internal constant DEVNET = 7_193;

    error WrongChain(uint256 chainId);

    function check() internal view {
        uint256 id = block.chainid;
        if (id != SEPOLIA && id != LOCAL && id != DEVNET) revert WrongChain(id);
    }
}
