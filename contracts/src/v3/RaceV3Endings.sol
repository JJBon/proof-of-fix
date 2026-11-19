// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {RaceV3Base} from "./RaceV3Base.sol";
import {Heads} from "../v2/Heads.sol";
import {Panels} from "./Panels.sol";
import {PoolV3} from "./PoolV3.sol";
import {Status} from "./PanelsBase.sol";

/// RaceV3's endings (proof-of-fix#251, contract batch 2; the EIP-170 split of RaceV3Annex): withdrawals, time-outs,
/// expired merges, and the refund of a check Panels couldn't judge (design L19). RaceV3Annex deploys it from its own
/// constructor with the same parameters and reaches it for any call it doesn't have (its fallback), so these run in
/// RaceV3's storage, with its balances and its caller, after two DELEGATECALLs. Called directly, they refuse. Each is
/// described on RaceV3.
contract RaceV3Endings is RaceV3Base {
    /// This contract's own address: called directly (not through a race's DELEGATECALL), its actions refuse.
    address internal immutable self;

    constructor(
        Config memory config_,
        uint256 bountyCap_,
        uint256 totalCap_,
        Panels panels_,
        PoolV3 pool_,
        uint256 start_
    )
        RaceV3Base(config_, bountyCap_, totalCap_, panels_, pool_, Heads(address(0)), start_)
    {
        self = address(this);
    }

    modifier delegated() {
        if (address(this) == self) revert Refused();
        _;
    }

    // ---------- issues ----------

    /// The reporter withdraws an issue whose check no panel was seated for: its stake and deposit return; the
    /// registration fee stays spent.
    function withdrawIssue(uint256 issueId) external delegated nonReentrant {
        Issue storage i = _issues[issueId];
        if (i.reporter != msg.sender || i.state != IssueState.Posted || i.bounty != 0) revert Refused();
        _end(i.check, Outcome.Withdrawn);
        _closeIssue(issueId, IssueState.Returned, msg.sender);
    }

    // ---------- submissions ----------

    /// The solver withdraws a submission no panel was seated for (waiting, or before its draw): its deposit returns
    /// whole (no counted check was charged; shadows are the pool's).
    function withdraw(uint256 id) external delegated nonReentrant {
        Submission storage s = _submissions[id];
        if (s.solver != msg.sender || s.bounty == 0 || s.outcome != Outcome.None) revert Refused();
        _end(id, Outcome.Withdrawn);
    }

    /// A submission no panel was seated for within resultDays of its commitment ends as timed out, its deposit back:
    /// it can't hold up the queue or the sunset. Anyone. One with a released round ends by `release` instead, which
    /// also refunds its bounty (L19).
    function timeOut(uint256 id) external delegated nonReentrant {
        Submission storage s = _submissions[id];
        if (s.bounty == 0 || s.outcome != Outcome.None || _w(_sub(id), S_REDRAWS) != 0) revert Refused();
        if (_day() < s.day + config.resultDays) revert NotYet();
        _end(id, Outcome.TimedOut);
    }

    /// A winning fix not claimed by its deadline (mergeDays after its win), or a claimed one whose final verdict wasn't
    /// merged by mergeDays after its finality (its base went stale, or nobody merged it, #251 L9): nothing is paid
    /// (the award closes with nothing earned) and the bounty reopens.
    function mergeExpired(uint256 b) external delegated nonReentrant {
        Bounty storage bt = _bounties[b];
        if (bt.state == State.Won) {
            if (_day() <= bt.mergeBy) revert NotYet();
            return _reopen(b);
        }
        if (bt.state != State.Merged) revert NotYet();
        uint256 e = bt.epoch;
        Award storage a = awards[b][e];
        (Status st,, uint256 finalAt) = _verdict(a.sub);
        if (a.merged || st != Status.Final || _day() <= (finalAt - start) / 1 days + config.mergeDays) revert NotYet();
        a.closed = true;
        emit ClawedBack(b, e, 0);
        _reopen(b);
    }

    // ---------- L19: a check that can't be judged ----------

    /// Check `id` released for good by Panels (MAX_REDRAWS released rounds), or parked after a released round at its
    /// deadline (resultDays after its commitment; Panels.abandon): it ends `Released`, with no slash and no failed
    /// verdict, its deposit's rest back to its solver (a counted verdict's judges are paid first, by `result`). If its
    /// bounty is open, or this check won it, the bounty is refunded to its funders (by input, `claimRefund`) and the
    /// issue stake returns; a registration check's issue is returned the same way. Anyone.
    function release(uint256 id) external delegated nonReentrant {
        Submission storage s = _submissions[id];
        if (s.solver == address(0) || s.done) revert Refused();
        bytes memory ps = _sub(id);
        if (_w(ps, S_PID) != 0 && !s.paid) revert NotYet(); // its counted judges first: `result`
        if (Status(_w(ps, S_STATUS)) != Status.Released) {
            if (_w(ps, S_REDRAWS) == 0 || _day() < s.day + config.resultDays) revert NotYet();
            panels.abandon(id);
        }
        s.outcome = Outcome.Released;
        emit Decided(id, Outcome.Released);
        s.done = true;
        uint256 left = s.deposit;
        s.deposit = 0;
        _release(coin, left, s.solver);
        uint256 b = s.bounty;
        uint256 issueId = b == 0 ? s.issue : _bounties[b].issue;
        if (b != 0) {
            Bounty storage bt = _bounties[b];
            bool won = bt.winner == id && (bt.state == State.Won || bt.state == State.Merged);
            if (bt.state != State.Open && !won) return;
            if (bt.state == State.Merged) {
                Award storage a = awards[b][bt.epoch];
                a.closed = true; // never final, so never merged: nothing earned
                emit ClawedBack(b, bt.epoch, 0);
            }
            _setState(b, State.Refunded);
        }
        Issue storage i = _issues[issueId];
        if (i.state == IssueState.Posted) _closeIssue(issueId, IssueState.Returned, i.reporter);
    }

    // ---------- internals ----------

    /// Panels withdraws the check (only before a panel is seated); its whole deposit returns.
    function _end(uint256 id, Outcome o) internal {
        panels.withdraw(id);
        Submission storage s = _submissions[id];
        s.done = true;
        uint256 left = s.deposit;
        s.deposit = 0;
        _release(coin, left, s.solver);
        _decided(id, o);
    }
}
