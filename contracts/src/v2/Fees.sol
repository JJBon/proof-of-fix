// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {MessageHashUtils} from "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";
import {IFees} from "./IFees.sol";
import {RaceV2Base} from "./RaceV2Base.sol";
import {Verdicts} from "./Verdicts.sol";

/// What the meter reads from its race (RaceV2's views).
interface IRaceViews {
    function submission(uint256 id) external view returns (RaceV2Base.Submission memory);
    function bounty(uint256 id) external view returns (RaceV2Base.Bounty memory);
    function issue(uint256 id) external view returns (RaceV2Base.Issue memory);
}

/// Check fees for v2 (proof-of-fix#85, task 5.7, design S15, constitution Article 5): a check is paid like a taxi fare
/// with tolls. Its costs are passed through at public unit prices, with no profit in them, plus one SERVICE_FEE per
/// counted check, the same for every seat. No seat sets a fee of its own.
///
///   a counted judge's pay = the median of the counted judges' usage × its own family's token prices
///                         + the median sandbox usage × the sandbox's prices (its own test run; once, with CI_SINGLE_RUN)
///                         + the median storage × the storage price
///                         + SERVICE_FEE
///   the relayer's pay      = the gas measured in the result's call plus RELAYER_GAS_OVERHEAD, at the transaction's gas
///                           price (at most MAX_GAS_PRICE), in the fee coin at the table's ETH price, within the
///                           deposit's gas allowance
///
/// The price table holds unit prices, every one in micro-coins per million units: per model family, input, cached and
/// output tokens; the sandbox's vCPU-seconds and GB-seconds; storage MB; then the ETH price (micro-coins per ETH, to
/// repay gas in the fee coin) and SERVICE_FEE (micro-coins per counted check). Every entry has a genesis value; no
/// update takes one above PRICE_CAP_MULTIPLE × its genesis value, nor SERVICE_FEE above SERVICE_FEE_CAP (the
/// constitution's, changed only by a new version until ADRs reach the chain, 5.10).
///
/// Usage (S14): each drawn judge signs what its check measured inside its attested node (the provider's token counts,
/// the sandbox's seconds, the stored MB) with its seat's key, bound to the submission and its receipt; anyone relays
/// it (`report`) before the result. Until receipts reach the chain (5.6) the usage is taken as signed; a judge that
/// doesn't report isn't paid. Every report is capped by the constitution's caps and the repository's CI profile
/// before the median, so one padder changes nothing.
///
/// The deposit (S15): the drawn judges' worst case under the caps, at the dearest family and the dearer of the prices
/// in force and pending, plus SERVICE_FEE each, the CI runs at the profile's limits, plus the gas allowance. The race
/// takes it at the commit, pays what `settle` returns, and refunds the rest.
///
/// Price updates (S15, #100 comment 4756): the constitution tier (5 of 7, Verdicts.authorizeAll) signs a new table
/// citing the public price lists it follows (the evidence's hash); every entry within PRICE_STEP_MAX_BPS of its current
/// value and under its cap; one pending at a time; in force PRICE_DELAY after it was published.
///   TODO(5.8) the procedure's step 4: a staked challenge during the notice, decided by the seats that didn't sign,
///   cancelling the update and paying the challenger from the proposers' bonds (PRICE_CHALLENGE_SLASH_BPS). It needs
///   the bonds; until then the notice is public and the update can't be stopped.
///
/// Keyless: no owner, no admin. The CI profiles, the caps and CI_SINGLE_RUN are fixed at deployment.
contract Fees is IFees {
    uint256 public constant BPS = 10_000;
    uint256 public constant PRICE_STEP_MAX_BPS = 2_500; // ±25 % per update (S15)
    uint256 public constant PRICE_DELAY = 7 days; // S15
    uint256 public constant PRICE_CAP_MULTIPLE = 2; // owner, 2026-11-01 (#102): no entry above 2× its genesis value
    uint256 public constant SERVICE_FEE_CAP = 250_000; // $0.25 per counted check (Article 5.11)
    uint256 internal constant M = 1e6; // prices are per million units

    /// What one judge's check used, as its attested node measured it (S14), and its receipt's hash.
    struct Usage {
        bytes32 receipt;
        uint64 input; // tokens, cached ones included
        uint64 cached;
        uint64 output;
        uint64 vcpuSeconds;
        uint64 gbSeconds;
        uint64 storageMb;
    }

    /// A repository's CI profile (S15): the test image, the CPU (thousandths of a vCPU), the memory and the timeout.
    struct Profile {
        bytes32 image;
        uint32 milliVcpus;
        uint32 memoryMb;
        uint32 timeoutSeconds;
    }

    /// The constitution's per-check caps and the relayer's gas terms (S15).
    struct Caps {
        uint64 inputTokens;
        uint64 outputTokens;
        uint64 storageMb;
        uint64 gasAllowance; // gas units a result's relay may be repaid
        uint64 gasOverhead; // RELAYER_GAS_OVERHEAD: what the call can't measure (calldata, the transaction's base)
        uint64 maxGasPrice; // wei: the deposit's gas price, and the most a repayment counts
    }

    struct Genesis {
        address coin;
        bytes32[] families;
        uint256[] prices; // 3 per family (input, cached, output), then vCPU-s, GB-s, storage MB, ETH, SERVICE_FEE
        Caps caps;
        bytes32[] repos;
        Profile[] profiles;
        Profile defaultProfile; // a repository without its own, and a project outside the registry
        bool ciSingleRun;
    }

    /// A counted judge's report: who's paid (its seat's first disclosed operator account, or its key), its family's
    /// index in the table, and its usage.
    struct Report {
        address judge;
        address payee;
        uint256 family;
        Usage usage;
    }

    struct Update {
        uint256[] prices;
        bytes32 evidence;
        uint64 effectiveAt; // 0: none pending
    }

    bytes32 internal constant DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    bytes32 public constant USAGE_TYPEHASH = keccak256(
        "Usage(uint256 submission,bytes32 receipt,uint64 input,uint64 cached,uint64 output,uint64 vcpuSeconds,uint64 gbSeconds,uint64 storageMb)"
    );
    bytes32 public constant PRICE_UPDATE_TYPEHASH =
        keccak256("PriceUpdate(bytes32 prices,bytes32 evidence,bytes32 nonce)");

    Verdicts public immutable verdicts;
    address public immutable coin;
    bool public immutable ciSingleRun;
    address public race;
    Caps internal _caps;
    bytes32[] internal _families;
    uint256[] internal _prices;
    uint256[] public genesis;
    Update internal _pending;
    mapping(bytes32 repo => Profile) internal _profiles;
    Profile internal _defaultProfile;
    mapping(uint256 submission => Report[]) internal _reports;
    mapping(uint256 submission => bool) public settled;
    bytes32 internal immutable _domain;

    event Bound(address indexed race);
    event Reported(uint256 indexed submission, address indexed judge, address payee, bytes32 receipt);
    event Charged(uint256 indexed submission, uint256 judges, uint256 total);
    event PriceUpdatePublished(bytes32 indexed prices, bytes32 evidence, uint256 effectiveAt);
    event PriceUpdateApplied(bytes32 indexed prices);

    error BadParams();
    error AlreadyBound();
    error NotRace();
    error Undecided();
    error NotDrawn();
    error AlreadyReported();
    error AlreadySettled();
    error OutOfBounds(uint256 entry);
    error AlreadyPending();
    error NothingPending();
    error TooEarly();

    constructor(Verdicts verdicts_, Genesis memory g) {
        uint256 f = g.families.length;
        if (address(verdicts_).code.length == 0 || g.coin == address(0) || f == 0) revert BadParams();
        if (g.prices.length != 3 * f + 5 || g.repos.length != g.profiles.length) revert BadParams();
        if (g.prices[3 * f + 4] > SERVICE_FEE_CAP || g.defaultProfile.timeoutSeconds == 0) revert BadParams();
        for (uint256 i; i < f; ++i) {
            for (uint256 j; j < i; ++j) {
                if (g.families[i] == g.families[j]) revert BadParams();
            }
        }
        // every seat's family is priced (a seat's family is fixed at genesis, vacant or not: S13)
        uint256 n = verdicts_.seatCount();
        for (uint256 s; s < n; ++s) {
            _familyIndex(g.families, verdicts_.seat(s).family);
        }
        for (uint256 r; r < g.repos.length; ++r) {
            if (g.profiles[r].timeoutSeconds == 0) revert BadParams();
            _profiles[g.repos[r]] = g.profiles[r];
        }
        verdicts = verdicts_;
        coin = g.coin;
        ciSingleRun = g.ciSingleRun;
        _caps = g.caps;
        _families = g.families;
        _prices = g.prices;
        genesis = g.prices;
        _defaultProfile = g.defaultProfile;
        _domain = keccak256(
            abi.encode(DOMAIN_TYPEHASH, keccak256("proof-of-fix Fees"), keccak256("2"), block.chainid, address(this))
        );
    }

    // ---------- the race ----------

    /// The race binds the meter, once (RaceV2's constructor): from then on only it settles.
    function bind() external {
        if (race != address(0)) revert AlreadyBound();
        race = msg.sender;
        emit Bound(msg.sender);
    }

    function settle(uint256 id, address relayer, uint256 gasUsed)
        external
        returns (address[] memory to, uint256[] memory micro)
    {
        if (msg.sender != race) revert NotRace();
        if (settled[id]) revert AlreadySettled();
        settled[id] = true;
        Report[] storage rs = _reports[id];
        uint256 n = rs.length;
        to = new address[](n + 1);
        micro = new uint256[](n + 1);
        uint256 total;
        if (n != 0) {
            Profile memory p = profileOf(_repoOf(IRaceViews(race).submission(id).bounty));
            Usage memory mid = _median(rs, p);
            uint256 shared = _storageCost(mid) + _price(_base() + 4); // storage and SERVICE_FEE, every judge
            uint256 run = _sandboxCost(mid);
            bool single = ciSingleRun;
            bool ran;
            for (uint256 k; k < n; ++k) {
                Report storage r = rs[k];
                uint256 pay = _tokensCost(r.family, mid) + shared;
                if (!single) {
                    pay += run;
                } else if (!ran && r.usage.vcpuSeconds != 0) {
                    pay += _sandboxCost(_capped(r.usage, p)); // the one attested run, at its own measurement
                    ran = true;
                }
                to[k] = r.payee;
                micro[k] = pay;
                total += pay;
            }
        }
        to[n] = relayer;
        micro[n] = _gasCost(gasUsed);
        total += micro[n];
        emit Charged(id, n, total);
    }

    /// Fees answers for no one's party (Verdicts.authorizeAll asks its consumer): a price update has no subject.
    function isParty(uint256, uint256, address) external pure returns (bool) {
        return false;
    }

    // ---------- anyone ----------

    /// Relays a drawn judge's usage for a submission still waiting for its result (S14, S15). The signer must be one
    /// of the issue tier's judges Verdicts draws with the submission's seed, once per submission.
    function report(uint256 id, Usage calldata u, bytes calldata sig) external {
        if (settled[id]) revert AlreadySettled();
        RaceV2Base.Submission memory s = IRaceViews(race).submission(id);
        if (s.solver == address(0) || s.outcome != RaceV2Base.Outcome.None) revert Undecided();
        address judge = ECDSA.recover(usageDigest(id, u), sig);
        (address[] memory judges,) = verdicts.drawn(s.seed, s.bounty, id, race);
        bool drawn;
        for (uint256 i; i < judges.length; ++i) {
            if (judges[i] == judge) drawn = true;
        }
        if (!drawn) revert NotDrawn();
        Report[] storage rs = _reports[id];
        for (uint256 k; k < rs.length; ++k) {
            if (rs[k].judge == judge) revert AlreadyReported();
        }
        (address payee, uint256 family) = _seatOf(judge);
        rs.push(Report(judge, payee, family, u));
        emit Reported(id, judge, payee, u.receipt);
    }

    /// The constitution tier publishes a new price table (S15): 5 of 7 seats, citing the public price lists followed
    /// (`evidence`, a hash; the list itself in the public log). Every entry within PRICE_STEP_MAX_BPS of its current
    /// value and at most PRICE_CAP_MULTIPLE × its genesis value; SERVICE_FEE at most SERVICE_FEE_CAP; one pending at a
    /// time; in force PRICE_DELAY after it was published.
    function propose(uint256[] calldata next, bytes32 evidence, bytes32 nonce, bytes[] calldata sigs) external {
        _applyIfDue();
        if (_pending.effectiveAt != 0) revert AlreadyPending();
        uint256 n = _prices.length;
        if (next.length != n) revert BadParams();
        for (uint256 i; i < n; ++i) {
            uint256 cur = _prices[i];
            uint256 v = next[i];
            if (v * BPS > cur * (BPS + PRICE_STEP_MAX_BPS) || v * BPS < cur * (BPS - PRICE_STEP_MAX_BPS)) {
                revert OutOfBounds(i);
            }
            if (v > genesis[i] * PRICE_CAP_MULTIPLE || (i == n - 1 && v > SERVICE_FEE_CAP)) revert OutOfBounds(i);
        }
        bytes32 h = keccak256(abi.encodePacked(next));
        verdicts.authorizeAll(updateDigest(h, evidence, nonce), 0, 0, sigs);
        uint64 at = uint64(block.timestamp + PRICE_DELAY);
        _pending = Update(next, evidence, at);
        emit PriceUpdatePublished(h, evidence, at);
    }

    /// Anyone, once the notice has run: the pending table replaces the one in force. Charges use the pending table
    /// from its effective time whether or not this was called.
    function applyUpdate() external {
        if (_pending.effectiveAt == 0) revert NothingPending();
        if (block.timestamp < _pending.effectiveAt) revert TooEarly();
        _applyIfDue();
    }

    // ---------- views ----------

    function usageDigest(uint256 id, Usage calldata u) public view returns (bytes32) {
        return MessageHashUtils.toTypedDataHash(
            _domain,
            keccak256(
                abi.encode(
                    USAGE_TYPEHASH, id, u.receipt, u.input, u.cached, u.output, u.vcpuSeconds, u.gbSeconds, u.storageMb
                )
            )
        );
    }

    function updateDigest(bytes32 prices_, bytes32 evidence, bytes32 nonce) public view returns (bytes32) {
        return MessageHashUtils.toTypedDataHash(
            _domain, keccak256(abi.encode(PRICE_UPDATE_TYPEHASH, prices_, evidence, nonce))
        );
    }

    function domainSeparator() external view returns (bytes32) {
        return _domain;
    }

    function families() external view returns (bytes32[] memory) {
        return _families;
    }

    /// The table in force now (a pending update counts from its effective time).
    function prices() external view returns (uint256[] memory out) {
        out = new uint256[](_prices.length);
        for (uint256 i; i < out.length; ++i) {
            out[i] = _price(i);
        }
    }

    function pending() external view returns (Update memory) {
        return _pending;
    }

    function caps() external view returns (Caps memory) {
        return _caps;
    }

    /// SERVICE_FEE in force, micro-coins per counted check.
    function serviceFee() external view returns (uint256) {
        return _price(_base() + 4);
    }

    function profileOf(bytes32 repo) public view returns (Profile memory p) {
        p = _profiles[repo];
        if (p.timeoutSeconds == 0) p = _defaultProfile;
    }

    function reports(uint256 id) external view returns (Report[] memory) {
        return _reports[id];
    }

    function maxDepositFor(uint256 b) external view returns (uint256) {
        return maxDeposit(_repoOf(b));
    }

    /// The solver's deposit for a check in `repo`, in micro-coins (S15): ISSUE_JUDGES judges at the caps, at the
    /// dearest family, each with its storage and SERVICE_FEE; the CI runs at the profile's limits (one with
    /// CI_SINGLE_RUN); the gas allowance at MAX_GAS_PRICE. Every price the dearer of the one in force and the pending
    /// one, so an update published after the commit can't push a charge over its deposit. Rounded up.
    function maxDeposit(bytes32 repo) public view returns (uint256) {
        Caps memory c = _caps;
        Profile memory p = profileOf(repo);
        uint256 judges = verdicts.ISSUE_JUDGES();
        uint256 f = _families.length;
        uint256 b = 3 * f;
        uint256 ai;
        for (uint256 i; i < f; ++i) {
            // the worst case: every input token uncached
            uint256 a = uint256(c.inputTokens) * _dear(3 * i) + uint256(c.outputTokens) * _dear(3 * i + 2);
            if (a > ai) ai = a;
        }
        uint256 perJudge = _ceil(ai + uint256(c.storageMb) * _dear(b + 2)) + _dear(b + 4);
        uint256 run = _ceil(_maxVcpu(p) * _dear(b) + _maxGb(p) * _dear(b + 1));
        uint256 gas = _ceil(uint256(c.gasAllowance) * c.maxGasPrice * _dear(b + 3) / 1e12);
        return judges * perJudge + (ciSingleRun ? 1 : judges) * run + gas;
    }

    // ---------- internals ----------

    function _base() internal view returns (uint256) {
        return 3 * _families.length;
    }

    /// An entry in force: the pending update's from its effective time.
    function _price(uint256 i) internal view returns (uint256) {
        uint64 at = _pending.effectiveAt;
        return at != 0 && block.timestamp >= at ? _pending.prices[i] : _prices[i];
    }

    /// The dearer of an entry in force and pending (the deposit's).
    function _dear(uint256 i) internal view returns (uint256 v) {
        v = _price(i);
        if (_pending.effectiveAt != 0 && _pending.prices[i] > v) v = _pending.prices[i];
    }

    function _applyIfDue() internal {
        uint64 at = _pending.effectiveAt;
        if (at == 0 || block.timestamp < at) return;
        _prices = _pending.prices;
        emit PriceUpdateApplied(keccak256(abi.encodePacked(_prices)));
        delete _pending;
    }

    function _repoOf(uint256 b) internal view returns (bytes32) {
        IRaceViews r = IRaceViews(race);
        return r.issue(r.bounty(b).issue).repo;
    }

    /// The judge's seat's first disclosed operator account (else the key itself), and its family's index.
    function _seatOf(address judge) internal view returns (address payee, uint256 family) {
        uint256 n = verdicts.seatCount();
        for (uint256 s; s < n; ++s) {
            Verdicts.Seat memory seat = verdicts.seat(s);
            if (seat.key == judge) {
                address[] memory ops = verdicts.operatorsOfSeat(s);
                return (ops.length != 0 ? ops[0] : judge, _familyIndex(_families, seat.family));
            }
        }
        revert NotDrawn();
    }

    function _familyIndex(bytes32[] memory list, bytes32 family) internal pure returns (uint256) {
        for (uint256 i; i < list.length; ++i) {
            if (list[i] == family) return i;
        }
        revert BadParams();
    }

    function _maxVcpu(Profile memory p) internal pure returns (uint256) {
        return uint256(p.milliVcpus) * p.timeoutSeconds / 1000;
    }

    function _maxGb(Profile memory p) internal pure returns (uint256) {
        return uint256(p.memoryMb) * p.timeoutSeconds / 1024;
    }

    /// A report within the constitution's caps and the CI profile's limits (a run that hit one stopped there).
    function _capped(Usage memory u, Profile memory p) internal view returns (Usage memory c) {
        Caps memory k = _caps;
        c.input = u.input < k.inputTokens ? u.input : k.inputTokens;
        c.cached = u.cached < c.input ? u.cached : c.input;
        c.output = u.output < k.outputTokens ? u.output : k.outputTokens;
        c.vcpuSeconds = uint64(u.vcpuSeconds < _maxVcpu(p) ? u.vcpuSeconds : _maxVcpu(p));
        c.gbSeconds = uint64(u.gbSeconds < _maxGb(p) ? u.gbSeconds : _maxGb(p));
        c.storageMb = u.storageMb < k.storageMb ? u.storageMb : k.storageMb;
    }

    /// Every field's median over the counted judges' capped reports (S15): the middle one of three, the mean of two
    /// rounded down (as pof.checkgas: statistics.median, truncated), the only one of one.
    function _median(Report[] storage rs, Profile memory p) internal view returns (Usage memory m) {
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

    /// The median of at most ISSUE_JUDGES values.
    function _mid(uint256[] memory xs) internal pure returns (uint256) {
        uint256 n = xs.length;
        for (uint256 i = 1; i < n; ++i) {
            for (uint256 j = i; j > 0 && xs[j - 1] > xs[j]; --j) {
                (xs[j - 1], xs[j]) = (xs[j], xs[j - 1]);
            }
        }
        return n % 2 == 1 ? xs[n / 2] : (xs[n / 2 - 1] + xs[n / 2]) / 2;
    }

    /// The AI review at a family's prices: uncached input, cached input and output (rounded down).
    function _tokensCost(uint256 family, Usage memory u) internal view returns (uint256) {
        uint256 i = 3 * family;
        return ((uint256(u.input) - u.cached) * _price(i) + uint256(u.cached) * _price(i + 1)
            + uint256(u.output) * _price(i + 2)) / M;
    }

    function _sandboxCost(Usage memory u) internal view returns (uint256) {
        uint256 b = _base();
        return (uint256(u.vcpuSeconds) * _price(b) + uint256(u.gbSeconds) * _price(b + 1)) / M;
    }

    function _storageCost(Usage memory u) internal view returns (uint256) {
        return uint256(u.storageMb) * _price(_base() + 2) / M;
    }

    /// The relayer's gas at cost: measured plus the overhead, at the transaction's gas price (at most MAX_GAS_PRICE),
    /// within the allowance, in micro-coins at the table's ETH price.
    function _gasCost(uint256 gasUsed) internal view returns (uint256) {
        Caps memory c = _caps;
        uint256 g = gasUsed + c.gasOverhead;
        if (g > c.gasAllowance) g = c.gasAllowance;
        uint256 price = tx.gasprice < c.maxGasPrice ? tx.gasprice : c.maxGasPrice;
        return g * price * _price(_base() + 3) / 1e18;
    }

    function _ceil(uint256 x) internal pure returns (uint256) {
        return (x + M - 1) / M;
    }
}
