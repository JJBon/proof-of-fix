// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {MockCoin} from "./MockCoin.sol";

/// A coin whose balances can shrink without a transfer (a negative rebase, a bug, or a hostile issuer), or whose
/// balanceOf can revert: what breaks the invariant (design D6).
contract LyingCoin is MockCoin {
    mapping(address => uint256) public shrunk;
    bool public broken;

    error Broken();

    constructor() MockCoin("Lying USD", "lUSD", 6) {}

    function shrink(address account, uint256 amount) external {
        shrunk[account] += amount;
    }

    function breakBalanceOf(bool on) external {
        broken = on;
    }

    function balanceOf(address account) public view override returns (uint256) {
        if (broken) revert Broken();
        uint256 b = super.balanceOf(account);
        return b > shrunk[account] ? b - shrunk[account] : 0;
    }
}
