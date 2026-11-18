// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {Pool} from "../v2/Pool.sol";

/// The sponsors' pool for v3 (proof-of-fix#138, task 3.5 of #132; design D5, D13): v2's Pool, which anyone funds and
/// nobody withdraws from, with one fixed spending rule. Its race, bound once (`bind`, from RaceV3's constructor),
/// pays from it what the version's rules say the pool pays: shadow judges' metered usage (validator-admission, "shadows
/// are repaid their usage from the sponsors' pool, capped per draw"), and the part of an audit's or a challenge panel's
/// pay that the checked submission's deposit no longer covers. The race computes every amount from FeesV3; the pool
/// pays at most what it holds. No owner, no admin, no other way out.
contract PoolV3 is Pool {
    using SafeERC20 for IERC20;

    address public spender;

    event Bound(address indexed spender);
    event Spent(address indexed coin, address indexed to, uint256 amount);

    error AlreadyBound();
    error NotSpender();

    constructor(address[] memory coins_) Pool(coins_) {}

    /// Binds the race that spends by the rules: the caller, once.
    function bind() external {
        if (spender != address(0)) revert AlreadyBound();
        spender = msg.sender;
        emit Bound(msg.sender);
    }

    /// Pays `amount` of `coin` to `to`, or what's left if less; returns what it paid. Only the bound race.
    function spend(address coin, address to, uint256 amount) external nonReentrant returns (uint256 paid) {
        if (msg.sender != spender) revert NotSpender();
        uint256 h = held[coin];
        paid = amount < h ? amount : h;
        if (paid == 0) return 0;
        held[coin] = h - paid;
        IERC20(coin).safeTransfer(to, paid);
        emit Spent(coin, to, paid);
    }
}
