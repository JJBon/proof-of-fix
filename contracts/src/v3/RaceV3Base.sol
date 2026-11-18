// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Baskets} from "../Baskets.sol";
import {Heads} from "../v2/Heads.sol";
import {IFeesV3} from "./IFeesV3.sol";
import {IValidators} from "./IValidators.sol";
import {Panels} from "./Panels.sol";
import {PoolV3} from "./PoolV3.sol";
import {Status, Kind} from "./PanelsBase.sol";

/// RaceV3's state, types and internals (proof-of-fix#138, task 3.5 of #132). RaceV3 and its companion RaceV3Annex both
/// inherit it, so they share one storage layout: RaceV3 runs its rarely called actions in its own storage by
/// delegating to RaceV3Annex, whose address RaceV3 fixes at its deployment (no key, no upgrade), as v2 did.
/// Everything here is described on RaceV3.
abstract contract RaceV3Base is Baskets {
    /// Fixed at deployment. Amounts are in micro-coins (1e-6) of the version's fee coin; shares in bps; days.
    struct Config {
        address infrastructure; // the registration, attempt, evaluation and appeal fees
        address insurance; // a junk issue's stake
        uint256 registrationFee;
        uint256 issueStake;
        uint256 attemptFee;
        uint256 evaluationFee; // a late submission's, and a duplicate win's
        uint256 appealFee;
        uint256 challengeStake; // a challenge's published stake, beside its panel's worst-case cost
        uint256 startPriceBps;
        uint256 riseBpsPerDay;
        uint256 finderFeeBps; // the reporter's fee, of the price
        uint256 idleDays; // an open bounty with no submission waiting for this long sunsets (D11)
        uint256 resultDays; // a submission no panel was seated for in this long can be timed out by anyone
        uint256 mergeDays; // a winning fix must be claimed (merged) within this, or the bounty reopens
        uint256 releaseEveryDays; // instalments are paid at each release after finality
        uint256 instalments;
    }

    enum State {
        None,
        Open,
        Won, // a submission's counted verdict passed; waiting for its claim (the merge)
        Merged, // claimed; paid in instalments from its verdict's finality
        Paid,
        Refunded,
        Unsolved
    }

    enum IssueState {
        None,
        Posted, // registered; its registration check runs, then its bounty is open
        Rewarded,
        Returned,
        Forfeited
    }

    enum Outcome {
        None,
        Pass,
        Fail,
        Duplicate, // a passing fix already paid on a bounty (D10), found at its claim
        Withdrawn, // the solver withdrew it before a panel was seated
        TimedOut // no panel seated within resultDays
    }

    struct Issue {
        bytes32 repo; // a repository of the head registry, or 0 outside it (S8)
        address reporter;
        uint256 registration;
        uint256 stake;
        uint256 bounty;
        uint256 check; // its registration check (a submission id)
        IssueState state;
        bool hidden; // hidden tests or a private repository: every check is judged at level A or B (Panels.openHidden)
    }

    struct Bounty {
        uint256 issue;
        State state;
        uint256 offerFrom;
        bool locked;
        uint256 lockBps;
        uint256 idleSince;
        uint256 attempting;
        uint256 next; // the first submission (index into its list) without a decision
        uint256 winner; // the winning submission, while Won or Merged
        uint256 mergeBy;
        uint256 epoch; // awards so far: each claim starts one, a reversal closes it
        uint256 pledges; // distinct funders so far, in the order they first pledged
    }

    /// A check judged by Panels under the same id: a fix to a bounty, or an issue's registration check (`issue` set,
    /// `bounty` 0).
    struct Submission {
        uint256 bounty;
        uint256 issue;
        uint256 day; // committed on
        address solver; // the solver, or the reporter of a registration check
        bytes32 commitment;
        uint256 deposit; // what's left of its check deposit, in the coin's units
        uint256 charged; // what its checks were paid from the deposit
        uint256 judged; // the bounty Panels judges it at, in micro-coins: the most its award can pay
        uint256 pledges; // the bounty's funders at its opening: its parties among the funders, frozen
        Outcome outcome;
        bool appealed;
        bool paid; // its counted judges were paid
        bool done; // its deposit's rest returned
        bytes32 fix; // revealed at its claim
    }

    struct Award {
        address winner;
        bytes32 fix;
        uint256 sub; // the winning submission: its verdict's finality starts the instalments
        bool closed; // a reversal closed it
        uint256 earned; // instalments earned when it closed
    }

    /// A challenge the race filed (Panels allows one open at a time): its stake and its panel's worst-case cost are
    /// held here until its panel's verdict.
    struct Challenge {
        address challenger;
        uint256 stake; // config.challengeStake, in units
        uint256 cover; // FeesV3.depositFor(id, repo, K_MAX), in units
        bool wasPass; // the verdict challenged
        uint256 floor; // Panels' panel count at the filing: its panel's id is above it
    }

    uint256 internal constant K_MAX = 7;
    /// The bounty a registration check is judged at (micro-coins): the lowest tier, as Panels' ADRs.
    uint256 internal constant CHECK_BOUNTY = 1;
    /// The judges' usage reports: a panel's pay waits for every seat's, or this long after its reveal deadline.
    uint256 internal constant REPORT_WINDOW = 1 days;
    bytes32 internal constant USAGE_TAG = keccak256("proof-of-fix v3 usage");

    Config internal config;
    Panels internal immutable panels;
    IFeesV3 internal immutable fees;
    PoolV3 internal immutable pool;
    IValidators internal immutable registry;
    Heads internal heads; // storage, not immutable: the annex reads its race's
    address internal immutable coin;
    uint256 internal immutable start;

    Issue[] internal _issues;
    Bounty[] internal _bounties;
    Submission[] internal _submissions;
    mapping(uint256 bounty => uint256[]) internal _bySubmission;
    mapping(uint256 bounty => mapping(uint256 epoch => Award)) internal awards;
    mapping(uint256 bounty => mapping(address coin => uint256)) internal _snapped; // awards whose price is stored
    mapping(uint256 bounty => mapping(address coin => mapping(uint256 epoch => uint256))) internal prices;
    mapping(uint256 bounty => mapping(address coin => mapping(uint256 epoch => uint256))) internal _instalmentsPaid;
    mapping(uint256 bounty => mapping(address coin => bool)) internal settled;
    mapping(uint256 bounty => mapping(address solver => uint256)) internal attemptedOn; // day + 1, 0 = none
    mapping(uint256 bounty => mapping(address funder => uint256)) internal pledgeOrder; // 1 = the first funder
    mapping(bytes32 fix => bool) internal paidFix;
    mapping(uint256 id => Challenge) internal challenges;
    mapping(uint256 pid => mapping(uint256 slot => IFeesV3.Usage)) internal _usage;
    mapping(uint256 pid => mapping(uint256 slot => address)) internal reportedBy;
    mapping(uint256 pid => bool) internal panelPaid; // an audit or challenge panel
    mapping(uint256 pid => uint256) internal shadowsPaid; // a shadow panel: one bit per seat

    event Registered(uint256 indexed issue, address indexed reporter, uint256 check);
    event IssueClosed(uint256 indexed issue, IssueState state);
    event BountyOpened(uint256 indexed bounty, uint256 indexed issue);
    event StateChanged(uint256 indexed bounty, State state);
    event Locked(uint256 indexed bounty, uint256 bps);
    event Attempted(uint256 indexed bounty, address indexed solver);
    event Committed(uint256 indexed bounty, uint256 indexed submission, address indexed solver);
    event TooLate(uint256 indexed bounty, address indexed solver);
    event Reported(uint256 indexed pid, uint256 slot, address indexed key, bytes32 receipt);
    event Decided(uint256 indexed submission, Outcome outcome);
    event Awarded(uint256 indexed bounty, uint256 indexed epoch, address winner);
    event ClawedBack(uint256 indexed bounty, uint256 indexed epoch, uint256 earned);
    event ChallengeFiled(uint256 indexed submission, address indexed challenger);
    event ChallengeSettled(uint256 indexed submission, uint256 indexed pid, bool upheld);
    event PanelPaid(uint256 indexed submission, uint256 indexed pid, uint256 fromDeposit, uint256 fromPool);

    error BadParams();
    error WrongState(uint256 bounty, State state);
    error NotYet();
    error Refused();

    constructor(
        Config memory config_,
        uint256 bountyCap_,
        uint256 totalCap_,
        Panels panels_,
        PoolV3 pool_,
        Heads heads_,
        uint256 start_
    ) Baskets(bountyCap_, totalCap_) {
        if (config_.releaseEveryDays == 0 || config_.instalments == 0 || start_ > block.timestamp) revert BadParams();
        if (address(panels_).code.length == 0) revert BadParams();
        IFeesV3 fees_ = IFeesV3(address(panels_.fees()));
        address coin_ = panels_.coin();
        if (fees_.coin() != coin_ || panels_.pool() != address(pool_) || !pool_.isFeeCoin(coin_)) revert BadParams();
        _see(coin_);
        // Panels judges bounties up to its BOUNTY_MAX: a pot never holds more (the cap counts whole coins)
        if (bountyCap_ == 0 || bountyCap_ * 1e6 > panels_.BOUNTY_MAX()) revert BadParams();
        config = config_;
        panels = panels_;
        fees = fees_;
        pool = pool_;
        registry = IValidators(address(panels_.validators()));
        heads = heads_;
        coin = coin_;
        start = start_ == 0 ? block.timestamp : start_;
        _issues.push(); // ids start at 1
        _bounties.push();
        _submissions.push();
    }

    // ---------- views ----------

    /// What a companion must share with its race: the same Panels, pool, start and caps.
    function _fingerprint() internal view returns (bytes32) {
        return keccak256(abi.encode(panels, pool, start, bountyCap, totalCap));
    }

    function _day() internal view returns (uint256) {
        return (block.timestamp - start) / 1 days;
    }

    /// The rising price's share, in bps, on offer now (or locked).
    function _offerBps(uint256 b) internal view returns (uint256) {
        Bounty storage bt = _bounties[b];
        if (bt.locked) return bt.lockBps;
        uint256 bps = config.startPriceBps + config.riseBpsPerDay * (_day() - bt.offerFrom);
        return bps < BPS ? bps : BPS;
    }

    /// pof's price_cap: what the pot holds, less the registration (refunded from it if solved), with room for the
    /// finder's fee.
    function _capOf(uint256 b, address c, uint256 h) internal view returns (uint256) {
        Issue storage i = _issues[_bounties[b].issue];
        if (c == coin) h = h > i.registration ? h - i.registration : 0;
        return h * BPS / (BPS + config.finderFeeBps);
    }

    /// The price on offer now: the offer's share of the cap.
    function _lockedPrice(uint256 b, address c) internal view returns (uint256) {
        return _capOf(b, c, held(b, c)) * _offerBps(b) / BPS;
    }

    /// An award's price: the locked share of the cap at the win, never above the bounty its panel judged.
    function _priceOf(uint256 b, address c, uint256 epoch) internal view returns (uint256) {
        if (epoch <= _snapped[b][c]) return prices[b][c][epoch];
        return _priceNow(b, c, epoch);
    }

    /// What earlier awards (before `epoch`) earned and haven't been paid.
    function _unpaidBefore(uint256 b, address c, uint256 epoch) internal view returns (uint256 total) {
        for (uint256 e = 1; e < epoch; ++e) {
            total += _instalmentsTotal(_priceOf(b, c, e), _earned(b, e)) - _instalmentsPaid[b][c][e];
        }
    }

    function _priceNow(uint256 b, address c, uint256 epoch) internal view returns (uint256 p) {
        p = _capOf(b, c, held(b, c) - _unpaidBefore(b, c, epoch)) * _bounties[b].lockBps / BPS;
        uint256 judged = _units(_submissions[awards[b][epoch].sub].judged);
        if (p > judged) p = judged;
    }

    /// Instalments earned by an award: one at each release after its verdict's finality, up to all of them. Nothing
    /// before Panels' finality, or if the final verdict isn't a pass.
    function _earned(uint256 b, uint256 epoch) internal view returns (uint256) {
        Award storage a = awards[b][epoch];
        if (a.closed) return a.earned;
        if (a.winner == address(0)) return 0;
        (Status st, bool pass, uint256 finalAt) = _verdict(a.sub);
        if (st != Status.Final || !pass) return 0;
        uint256 rel = config.releaseEveryDays;
        uint256 n = _day() / rel - ((finalAt - start) / 1 days) / rel;
        return n < config.instalments ? n : config.instalments;
    }

    function _instalmentsTotal(uint256 price, uint256 k) internal view returns (uint256) {
        return k >= config.instalments ? price : price / config.instalments * k;
    }

    /// Panels' status, verdict and finality time for a check.
    function _verdict(uint256 id) internal view returns (Status, bool, uint256) {
        bytes memory s = _sub(id);
        return (Status(_w(s, S_STATUS)), _w(s, S_PASS) != 0, _w(s, S_FINAL_AT));
    }

    // Panels' and the registry's records are static structs: their views return one ABI word a field, in order. The
    // race reads the few words it needs (test_theRaceReadsPanelsRecordsRight checks each against the typed view).
    uint256 internal constant S_STATUS = 3; // Panels' Submission
    uint256 internal constant S_K = 5;
    uint256 internal constant S_PASS = 7;
    uint256 internal constant S_FINAL_AT = 15;
    uint256 internal constant S_PID = 16;
    uint256 internal constant P_ID = 0; // Panels' Panel
    uint256 internal constant P_REVEAL_BY = 3;
    uint256 internal constant P_K = 5;
    uint256 internal constant P_SEATS = 6;
    uint256 internal constant P_PASSES = 9;
    uint256 internal constant P_COUNTED = 11;
    uint256 internal constant P_KIND = 12;
    uint256 internal constant X_KEY = 0; // Panels' Seat
    uint256 internal constant X_REVEALED = 3;
    uint256 internal constant X_RECEIPTED = 4;
    uint256 internal constant X_MASK = 6;
    uint256 internal constant X_RECEIPT = 8;
    uint256 internal constant V_OPERATOR = 5; // the registry's Validator
    uint256 internal constant V_FAMILY = 12;

    function _view(address t, bytes memory data) internal view returns (bytes memory r) {
        bool ok;
        (ok, r) = t.staticcall(data);
        if (!ok) {
            assembly ("memory-safe") {
                revert(add(r, 32), mload(r))
            }
        }
    }

    function _w(bytes memory r, uint256 i) internal pure returns (uint256 x) {
        assembly ("memory-safe") {
            x := mload(add(r, mul(add(i, 1), 32)))
        }
    }

    function _sub(uint256 id) internal view returns (bytes memory) {
        return _view(address(panels), abi.encodeCall(Panels.submission, (id)));
    }

    function _pan(uint256 pid) internal view returns (bytes memory) {
        return _view(address(panels), abi.encodeCall(Panels.panel, (pid)));
    }

    function _seat(uint256 pid, uint256 slot) internal view returns (bytes memory) {
        return _view(address(panels), abi.encodeCall(Panels.seat, (pid, slot)));
    }

    function _val(address key) internal view returns (bytes memory) {
        return _view(address(registry), abi.encodeCall(IValidators.validator, (key)));
    }

    // ---------- internals ----------

    function _settleForRefund(uint256 b, address c) internal override returns (bool) {
        return _settle(b, c);
    }

    function _settle(uint256 b, address c) internal returns (bool) {
        Bounty storage bt = _bounties[b];
        if (bt.state == State.Merged && _earned(b, bt.epoch) >= config.instalments) {
            _setState(b, State.Paid);
            Issue storage i = _issues[bt.issue];
            if (i.state == IssueState.Posted) _closeIssue(bt.issue, IssueState.Rewarded, i.reporter);
        }
        if (bt.state != State.Paid && bt.state != State.Refunded && bt.state != State.Unsolved) return false;
        if (settled[b][c]) return true;
        settled[b][c] = true;
        for (uint256 e = 1; e <= bt.epoch; ++e) {
            _payInstalments(b, c, e);
        }
        if (bt.state == State.Paid && c == coin) {
            Issue storage i = _issues[bt.issue];
            uint256 fee = _priceOf(b, c, bt.epoch) * config.finderFeeBps / BPS;
            uint256 h = held(b, c);
            if (fee > h) fee = h;
            if (fee != 0) _pay(b, c, i.reporter, fee);
            uint256 refund = i.registration < held(b, c) ? i.registration : held(b, c);
            if (refund != 0) _pay(b, c, i.reporter, refund);
            // S6: the winner's checks for its fix, from what the pot holds once the award is paid
            Submission storage w = _submissions[bt.winner];
            uint256 back = w.charged < held(b, c) ? w.charged : held(b, c);
            if (back != 0) _pay(b, c, w.solver, back);
        }
        return true;
    }

    function _payInstalments(uint256 b, address c, uint256 epoch) internal {
        Award storage a = awards[b][epoch];
        if (a.winner == address(0)) revert Refused();
        _touch(b, c);
        uint256 due = _instalmentsTotal(_priceOf(b, c, epoch), _earned(b, epoch)) - _instalmentsPaid[b][c][epoch];
        if (due == 0) return;
        _instalmentsPaid[b][c][epoch] += due;
        _pay(b, c, a.winner, due);
    }

    /// Before a pot changes: snapshot every award's price not yet stored.
    function _touch(uint256 b, address c) internal {
        uint256 epochs = _bounties[b].epoch;
        uint256 e = _snapped[b][c];
        while (e < epochs) {
            ++e;
            prices[b][c][e] = _priceNow(b, c, e);
            _snapped[b][c] = e;
        }
    }

    function _lock(uint256 b) internal {
        Bounty storage bt = _bounties[b];
        if (bt.locked) return;
        bt.lockBps = _offerBps(b);
        bt.locked = true;
        emit Locked(b, bt.lockBps);
    }

    function _repoOf(Submission storage s) internal view returns (bytes32) {
        return _issues[s.issue != 0 ? s.issue : _bounties[s.bounty].issue].repo;
    }

    /// A check for Panels: its deposit (FeesV3's worst case for K_MAX judges, k being unknown until the draw) is held,
    /// FeesV3 fixes its prices, and Panels opens it at `judged` micro-coins (TEE judges only for a hidden issue). Its
    /// parties among the funders are those who pledged before it (`pledges`).
    function _newCheck(uint256 b, uint256 issueId, address solver, bytes32 commitment, uint256 judged)
        internal
        returns (uint256 id)
    {
        id = _submissions.length;
        _submissions.push();
        Submission storage s = _submissions[id];
        s.bounty = b;
        s.issue = issueId;
        s.day = _day();
        s.solver = solver;
        s.commitment = commitment;
        s.judged = judged;
        if (b != 0) s.pledges = _bounties[b].pledges;
        uint256 deposit = _units(fees.maxDeposit(_repoOf(s), K_MAX));
        if (deposit != 0) _hold(coin, solver, deposit);
        s.deposit = deposit;
        fees.open(id);
        if (_issues[issueId != 0 ? issueId : _bounties[b].issue].hidden) panels.openHidden(id, commitment, judged);
        else panels.open(id, commitment, judged);
    }

    function _submit(uint256 b, address solver, bytes32 commitment) internal returns (uint256 id) {
        uint256 judged = _lockedPrice(b, coin) * 1e6 / unit[coin];
        id = _newCheck(b, 0, solver, commitment, judged == 0 ? 1 : judged);
        _bySubmission[b].push(id);
        emit Committed(b, id, solver);
    }

    /// D4: walk the queue in commitment order; the first pass wins once everything before it is decided.
    function _decide(uint256 b) internal {
        Bounty storage bt = _bounties[b];
        uint256[] storage list = _bySubmission[b];
        while (bt.state == State.Open && bt.next < list.length) {
            Outcome o = _submissions[list[bt.next]].outcome;
            if (o == Outcome.None) return;
            if (o == Outcome.Pass) {
                _win(b, list[bt.next]);
                bt.next += 1;
                return;
            }
            bt.next += 1;
        }
    }

    function _win(uint256 b, uint256 id) internal {
        Bounty storage bt = _bounties[b];
        bt.winner = id;
        bt.mergeBy = _day() + config.mergeDays;
        _setState(b, State.Won);
    }

    function _reopen(uint256 b) internal {
        _bounties[b].idleSince = _day();
        _setState(b, State.Open);
        _decide(b); // a pass already waiting behind the old winner wins now
    }

    function _decided(uint256 id, Outcome o) internal {
        Submission storage s = _submissions[id];
        s.outcome = o;
        emit Decided(id, o);
        uint256 b = s.bounty;
        if (b == 0) return;
        // A checked fix that failed is progress, and the bounty is open to everyone again: its idle clock restarts.
        if (o == Outcome.Fail && _bounties[b].state == State.Open) _bounties[b].idleSince = _day();
        _decide(b);
    }

    /// A reported seat's usage, as FeesV3 reads it: paid to the validator's operator, at its family's prices.
    function _reports(uint256 pid, address[] memory keys) internal view returns (IFeesV3.Report[] memory rs) {
        uint256 n;
        rs = new IFeesV3.Report[](keys.length);
        for (uint256 i; i < keys.length; ++i) {
            address key = keys[i];
            if (key == address(0) || reportedBy[pid][i] != key) continue;
            bytes memory v = _val(key);
            rs[n++] = IFeesV3.Report(address(uint160(_w(v, V_OPERATOR))), bytes32(_w(v, V_FAMILY)), _usage[pid][i]);
        }
        assembly ("memory-safe") {
            mstore(rs, n)
        }
    }

    /// The seated keys of a panel, its empty seats left out (a counted panel keeps a seat empty when its judge missed
    /// its reveal after a majority had revealed, 3.4's option 2).
    function _seated(address[] memory keys) internal pure returns (address[] memory) {
        uint256 n;
        for (uint256 i; i < keys.length; ++i) {
            if (keys[i] != address(0)) keys[n++] = keys[i];
        }
        assembly ("memory-safe") {
            mstore(keys, n)
        }
        return keys;
    }

    /// A panel's reports are in: every seat reported, or REPORT_WINDOW has passed since its reveal deadline.
    function _reportsDue(uint256 pid, uint256 revealBy, address[] memory keys) internal view {
        if (block.timestamp > revealBy + REPORT_WINDOW) return;
        for (uint256 i; i < keys.length; ++i) {
            if (reportedBy[pid][i] != keys[i]) revert NotYet();
        }
    }

    /// Pays `micro` to `to` from the check's deposit, and what it no longer covers from the sponsors' pool.
    function _payExtra(Submission storage s, address to, uint256 micro) internal returns (uint256 a, uint256 rest) {
        uint256 amount = _units(micro);
        a = s.done ? 0 : amount < s.deposit ? amount : s.deposit;
        if (a != 0) {
            s.deposit -= a;
            s.charged += a;
            _release(coin, a, to);
        }
        if (amount > a) rest = pool.spend(coin, to, amount - a);
    }

    function _closeIssue(uint256 id, IssueState state, address to) internal {
        Issue storage i = _issues[id];
        i.state = state;
        _release(coin, i.stake, to);
        emit IssueClosed(id, state);
    }

    function _setState(uint256 b, State st) internal {
        _bounties[b].state = st;
        emit StateChanged(b, st);
    }

    function _stopAttempt(uint256 b, address solver) internal {
        if (attemptedOn[b][solver] == 0) return;
        attemptedOn[b][solver] = 0;
        _bounties[b].attempting -= 1;
    }

    /// Micro-coins to the fee coin's smallest units.
    function _units(uint256 micro) internal view returns (uint256) {
        return micro * unit[coin] / 1e6;
    }
}
