// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {MessageHashUtils} from "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";
import {IPanelsRegistry, IPanelsFees, IPanelsHost, IPanelScores, IPanelsPool} from "./IPanels.sol";
import {PanelsDraw} from "./PanelsDraw.sol";
import {WindowsLib} from "./Windows.sol";

// Panels' state and its shared internals (proof-of-fix#138, task 3.2). Panels holds one `Store`; its logic lives in
// the linked libraries PanelsJudge (seals, reveals, receipts, replacement), PanelsVerdict (draws, counting, audits,
// challenges, shadows, finality) and PanelsDraw (the sampling), so each contract stays under EIP-170. See Panels for
// the rules.

enum Status {
    None,
    Sealed, // opened, waiting for its seed block
    Waiting, // no panel: too few eligible, a bounty above the reachable k's limit, or a void draw
    Judging, // a panel is seated
    Held, // a counted k = 1 verdict waiting for its challengers (D4)
    Window, // counted, its window running (frozen while a challenge is open)
    Final,
    Withdrawn,
    Expired, // a constitution-tier submission on too small a network (D7)
    Released // its rounds were released MAX_REDRAWS times, or at the race's deadline: never judged, refunded (L19)
}

enum Tier {
    Issue,
    Adr, // adds or loosens: CONSTITUTION_MIN_ELIGIBLE, ADR_WINDOW
    Removal, // only removes or raises a minimum: REMOVAL_MIN_ELIGIBLE, REMOVAL_WINDOW
    Escalated // a fix judged at the constitution tier: CONSTITUTION_MIN_ELIGIBLE, its (K_MAX, level) window
}

enum Kind {
    Counted,
    Shadow,
    Audit,
    Challenge
}

struct Submission {
    bytes32 commitment;
    uint128 bounty; // micro-coins; 1 for an ADR (its draw reads the lowest tier)
    uint64 seedBlock;
    Status status;
    Tier tier;
    uint8 k;
    uint8 level;
    bool pass;
    bool heldAtCount;
    bool teeOnly; // hidden tests or a private repository: every judge at level A or B (D10)
    PanelsDraw.Snap snap;
    uint64 waitEpoch; // registry epoch + 1 when it last waited
    uint64 finalAt;
    uint64 pid; // its counted panel
    uint64 shadowPid; // its latest shadow panel
    uint64 frozenLeft; // a frozen window's remaining time
    uint64 auditBlock;
    uint8 auditsDue;
    uint8 auditsDrawn;
    uint8 auditsDone;
    bool auditDecided;
    bool challengeOpen;
    bool lastUpheld;
    uint64 challengeBlock;
    uint64 challengeEpoch; // registry epoch + 1 while its challenge waits for a panel
    uint64 challengePid;
    PanelsDraw.Snap auditSnap;
    PanelsDraw.Snap challengeSnap;
    address challenger;
    address author; // a constitution-tier submission's deposit returns here
    uint64 auditEpoch; // registry epoch + 1 when its audit snapshot was taken (#251 task 3.10)
    bool auditWaits; // no auditor in that snapshot, and the registry hasn't changed: drawAudits refuses until it does
    uint8 redraws; // rounds released so far: stuck panels and audits that couldn't be drawn (#251, L19)
    uint64 retryAt; // while waiting: when it's drawn again even if the registry didn't change (L19, L16)
    uint64 auditStuckAt; // when its audits first found no auditor since the last one was drawn (0: not stuck)
    uint64 challengeBy; // its open challenge's CHALLENGE_DEADLINE: past it with no panel, the challenge lapses (L25)
    uint64 challengeRetryAt; // while its challenge waits: when it's drawn again even if the registry didn't change (L25)
    uint8 lapses; // challenges lapsed so far (L25): at MAX_REDRAWS, no new challenge is accepted
    bool chalFiled; // its open (or last) challenge was filed by the race, not opened by an auditor
    bool filedLapsed; // the race's last filed challenge lapsed: the race returns its stake and cover (settleLapse)
}

struct Panel {
    uint256 id; // the submission
    bytes32 seed;
    uint64 sealBy;
    uint64 revealBy;
    uint32 counter; // the sample's next try
    uint8 k;
    uint8 seats; // filled seats
    uint8 nSealed; // filled seats that sealed
    uint8 done; // revealed with a receipt
    uint8 passes;
    uint8 level;
    bool counted;
    Kind kind;
    bool closed; // shadows: deadlines recorded
    bool scored; // shadows: scored (or found unscorable)
    uint64 ex; // a challenge's or an audit's original panel; a shadow panel's counted panel (0: a waiting one)
    PanelsDraw.Snap snap;
}

