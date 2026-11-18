// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {RaceV3Base} from "./RaceV3Base.sol";
import {Heads} from "../v2/Heads.sol";
import {IFeesV3} from "./IFeesV3.sol";
import {IValidators} from "./IValidators.sol";
import {Panels} from "./Panels.sol";
import {PoolV3} from "./PoolV3.sol";
import {Status, Kind} from "./PanelsBase.sol";

/// RaceV3's rarely called actions (proof-of-fix#138, task 3.5; v2's EIP-170 split, RaceV2Annex): registration and the
/// registration check's outcome, withdrawals, appeals, time-outs, expired merges, challenges, reversals, the pay of
/// audits, challenge panels and shadows, FeesV3's queue signals and the deposit's return. It's deployed first, with the
/// race's Panels, pool, start and caps (its `fingerprint`, which RaceV3's constructor checks), and RaceV3 delegates
/// those calls here (DELEGATECALL), so they run in RaceV3's storage, with its balances and its caller. Called directly,
/// they refuse: this contract's own storage holds nothing. Each is described on RaceV3.
contract RaceV3Annex is RaceV3Base {
    /// This contract's own address: called directly (not through a race's DELEGATECALL), its actions refuse.
    address internal immutable self;

    /// Deployed before its RaceV3 with the same parameters (`start_` nonzero); the race checks `fingerprint`.
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
        if (start_ == 0) revert BadParams();
        self = address(this);
    }

    modifier delegated() {
        if (address(this) == self) revert Refused();
        _;
    }

    /// The Panels, pool, start and caps this companion was built with (its immutables), for its race to check.
    function fingerprint() external view returns (bytes32) {
        return _fingerprint();
    }

    // ---------- issues ----------

    /// Once an issue's registration check is final in Panels: a pass opens its bounty at once (no target, D12), a fail
    /// forfeits its stake to insurance. Anyone.
    function openBounty(uint256 issueId) external delegated nonReentrant returns (uint256 b) {
        Issue storage i = _issues[issueId];
        if (i.state != IssueState.Posted || i.bounty != 0) revert Refused();
        (Status st, bool pass,) = _verdict(i.check);
        if (st != Status.Final) revert NotYet();
        Submission storage s = _submissions[i.check];
        if (s.outcome == Outcome.None) {
            s.outcome = pass ? Outcome.Pass : Outcome.Fail;
            emit Decided(i.check, s.outcome);
        }
        if (!pass) {
            _closeIssue(issueId, IssueState.Forfeited, config.insurance);
            return 0;
        }
        b = _bounties.length;
        _bounties.push();
        _bounties[b].issue = issueId;
        i.bounty = b;
        emit BountyOpened(b, issueId);
        Bounty storage bt = _bounties[b];
        bt.offerFrom = _day();
        bt.idleSince = _day();
        _setState(b, State.Open);
    }

    /// The reporter withdraws an issue whose check no panel was seated for: its stake and deposit return; the
    /// registration fee stays spent.
    function withdrawIssue(uint256 issueId) external delegated nonReentrant {
        Issue storage i = _issues[issueId];
        if (i.reporter != msg.sender || i.state != IssueState.Posted || i.bounty != 0) revert Refused();
        _end(i.check, Outcome.Withdrawn);
        _closeIssue(issueId, IssueState.Returned, msg.sender);
    }

    /// Anyone registers an issue in `repo` (a repository of the head registry, or 0 outside it): the registration fee,
    /// the issue stake and its registration check's deposit. Panels judges the check; its final pass opens the bounty
    /// and its final fail forfeits the stake (`openBounty`).
    function register(bytes32 repo, bool hidden) external delegated nonReentrant returns (uint256 id) {
        if (repo != bytes32(0) && !heads.isRepo(repo)) revert Refused();
        uint256 fee = _units(config.registrationFee);
        uint256 stake = _units(config.issueStake);
        if (fee != 0) _collect(coin, msg.sender, fee, config.infrastructure);
        if (stake != 0) _hold(coin, msg.sender, stake);
        id = _issues.length;
        _issues.push(Issue(repo, msg.sender, fee, stake, 0, 0, IssueState.Posted, hidden));
        bytes32 commitment = keccak256(abi.encode("issue", id, msg.sender, repo, hidden));
        uint256 check = _newCheck(0, id, msg.sender, commitment, CHECK_BOUNTY);
        _issues[id].check = check;
        emit Registered(id, msg.sender, check);
    }

    // ---------- submissions ----------

    /// The author of a failed submission appeals once, while the bounty is open: the appeal fee, and the same
    /// commitment judged again by a fresh panel, as a new submission with a new deposit.
    function appeal(uint256 id) external delegated nonReentrant returns (uint256 newId) {
        Submission storage s = _submissions[id];
        uint256 b = s.bounty;
        if (b == 0 || s.solver != msg.sender || s.outcome != Outcome.Fail || s.appealed) revert Refused();
        Bounty storage bt = _bounties[b];
        if (bt.state != State.Open) revert WrongState(b, bt.state);
        s.appealed = true;
        uint256 fee = _units(config.appealFee);
        if (fee != 0) _collect(coin, msg.sender, fee, config.infrastructure);
        newId = _submit(b, msg.sender, s.commitment);
        _submissions[newId].appealed = true;
    }

    /// The solver withdraws a submission no panel was seated for (waiting, or before its draw): its deposit returns
    /// whole (no counted check was charged; shadows are the pool's).
    function withdraw(uint256 id) external delegated nonReentrant {
        Submission storage s = _submissions[id];
        if (s.solver != msg.sender || s.bounty == 0 || s.outcome != Outcome.None) revert Refused();
        _end(id, Outcome.Withdrawn);
    }

    /// A submission no panel was seated for within resultDays of its commitment ends as timed out, its deposit back:
    /// it can't hold up the queue or the sunset. Anyone.
    function timeOut(uint256 id) external delegated nonReentrant {
        Submission storage s = _submissions[id];
        if (s.bounty == 0 || s.outcome != Outcome.None) revert Refused();
        if (_day() < s.day + config.resultDays) revert NotYet();
        _end(id, Outcome.TimedOut);
    }

    /// A winning fix not claimed by its deadline: nothing is paid and the bounty reopens.
    function mergeExpired(uint256 b) external delegated nonReentrant {
        Bounty storage bt = _bounties[b];
        if (bt.state != State.Won || _day() <= bt.mergeBy) revert NotYet();
        _reopen(b);
    }

    // ---------- challenges and reversals ----------

    /// A challenge of check `id`'s verdict in its window (or held), with `evidence`: the challenger posts the
    /// published stake and its panel's worst-case cost (FeesV3's deposit for K_MAX judges at the check's prices), held
    /// here; Panels draws a larger, fresh panel. One at a time.
    function challenge(uint256 id, bytes32 evidence) external delegated nonReentrant {
        Submission storage s = _submissions[id];
        if (s.solver == address(0) || challenges[id].challenger != address(0)) revert Refused();
        uint256 stake = _units(config.challengeStake);
        uint256 cover = _units(fees.depositFor(id, _repoOf(s), K_MAX));
        (, bool pass,) = _verdict(id);
        if (stake + cover != 0) _hold(coin, msg.sender, stake + cover);
        challenges[id] = Challenge(msg.sender, stake, cover, pass, panels.panelCount());
        panels.challenge(id, msg.sender, evidence);
        emit ChallengeFiled(id, msg.sender);
    }

    /// A filed challenge's panel `cpid` has counted, with its reports in. Upheld (the fix decided the other way, or a
    /// judge's receipt found false), the stake and the cover return and the panel is paid from the check's deposit
    /// (and the pool); rejected, the panel is paid from the cover, its rest returns, and the stake goes to the
    /// challenged panel's judges, in equal shares. The verdict's reversal, if any, follows (`sync`). Anyone.
    function settleChallenge(uint256 id, uint256 cpid) external delegated nonReentrant {
        Challenge memory c = challenges[id];
        bytes memory p = _pan(cpid);
        if (
            c.challenger == address(0) || _w(p, P_ID) != id || Kind(_w(p, P_KIND)) != Kind.Challenge
                || _w(p, P_COUNTED) == 0 || cpid <= c.floor
        ) revert Refused();
        address[] memory keys = panels.judges(cpid);
        _reportsDue(cpid, _w(p, P_REVEAL_BY), keys);
        delete challenges[id];
        panelPaid[cpid] = true;
        Submission storage s = _submissions[id];
        IFeesV3.Report[] memory rs = _reports(cpid, keys);
        uint256[] memory micro = fees.checkCost(id, _repoOf(s), rs);
        bytes memory ps = _sub(id);
        uint256 kc = _w(p, P_K);
        bool upheld = (2 * _w(p, P_PASSES) > kc) != c.wasPass || _falseReceipt(cpid, kc, _w(ps, S_K));
        if (upheld) {
            _release(coin, c.stake + c.cover, c.challenger);
            _payPanel(id, cpid, rs, micro);
        } else {
            uint256 left = c.cover;
            for (uint256 i; i < rs.length; ++i) {
                uint256 a = _units(micro[i]);
                if (a > left) a = left;
                left -= a;
                _release(coin, a, rs[i].payee);
            }
            _release(coin, left, c.challenger);
            _shareStake(_w(ps, S_PID), c.stake);
        }
        emit ChallengeSettled(id, cpid, upheld);
        _sync(id);
    }

    /// The race follows the verdict Panels holds now, after a challenge (filed here, or opened by an auditor) reversed
    /// it: a pass reversed to a fail claws back the bounty's award (nothing was earned before finality) and reopens the
    /// bounty; a fail reversed to a pass wins if the bounty is still open, in its commitment's turn. Anyone.
    function sync(uint256 id) external delegated nonReentrant {
        _sync(id);
    }

    // ---------- the pay of audits, challenge panels and shadows ----------

    /// An audit panel, or the challenge panel of an auditor's challenge, once counted with its reports in: each judge
    /// is paid FeesV3's `checkCost` (the median of the panel's reports, the unscaled service fee) from the check's
    /// deposit, and from the sponsors' pool beyond it. Once a panel. Anyone.
    function payPanel(uint256 pid) external delegated nonReentrant {
        bytes memory p = _pan(pid);
        uint256 id = _w(p, P_ID);
        Kind kind = Kind(_w(p, P_KIND));
        Challenge storage c = challenges[id];
        bool filed = c.challenger != address(0) && pid > c.floor; // its own panel: settleChallenge
        if ((kind != Kind.Audit && kind != Kind.Challenge) || _w(p, P_COUNTED) == 0 || panelPaid[pid] || filed) {
            revert Refused();
        }
        address[] memory keys = panels.judges(pid);
        _reportsDue(pid, _w(p, P_REVEAL_BY), keys);
        panelPaid[pid] = true;
        IFeesV3.Report[] memory rs = _reports(pid, keys);
        _payPanel(id, pid, rs, fees.checkCost(id, _repoOf(_submissions[id]), rs));
        if (kind == Kind.Challenge) _sync(id);
    }

    /// A shadow seat that revealed with its receipt and reported its usage: its capped usage at the check's prices
    /// (FeesV3's `shadowCost`, no service fee) from the sponsors' pool, as far as the pool holds. Once a seat; a family
    /// priced after the check opened is paid nothing (FeesV3 has no price for it at the check's epoch). Anyone.
    function payShadow(uint256 spid, uint256 slot) external delegated nonReentrant {
        bytes memory p = _pan(spid);
        bytes memory x = _seat(spid, slot);
        uint256 bit = 1 << slot;
        if (Kind(_w(p, P_KIND)) != Kind.Shadow || slot >= _w(p, P_K) || shadowsPaid[spid] & bit != 0) revert Refused();
        address key = address(uint160(_w(x, X_KEY)));
        if (_w(x, X_REVEALED) == 0 || _w(x, X_RECEIPTED) == 0 || reportedBy[spid][slot] != key) revert Refused();
        shadowsPaid[spid] |= bit;
        bytes memory v = _val(key);
        uint256 id = _w(p, P_ID);
        try fees.shadowCost(id, _repoOf(_submissions[id]), bytes32(_w(v, V_FAMILY)), _usage[spid][slot]) returns (
            uint256 c
        ) {
            pool.spend(coin, address(uint160(_w(v, V_OPERATOR))), _units(c));
        } catch {}
    }

    // ---------- FeesV3's queue signals, and the deposit's return ----------

    /// From Panels' status now: a waiting submission counts once as waited, a counted panel with an empty seat once as
    /// stalled, and every validator seated on its counted panel as drawn this period (FeesV3 counts each once a
    /// period). Anyone, any time; a keeper calls it after each draw and each replacement.
    function signal(uint256 id) external delegated nonReentrant {
        if (_submissions[id].solver == address(0)) revert Refused();
        bytes memory ps = _sub(id);
        if (Status(_w(ps, S_STATUS)) == Status.Waiting) {
            fees.waited(id);
            return;
        }
        uint256 pid = _w(ps, S_PID);
        if (pid == 0) return;
        bytes memory p = _pan(pid);
        if (_w(p, P_COUNTED) == 0 && _w(p, P_SEATS) < _w(p, P_K)) fees.stalled(id);
        fees.drawn(_seated(panels.judges(pid)));
    }

    /// The deposit's rest back to the solver (or reporter), once its counted judges were paid and its verdict has
    /// been final for REPORT_WINDOW (its audits' and challenge panels' reports are in by then; any paid later come
    /// from the pool). Anyone.
    function finish(uint256 id) external delegated nonReentrant {
        Submission storage s = _submissions[id];
        (Status st,, uint256 finalAt) = _verdict(id);
        if (s.done || !s.paid || st != Status.Final || block.timestamp <= finalAt + REPORT_WINDOW) revert NotYet();
        s.done = true;
        uint256 left = s.deposit;
        s.deposit = 0;
        _release(coin, left, s.solver);
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

    function _payPanel(uint256 id, uint256 pid, IFeesV3.Report[] memory rs, uint256[] memory micro) internal {
        Submission storage s = _submissions[id];
        uint256 dep;
        uint256 fromPool;
        for (uint256 i; i < rs.length; ++i) {
            (uint256 a, uint256 r) = _payExtra(s, rs[i].payee, micro[i]);
            dep += a;
            fromPool += r;
        }
        emit PanelPaid(id, pid, dep, fromPool);
    }

    /// The challenged panel's judges (its filled seats) share a rejected challenge's stake equally; the first takes
    /// the remainder.
    function _shareStake(uint256 pid, uint256 stake) internal {
        if (stake == 0) return;
        address[] memory keys = _seated(panels.judges(pid));
        uint256 n = keys.length;
        uint256 each = stake / n;
        for (uint256 i; i < n; ++i) {
            uint256 a = i == 0 ? stake - each * (n - 1) : each;
            _release(coin, a, address(uint160(_w(_val(keys[i]), V_OPERATOR))));
        }
    }

    /// Whether the challenge panel's majority found one of the challenged panel's receipts false (Panels' rule: more
    /// than half of its seats flag that seat).
    function _falseReceipt(uint256 cpid, uint256 kc, uint256 k) internal view returns (bool) {
        uint256[7] memory flags;
        for (uint256 i; i < kc; ++i) {
            uint256 mask = _w(_seat(cpid, i), X_MASK);
            for (uint256 j; j < k; ++j) {
                if ((mask >> j) & 1 == 1) ++flags[j];
            }
        }
        for (uint256 j; j < k; ++j) {
            if (2 * flags[j] > kc) return true;
        }
        return false;
    }

    function _sync(uint256 id) internal {
        Submission storage s = _submissions[id];
        Outcome o = s.outcome;
        if (o != Outcome.Pass && o != Outcome.Fail) return;
        (, bool pass,) = _verdict(id);
        if (pass == (o == Outcome.Pass)) return;
        s.outcome = pass ? Outcome.Pass : Outcome.Fail;
        emit Decided(id, s.outcome);
        uint256 b = s.bounty;
        if (b == 0) return;
        Bounty storage bt = _bounties[b];
        if (pass) {
            if (bt.state != State.Open) return;
            // ids rise in commitment order: one the queue already passed wins (everything before it is decided and
            // failed); one still ahead waits its turn
            uint256[] storage list = _bySubmission[b];
            if (bt.next == list.length || id < list[bt.next]) _win(b, id);
            else _decide(b);
            return;
        }
        if (bt.winner != id) return;
        if (bt.state == State.Merged) {
            uint256 e = bt.epoch;
            Award storage a = awards[b][e];
            if (a.sub != id || a.closed) return;
            uint256 n = _earned(b, e);
            a.earned = n;
            a.closed = true;
            emit ClawedBack(b, e, n);
        } else if (bt.state != State.Won) {
            return;
        }
        _reopen(b);
    }
}
