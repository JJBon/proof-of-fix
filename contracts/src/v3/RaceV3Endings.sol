// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {RaceV3Base} from "./RaceV3Base.sol";
import {IFeesV3} from "./IFeesV3.sol";
import {Heads} from "../v2/Heads.sol";
import {Panels} from "./Panels.sol";
import {PoolV3} from "./PoolV3.sol";
import {Status, Kind} from "./PanelsBase.sol";

/// RaceV3's endings (proof-of-fix#251, contract batch 2; the EIP-170 split of RaceV3Annex): withdrawals, time-outs,
/// expired merges, and the refund of a check Panels couldn't judge (design L19); since batch 3 also registration and
/// the opening of a bounty, the judges' reports, shadows' pay, FeesV3's signals and the deposit's return. It is deployed
/// first, with the race's parameters; RaceV3Annex takes it at construction (checking its fingerprint) and reaches it for
/// any call it doesn't have (its fallback), so these run in RaceV3's storage, with its balances and its caller, after
/// two DELEGATECALLs. Called directly, they refuse. Each is described on RaceV3.
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
        if (start_ == 0) revert BadParams();
        self = address(this);
    }

    /// The Panels, pool, start and caps these endings were built with, for their annex to check.
    function fingerprint() external view returns (bytes32) {
        return _fingerprint();
    }

    modifier delegated() {
        if (address(this) == self) revert Refused();
        _;
    }

    // ---------- issues (moved from the annex, batch 3: EIP-170) ----------

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

    /// Anyone registers an issue in `repo`, which must be the deployment's one repository (#251, L1: the head registry
    /// holds only it; another id or zero is refused, so no bounty is won without moving the head): the registration
    /// fee, the issue stake and its registration check's deposit. Panels judges the check; its final pass opens the
    /// bounty and its final fail forfeits the stake (`openBounty`).
    function register(bytes32 repo, bool hidden) external delegated nonReentrant returns (uint256 id) {
        if (repo == bytes32(0) || !heads.isRepo(repo)) revert Refused();
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

    // ---------- shadows' pay (moved from the annex, batch 3) ----------

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

    // ---------- FeesV3's queue signals, and the deposit's return (moved from the annex, batch 3) ----------

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
        _rest(id, false); // back to the solver; a fix's flat judges' fee's rest (judgeFee above 0) to the pool
        _penalize(id);
        book.closeClaim(id);
    }

    // ---------- issues: withdrawal ----------

    /// The reporter withdraws an issue whose check no panel was seated for: its stake and deposit return; the
    /// registration fee stays spent.
    function withdrawIssue(uint256 issueId) external delegated nonReentrant {
        Issue storage i = _issues[issueId];
        if (i.reporter != msg.sender || i.state != IssueState.Posted || i.bounty != 0) revert Refused();
        _end(i.check, Outcome.Withdrawn);
        _closeIssue(issueId, IssueState.Returned, msg.sender);
    }

    // ---------- submissions ----------

    /// The solver withdraws a submission no panel was seated for (waiting, or before its draw): no counted check was
    /// charged (shadows are the pool's), so under the taxi fare (`judgeFee` 0) its whole deposit returns; a flat
    /// judges' fee (`judgeFee` above 0) goes to the sponsors' pool whole (D30's "A withdrawn submission").
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
        book.closeClaim(a.sub); // final, never merged: its claim closes, nothing joins the reputation
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
        _rest(id, true); // never judged: the rest of its fee returns, and its claim closes with no reputation lost
        book.closeClaim(id);
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

    /// Panels withdraws the check (only before a panel is seated). Its whole deposit returns, except, under a flat
    /// judges' fee, a withdrawn fix's fee, which goes to the sponsors' pool (D30: the fee isn't returned, and no
    /// per-check charge is made); a timed-out fix was never seated, so it gets its fee back as a released one does. Its
    /// claim closes.
    function _end(uint256 id, Outcome o) internal {
        panels.withdraw(id);
        _rest(id, o != Outcome.Withdrawn);
        book.closeClaim(id);
        _decided(id, o);
    }

    // ---------- the judges' reports (moved from RaceV3, batch 3: EIP-170) ----------

    /// Seat `key`'s metered usage on panel `pid` (any kind), signed by `key` as a registry statement on the subject
    /// keccak256(USAGE_TAG, this race, pid, key) over keccak256(abi.encode(u)) (two usages for one seat are provable
    /// equivocation). Its receipt must be the seat's on-chain receipt. A replacement in the same seat reports its own.
    function report(uint256 pid, address key, IFeesV3.Usage calldata u, bytes calldata sig) external delegated {
        address[] memory keys = panels.judges(pid);
        uint256 slot = keys.length;
        for (uint256 i; i < keys.length; ++i) {
            if (keys[i] == key && key != address(0)) slot = i;
        }
        if (slot == keys.length || reportedBy[pid][slot] == key) revert Refused();
        bytes memory x = _seat(pid, slot);
        if (_w(x, X_RECEIPTED) == 0 || bytes32(_w(x, X_RECEIPT)) != u.receipt) revert Refused();
        bytes32 subject = keccak256(abi.encode(USAGE_TAG, address(this), pid, key));
        if (ECDSA.recover(registry.statementDigest(subject, keccak256(abi.encode(u))), sig) != key) {
            revert BadSignature();
        }
        _usage[pid][slot] = u;
        reportedBy[pid][slot] = key;
        emit Reported(pid, slot, key, u.receipt);
    }
}