struct Seat {
    address key;
    uint8 level;
    bool hasSeal;
    bool revealed;
    bool receipted;
    bool vote;
    uint8 mask;
    bytes32 seal;
    bytes32 receipt;
}

/// Everything Panels keeps.
struct Store {
    address race;
    uint256 panelCount;
    mapping(address key => uint256) k1Pending; // unfinished counted k = 1 seats (D4)
    mapping(address key => uint256) k1FreedAt; // the block one last dropped below K1_PENDING_MAX
    mapping(uint256 id => Submission) subs;
    mapping(uint256 pid => Panel) panels;
    mapping(uint256 pid => mapping(uint256 slot => Seat)) seats;
    mapping(uint256 pid => mapping(address key => uint8)) seatOf; // slot + 1, or GONE
    mapping(address key => PanelsDraw.Load) load; // each validator's capacity and recent seats (#251, L16)
}

/// Panels' immutables, passed to its libraries: its bindings and the deployment's windows (#251, design L4).
struct Env {
    IPanelsRegistry reg;
    IPanelsFees fees;
    IPanelScores scores;
    address coin;
    address pool;
    bytes32 domain;
    uint256 seal; // SEAL_WINDOW
    uint256 reveal; // REVEAL_WINDOW
    uint256 adr; // ADR_WINDOW
    uint256 removal; // REMOVAL_WINDOW
    uint256 chalAB; // CHALLENGE_WINDOW at levels A and B, packed (WindowsLib.pack)
    uint256 chalC; // and at level C
    uint256 stuckGrace; // STUCK_GRACE (L19)
    uint256 retryDelay; // RETRY_DELAY
    uint256 maxRedraws; // MAX_REDRAWS
    uint256 capWindow; // the capacity's trailing window (L16)
    uint256 challengeDeadline; // CHALLENGE_DEADLINE (L25)
    bool opCap; // the operator cap is Strict (#251 batch 4, L23)
    bool hostCap; // the host cap is Strict
    bool teeCap; // the TEE-type cap is Strict
    uint256 kTop; // the largest issue-tier panel (L24)
    bool sameSize; // a challenge of k >= 3 draws a fresh panel of k (L24's `Same`), not CHALLENGE_K[k]
}

