// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {IERC20Metadata} from "@openzeppelin/contracts/token/ERC20/extensions/IERC20Metadata.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {MessageHashUtils} from "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";
import {ReentrancyGuardTransient} from "@openzeppelin/contracts/utils/ReentrancyGuardTransient.sol";
import {IValidators} from "./IValidators.sol";
import {Windows, WindowsLib} from "./Windows.sol";
import {LaunchChain} from "./LaunchChain.sol";

/// The sponsors' pool's funding call (v2's `Pool.fund`): the registry's share of every slash goes there.
interface IPoolFund {
    function fund(address coin, uint256 amount) external returns (uint256 received);
}

/// v3's open validator registry (proof-of-fix#138, task 3.1 of #132; design D1, D2, D5, D16, D18; ADR 0004;
/// specs/validator-admission). It replaces v2's seven fixed seats and co-signed joins, for v3 only (v2 is unchanged).
///
/// Registration is permissionless: any account posts at least BOND_FLOOR in the fee coin for a key that signs its own
/// registration (EIP-712, this contract's domain), naming an accepted proof type, an accepted TEE type (none for
/// zkTLS), an attestation's hash, a checker image on the allowed list, its infrastructure host, its model family and
/// its operator account. Nobody co-signs. The record is public and the family never changes: another family is
/// another key (D6, gap 17). The attestation itself is checked off-chain by the drawn panel (design, Non-goals).
///
/// The Radicle node key (#251, design L11 condition 1, owner 2026-11-20): each registration signs its node's Ed25519
/// public key (`radNode`), stored in the record and readable by anyone (`radNodeOf`, the `Registered` event's indexed
/// topic), so a seat maps to one node and `verify-delegates` reads it from the chain. 0 names no node: the validator
/// still judges, but its seat isn't counted as a delegate. A node key held by another registration that isn't leaving
/// or exited is refused (`NodeTaken`); once that one leaves, the key is free again. There is no setter: a validator
/// changes its node by registering again (a new key, after leaving with the old one).
///
/// Lists (D6, D10, D11, D18; task 3.4): the accepted proof types, TEE types (each with its minimum firmware level),
/// checker image digests and zkTLS notaries. The genesis lists them (no notary, no zkTLS); after that only an ADR the
/// constitution tier passed changes them (`applyAdr`, from Panels' `adrPassed` at the ADR's finality: REMOVAL_WINDOW
/// for an ADR that only removes or raises a minimum, the full ADR_WINDOW for anything else).
/// - Proof types this code has a verifier path for: PROOF_TEE (levels A and B, declared, checked off-chain), PROOF_ZKTLS
///   (level C) and PROOF_SIMULATED (devnets only, level A). Any other id is refused, at genesis and by ADR: the
///   constitution only switches verifier paths on or off, never adds verifier code (owner, 2026-11-03).
/// - zkTLS is in the code but can't be on the genesis list: level C is off at launch (D10). An adding ADR lists it with
///   its notaries; while it's listed at least one notary must be.
/// - `simulated` is refused unless block.chainid is 31337 or 7193 (D18), at deployment and by ADR.
/// - A TEE-only deployment (`teeOnly`, #251 design L10: Sepolia's) refuses zkTLS by ADR too, so level C can never be
///   listed there: the genesis never lists it, and `applyAdr` reverts an ADR that adds it.
/// - No ADR removes the last accepted TEE type or image digest (owner, 2026-11-03), nor PROOF_TEE (every TEE type).
/// - A validator is in standing while its proof type, TEE type and image are listed and its attested firmware is at
///   least its type's minimum. One out of standing isn't drawn (counted or shadow) and keeps its bond and state. After
///   a raised minimum or a new image it re-attests (`reattest`, signed by its key) and returns without qualifying again;
///   after a removed TEE or proof type it registers again. A removed TEE type (or zkTLS) leaves the tier counters at
///   once, by its group (O(tiers)); validators left out of standing otherwise are skipped by the draw at once and
///   leave the counters when anyone calls `recheck`.

