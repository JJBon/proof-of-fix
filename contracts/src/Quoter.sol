// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {Race} from "./Race.sol";

/// Task 3.2 (design D8, phase 3): what a solver pays to try a bounty and could earn, in one read. A lens with no
/// state and no write: it reads Race's public views, so Race itself doesn't grow (it's already above EIP-170's
/// 24,576 bytes, see D8) and anyone can deploy their own copy. pof's counterpart is `Market.quote`; the replay checks
/// the two agree after every event of the exported runs.
contract Quoter {
    uint256 constant BPS = 10_000;

    /// Amounts in micro-units of the quoted coin; the fees in micro-units of whichever fee coin pays them.
    struct Quote {
        Race.State state;
        uint256 day; // the contract's day now
        bool locked; // the first attempt locked the share
        uint256 offerBps; // the share of the cap on offer: rising daily until locked
        uint256 cap; // what the pot can pay in this coin (pof's price_cap)
        uint256 price; // open or won: what the win pays (the share of the cap); merged or paid: the award's price
        uint256 instalments; // paid at each release after the challenge window
        uint256 instalment; // price / instalments
        uint256 lastInstalment; // the last one takes the remainder
        uint256 finderFee; // the reporter's, from the pot when it's paid
        uint256 attempting; // attempts in progress
        uint256 sunsetDay; // open: it sunsets on this day unless a checked submission restarts the count (D11)
        uint256 attemptFee;
        uint256 checkDeposit; // posted with a submission: the checks are paid from it, the rest returns
        uint256 evaluationFee; // a late or duplicate submission's fee
        uint256 appealFee;
    }

    function quote(Race race, uint256 b, address coin) external view returns (Quote memory q) {
        Race.Bounty memory bt = race.bounty(b);
        Race.Config memory c = race.getConfig();
        q.state = bt.state;
        q.day = race.day();
        q.locked = bt.locked;
        q.offerBps = race.offerBps(b);
        if (bt.state == Race.State.Merged || bt.state == Race.State.Paid) {
            q.price = race.priceOf(b, coin, bt.epoch);
        } else if (bt.state == Race.State.Open || bt.state == Race.State.Won) {
            // the pot at a win: what it holds less what earlier awards earned and haven't pulled (Race._priceNow)
            uint256 h = race.held(b, coin) - race.unpaidBefore(b, coin, bt.epoch + 1);
            q.cap = race.capOf(b, coin, h);
            q.price = q.cap * q.offerBps / BPS;
        }
        q.instalments = c.instalments;
        q.instalment = q.price / c.instalments;
        q.lastInstalment = q.price - q.instalment * (c.instalments - 1);
        q.finderFee = q.price * c.finderFeeBps / BPS;
        q.attempting = bt.attempting;
        if (bt.state == Race.State.Open) q.sunsetDay = bt.idleSince + c.idleDays;
        q.attemptFee = c.attemptFee;
        q.checkDeposit = c.checkDeposit;
        q.evaluationFee = c.evaluationFee;
        q.appealFee = c.appealFee;
    }
}
