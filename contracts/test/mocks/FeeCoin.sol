// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {MockCoin} from "./MockCoin.sol";

/// A fee-on-transfer coin: 1 % of every transfer is burned, so less arrives than was sent.
contract FeeCoin is MockCoin {
    constructor() MockCoin("Fee USD", "feeUSD", 6) {}

    function _update(address from, address to, uint256 value) internal override {
        if (from == address(0) || to == address(0)) return super._update(from, to, value);
        uint256 fee = value / 100;
        super._update(from, address(0), fee);
        super._update(from, to, value - fee);
    }
}
