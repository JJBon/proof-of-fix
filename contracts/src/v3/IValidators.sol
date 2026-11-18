// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

/// v3's validator registry as Panels, FeesV3 and RaceV3 see it (proof-of-fix#138, task 3.1 of #132; design D1, D2, D5,
/// D16, D18; specs/validator-admission). `Validators` implements it.
///
/// A validator is its key's address. Amounts are in micro-coins (1e-6) of the version's fee coin (`FEE_COIN`).
///
/// States:
/// - Candidate: registered and bonded, or suspended by the reveal-rate floor; drawn only as a shadow judge;
/// - Active: qualified; drawn for counted panels while its bond is at least BOND_FLOOR (`isDrawable`);
/// - Leaving: announced its exit; never drawn again, still slashable, withdrawable after the unbonding conditions;
/// - Exited: its bond withdrawn.
///
/// Hooks (the `onlyPanels` functions): callable only by the address bound once with `bind()` (v2's pattern: the
/// consumer calls it from its own constructor). They never revert for a state the caller can't foresee: a hook that
/// doesn't apply to a validator's state is a no-op, so a draw's deadline or a verdict's finality can't be blocked by a
/// validator leaving or being suspended in between.
interface IValidators {
    enum State {
        None,
        Candidate,
        Active,
        Leaving,
        Exited
    }

    /// The faults Panels (or RaceV3, through Panels) proves and reports (D16). Equivocation is proven to the registry
    /// directly by anyone (`proveEquivocation`); silence and a sealed vote not revealed come with `recordCounted`.
    enum Fault {
        FalseVerdict, // an upheld receipt challenge: the whole bond (FALSE_VERDICT_SLASH_BPS)
        Mismatch, // a reveal that doesn't match its seal: the whole bond (EQUIVOCATION_SLASH_BPS)
        Availability // a failed availability challenge: v2's share (DA_FAIL_SLASH_BPS)
    }

    /// What a registration declares, signed by `key` (specs/validator-admission, "A registration records what the
    /// caps need"). `level` is read only for the TEE proof type (A or B); zkTLS is level C and `simulated` level A.
    struct Registration {
        address key;
        address operator; // the declared operator account: one per panel (D6), and where the bond returns
        bytes32 proofType; // PROOF_TEE, PROOF_ZKTLS or PROOF_SIMULATED
        bytes32 teeType; // an accepted TEE type (D6); 0 for zkTLS
        uint8 level; // LEVEL_A or LEVEL_B, for PROOF_TEE
        bytes32 attestation; // the attestation's hash (checked off-chain by the drawn panel); 0 allowed for zkTLS
        bytes32 image; // the checker image digest the attestation shows
        bytes32 host; // the infrastructure host the attestation identifies or the operator declares
        bytes32 family; // the declared model family, fixed for this key
        uint32 firmware; // the TEE's attested firmware (TCB) level, at least its type's minimum (D10); 0 for zkTLS
    }

    /// A registered validator, readable by anyone.
    struct Validator {
        address key;
        uint8 level;
        State state;
        bool genesis;
        uint8 suspensions; // times the reveal-rate floor sent it back to Candidate
        address operator;
        uint64 leftAt; // when it announced leaving (0: not leaving)
        bytes32 proofType;
        bytes32 teeType;
        bytes32 attestation;
        bytes32 image;
        bytes32 host;
        bytes32 family;
        uint128 bond;
        uint128 slashed; // everything ever slashed from it
        uint32 openVerdicts; // counted verdicts it gave that aren't final yet
        uint32 openChallenges; // challenges naming it that aren't closed yet
        uint64 registeredAt;
        uint32 firmware; // its latest attested firmware (TCB) level (0 for zkTLS)
        uint32 reattestations; // attestations after the registration's: the next re-attestation's nonce
    }

    /// An ADR's operations on the constitution's lists (D10, D11; task 3.4). The removal kind (an ADR that only removes
    /// or raises a minimum: REMOVAL_MIN_ELIGIBLE and REMOVAL_WINDOW) is RemoveTeeType, RaiseFirmware, RemoveImage,
    /// RemoveNotary and RemoveProofType; every other operation adds or loosens (CONSTITUTION_MIN_ELIGIBLE, ADR_WINDOW).
    enum Op {
        AddTeeType, // `id` a TEE type (one attestation scheme, D6), with its minimum `firmware`
        RemoveTeeType,
        RaiseFirmware, // `id` an accepted TEE type: its minimum to at least `firmware`
        LowerFirmware, // `id` an accepted TEE type: its minimum to at most `firmware`
        AddImage, // `id` a checker image digest
        RemoveImage,
        AddNotary, // `id` a zkTLS notary
        RemoveNotary,
        AddProofType, // `id` a proof type whose verifier path is in this code (zkTLS; `simulated` on a devnet only)
        RemoveProofType
    }

    struct Change {
        Op op;
        bytes32 id;
        uint32 firmware; // AddTeeType, RaiseFirmware, LowerFirmware; 0 otherwise
    }

