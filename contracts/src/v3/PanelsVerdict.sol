// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {IValidators} from "./IValidators.sol";
import {IPanelsHost} from "./IPanels.sol";
import {PanelsDraw} from "./PanelsDraw.sol";
import {PanelsBase, Store, Env, Submission, Panel, Seat, Status, Tier, Kind} from "./PanelsBase.sol";

/// Panels' verdicts (proof-of-fix#138, task 3.2; design D2–D5, D7, D13, D14): the draws of counted, shadow, audit and
/// challenge panels, the count, the hold and the window, audits, challenges, the shadows' scores and finality. A
/// linked library on Panels' `Store`; see Panels for the rules.
library PanelsVerdict {
    event Held(uint256 indexed id);
    event Counted(uint256 indexed id, uint256 indexed pid, bool pass, uint256 passes, uint8 level);
    event WindowStarted(uint256 indexed id, uint256 finalAt);
    event ShadowScored(uint256 indexed pid, address indexed key, bool agreed);
    event AuditsDecided(uint256 indexed id, uint256 due);
    event AuditWaits(uint256 indexed id, uint256 auditBlock);
    event Audited(uint256 indexed id, uint256 indexed pid, address indexed auditor, bool agrees);
    event ChallengeOpened(uint256 indexed id, address indexed challenger, bytes32 evidence);
    event ChallengeWaits(uint256 indexed id);
    event SecondDraw(uint256 indexed id, uint256 indexed pid);
    event ChallengeResolved(uint256 indexed id, uint256 indexed pid, bool upheld, bool pass, bool falseReceipt);
    event Final(uint256 indexed id, bool pass);

    error WrongStatus();
    error TooEarly();
    error NothingChanged();
    error NothingDue();
    error NotReady();

    // ---------- the draws ----------

    /// A waiting submission is drawn again (a fresh seed block and snapshot) once the registry changed or at its
    /// `retryAt` (#251, L19): RETRY_DELAY after it began waiting, or the capacity's window when a full or paused
    /// validator was skipped (L16), whichever comes first. So every waiting submission has a scheduled redraw.
    function draw(Store storage st, Env memory e, uint256 id) external {
        Submission storage s = st.subs[id];
        if (s.status == Status.Waiting) {
            if (e.reg.epoch() + 1 == s.waitEpoch && block.timestamp < s.retryAt) revert NothingChanged();
            return _retarget(e, id, s);
        }
        if (s.status != Status.Sealed) revert WrongStatus();
        bytes32 bh = PanelsBase.hashOf(s.seedBlock);
        if (bh == 0) return _retarget(e, id, s);
        bytes32 seed = keccak256(abi.encode(bh, s.commitment, s.bounty, id));
        bool con = s.tier != Tier.Issue;
        if (con && s.snap.nLive < PanelsBase.minEligible(s.tier)) return PanelsBase.expire(e, id, s);
        (PanelsDraw.Ctx memory c, uint256 k, uint8 level) = PanelsBase.drawCounted(st, e, id, seed);
        if (c.unpriced != address(0)) PanelsBase.announce(e, c.unpriced);
        if (k == 0 || PanelsDraw.limitOf(k, level) < s.bounty) {
            if (con) return PanelsBase.expire(e, id, s);
            s.status = Status.Waiting;
            s.waitEpoch = uint64(e.reg.epoch() + 1);
            s.retryAt = uint64(block.timestamp + (c.full ? e.capWindow : e.retryDelay));
            emit PanelsBase.Waited(id, k, level);
            uint256 sp = s.shadowPid;
            if (sp == 0 || st.panels[sp].closed) {
                _drawShadows(st, e, id, 0, seed, PanelsBase.SHADOW_PER_WAITING, block.timestamp + e.seal);
            }
            return;
        }
        (uint256 pid, Panel storage p) = PanelsBase.newPanel(st, e, id, Kind.Counted, seed, k, 0, s.snap, c.counter);
        for (uint256 i; i < k; ++i) {
            PanelsBase.seat(st, e, pid, p, i, c.members[i].key, c.members[i].level);
        }
        s.status = Status.Judging;
        s.k = uint8(k);
        s.level = level;
        s.pid = uint64(pid);
        uint256 n = e.reg.activeCount() < PanelsBase.K_MAX ? PanelsBase.SHADOW_PER_DRAW_SMALL : PanelsBase.SHADOW_PER_DRAW;
        _drawShadows(st, e, id, pid, seed, n, p.sealBy);
    }

    /// #251 task 3.10 (open problems 7.5): repeat calls are refused. A draw that finds no auditor re-targets (a fresh
    /// audit block and snapshot) only if the registry changed since its snapshot was taken (`auditEpoch`); otherwise the
    /// audits wait (`auditWaits`), and every call is refused until the registry changes, as a waiting submission's
    /// `draw` and a waiting challenge's `drawChallenge` are. Then one call re-targets and the next, from the new audit
    /// block, draws. So nobody can roll fresh audit blocks at will.
    function drawAudits(Store storage st, Env memory e, uint256 id) external {
        Submission storage s = st.subs[id];
        if (s.status != Status.Held && s.status != Status.Window) revert WrongStatus();
        if (s.auditDecided && s.auditsDrawn == s.auditsDue) revert NothingDue();
        if (s.auditWaits) {
            if (e.reg.epoch() + 1 == s.auditEpoch) revert NothingChanged();
            s.auditWaits = false;
            return _retargetAudits(e, id, s);
        }
        bytes32 bh = PanelsBase.hashOf(s.auditBlock);
        if (bh != 0) {
            bytes32 base = keccak256(abi.encode(bh, st.panels[s.pid].seed, "audit"));
            if (!s.auditDecided) {
                s.auditDecided = true;
                if (uint256(base) % 10_000 < PanelsBase.AUDIT_RATE_BPS && !_splitC(s, st.panels[s.pid])) ++s.auditsDue;
                emit AuditsDecided(id, s.auditsDue);
            }
            bool full;
            while (s.auditsDrawn < s.auditsDue) {
                PanelsDraw.Ctx memory c = PanelsBase.ctx(
                    st, e, id, s.bounty, keccak256(abi.encode(base, s.auditsDrawn)), s.auditSnap, st.panelCount + 1, s.pid
                );
                c.k = 1;
                c = PanelsDraw.fill(c, PanelsDraw.tries(c.snap), st.seatOf, st.k1Pending, st.k1FreedAt, st.load);
                if (c.unpriced != address(0)) PanelsBase.announce(e, c.unpriced);
                full = c.full;
                if (c.m == 0) break;
                s.auditStuckAt = 0;
                (uint256 apid, Panel storage ap) =
                    PanelsBase.newPanel(st, e, id, Kind.Audit, c.seed, 1, s.pid, s.auditSnap, c.counter);
                PanelsBase.seat(st, e, apid, ap, 0, c.members[0].key, c.members[0].level);
                ++s.auditsDrawn;
            }
            if (s.auditsDrawn == s.auditsDue) return;
            // no auditor: the audits are stuck from now (L19: Panels.releaseAudits after STUCK_GRACE)
            if (s.auditStuckAt == 0) s.auditStuckAt = uint64(block.timestamp);
            if (full) return; // busy auditors: retried from the same audit block once they have room (L16)
            if (e.reg.epoch() + 1 == s.auditEpoch) {
                s.auditWaits = true; // no auditor in a snapshot of the registry as it is: wait for it to change
                emit AuditWaits(id, s.auditBlock);
                return;
            }
        }
        _retargetAudits(e, id, s); // the snapshot is older than the registry, or the audit block is gone
    }

    function _retargetAudits(Env memory e, uint256 id, Submission storage s) private {
        s.auditBlock = uint64(block.number + PanelsBase.SEED_DELAY);
        s.auditSnap = PanelsBase.snap(e, s.bounty);
        s.auditEpoch = uint64(e.reg.epoch() + 1);
        emit AuditWaits(id, s.auditBlock);
    }

    function drawChallenge(Store storage st, Env memory e, uint256 id) external {
        Submission storage s = st.subs[id];
        if (!s.challengeOpen || s.challengePid != 0) revert WrongStatus();
        if (s.challengeEpoch != 0) {
            if (e.reg.epoch() + 1 == s.challengeEpoch) revert NothingChanged();
            s.challengeEpoch = 0;
            return _retargetChallenge(e, s);
        }
        bytes32 bh = PanelsBase.hashOf(s.challengeBlock);
        if (bh == 0) return _retargetChallenge(e, s);
        bytes32 seed = keccak256(abi.encode(bh, s.commitment, id, "challenge"));
        uint256 k = s.k;
        PanelsDraw.Ctx memory c = PanelsBase.ctx(st, e, id, s.bounty, seed, s.challengeSnap, st.panelCount + 1, s.pid);
        c.kTop = PanelsBase.challengeK(k);
        c.kMin = k == PanelsBase.K_MAX ? PanelsBase.K_MAX : k + 2;
        uint256 kc;
        (c, kc,) = PanelsDraw.drawPanel(c, st.seatOf, st.k1Pending, st.k1FreedAt, st.load);
        if (c.unpriced != address(0)) PanelsBase.announce(e, c.unpriced);
        uint256 ex = s.pid;
        if (kc == 0) {
            if (c.full) return; // busy validators: retried from the same seed once they have room (L16)
            if (!c.famCap && k > 1) {
                // #132 D27 (`SECOND_PANEL` "few families"): while fewer than CAP_MIN_FAMILIES families can judge (at
                // the snapshot), a challenge that can't draw its larger fresh panel is judged by a second draw of the
                // original panel's size, the original judges not excluded. It ends the wait; it corrects nothing. Not
                // for k = 1: a second draw of one could seat the lone judge on its own verdict, and the k = 1 hold
                // already waits for CHALLENGE_K[1] challengers (D4).
                c = PanelsBase.ctx(st, e, id, s.bounty, seed, s.challengeSnap, st.panelCount + 1, 0);
                c.kTop = k;
                c.kMin = k;
                (c, kc,) = PanelsDraw.drawPanel(c, st.seatOf, st.k1Pending, st.k1FreedAt, st.load);
                if (kc == 0 && c.full) return;
                ex = 0;
                if (kc != 0) emit SecondDraw(id, st.panelCount + 1);
            }
            if (kc == 0) {
                s.challengeEpoch = uint64(e.reg.epoch() + 1);
                emit ChallengeWaits(id);
                return;
            }
        }
        (uint256 cpid, Panel storage cp) =
            PanelsBase.newPanel(st, e, id, Kind.Challenge, seed, kc, ex, s.challengeSnap, c.counter);
        for (uint256 i; i < kc; ++i) {
            PanelsBase.seat(st, e, cpid, cp, i, c.members[i].key, c.members[i].level);
        }
        s.challengePid = uint64(cpid);
    }

    // ---------- challenges, the window, finality ----------

    /// Opens a challenge (the race's, or an auditor's mismatch): its seed block and snapshot are fixed now, the
    /// window freezes, and the original judges can't unbond until it closes.
    function openChallenge(Store storage st, Env memory e, uint256 id, address challenger, bytes32 evidence) public {
        Submission storage s = st.subs[id];
        s.challengeOpen = true;
        s.challenger = challenger;
        _retargetChallenge(e, s);
        if (s.status == Status.Window) {
            s.frozenLeft = s.finalAt > block.timestamp ? uint64(s.finalAt - block.timestamp) : 0;
        }
        uint256 pid = s.pid;
        for (uint256 i; i < s.k; ++i) {
            address key = st.seats[pid][i].key;
            if (key != address(0)) e.reg.challengeOpened(key);
        }
        emit ChallengeOpened(id, challenger, evidence);
    }

    function startWindow(Store storage st, Env memory e, uint256 id) external {
        Submission storage s = st.subs[id];
        if (s.status != Status.Held) revert WrongStatus();
        if (!_challengersReady(st, e, id, s)) revert NotReady();
        _startWindow(e, id, s);
    }

    function finalize(Store storage st, Env memory e, uint256 id) external {
        Submission storage s = st.subs[id];
        if (s.status != Status.Window) revert WrongStatus();
        if (block.timestamp < s.finalAt) revert TooEarly();
        if (s.challengeOpen || !s.auditDecided || s.auditsDone < s.auditsDue) revert NotReady();
        s.status = Status.Final;
        uint256 pid = s.pid;
        uint256 k = s.k;
        bool pass = s.pass;
        for (uint256 i; i < k; ++i) {
            Seat storage x = st.seats[pid][i];
            address key = x.key;
            if (key == address(0)) continue; // a reveal missed after the majority revealed: closed at the count
            e.reg.verdictFinal(key);
            if (k == 1) PanelsBase.k1Release(st, key);
            e.scores.recordCounted(e.reg.familyOf(key), pass, x.vote == pass);
        }
        if (s.tier != Tier.Issue) {
            PanelsBase.returnDeposit(e, id, s, pass);
            // an ADR passed and final: the registry may apply its operations (task 3.4)
            if (pass && s.tier != Tier.Escalated) e.reg.adrPassed(id, s.tier == Tier.Removal, s.commitment);
        }
        uint256 sp = s.shadowPid;
        if (sp != 0 && st.panels[sp].ex == pid && block.timestamp > st.panels[sp].revealBy) {
            _settleShadows(st, e, sp, st.panels[sp]);
        }
        emit Final(id, pass);
    }

    function settleShadows(Store storage st, Env memory e, uint256 spid) external {
        Panel storage p = st.panels[spid];
        if (p.kind != Kind.Shadow || p.k == 0 || block.timestamp <= p.revealBy) revert NotReady();
        if (!_settleShadows(st, e, spid, p)) revert NothingDue();
    }

    // ---------- counting ----------

    /// A panel's last seat revealed with its receipt (from PanelsJudge).
    function count(Store storage st, Env memory e, uint256 pid) external {
        Panel storage p = st.panels[pid];
        Kind kind = p.kind;
        if (kind == Kind.Counted) _countMain(st, e, pid, p);
        else if (kind == Kind.Audit) _countAudit(st, e, pid, p);
        else _countChallenge(st, e, pid, p);
    }

    /// The majority (CONSTITUTION_QUORUM at the constitution tier) of `passes` of k.
    function _passes(Submission storage s, uint256 passes, uint256 k) private view returns (bool) {
        return s.tier == Tier.Issue ? 2 * passes > k : passes >= PanelsBase.CONSTITUTION_QUORUM;
    }

    /// The verdict, its level and its audits; a k = 1 verdict is held unless its challengers exist. A seat emptied by a
    /// reveal missed after the revealed votes decided (PanelsJudge.advance) neither votes nor counts toward the level.
    function _countMain(Store storage st, Env memory e, uint256 pid, Panel storage p) private {
        uint256 k = p.k;
        PanelsDraw.Member[] memory ms = new PanelsDraw.Member[](k);
        uint256 m;
        uint256 passes;
        for (uint256 i; i < k; ++i) {
            Seat storage x = st.seats[pid][i];
            if (x.key == address(0)) continue;
            if (x.vote) ++passes;
            ms[m++].level = x.level;
        }
        uint8 level = PanelsDraw.levelOf(ms, m, k);
        p.passes = uint8(passes);
        p.level = level;
        uint256 id = p.id;
        Submission storage s = st.subs[id];
        bool pass = _passes(s, passes, k);
        s.pass = pass;
        s.level = level;
        s.auditBlock = uint64(block.number + PanelsBase.SEED_DELAY);
        s.auditSnap = PanelsBase.snap(e, s.bounty);
        s.auditEpoch = uint64(e.reg.epoch() + 1);
        s.auditsDue = uint8((k == 1 ? PanelsBase.K1_AUDITS : 0) + (_splitC(s, p) ? 1 : 0));
        emit Counted(id, pid, pass, passes, level);
        if (k == 1 && !_challengersReady(st, e, id, s)) {
            s.status = Status.Held;
            s.heldAtCount = true;
            emit Held(id);
        } else {
            _startWindow(e, id, s);
        }
    }

    /// A split pass by a level C panel (always audited, D10); a seat emptied by a missed reveal counts as not passing.
    function _splitC(Submission storage s, Panel storage p) private view returns (bool) {
        return s.tier == Tier.Issue && p.level == PanelsBase.LEVEL_C && 2 * p.passes > p.k && p.passes < p.k;
    }

    function _countAudit(Store storage st, Env memory e, uint256 apid, Panel storage p) private {
        Seat storage x = st.seats[apid][0];
        uint256 id = p.id;
        Submission storage s = st.subs[id];
        e.reg.verdictFinal(x.key);
        ++s.auditsDone;
        bool agrees = x.vote == s.pass;
        emit Audited(id, apid, x.key, agrees);
        if (!agrees && !s.challengeOpen && (s.status == Status.Held || s.status == Status.Window)) {
            openChallenge(st, e, id, x.key, bytes32(0));
        }
    }

    /// A false receipt found by the challenge panel's majority is the whole bond; its majority decides the fix; the
    /// window resumes where it froze.
    function _countChallenge(Store storage st, Env memory e, uint256 cpid, Panel storage p) private {
        uint256 id = p.id;
        Submission storage s = st.subs[id];
        uint256 kc = p.k;
        uint256 k = s.k;
        uint256 passes;
        uint256[7] memory flags;
        for (uint256 i; i < kc; ++i) {
            Seat storage x = st.seats[cpid][i];
            if (x.vote) ++passes;
            for (uint256 j; j < k; ++j) {
                if ((x.mask >> j) & 1 == 1) ++flags[j];
            }
            e.reg.verdictFinal(x.key);
        }
        bool falseReceipt;
        uint256 pid = s.pid;
        for (uint256 j; j < k; ++j) {
            address key = st.seats[pid][j].key;
            if (key == address(0)) continue;
            if (2 * flags[j] > kc) {
                e.reg.slashFault(key, IValidators.Fault.FalseVerdict, s.challenger);
                falseReceipt = true;
            }
            e.reg.challengeClosed(key);
        }
        bool pass = _passes(s, passes, kc);
        bool upheld = pass != s.pass || falseReceipt;
        p.passes = uint8(passes);
        s.pass = pass;
        s.lastUpheld = upheld;
        s.challengeOpen = false;
        s.challengePid = 0;
        if (s.status == Status.Window) s.finalAt = uint64(block.timestamp + s.frozenLeft);
        emit ChallengeResolved(id, cpid, upheld, pass, falseReceipt);
    }

    function _startWindow(Env memory e, uint256 id, Submission storage s) private {
        Tier t = s.tier;
        uint256 w = t == Tier.Adr ? e.adr : t == Tier.Removal ? e.removal : PanelsBase.windowOf(e, s.k, s.level);
        uint256 finalAt = block.timestamp + w;
        s.finalAt = uint64(finalAt);
        s.status = Status.Window;
        if (s.auditStuckAt != 0) s.auditStuckAt = uint64(block.timestamp); // L19's clock runs in the window only
        emit WindowStarted(id, finalAt);
    }

    function _challengersReady(Store storage st, Env memory e, uint256 id, Submission storage s)
        private
        view
        returns (bool)
    {
        return PanelsDraw.challengersReady(
            PanelsDraw.ShadowCtx(
                e.reg,
                IPanelsHost(st.race),
                e.fees,
                e.scores,
                id,
                s.bounty,
                st.panels[s.pid].seed,
                PanelsBase.challengeK(1),
                s.teeOnly,
                e.capWindow
            ),
            st.seatOf[s.pid],
            st.load
        );
    }

    // ---------- shadows ----------

    function _drawShadows(
        Store storage st,
        Env memory e,
        uint256 id,
        uint256 countedPid,
        bytes32 seed,
        uint256 n,
        uint256 sealBy
    ) private {
        Submission storage s = st.subs[id];
        (address[] memory keys, address unpriced) = PanelsDraw.shadows(
            PanelsDraw.ShadowCtx(
                e.reg,
                IPanelsHost(st.race),
                e.fees,
                e.scores,
                id,
                s.bounty,
                keccak256(abi.encode(seed, "shadow")),
                n,
                s.teeOnly,
                e.capWindow
            ),
            st.load
        );
        if (unpriced != address(0)) PanelsBase.announce(e, unpriced);
        if (keys.length == 0) return;
        (uint256 spid, Panel storage p) =
            PanelsBase.newPanel(st, e, id, Kind.Shadow, seed, keys.length, countedPid, s.snap, 0);
        p.sealBy = uint64(sealBy);
        p.revealBy = uint64(sealBy + e.reveal);
        for (uint256 i; i < keys.length; ++i) {
            PanelsBase.seat(st, e, spid, p, i, keys[i], 0);
        }
        s.shadowPid = uint64(spid);
    }

    /// Records the shadows' reveals and misses once, then scores the revealed ones once their outcome exists (D5).
    /// Returns whether anything changed.
    function _settleShadows(Store storage st, Env memory e, uint256 spid, Panel storage p)
        private
        returns (bool changed)
    {
        uint256 n = p.k;
        if (!p.closed) {
            p.closed = true;
            changed = true;
            for (uint256 i; i < n; ++i) {
                Seat storage x = st.seats[spid][i];
                e.reg.recordShadow(x.key, x.revealed && x.receipted);
            }
        }
        if (p.scored) return changed;
        Submission storage s = st.subs[p.id];
        uint256 cpid = p.ex;
        bool truth;
        bool byMajority = true;
        uint256 votes;
        uint256 passes;
        if (cpid != 0) {
            if (!st.panels[cpid].counted) return changed;
            if (s.heldAtCount) {
                votes = 1; // the held k = 1 verdict's own vote joins the majority
                if (st.seats[cpid][0].vote) passes = 1;
            } else {
                if (s.status != Status.Final) return changed;
                truth = s.pass; // the final outcome of a panel no lone validator decided
                byMajority = false;
            }
        }
        p.scored = true;
        if (byMajority) {
            for (uint256 i; i < n; ++i) {
                Seat storage x = st.seats[spid][i];
                if (!(x.revealed && x.receipted)) continue;
                ++votes;
                if (x.vote) ++passes;
            }
            if (votes < 3 || 2 * passes == votes) return true; // too few sealed verdicts revealed, or a tie
            truth = 2 * passes > votes;
        }
        for (uint256 i; i < n; ++i) {
            Seat storage x = st.seats[spid][i];
            if (!(x.revealed && x.receipted)) continue;
            bool agreed = x.vote == truth;
            e.reg.scoreShadow(x.key, agreed);
            e.scores.recordShadow(e.reg.familyOf(x.key), truth, agreed);
            emit ShadowScored(spid, x.key, agreed);
        }
        return true;
    }

    // ---------- re-targets ----------

    function _retarget(Env memory e, uint256 id, Submission storage s) private {
        PanelsBase.start(e, s);
        emit PanelsBase.Retargeted(id, s.seedBlock);
    }

    function _retargetChallenge(Env memory e, Submission storage s) private {
        s.challengeBlock = uint64(block.number + PanelsBase.SEED_DELAY);
        s.challengeSnap = PanelsBase.snap(e, s.bounty);
    }
}
