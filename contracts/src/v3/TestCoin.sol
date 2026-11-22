// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {LaunchChain} from "./LaunchChain.sol";

/// The fee coin of the Sepolia launch (proof-of-fix#251, design L17 as amended by the owner on 2026-11-20;
/// specs/deployment-binding, "The fee coin is a test coin with no key"): "proof-of-fix test coin", POFTEST, a test
/// coin with no value. Nobody sells it and the project runs no market for it. Six decimals, so the design's dollar
/// arithmetic is unchanged (1 coin = one "$" of its tables).
///
/// Its whole supply comes from two places: the genesis mint in this constructor, fixed at deploy and named in the
/// deployment record, and its faucet (CoinFaucet), the only address that may mint afterwards. The faucet is the
/// contract that creates this one (CoinFaucet deploys it in its own constructor), so the minter is fixed from the
/// token's first moment. No owner, admin, pause, setter or upgrade (ADR 0003; D15).
contract TestCoin is ERC20 {
    /// The faucet: the contract that created this token, and its only minter.
    address public immutable faucet;
    /// The genesis mint's total, in micro-coins.
    uint256 public immutable genesisMint;

    error NotFaucet(address caller);
    error BadGenesis();

    /// `to` and `amounts`: the genesis mint, one entry per recipient (micro-coins). Called by the faucet.
    constructor(address[] memory to, uint256[] memory amounts) ERC20("proof-of-fix test coin", "POFTEST") {
        LaunchChain.check();
        if (to.length != amounts.length) revert BadGenesis();
        faucet = msg.sender;
        uint256 total;
        for (uint256 i; i < to.length; ++i) {
            _mint(to[i], amounts[i]);
            total += amounts[i];
        }
        genesisMint = total;
    }

    function decimals() public pure override returns (uint8) {
        return 6;
    }

    /// Only the faucet mints, by its fixed rule.
    function mint(address to, uint256 amount) external {
        if (msg.sender != faucet) revert NotFaucet(msg.sender);
        _mint(to, amount);
    }
}
