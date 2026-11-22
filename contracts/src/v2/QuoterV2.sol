// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {RaceV2 as Race} from "./RaceV2.sol";
import {RaceV2Base} from "./RaceV2Base.sol";
import {Fees} from "./Fees.sol";

/// The quote for v2 (proof-of-fix#85, task 5.1): v1's Quoter (task 3.2, D8) reading RaceV2, whose views are the same.
/// A lens with no state and no write; anyone can deploy their own copy.
/// With a check-fee meter (task 5.7, S15) the check deposit is the maximum check cost: the repository's CI profile and
/// the unit price table in force (or pending, if dearer) at the caps, plus the agreed SERVICE_FEE per judge and the
/// relayer's gas allowance; whatever the checks don't use is refunded. Without one, v1's flat deposit.
contract QuoterV2 {
    uint256 constant BPS = 10_000;

    /// Amounts in micro-units of the quoted coin; the fees in micro-units of whichever fee coin pays them.
    struct Quote {
        RaceV2Base.State state;
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
        bool metered; // a meter charges the checks (S15): checkDeposit is the maximum, in the meter's fee coin
        uint256 serviceFee; // metered: the agreed fee per counted check
        uint256 judges; // metered: the judges drawn per check (each charged its usage plus the service fee)
        uint256 evaluationFee; // a late or duplicate submission's fee
        uint256 appealFee;
    }

    function quote(Race race, uint256 b, address coin) external view returns (Quote memory q) {
        RaceV2Base.Bounty memory bt = race.bounty(b);
        RaceV2Base.Config memory c = race.getConfig();
        q.state = bt.state;
        q.day = race.day();
        q.locked = bt.locked;
        q.offerBps = race.offerBps(b);
        if (bt.state == RaceV2Base.State.Merged || bt.state == RaceV2Base.State.Paid) {
            q.price = race.priceOf(b, coin, bt.epoch);
        } else if (bt.state == RaceV2Base.State.Open || bt.state == RaceV2Base.State.Won) {
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
        if (bt.state == RaceV2Base.State.Open) q.sunsetDay = bt.idleSince + c.idleDays;
        q.attemptFee = c.attemptFee;
        q.checkDeposit = c.checkDeposit;
        if (address(race.meter()) != address(0)) {
            Fees m = Fees(address(race.meter()));
            q.metered = true;
            q.checkDeposit = m.maxDepositFor(b);
            q.serviceFee = m.serviceFee();
            q.judges = race.verdicts().ISSUE_JUDGES();
        }
        q.evaluationFee = c.evaluationFee;
        q.appealFee = c.appealFee;
    }
}
