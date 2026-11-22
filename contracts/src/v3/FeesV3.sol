// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {IFeesV3, IFeesV3Validators, IFeesV3Scores} from "./IFeesV3.sol";
import {LaunchChain} from "./LaunchChain.sol";

/// Check fees for v3 (#132 task 3.3; design D9, D14, D19; specs/check-pricing, specs/judge-scores): v2's taxi fare with
/// tolls (src/v2/Fees.sol), with prices set by market rules instead of a vote, and model families open.
///
///   a counted judge's pay = the median of the counted judges' usage × its own family's token prices
///                         + the median sandbox usage × the sandbox's prices (its own test run; once, with CI_SINGLE_RUN)
///                         + the median storage × the storage price
///                         + the service fee × its family's score factor (D14)
///   the relayer's pay      = the gas measured in the result's call plus the overhead, at the transaction's gas price
///                           (at most the cap), in the fee coin at the table's ETH price, within the gas allowance
///
/// **Units.** Four shared units (the sandbox's vCPU-seconds and GB-seconds, storage MB: micro-coins per million; the
/// ETH price: micro-coins per ETH), and three token units per priced family (input, cached and output tokens,
/// micro-coins per million). The service fee isn't a unit and no one posts it.
///
/// **Open families (D19).** No list: the genesis prices the shared units and the families the genesis needs (its
/// validator's at least); any other family appears when someone announces a registered validator of it (`announce`),
/// and is priced by the other validators' tables. Its first price is the lower median of the counting tables that price
/// it, once at least MEDIAN_MIN_POSTERS do and at least MEDIAN_MIN_POSTERS of them come from validators of other
/// families, each token unit capped at PRICE_CAP_X × that unit's dearest priced family at that moment. From then on the
/// normal rule, with the cap at PRICE_CAP_X × its first price; from the next period a table must price it to count. A
/// family announced but not priced within PENDING_PERIODS periods leaves the queue (anyone may announce it again), so
/// `roll`'s work stays bounded by the families someone keeps registering.
///
/// **Unit prices: a median feed (D9).** Any active validator posts a table whenever it likes (`post`): the shared units
/// and any families' token prices; only its latest counts. A table counts if it has every shared unit and every family
/// priced before the period closes, each value above 0 (0 marks a unit not posted). At the end of each PRICE_PERIOD
/// (`roll`, anyone, in bounded parts: `rollPart`), each priced unit moves toward the lower median of the counting
/// tables, by at most PRICE_STEP_MAX_BPS of itself, never above PRICE_CAP_X × its first value, and only if at least
/// MEDIAN_MIN_POSTERS tables count.
///
/// **The service fee: a queue controller (D9).** It starts at FEE_CEILING. At the end of each period it rises
/// FEE_STEP_BPS if more than WAIT_HIGH_BPS of the period's submissions waited for a panel (every wait once, in the
/// period it started, and a stalled counted panel once), otherwise falls FEE_STEP_BPS if more than IDLE_HIGH_BPS of the
/// active validators weren't drawn; always within [FEE_FLOOR, FEE_CEILING].
///
/// **The score factor (D14).** A counted judge's service fee is scaled by its family's factor: linear from
/// SCORE_FACTOR_MIN at SCORE_MIN to SCORE_FACTOR_MAX at 100 % (the raw factor), divided by the mean raw factor over the
/// previous period's counted seats of scored families (`norm`, carried over a period with none), and kept within both
/// bounds. A neutral family is paid 1 ×, a recovering one SCORE_FACTOR_MIN. Metered usage is always repaid in full.
///
/// **Quotes are stable.** Each closed period is an epoch; every unit keeps the history of its changes, so an attempt
/// opened in epoch e is charged epoch e's prices, whatever later periods do.
///
/// **One repository (#251, design L1).** The deployment serves one repository, and FeesV3 keeps its one CI profile
/// (`repo`, `profileOf`); another repository's profile is refused. There is no default profile.
///
/// Keyless: no owner, no admin, no setter. The parameters are constants of the version; the genesis prices, the caps
/// and the CI profile are fixed at deployment. Prices move only by `roll`'s rules. The constructor reverts off Sepolia
/// and the local test chains (LaunchChain).
contract FeesV3 is IFeesV3 {
    uint256 public constant BPS = 10_000;
    uint256 internal constant M = 1e6; // unit prices are per million units
    uint256 internal constant WAD = 1e18;
    uint256 internal constant SHARED = 4; // vCPU-s, GB-s, storage MB, ETH
    // values are kept in 64 bits (a table entry packs a version and three prices in one slot); a price, its first
    // value and its cap stay below a quarter of that, so posted values clamped to 64 bits move nothing differently
    uint256 internal constant MAX_POSTED = type(uint64).max;
    uint256 internal constant MAX_PRICE = type(uint64).max / 4;

    // D9 and ADR 0004's accepted values
    uint256 public constant PRICE_PERIOD = 1 days;
    uint256 public constant PRICE_STEP_MAX_BPS = 2_500; // 25 % a period
    uint256 public constant PRICE_CAP_X = 2; // never above 2 × the first price
    uint256 public constant MEDIAN_MIN_POSTERS = 3; // counting tables, and (D19) of other families for a first price
    uint256 public constant FEE_STEP_BPS = 500; // 5 % a period, both ways
    uint256 public constant WAIT_HIGH_BPS = 500; // 5 % of the period's submissions waited
    uint256 public constant IDLE_HIGH_BPS = 4_000; // 40 % of active validators not drawn
    uint256 public constant FEE_FLOOR = 10_000; // $0.01 a counted check
    uint256 public constant FEE_CEILING = 250_000; // $0.25 a counted check; FEE_START
    // a gas bound, not a market rule: an announced family waits at most this many periods for its first price
    uint256 public constant PENDING_PERIODS = 7;
    // gas bounds, not market rules (task 3.5): a roll part reads at most about ROLL_WORK posted entries (a poster's
    // table in the counting part, a family's in the others); `roll` keeps going while ROLL_PART_GAS is left
    uint256 public constant ROLL_WORK = 100;
    uint256 public constant ROLL_PART_GAS = 1_000_000;

    // D14 and ADR 0004's accepted values (WAD: 1e18 = 100 % or 1 ×)
    uint256 public constant SCORE_MIN = 0.7e18;
    uint256 public constant SCORE_FACTOR_MIN = 0.5e18;
    uint256 public constant SCORE_FACTOR_MAX = 2e18;

    struct Genesis {
        address coin;
        uint256[4] shared; // vCPU-s, GB-s, storage MB, ETH; each > 0
        bytes32[] families; // priced from the start (the genesis validator's at least); more arrive by D19
        uint256[3][] tokens; // per family: input, cached, output; each > 0
        Caps caps;
        bytes32 repo; // the deployment's one repository, keccak256 of its Radicle RID (RaceV3.repo)
        Profile profile; // its CI profile
        bool ciSingleRun;
    }

    /// A pricing period's queue signals and counted seats.
    struct Period {
        uint64 submitted;
        uint64 waited; // waits and stalls, each once
        uint64 drawn; // distinct validators seated on counted panels
        uint64 seats; // counted seats of scored families paid in it
        uint256 rawSum; // their raw factors (WAD)
    }

    /// A roll under way (`rollPart`): its phase (0 none, 1 counting, 2 shared, 3 families, 4 new families, 5 close),
    /// the part's cursor, and the counting tables found.
    struct Rolling {
        uint64 phase;
        uint64 cursor;
        uint64 n;
        uint64 spare;
    }

    /// A unit's value from `epoch` on.
    struct Checkpoint {
        uint64 epoch;
        uint192 value;
    }

    IFeesV3Validators public immutable validators;
    IFeesV3Scores public immutable scores;
    address public immutable coin;
    bool public immutable ciSingleRun;
    bytes32 public immutable repo;
    uint256 public immutable start; // period p is [start + p × PRICE_PERIOD, start + (p + 1) × PRICE_PERIOD)

    address public race;
    uint256 public rolled; // periods closed; the epoch in force
    uint256 public norm = WAD; // the mean raw factor over the last closed period with counted seats

    Caps internal _caps;
    mapping(bytes32 unit => Checkpoint[]) internal _hist; // unit: _unit(family, j); the shared units' family is 0
    mapping(bytes32 unit => uint256) internal _first; // the cap's reference: genesis, or a new family's first price
    mapping(bytes32 family => uint256) internal _pricedAt; // epoch + 1
    mapping(bytes32 family => uint256) internal _announced; // period + 1, while waiting for a first price
    bytes32[] internal _priced;
    bytes32[] internal _pending;
    mapping(uint256 epoch => uint256) internal _fees;

    // the posted tables: each post is a new version; a value counts only from the poster's latest version. One slot
    // each: _vers = version << 128 | the version of its last complete shared units; _shared = 4 × 64-bit values;
    // _tok = version << 192 | input << 128 | cached << 64 | output
    mapping(address validator => uint256) internal _vers;
    mapping(address validator => uint256) internal _shared;
    mapping(address validator => mapping(bytes32 family => uint256)) internal _tok;
    mapping(address validator => bytes32) internal _famOf;
    mapping(address validator => bool) internal _listed;
    address[] internal _posters;

    Rolling internal _rolling;
    uint256[3] internal _top; // each token unit's dearest priced family before the roll under way
    mapping(uint256 k => uint256) internal _rc; // the roll's counting posters: address << 96 | its table's version

    mapping(uint256 period => Period) internal _periods;
    mapping(address validator => uint256) internal _drawnIn; // period + 1
    mapping(uint256 id => uint256) internal _epochOf; // epoch + 1
    mapping(uint256 id => uint256) internal _flags; // 1: waited, 2: stalled
    mapping(uint256 id => bool) public settled;
    Profile internal _profile;

    event Bound(address indexed race);
    event Posted(address indexed validator, uint256 version, bytes32 table);
    event Announced(bytes32 indexed family, address key);
    event FamilyPriced(bytes32 indexed family, uint256 epoch, uint256[3] first);
    event FamilyDropped(bytes32 indexed family);
    event Rolled(uint256 indexed period, uint256 counting, uint256 serviceFee, uint256 norm);
    event Opened(uint256 indexed id, uint256 epoch);
    event Waited(uint256 indexed id, uint256 indexed period, bool stall);
    event Charged(uint256 indexed id, uint256 judges, uint256 total);

    error BadParams();
    error AlreadyBound();
    error NotRace();
    error NotActive();
    error BadTable();
    error NotRegistered();
    error TooEarly();
    error AlreadyOpen();
    error NotOpen();
    error AlreadySettled();
    error Unpriced(bytes32 family);
    error RollInProgress();
    error UnknownRepo(bytes32 repo);

    constructor(IFeesV3Validators validators_, IFeesV3Scores scores_, Genesis memory g) {
        LaunchChain.check();
        uint256 f = g.families.length;
        if (address(validators_).code.length == 0 || address(scores_).code.length == 0) revert BadParams();
        if (g.coin == address(0) || f == 0 || g.tokens.length != f) revert BadParams();
        if (g.repo == bytes32(0) || g.profile.timeoutSeconds == 0) revert BadParams();
        for (uint256 j; j < SHARED; ++j) {
            _genesisUnit(_unit(0, j), g.shared[j]);
        }
        for (uint256 i; i < f; ++i) {
            bytes32 fam = g.families[i];
            if (fam == 0 || _pricedAt[fam] != 0) revert BadParams();
            for (uint256 j; j < 3; ++j) {
                _genesisUnit(_unit(fam, j), g.tokens[i][j]);
            }
            _pricedAt[fam] = 1;
            _priced.push(fam);
        }
        validators = validators_;
        scores = scores_;
        coin = g.coin;
        ciSingleRun = g.ciSingleRun;
        repo = g.repo;
        _profile = g.profile;
        start = block.timestamp;
        _caps = g.caps;
        _fees[0] = FEE_CEILING; // FEE_START (#141)
    }

    // ---------- the race ----------

    function bind() external {
        if (race != address(0)) revert AlreadyBound();
        race = msg.sender;
        emit Bound(msg.sender);
    }

    function open(uint256 id) external {
        _onlyRace();
        if (_epochOf[id] != 0) revert AlreadyOpen();
        uint256 e = rolled;
        _epochOf[id] = e + 1;
        ++_periods[currentPeriod()].submitted;
        emit Opened(id, e);
    }

    function waited(uint256 id) external {
        _wait(id, 1);
    }

    function stalled(uint256 id) external {
        _wait(id, 2);
    }

    function drawn(address[] calldata judges) external {
        _onlyRace();
        uint256 p = currentPeriod();
        Period storage per = _periods[p];
        for (uint256 i; i < judges.length; ++i) {
            if (_drawnIn[judges[i]] != p + 1) {
                _drawnIn[judges[i]] = p + 1;
                ++per.drawn;
            }
        }
    }

    function settle(uint256 id, bytes32 repo_, Report[] calldata counted, address relayer, uint256 gasUsed)
        external
        returns (address[] memory to, uint256[] memory micro)
    {
        _onlyRace();
        uint256 e = _epoch(id);
        if (settled[id]) revert AlreadySettled();
        settled[id] = true;
        uint256[4] memory sh = _sharedAt(e);
        uint256 n = counted.length;
        to = new address[](n + 1);
        micro = new uint256[](n + 1);
        uint256 total;
        if (n != 0) {
            Profile memory p = profileOf(repo_);
            Usage memory mid = _median(counted, p);
            uint256 shared = _storageCost(sh, mid);
            uint256 run = _sandboxCost(sh, mid);
            uint256 fee = _fees[e];
            Period storage per = _periods[currentPeriod()];
            bool ran;
            for (uint256 k; k < n; ++k) {
                Report calldata r = counted[k];
                uint256 pay = _tokensCost(_tokensAt(r.family, e), mid) + shared + _service(fee, r.family, per);
                if (!ciSingleRun) {
                    pay += run;
                } else if (!ran && r.usage.vcpuSeconds != 0) {
                    pay += _sandboxCost(sh, _capped(r.usage, p)); // the one attested run, at its own measurement
                    ran = true;
                }
                to[k] = r.payee;
                micro[k] = pay;
                total += pay;
            }
        }
        to[n] = relayer;
        micro[n] = _gasCost(sh, gasUsed);
        total += micro[n];
        emit Charged(id, n, total);
    }

    // ---------- validators and anyone ----------

    /// An active validator posts its cost table, replacing its earlier one: the shared units, and the token prices of
    /// any families (every priced one, for the table to count; others count toward a new family's first price). A 0
    /// marks a value not posted: the shared units then don't count, nor does that family's entry.
    function post(uint256[4] calldata shared, bytes32[] calldata families, uint256[3][] calldata tokens) external {
        _notRolling();
        if (!validators.isActive(msg.sender)) revert NotActive();
        if (families.length != tokens.length) revert BadTable();
        uint256 vs = _vers[msg.sender];
        uint256 ver = (vs >> 128) + 1;
        uint256 sharedVer = uint128(vs);
        if (shared[0] != 0 && shared[1] != 0 && shared[2] != 0 && shared[3] != 0) {
            _shared[msg.sender] = _clip(shared[0]) << 192 | _clip(shared[1]) << 128 | _clip(shared[2]) << 64
                | _clip(shared[3]);
            sharedVer = ver;
        }
        _vers[msg.sender] = ver << 128 | sharedVer;
        for (uint256 i; i < families.length; ++i) {
            uint256[3] calldata t = tokens[i];
            if (families[i] != 0 && t[0] != 0 && t[1] != 0 && t[2] != 0) {
                _tok[msg.sender][families[i]] = ver << 192 | _clip(t[0]) << 128 | _clip(t[1]) << 64 | _clip(t[2]);
            }
        }
        if (!_listed[msg.sender]) {
            _listed[msg.sender] = true;
            _posters.push(msg.sender);
            _famOf[msg.sender] = validators.familyOf(msg.sender);
        }
        emit Posted(msg.sender, ver, keccak256(abi.encode(shared, families, tokens)));
    }

    /// Anyone: a registered validator's family, if it isn't priced or waiting, waits for its first price (D19: a family
    /// appears when a validator first registers with it).
    function announce(address key) external {
        _notRolling();
        bytes32 f = validators.familyOf(key);
        if (f == 0) revert NotRegistered();
        if (_pricedAt[f] != 0 || _announced[f] != 0) return;
        _announced[f] = currentPeriod() + 1;
        _pending.push(f);
        emit Announced(f, key);
    }

    /// Anyone closes the oldest open period once it has ended: the unit prices by the median rule, new families' first
    /// prices, the service fee by the queue rule, and the score factor's normaliser. One period a call, in bounded
    /// parts (`rollPart`): this runs parts while more than ROLL_PART_GAS gas is left, at least one, and stops once the
    /// period has closed. With the gas a busy block allows, a caller passes a smaller limit and calls again.
    function roll() external {
        uint256 p = rolled;
        do {
            rollPart();
        } while (rolled == p && gasleft() > ROLL_PART_GAS);
    }

    /// One bounded part of closing the oldest open period (#222's roll split, task 3.5). The parts, in order:
    /// - **counting:** up to ROLL_WORK table entries (a poster's every priced family) of the posters whose latest
    ///   table counts, kept in order with their versions; a poster no longer active leaves the list;
    /// - **shared:** the four shared units, toward the counting tables' lower median;
    /// - **families:** the priced families' token units, a few families a part (ROLL_WORK entries), noting each unit's
    ///   dearest family before this period's change (a new family's cap);
    /// - **new families:** the waiting families, a few a part: priced, dropped after PENDING_PERIODS, or left waiting;
    /// - **close:** the service fee, the normaliser, and the epoch.
    /// While a roll is under way, `post` and `announce` wait (RollInProgress): every part reads the same tables. Quotes
    /// don't move until the close (each new value is recorded for the next epoch). The parts compose to exactly the
    /// one-call roll of #222.
    function rollPart() public {
        Rolling memory r = _rolling;
        uint256 p = rolled;
        if (r.phase == 0) {
            if (block.timestamp < start + (p + 1) * PRICE_PERIOD) revert TooEarly();
            r = Rolling(1, 0, 0, 0);
            delete _top;
        }
        uint256 e = p + 1;
        if (r.phase == 1) {
            _countPart(r);
        } else if (r.phase == 2) {
            if (r.n >= MEDIAN_MIN_POSTERS) _sharedPart(r.n, e);
            r.phase = 3;
        } else if (r.phase == 3) {
            _familiesPart(r, e);
        } else if (r.phase == 4) {
            _pendingPart(r, e, p);
        } else {
            Period memory per = _periods[p];
            uint256 fee = stepFee(_fees[p], per.submitted, per.waited, validators.activeCount(), per.drawn);
            _fees[e] = fee;
            if (per.seats != 0) norm = per.rawSum / per.seats;
            rolled = e;
            r.phase = 0;
            emit Rolled(p, r.n, fee, norm);
        }
        _rolling = r;
    }

    // ---------- the rules, as pure functions ----------

    /// A unit's next price: toward `target`, by at most PRICE_STEP_MAX_BPS of `old` either way (so the move is never
    /// more than that share, rounding included), and never above PRICE_CAP_X × `first`.
    function stepPrice(uint256 old, uint256 first, uint256 target) public pure returns (uint256) {
        uint256 lo = (old * (BPS - PRICE_STEP_MAX_BPS) + BPS - 1) / BPS;
        uint256 hi = old * (BPS + PRICE_STEP_MAX_BPS) / BPS;
        uint256 cap = first * PRICE_CAP_X;
        if (hi > cap) hi = cap;
        return target < lo ? lo : target > hi ? hi : target;
    }

    /// The next service fee: up FEE_STEP_BPS if more than WAIT_HIGH_BPS of the submissions waited; otherwise down
    /// FEE_STEP_BPS if more than IDLE_HIGH_BPS of the active validators weren't drawn; within [FEE_FLOOR, FEE_CEILING].
    function stepFee(uint256 fee, uint256 submitted, uint256 waits, uint256 active, uint256 seated)
        public
        pure
        returns (uint256)
    {
        if (seated > active) seated = active;
        if (submitted != 0 && waits * BPS > submitted * WAIT_HIGH_BPS) {
            fee = fee * (BPS + FEE_STEP_BPS) / BPS;
        } else if (active != 0 && (active - seated) * BPS > active * IDLE_HIGH_BPS) {
            fee = fee * (BPS - FEE_STEP_BPS) / BPS;
        }
        return fee < FEE_FLOOR ? FEE_FLOOR : fee > FEE_CEILING ? FEE_CEILING : fee;
    }

    /// The raw factor for a score: linear from SCORE_FACTOR_MIN at SCORE_MIN to SCORE_FACTOR_MAX at 100 %, within
    /// those bounds (WAD).
    function rawFactor(uint256 scoreWad) public pure returns (uint256) {
        if (scoreWad <= SCORE_MIN) return SCORE_FACTOR_MIN;
        uint256 x = SCORE_FACTOR_MIN + (scoreWad - SCORE_MIN) * (SCORE_FACTOR_MAX - SCORE_FACTOR_MIN) / (WAD - SCORE_MIN);
        return x > SCORE_FACTOR_MAX ? SCORE_FACTOR_MAX : x;
    }

    // ---------- views ----------

    function currentPeriod() public view returns (uint256) {
        return (block.timestamp - start) / PRICE_PERIOD;
    }

    function isPriced(bytes32 family) external view returns (bool) {
        return _pricedAt[family] != 0;
    }

    /// The epoch from which a family is priced (reverts while it isn't).
    function pricedFrom(bytes32 family) external view returns (uint256) {
        uint256 at = _pricedAt[family];
        if (at == 0) revert Unpriced(family);
        return at - 1;
    }

    function pricedFamilies() external view returns (bytes32[] memory) {
        return _priced;
    }

    function pendingFamilies() external view returns (bytes32[] memory) {
        return _pending;
    }

    /// The shared units in force now: vCPU-s, GB-s, storage MB, ETH.
    function sharedPrices() external view returns (uint256[4] memory) {
        return _sharedAt(rolled);
    }

    function sharedPricesAt(uint256 epoch) external view returns (uint256[4] memory) {
        return _sharedAt(epoch);
    }

    /// A priced family's token prices in force now: input, cached, output.
    function tokenPrices(bytes32 family) external view returns (uint256[3] memory) {
        return _tokensAt(family, rolled);
    }

    function tokenPricesAt(bytes32 family, uint256 epoch) external view returns (uint256[3] memory) {
        return _tokensAt(family, epoch);
    }

    /// A unit's cap reference (family 0: the shared unit j): its genesis value or a new family's first price.
    function firstPrice(bytes32 family, uint256 j) external view returns (uint256) {
        return _first[_unit(family, j)];
    }

    /// The service fee in force now, micro-coins per counted check, before the score factor.
    function serviceFee() external view returns (uint256) {
        return _fees[rolled];
    }

    function serviceFeeAt(uint256 epoch) external view returns (uint256) {
        return _fees[epoch];
    }

    /// The epoch whose prices attempt `id` is charged (reverts if it isn't open).
    function epochOf(uint256 id) external view returns (uint256) {
        return _epoch(id);
    }

    /// A validator's latest complete shared units (as kept: within 64 bits), and whether its latest table has them.
    function postedShared(address validator) external view returns (uint256[4] memory values, bool current) {
        uint256 w = _shared[validator];
        for (uint256 j; j < SHARED; ++j) {
            values[j] = _word(w, 3 - j);
        }
        uint256 vs = _vers[validator];
        current = vs != 0 && uint128(vs) == vs >> 128;
    }

    /// A validator's latest token prices for a family (as kept: within 64 bits), and whether its latest table has them.
    function postedTokens(address validator, bytes32 family)
        external
        view
        returns (uint256[3] memory values, bool current)
    {
        uint256 w = _tok[validator][family];
        for (uint256 j; j < 3; ++j) {
            values[j] = _word(w, 2 - j);
        }
        current = w != 0 && w >> 192 == _vers[validator] >> 128;
    }

    function posters() external view returns (address[] memory) {
        return _posters;
    }

    function period(uint256 p) external view returns (Period memory) {
        return _periods[p];
    }

    /// A family's score factor now (WAD), as `settle` would pay it.
    function factorOf(bytes32 family) public view returns (uint256 f) {
        (IFeesV3Scores.ScoreState s, uint256 score) = scores.familyScore(family);
        if (s == IFeesV3Scores.ScoreState.Neutral) return WAD;
        if (s == IFeesV3Scores.ScoreState.Recovering) return SCORE_FACTOR_MIN;
        f = rawFactor(score) * WAD / norm;
        if (f < SCORE_FACTOR_MIN) f = SCORE_FACTOR_MIN;
        if (f > SCORE_FACTOR_MAX) f = SCORE_FACTOR_MAX;
    }

    function caps() external view returns (Caps memory) {
        return _caps;
    }

    /// The deployment's repository's CI profile; any other repository is refused.
    function profileOf(bytes32 r) public view returns (Profile memory) {
        if (r != repo) revert UnknownRepo(r);
        return _profile;
    }

    function maxDeposit(bytes32 repo_, uint256 judges) external view returns (uint256) {
        return _deposit(rolled, repo_, judges);
    }

    function depositFor(uint256 id, bytes32 repo_, uint256 judges) external view returns (uint256) {
        uint256 e = _epochOf[id];
        return _deposit(e == 0 ? rolled : e - 1, repo_, judges);
    }

    function shadowCost(uint256 id, bytes32 repo_, bytes32 family, Usage calldata u) external view returns (uint256) {
        uint256 e = _epoch(id);
        uint256[4] memory sh = _sharedAt(e);
        Usage memory c = _capped(u, profileOf(repo_));
        return _tokensCost(_tokensAt(family, e), c) + _sandboxCost(sh, c) + _storageCost(sh, c);
    }

    /// What each judge of an audit or a challenge panel of attempt `id` is paid (task 3.5; specs/judge-panels, "An
    /// audit agrees"): the median of that panel's reports at the attempt's prices, as `settle` computes it, plus the
    /// service fee unscaled (the score factor is for counted seats, D14). No relayer's gas. A view: the race pays it
    /// once per panel, from what it holds.
    function checkCost(uint256 id, bytes32 repo_, Report[] calldata judges)
        external
        view
        returns (uint256[] memory micro)
    {
        uint256 e = _epoch(id);
        uint256 n = judges.length;
        micro = new uint256[](n);
        if (n == 0) return micro;
        uint256[4] memory sh = _sharedAt(e);
        Profile memory p = profileOf(repo_);
        Usage memory mid = _median(judges, p);
        uint256 base = _storageCost(sh, mid) + _fees[e];
        uint256 run = _sandboxCost(sh, mid);
        bool ran;
        for (uint256 k; k < n; ++k) {
            Report calldata r = judges[k];
            uint256 pay = _tokensCost(_tokensAt(r.family, e), mid) + base;
            if (!ciSingleRun) {
                pay += run;
            } else if (!ran && r.usage.vcpuSeconds != 0) {
                pay += _sandboxCost(sh, _capped(r.usage, p));
                ran = true;
            }
            micro[k] = pay;
        }
    }

    /// Whether a roll is under way (`rollPart`), and its phase.
    function rollPhase() external view returns (uint256) {
        return _rolling.phase;
    }

    // ---------- internals ----------

    function _onlyRace() internal view {
        if (msg.sender != race) revert NotRace();
    }

    function _epoch(uint256 id) internal view returns (uint256) {
        uint256 e = _epochOf[id];
        if (e == 0) revert NotOpen();
        return e - 1;
    }

    function _wait(uint256 id, uint256 bit) internal {
        _onlyRace();
        uint256 fl = _flags[id];
        if (fl & bit != 0) return;
        _flags[id] = fl | bit;
        uint256 p = currentPeriod();
        ++_periods[p].waited;
        emit Waited(id, p, bit == 2);
    }

    /// A posted value as kept: at most 64 bits (MAX_POSTED is above every cap, so clamping changes no outcome).
    function _clip(uint256 v) internal pure returns (uint256) {
        return v > MAX_POSTED ? MAX_POSTED : v;
    }

    /// The i-th 64-bit word of a packed slot, counted from the low end.
    function _word(uint256 w, uint256 i) internal pure returns (uint256) {
        return uint64(w >> (64 * i));
    }

    function _unit(bytes32 family, uint256 j) internal pure returns (bytes32) {
        return keccak256(abi.encode(family, j));
    }

    /// A genesis value: above 0 (a price at 0 could never move: each step is a share of itself) and within MAX_PRICE
    /// (so the steps' products stay safe).
    function _genesisUnit(bytes32 u, uint256 v) internal {
        if (v == 0 || v > MAX_PRICE) revert BadParams();
        _hist[u].push(Checkpoint(0, uint192(v)));
        _first[u] = v;
    }

    function _latest(bytes32 u) internal view returns (uint256) {
        Checkpoint[] storage h = _hist[u];
        return h[h.length - 1].value;
    }

    /// A unit's value in epoch `e`: its last change at or before it (0 if it had no value yet).
    function _at(bytes32 u, uint256 e) internal view returns (uint256) {
        Checkpoint[] storage h = _hist[u];
        uint256 hi = h.length;
        if (hi == 0) return 0;
        if (h[hi - 1].epoch <= e) return h[hi - 1].value; // the usual case: no change since
        uint256 lo;
        while (lo < hi) {
            uint256 mid = (lo + hi) / 2;
            if (h[mid].epoch <= e) lo = mid + 1;
            else hi = mid;
        }
        return lo == 0 ? 0 : h[lo - 1].value;
    }

    function _sharedAt(uint256 e) internal view returns (uint256[4] memory s) {
        for (uint256 j; j < SHARED; ++j) {
            s[j] = _at(_unit(0, j), e);
        }
    }

    function _tokensAt(bytes32 family, uint256 e) internal view returns (uint256[3] memory t) {
        uint256 at = _pricedAt[family];
        if (at == 0 || at - 1 > e) revert Unpriced(family);
        for (uint256 j; j < 3; ++j) {
            t[j] = _at(_unit(family, j), e);
        }
    }

    /// Moves a priced unit toward the lower median of `vals` (reordered), recording a change.
    function _step(bytes32 u, uint256 e, uint256[] memory vals) internal {
        uint256 old = _latest(u);
        uint256 v = stepPrice(old, _first[u], _select(vals, (vals.length - 1) / 2));
        if (v != old) _hist[u].push(Checkpoint(uint64(e), uint192(v)));
    }

    /// The counting part: posters from the cursor, ROLL_WORK entries' worth (each poster costs one plus the priced
    /// families). A counting poster is active, with every shared unit and every priced family in its latest table.
    function _countPart(Rolling memory r) internal {
        uint256 len = _posters.length;
        uint256 priced = _priced.length;
        uint256 i = r.cursor;
        uint256 n = r.n;
        uint256 work;
        while (i < len && work < ROLL_WORK) {
            work += priced + 1;
            address v = _posters[i];
            if (!validators.isActive(v)) {
                _posters[i] = _posters[len - 1];
                _posters.pop();
                _listed[v] = false;
                --len;
                continue;
            }
            ++i;
            uint256 vs = _vers[v];
            uint256 ver = vs >> 128;
            if (uint128(vs) != ver) continue;
            bool all = true;
            for (uint256 f; f < priced && all; ++f) {
                all = _tok[v][_priced[f]] >> 192 == ver;
            }
            if (!all) continue;
            _rc[n++] = uint256(uint160(v)) << 96 | ver;
            // a version is a post count: far below 2^96
        }
        r.cursor = uint64(i);
        r.n = uint64(n);
        if (i == len) {
            r.phase = 2;
            r.cursor = 0;
        }
    }

    function _sharedPart(uint256 n, uint256 e) internal {
        uint256[] memory w = new uint256[](n);
        for (uint256 k; k < n; ++k) {
            w[k] = _shared[_poster(k)];
        }
        uint256[] memory vals = new uint256[](n);
        for (uint256 j; j < SHARED; ++j) {
            for (uint256 k; k < n; ++k) {
                vals[k] = _word(w[k], 3 - j);
            }
            _step(_unit(0, j), e, vals);
        }
    }

    /// The families part: the priced families from the cursor, ROLL_WORK entries' worth (each family costs the
    /// counting tables, at least one family a part).
    function _familiesPart(Rolling memory r, uint256 e) internal {
        uint256 priced = _priced.length;
        uint256 n = r.n;
        uint256 i = r.cursor;
        uint256 work;
        uint256[3] memory top = _top;
        address[] memory c = new address[](n);
        for (uint256 k; k < n; ++k) {
            c[k] = _poster(k);
        }
        uint256[] memory w = new uint256[](n);
        uint256[] memory vals = new uint256[](n);
        while (i < priced && (work == 0 || work + n <= ROLL_WORK)) {
            work += n + 1;
            bytes32 f = _priced[i++];
            if (n >= MEDIAN_MIN_POSTERS) {
                for (uint256 k; k < n; ++k) {
                    w[k] = _tok[c[k]][f];
                }
            }
            for (uint256 j; j < 3; ++j) {
                bytes32 u = _unit(f, j);
                uint256 old = _latest(u);
                if (old > top[j]) top[j] = old;
                if (n >= MEDIAN_MIN_POSTERS) {
                    for (uint256 k; k < n; ++k) {
                        vals[k] = _word(w[k], 2 - j);
                    }
                    _step(u, e, vals);
                }
            }
        }
        _top = top;
        r.cursor = uint64(i);
        if (i == priced) {
            r.phase = 4;
            r.cursor = 0;
        }
    }

    /// D19, the new families part: from the cursor, ROLL_WORK entries' worth, each waiting family whose counting
    /// tables number at least MEDIAN_MIN_POSTERS, at least that many from validators of other families, gets its first
    /// price: the lower median per token unit, at most PRICE_CAP_X × that unit's dearest priced family before this
    /// period (`_top`). A family waiting PENDING_PERIODS periods unpriced leaves the queue.
    function _pendingPart(Rolling memory r, uint256 e, uint256 p) internal {
        uint256 len = _pending.length;
        uint256 n = r.n;
        uint256 i = r.cursor;
        uint256 work;
        address[] memory c = new address[](n);
        uint256[] memory vers = new uint256[](n);
        for (uint256 k; k < n; ++k) {
            uint256 x = _rc[k];
            c[k] = address(uint160(x >> 96));
            vers[k] = uint96(x);
        }
        while (i < len && (work == 0 || work + 2 * n <= ROLL_WORK)) {
            work += 2 * n + 1; // its tables read, and a first price written
            bytes32 f = _pending[i];
            if (_priceNew(f, c, vers, e) || p + 1 >= _announced[f] - 1 + PENDING_PERIODS) {
                if (_pricedAt[f] == 0) emit FamilyDropped(f);
                _announced[f] = 0;
                _pending[i] = _pending[len - 1];
                _pending.pop();
                --len;
            } else {
                ++i;
            }
        }
        r.cursor = uint64(i);
        if (i == len) r.phase = 5;
    }

    /// Prices waiting family `f` if enough counting tables price it (D19); returns whether it did.
    function _priceNew(bytes32 f, address[] memory c, uint256[] memory vers, uint256 e) internal returns (bool) {
        address[] memory by = new address[](c.length);
        uint256 m;
        uint256 others;
        for (uint256 k; k < c.length; ++k) {
            if (_tok[c[k]][f] >> 192 == vers[k]) {
                by[m++] = c[k];
                if (_famOf[c[k]] != f) ++others;
            }
        }
        if (m < MEDIAN_MIN_POSTERS || others < MEDIAN_MIN_POSTERS) return false;
        uint256[] memory vals = new uint256[](m);
        uint256[3] memory first;
        uint256[3] memory top = _top;
        for (uint256 j; j < 3; ++j) {
            for (uint256 k; k < m; ++k) {
                vals[k] = _word(_tok[by[k]][f], 2 - j);
            }
            uint256 v = _select(vals, (m - 1) / 2);
            uint256 cap = top[j] * PRICE_CAP_X;
            if (v > cap) v = cap;
            if (v > MAX_PRICE) v = MAX_PRICE;
            bytes32 u = _unit(f, j);
            _hist[u].push(Checkpoint(uint64(e), uint192(v)));
            _first[u] = v;
            first[j] = v;
        }
        _pricedAt[f] = e + 1;
        _priced.push(f);
        emit FamilyPriced(f, e, first);
        return true;
    }

    /// The k-th counting poster of the roll under way.
    function _poster(uint256 k) internal view returns (address) {
        return address(uint160(_rc[k] >> 96));
    }

    function _notRolling() internal view {
        if (_rolling.phase != 0) revert RollInProgress();
    }

    /// The k-th smallest of `a` (0-based), reordering it: quickselect with a three-way partition, so equal values
    /// (every validator posting the same list price) cost one pass.
    function _select(uint256[] memory a, uint256 k) internal pure returns (uint256 kth) {
        uint256 lo;
        uint256 hi = a.length; // [lo, hi)
        while (true) {
            uint256 pv = a[lo + (hi - lo) / 2];
            uint256 lt = lo;
            uint256 i = lo;
            uint256 gt = hi;
            while (i < gt) {
                uint256 x = a[i];
                if (x < pv) {
                    (a[i], a[lt]) = (a[lt], x);
                    ++lt;
                    ++i;
                } else if (x > pv) {
                    --gt;
                    (a[i], a[gt]) = (a[gt], x);
                } else {
                    ++i;
                }
            }
            if (k < lt) hi = lt;
            else if (k >= gt) lo = gt;
            else return pv;
        }
    }

    /// A counted seat's service fee: the epoch's fee times its family's factor; a scored family's raw factor is
    /// recorded for the next period's normaliser.
    function _service(uint256 fee, bytes32 family, Period storage per) internal returns (uint256) {
        (IFeesV3Scores.ScoreState s, uint256 score) = scores.familyScore(family);
        if (s == IFeesV3Scores.ScoreState.Neutral) return fee;
        if (s == IFeesV3Scores.ScoreState.Recovering) return fee * SCORE_FACTOR_MIN / WAD;
        uint256 raw = rawFactor(score);
        ++per.seats;
        per.rawSum += raw;
        uint256 f = raw * WAD / norm;
        if (f < SCORE_FACTOR_MIN) f = SCORE_FACTOR_MIN;
        if (f > SCORE_FACTOR_MAX) f = SCORE_FACTOR_MAX;
        return fee * f / WAD;
    }

    /// The deposit at epoch `e`'s prices: `judges` judges at the caps (every input token at the dearer of the
    /// uncached and cached prices), at the dearest family priced in that epoch, each with its storage and the service
    /// fee at SCORE_FACTOR_MAX; the CI runs at the profile's limits (one with CI_SINGLE_RUN); the gas allowance at the
    /// gas price cap. Rounded up.
    function _deposit(uint256 e, bytes32 repo_, uint256 judges) internal view returns (uint256) {
        uint256[4] memory sh = _sharedAt(e);
        Caps memory c = _caps;
        Profile memory p = profileOf(repo_);
        uint256 ai;
        for (uint256 i; i < _priced.length; ++i) {
            bytes32 f = _priced[i];
            if (_pricedAt[f] - 1 > e) continue;
            uint256[3] memory t = _tokensAt(f, e);
            uint256 inp = t[0] > t[1] ? t[0] : t[1];
            uint256 a = uint256(c.inputTokens) * inp + uint256(c.outputTokens) * t[2];
            if (a > ai) ai = a;
        }
        uint256 perJudge = _ceil(ai + uint256(c.storageMb) * sh[2]) + _fees[e] * SCORE_FACTOR_MAX / WAD;
        uint256 run = _ceil(_maxVcpu(p) * sh[0] + _maxGb(p) * sh[1]);
        uint256 gas = _ceil(uint256(c.gasAllowance) * c.maxGasPrice * sh[3] / 1e12);
        return judges * perJudge + (ciSingleRun ? 1 : judges) * run + gas;
    }

    function _maxVcpu(Profile memory p) internal pure returns (uint256) {
        return uint256(p.milliVcpus) * p.timeoutSeconds / 1000;
    }

    function _maxGb(Profile memory p) internal pure returns (uint256) {
        return uint256(p.memoryMb) * p.timeoutSeconds / 1024;
    }

    /// A report within the constitution's caps and the CI profile's limits (v2's).
    function _capped(Usage calldata u, Profile memory p) internal view returns (Usage memory c) {
        Caps memory k = _caps;
        c.input = u.input < k.inputTokens ? u.input : k.inputTokens;
        c.cached = u.cached < c.input ? u.cached : c.input;
        c.output = u.output < k.outputTokens ? u.output : k.outputTokens;
        c.vcpuSeconds = uint64(u.vcpuSeconds < _maxVcpu(p) ? u.vcpuSeconds : _maxVcpu(p));
        c.gbSeconds = uint64(u.gbSeconds < _maxGb(p) ? u.gbSeconds : _maxGb(p));
        c.storageMb = u.storageMb < k.storageMb ? u.storageMb : k.storageMb;
    }

    /// Every field's median over the counted judges' capped reports (v2's rule: the middle one of an odd count, the
    /// mean of the two middle ones rounded down for an even count; k = 1 is its own median).
    function _median(Report[] calldata rs, Profile memory p) internal view returns (Usage memory m) {
        uint256 n = rs.length;
        Usage[] memory us = new Usage[](n);
        for (uint256 k; k < n; ++k) {
            us[k] = _capped(rs[k].usage, p);
        }
        uint256[] memory xs = new uint256[](n);
        for (uint256 field; field < 6; ++field) {
            for (uint256 k; k < n; ++k) {
                xs[k] = _field(us[k], field);
            }
            uint256 v = _mid(xs);
            if (field == 0) m.input = uint64(v);
            else if (field == 1) m.cached = uint64(v);
            else if (field == 2) m.output = uint64(v);
            else if (field == 3) m.vcpuSeconds = uint64(v);
            else if (field == 4) m.gbSeconds = uint64(v);
            else m.storageMb = uint64(v);
        }
        if (m.cached > m.input) m.cached = m.input;
    }

    function _field(Usage memory u, uint256 i) internal pure returns (uint256) {
        if (i == 0) return u.input;
        if (i == 1) return u.cached;
        if (i == 2) return u.output;
        if (i == 3) return u.vcpuSeconds;
        if (i == 4) return u.gbSeconds;
        return u.storageMb;
    }

    /// The median of at most K_MAX values.
    function _mid(uint256[] memory xs) internal pure returns (uint256) {
        uint256 n = xs.length;
        for (uint256 i = 1; i < n; ++i) {
            for (uint256 j = i; j > 0 && xs[j - 1] > xs[j]; --j) {
                (xs[j - 1], xs[j]) = (xs[j], xs[j - 1]);
            }
        }
        return n % 2 == 1 ? xs[n / 2] : (xs[n / 2 - 1] + xs[n / 2]) / 2;
    }

    function _tokensCost(uint256[3] memory t, Usage memory u) internal pure returns (uint256) {
        return ((uint256(u.input) - u.cached) * t[0] + uint256(u.cached) * t[1] + uint256(u.output) * t[2]) / M;
    }

    function _sandboxCost(uint256[4] memory s, Usage memory u) internal pure returns (uint256) {
        return (uint256(u.vcpuSeconds) * s[0] + uint256(u.gbSeconds) * s[1]) / M;
    }

    function _storageCost(uint256[4] memory s, Usage memory u) internal pure returns (uint256) {
        return uint256(u.storageMb) * s[2] / M;
    }

    function _gasCost(uint256[4] memory s, uint256 gasUsed) internal view returns (uint256) {
        Caps memory c = _caps;
        uint256 g = gasUsed + c.gasOverhead;
        if (g > c.gasAllowance) g = c.gasAllowance;
        uint256 price = tx.gasprice < c.maxGasPrice ? tx.gasprice : c.maxGasPrice;
        return g * price * s[3] / 1e18;
    }

    function _ceil(uint256 x) internal pure returns (uint256) {
        return (x + M - 1) / M;
    }
}
