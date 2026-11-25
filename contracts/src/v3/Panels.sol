// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {IPanelsRegistry, IPanelsFees, IPanelScores} from "./IPanels.sol";
import {PanelsDraw} from "./PanelsDraw.sol";
import {PanelsJudge} from "./PanelsJudge.sol";
import {PanelsVerdict} from "./PanelsVerdict.sol";
import {PanelsBase, Store, Env, Submission, Panel, Seat, Status, Tier, Kind} from "./PanelsBase.sol";
import {Windows, WindowsLib} from "./Windows.sol";
import {PanelRules, PanelRulesLib, Cap, ChallengeSize} from "./PanelRules.sol";
import {LaunchChain} from "./LaunchChain.sol";

/// v3's panels (proof-of-fix#138, task 3.2 of #132; design D2–D7, D10, D13, D14, D16, D18, D19; ADR 0004;
/// specs/judge-panels, specs/judge-scores): who judges a submission, how many, and when their verdict is final. It
/// replaces v2's fixed "3 of 7" and "all 7" for v3 only.
///
/// **The draw (D2, D3; PanelsDraw).** The race opens a sealed submission at block B; Panels snapshots what the draw
/// will read (PanelsDraw.Snap: fixed before the seed is known, so a registry change made after it can't re-roll the
/// draw). From block B + SEED_DELAY + 1 anyone draws it with seed = keccak(blockhash(B + SEED_DELAY), commitment,
/// bounty, id); after 256 blocks the seed block re-targets. k is the largest odd number up to K_MAX that the snapshot's
/// count allows and whose level A limit covers the bounty, stepped down by 2 while the sample under the caps can't fill
/// it. A submission with no k waits, and so does one whose panel's proof level (D10) can't judge the bounty (void); a
/// waiting one is drawn again, from a fresh seed block and snapshot, after the registry changes. The draw is a view
/// (`sample`).
///
/// **Seals, reveals and receipts on-chain (D18).** Each drawn judge posts, signed by its key as a registry
/// `Statement(subject, content)` (two contents for one subject are provable equivocation): its seal,
/// `commitmentOf(pid, key, vote, mask, salt)`, by `sealBy`; then its reveal and its receipt's hash by `revealBy`. A
/// judging panel's reveal opens as soon as every seat is filled and sealed, without waiting for `sealBy` (#311); a
/// counted panel's, before its `sealBy`, also only once every shadow drawn with it has sealed, so no counted vote is
/// public while a shadow can still seal. `sealBy` stays the limit for a silent seat and `revealBy` for a reveal. Early
/// and replayed reveals are refused; a reveal that doesn't match its seal is `Fault.Mismatch` (the whole bond). The
/// counted result is the majority of the k reveals with receipts (CONSTITUTION_QUORUM of K_MAX at the constitution
/// tier). `mask` is a challenge judge's finding of false receipts, one bit per seat of the challenged panel (0
/// elsewhere).
///
/// **Replacement.** At a missed deadline anyone calls `advance`: silence costs SILENCE_SLASH, a sealed vote without its
/// reveal and receipt SEALED_NO_REVEAL_SLASH (the registry also counts the miss), and the next eligible validator in the
/// same sample takes the seat with a fresh window. k and the majority never change. Except (owner, 2026-11-13, option 2
/// of #227): on a counted panel whose revealed votes already decide ((k + 1) / 2 on one side; at the constitution tier
/// CONSTITUTION_QUORUM passes or more than k - CONSTITUTION_QUORUM fails), and whose revealed judges' level still covers
/// the bounty, a missed reveal is slashed but not replaced, and the verdict counts with the revealed votes: no
/// replacement seals after the reveals are public where it couldn't change the outcome. Its seat is left empty
/// (`judges` returns 0 for it). Challenge and audit panels always replace.
///
/// **Shadows (D5).** Each draw also seats SHADOW_PER_DRAW (SHADOW_PER_DRAW_SMALL while fewer than K_MAX are active)
/// shadows, candidates or validators of a barred family, sealing in the same seal window (the counted reveal waits for
/// them, up to `sealBy`); a submission that waits gets SHADOW_PER_WAITING, whose seal window closes when its counted
/// panel is drawn (#311). They're never replaced or slashed for silence; after their deadline the registry counts each
/// reveal or miss (`settleShadows`; a waiting shadow cut short by the draw that hadn't sealed counts neither). Each
/// revealed shadow is scored once: against the final outcome of a panel no lone validator decided, or, for a k = 1
/// verdict held at its count and for a waiting or withdrawn submission, against the majority of the verdicts sealed on
/// it (counted and shadow) when at least 3 were revealed.
///
/// **Audits (D13).** At a counted verdict an audit block and snapshot are fixed; from that block a random
/// AUDIT_RATE_BPS share is decided, and every k = 1 verdict gets K1_AUDITS and every split level C pass one. Each auditor,
/// drawn as soon as one is eligible, is a one-seat panel outside the original; a result that differs from the verdict
/// opens a challenge with no stake.
///
/// **Challenges (D4).** The race files a challenge (it holds the stakes); a fresh panel of CHALLENGE_K[k] (or the
/// largest odd number above k the network allows; K_MAX for K_MAX), without the original judges, its auditors or
/// parties, judges the fix and each original judge's receipt. Until one can be drawn it waits, and the window is
/// frozen. A false receipt found by its majority is `Fault.FalseVerdict` (the whole bond, the challenger's share); the
/// challenge panel's majority decides the fix. While fewer than CAP_MIN_FAMILIES families are seated (#132 D27,
/// `SECOND_PANEL` "few families"), a challenge of a panel of 3 or more that can't draw its larger panel is judged by a
/// second draw of the original size, the original judges not excluded (`SecondDraw`); a lone verdict's challenge still
/// waits (its hold does). A test-backed dispute (D21) is a challenge the race
/// files with the test's hash as its evidence; the race holds its stake and pays its reward.
///
/// **Seats by rank (#132 D20).** Counted, audit, challenge and replacement draws seat only validators of seated
/// families (PanelScores: within SEAT_MARGIN of the best Scored family, not barred); contenders shadow. The family cap
/// applies only while at least CAP_MIN_FAMILIES families are seated.
///
/// **Proof levels (D10, task 3.4).** A panel's level is its majority's weakest; each (k, level) has its own largest
/// bounty and window (`limitOf`, `windowOf`). A submission opened with `openHidden` (hidden tests or a private
/// repository) draws level A or B validators only, for every seat: counted, shadow, auditor and challenger, and for its
/// k = 1 hold's challengers. The registry's lists change only by ADR (`Validators.applyAdr`, after `adrPassed` at the
/// ADR's finality); a validator out of standing (a delisted type or image, firmware below its type's minimum) isn't
/// drawn. The TEE-type cap's start follows the registry's count of accepted types.
///
/// **Finality (D4, D14).** A counted verdict is final once its window has passed with its audits done and no challenge
/// open: CHALLENGE_WINDOW[k, level], or ADR_WINDOW / REMOVAL_WINDOW for ADRs whatever the level. A k = 1 verdict is held
/// until CHALLENGE_K[1] validators could judge its challenge. At finality each counted judge's family is scored against
/// the final outcome (PanelScores), and the shadows are scored.
///
/// **The constitution tier (D7).** ADRs and escalated fixes draw exactly K_MAX under the caps, only while at least
/// CONSTITUTION_MIN_ELIGIBLE (REMOVAL_MIN_ELIGIBLE for an ADR that only removes) are eligible, else they expire
/// unjudged. Each posts ADR_DEPOSIT, refunded when it takes effect or expires, and forfeited to the sponsors' pool when
/// rejected. An ADR passed and final is reported to the registry (`adrPassed`, with its commitment and whether it's a
/// removal), whose lists anyone may then update with the operations it bound (`Validators.adrCommitment`).
///
/// **The split (EIP-170).** Panels holds the state (`Store`, PanelsBase) and the race's entry points; the rules run in
/// linked libraries on that state: PanelsJudge (seals, reveals, receipts, replacement), PanelsVerdict (draws,
/// counting, audits, challenges, shadows, finality) and PanelsDraw (the sampling).
///
/// **The windows (#251, design L4).** SEAL_WINDOW, REVEAL_WINDOW, CHALLENGE_WINDOW[k, level], ADR_WINDOW,
/// REMOVAL_WINDOW and K1_WINDOW_MIN are the deployment's, passed to the constructor as one `Windows` struct, checked
/// for order (WindowsLib.check), stored as immutables and readable (`windows`, `windowOf`). They must be exactly the
/// registry's (`Validators.windowsHash`), whose unbonding delay derives from them. The production values
/// (WindowsLib.production, ADR 0004) give what the constants gave.
///
/// **Stuck rounds are released, never stuck (#251, design L19; specs/panel-liveness).** A counted or audit panel with
/// a seat its replacements couldn't fill ends STUCK_GRACE after its reveal deadline (`release`): its silent seats are
/// slashed as any silence, the others close unslashed, and a counted round sends the submission back to waiting with
/// a redraw scheduled; an audit that no validator could take for STUCK_GRACE is released the same way
/// (`releaseAudits`). A waiting submission is drawn again with a fresh seed once the registry changes or at its
/// `retryAt` (RETRY_DELAY later). The MAX_REDRAWS-th released round (or the race's deadline for a parked one,
/// `abandon`) makes it `Released`: never judged, and the race refunds its bounty with no slash for the solver. So
/// every submission is always drawn with a live deadline, waiting with a scheduled redraw, counted, final, or refunded.
///
/// **Capacity (#251, design L16; #253's spending controls).** A validator takes at most its capacity of seats (any
/// kind) in a trailing `capWindow` (an hour in production): CHECKS_DEFAULT (MAX_CHECKS_PER_HOUR, 5) until it sets its
/// own with `setCapacity`, at most CHECKS_CEILING; 0 pauses it. A full or paused validator is skipped by every draw,
/// never slashed. A paused one is as if absent (a panel steps down without it); a full one is busy for at most
/// `capWindow`, so a panel that busy validators leave short waits for them rather than shrinking: a counted draw
/// waits and is retried after `capWindow`, and an audit or a challenge is retried from the same seed. A change takes
/// effect CAP_DELAY blocks after it's made (more than a seed block's 256-block life plus SEED_DELAY), and no change is made
/// while one is pending: a validator that learns from a seed block that it's about to be drawn can't pause in time to
/// dodge that draw. Pausing applies to later draws only; a seat already given is judged or slashed as usual.
/// REPO_CHECKS_PER_HOUR, a per-repository cap, is 0 (off) while a deployment serves one repository (L16, D31).
///
/// **The panel rules (#251 contract batch 4, design L23, L24; PanelRules).** The deployment's, passed to the
/// constructor beside its windows, immutable and readable (`panelRules`): the operator, host and TEE-type caps each
/// `Strict` (the rules above) or `Off` (dropped from every draw and from the k = 1 hold's count of challengers, which
/// under `Strict` counts only challengers that could sit together under them); `kTop`, the largest issue-tier panel
/// (the constitution tier keeps K_MAX); and `challengeSize`: `Larger` (D4's CHALLENGE_K) or `Same`, a fresh panel of
/// the challenged verdict's size for k >= 3, without the original judges, its auditors and its replaced judges, with
/// no step-down (a lone verdict's challenge keeps 3; D27's second draw stays the fallback). The defaults are #132's
/// (all `Strict`, 7, `Larger`); the Sepolia launch sets all `Off`, 3 and `Same`.
///
/// **Challenges always end (#251 batch 4, design L25; specs/panel-liveness).** Each challenge (filed, disputed, or
/// opened by an auditor's mismatch) has CHALLENGE_DEADLINE from its opening (`Windows.challengeDeadline`). A waiting
/// challenge is drawn again once the registry changes or at its retry time (RETRY_DELAY). A challenge panel whose
/// replacements are exhausted is released as a counted one is (`release`): before the deadline the challenge waits
/// again, after it the challenge lapses. Past the deadline a challenge with no panel lapses (`lapseChallenge`). A lapse
/// leaves the verdict as it was, resumes its window where it froze and closes the challenge for the original judges;
/// the race returns the challenger's stake and cover whole, with no reward. A verdict takes at most MAX_REDRAWS lapsed
/// challenges (decided (owner, 2026-11-20)); after that new ones are refused and it finalizes at its window.
///
/// Keyless: no owner, no admin, no setter. The registry and the scores are bound once from the constructor; the race
/// binds itself once (`bind`). A validator's capacity is its own setting, not an admin power. The constructor reverts off Sepolia and the local test chains (LaunchChain).
///
/// TODO(3.5): the race checks `Validators.isRemoval` before opening a `Removal` ADR and `openHidden` for hidden tests and
/// private repositories; it forwards FeesV3's `waited`, `stalled` and `drawn`
/// (from Panels' status and events), keeps a submission's parties fixed from its opening (they're read at the draw),
/// and settles challenge stakes and shadow pay.
contract Panels {
    using SafeERC20 for IERC20;

    uint256 public constant K_MAX = 7;
    uint256 public constant DRAW_TRIES = 8;
    uint256 public constant SEED_DELAY = 5;
    uint256 public constant K1_PENDING_MAX = 10;
    uint256 public constant TEE_CAP_K3_TYPES = 5;
    /// The largest bounty any panel may judge: k = 5 and 7 at level A (v2's BOUNTY_MAX).
    uint256 public constant BOUNTY_MAX = 625e6;
    uint256 public constant SHADOW_PER_DRAW = 1;
    uint256 public constant SHADOW_PER_DRAW_SMALL = 2; // while fewer than K_MAX validators are active
    uint256 public constant SHADOW_PER_WAITING = 3;
    uint256 public constant AUDIT_RATE_BPS = 1_000;
    uint256 public constant K1_AUDITS = 2;
    uint256 public constant CONSTITUTION_QUORUM = 5;
    uint256 public constant CONSTITUTION_MIN_ELIGIBLE = 21;
    uint256 public constant REMOVAL_MIN_ELIGIBLE = 14;
    uint256 public constant ADR_DEPOSIT = 15e6;
    bytes32 public constant SEAL_TAG = keccak256("proof-of-fix v3 seal");
    bytes32 public constant REVEAL_TAG = keccak256("proof-of-fix v3 reveal");
    bytes32 public constant RECEIPT_TAG = keccak256("proof-of-fix v3 receipt");
    /// MAX_CHECKS_PER_HOUR until a validator sets its own (L16), and the protocol's ceiling on it.
    uint256 public constant CHECKS_DEFAULT = 5;
    uint256 public constant CHECKS_CEILING = 16;
    /// Blocks from a capacity change to its effect: a seed block's hash lives 256 blocks, after SEED_DELAY.
    uint256 public constant CAP_DELAY = 262;
    /// The per-repository cap (D31): 0, off, while the deployment serves one repository (L16).
    uint256 public constant REPO_CHECKS_PER_HOUR = 0;

    IPanelsRegistry public immutable validators;
    IPanelsFees public immutable fees;
    IPanelScores public immutable scores;
    address public immutable coin;
    address public immutable pool;
    bytes32 internal immutable _domain;
    uint256 public immutable SEAL_WINDOW;
    uint256 public immutable REVEAL_WINDOW;
    uint256 public immutable ADR_WINDOW;
    uint256 public immutable REMOVAL_WINDOW;
    /// k = 1's challenge window is at least this at every level (D4: 7 days in production).
    uint256 public immutable K1_WINDOW_MIN;
    uint256 internal immutable _chalAB; // CHALLENGE_WINDOW at levels A and B (WindowsLib.pack)
    uint256 internal immutable _chalC; // and at level C
    uint256 public immutable STUCK_GRACE;
    uint256 public immutable RETRY_DELAY;
    uint256 public immutable MAX_REDRAWS;
    /// The trailing window MAX_CHECKS_PER_HOUR counts over (an hour in production).
    uint256 public immutable CAP_WINDOW;
    /// A rejected fix's one appeal is filed within this of its counted panel's reveal deadline (#132 D24; 72 h).
    uint256 public immutable APPEAL_WINDOW;
    /// How long a merged fix or an upheld test dispute keeps its solver active (launch L6; 26 weeks). The race's
    /// SolverBook reads it.
    uint256 public immutable ACTIVE_WINDOW;
    /// A challenge with no panel lapses this long after its opening (L25; 120 h, decided (owner, 2026-11-20)).
    uint256 public immutable CHALLENGE_DEADLINE;
    // The panel rules (L23, L24): the caps (true: Strict), the largest issue-tier panel and the challenge's size.
    bool internal immutable _opCap;
    bool internal immutable _hostCap;
    bool internal immutable _teeCap;
    uint256 internal immutable _kTop;
    bool internal immutable _sameSize;
    Store internal _st;

    // The libraries' events, declared here too so Panels' ABI carries them.
    event Bound(address indexed race);
    event Opened(uint256 indexed id, Tier tier, uint256 bounty, uint256 seedBlock);
    event Withdrawn(uint256 indexed id);
    event Retargeted(uint256 indexed id, uint256 seedBlock);
    event Waited(uint256 indexed id, uint256 k, uint8 level);
    event Expired(uint256 indexed id);
    event Drawn(uint256 indexed id, uint256 indexed pid, Kind kind, uint256 k, bytes32 seed);
    event Seated(uint256 indexed pid, uint256 slot, address indexed key, uint256 sealBy);
    event DepositReturned(uint256 indexed id, address indexed to, bool refunded);
    event Sealed(uint256 indexed pid, address indexed key, bytes32 seal);
    event Revealed(uint256 indexed pid, address indexed key, bool vote, uint8 mask);
    event Receipt(uint256 indexed pid, address indexed key, bytes32 receipt);
    event Mismatch(uint256 indexed pid, address indexed key);
    event Missed(uint256 indexed pid, address indexed key, bool hadSeal);
    event Stalled(uint256 indexed pid, uint256 vacant);
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
    event Released(uint256 indexed id, uint256 indexed pid, uint256 redraws);
    event Refunded(uint256 indexed id);
    event CapacitySet(address indexed key, uint256 checks, uint256 fromBlock);
    event ChallengeReleased(uint256 indexed id, uint256 indexed pid, bool lapsed);
    event ChallengeLapsed(uint256 indexed id, uint256 lapses);

    // Panels' errors and its libraries' (same selectors).
    error BadParams();
    error AlreadyBound();
    error NotRace();
    error WrongStatus();
    error BadBounty();
    error Busy();
    error TooEarly();
    error TooLate();
    error NothingChanged();
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
    error NotYours();
    error TooManyLapses();

    /// `teeTypes_`: the accepted TEE types at deployment, exactly the registry's list (a deployment check). The TEE-type
    /// cap starts at k = 3 while at least TEE_CAP_K3_TYPES types are accepted, else at k = 5 (D6), following the
    /// registry's list as ADRs change it. `windows_`: the deployment's windows, checked for order and exactly the
    /// registry's (#251, L4). `rules_`: the panel rules (#251 batch 4, L23 and L24), `kTop` odd from 1 to K_MAX.
    constructor(
        IPanelsRegistry validators_,
        IPanelsFees fees_,
        IPanelScores scores_,
        bytes32[] memory teeTypes_,
        Windows memory windows_,
        PanelRules memory rules_
    ) {
        LaunchChain.check();
        WindowsLib.check(windows_);
        PanelRulesLib.check(rules_);
        if (
            address(validators_).code.length == 0 || address(fees_).code.length == 0
                || address(scores_).code.length == 0 || teeTypes_.length != validators_.teeTypeCount()
                || validators_.windowsHash() != keccak256(abi.encode(windows_))
        ) revert BadParams();
        for (uint256 i; i < teeTypes_.length; ++i) {
            if (!validators_.acceptedTeeType(teeTypes_[i])) revert BadParams();
            for (uint256 j; j < i; ++j) {
                if (teeTypes_[j] == teeTypes_[i]) revert BadParams();
            }
        }
        validators = validators_;
        fees = fees_;
        scores = scores_;
        coin = validators_.coin();
        pool = validators_.pool();
        _domain = validators_.domainSeparator();
        SEAL_WINDOW = windows_.seal;
        REVEAL_WINDOW = windows_.reveal;
        ADR_WINDOW = windows_.adr;
        REMOVAL_WINDOW = windows_.removal;
        K1_WINDOW_MIN = windows_.k1Min;
        (_chalAB, _chalC) = WindowsLib.pack(windows_);
        STUCK_GRACE = windows_.stuckGrace;
        RETRY_DELAY = windows_.retryDelay;
        MAX_REDRAWS = windows_.maxRedraws;
        CAP_WINDOW = windows_.capWindow;
        APPEAL_WINDOW = windows_.appeal;
        ACTIVE_WINDOW = windows_.active;
        CHALLENGE_DEADLINE = windows_.challengeDeadline;
        _opCap = rules_.operatorCap == Cap.Strict;
        _hostCap = rules_.hostCap == Cap.Strict;
        _teeCap = rules_.teeCap == Cap.Strict;
        _kTop = rules_.kTop;
        _sameSize = rules_.challengeSize == ChallengeSize.Same;
        validators_.bind();
        scores_.bind();
    }

    // ---------- the race ----------

    function bind() external {
        if (_st.race != address(0)) revert AlreadyBound();
        _st.race = msg.sender;
        emit Bound(msg.sender);
    }

    /// A sealed submission `id` to a bounty of `bounty` micro-coins: its seed comes from the block SEED_DELAY later.
    function open(uint256 id, bytes32 commitment, uint256 bounty) external {
        Submission storage s = _new(id, commitment, bounty);
        PanelsBase.start(_env(), s);
        emit Opened(id, Tier.Issue, bounty, s.seedBlock);
    }

    /// `open` for a submission with hidden tests or to a private repository (D10, task 3.4): every judge drawn for it,
    /// counted, shadow, auditor or challenger, is at level A or B, since a level C node could read what it hides.
    function openHidden(uint256 id, bytes32 commitment, uint256 bounty) external {
        Submission storage s = _new(id, commitment, bounty);
        s.teeOnly = true;
        PanelsBase.start(_env(), s);
        emit Opened(id, Tier.Issue, bounty, s.seedBlock);
    }

    /// An ADR (`Adr`, `Removal`) or an escalated fix (`Escalated`, with its bounty) at the constitution tier, with
    /// ADR_DEPOSIT pulled from the race for `author`. On a network too small for it, it expires at once, refunded.
    function openConstitution(uint256 id, bytes32 commitment, Tier tier, uint256 bounty, address author) external {
        if (tier == Tier.Issue || author == address(0)) revert BadParams();
        Submission storage s = _new(id, commitment, tier == Tier.Escalated ? bounty : 1);
        s.tier = tier;
        s.author = author;
        IERC20(coin).safeTransferFrom(msg.sender, address(this), ADR_DEPOSIT);
        Env memory e = _env();
        PanelsBase.start(e, s);
        emit Opened(id, tier, bounty, s.seedBlock);
        if (s.snap.nLive < PanelsBase.minEligible(tier)) PanelsBase.expire(e, id, s);
    }

    /// The solver withdraws an issue-tier submission no panel has been seated for.
    function withdraw(uint256 id) external {
        _onlyRace();
        Submission storage s = _st.subs[id];
        if (s.tier != Tier.Issue || (s.status != Status.Sealed && s.status != Status.Waiting)) revert WrongStatus();
        s.status = Status.Withdrawn;
        emit Withdrawn(id);
    }

    /// A challenge of a counted verdict in its window (or held), by `challenger` with `evidence`; the race holds the
    /// stake. One at a time; none once MAX_REDRAWS challenges of it lapsed (L25).
    function challenge(uint256 id, address challenger, bytes32 evidence) external {
        _onlyRace();
        Submission storage s = _st.subs[id];
        if (s.challengeOpen) revert Busy();
        if (s.status != Status.Held && (s.status != Status.Window || block.timestamp >= s.finalAt)) {
            revert WrongStatus();
        }
        if (s.lapses >= MAX_REDRAWS) revert TooManyLapses();
        PanelsVerdict.openChallenge(_st, _env(), id, challenger, evidence);
        s.chalFiled = true;
        s.filedLapsed = false;
    }

    // ---------- anyone ----------

    /// Draws submission `id`'s panel and its shadows; or, for a waiting submission after a registry change, or a seed
    /// block more than 256 blocks back, re-targets the seed block (and the snapshot) to SEED_DELAY blocks from now.
    function draw(uint256 id) external {
        PanelsVerdict.draw(_st, _env(), id);
    }

    /// From a verdict's audit block: decides its random audit (once), then draws the auditors due, each as soon as
    /// one is eligible; with none eligible, the audit block and its snapshot re-target for the next try.
    function drawAudits(uint256 id) external {
        PanelsVerdict.drawAudits(_st, _env(), id);
    }

    /// Draws an open challenge's panel from its seed block; or, while it waits for validators, re-targets after a
    /// registry change.
    function drawChallenge(uint256 id) external {
        PanelsVerdict.drawChallenge(_st, _env(), id);
    }

    /// Seat `key`'s seal on panel `pid`, signed by `key` over Statement(sealSubject, seal), within its seal window.
    function seal(uint256 pid, address key, bytes32 sealHash, bytes calldata sig) external {
        PanelsJudge.seal(_st, _env(), pid, key, sealHash, sig);
    }

    /// Seat `key`'s reveal, signed over Statement(revealSubject, keccak(vote, mask, salt)), in the reveal window. A
    /// reveal that doesn't match its seal is a fault: slashed (Mismatch), and a judging seat replaced; the call
    /// succeeds.
    function reveal(uint256 pid, address key, bool vote, uint8 mask, bytes32 salt, bytes calldata sig) external {
        PanelsJudge.reveal(_st, _env(), pid, key, vote, mask, salt, sig);
    }

    /// Seat `key`'s receipt hash, signed over Statement(receiptSubject, receipt), in the reveal window. A verdict
    /// counts only with its receipt (judge-panels, "A counted verdict carries proof that the check ran").
    function receipt(uint256 pid, address key, bytes32 receiptHash, bytes calldata sig) external {
        PanelsJudge.receipt(_st, _env(), pid, key, receiptHash, sig);
    }

    /// After a missed deadline on a counted, audit or challenge panel: every seat that didn't seal by `sealBy`
    /// (silence), or, once all had sealed, didn't reveal with its receipt by `revealBy`, is a miss and is replaced from
    /// the same sample with a fresh window.
    function advance(uint256 pid) external {
        PanelsJudge.advance(_st, _env(), pid);
    }

    /// A panel with an empty seat (its sample yielded nobody) tries again, from a snapshot of now: the registry may
    /// have grown since its draw.
    function refill(uint256 pid) external {
        PanelsJudge.refill(_st, _env(), pid);
    }

    /// After a shadow panel's reveal deadline: the registry counts each shadow's reveal or miss (once), then each
    /// revealed shadow is scored once the outcome it's scored against exists (D5).
    function settleShadows(uint256 spid) external {
        PanelsVerdict.settleShadows(_st, _env(), spid);
    }

    /// A counted, audit or challenge panel whose replacements couldn't fill a seat, STUCK_GRACE after its reveal
    /// deadline: the round ends, its silent seats slashed; the submission waits for a redraw, or its audit is due
    /// again (L19); a challenge waits for a redraw, or lapses past its CHALLENGE_DEADLINE (L25).
    function release(uint256 pid) external {
        PanelsJudge.release(_st, _env(), pid);
    }

    /// An open challenge with no panel, past its CHALLENGE_DEADLINE, lapses: the verdict stands and its window resumes
    /// (L25).
    function lapseChallenge(uint256 id) external {
        PanelsJudge.lapseChallenge(_st, _env(), id);
    }

    /// A verdict's audit no validator could take for STUCK_GRACE: the round is released and the audit drawn again
    /// from a fresh audit block (L19).
    function releaseAudits(uint256 id) external {
        PanelsJudge.releaseAudits(_st, _env(), id);
    }

    /// The race's deadline for a submission parked after a released round: it's refunded (`Released`, L19).
    function abandon(uint256 id) external {
        _onlyRace();
        PanelsJudge.abandon(_st, _env(), id);
    }

    /// A validator's capacity, set by its key or its operator: `checks` seats a `CAP_WINDOW` at most (0 pauses it, at
    /// most CHECKS_CEILING), from CAP_DELAY blocks on; refused while an earlier change is still pending (L16, #253).
    function setCapacity(address key, uint256 checks) external {
        if (msg.sender != key && msg.sender != validators.validator(key).operator) revert NotYours();
        if (checks > CHECKS_CEILING) revert BadParams();
        PanelsDraw.Load storage l = _st.load[key];
        if (block.number < l.from) revert Busy();
        uint256 from = block.number + CAP_DELAY;
        l.prev = l.cap;
        l.cap = uint8(checks + 1);
        l.from = uint64(from);
        emit CapacitySet(key, checks, from);
    }

    /// A validator's capacity: in force now, the next (equal unless a change is pending) from block `from`, and
    /// whether it has room for a seat now.
    function capacity(address key) external view returns (uint256 checks, uint256 next, uint256 from, bool room) {
        PanelsDraw.Load storage l = _st.load[key];
        checks = PanelsDraw.capOf(l);
        next = l.cap == 0 ? CHECKS_DEFAULT : l.cap - 1;
        from = l.from;
        room = PanelsDraw.hasRoom(l, CAP_WINDOW);
    }

    /// A held k = 1 verdict's window starts once CHALLENGE_K[1] validators could judge its challenge (D4).
    function startWindow(uint256 id) external {
        PanelsVerdict.startWindow(_st, _env(), id);
    }

    /// A counted verdict whose window has passed, with its audits done and no challenge open, is final: its judges'
    /// verdicts close in the registry, their families are scored against the outcome, its shadows are scored, and a
    /// constitution-tier deposit is refunded (passed) or forfeited to the sponsors' pool (rejected).
    function finalize(uint256 id) external {
        PanelsVerdict.finalize(_st, _env(), id);
    }

    // ---------- views ----------

    function race() external view returns (address) {
        return _st.race;
    }

    function panelCount() external view returns (uint256) {
        return _st.panelCount;
    }

    function k1Pending(address key) external view returns (uint256) {
        return _st.k1Pending[key];
    }

    function submission(uint256 id) external view returns (Submission memory) {
        return _st.subs[id];
    }

    function panel(uint256 pid) external view returns (Panel memory) {
        return _st.panels[pid];
    }

    function seat(uint256 pid, uint256 slot) external view returns (Seat memory) {
        return _st.seats[pid][slot];
    }

    /// The panel's seated validators in seat order (0 for an empty seat).
    function judges(uint256 pid) external view returns (address[] memory keys) {
        uint256 k = _st.panels[pid].k;
        keys = new address[](k);
        for (uint256 i; i < k; ++i) {
            keys[i] = _st.seats[pid][i].key;
        }
    }

    /// The counted panel `draw` would seat now for submission `id` with `seed`, from its snapshot: k (0: none), its
    /// level (void if `limitOf(k, level)` is below the bounty), its validators in seat order, and the sample's next try.
    function sample(uint256 id, bytes32 seed)
        external
        view
        returns (uint256 k, uint8 level, address[] memory keys, uint256 counter)
    {
        PanelsDraw.Ctx memory c;
        (c, k, level) = PanelsBase.drawCounted(_st, _env(), id, seed);
        keys = new address[](k);
        for (uint256 i; i < k; ++i) {
            keys[i] = c.members[i].key;
        }
        counter = c.counter;
    }

    /// The seed of a draw (D3).
    function seedOf(bytes32 blockHash, bytes32 commitment, uint256 bounty, uint256 id) external pure returns (bytes32) {
        return keccak256(abi.encode(blockHash, commitment, bounty, id));
    }

    /// What a judge seals: its vote, its mask (a challenge judge's false receipts, one bit per challenged seat) and a
    /// secret salt, bound to this Panels, the panel and its key.
    function commitmentOf(uint256 pid, address key, bool vote, uint8 mask, bytes32 salt)
        external
        view
        returns (bytes32)
    {
        return PanelsBase.commitmentOf(pid, key, vote, mask, salt);
    }

    /// The subject of a judge's statement on a panel: `tag` is SEAL_TAG, REVEAL_TAG or RECEIPT_TAG.
    function subjectOf(bytes32 tag, uint256 pid, address key) external view returns (bytes32) {
        return PanelsBase.subjectOf(tag, pid, key);
    }

    /// The registry's statement digest (`Validators.statementDigest`), computed here from its domain.
    function statementDigest(bytes32 subject, bytes32 content) external view returns (bytes32) {
        return PanelsBase.statementDigest(_domain, subject, content);
    }

    function limitOf(uint256 k, uint8 level) external pure returns (uint256) {
        return PanelsDraw.limitOf(k, level);
    }

    /// CHALLENGE_WINDOW[k, level], the deployment's.
    function windowOf(uint256 k, uint8 level) external view returns (uint256) {
        return WindowsLib.windowOf(_chalAB, _chalC, k, level);
    }

    /// The deployment's windows, as the constructor took them.
    function windows() external view returns (Windows memory w) {
        w.seal = SEAL_WINDOW;
        w.reveal = REVEAL_WINDOW;
        w.adr = ADR_WINDOW;
        w.removal = REMOVAL_WINDOW;
        w.k1Min = K1_WINDOW_MIN;
        w.stuckGrace = STUCK_GRACE;
        w.retryDelay = RETRY_DELAY;
        w.maxRedraws = MAX_REDRAWS;
        w.capWindow = CAP_WINDOW;
        w.appeal = APPEAL_WINDOW;
        w.active = ACTIVE_WINDOW;
        w.challengeDeadline = CHALLENGE_DEADLINE;
        uint8[3] memory levels = [1, 2, 3];
        uint256[4] memory ks = [uint256(1), 3, 5, 7];
        for (uint256 l; l < 3; ++l) {
            for (uint256 i; i < 4; ++i) {
                w.challenge[l][i] = WindowsLib.windowOf(_chalAB, _chalC, ks[i], levels[l]);
            }
        }
    }

    function challengeK(uint256 k) external pure returns (uint256) {
        return PanelsBase.challengeK(k);
    }

    /// The deployment's panel rules, as the constructor took them (L23, L24).
    function panelRules() external view returns (PanelRules memory) {
        return PanelRules(
            _opCap ? Cap.Strict : Cap.Off,
            _hostCap ? Cap.Strict : Cap.Off,
            _teeCap ? Cap.Strict : Cap.Off,
            _kTop,
            _sameSize ? ChallengeSize.Same : ChallengeSize.Larger
        );
    }

    /// A challenge panel's size for a verdict of k under these rules: the first k tried and the smallest (L24).
    function challengeRange(uint256 k) external view returns (uint256 top, uint256 min) {
        return PanelsBase.challengeRange(_env(), k);
    }

    function teeCapFrom() external view returns (uint256) {
        return PanelsBase.teeCapFrom(_env());
    }

    // ---------- internals ----------

    function _env() internal view returns (Env memory) {
        return Env(
            validators,
            fees,
            scores,
            coin,
            pool,
            _domain,
            SEAL_WINDOW,
            REVEAL_WINDOW,
            ADR_WINDOW,
            REMOVAL_WINDOW,
            _chalAB,
            _chalC,
            STUCK_GRACE,
            RETRY_DELAY,
            MAX_REDRAWS,
            CAP_WINDOW,
            CHALLENGE_DEADLINE,
            _opCap,
            _hostCap,
            _teeCap,
            _kTop,
            _sameSize
        );
    }

    function _onlyRace() internal view {
        if (msg.sender != _st.race) revert NotRace();
    }

    function _new(uint256 id, bytes32 commitment, uint256 bounty) internal returns (Submission storage s) {
        _onlyRace();
        s = _st.subs[id];
        if (s.status != Status.None) revert WrongStatus();
        if (bounty == 0 || bounty > BOUNTY_MAX) revert BadBounty();
        s.commitment = commitment;
        s.bounty = uint128(bounty);
    }
}
