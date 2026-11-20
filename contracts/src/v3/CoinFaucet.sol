// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {TestCoin} from "./TestCoin.sol";
import {LaunchChain} from "./LaunchChain.sol";

/// The test coin's keyless faucet (proof-of-fix#251, design L17 as amended by the owner on 2026-11-20;
/// specs/deployment-binding, "The faucet's rule is fixed"): 20 coins a claim, one claim per address every 2 hours,
/// mirroring Circle's public faucet (reports/faucet-spam-v1.md, fact 1). Anyone may claim, for itself only. After the
/// genesis mint this rule is the only way new coins come into existence. No owner, admin, pause, setter or upgrade.
///
/// It deploys the token in its own constructor, so the token's minter is this contract from the start and neither
/// needs the other's address in advance. Its creation code holds the token's.
///
/// The limit is per address, and addresses are free (no reCAPTCHA): a bot can farm many, paying only their gas. That
/// spam is bounded by the validators' capacity and the nodes' spending caps, not by the coin (ADR 0007 trust point 6,
/// accepted by the owner on 2026-11-19).
contract CoinFaucet {
    /// 20 coins (6 decimals).
    uint256 public constant CLAIM_AMOUNT = 20e6;
    /// One claim per address every 2 hours.
    uint256 public constant CLAIM_INTERVAL = 2 hours;

    TestCoin public immutable coin;

    /// The time from which each address may claim again; 0 if it never claimed.
    mapping(address => uint256) public nextClaim;

    event Claimed(address indexed by, uint256 amount, uint256 nextClaim);

    error TooSoon(uint256 nextClaim);

    /// `genesisTo`, `genesisAmounts`: the token's genesis mint (micro-coins), fixed at deploy.
    constructor(address[] memory genesisTo, uint256[] memory genesisAmounts) {
        LaunchChain.check();
        coin = new TestCoin(genesisTo, genesisAmounts);
    }

    /// Mints `CLAIM_AMOUNT` to the caller and returns the time of its next claim.
    function claim() external returns (uint256 next) {
        uint256 at = nextClaim[msg.sender];
        if (block.timestamp < at) revert TooSoon(at);
        next = block.timestamp + CLAIM_INTERVAL;
        nextClaim[msg.sender] = next;
        coin.mint(msg.sender, CLAIM_AMOUNT);
        emit Claimed(msg.sender, CLAIM_AMOUNT, next);
    }
}
