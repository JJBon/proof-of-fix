// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

/// What FeesV3 reads from the validator registry (#132 task 3.1, `Validators`). Declared here, not imported, so the
/// meter builds before the registry exists; task 3.5 reconciles the two (an adapter, or Validators exposing these).
/// Assumed: a validator is its key's address; "active" is the state whose tables count (not a candidate, a suspended
/// or a leaving validator: check-pricing, "Validators post cost tables for every unit").
interface IFeesV3Validators {
    /// Whether `key` is an active validator now.
    function isActive(address key) external view returns (bool);

    /// How many validators are active now (the idle share's denominator: check-pricing, "The service fee follows the
    /// queue").
    function activeCount() external view returns (uint256);

    /// The model family `key` registered with (D19: any family, fixed by the registration), whatever its state;
    /// bytes32(0) for a key never registered. PR #223's `validator(key).family`, as a single view.
    function familyOf(address key) external view returns (bytes32);
}

/// What FeesV3 reads from the family scores (#132 task 3.2, `Panels`; specs/judge-scores). Declared here, not imported;
/// task 3.5 reconciles it.
interface IFeesV3Scores {
    /// A family's score state, as specs/judge-scores defines them:
    /// - Neutral: fewer than SCORE_MIN_VERDICTS counted verdicts and never barred (paid the neutral factor, 1 ×);
    /// - Scored: SCORE_MIN_VERDICTS or more counted verdicts in its window (paid by its score, normalised);
    /// - Recovering: drawn again after a barring, fewer than SCORE_MIN_VERDICTS new counted verdicts (paid
    ///   SCORE_FACTOR_MIN);
    /// - Barred: below SCORE_MIN; not drawn for counted panels, but a seat drawn before its barring is paid by its score.
    enum ScoreState {
        Neutral,
        Scored,
        Recovering,
        Barred
    }

    /// A family's state and its balanced score over its counted window, in WAD (1e18 = 100 %). The score is read only
    /// in the Scored and Barred states.
    function familyScore(bytes32 family) external view returns (ScoreState state, uint256 scoreWad);
}

/// What RaceV3 (task 3.5) asks of its check-fee meter (#132 task 3.3, design D9, D14; specs/check-pricing): v2's
/// formula (IFees, Fees) with market prices. Every amount in micro-coins of the version's fee coin.
interface IFeesV3 {
    /// What one judge's check used, as its attested node measured it (v2's S14), and its receipt's hash.
    struct Usage {
        bytes32 receipt;
        uint64 input; // tokens, cached ones included
        uint64 cached;
        uint64 output;
        uint64 vcpuSeconds;
        uint64 gbSeconds;
        uint64 storageMb;
    }

    /// A repository's CI profile (v2's S15): the test image, the CPU (thousandths of a vCPU), the memory and the
    /// timeout.
    struct Profile {
        bytes32 image;
        uint32 milliVcpus;
        uint32 memoryMb;
        uint32 timeoutSeconds;
    }

    /// The constitution's per-check caps and the relayer's gas terms (v2's S15).
    struct Caps {
        uint64 inputTokens;
        uint64 outputTokens;
        uint64 storageMb;
        uint64 gasAllowance; // gas units a result's relay may be repaid
        uint64 gasOverhead; // what the call can't measure (calldata, the transaction's base)
        uint64 maxGasPrice; // wei: the deposit's gas price, and the most a repayment counts
    }

    /// A counted judge's report, as the race found it (the race checks that the judge was counted): who is paid, the
    /// judge's model family, and its usage.
    struct Report {
        address payee;
        bytes32 family;
        Usage usage;
    }

    /// The version's fee coin: every metered check deposit is in it.
    function coin() external view returns (address);

    /// The race this meter serves, bound once by the race itself (`bind`).
    function race() external view returns (address);

    /// Binds the meter to its race: the caller, once.
    function bind() external;

    /// Starts attempt `id`: its prices are the table and the service fee in force now, whatever later periods do
    /// (check-pricing, "An attempt is charged the prices it was quoted"); it counts as one of this period's
    /// submissions. Once per attempt; only the race.
    function open(uint256 id) external;

    /// Attempt `id` started waiting for a panel: it counts once, in this period, however long it waits and whatever
    /// kept it from being drawn. Further calls change nothing. Only the race.
    function waited(uint256 id) external;

    /// A counted panel of attempt `id` stalled for want of a replacement: it counts as a wait once. Only the race.
    function stalled(uint256 id) external;

    /// Validators seated on a counted panel this period (silent ones and replacements included): each counts once a
    /// period as drawn (the idle share's numerator is the active validators not drawn). Only the race.
    function drawn(address[] calldata judges) external;

    /// Whether a model family has its first price (D19). An unpriced family's validators aren't drawn, as counted
    /// judges or as shadows, and `settle` and `shadowCost` refuse it.
    function isPriced(bytes32 family) external view returns (bool);

    /// The deposit for an attempt with up to `judges` counted judges in `repo` at the prices in force now: every judge
    /// at the caps and the dearest priced family, the service fee at SCORE_FACTOR_MAX each, the CI runs at the profile's
    /// limits, and the gas allowance.
    function maxDeposit(bytes32 repo, uint256 judges) external view returns (uint256);

    /// The same at attempt `id`'s fixed prices (the prices in force now if it isn't open yet).
    function depositFor(uint256 id, bytes32 repo, uint256 judges) external view returns (uint256);

    /// Settles attempt `id`'s counted checks once, at its fixed prices: what each counted judge's payee and the
    /// relayer are paid, judges first. Only the race.
    function settle(uint256 id, bytes32 repo, Report[] calldata counted, address relayer, uint256 gasUsed)
        external
        returns (address[] memory to, uint256[] memory micro);

    /// A shadow judge's metered usage (its own report, capped) at attempt `id`'s prices: no service fee
    /// (validator-admission: shadows are repaid their usage from the sponsors' pool, capped per draw).
    function shadowCost(uint256 id, bytes32 repo, bytes32 family, Usage calldata u) external view returns (uint256);

    /// What each judge of an audit or a challenge panel of attempt `id` is paid: the median of the panel's reports at
    /// the attempt's prices plus the unscaled service fee (task 3.5). A view; the race pays each panel once.
    function checkCost(uint256 id, bytes32 repo, Report[] calldata judges) external view returns (uint256[] memory);
    /// Closes the oldest ended pricing period, in bounded parts (task 3.5).
    function roll() external;
}