    /// What a receipt names (D11, owner 2026-11-03): its proof, the model and its weights (0 where not public), the
    /// inference image, the seed, the prompt and the answer, the tests' results, and the proof's bytes. A counted
    /// verdict posts `receiptHash` of it on-chain; a proof type switched on later reuses this format.
    struct Receipt {
        bytes32 proofType;
        bytes32 notary; // zkTLS: the notary that signed the proof; 0 for a TEE
        bytes32 model;
        bytes32 weights;
        bytes32 image;
        bytes32 seed;
        bytes32 prompt;
        bytes32 answer;
        bytes32 tests; // each test's pass or fail, hashed
        bytes32 proof; // the proof bytes (a TEE quote or a zkTLS proof), hashed
    }

    /// A candidate's qualification attempt and an active validator's reveal window.
    struct Progress {
        uint16 shadowDraws; // shadow draws whose deadline passed in this attempt
        uint16 shadowReveals; // of which revealed
        uint16 scored; // scored shadow verdicts in this attempt
        uint16 agreed; // of which agreeing with the outcome they were scored against
        uint64 cooldownUntil; // a failed attempt: no shadow draw before this
        uint64 missBits; // the last ACTIVE_REVEAL_WINDOW counted draws, newest in bit 0, 1 = missed
        uint8 misses; // set bits in missBits
    }

    // ---------- reads ----------

    /// Active: qualified, not suspended, not leaving (FeesV3 counts its price tables).
    function isActive(address key) external view returns (bool);
    /// How many validators are active now.
    function activeCount() external view returns (uint256);
    /// Active, bonded at least BOND_FLOOR and in standing (its proof type, TEE type and image still listed, its firmware
    /// at its type's minimum): may be drawn for a counted panel (Panels still applies the parties, the caps, the family
    /// scores and K1_PENDING_MAX).
    function isDrawable(address key) external view returns (bool);
    /// A candidate in standing, not cooling off after a failed attempt: may be drawn as a shadow judge.
    function canShadow(address key) external view returns (bool);
    function validator(address key) external view returns (Validator memory);
    function progress(address key) external view returns (Progress memory);

    /// The bond tier a bounty falls in (D2): the smallest step at or above it; reverts above the largest step.
    function tierOf(uint256 bounty) external pure returns (uint256);
    /// D2's counter: drawable validators bonded at least BOND_FACTOR × the bounty's tier (0 above the largest step).
    function eligibleCount(uint256 bounty) external view returns (uint256);
    /// The index-th of those `eligibleCount(bounty)` validators, in a fixed order for a given `epoch()`.
    function eligibleAt(uint256 bounty, uint256 index) external view returns (address);
    function candidateCount() external view returns (uint256);
    function candidateAt(uint256 index) external view returns (address);
    /// Bumped on every change to the registry; a draw records the epoch it read (D2).
    function epoch() external view returns (uint256);
    /// The digest a key signs for a statement on a subject (a seal, a reveal...). Two different contents signed for
    /// one subject are equivocation, provable by anyone (`proveEquivocation`). Panels defines its subjects.
    function statementDigest(bytes32 subject, bytes32 content) external view returns (bytes32);

    // ---------- hooks: the bound consumer (Panels) only ----------

    /// A shadow draw's deadline: the candidate revealed or not (a missing seal is a miss). Counts toward its
    /// attempt's reveal rate; never slashed (D16).
    function recordShadow(address key, bool revealed) external;
    /// A revealed shadow verdict scored once (D5): agreeing or not with the outcome it's scored against. Activates
    /// the candidate at QUALIFY_VERDICTS if its reveal rate and agreement meet the thresholds; else it cools off.
    function scoreShadow(address key, bool agreed) external;
    /// A counted (or audit) draw's deadline: sealed and revealed, or a miss. A miss costs the flat SILENCE_SLASH
    /// (never sealed) or SEALED_NO_REVEAL_SLASH (sealed, not revealed), to the pool, and counts toward the
    /// reveal-rate floor, which suspends an active validator at more than ACTIVE_MISSES_MAX misses in its window.
    function recordCounted(address key, bool hasSeal, bool revealed) external;
    /// A counted verdict given (at its draw or reveal) and its finality: unbonding waits for every one.
    function verdictOpened(address key) external;
    function verdictFinal(address key) external;
    /// A challenge naming the validator opened and closed (judged, or ended): unbonding waits for every one.
    function challengeOpened(address key) external;
    function challengeClosed(address key) external;
    /// A provable fault (D16), with whoever proved it (`challenger`, 0 if none) taking CHALLENGE_REWARD_BPS of the
    /// slash and the sponsors' pool the rest. Never more than the bond.
    function slashFault(address key, Fault fault, address challenger) external;
    /// An ADR (`removal`: one that only removes or raises a minimum) passed the constitution tier and became final
    /// after its window: its operations, bound by `commitment` (`adrCommitment`), may now be applied (`applyAdr`).
    function adrPassed(uint256 id, bool removal, bytes32 commitment) external;
}
