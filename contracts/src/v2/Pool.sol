// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuardTransient} from "@openzeppelin/contracts/utils/ReentrancyGuardTransient.sol";

/// The sponsors' pool, v2 (proof-of-fix#85, design S6, S7, S10): an on-chain pot anyone funds, in the fee coins fixed
/// at deployment, spent only by fixed rules. There is no withdraw function and no owner: nobody can take money out.
///
/// Task 5.1 builds the pot: funding and its accounts. The spending rules come with their tasks, each a fixed rule in
/// code, never a discretionary call:
///   TODO(5.10) refunds of accepted ADRs' fees.
///   TODO(5.11) system issues: their registration fees, and SYSTEM_BOUNTY_START for each system issue's bounty while
///              the pool holds it.
contract Pool is ReentrancyGuardTransient {
    using SafeERC20 for IERC20;

    address[] internal _coins;
    mapping(address coin => bool) public isFeeCoin;
    mapping(address coin => uint256) public held; // what the pool holds in each coin (by what actually arrived)
    mapping(address coin => uint256) public funded; // everything ever funded in each coin
    mapping(address coin => mapping(address sponsor => uint256)) public fundedBy;

    event Funded(address indexed sponsor, address indexed coin, uint256 amount);

    error BadParams();
    error NotFeeCoin(address coin);
    error NothingArrived();

    constructor(address[] memory coins_) {
        if (coins_.length == 0) revert BadParams();
        for (uint256 i; i < coins_.length; ++i) {
            address c = coins_[i];
            if (c == address(0) || isFeeCoin[c]) revert BadParams();
            isFeeCoin[c] = true;
            _coins.push(c);
        }
    }

    function coins() external view returns (address[] memory) {
        return _coins;
    }

    /// Anyone adds to the pool. It counts what arrived, so a coin that charges on transfer is credited with what the
    /// pool received, not what was asked.
    function fund(address coin, uint256 amount) external nonReentrant returns (uint256 received) {
        if (!isFeeCoin[coin]) revert NotFeeCoin(coin);
        IERC20 c = IERC20(coin);
        uint256 before = c.balanceOf(address(this));
        c.safeTransferFrom(msg.sender, address(this), amount);
        received = c.balanceOf(address(this)) - before;
        if (received == 0) revert NothingArrived();
        held[coin] += received;
        funded[coin] += received;
        fundedBy[coin][msg.sender] += received;
        emit Funded(msg.sender, coin, received);
    }
}
