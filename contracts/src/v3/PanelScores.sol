// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {IFeesV3Scores} from "./IFeesV3.sol";
import {LaunchChain} from "./LaunchChain.sol";

/// v3's per-family scores (proof-of-fix#138, task 3.2 of #132; design D14; ADR 0004; specs/judge-scores), fed by
/// Panels and read by FeesV3 (`familyScore`) and by the draw (`isBarred`). Its own contract so FeesV3 can take its
/// address at deployment before Panels exists, and so Panels stays under EIP-170.
///
/// - **The score:** each family's balanced agreement with final outcomes over its last SCORE_WINDOW counted verdicts:
///   the mean of its agreement on passed outcomes and on failed ones, or the agreement on the one kind present. Shadow
///   verdicts never enter it. Kept as a ring of 2 bits a verdict (outcome passed, agreed), so anyone recomputes it from
///   the `Scored` events.
/// - **States:** Neutral (fewer than SCORE_MIN_VERDICTS, never barred: drawn, paid 1 ×); Scored; Barred (a score below
///   SCORE_MIN over at least SCORE_MIN_VERDICTS: not drawn for counted panels); Recovering (drawn again, its counted
///   window restarted; paid SCORE_FACTOR_MIN until SCORE_MIN_VERDICTS new counted verdicts).
/// - **Recovery:** from its barring on, a barred family's shadow verdicts are taken in consecutive blocks of
///   SCORE_RECOVER_VERDICTS, each judged once when complete, balanced as the score is; a block at SCORE_MIN +
///   SCORE_RECOVER_MARGIN recovers it.
///
/// - **Seats by rank (#132 D20, #251 contract batch 3; ADR 0007):** a Scored family is **seated** while its score is
///   within SEAT_MARGIN (5 points) of the best Scored family's; below that it is a **contender**: not drawn for counted
///   panels, drawn as a shadow (as a barred family is), free to dispute passes with a test. Neutral and Recovering
///   families are seated (their windows are too short to rank: D23's contender start for a new family isn't built
///   here). The family cap ((k − 1) / 2 per panel, D6) applies only while at least CAP_MIN_FAMILIES (3) of the families
///   known here (every family with a counted verdict scored) are seated (`capApplies`); with fewer, a panel may be one
///   family's, and a challenge that can't draw its larger panel gets a second draw (D27, `fewFamilies`). Recomputed at
///   every counted verdict and every recovery. Against grinding, as `isBarredSince`: a family seated only after a
///   draw's snapshot isn't drawn by it (`isSeatedSince`), and a draw whose snapshot predates a switch of the cap applies
///   it (`capApplies`), so a change made after a seed is known only ever removes validators from that draw.
///
/// Keyless: bound once by Panels (`bind`, from its constructor); every parameter a constant. The constructor reverts
/// off Sepolia and the local test chains (LaunchChain).
contract PanelScores is IFeesV3Scores {
    uint256 internal constant WAD = 1e18;
    uint256 public constant SCORE_WINDOW = 200;
    uint256 public constant SCORE_MIN_VERDICTS = 50;
    uint256 public constant SCORE_MIN = 0.7e18;
    uint256 public constant SCORE_RECOVER_VERDICTS = 100;
    uint256 public constant SCORE_RECOVER_MARGIN = 0.1e18;
    /// D20: a Scored family within this of the best Scored family's score is seated (5 points).
    uint256 public constant SEAT_MARGIN = 0.05e18;
    /// D20, D27: the family cap applies while at least this many families are seated; with fewer, a challenge that
    /// can't draw its larger fresh panel gets a second draw (`SECOND_PANEL` "few families").
    uint256 public constant CAP_MIN_FAMILIES = 3;

    /// A known family's seat: `contender` while it is Scored and more than SEAT_MARGIN below the best; `seatedAt` the
    /// block it last stopped being one.
    struct Seat {
        bool known;
        bool contender;
        uint64 seatedAt;
    }

    /// A family's counters: its counted window (n entries, the oldest at `head`) and its current recovery block.
    struct Family {
        ScoreState state;
        uint16 n;
        uint16 head;
        uint16 passN;
        uint16 passAgree;
        uint16 failN;
        uint16 failAgree;
        uint16 fresh; // counted verdicts since it recovered (Recovering)
        uint16 bPassN;
        uint16 bPassAgree;
        uint16 bFailN;
        uint16 bFailAgree;
    }

    address public panels;
    mapping(bytes32 family => Family) internal _f;
    mapping(bytes32 family => uint256[2]) internal _ring; // 2 bits an entry: bit 0 the outcome passed, bit 1 agreed
    /// The block a family last recovered: a draw whose registry snapshot is older doesn't count it as drawn again.
    mapping(bytes32 family => uint256) public recoveredAt;
    /// How many families are barred now (the shadow draw looks for barred families' validators only when some are).
    uint256 public barredCount;
    /// Every family with a counted verdict scored, in the order first seen.
    bytes32[] internal _families;
    mapping(bytes32 family => Seat) internal _seats;
    /// The best Scored family's score (WAD; 0 while none is Scored), the known families seated now, and the
    /// contenders.
    uint256 public bestScore;
    uint256 public seatedCount;
    uint256 public contenderCount;
    /// The block the family cap last switched on or off (`seatedCount` crossed CAP_MIN_FAMILIES).
    uint256 public capChangedAt;

    event Bound(address indexed panels);
    event Scored(bytes32 indexed family, bool passed, bool agreed, ScoreState state, uint256 scoreWad);
    event ShadowScored(bytes32 indexed family, bool passed, bool agreed);
    event BlockJudged(bytes32 indexed family, uint256 scoreWad, bool recovered);
    event SeatChanged(bytes32 indexed family, bool seated, uint256 bestWad);

    error AlreadyBound();
    error NotPanels();

    constructor() {
        LaunchChain.check();
    }

    function bind() external {
        if (panels != address(0)) revert AlreadyBound();
        panels = msg.sender;
        emit Bound(msg.sender);
    }

    /// A counted judge's verdict at its final outcome (Panels, at finality).
    function recordCounted(bytes32 family, bool passed, bool agreed) external {
        if (msg.sender != panels) revert NotPanels();
        Family storage f = _f[family];
        bool fresh = !_seats[family].known;
        if (fresh) {
            _seats[family].known = true;
            _families.push(family);
        }
        uint256[2] storage ring = _ring[family];
        uint256 n = f.n;
        uint256 slot;
        if (n == SCORE_WINDOW) {
            slot = f.head;
            uint256 old = (ring[slot / 128] >> ((slot % 128) * 2)) & 3;
            _count(f, old & 1 == 1, old & 2 == 2, false);
            f.head = uint16((slot + 1) % SCORE_WINDOW);
        } else {
            slot = (uint256(f.head) + n) % SCORE_WINDOW;
            f.n = uint16(n + 1);
        }
        uint256 bits = (passed ? 1 : 0) | (agreed ? 2 : 0);
        uint256 shift = (slot % 128) * 2;
        ring[slot / 128] = (ring[slot / 128] & ~(uint256(3) << shift)) | (bits << shift);
        _count(f, passed, agreed, true);
        ScoreState s = f.state;
        if (s == ScoreState.Recovering) {
            if (++f.fresh >= SCORE_MIN_VERDICTS) s = ScoreState.Scored;
        } else if (s == ScoreState.Neutral && f.n >= SCORE_MIN_VERDICTS) {
            s = ScoreState.Scored;
        }
        uint256 score = _balanced(f.passN, f.passAgree, f.failN, f.failAgree);
        if (s == ScoreState.Scored && score < SCORE_MIN) {
            s = ScoreState.Barred;
            ++barredCount;
            _clearBlock(f);
        }
        f.state = s;
        emit Scored(family, passed, agreed, s, score);
        if (s != ScoreState.Neutral || fresh) _reseat(); // a Neutral family seen before changes no seat
    }

    /// A barred family's shadow verdict, scored once (Panels). Other families' shadow verdicts change nothing here.
    function recordShadow(bytes32 family, bool passed, bool agreed) external {
        if (msg.sender != panels) revert NotPanels();
        Family storage f = _f[family];
        if (f.state != ScoreState.Barred) return;
        if (passed) {
            ++f.bPassN;
            if (agreed) ++f.bPassAgree;
        } else {
            ++f.bFailN;
            if (agreed) ++f.bFailAgree;
        }
        emit ShadowScored(family, passed, agreed);
        if (uint256(f.bPassN) + f.bFailN < SCORE_RECOVER_VERDICTS) return;
        uint256 score = _balanced(f.bPassN, f.bPassAgree, f.bFailN, f.bFailAgree);
        bool recovered = score >= SCORE_MIN + SCORE_RECOVER_MARGIN;
        _clearBlock(f);
        if (recovered) {
            // the counted window restarts
            f.state = ScoreState.Recovering;
            recoveredAt[family] = block.number;
            --barredCount;
            f.n = 0;
            f.head = 0;
            f.passN = 0;
            f.passAgree = 0;
            f.failN = 0;
            f.failAgree = 0;
            f.fresh = 0;
        }
        emit BlockJudged(family, score, recovered);
        if (recovered) _reseat();
    }

    // ---------- views ----------

    function familyScore(bytes32 family) external view returns (ScoreState, uint256) {
        Family storage f = _f[family];
        return (f.state, _balanced(f.passN, f.passAgree, f.failN, f.failAgree));
    }

    /// Not drawn for counted panels (judge-scores, "A family below the minimum score isn't drawn").
    function isBarred(bytes32 family) external view returns (bool) {
        return _f[family].state == ScoreState.Barred;
    }

    /// Barred now, or recovered after block `snapshot`: a draw snapshotted then doesn't seat it (Panels).
    function isBarredSince(bytes32 family_, uint256 snapshot) external view returns (bool) {
        return _f[family_].state == ScoreState.Barred || recoveredAt[family_] > snapshot;
    }

    function family(bytes32 f) external view returns (Family memory) {
        return _f[f];
    }

    /// Drawn for counted panels now (D20): not barred, and not a contender.
    function isSeated(bytes32 family_) public view returns (bool) {
        return _f[family_].state != ScoreState.Barred && !_seats[family_].contender;
    }

    /// Seated now and already at block `snapshot` (not recovered, nor seated by rank, after it): a draw snapshotted
    /// then may seat it (Panels).
    function isSeatedSince(bytes32 family_, uint256 snapshot) external view returns (bool) {
        return isSeated(family_) && recoveredAt[family_] <= snapshot && _seats[family_].seatedAt <= snapshot;
    }

    /// Whether a draw snapshotted at block `snapshot` applies the family cap (D20): while at least CAP_MIN_FAMILIES
    /// families are seated, or when the cap switched since the snapshot (the stricter rule, against grinding).
    function capApplies(uint256 snapshot) external view returns (bool) {
        return seatedCount >= CAP_MIN_FAMILIES || capChangedAt > snapshot;
    }

    /// Fewer than CAP_MIN_FAMILIES families can judge: a challenge that can't draw its larger panel gets a second draw of
    /// the original size (D27, `SECOND_PANEL` "few families").
    function fewFamilies() external view returns (bool) {
        return seatedCount < CAP_MIN_FAMILIES;
    }

    /// Families whose validators shadow instead of judging counted panels: barred or contenders.
    function unseatedCount() external view returns (uint256) {
        return barredCount + contenderCount;
    }

    function seatOf(bytes32 family_) external view returns (Seat memory) {
        return _seats[family_];
    }

    function families() external view returns (bytes32[] memory) {
        return _families;
    }

    // ---------- internals ----------

    function _count(Family storage f, bool passed, bool agreed, bool add) internal {
        if (passed) {
            f.passN = add ? f.passN + 1 : f.passN - 1;
            if (agreed) f.passAgree = add ? f.passAgree + 1 : f.passAgree - 1;
        } else {
            f.failN = add ? f.failN + 1 : f.failN - 1;
            if (agreed) f.failAgree = add ? f.failAgree + 1 : f.failAgree - 1;
        }
    }

    /// Recomputes the best Scored score, each known family's seat, and the counts (D20): one read of each family, and
    /// a write only where something changed.
    function _reseat() internal {
        uint256 n = _families.length;
        bytes32[] memory fams = new bytes32[](n);
        uint256[] memory sc = new uint256[](n); // the score + 1 of a Scored family, 0 otherwise
        bool[] memory barred = new bool[](n);
        uint256 best;
        for (uint256 i; i < n; ++i) {
            bytes32 fam = _families[i];
            fams[i] = fam;
            Family storage f = _f[fam];
            ScoreState st = f.state;
            if (st == ScoreState.Barred) barred[i] = true;
            if (st != ScoreState.Scored) continue;
            uint256 v = _balanced(f.passN, f.passAgree, f.failN, f.failAgree);
            sc[i] = v + 1;
            if (v > best) best = v;
        }
        uint256 seated;
        uint256 contenders;
        for (uint256 i; i < n; ++i) {
            bool c = sc[i] != 0 && sc[i] - 1 + SEAT_MARGIN < best;
            Seat storage x = _seats[fams[i]];
            if (c != x.contender) {
                x.contender = c;
                if (!c) x.seatedAt = uint64(block.number);
                emit SeatChanged(fams[i], !c, best);
            }
            if (c) ++contenders;
            else if (!barred[i]) ++seated;
        }
        uint256 was = seatedCount;
        if ((was >= CAP_MIN_FAMILIES) != (seated >= CAP_MIN_FAMILIES)) capChangedAt = block.number;
        if (best != bestScore) bestScore = best;
        if (seated != was) seatedCount = seated;
        if (contenders != contenderCount) contenderCount = contenders;
    }

    function _clearBlock(Family storage f) internal {
        f.bPassN = 0;
        f.bPassAgree = 0;
        f.bFailN = 0;
        f.bFailAgree = 0;
    }

    /// The balanced agreement (WAD): the mean over passed and failed outcomes, or the one kind present; 0 with none.
    function _balanced(uint256 pn, uint256 pa, uint256 fn, uint256 fa) internal pure returns (uint256) {
        if (pn == 0 && fn == 0) return 0;
        if (pn == 0) return fa * WAD / fn;
        if (fn == 0) return pa * WAD / pn;
        return (pa * WAD / pn + fa * WAD / fn) / 2;
    }
}
