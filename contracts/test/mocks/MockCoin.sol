// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// A plain coin for tests: anyone mints. Six decimals by default, so the simulation's micro-credits replay
/// one to one (design D2).
contract MockCoin is ERC20 {
    uint8 private immutable _decimals;

    constructor(string memory name_, string memory symbol_, uint8 decimals_) ERC20(name_, symbol_) {
        _decimals = decimals_;
    }

    function decimals() public view override returns (uint8) {
        return _decimals;
    }

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
