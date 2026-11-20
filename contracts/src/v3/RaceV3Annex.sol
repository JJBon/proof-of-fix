// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {RaceV3Base} from "./RaceV3Base.sol";
import {RaceV3Endings} from "./RaceV3Endings.sol";
import {Heads} from "../v2/Heads.sol";
import {IFeesV3} from "./IFeesV3.sol";
import {IValidators} from "./IValidators.sol";
import {Panels} from "./Panels.sol";
import {PoolV3} from "./PoolV3.sol";
import {Status, Kind} from "./PanelsBase.sol";

/// RaceV3's rarely called actions (proof-of-fix#138, task 3.5; v2's EIP-170 split, RaceV2Annex): registration and the
/// registration check's outcome, appeals, challenges, reversals, the pay of audits, challenge panels and shadows,
/// FeesV3's queue signals and the deposit's return. It's deployed first, with the race's Panels, pool, start and caps
/// (its `fingerprint`, which RaceV3's constructor checks), and RaceV3 delegates those calls here (DELEGATECALL), so
/// they run in RaceV3's storage, with its balances and its caller. Called directly, they refuse: this contract's own
/// storage holds nothing. Each is described on RaceV3.
///
/// **A second companion (#251, contract batch 2).** The endings (withdrawals, time-outs, expired merges and L19's
/// release) run in RaceV3Endings. A call this annex doesn't have goes on to it (`fallback`, one more DELEGATECALL,
/// still in the race's storage). Since contract batch 3 the endings are deployed first, on their own (EIP-3860: this
/// annex's initcode can't hold them any more), and passed to this annex's constructor, which checks their
/// fingerprint; they also run registration, the opening of a bounty, the judges' reports, shadows' pay, FeesV3's
/// signals and the deposit's return.
contract RaceV3Annex is RaceV3Base {
    /// This contract's own address: called directly (not through a race's DELEGATECALL), its actions refuse.
    address internal immutable self;
    /// The endings' companion, deployed here.
    address public immutable endings;

    /// Deployed before its RaceV3 with the same parameters (`start_` nonzero), after its endings (`endings_`, built
    /// with the same parameters: its fingerprint must be this annex's); the race checks `fingerprint`.
    constructor(
        Config memory config_,
        uint256 bountyCap_,
        uint256 totalCap_,
        Panels panels_,
        PoolV3 pool_,
        uint256 start_,
        RaceV3Endings endings_
    )
        RaceV3Base(config_, bountyCap_, totalCap_, panels_, pool_, Heads(address(0)), start_)
    {
        if (start_ == 0) revert BadParams();
        if (address(endings_).code.length == 0 || endings_.fingerprint() != _fingerprint()) revert BadParams();
        self = address(this);
        endings = address(endings_);
    }

    /// The endings' calls (RaceV3Endings), run in the race's storage like this annex's own.
    fallback() external {
        if (address(this) == self) revert Refused();
        address target = endings;
        assembly ("memory-safe") {
            calldatacopy(0, 0, calldatasize())
            let ok := delegatecall(gas(), target, 0, calldatasize(), 0, 0)
            returndatacopy(0, 0, returndatasize())
            if iszero(ok) { revert(0, returndatasize()) }
            return(0, returndatasize())
        }
    }

    modifier delegated() {
        if (address(this) == self) revert Refused();
        _;
    }

    /// The Panels, pool, start and caps this companion was built with (its immutables), for its race to check.
    function fingerprint() external view returns (bytes32) {
        return _fingerprint();
    }

    // ---------- submissions ----------

    /// The author of a rejected fix appeals once (#132 D24), while the bounty is open and within APPEAL_WINDOW of its
    /// counted panel's reveal deadline, with `test` (the hash of a test that fails on the base code and passes with the
    /// fix: the appeal panel's judges run it, and the checker image's run decides nothing on-chain). No stake (owner,
    /// 2026-11-19): the appeal fee (0 on Sepolia), and the same commitment judged again as a new submission with its
    /// own deposit or flat fee, so the appellant pays the appeal panel's metered checks (the rest refunded under the
    /// taxi fare); drawn fresh from the seated families with the original judges not excluded. Its claim replaces the
    /// rejected one's under the cap.
    function appeal(uint256 id, bytes32 test) external delegated nonReentrant returns (uint256 newId) {
        Submission storage s = _submissions[id];
        uint256 b = s.bounty;
        if (b == 0 || test == 0 || s.solver != msg.sender || s.outcome != Outcome.Fail || s.appealed) revert Refused();
        Bounty storage bt = _bounties[b];
        if (bt.state != State.Open) revert WrongState(b, bt.state);
        if (block.timestamp > _w(_pan(_w(_sub(id), S_PID)), P_REVEAL_BY) + panels.APPEAL_WINDOW()) revert AppealClosed();
        s.appealed = true;
        uint256 fee = _units(config.appealFee);
        if (fee != 0) _collect(coin, msg.sender, fee, config.infrastructure);
        book.closeClaim(id);
        newId = _submit(b, msg.sender, s.commitment);
        _submissions[newId].appealed = true;
        emit Appealed(id, newId, test);
    }

    /// Once check `id`'s verdict is final, or it ended unjudged: its open claim closes, and a reversed pass is charged to
    /// its solver's reputation if nobody had it recorded. Anyone; `finish`, the merge and the endings close claims too.
    function close(uint256 id) external delegated nonReentrant {
        Submission storage s = _submissions[id];
        if (s.bounty == 0) revert Refused();
        Outcome o = s.outcome;
        (Status st,,) = _verdict(id);
        bool ended = o == Outcome.Withdrawn || o == Outcome.TimedOut || o == Outcome.Released || o == Outcome.Duplicate;
        if ((st != Status.Final && !ended) || book.claimOf(id).solver == address(0)) revert NotYet();
        _penalize(id);
        book.closeClaim(id);
    }

    // ---------- challenges and reversals ----------

    /// A challenge of check `id`'s verdict in its window (or held), with `evidence`: the challenger posts the
    /// published stake and its panel's worst-case cost (FeesV3's deposit for K_MAX judges at the check's prices), held
    /// here; Panels draws a larger, fresh panel. One at a time.
    function challenge(uint256 id, bytes32 evidence) external delegated nonReentrant {
        _file(id, evidence, _units(config.challengeStake), false);
    }

    /// A failing-test dispute (#132 D21) of check `id`'s pass in its window (or held): `test` is the hash of a test that
    /// fails on the fixed code (the challenge panel's judges run it and decide whether it states what the issue asks
    /// for). The stake is the larger of $5 and 10 % of the bounty, beside its panel's worst-case cost. Upheld (the panel
    /// fails the fix), the disputer gets both back and EVIDENCE_REWARD_BPS of the bounty from its pot, and counts as an
    /// active solver if it has a merged fix; rejected, its stake goes to the solver. Fixes only; one challenge at a time.
    function dispute(uint256 id, bytes32 test) external delegated nonReentrant {
        (, bool pass,) = _verdict(id);
        if (_submissions[id].bounty == 0 || test == 0 || !pass) revert Refused();
        _file(id, test, _stakeOf(id), true);
        emit Disputed(id, msg.sender, test, challenges[id].stake);
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
        bool upheld = (2 * _w(p, P_PASSES) > kc) != c.wasPass || (!c.test && _falseReceipt(cpid, kc, _w(ps, S_K)));
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
            if (c.test) _release(coin, c.stake, s.solver); // a rejected test dispute's stake pays the solver's delay
            else _shareStake(_w(ps, S_PID), c.stake);
        }
        emit ChallengeSettled(id, cpid, upheld);
        Bounty storage bt = _bounties[s.bounty];
        bool won = s.bounty != 0 && bt.winner == id && (bt.state == State.Won || bt.state == State.Merged);
        _sync(id);
        if (upheld && c.test) _reward(id, c.challenger, won);
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

    // ---------- internals ----------

    /// A challenge (`test`: a failing-test dispute) filed by the caller with `stake` and its panel's cover, held here.
    function _file(uint256 id, bytes32 evidence, uint256 stake, bool test) internal {
        Submission storage s = _submissions[id];
        if (s.solver == address(0) || challenges[id].challenger != address(0)) revert Refused();
        uint256 cover = _units(fees.depositFor(id, _repoOf(s), K_MAX));
        (, bool pass,) = _verdict(id);
        if (stake + cover != 0) _hold(coin, msg.sender, stake + cover);
        challenges[id] = Challenge(msg.sender, stake, cover, pass, panels.panelCount(), test);
        panels.challenge(id, msg.sender, evidence);
        emit ChallengeFiled(id, msg.sender);
    }

    /// An upheld test dispute's reward (D21): EVIDENCE_REWARD_BPS of the bounty the fix was judged at, from the
    /// bounty's pot when the reversed fix had won it (the pot then pays no award), never from the solver; and the
    /// disputer is active if it has a merged fix in the repository (launch L6).
    function _reward(uint256 id, address to, bool won) internal {
        book.disputeUpheld(to);
        uint256 b = _submissions[id].bounty;
        uint256 r;
        if (won) {
            r = _units(_submissions[id].judged * EVIDENCE_REWARD_BPS / BPS);
            uint256 h = held(b, coin);
            if (r > h) r = h;
            if (r != 0) {
                _touch(b, coin);
                _pay(b, coin, to, r);
            }
        }
        emit DisputeRewarded(id, to, r);
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
        _penalize(id); // a reversed pass costs its solver's reputation (D29)
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
