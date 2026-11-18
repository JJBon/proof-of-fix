// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {IValidators} from "./IValidators.sol";
import {IPanelsRegistry, IPanelsFees, IPanelsHost, IPanelScores} from "./IPanels.sol";

/// v3's draws (design D2, D5, D6, D10, D13, D14, D19; specs/judge-panels), a linked library so Panels stays under
/// EIP-170: k from the registry's bond-tier counter, rejection sampling under the caps with a fixed number of tries,
/// the step-down, the panel's proof level, the shadow draw, and the k = 1 hold's count of challengers. Reads only (the
/// registry, the meter, the scores, the host, and Panels' seats and pending counts), so `Panels.sample` recomputes any
/// draw from its seed.
///
/// **A snapshot fixed before the seed is known (#138, against grinding).** When a draw's seed block is set (at `open`, a
/// re-target, a challenge or an audit), Panels records a `Snap`: the block, the bounty tier's live count, its roster's
/// length (`Validators.rosterEntry`: every key that ever became drawable for the tier, append-only) and FeesV3's
/// epoch. The draw reads only that: k from the live count, try i reads roster entry `keccak(seed, i) mod nRoster`, and an
/// entry counts only if it was drawable for the tier at the snapshot's block and still is (it rose to its bucket at or
/// before that block, and its bucket now covers the tier), its family was priced by the snapshot's epoch, isn't barred
/// and didn't recover after it, and (a counted k = 1) it wasn't below K1_PENDING_MAX only since. So a change made after
/// the seed is fixed (a leave, a top-up, a slash, an activation, a roll, a finality) can only remove a validator from
/// the draw, as silence would, never add one or move the others. Each k's tries are DRAW_TRIES × k × the roster's
/// slack (its length over the live count at the snapshot, at most ROSTER_SLACK_MAX), so departed keys don't eat the
/// tries.
///
/// An entry is also skipped when it sits or sat on the panel or on its excluded panel (a challenge's or an audit's
/// original panel), is a party, or would break a cap:
/// - one per operator account;
/// - at most (k − 1) / 2 per host and per model family, from k = 3;
/// - at most (k − 1) / 2 per TEE type, from `teeFrom` (3 while TEE_CAP_K3_TYPES types are accepted, else 5).
/// Each k gets DRAW_TRIES × k tries; a k that can't be filled steps down by 2, keeping the members that still fit its
/// caps, in order, and the sample continues from the same counter, down to `kMin`.
library PanelsDraw {
    uint256 internal constant K_MAX = 7;
    uint256 internal constant DRAW_TRIES = 8;
    uint256 internal constant K1_PENDING_MAX = 10;
    uint256 internal constant HOLD_SCAN_MAX = 32;
    uint256 internal constant ROSTER_SLACK_MAX = 4;
    uint8 internal constant LEVEL_A = 1;
    uint8 internal constant LEVEL_B = 2;
    uint8 internal constant LEVEL_C = 3;

    /// What the caps and the level need to know of a drawn validator.
    struct Member {
        address key;
        address operator;
        bytes32 host;
        bytes32 family;
        bytes32 tee;
        uint8 level;
    }

    /// What a draw reads of the registry and the meter, fixed before its seed is known.
    struct Snap {
        uint64 blockNo;
        uint32 nLive; // eligibleCount(bounty) then
        uint32 nRoster; // the bounty tier's roster length then
        uint64 rolled; // FeesV3's epoch then
    }

    /// One sampling run. `members[0..m)` is the panel so far (capacity K_MAX).
    struct Ctx {
        IPanelsRegistry reg;
        IPanelsHost host;
        IPanelsFees fees;
        IPanelScores scores;
        uint256 id;
        uint256 bounty;
        bytes32 seed;
        uint256 counter; // the next try
        uint256 k;
        uint256 kTop; // the first k tried (at most K_MAX)
        uint256 kMin; // below it, nothing is drawn
        bool limits; // a counted issue panel: k only while its level A limit covers the bounty
        bool k1Cap; // a counted panel: K1_PENDING_MAX applies at k = 1
        bool levelCheck; // a replacement: skip a validator that would leave the full panel too weak for the bounty
        bool teeOnly; // hidden tests or a private repository: level A or B only (D10)
        uint256 teeFrom;
        uint256 tier;
        Snap snap;
        uint256 pid; // the panel drawn: its seats and past seats are skipped
        uint256 exPid; // a panel whose seats and past seats are skipped too (0: none)
        Member[] members;
        uint256 m;
        address unpriced; // the first validator of an unpriced family met, to announce
    }

    /// A shadow draw (D5): `count` candidates, or validators of barred families, by the seed.
    struct ShadowCtx {
        IPanelsRegistry reg;
        IPanelsHost host;
        IPanelsFees fees;
        IPanelScores scores;
        uint256 id;
        uint256 bounty;
        bytes32 seed;
        uint256 count;
        bool teeOnly;
    }

    /// The largest bounty a panel of k at `level` may judge (ADR 0004): level A k=1 $50 · k=3 $250 · k=5 $625 · k=7
    /// $625; level B half of A's; level C k=1 $10 · k=3 $50 · k=5 $125 · k=7 $250. Micro-coins.
    function limitOf(uint256 k, uint8 level) internal pure returns (uint256) {
        uint256 a = k == 1 ? 50e6 : k == 3 ? 250e6 : 625e6;
        if (level == LEVEL_A) return a;
        if (level == LEVEL_B) return a / 2;
        return k == 1 ? 10e6 : k == 3 ? 50e6 : k == 5 ? 125e6 : 250e6;
    }

    /// The bond tier of a bounty: the smallest k-table limit at or above it (D2; `Validators.tierOf`).
    function tierOf(uint256 bounty) internal pure returns (uint256 t) {
        uint256[7] memory steps = [uint256(10e6), 25e6, 50e6, 125e6, 250e6, 312_500_000, 625e6];
        while (t < 6 && bounty > steps[t]) ++t;
    }

    /// The tries a seat gets: DRAW_TRIES, times the roster's slack at the snapshot.
    function tries(Snap memory s) internal pure returns (uint256) {
        if (s.nLive == 0) return 0;
        uint256 slack = (uint256(s.nRoster) + s.nLive - 1) / s.nLive;
        return DRAW_TRIES * (slack < ROSTER_SLACK_MAX ? slack : ROSTER_SLACK_MAX);
    }

    /// The panel's proof level: the lowest level a majority holds (D10), i.e. the ((k + 1) / 2)-th strongest.
    function levelOf(Member[] memory ms, uint256 m, uint256 k) internal pure returns (uint8) {
        uint256 need = (k + 1) / 2;
        for (uint8 l = LEVEL_A; l < LEVEL_C; ++l) {
            uint256 count;
            for (uint256 j; j < m; ++j) {
                if (ms[j].level <= l) ++count;
            }
            if (count >= need) return l;
        }
        return LEVEL_C;
    }

    /// A panel's first draw: k from the counter (at most c.kTop), then the sample with the step-down to c.kMin.
    /// Returns the run, the k drawn (0: nothing could be drawn) and the panel's level.
    function drawPanel(
        Ctx memory c,
        mapping(uint256 => mapping(address => uint8)) storage seatOf,
        mapping(address => uint256) storage k1Pending,
        mapping(address => uint256) storage k1FreedAt
    ) public view returns (Ctx memory, uint256, uint8) {
        uint256 n = c.snap.nLive;
        uint256 k = n < c.kTop ? n : c.kTop;
        if (k % 2 == 0 && k != 0) --k;
        while (true) {
            if (k == 0 || k < c.kMin || (c.limits && limitOf(k, LEVEL_A) < c.bounty)) return (c, 0, 0);
            c.k = k;
            _refilter(c, k1Pending, k1FreedAt);
            c = fill(c, tries(c.snap) * k, seatOf, k1Pending, k1FreedAt);
            if (c.m == k) break;
            if (k < 3) return (c, 0, 0);
            k -= 2;
        }
        return (c, k, levelOf(c.members, c.m, k));
    }

    /// Samples until the panel holds c.k members or `budget` tries are spent.
    function fill(
        Ctx memory c,
        uint256 budget,
        mapping(uint256 => mapping(address => uint8)) storage seatOf,
        mapping(address => uint256) storage k1Pending,
        mapping(address => uint256) storage k1FreedAt
    ) public view returns (Ctx memory) {
        uint256 nr = c.snap.nRoster;
        if (nr == 0) return c;
        uint256 end = c.counter + budget;
        uint256 k = c.k;
        while (c.m < k && c.counter < end) {
            uint256 i = c.counter++;
            (address key, uint64 raisedAt, uint8 bucket) =
                c.reg.rosterEntry(c.tier, uint256(keccak256(abi.encode(c.seed, i))) % nr);
            if (bucket <= c.tier || raisedAt > c.snap.blockNo) continue;
            if (seatOf[c.pid][key] != 0 || seatOf[c.exPid][key] != 0 || _has(c, key)) continue;
            if (c.k1Cap && k == 1 && !_k1Free(key, c.snap.blockNo, k1Pending, k1FreedAt)) continue;
            IValidators.Validator memory v = c.reg.validator(key);
            if (c.teeOnly && v.level == LEVEL_C) continue;
            Member memory x = Member(key, v.operator, v.host, v.family, v.teeType, v.level);
            if (!fits(c, x, k)) continue;
            if (c.levelCheck && c.m + 1 == k) {
                c.members[c.m] = x;
                if (limitOf(k, levelOf(c.members, k, k)) < c.bounty) continue;
            }
            if (c.host.isParty(c.id, key) || c.host.isParty(c.id, v.operator)) continue;
            if (!c.fees.isPriced(v.family)) {
                if (c.unpriced == address(0)) c.unpriced = key;
                continue;
            }
            if (c.fees.pricedFrom(v.family) > c.snap.rolled) continue;
            if (c.scores.isBarredSince(v.family, c.snap.blockNo)) continue;
            c.members[c.m++] = x;
        }
        return c;
    }

    /// Whether `x` may join `c.members[0..m)` on a panel of k under the caps (D6).
    function fits(Ctx memory c, Member memory x, uint256 k) internal pure returns (bool) {
        uint256 cap = (k - 1) / 2;
        uint256 hosts;
        uint256 families;
        uint256 tees;
        for (uint256 j; j < c.m; ++j) {
            Member memory y = c.members[j];
            if (y.operator == x.operator) return false;
            if (y.host == x.host) ++hosts;
            if (y.family == x.family) ++families;
            if (x.tee != 0 && y.tee == x.tee) ++tees;
        }
        if (k >= 3 && (hosts >= cap || families >= cap)) return false;
        if (k >= c.teeFrom && x.tee != 0 && tees >= cap) return false;
        return true;
    }

    /// The shadow judges (D5): candidates in standing not cooling off, or drawable validators of a family barred by its
    /// score (they judge only as shadows until it recovers), not parties, of a priced family (D19), and at level A or B
    /// for a hidden-test submission (D10). DRAW_TRIES tries a shadow, over the candidates and then the validators
    /// eligible for the bounty.
    function shadows(ShadowCtx memory c) public view returns (address[] memory keys, address unpriced) {
        uint256 cc = c.reg.candidateCount();
        uint256 ne = c.scores.barredCount() == 0 ? 0 : c.reg.eligibleCount(c.bounty);
        keys = new address[](c.count);
        uint256 got;
        if (cc + ne == 0) return (_trim(keys, 0), address(0));
        for (uint256 i; i < DRAW_TRIES * c.count && got < c.count; ++i) {
            uint256 idx = uint256(keccak256(abi.encode(c.seed, i))) % (cc + ne);
            address key = idx < cc ? c.reg.candidateAt(idx) : c.reg.eligibleAt(c.bounty, idx - cc);
            bool dup;
            for (uint256 j; j < got; ++j) {
                if (keys[j] == key) dup = true;
            }
            if (dup) continue;
            IValidators.Validator memory v = c.reg.validator(key);
            bytes32 family = v.family;
            if (c.teeOnly && v.level == LEVEL_C) continue;
            if (idx < cc ? !c.reg.canShadow(key) : !c.scores.isBarred(family) || !c.reg.isDrawable(key)) continue;
            if (c.host.isParty(c.id, key) || c.host.isParty(c.id, v.operator)) continue;
            if (!c.fees.isPriced(family)) {
                if (unpriced == address(0)) unpriced = key;
                continue;
            }
            keys[got++] = key;
        }
        keys = _trim(keys, got);
    }

    /// Whether `need` validators are eligible for a verdict's challenge: drawable and bonded for its bounty, outside
    /// its panel (and its auditors), not parties, at level A or B for a hidden-test submission (D4, D10). Reads up to
    /// HOLD_SCAN_MAX of them from a seeded offset: exact up to that many eligible validators, a random window beyond.
    function challengersReady(
        IPanelsRegistry reg,
        IPanelsHost host,
        uint256 id,
        uint256 bounty,
        bytes32 seed,
        uint256 need,
        bool teeOnly,
        mapping(address => uint8) storage seated
    ) public view returns (bool) {
        uint256 n = reg.eligibleCount(bounty);
        if (n < need) return false;
        uint256 start = uint256(keccak256(abi.encode(seed, "hold")));
        uint256 reads = n < HOLD_SCAN_MAX ? n : HOLD_SCAN_MAX;
        uint256 found;
        for (uint256 i; i < reads && found < need; ++i) {
            address key = reg.eligibleAt(bounty, (start + i) % n);
            if (seated[key] != 0 || !reg.isDrawable(key)) continue;
            IValidators.Validator memory v = reg.validator(key);
            if (teeOnly && v.level == LEVEL_C) continue;
            if (host.isParty(id, key) || host.isParty(id, v.operator)) continue;
            ++found;
        }
        return found >= need;
    }

    /// At a step-down: keeps, in order, the members that fit the new k's caps (and its pending cap at k = 1).
    function _refilter(
        Ctx memory c,
        mapping(address => uint256) storage k1Pending,
        mapping(address => uint256) storage k1FreedAt
    ) private view {
        uint256 old = c.m;
        c.m = 0;
        for (uint256 j; j < old && c.m < c.k; ++j) {
            Member memory x = c.members[j];
            if (c.k1Cap && c.k == 1 && !_k1Free(x.key, c.snap.blockNo, k1Pending, k1FreedAt)) continue;
            if (fits(c, x, c.k)) c.members[c.m++] = x;
        }
    }

    /// Below K1_PENDING_MAX now, and already at the snapshot (D4).
    function _k1Free(
        address key,
        uint256 snapshot,
        mapping(address => uint256) storage k1Pending,
        mapping(address => uint256) storage k1FreedAt
    ) private view returns (bool) {
        return k1Pending[key] < K1_PENDING_MAX && k1FreedAt[key] <= snapshot;
    }

    function _has(Ctx memory c, address key) private pure returns (bool) {
        for (uint256 j; j < c.m; ++j) {
            if (c.members[j].key == key) return true;
        }
        return false;
    }

    function _trim(address[] memory a, uint256 n) private pure returns (address[] memory) {
        assembly ("memory-safe") {
            mstore(a, n)
        }
        return a;
    }
}
