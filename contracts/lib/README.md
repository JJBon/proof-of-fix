# Vendored libraries

Copied at pinned commits so builds fetch nothing (proof-of-fix#56, design D1). Don't edit these files: `scripts/check.sh` checks them against `SHA256SUMS`, and `scripts/contracts.sh vendor` re-creates them from the commits below.

| Library | Release | Commit | License | What's copied |
|---|---|---|---|---|
| [forge-std](https://github.com/foundry-rs/forge-std) | v1.17.0 | `f3dae6e6ee381f25eb6a246f7da9b85c91a68219` | MIT OR Apache-2.0 (`LICENSE-MIT`, `LICENSE-APACHE`) | `src/` |
| [OpenZeppelin Contracts](https://github.com/OpenZeppelin/openzeppelin-contracts) | v5.7.0 | `cab19933c33c2ad1d4c7a84864a3601dddfd16f3` | MIT (`LICENSE`) | `SafeERC20`, `ECDSA`, `MessageHashUtils`, `ReentrancyGuardTransient`, `ERC20` (for the mock coins) and what they import; the list is `OZ_FILES` in `scripts/contracts.sh` |

The toolchain is pinned in `scripts/contracts.sh`: the Foundry image v1.8.5 by digest, and solc 0.8.37 by sha256.
