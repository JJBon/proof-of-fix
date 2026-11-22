// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {IValidators} from "./IValidators.sol";
import {PanelsDraw} from "./PanelsDraw.sol";
import {PanelsVerdict} from "./PanelsVerdict.sol";
import {PanelsBase, Store, Env, Submission, Panel, Seat, Kind, Tier, Status} from "./PanelsBase.sol";

/// Panels' seats (proof-of-fix#138, task 3.2; design D18, D16): the drawn judges' signed seals, reveals and receipts,
/// and the replacement of a seat that misses a deadline; and the release of rounds that can't complete (#251, L19). A
/// linked library on Panels' `Store`; see Panels for the rules.
library PanelsJudge {
    event Sealed(uint256 indexed pid, address indexed key, bytes32 seal);
    event Revealed(uint256 indexed pid, address indexed key, bool vote, uint8 mask);
    event Receipt(uint256 indexed pid, address indexed key, bytes32 receipt);
    event Mismatch(uint256 indexed pid, address indexed key);
    event Missed(uint256 indexed pid, address indexed key, bool hadSeal);
    event Stalled(uint256 indexed pid, uint256 vacant);
    event Released(uint256 indexed id, uint256 indexed pid, uint256 redraws);
    event Refunded(uint256 indexed id);
    event Waited(uint256 indexed id, uint256 k, uint8 level);
    event ChallengeReleased(uint256 indexed id, uint256 indexed pid, bool lapsed);
    event ChallengeWaits(uint256 indexed id);
    event ChallengeLapsed(uint256 indexed id, uint256 lapses);

    error TooEarly();
    error TooLate();
    error NotOpen();
    error NotSeated();
    error AlreadySealed();
    error NotSealed();
    error AlreadyRevealed();
    error AlreadyReceipted();
    error BadSignature();
    error EmptyHash();
    error NothingDue();
    error NotReady();
    error WrongStatus();

    function seal(Store storage st, Env memory e, uint256 pid, address key, bytes32 sealHash, bytes calldata sig)
        external
    {
        Panel storage p = _live(st, pid);
        Seat storage x = _seatFor(st, pid, key);
        if (x.hasSeal) revert AlreadySealed();
        if (block.timestamp > p.sealBy) revert TooLate();
        if (sealHash == 0) revert EmptyHash();
        _checkSig(e, key, PanelsBase.SEAL_TAG, pid, sealHash, sig);
        x.seal = sealHash;
        x.hasSeal = true;
        ++p.nSealed;
        emit Sealed(pid, key, sealHash);
    }

    function reveal(
        Store storage st,
        Env memory e,
        uint256 pid,
        address key,
        bool vote,
        uint8 mask,
        bytes32 salt,
        bytes calldata sig
    ) external {
        Panel storage p = _live(st, pid);
        Seat storage x = _seatFor(st, pid, key);
        if (!x.hasSeal) revert NotSealed();
        if (x.revealed) revert AlreadyRevealed();
        _inRevealWindow(p);
        _checkSig(e, key, PanelsBase.REVEAL_TAG, pid, keccak256(abi.encode(vote, mask, salt)), sig);
        if (PanelsBase.commitmentOf(pid, key, vote, mask, salt) != x.seal) {
            emit Mismatch(pid, key);
            e.reg.slashFault(key, IValidators.Fault.Mismatch, address(0));
            if (p.kind == Kind.Shadow) {
                x.seal = bytes32(uint256(1)); // no reveal can match it any more: a miss at its deadline
            } else {
                _vacate(st, e, pid, p, st.seatOf[pid][key] - 1, true);
                _refill(st, e, pid, p);
            }
            return;
        }
        x.revealed = true;
        x.vote = vote;
        x.mask = mask;
        emit Revealed(pid, key, vote, mask);
        if (x.receipted) _complete(st, e, pid, p, key);
    }

    function receipt(Store storage st, Env memory e, uint256 pid, address key, bytes32 receiptHash, bytes calldata sig)
        external
    {
        Panel storage p = _live(st, pid);
        Seat storage x = _seatFor(st, pid, key);
        if (!x.hasSeal) revert NotSealed();
        if (x.receipted) revert AlreadyReceipted();
        if (receiptHash == 0) revert EmptyHash();
        _inRevealWindow(p);
        _checkSig(e, key, PanelsBase.RECEIPT_TAG, pid, receiptHash, sig);
        x.receipt = receiptHash;
        x.receipted = true;
        emit Receipt(pid, key, receiptHash);
        if (x.revealed) _complete(st, e, pid, p, key);
    }

    function advance(Store storage st, Env memory e, uint256 pid) external {
        Panel storage p = _live(st, pid);
        if (p.kind == Kind.Shadow) revert NothingDue();
        uint256 k = p.k;
        if (block.timestamp > p.sealBy && p.nSealed < p.seats) {
            for (uint256 i; i < k; ++i) {
                Seat storage x = st.seats[pid][i];
                if (x.key != address(0) && !x.hasSeal) _vacate(st, e, pid, p, i, false);
            }
        } else if (block.timestamp > p.revealBy && p.seats == k && p.nSealed == k) {
            if (p.kind == Kind.Counted && _decided(st, pid, p)) {
                // the revealed votes already decide (owner, 2026-11-13, option 2): the missing seats are slashed and
                // not replaced, so no replacement seals after the reveals are public; the verdict counts as revealed
                for (uint256 i; i < k; ++i) {
                    Seat storage x = st.seats[pid][i];
                    if (!(x.revealed && x.receipted)) _vacate(st, e, pid, p, i, true);
                }
                p.counted = true;
                PanelsVerdict.count(st, e, pid);
                return;
            }
            for (uint256 i; i < k; ++i) {
                Seat storage x = st.seats[pid][i];
                if (!(x.revealed && x.receipted)) _vacate(st, e, pid, p, i, true);
            }
        } else {
            revert NothingDue();
        }
        _refill(st, e, pid, p);
    }

    function refill(Store storage st, Env memory e, uint256 pid) external {
        Panel storage p = _live(st, pid);
        uint256 before = p.seats;
        if (p.kind == Kind.Shadow || before == p.k) revert NothingDue();
        p.snap = PanelsBase.snap(e, st.subs[p.id].bounty);
        _refill(st, e, pid, p);
        if (p.seats == before) revert NotReady();
    }

    // ---------- stuck rounds (#251, design L19; specs/panel-liveness) ----------

    /// A counted or audit panel with a seat its replacements couldn't fill, STUCK_GRACE after its reveal deadline: the
    /// round ends. A seat that never sealed is silent and slashed as any silence (`_vacate`); a seat that sealed (it
    /// couldn't reveal: the reveal window opens only on a full panel) or revealed is closed with no slash. A counted
    /// round sends its submission back to waiting with a redraw scheduled (a fresh seed block and snapshot at the next
    /// `draw`, once the registry changes or at `retryAt`); an audit round makes its audit due again, from a fresh audit
    /// block. Each is one of the submission's MAX_REDRAWS released rounds; the last one refunds it (`_refund`).
    ///
    /// A challenge panel is released the same way (#251 batch 4, L25; specs/panel-liveness, "A stuck challenge panel is
    /// released"), its seats slashed or closed alike; it isn't one of the submission's released rounds. Before the
    /// challenge's CHALLENGE_DEADLINE the challenge waits again, drawn with a fresh seed block and snapshot once the
    /// registry changes or at its retry time (RETRY_DELAY); after it, the challenge lapses (`_lapse`).
    function release(Store storage st, Env memory e, uint256 pid) external {
        Panel storage p = _live(st, pid);
        Kind kind = p.kind;
        uint256 k = p.k;
        if (kind == Kind.Shadow || p.seats == k || block.timestamp <= p.revealBy + e.stuckGrace) revert NothingDue();
        for (uint256 i; i < k; ++i) {
            Seat storage x = st.seats[pid][i];
            address key = x.key;
            if (key == address(0)) continue;
            if (!x.hasSeal) {
                _vacate(st, e, pid, p, i, false);
            } else {
                e.reg.verdictFinal(key);
                if (kind == Kind.Counted && k == 1) PanelsBase.k1Release(st, key);
            }
        }
        p.closed = true;
        uint256 id = p.id;
        Submission storage s = st.subs[id];
        if (kind == Kind.Challenge) {
            s.challengePid = 0;
            bool lapsed = block.timestamp > s.challengeBy;
            emit ChallengeReleased(id, pid, lapsed);
            if (lapsed) return _lapse(st, e, id, s);
            s.challengeEpoch = uint64(e.reg.epoch() + 1);
            s.challengeRetryAt = uint64(block.timestamp + e.retryDelay);
            emit ChallengeWaits(id);
            return;
        }
        emit Released(id, pid, s.redraws + 1);
        if (kind == Kind.Audit) {
            if (s.status != Status.Held && s.status != Status.Window) return; // already refunded: nothing to redraw
            --s.auditsDrawn;
            if (!_round(st, e, id, s)) _retargetAudits(e, s);
            return;
        }
        s.pid = 0;
        s.k = 0;
        s.level = 0;
        if (_round(st, e, id, s)) return;
        s.status = Status.Waiting;
        s.waitEpoch = uint64(e.reg.epoch() + 1);
        s.retryAt = uint64(block.timestamp + e.retryDelay);
        emit Waited(id, 0, 0);
    }

    /// A verdict in its window whose audit no validator could take for STUCK_GRACE (since its audits first found no
    /// auditor in the window, or the last released round): the round is released, and the audit is drawn again from a
    /// fresh audit block; the last of MAX_REDRAWS refunds the submission. Only in the window: while a k = 1 verdict is
    /// held, its hold, not its audits, keeps it from finality, and it ends when the network has grown enough to judge
    /// its challenge (D4), auditors included; the stuck clock restarts when its window starts.
    function releaseAudits(Store storage st, Env memory e, uint256 id) external {
        Submission storage s = st.subs[id];
        if (s.status != Status.Window) revert WrongStatus();
        uint256 since = s.auditStuckAt;
        if (since == 0 || s.challengeOpen || s.auditsDrawn == s.auditsDue || block.timestamp <= since + e.stuckGrace) {
            revert NothingDue();
        }
        emit Released(id, 0, s.redraws + 1);
        if (_round(st, e, id, s)) return;
        _retargetAudits(e, s);
        s.auditStuckAt = uint64(block.timestamp);
    }

    /// An open challenge with no panel past its CHALLENGE_DEADLINE lapses (#251 batch 4, L25; specs/panel-liveness, "A
    /// challenge has a deadline"). Anyone.
    function lapseChallenge(Store storage st, Env memory e, uint256 id) external {
        Submission storage s = st.subs[id];
        if (!s.challengeOpen || s.challengePid != 0) revert WrongStatus();
        if (block.timestamp <= s.challengeBy) revert TooEarly();
        _lapse(st, e, id, s);
    }

    /// A lapse (L25): the verdict stands and its window resumes where it froze, as after a rejected challenge; the
    /// original judges' challenge closes (they can unbond); nobody is slashed. A race-filed challenge is marked
    /// (`filedLapsed`) so the race returns its stake and cover whole, with no reward (RaceV3.settleLapse).
    function _lapse(Store storage st, Env memory e, uint256 id, Submission storage s) private {
        s.challengeOpen = false;
        s.challengePid = 0;
        s.challengeEpoch = 0;
        uint256 n = ++s.lapses;
        if (s.chalFiled) s.filedLapsed = true;
        if (s.status == Status.Window) s.finalAt = uint64(block.timestamp + s.frozenLeft);
        uint256 pid = s.pid;
        for (uint256 i; i < s.k; ++i) {
            address key = st.seats[pid][i].key;
            if (key != address(0)) e.reg.challengeClosed(key);
        }
        emit ChallengeLapsed(id, n);
    }

    /// The race's deadline (RaceV3's resultDays after the commitment) for a submission with a released round that is
    /// parked: waiting, before its seed, or a verdict whose audits are due with none drawn and no challenge open.
    function abandon(Store storage st, Env memory e, uint256 id) external {
        Submission storage s = st.subs[id];
        Status x = s.status;
        bool parked = x == Status.Waiting || x == Status.Sealed
            || ((x == Status.Held || x == Status.Window) && !s.challengeOpen && s.auditsDrawn < s.auditsDue);
        if (s.redraws == 0 || !parked) revert WrongStatus();
        _refund(st, e, id, s);
    }

    /// One more released round: the last of MAX_REDRAWS refunds the submission (returns true).
    function _round(Store storage st, Env memory e, uint256 id, Submission storage s) private returns (bool) {
        if (++s.redraws < e.maxRedraws) return false;
        _refund(st, e, id, s);
        return true;
    }

    /// Never judged: `Released`, the race refunds the bounty (RaceV3.release). A counted verdict's judges' verdicts close
    /// unscored. A constitution-tier submission expires instead, its deposit refunded.
    function _refund(Store storage st, Env memory e, uint256 id, Submission storage s) private {
        if (s.status == Status.Held || s.status == Status.Window) {
            uint256 pid = s.pid;
            uint256 k = s.k;
            for (uint256 i; i < k; ++i) {
                address key = st.seats[pid][i].key;
                if (key == address(0)) continue;
                e.reg.verdictFinal(key);
                if (k == 1) PanelsBase.k1Release(st, key);
            }
        }
        if (s.tier != Tier.Issue) return PanelsBase.expire(e, id, s);
        s.status = Status.Released;
        emit Refunded(id);
    }

    function _retargetAudits(Env memory e, Submission storage s) private {
        s.auditWaits = false;
        s.auditBlock = uint64(block.number + PanelsBase.SEED_DELAY);
        s.auditSnap = PanelsBase.snap(e, s.bounty);
        s.auditEpoch = uint64(e.reg.epoch() + 1);
    }

    // ---------- internals ----------

    /// A miss: the registry slashes and counts it, the seat's verdict closes, and the seat empties.
    function _vacate(Store storage st, Env memory e, uint256 pid, Panel storage p, uint256 i, bool hasSeal) private {
        Seat storage x = st.seats[pid][i];
        address key = x.key;
        e.reg.recordCounted(key, hasSeal, false);
        e.reg.verdictFinal(key);
        if (p.kind == Kind.Counted && p.k == 1) PanelsBase.k1Release(st, key);
        st.seatOf[pid][key] = PanelsBase.GONE;
        if (x.hasSeal) --p.nSealed;
        --p.seats;
        delete st.seats[pid][i];
        emit Missed(pid, key, hasSeal);
    }

    /// Fills the empty seats from the same sample (the snapshot's tries a seat), never with a validator that already
    /// sat on the panel (or its original panel) nor, on a counted panel, one that would leave it too weak for its
    /// bounty; a seat filled restarts the panel's windows.
    function _refill(Store storage st, Env memory e, uint256 pid, Panel storage p) private {
        uint256 k = p.k;
        uint256 have = p.seats;
        if (have == k) return;
        PanelsDraw.Ctx memory c = PanelsBase.ctx(st, e, p.id, st.subs[p.id].bounty, p.seed, p.snap, pid, p.ex);
        c.counter = p.counter;
        c.k = k;
        c.k1Cap = p.kind == Kind.Counted;
        c.levelCheck = p.kind == Kind.Counted;
        for (uint256 i; i < k; ++i) {
            Seat storage x = st.seats[pid][i];
            if (x.key == address(0)) continue;
            IValidators.Validator memory v = e.reg.validator(x.key);
            c.members[c.m++] = PanelsDraw.Member(x.key, v.operator, v.host, v.family, v.teeType, x.level);
        }
        c = PanelsDraw.fill(c, PanelsDraw.tries(c.snap) * (k - have), st.seatOf, st.k1Pending, st.k1FreedAt, st.load);
        p.counter = uint32(c.counter);
        if (c.unpriced != address(0)) PanelsBase.announce(e, c.unpriced);
        if (c.m > have) {
            PanelsBase.resetTimeline(e, p);
            uint256 j = have;
            for (uint256 i; i < k && j < c.m; ++i) {
                if (st.seats[pid][i].key == address(0)) {
                    PanelsBase.seat(st, e, pid, p, i, c.members[j].key, c.members[j].level);
                    ++j;
                }
            }
        }
        if (p.seats < k) emit Stalled(pid, k - p.seats);
    }

    /// At a missed reveal on a counted panel: whether the votes revealed with receipts already decide the outcome
    /// whatever the missing ones would be ((k + 1) / 2 on one side; at the constitution tier CONSTITUTION_QUORUM passes,
    /// or more than k - CONSTITUTION_QUORUM fails), and, at the issue tier, the revealed judges' level still covers the
    /// bounty (else a replacement keeps the panel strong enough, as at the draw).
    function _decided(Store storage st, uint256 pid, Panel storage p) private view returns (bool) {
        uint256 k = p.k;
        PanelsDraw.Member[] memory ms = new PanelsDraw.Member[](k);
        uint256 m;
        uint256 passes;
        for (uint256 i; i < k; ++i) {
            Seat storage x = st.seats[pid][i];
            if (!(x.revealed && x.receipted)) continue;
            if (x.vote) ++passes;
            ms[m++].level = x.level;
        }
        uint256 fails = m - passes;
        Submission storage s = st.subs[p.id];
        if (s.tier != Tier.Issue) {
            return passes >= PanelsBase.CONSTITUTION_QUORUM || fails > k - PanelsBase.CONSTITUTION_QUORUM;
        }
        if (2 * passes <= k && 2 * fails <= k) return false;
        return PanelsDraw.limitOf(k, PanelsDraw.levelOf(ms, m, k)) >= s.bounty;
    }

    function _complete(Store storage st, Env memory e, uint256 pid, Panel storage p, address key) private {
        Kind kind = p.kind;
        if (kind != Kind.Shadow) e.reg.recordCounted(key, true, true);
        if (++p.done < p.k || kind == Kind.Shadow) return;
        p.counted = true;
        PanelsVerdict.count(st, e, pid);
    }

    function _live(Store storage st, uint256 pid) private view returns (Panel storage p) {
        p = st.panels[pid];
        if (p.k == 0 || p.counted || p.closed) revert NotOpen();
    }

    function _seatFor(Store storage st, uint256 pid, address key) private view returns (Seat storage) {
        uint8 slot = st.seatOf[pid][key];
        if (slot == 0 || slot == PanelsBase.GONE) revert NotSeated();
        return st.seats[pid][slot - 1];
    }

    /// The reveal window: the seal window over and the reveal window not; on a judging panel, every seat filled and
    /// sealed first (shadows reveal on their own).
    function _inRevealWindow(Panel storage p) private view {
        if (block.timestamp <= p.sealBy) revert TooEarly();
        if (p.kind != Kind.Shadow && (p.seats < p.k || p.nSealed < p.k)) revert TooEarly();
        if (block.timestamp > p.revealBy) revert TooLate();
    }

    function _checkSig(Env memory e, address key, bytes32 tag, uint256 pid, bytes32 content, bytes calldata sig)
        private
        view
    {
        bytes32 digest = PanelsBase.statementDigest(e.domain, PanelsBase.subjectOf(tag, pid, key), content);
        if (ECDSA.recover(digest, sig) != key) revert BadSignature();
    }
}
