// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Baskets} from "../../src/Baskets.sol";

/// Baskets with its internals exposed, standing in for the race in task 2.1's tests: anyone can pay out of a pot or
/// close it for refunds here, which Race.sol will restrict to its own rules.
contract BasketsHarness is Baskets {
    mapping(uint256 bounty => bool) public closed;

    constructor(uint256 bountyCap_, uint256 totalCap_) Baskets(bountyCap_, totalCap_) {}

    function pledge(uint256 bounty, address coin, uint256 amount) external nonReentrant {
        _pledge(bounty, coin, amount);
    }

    function pay(uint256 bounty, address coin, address to, uint256 amount) external nonReentrant {
        _pay(bounty, coin, to, amount);
    }

    function collect(address coin, uint256 amount, address to) external nonReentrant {
        _collect(coin, msg.sender, amount, to);
    }

    function close(uint256 bounty) external {
        closed[bounty] = true;
    }

    function hold(address coin, uint256 amount) external nonReentrant {
        _hold(coin, msg.sender, amount);
    }

    function release(address coin, uint256 amount, address to) external nonReentrant {
        _release(coin, amount, to);
    }

    function _settleForRefund(uint256 bounty, address) internal view override returns (bool) {
        return closed[bounty];
    }
}
