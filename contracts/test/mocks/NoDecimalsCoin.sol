// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

/// A coin without decimals(): Baskets can't scale its caps, so it's refused.
contract NoDecimalsCoin {
    function balanceOf(address) external pure returns (uint256) {
        return 0;
    }
}
