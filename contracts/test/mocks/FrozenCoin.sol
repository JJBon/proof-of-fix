// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {MockCoin} from "./MockCoin.sol";

/// A coin whose issuer can freeze an address or pause every transfer, like the big stablecoins (#59).
contract FrozenCoin is MockCoin {
    mapping(address => bool) public frozen;
    bool public paused;

    error Frozen(address account);
    error Paused();

    constructor() MockCoin("Frozen USD", "fUSD", 6) {}

    function freeze(address account, bool on) external {
        frozen[account] = on;
    }

    function pause(bool on) external {
        paused = on;
    }

    function _update(address from, address to, uint256 value) internal override {
        if (paused) revert Paused();
        if (frozen[from]) revert Frozen(from);
        if (frozen[to]) revert Frozen(to);
        super._update(from, to, value);
    }
}
