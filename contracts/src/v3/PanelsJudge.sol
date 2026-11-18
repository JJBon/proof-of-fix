// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {IValidators} from "./IValidators.sol";
import {PanelsDraw} from "./PanelsDraw.sol";
import {PanelsVerdict} from "./PanelsVerdict.sol";
import {PanelsBase, Store, Env, Submission, Panel, Seat, Kind, Tier} from "./PanelsBase.sol";

/// Panels' seats (proof-of-fix#138, task 3.2; design D18, D16): the drawn judges' signed seals, reveals and receipts,
/// and the replacement of a seat that misses a deadline. A linked library on Panels' `Store`; see Panels for the rules.
library PanelsJudge {
    event Sealed(uint256 indexed pid, address indexed key, bytes32 seal);
    event Revealed(uint256 indexed pid, address indexed key, bool vote, uint8 mask);
    event Receipt(uint256 indexed pid, address indexed key, bytes32 receipt);
    event Mismatch(uint256 indexed pid, address indexed key);
    event Missed(uint256 indexed pid, address indexed key, bool hadSeal);
    event Stalled(uint256 indexed pid, uint256 vacant);

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
        c = PanelsDraw.fill(c, PanelsDraw.tries(c.snap) * (k - have), st.seatOf, st.k1Pending, st.k1FreedAt);
        p.counter = uint32(c.counter);
        if (c.unpriced != address(0)) PanelsBase.announce(e, c.unpriced);
        if (c.m > have) {
            PanelsBase.resetTimeline(p);
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