/// States: Candidate → Active (automatic, by qualification) → Leaving → Exited; an Active validator below the
/// reveal-rate floor goes back to Candidate (suspended) and re-qualifies the same way (validator-admission, "A
/// validator stops being drawn when it can't serve").
/// - BelowFloor (#251, design L5; validator-admission, "A validator below the bond floor is visibly inactive"): an
///   Active validator whose bond falls below BOND_FLOOR (a slash) becomes BelowFloor in the same transaction, with
///   `WentBelowFloor`; it leaves `activeCount` and is never drawn. A top-up to the floor brings it back to Active
///   (`BackAboveFloor`) without qualifying again; it may also leave, under the same unbonding conditions. Its misses
///   still count toward the reveal-rate floor. So `activeCount` is always the number of Active validators, and every
///   Active validator is bonded at least BOND_FLOOR.
/// - Qualification (D5): QUALIFY_VERDICTS scored shadow verdicts, a reveal rate of at least QUALIFY_REVEAL_BPS over the
///   attempt's shadow draws and an agreement of at least QUALIFY_AGREE_BPS. No vote; a failed attempt starts again
///   after QUALIFY_COOLDOWN. Panels decides what a shadow verdict is scored against (task 3.2).
/// - The reveal-rate floor (ACTIVE_REVEAL_MIN, 90 % over the last 50 counted draws): more than ACTIVE_MISSES_MAX misses
///   in the last ACTIVE_REVEAL_WINDOW draws suspends; draws before the first are counted as revealed.
///
/// Bond tiers (D2, gap 2): the steps are every bounty limit of the k table at any level ($10, $25, $50, $125, $250,
/// $312.50, $625). A validator is eligible for a bounty if its bond is at least BOND_FACTOR × the bounty's tier, the
/// smallest step at or above it. One counter per tier (`eligibleCount`) holds the drawable validators eligible for it,
/// kept on every change, so Panels reads k's n without a pass over the registry; `eligibleAt` indexes them for its
/// rejection sampling. `epoch` changes with every change to the registry.
///
/// Bonds and slashes (D16, D18; in place of #85 5.8): bonds are in the fee coin, counted by what arrives. A slash is
/// only for a provable fault and never exceeds the bond:
/// - equivocation (two statements signed by one key for one subject), checked here by anyone: the whole bond;
/// - a false verdict (an upheld receipt challenge) or a reveal that doesn't match its seal, reported by Panels: the
///   whole bond; a failed availability challenge: DA_FAIL_SLASH_BPS (v2's share, #85 S16);
/// - a counted judge's silence or sealed vote not revealed, reported by Panels: a flat $5 each, whatever the bond.
/// Whoever proved a fault takes CHALLENGE_REWARD_BPS of it (`claim`); the rest, and every flat slash, goes to the
/// sponsors' pool (`payPool`). A disagreement is never a fault: no function slashes on one.
///
/// Unbonding: `leave` stops the draws at once; `withdraw` pays the operator account what's left, only UNBONDING_DELAY
/// after leaving and once every counted verdict the validator gave is final and every challenge naming it is closed.
/// It stays slashable until then. UNBONDING_DELAY is derived from the deployment's windows (#251, design L4): the
/// longest challenge window plus UNBONDING_MARGIN (504 h with the production windows).
///
/// Genesis (D10, #141): at most GENESIS_MAX validators at deployment, at level A or B, bonded, attested and signed like
/// any other, active from the start, and disclosed (`genesis` in its record, the `Registered` event).
///
/// The hooks (counters, scores, finality, faults) are callable only by the consumer bound once (`bind`, v2's pattern):
/// Panels, from its constructor. Keyless: no owner, no admin, no setter; every parameter is a constant or fixed at
/// construction (the windows, `teeOnly`). The constructor reverts off Sepolia and the local test chains (LaunchChain).
contract Validators is IValidators, ReentrancyGuardTransient {
    using SafeERC20 for IERC20;

    uint256 public constant BPS = 10_000;
    /// $100 (ADR 0004): covers k = 1's largest bounty at BOND_FACTOR.
    uint256 public constant BOND_FLOOR = 100e6;
    uint256 public constant BOND_FACTOR = 2;
    uint256 public constant TIERS = 7;
    uint256 public constant QUALIFY_VERDICTS = 20;
    uint256 public constant QUALIFY_REVEAL_BPS = 9_500;
    uint256 public constant QUALIFY_AGREE_BPS = 8_000;
    uint256 public constant QUALIFY_COOLDOWN = 7 days;
    /// ACTIVE_REVEAL_MIN, 90 % over the last 50 counted draws: more than 5 misses among them suspends.
    uint256 public constant ACTIVE_REVEAL_WINDOW = 50;
    uint256 public constant ACTIVE_MISSES_MAX = 5;
    /// Added to the longest challenge window for UNBONDING_DELAY (#132).
    uint256 public constant UNBONDING_MARGIN = WindowsLib.UNBONDING_MARGIN;
    uint256 public constant GENESIS_MAX = 1;
    uint256 public constant FALSE_VERDICT_SLASH_BPS = 10_000;
    uint256 public constant EQUIVOCATION_SLASH_BPS = 10_000;
    uint256 public constant DA_FAIL_SLASH_BPS = 2_000;
    uint256 public constant SILENCE_SLASH = 5e6;
    uint256 public constant SEALED_NO_REVEAL_SLASH = 5e6;
    uint256 public constant CHALLENGE_REWARD_BPS = 5_000;
    uint8 public constant LEVEL_A = 1;
    uint8 public constant LEVEL_B = 2;
    uint8 public constant LEVEL_C = 3;
    bytes32 public constant PROOF_TEE = keccak256("tee");
    bytes32 public constant PROOF_ZKTLS = keccak256("zktls");
    bytes32 public constant PROOF_SIMULATED = keccak256("simulated");
    /// The devnet chain ids on which `simulated` may be listed (D18): anvil's, and the AWS devnet's.
    uint256 public constant LOCAL_CHAIN_ID = 31_337;
    uint256 public constant DEVNET_CHAIN_ID = 7_193;

    bytes32 internal constant DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    bytes32 public constant REGISTRATION_TYPEHASH = keccak256(
        "Registration(address key,address operator,bytes32 proofType,bytes32 teeType,uint8 level,bytes32 attestation,bytes32 image,bytes32 host,bytes32 family,uint32 firmware,bytes32 radNode)"
    );
    bytes32 public constant STATEMENT_TYPEHASH = keccak256("Statement(bytes32 subject,bytes32 content)");
    bytes32 public constant REATTESTATION_TYPEHASH =
        keccak256("Reattestation(address key,bytes32 attestation,bytes32 image,uint32 firmware,uint32 nonce)");
    bytes32 public constant RECEIPT_TYPEHASH = keccak256(
        "Receipt(bytes32 proofType,bytes32 notary,bytes32 model,bytes32 weights,bytes32 image,bytes32 seed,bytes32 prompt,bytes32 answer,bytes32 tests,bytes32 proof,address panels,uint256 pid,uint256 slot,address key)"
    );
    bytes32 public constant ADR_TAG = keccak256("proof-of-fix v3 adr");
    uint64 internal constant WINDOW_MASK = uint64((1 << 50) - 1);

    /// Why a bond was slashed (the `Slashed` event).
    enum Reason {
        Equivocation,
        FalseVerdict,
        Mismatch,
        Availability,
        Silence,
        SealedNoReveal
    }

    struct Genesis {
        address coin; // FEE_COIN: 6 decimals, so amounts are micro-coins
        address pool; // the sponsors' pool (v2's Pool interface)
        bytes32[] proofTypes;
        bytes32[] teeTypes;
        uint32[] firmware; // each TEE type's minimum firmware (TCB) level, in teeTypes' order; empty: all 0
        bytes32[] images;
        Registration[] validators; // at most GENESIS_MAX
        bytes[] signatures; // each by its validator's key
        uint256[] bonds; // pulled from the deployer, each at least BOND_FLOOR
        Windows windows; // the deployment's windows, exactly Panels' (#251, L4): UNBONDING_DELAY derives from them
        bool teeOnly; // refuse zkTLS by ADR as well as at genesis (#251, L10)
    }

    /// Where a validator sits in the draw's structures: its bucket (1 + the highest tier its bond covers, 0 when not
    /// drawable), its index + 1 in that bucket, and its index + 1 among the candidates.
    struct Place {
        uint8 bucket;
        uint32 pos;
        uint32 candidatePos;
    }

    /// One entry of a list: listed or not, a TEE type's minimum firmware, the block it was last listed or loosened (a
    /// draw whose snapshot is older skips the validators it brings back), and when it was last listed and delisted.
    struct Listing {
        bool on;
        uint32 firmware;
        uint64 onBlock;
        uint64 since;
        uint64 until;
    }

    /// An ADR the constitution tier passed (Panels' `adrPassed`), until applied.
    struct Adr {
        bytes32 commitment;
        bool passed;
        bool removal;
        bool applied;
    }

    address public immutable coin;
    address public immutable pool;
    bytes32 internal immutable _domain;
    /// The longest challenge window of the deployment's windows plus UNBONDING_MARGIN (504 h with production values).
    uint256 public immutable UNBONDING_DELAY;
    /// keccak256(abi.encode(windows)): Panels' constructor checks its windows are these.
    bytes32 public immutable windowsHash;
    /// No zkTLS (level C) at genesis or by ADR (#251, L10).
    bool public immutable teeOnly;
    /// The consumer whose hooks drive the counters, scores, finality and faults: Panels, bound once.
    address public panels;
    uint256 public epoch;
    uint256 public activeCount;
    uint256 public totalBonds;
    uint256 public totalOwed;
    uint256 public poolOwed;
    address public genesisKey;
    uint256 public teeTypeCount;
    uint256 public imageCount;
    uint256 public notaryCount;
    mapping(address account => uint256) public owed;
    mapping(bytes32 proofType => Listing) internal _proofs;
    mapping(bytes32 teeType => Listing) internal _tees;
    mapping(bytes32 image => Listing) internal _images;
    mapping(bytes32 notary => Listing) internal _notaries;
    mapping(uint256 id => Adr) internal _adrs;
    /// keccak(key, subject) of every equivocation already proven: one slash per equivocation.
    mapping(bytes32 => bool) public equivocationProven;

    mapping(address key => Validator) internal _v;
    mapping(address key => Progress) internal _p;
    mapping(address key => Place) internal _place;
    address[] internal _keys;
    address[] internal _candidates;
    bytes32[] internal _groups;
    mapping(bytes32 group => bool) internal _groupSeen;
    mapping(bytes32 group => address[][TIERS]) internal _buckets;
    uint256[TIERS] internal _tierCount;
    /// The draw's frozen index space (Panels, #138): per tier, every key that ever became drawable for it, in order,
    /// never removed; and the block each key last rose to a higher bucket (became drawable, or covered a higher
    /// tier). A draw samples a roster up to its length at a block fixed before the seed is known and skips keys not
    /// drawable then, so a change after that block can remove a validator from a draw but never add one or reorder.
    address[][TIERS] internal _roster;
    mapping(address key => uint8) internal _rostered; // tiers 0 .. _rostered - 1 hold the key
    mapping(address key => uint64) internal _raisedAt;
    /// The last key registered with each Radicle node key (#251, L11): it holds the node while it isn't leaving or exited.
    mapping(bytes32 radNode => address key) internal _radHolder;

    event Bound(address indexed panels);
    event Registered(
        address indexed key,
        address indexed operator,
        bool genesis,
        uint8 level,
        uint256 bond,
        Registration r,
        bytes32 indexed radNode
    );
    event ToppedUp(address indexed key, address indexed from, uint256 amount);
    event Activated(address indexed key);
    event QualificationFailed(address indexed key, uint256 cooldownUntil);
    event Suspended(address indexed key);
    event Leaving(address indexed key, uint256 withdrawableFrom);
    event Withdrawn(address indexed key, address indexed operator, uint256 amount);
    event Slashed(address indexed key, Reason reason, uint256 amount, address indexed challenger, uint256 reward);
    event Claimed(address indexed account, uint256 amount);
    event PoolPaid(uint256 amount);
    event Reattested(address indexed key, bytes32 attestation, bytes32 image, uint32 firmware);
    event AdrPassed(uint256 indexed id, bool removal, bytes32 commitment);
    event AdrApplied(uint256 indexed id);
    event Listed(Op indexed op, bytes32 indexed id, uint32 firmware);
    /// L5: an Active validator's bond fell below BOND_FLOOR (it is BelowFloor now, not counted, not drawn)...
    event WentBelowFloor(address indexed key, uint256 bond);
    /// ... and a top-up brought it back to Active.
    event BackAboveFloor(address indexed key, uint256 bond);

    error BadParams();
    error AlreadyBound();
    error NotPanels();
    error KeyTaken();
    error BadRegistration();
    error ProofTypeNotAccepted();
    error TeeTypeNotAccepted();
    error ImageNotAllowed();
    error NoAttestation();
    error BadLevel();
    error BadSignature();
    error BondTooSmall();
    error NothingArrived();
    error Unknown();
    error NotAllowed();
    error WrongState();
    error TooEarly();
    error Locked();
    error NotConflicting();
    error AlreadyProven();
    error BountyTooLarge();
    error OutOfRange();
    error NothingOwed();
    error FirmwareTooOld();
    error NotPassed();
    error AlreadyApplied();
    error NotTheAdr();
    error NotARemoval();
    error NoVerifier();
    error LastOne();
    error NoNotary();
    error BadChange();
    error TeeOnly();
    error NodeTaken();

    constructor(Genesis memory g) {
        LaunchChain.check();
        WindowsLib.check(g.windows);
        UNBONDING_DELAY = WindowsLib.unbondingDelay(g.windows);
        windowsHash = keccak256(abi.encode(g.windows));
        teeOnly = g.teeOnly;
        if (g.coin.code.length == 0 || g.pool.code.length == 0) revert BadParams();
        try IERC20Metadata(g.coin).decimals() returns (uint8 d) {
            if (d != 6) revert BadParams();
        } catch {
            revert BadParams();
        }
        if (g.proofTypes.length == 0 || g.teeTypes.length == 0 || g.images.length == 0) revert BadParams();
        if (g.firmware.length != 0 && g.firmware.length != g.teeTypes.length) revert BadParams();
        for (uint256 i; i < g.proofTypes.length; ++i) {
            bytes32 t = g.proofTypes[i];
            // level C is off at launch (D10): zkTLS is in the code, never on the genesis list
            if (t != PROOF_TEE && (t != PROOF_SIMULATED || !_devnet())) revert BadParams();
            if (!_list(_proofs[t])) revert BadParams();
        }
        for (uint256 i; i < g.teeTypes.length; ++i) {
            bytes32 t = g.teeTypes[i];
            if (t == bytes32(0) || _isProofType(t) || !_list(_tees[t])) revert BadParams();
            if (g.firmware.length != 0) _tees[t].firmware = g.firmware[i];
        }
        teeTypeCount = g.teeTypes.length;
        for (uint256 i; i < g.images.length; ++i) {
            if (g.images[i] == bytes32(0) || !_list(_images[g.images[i]])) revert BadParams();
        }
        imageCount = g.images.length;
        uint256 n = g.validators.length;
        if (n > GENESIS_MAX || g.signatures.length != n || g.bonds.length != n) revert BadParams();
        coin = g.coin;
        pool = g.pool;
        bytes32 domain = keccak256(
            abi.encode(DOMAIN_TYPEHASH, keccak256("proof-of-fix Validators"), keccak256("3"), block.chainid, address(this))
        );
        _domain = domain;
        for (uint256 i; i < n; ++i) {
            Registration memory r = g.validators[i];
            uint8 level = _checkRegistration(r);
            if (level == LEVEL_C) revert BadLevel(); // unreachable while zkTLS can't be on the genesis list
            if (ECDSA.recover(_digest(domain, r), g.signatures[i]) != r.key) revert BadSignature();
            uint256 bond = _pull(msg.sender, g.bonds[i]);
            if (bond < BOND_FLOOR) revert BondTooSmall();
            _add(r, level, bond, true);
            genesisKey = r.key;
        }
    }

    // ---------- the consumer ----------

    /// Panels binds the registry, once (from its constructor): from then on only it drives the hooks.
    function bind() external {
        if (panels != address(0)) revert AlreadyBound();
        panels = msg.sender;
        emit Bound(msg.sender);
    }

    modifier onlyPanels() {
        if (msg.sender != panels) revert NotPanels();
        _;
    }

    // ---------- anyone ----------

    /// Registers `r.key` as a candidate with a bond of `amount` from the caller, signed by `r.key` (`sig` over
    /// `registrationDigest(r)`). No one else signs.
    function register(Registration calldata r, uint256 amount, bytes calldata sig) external nonReentrant {
        uint8 level = _checkRegistration(r);
        if (ECDSA.recover(_digest(_domain, r), sig) != r.key) revert BadSignature();
        uint256 bond = _pull(msg.sender, amount);
        if (bond < BOND_FLOOR) revert BondTooSmall();
        _add(r, level, bond, false);
    }

    /// Anyone adds to a candidate's, an active or a below-floor validator's bond (to get back to the floor after a
    /// slash, which makes a BelowFloor validator Active again without qualifying, or to a higher tier).
    function topUp(address key, uint256 amount) external nonReentrant {
        Validator storage v = _v[key];
        State s = v.state;
        if (s != State.Candidate && s != State.Active && s != State.BelowFloor) revert WrongState();
        uint256 received = _pull(msg.sender, amount);
        v.bond += uint128(received);
        totalBonds += received;
        _rebucket(key);
        ++epoch;
        emit ToppedUp(key, msg.sender, received);
    }

    /// The key or its operator account announces leaving: it isn't drawn from now on, and stays slashable.
    function leave(address key) external {
        Validator storage v = _v[key];
        if (msg.sender != key && msg.sender != v.operator) revert NotAllowed();
        State s = v.state;
        if (s == State.Candidate) {
            _removeCandidate(key);
        } else if (s == State.Active) {
            --activeCount;
        } else if (s != State.BelowFloor) {
            revert WrongState(); // a BelowFloor validator isn't counted: it just leaves
        }
        v.state = State.Leaving;
        v.leftAt = uint64(block.timestamp);
        _rebucket(key);
        ++epoch;
        emit Leaving(key, block.timestamp + UNBONDING_DELAY);
    }

    /// Anyone, once UNBONDING_DELAY has passed since leaving, every counted verdict the validator gave is final and
    /// every challenge naming it is closed: what remains of its bond goes to its operator account.
    function withdraw(address key) external nonReentrant {
        Validator storage v = _v[key];
        if (v.state != State.Leaving) revert WrongState();
        if (block.timestamp < uint256(v.leftAt) + UNBONDING_DELAY) revert TooEarly();
        if (v.openVerdicts != 0 || v.openChallenges != 0) revert Locked();
        uint256 amount = v.bond;
        v.bond = 0;
        v.state = State.Exited;
        totalBonds -= amount;
        ++epoch;
        if (amount != 0) IERC20(coin).safeTransfer(v.operator, amount);
        emit Withdrawn(key, v.operator, amount);
    }

    /// Anyone proves equivocation: two different contents signed by `key` for one subject. The whole bond, once per
    /// (key, subject); the prover takes CHALLENGE_REWARD_BPS of it.
    function proveEquivocation(
        address key,
        bytes32 subject,
        bytes32 a,
        bytes calldata sigA,
        bytes32 b,
        bytes calldata sigB
    ) external {
        if (a == b) revert NotConflicting();
        if (_v[key].state == State.None) revert Unknown();
        if (
            ECDSA.recover(statementDigest(subject, a), sigA) != key
                || ECDSA.recover(statementDigest(subject, b), sigB) != key
        ) revert BadSignature();
        bytes32 id = keccak256(abi.encode(key, subject));
        if (equivocationProven[id]) revert AlreadyProven();
        equivocationProven[id] = true;
        _slash(key, uint256(_v[key].bond) * EQUIVOCATION_SLASH_BPS / BPS, msg.sender, Reason.Equivocation);
    }

    /// A challenger's share of the slashes it proved.
    function claim() external nonReentrant {
        uint256 amount = owed[msg.sender];
        if (amount == 0) revert NothingOwed();
        owed[msg.sender] = 0;
        totalOwed -= amount;
        IERC20(coin).safeTransfer(msg.sender, amount);
        emit Claimed(msg.sender, amount);
    }

    /// Anyone moves the pool's share of the slashes into the sponsors' pool.
    function payPool() external nonReentrant {
        uint256 amount = poolOwed;
        if (amount == 0) revert NothingOwed();
        poolOwed = 0;
        IERC20(coin).forceApprove(pool, amount);
        IPoolFund(pool).fund(coin, amount);
        emit PoolPaid(amount);
    }

    /// The key attests again (D11, #141 gap 6): a new attestation's hash, a checker image on the list and, for a TEE,
    /// a firmware level at least its type's minimum, signed by the key over `reattestationDigest`. Its state, bond,
    /// family, level and qualification are unchanged: a validator left out of standing by a raised minimum or a
    /// removed image returns without qualifying again. It leaves the draws whose snapshot is older (as a top-up does).
    function reattest(address key, bytes32 attestation, bytes32 image, uint32 firmware, bytes calldata sig) external {
        Validator storage v = _v[key];
        State s = v.state;
        if (s != State.Candidate && s != State.Active && s != State.BelowFloor) revert WrongState();
        if (!_images[image].on) revert ImageNotAllowed();
        bytes32 tee = v.teeType;
        if (tee == bytes32(0)) {
            if (firmware != 0) revert BadRegistration();
        } else {
            if (attestation == bytes32(0)) revert NoAttestation();
            if (!_tees[tee].on) revert TeeTypeNotAccepted();
            if (firmware < _tees[tee].firmware) revert FirmwareTooOld();
        }
        if (ECDSA.recover(reattestationDigest(key, attestation, image, firmware), sig) != key) revert BadSignature();
        v.attestation = attestation;
        v.image = image;
        v.firmware = firmware;
        ++v.reattestations;
        _raisedAt[key] = uint64(block.number);
        _rebucket(key);
        ++epoch;
        emit Reattested(key, attestation, image, firmware);
    }

    /// Anyone moves validators the lists left out of standing (a raised minimum, a removed image or `simulated`) out of
    /// the tier counters, or back in once they're in standing again. The draw already skips them; this keeps k exact.
    /// `epoch` moves only if a validator did (#251 task 3.10): a call that changes nothing can't re-open the draws,
    /// audits and challenges that wait for the registry to change.
    function recheck(address[] calldata keys) external {
        bool changed;
        for (uint256 i; i < keys.length; ++i) {
            address key = keys[i];
            if (_v[key].state == State.None) continue;
            uint8 was = _place[key].bucket;
            _rebucket(key);
            if (_place[key].bucket != was) changed = true;
        }
        if (changed) ++epoch;
    }

    /// Anyone applies a passed ADR's operations (`changes`, with the ADR's text hash `text`), once: they must be what
    /// its commitment bound (`adrCommitment`), and a removal ADR's must all be removals (`isRemoval`). All or nothing,
    /// in order. Refused if it would leave no TEE type or image digest, or zkTLS listed without a notary; it can be
    /// applied later, once another ADR has added a replacement.
    function applyAdr(uint256 id, bytes32 text, Change[] calldata changes) external {
        Adr storage a = _adrs[id];
        if (!a.passed) revert NotPassed();
        if (a.applied) revert AlreadyApplied();
        if (adrCommitment(text, changes) != a.commitment) revert NotTheAdr();
        if (a.removal && !isRemoval(changes)) revert NotARemoval();
        a.applied = true;
        for (uint256 i; i < changes.length; ++i) {
            _change(changes[i]);
        }
        if (teeTypeCount == 0 || imageCount == 0) revert LastOne();
        if (_proofs[PROOF_ZKTLS].on && notaryCount == 0) revert NoNotary();
        ++epoch;
        emit AdrApplied(id);
    }

    // ---------- hooks (Panels) ----------

    function recordShadow(address key, bool revealed) external onlyPanels {
        if (!canShadow(_known(key))) return;
        Progress storage p = _p[key];
        if (p.shadowDraws == type(uint16).max) return; // saturates; the attempt's rate stays readable
        ++p.shadowDraws;
        if (revealed) ++p.shadowReveals;
    }

    function scoreShadow(address key, bool agreed) external onlyPanels {
        if (!canShadow(_known(key))) return;
        Progress storage p = _p[key];
        uint256 scored = ++p.scored;
        if (agreed) ++p.agreed;
        if (scored < QUALIFY_VERDICTS) return;
        if (
            uint256(p.shadowReveals) * BPS >= uint256(p.shadowDraws) * QUALIFY_REVEAL_BPS
                && uint256(p.agreed) * BPS >= scored * QUALIFY_AGREE_BPS
        ) {
            _removeCandidate(key);
            _v[key].state = State.Active;
            ++activeCount;
            delete _p[key];
            emit Activated(key);
            _rebucket(key); // below the floor already (a suspended validator slashed meanwhile): BelowFloor at once
        } else {
            uint64 until = uint64(block.timestamp + QUALIFY_COOLDOWN);
            delete _p[key];
            _p[key].cooldownUntil = until;
            emit QualificationFailed(key, until);
        }
        ++epoch;
    }

    function recordCounted(address key, bool hasSeal, bool revealed) external onlyPanels {
        Validator storage v = _v[_known(key)];
        if (!revealed) {
            if (hasSeal) _slash(key, SEALED_NO_REVEAL_SLASH, address(0), Reason.SealedNoReveal);
            else _slash(key, SILENCE_SLASH, address(0), Reason.Silence);
        }
        State s = v.state; // a miss's slash may just have taken it below the floor: its misses still count
        if (s != State.Active && s != State.BelowFloor) return;
        Progress storage p = _p[key];
        uint64 bits = p.missBits;
        uint8 misses = p.misses;
        if ((bits >> (ACTIVE_REVEAL_WINDOW - 1)) & 1 == 1) --misses; // the oldest draw leaves the window
        bits = (bits << 1) & WINDOW_MASK;
        if (!revealed) {
            bits |= 1;
            ++misses;
        }
        p.missBits = bits;
        p.misses = misses;
        if (misses > ACTIVE_MISSES_MAX) {
            v.state = State.Candidate;
            if (s == State.Active) --activeCount;
            if (v.suspensions < type(uint8).max) ++v.suspensions;
            delete _p[key];
            _rebucket(key);
            _addCandidate(key);
            ++epoch;
            emit Suspended(key);
        }
    }

    function verdictOpened(address key) external onlyPanels {
        ++_v[_known(key)].openVerdicts;
    }

    function verdictFinal(address key) external onlyPanels {
        Validator storage v = _v[_known(key)];
        if (v.openVerdicts != 0) --v.openVerdicts;
    }

    function challengeOpened(address key) external onlyPanels {
        ++_v[_known(key)].openChallenges;
    }

    function challengeClosed(address key) external onlyPanels {
        Validator storage v = _v[_known(key)];
        if (v.openChallenges != 0) --v.openChallenges;
    }

    function slashFault(address key, Fault fault, address challenger) external onlyPanels {
        uint256 bond = _v[_known(key)].bond;
        if (fault == Fault.FalseVerdict) {
            _slash(key, bond * FALSE_VERDICT_SLASH_BPS / BPS, challenger, Reason.FalseVerdict);
        } else if (fault == Fault.Mismatch) {
            _slash(key, bond * EQUIVOCATION_SLASH_BPS / BPS, challenger, Reason.Mismatch);
        } else {
            _slash(key, bond * DA_FAIL_SLASH_BPS / BPS, challenger, Reason.Availability);
        }
    }

    function adrPassed(uint256 id, bool removal, bytes32 commitment) external onlyPanels {
        Adr storage a = _adrs[id];
        if (a.passed) return;
        a.commitment = commitment;
        a.passed = true;
        a.removal = removal;
        emit AdrPassed(id, removal, commitment);
    }

    // ---------- views ----------

    function isActive(address key) external view returns (bool) {
        return _v[key].state == State.Active;
    }

    function isDrawable(address key) external view returns (bool ok) {
        if (_place[key].bucket == 0) return false;
        (ok,) = _standing(_v[key]);
    }

    function canShadow(address key) public view returns (bool ok) {
        if (_v[key].state != State.Candidate || block.timestamp < _p[key].cooldownUntil) return false;
        (ok,) = _standing(_v[key]);
    }

    /// Whether the validator is in standing: its proof type, TEE type and image listed, its firmware at its minimum.
    function inStanding(address key) external view returns (bool ok) {
        (ok,) = _standing(_v[key]);
    }

    function acceptedProofType(bytes32 t) external view returns (bool) {
        return _proofs[t].on;
    }

    function acceptedTeeType(bytes32 t) external view returns (bool) {
        return _tees[t].on;
    }

    function allowedImage(bytes32 image) external view returns (bool) {
        return _images[image].on;
    }

    function acceptedNotary(bytes32 notary) external view returns (bool) {
        return _notaries[notary].on;
    }

    /// A TEE type's minimum firmware (TCB) level (D10).
    function minFirmware(bytes32 teeType) external view returns (uint32) {
        return _tees[teeType].firmware;
    }

    /// Whether a zkTLS proof by `notary` revealed at `revealedAt` counts: the notary was listed then, so a verdict
    /// revealed before its removal took effect still counts (D11, gap 14). Only its latest listing is kept.
    function notaryCounts(bytes32 notary, uint256 revealedAt) external view returns (bool) {
        Listing storage l = _notaries[notary];
        return l.since != 0 && revealedAt >= l.since && (l.on || revealedAt < l.until);
    }

    function adr(uint256 id) external view returns (Adr memory) {
        return _adrs[id];
    }

    /// The commitment an ADR is opened with at the constitution tier: its text's hash and its operations.
    function adrCommitment(bytes32 text, Change[] calldata changes) public pure returns (bytes32) {
        return keccak256(abi.encode(ADR_TAG, text, changes));
    }

    /// Whether every operation only removes or raises a minimum (D7, D11): such an ADR is drawn from
    /// REMOVAL_MIN_ELIGIBLE and takes effect after REMOVAL_WINDOW. An empty list isn't a removal.
    function isRemoval(Change[] calldata changes) public pure returns (bool) {
        if (changes.length == 0) return false;
        for (uint256 i; i < changes.length; ++i) {
            Op op = changes[i].op;
            if (
                op != Op.RemoveTeeType && op != Op.RaiseFirmware && op != Op.RemoveImage && op != Op.RemoveNotary
                    && op != Op.RemoveProofType
            ) return false;
        }
        return true;
    }

    /// The hash a counted verdict posts as its receipt (`Panels.receipt`).
    function receiptHash(Receipt calldata r) external pure returns (bytes32) {
        return keccak256(abi.encode(RECEIPT_TYPEHASH, r));
    }

    function reattestationDigest(address key, bytes32 attestation, bytes32 image, uint32 firmware)
        public
        view
        returns (bytes32)
    {
        return MessageHashUtils.toTypedDataHash(
            _domain,
            keccak256(abi.encode(REATTESTATION_TYPEHASH, key, attestation, image, firmware, _v[key].reattestations))
        );
    }

    function validator(address key) external view returns (Validator memory) {
        return _v[key];
    }

    function progress(address key) external view returns (Progress memory) {
        return _p[key];
    }

    /// The model family `key` registered with, whatever its state (candidates included); 0 for a key never registered
    /// (FeesV3's `IFeesV3Validators.familyOf`).
    function familyOf(address key) external view returns (bytes32) {
        return _v[key].family;
    }

    /// The Radicle node key `key` registered with (#251, L11; specs/radicle-hosting): the 32-byte Ed25519 public key its
    /// node's did:key names, whatever its state; 0 for none (its seat isn't counted as a delegate) or a key never
    /// registered. `verify-delegates` reads the seats' nodes here.
    function radNodeOf(address key) external view returns (bytes32) {
        return _v[key].radNode;
    }

    function validatorCount() external view returns (uint256) {
        return _keys.length;
    }

    function validatorAt(uint256 i) external view returns (address) {
        return _keys[i];
    }

    function candidateCount() external view returns (uint256) {
        return _candidates.length;
    }

    function candidateAt(uint256 i) external view returns (address) {
        return _candidates[i];
    }

    /// The tier steps: every bounty limit of the k table at any level (D2).
    function tierStep(uint256 t) public pure returns (uint256) {
        if (t == 0) return 10e6;
        if (t == 1) return 25e6;
        if (t == 2) return 50e6;
        if (t == 3) return 125e6;
        if (t == 4) return 250e6;
        if (t == 5) return 312_500_000;
        if (t == 6) return 625e6;
        revert OutOfRange();
    }

    function tierOf(uint256 bounty) public pure returns (uint256) {
        for (uint256 t; t < TIERS; ++t) {
            if (bounty <= tierStep(t)) return t;
        }
        revert BountyTooLarge();
    }

    function eligibleCount(uint256 bounty) external view returns (uint256) {
        if (bounty > tierStep(TIERS - 1)) return 0;
        return _tierCount[tierOf(bounty)];
    }

    function eligibleAt(uint256 bounty, uint256 index) external view returns (address) {
        uint256 t = tierOf(bounty);
        if (index >= _tierCount[t]) revert OutOfRange();
        uint256 gs = _groups.length;
        for (uint256 i; i < gs; ++i) {
            bytes32 g = _groups[i];
            if (!_counted(g)) continue;
            address[][TIERS] storage bs = _buckets[g];
            for (uint256 b = t; b < TIERS; ++b) {
                uint256 len = bs[b].length;
                if (index < len) return bs[b][index];
                index -= len;
            }
        }
        revert OutOfRange(); // unreachable: the counters match the buckets
    }

    /// The size of one group's bucket (validators whose bond covers tier `b` and not `b + 1`), for recounts.
    /// Tier t's roster length (Panels snapshots it before a draw's seed is known).
    function rosterLength(uint256 t) external view returns (uint256) {
        return _roster[t].length;
    }

    /// Tier t's i-th roster entry: its key, the block it last rose to a higher bucket (or a list brought it back into
    /// standing), and its bucket now, 0 out of standing (drawable for tier t now when the bucket is above t).
    function rosterEntry(uint256 t, uint256 i) external view returns (address key, uint64 raisedAt, uint8 bucket) {
        key = _roster[t][i];
        raisedAt = _raisedAt[key];
        bucket = _place[key].bucket;
        if (bucket > t) {
            (bool ok, uint64 on) = _standing(_v[key]);
            if (!ok) bucket = 0;
            else if (on > raisedAt) raisedAt = on;
        }
    }

    function bucketSize(bytes32 group, uint256 b) external view returns (uint256) {
        return _buckets[group][b].length;
    }

    function groups() external view returns (bytes32[] memory) {
        return _groups;
    }

    function domainSeparator() external view returns (bytes32) {
        return _domain;
    }

    function registrationDigest(Registration calldata r) external view returns (bytes32) {
        return _digest(_domain, r);
    }

    function statementDigest(bytes32 subject, bytes32 content) public view returns (bytes32) {
        return MessageHashUtils.toTypedDataHash(_domain, keccak256(abi.encode(STATEMENT_TYPEHASH, subject, content)));
    }

    // ---------- internals ----------

    function _digest(bytes32 domain, Registration memory r) internal pure returns (bytes32) {
        return MessageHashUtils.toTypedDataHash(
            domain,
            keccak256(
                abi.encode(
                    REGISTRATION_TYPEHASH,
                    r.key,
                    r.operator,
                    r.proofType,
                    r.teeType,
                    r.level,
                    r.attestation,
                    r.image,
                    r.host,
                    r.family,
                    r.firmware,
                    r.radNode
                )
            )
        );
    }

    /// The registration's checks, and the level it records: zkTLS C, simulated A, a TEE its declared A or B.
    function _checkRegistration(Registration memory r) internal view returns (uint8) {
        if (r.key == address(0) || _v[r.key].state != State.None) revert KeyTaken();
        if (r.operator == address(0) || r.host == bytes32(0) || r.family == bytes32(0)) revert BadRegistration();
        if (r.radNode != bytes32(0)) {
            // one node per seat (#251, L11): refused while another registration that isn't leaving or exited holds it
            State h = _v[_radHolder[r.radNode]].state;
            if (h == State.Candidate || h == State.Active || h == State.BelowFloor) revert NodeTaken();
        }
        if (!_proofs[r.proofType].on) revert ProofTypeNotAccepted();
        if (!_images[r.image].on) revert ImageNotAllowed();
        if (r.proofType == PROOF_ZKTLS) {
            if (r.teeType != bytes32(0) || r.firmware != 0) revert BadRegistration();
            return LEVEL_C;
        }
        if (!_tees[r.teeType].on) revert TeeTypeNotAccepted();
        if (r.firmware < _tees[r.teeType].firmware) revert FirmwareTooOld();
        if (r.attestation == bytes32(0)) revert NoAttestation();
        if (r.proofType == PROOF_SIMULATED) return LEVEL_A; // D18: on a devnet, simulated counts as level A
        if (r.level != LEVEL_A && r.level != LEVEL_B) revert BadLevel();
        return r.level;
    }

    function _add(Registration memory r, uint8 level, uint256 bond, bool genesis) internal {
        Validator storage v = _v[r.key];
        v.key = r.key;
        v.level = level;
        v.state = genesis ? State.Active : State.Candidate;
        v.genesis = genesis;
        v.operator = r.operator;
        v.proofType = r.proofType;
        v.teeType = r.teeType;
        v.attestation = r.attestation;
        v.image = r.image;
        v.host = r.host;
        v.family = r.family;
        v.firmware = r.firmware;
        v.radNode = r.radNode;
        if (r.radNode != bytes32(0)) _radHolder[r.radNode] = r.key;
        v.bond = uint128(bond);
        v.registeredAt = uint64(block.timestamp);
        _keys.push(r.key);
        totalBonds += bond;
        if (genesis) {
            ++activeCount;
            _rebucket(r.key);
        } else {
            _addCandidate(r.key);
        }
        ++epoch;
        emit Registered(r.key, r.operator, genesis, level, bond, r, r.radNode);
    }

    function _known(address key) internal view returns (address) {
        if (_v[key].state == State.None) revert Unknown();
        return key;
    }

    /// Pulls `amount` from `from`, counting what arrived (a coin that charges on transfer is credited less).
    function _pull(address from, uint256 amount) internal returns (uint256 received) {
        IERC20 c = IERC20(coin);
        uint256 before = c.balanceOf(address(this));
        c.safeTransferFrom(from, address(this), amount);
        received = c.balanceOf(address(this)) - before;
        if (received == 0) revert NothingArrived();
    }

    /// Takes `amount` (at most the bond) from the validator: `challenger` (if any) gets CHALLENGE_REWARD_BPS of it,
    /// the pool the rest.
    function _slash(address key, uint256 amount, address challenger, Reason reason) internal {
        Validator storage v = _v[key];
        if (amount > v.bond) amount = v.bond;
        v.bond -= uint128(amount);
        v.slashed += uint128(amount);
        totalBonds -= amount;
        uint256 reward = challenger == address(0) ? 0 : amount * CHALLENGE_REWARD_BPS / BPS;
        if (reward != 0) {
            owed[challenger] += reward;
            totalOwed += reward;
        }
        poolOwed += amount - reward;
        _rebucket(key);
        ++epoch;
        emit Slashed(key, reason, amount, challenger, reward);
    }

    /// 1 + the highest tier a bond covers at BOND_FACTOR (0: none).
    function _bucketFor(uint256 bond) internal pure returns (uint8) {
        for (uint256 t = TIERS; t > 0; --t) {
            if (bond >= BOND_FACTOR * tierStep(t - 1)) return uint8(t);
        }
        return 0;
    }

    /// Moves the validator to the bucket its state, bond and standing call for, and keeps the tier counters: a drawable
    /// validator (active, bonded at least BOND_FLOOR, in standing) in bucket b counts in tiers 0 to b - 1, while its
    /// group (its TEE type, or zkTLS) is listed. One of a listed group may stay counted out of standing until
    /// rechecked (a raised minimum, a removed image or `simulated`); the draw skips it meanwhile.
    function _rebucket(address key) internal {
        Validator storage v = _v[key];
        _floor(key, v);
        Place storage pl = _place[key];
        (bool standing,) = _standing(v);
        uint8 want = v.state == State.Active && v.bond >= BOND_FLOOR && standing ? _bucketFor(v.bond) : 0;
        uint8 have = pl.bucket;
        if (want == have) return;
        bytes32 g = v.teeType != bytes32(0) ? v.teeType : v.proofType;
        if (have != 0) {
            address[] storage from = _buckets[g][have - 1];
            uint256 i = pl.pos - 1;
            address last = from[from.length - 1];
            from[i] = last;
            _place[last].pos = uint32(i + 1);
            from.pop();
            // a delisted group already left the counters (_group)
            if (_counted(g)) {
                for (uint256 t; t < have; ++t) {
                    --_tierCount[t];
                }
            }
        }
        if (want != 0) {
            if (!_groupSeen[g]) {
                _groupSeen[g] = true;
                _groups.push(g);
            }
            address[] storage to = _buckets[g][want - 1];
            to.push(key);
            pl.pos = uint32(to.length);
            for (uint256 t; t < want; ++t) {
                ++_tierCount[t];
            }
        } else {
            pl.pos = 0;
        }
        if (want > have) {
            _raisedAt[key] = uint64(block.number);
            for (uint256 t = _rostered[key]; t < want; ++t) {
                _roster[t].push(key);
            }
            if (want > _rostered[key]) _rostered[key] = want;
        }
        pl.bucket = want;
    }

    /// L5: an Active validator whose bond is below BOND_FLOOR becomes BelowFloor (out of `activeCount`), and a
    /// BelowFloor one bonded at the floor again becomes Active, each with its event, in the transaction that moved the
    /// bond. Every bond change and every state change reaches here (`_rebucket`).
    function _floor(address key, Validator storage v) internal {
        State s = v.state;
        if (s == State.Active && v.bond < BOND_FLOOR) {
            v.state = State.BelowFloor;
            --activeCount;
            emit WentBelowFloor(key, v.bond);
        } else if (s == State.BelowFloor && v.bond >= BOND_FLOOR) {
            v.state = State.Active;
            ++activeCount;
            emit BackAboveFloor(key, v.bond);
        }
    }

    /// In standing: its proof type, image and TEE type listed and its firmware at the type's minimum; and the latest
    /// block one of those was listed or loosened (a draw whose snapshot is older doesn't count the validator).
    function _standing(Validator storage v) internal view returns (bool, uint64) {
        Listing storage p = _proofs[v.proofType];
        Listing storage im = _images[v.image];
        if (!p.on || !im.on) return (false, 0);
        uint64 on = p.onBlock > im.onBlock ? p.onBlock : im.onBlock;
        bytes32 tee = v.teeType;
        if (tee != bytes32(0)) {
            Listing storage t = _tees[tee];
            if (!t.on || v.firmware < t.firmware) return (false, 0);
            if (t.onBlock > on) on = t.onBlock;
        }
        return (true, on);
    }

    /// Whether a bucket group (a TEE type, or zkTLS) counts in the tier counters: while it's listed.
    function _counted(bytes32 g) internal view returns (bool) {
        return g == PROOF_ZKTLS ? _proofs[g].on : _tees[g].on;
    }

    /// A group listed again adds its buckets back to the counters; one delisted takes them out (O(tiers)).
    function _group(bytes32 g, bool on) internal {
        if (!_groupSeen[g]) return;
        address[][TIERS] storage bs = _buckets[g];
        for (uint256 b; b < TIERS; ++b) {
            uint256 n = bs[b].length;
            if (n == 0) continue;
            for (uint256 t; t <= b; ++t) {
                if (on) _tierCount[t] += n;
                else _tierCount[t] -= n;
            }
        }
    }

    /// Lists an entry; false if it was already listed.
    function _list(Listing storage l) internal returns (bool) {
        if (l.on) return false;
        l.on = true;
        l.onBlock = uint64(block.number);
        l.since = uint64(block.timestamp);
        return true;
    }

    /// Delists an entry; false if it wasn't listed.
    function _delist(Listing storage l) internal returns (bool) {
        if (!l.on) return false;
        l.on = false;
        l.until = uint64(block.timestamp);
        return true;
    }

    function _devnet() internal view returns (bool) {
        return block.chainid == LOCAL_CHAIN_ID || block.chainid == DEVNET_CHAIN_ID;
    }

    function _isProofType(bytes32 t) internal pure returns (bool) {
        return t == PROOF_TEE || t == PROOF_ZKTLS || t == PROOF_SIMULATED;
    }

    /// One ADR operation (D10, D11). Adding what's listed, or removing what isn't, changes nothing.
    function _change(Change calldata c) internal {
        Op op = c.op;
        bytes32 id = c.id;
        if (id == bytes32(0)) revert BadChange();
        if (op == Op.AddTeeType) {
            if (_isProofType(id)) revert BadChange();
            if (_list(_tees[id])) {
                _tees[id].firmware = c.firmware;
                ++teeTypeCount;
                _group(id, true);
            }
        } else if (op == Op.RemoveTeeType) {
            if (_delist(_tees[id])) {
                --teeTypeCount;
                _group(id, false);
            }
        } else if (op == Op.RaiseFirmware || op == Op.LowerFirmware) {
            Listing storage t = _tees[id]; // a type delisted meanwhile: nothing to change
            if (t.on && (op == Op.RaiseFirmware ? c.firmware > t.firmware : c.firmware < t.firmware)) {
                t.firmware = c.firmware;
                if (op == Op.LowerFirmware) t.onBlock = uint64(block.number);
            }
        } else if (op == Op.AddImage) {
            if (_list(_images[id])) ++imageCount;
        } else if (op == Op.RemoveImage) {
            if (_delist(_images[id])) --imageCount;
        } else if (op == Op.AddNotary) {
            if (_list(_notaries[id])) ++notaryCount;
        } else if (op == Op.RemoveNotary) {
            if (_delist(_notaries[id])) --notaryCount;
        } else if (op == Op.AddProofType) {
            // only a verifier path in this code; `simulated` only on a devnet (D18); no zkTLS when TEE-only (L10)
            if (id != PROOF_TEE && id != PROOF_ZKTLS && (id != PROOF_SIMULATED || !_devnet())) revert NoVerifier();
            if (id == PROOF_ZKTLS && teeOnly) revert TeeOnly();
            if (_list(_proofs[id]) && id == PROOF_ZKTLS) _group(id, true);
        } else {
            if (id == PROOF_TEE) revert LastOne(); // every TEE type at once
            if (_delist(_proofs[id]) && id == PROOF_ZKTLS) _group(id, false);
        }
        emit Listed(op, id, c.firmware);
    }

    function _addCandidate(address key) internal {
        _candidates.push(key);
        _place[key].candidatePos = uint32(_candidates.length);
    }

    function _removeCandidate(address key) internal {
        uint256 i = _place[key].candidatePos - 1;
        address last = _candidates[_candidates.length - 1];
        _candidates[i] = last;
        _place[last].candidatePos = uint32(i + 1);
        _candidates.pop();
        _place[key].candidatePos = 0;
    }
}
