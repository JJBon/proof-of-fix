// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {RaceV2Base} from "./RaceV2Base.sol";
import {Verdicts} from "./Verdicts.sol";
import {Heads} from "./Heads.sol";
import {IFees} from "./IFees.sol";

/// RaceV2's rarely called actions (proof-of-fix#85, task 5.3: the EIP-170 split continued, design S10), moved out of
/// RaceV2 unchanged to make room for the issue tier's draw: the appeals, withdrawIssue, junk, refuseSimilar, timeOut,
/// mergeExpired and challengeUpheld. RaceV2 deploys this contract with its own parameters and delegates those calls
/// here (DELEGATECALL), so they run in RaceV2's storage, with its balances and its caller, exactly as before. Called
/// directly, they refuse: this contract's own storage holds nothing.
contract RaceV2Annex is RaceV2Base {
    /// The RaceV2 that deployed this contract: the only context these functions run in.
    address internal immutable race;

    constructor(
        Config memory config_,
        address[] memory feeCoins_,
        uint256 bountyCap_,
        uint256 totalCap_,
        Verdicts verdicts_,
        uint256 inflationPct_,
        uint256 start_,
        Heads heads_,
        IFees meter_
    ) RaceV2Base(config_, feeCoins_, bountyCap_, totalCap_, verdicts_, inflationPct_, start_, heads_, meter_) {
        race = msg.sender;
    }

    /// Only through RaceV2's delegation.
    modifier delegated() {
        if (address(this) != race) revert Refused();
        _;
    }

    /// The author of a failed or split-rejected submission appeals once: the appeal fee, and the same fix checked
    /// again (by the second jury) as a new submission with a new deposit. A split rejection is where the checks
    /// most often wrong a good fix (owner, 2026-10-29: 70 % of them were good in the simulation).
    function appeal(uint256 id, address coin) external delegated nonReentrant returns (uint256 newId) {
        Submission storage s = _submissions[id];
        Bounty storage bt = _bounties[s.bounty];
        bool rejected = s.outcome == Outcome.Fail || s.outcome == Outcome.Split;
        if (s.solver != msg.sender || !rejected || s.appealed) revert Refused();
        if (bt.state != State.Open) revert WrongState(s.bounty, bt.state);
        _feeCoin(coin);
        s.appealed = true;
        _collect(coin, msg.sender, _units(coin, config.appealFee), config.infrastructure);
        newId = _submit(s.bounty, msg.sender, s.commitment, coin);
        _submissions[newId].appealed = true;
    }

    /// A submitter whose fix was rejected as a duplicate appeals to a jury from different providers, posting the
    /// appeal deposit; the appeal fee and the jurors' fees come from it (#64).
    function appealDuplicate(uint256 b, bytes32 fix, address coin)
        external
        delegated
        nonReentrant
        returns (uint256 id)
    {
        Bounty storage bt = _bounties[b];
        if (bt.state != State.Open) revert WrongState(b, bt.state);
        _feeCoin(coin);
        uint256 deposit = _units(coin, config.appealDeposit);
        _hold(coin, msg.sender, deposit);
        id = _appeals.length;
        _appeals.push(Appeal(b, msg.sender, fix, coin, deposit, false));
    }

    /// A duplicate appeal's verdict: the appeal fee and the jurors' fees from its deposit, the rest back. A cleared
    /// fix is checked like any the next time it's submitted (the oracles' record).
    function appealResult(uint256 id, bool cleared, Fee[] calldata jurors, Signed calldata auth)
        external
        delegated
        nonReentrant
    {
        Appeal storage a = _appeals[id];
        _authorize(
            keccak256(abi.encode(APPEAL_RESULT_TYPEHASH, id, a.bounty, cleared, _hashFees(jurors), auth.nonce)), auth
        );
        if (a.solver == address(0) || a.decided) revert Refused();
        a.decided = true;
        uint256 fee = _units(a.coin, config.appealFee);
        if (fee > a.deposit) fee = a.deposit;
        _release(a.coin, fee, config.infrastructure);
        uint256 left = _payFees(a.coin, a.deposit - fee, jurors);
        _release(a.coin, left, a.solver);
        emit AppealDecided(id, cleared);
    }

    /// An issue no bounty was opened for (the check hasn't answered): its reporter takes the stake back.
    function withdrawIssue(uint256 id) external delegated nonReentrant {
        Issue storage i = _issues[id];
        if (i.reporter != msg.sender || i.state != IssueState.Posted || i.bounty != 0) revert Refused();
        _closeIssue(id, IssueState.Returned, msg.sender);
    }

    /// The oracles found the issue junk: its stake goes to insurance, and its bounty, if still open, refunds.
    function junk(uint256 id, Signed calldata auth) external delegated nonReentrant {
        _authorize(keccak256(abi.encode(JUNK_TYPEHASH, id, auth.nonce)), auth);
        Issue storage i = _issues[id];
        if (i.state != IssueState.Posted) revert Refused();
        _closeIssue(id, IssueState.Forfeited, config.insurance);
        if (i.bounty != 0) {
            State s = _bounties[i.bounty].state;
            if (s == State.Open) _setState(i.bounty, State.Refunded);
        }
    }

    /// The registration check found the issue similar to one whose bounty is still open or being paid (D12): no
    /// bounty opens, the fee stays spent on the check, and the stake returns. Funders add to the open one.
    function refuseSimilar(uint256 issueId, uint256 openBounty, Signed calldata auth) external delegated nonReentrant {
        _authorize(keccak256(abi.encode(REFUSE_SIMILAR_TYPEHASH, issueId, openBounty, auth.nonce)), auth);
        Issue storage i = _issues[issueId];
        State s = _bounties[openBounty].state;
        if (i.state != IssueState.Posted || i.bounty != 0) revert Refused();
        if (s != State.Open && s != State.Won && s != State.Merged) revert WrongState(openBounty, s);
        _closeIssue(issueId, IssueState.Returned, i.reporter);
        emit RefusedSimilar(issueId, openBounty);
    }

    /// A submission with no result after resultDays (most likely never revealed to the oracles) fails, so it can't
    /// hold up the queue or the sunset. Its deposit pays the evaluation fee and the rest returns. Anyone can call it.
    function timeOut(uint256 id) external delegated nonReentrant {
        Submission storage s = _submissions[id];
        if (s.solver == address(0) || s.outcome != Outcome.None) revert Refused();
        if (day() < s.day + config.resultDays) revert NotYet();
        uint256 fee = _units(s.coin, config.evaluationFee);
        if (fee > s.deposit) fee = s.deposit;
        _release(s.coin, fee, config.infrastructure);
        _release(s.coin, s.deposit - fee, s.solver);
        s.outcome = Outcome.TimedOut;
        emit Decided(id, Outcome.TimedOut);
        _decide(s.bounty);
    }

    /// A winning fix not merged by its deadline: nothing is paid and the bounty reopens.
    function mergeExpired(uint256 b) external delegated nonReentrant {
        Bounty storage bt = _bounties[b];
        if (bt.state != State.Won || day() <= bt.mergeBy) revert NotYet();
        _reopen(b);
    }

    /// An upheld challenge (in the window, or after it while instalments are unpaid): the award keeps what it has
    /// earned, the rest stays in the bounty, and the bounty reopens at its locked price (pof's slash and claw_back).
    function challengeUpheld(uint256 b, uint256 epoch, Signed calldata auth) external delegated nonReentrant {
        _authorize(keccak256(abi.encode(CHALLENGE_UPHELD_TYPEHASH, b, epoch, auth.nonce)), auth);
        Bounty storage bt = _bounties[b];
        if (bt.state != State.Merged) revert WrongState(b, bt.state);
        uint256 e = bt.epoch;
        if (e != epoch) revert Refused(); // signed for another award
        uint256 n = earned(b, e);
        if (n >= config.instalments) revert Refused(); // fully paid: nothing to claw back
        Award storage a = awards[b][e];
        a.earned = n;
        a.closed = true;
        emit ClawedBack(b, e, n);
        _reopen(b);
    }
}