library PanelsBase {
    using SafeERC20 for IERC20;

    uint256 internal constant K_MAX = 7;
    uint256 internal constant SEED_DELAY = 5;
    uint256 internal constant K1_PENDING_MAX = 10;
    uint256 internal constant TEE_CAP_K3_TYPES = 5;
    uint256 internal constant SHADOW_PER_DRAW = 1;
    uint256 internal constant SHADOW_PER_DRAW_SMALL = 2;
    uint256 internal constant SHADOW_PER_WAITING = 3;
    uint256 internal constant AUDIT_RATE_BPS = 1_000;
    uint256 internal constant K1_AUDITS = 2;
    uint256 internal constant CONSTITUTION_QUORUM = 5;
    uint256 internal constant CONSTITUTION_MIN_ELIGIBLE = 21;
    uint256 internal constant REMOVAL_MIN_ELIGIBLE = 14;
    uint256 internal constant ADR_DEPOSIT = 15e6;
    uint8 internal constant LEVEL_C = 3;
    uint8 internal constant GONE = type(uint8).max; // seatOf: sat on the panel (or is excluded from its draws)
    bytes32 internal constant STATEMENT_TYPEHASH = keccak256("Statement(bytes32 subject,bytes32 content)");
    bytes32 internal constant SEAL_TAG = keccak256("proof-of-fix v3 seal");
    bytes32 internal constant REVEAL_TAG = keccak256("proof-of-fix v3 reveal");
    bytes32 internal constant RECEIPT_TAG = keccak256("proof-of-fix v3 receipt");

    event Retargeted(uint256 indexed id, uint256 seedBlock);
    event Waited(uint256 indexed id, uint256 k, uint8 level);
    event Expired(uint256 indexed id);
    event Drawn(uint256 indexed id, uint256 indexed pid, Kind kind, uint256 k, bytes32 seed);
    event Seated(uint256 indexed pid, uint256 slot, address indexed key, uint256 sealBy);
    event DepositReturned(uint256 indexed id, address indexed to, bool refunded);

    error TooEarly();

    function snap(Env memory e, uint256 bounty) internal view returns (PanelsDraw.Snap memory) {
        return PanelsDraw.Snap(
            uint64(block.number),
            uint32(e.reg.eligibleCount(bounty)),
            uint32(e.reg.rosterLength(PanelsDraw.tierOf(bounty))),
            uint64(e.fees.rolled())
        );
    }

    /// Fixes the seed block SEED_DELAY ahead and, now, the snapshot the draw will read (PanelsDraw.Snap).
    function start(Env memory e, Submission storage s) internal {
        s.status = Status.Sealed;
        s.seedBlock = uint64(block.number + SEED_DELAY);
        s.snap = snap(e, s.bounty);
    }

    /// The seed block's hash once it's past; 0 when it's gone (more than 256 blocks back), to re-target.
    function hashOf(uint256 b) internal view returns (bytes32) {
        if (block.number <= b) revert TooEarly();
        return blockhash(b);
    }

    /// The first k the TEE-type cap applies to: 3 while at least TEE_CAP_K3_TYPES TEE types are accepted, else 5 (D6).
    /// It follows the constitution's list as ADRs add and remove types, from the next draw.
    function teeCapFrom(Env memory e) internal view returns (uint256) {
        return e.reg.teeTypeCount() >= TEE_CAP_K3_TYPES ? 3 : 5;
    }

    function ctx(
        Store storage st,
        Env memory e,
        uint256 id,
        uint256 bounty,
        bytes32 seed,
        PanelsDraw.Snap memory sn,
        uint256 pid,
        uint256 exPid
    ) internal view returns (PanelsDraw.Ctx memory c) {
        c.reg = e.reg;
        c.host = IPanelsHost(st.race);
        c.fees = e.fees;
        c.scores = e.scores;
        c.id = id;
        c.bounty = bounty;
        c.seed = seed;
        c.snap = sn;
        c.tier = PanelsDraw.tierOf(bounty);
        c.pid = pid;
        c.exPid = exPid;
        c.teeFrom = e.teeCap ? teeCapFrom(e) : type(uint256).max; // Off: no k reaches it (L23)
        c.opCap = e.opCap;
        c.hostCap = e.hostCap;
        c.teeOnly = st.subs[id].teeOnly;
        c.members = new PanelsDraw.Member[](K_MAX);
        c.capWindow = e.capWindow;
        c.famCap = e.scores.capApplies(sn.blockNo);
    }

    /// The counted panel a submission's draw seats with `seed`: up to the deployment's `kTop` at the issue tier (L24),
    /// K_MAX exactly at the constitution tier.
    function drawCounted(Store storage st, Env memory e, uint256 id, bytes32 seed)
        internal
        view
        returns (PanelsDraw.Ctx memory c, uint256 k, uint8 level)
    {
        Submission storage s = st.subs[id];
        bool con = s.tier != Tier.Issue;
        c = ctx(st, e, id, s.bounty, seed, s.snap, st.panelCount + 1, 0);
        c.kTop = con ? K_MAX : e.kTop;
        c.kMin = con ? K_MAX : 1;
        c.limits = !con;
        c.k1Cap = true;
        return PanelsDraw.drawPanel(c, st.seatOf, st.k1Pending, st.k1FreedAt, st.load);
    }

    function newPanel(
        Store storage st,
        Env memory e,
        uint256 id,
        Kind kind,
        bytes32 seed,
        uint256 k,
        uint256 ex,
        PanelsDraw.Snap memory sn,
        uint256 counter
    ) internal returns (uint256 pid, Panel storage p) {
        pid = ++st.panelCount;
        p = st.panels[pid];
        p.id = id;
        p.seed = seed;
        p.k = uint8(k);
        p.kind = kind;
        p.ex = uint64(ex);
        p.snap = sn;
        p.counter = uint32(counter);
        resetTimeline(e, p);
        emit Drawn(id, pid, kind, k, seed);
    }

    function resetTimeline(Env memory e, Panel storage p) internal {
        uint256 sealBy = block.timestamp + e.seal;
        p.sealBy = uint64(sealBy);
        p.revealBy = uint64(sealBy + e.reveal);
    }

    /// Seats `key`: counted, audit and challenge seats open a verdict in the registry; a counted k = 1 seat counts
    /// toward K1_PENDING_MAX; an auditor is excluded from its verdict's later audits and challenge panels. Every seat
    /// counts toward its validator's capacity (L16).
    function seat(Store storage st, Env memory e, uint256 pid, Panel storage p, uint256 i, address key, uint8 level)
        internal
    {
        Seat storage x = st.seats[pid][i];
        x.key = key;
        x.level = level;
        st.seatOf[pid][key] = uint8(i + 1);
        PanelsDraw.took(st.load[key]);
        ++p.seats;
        Kind kind = p.kind;
        if (kind != Kind.Shadow) e.reg.verdictOpened(key);
        if (kind == Kind.Counted && p.k == 1) ++st.k1Pending[key];
        if (kind == Kind.Audit && st.seatOf[p.ex][key] == 0) st.seatOf[p.ex][key] = GONE;
        emit Seated(pid, i, key, p.sealBy);
    }

    function k1Release(Store storage st, address key) internal {
        if (st.k1Pending[key]-- == K1_PENDING_MAX) st.k1FreedAt[key] = block.number;
    }

    function announce(Env memory e, address key) internal {
        try e.fees.announce(key) {} catch {} // never blocks a draw
    }

    function minEligible(Tier t) internal pure returns (uint256) {
        return t == Tier.Removal ? REMOVAL_MIN_ELIGIBLE : CONSTITUTION_MIN_ELIGIBLE;
    }

    function expire(Env memory e, uint256 id, Submission storage s) internal {
        s.status = Status.Expired;
        emit Expired(id);
        returnDeposit(e, id, s, true);
    }

    /// ADR_DEPOSIT back to the author (taken effect, or expired), or to the sponsors' pool (rejected).
    function returnDeposit(Env memory e, uint256 id, Submission storage s, bool refund) internal {
        if (refund) {
            IERC20(e.coin).safeTransfer(s.author, ADR_DEPOSIT);
            emit DepositReturned(id, s.author, true);
        } else {
            IERC20(e.coin).forceApprove(e.pool, ADR_DEPOSIT);
            IPanelsPool(e.pool).fund(e.coin, ADR_DEPOSIT);
            emit DepositReturned(id, e.pool, false);
        }
    }

    /// CHALLENGE_WINDOW[k, level], the deployment's (#251, L4; the production values are ADR 0004's: level A k=1
    /// 168 h · k=3 24 h · k=5 12 h · k=7 6 h; level B twice A's; level C k=1 336 h · k=3 72 h · k=5 48 h · k=7 24 h).
    function windowOf(Env memory e, uint256 k, uint8 level) internal pure returns (uint256) {
        return WindowsLib.windowOf(e.chalAB, e.chalC, k, level);
    }

    /// CHALLENGE_K[k]: k=1→3 · k=3→5 · k=5→7 · k=7→7.
    function challengeK(uint256 k) internal pure returns (uint256) {
        return k == 1 ? 3 : k == 3 ? 5 : 7;
    }

    /// A challenge panel's first k and its smallest (L24): with `Same`, k fresh judges for a verdict of k >= 3, no
    /// step-down; otherwise D4's CHALLENGE_K[k] down to k + 2 (K_MAX for K_MAX), which also keeps a lone verdict's 3.
    function challengeRange(Env memory e, uint256 k) internal pure returns (uint256 top, uint256 min) {
        if (e.sameSize && k > 1) return (k, k);
        return (challengeK(k), k == K_MAX ? K_MAX : k + 2);
    }

    /// What a judge seals: its vote, its mask (a challenge judge's false receipts) and a secret salt, bound to this
    /// Panels, the panel and its key.
    function commitmentOf(uint256 pid, address key, bool vote, uint8 mask, bytes32 salt)
        internal
        view
        returns (bytes32)
    {
        return keccak256(abi.encode(address(this), pid, key, vote, mask, salt));
    }

    function subjectOf(bytes32 tag, uint256 pid, address key) internal view returns (bytes32) {
        return keccak256(abi.encode(tag, address(this), pid, key));
    }

    function statementDigest(bytes32 domain, bytes32 subject, bytes32 content) internal pure returns (bytes32) {
        return MessageHashUtils.toTypedDataHash(domain, keccak256(abi.encode(STATEMENT_TYPEHASH, subject, content)));
    }
}
