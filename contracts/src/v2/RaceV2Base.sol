// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {MessageHashUtils} from "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";
import {Baskets} from "../Baskets.sol";
import {Verdicts} from "./Verdicts.sol";
import {Heads} from "./Heads.sol";
import {IFees} from "./IFees.sol";

/// RaceV2's state, types and internals (proof-of-fix#85, task 5.3: the EIP-170 split continued, design S10). RaceV2
/// and its companion RaceV2Annex both inherit it, so they share one storage layout: RaceV2 runs its rarely called
/// actions in its own storage by delegating to RaceV2Annex, whose address RaceV2 fixes at its deployment (no key, no
/// upgrade).
/// Everything here is described on RaceV2.
abstract contract RaceV2Base is Baskets {
    /// Fixed at deployment. Amounts are in micro-coins (1e-6) of whichever fee coin pays them; shares in bps.
    struct Config {
        address infrastructure; // the registration, attempt, late, duplicate and appeal fees (the checks' costs)
        address insurance; // a junk issue's stake
        uint256 registrationFee;
        uint256 issueStake;
        uint256 attemptFee;
        uint256 evaluationFee; // a late or duplicate submission's fee
        uint256 checkDeposit; // posted with a submission; its oracle fees are paid from it, the rest returns
        uint256 appealFee; // an appeal's fee (the author's, or a duplicate rejection's)
        uint256 appealDeposit; // posted with a duplicate appeal: the appeal fee and the jurors' fees come from it
        uint256 startPriceBps;
        uint256 riseBpsPerDay;
        uint256 finderFeeBps; // the reporter's fee, of the price (1765: 15 % of the payout, D12)
        uint256 idleDays; // an open bounty with no attempt in progress for this long sunsets (D11)
        uint256 resultDays; // a submission with no result for this long can be timed out by anyone (D14)
        uint256 mergeDays; // a winning fix must be merged within this, or the bounty reopens
        uint256 windowDays; // the challenge window after the merge
        uint256 releaseEveryDays; // instalments are paid at each release after the window
        uint256 instalments;
    }

    enum State {
        None,
        Open,
        Won, // a submission passed; waiting for its merge
        Merged, // in the window, then paid in instalments
        Paid,
        Refunded,
        Unsolved
    }

    enum IssueState {
        None,
        Posted,
        Rewarded,
        Returned,
        Forfeited
    }

    enum Outcome {
        None,
        Pass,
        Fail,
        Duplicate, // a failed fix's, or one already paid elsewhere (D10): rejected unchecked for the evaluation fee
        Split, // no clear failure (a split jury, inconclusive CI): the deposit pays the checks, the rest returns
        TimedOut // no result in time (not revealed to the oracles, most likely): fails, and pays the evaluation fee
    }

    struct Issue {
        bytes32 repo; // a repository of the head registry, or 0 outside it (S8)
        address reporter;
        address coin; // the fee coin its registration and stake were paid in
        uint256 registration;
        uint256 stake;
        uint256 bounty;
        IssueState state;
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
        uint256 winner; // the winning submission, while Won
        uint256 mergeBy;
        uint256 epoch; // awards so far: each merge starts one, an upheld challenge closes it
        uint256 weight; // the registration check's importance estimate (#58 D3)
        uint256 mergeWeight; // the latest merge's estimate
        bool inflated; // closed paid with its registered weight above inflationPct of the merge estimate
    }

    struct Submission {
        uint256 bounty;
        uint256 day; // committed on
        address solver;
        bytes32 commitment;
        address coin;
        uint256 deposit;
        Outcome outcome;
        bytes32 fix;
        bool appealed;
        bytes32 base; // the commit its result was checked on (S11)
        bytes32 receipt; // its result's receipt hash (S11, S14)
        bytes32 seed; // the issue tier's draw (S2, task 5.3), fixed when it's committed
    }

    struct Award {
        address winner;
        bytes32 fix;
        uint256 windowEnd; // accepted on this day, if nothing was upheld before
        bool closed; // an upheld challenge closed it
        uint256 earned; // instalments earned when it closed
    }

    struct PotRace {
        uint256 snappedEpochs; // awards whose price in this coin is stored
        uint256 finderPaid; // epochs settled (1 once settled)
    }

    struct Appeal {
        uint256 bounty;
        address solver;
        bytes32 fix;
        address coin;
        uint256 deposit;
        bool decided;
    }

    struct Fee {
        address to;
        uint256 amount;
    }

    /// An oracle result's authorization: a nonce the oracles chose, and their signatures over the action's EIP-712
    /// digest, ordered by signer address (strictly increasing, so no key counts twice).
    struct Signed {
        bytes32 nonce;
        bytes[] sigs;
    }

    /// The verdict v2 (S11): what the judges checked and where. Commits are bytes32 like Heads' (a SHA-1 left-aligned,
    /// or a SHA-256 id); the nonce is bytes32 like every other signed action here.
    struct Verdict {
        bytes32 repo;
        bytes32 base;
        bytes32 fix;
        uint256 bounty;
        uint256 submission;
        uint8 tier;
        uint8 outcome;
        bytes32 receiptHash;
        bytes32 seed;
        bytes32 nonce;
    }

    bytes32 internal constant DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    bytes32 internal constant NAME_HASH = keccak256("proof-of-fix Race");
    bytes32 internal constant VERSION_HASH = keccak256("2"); // a v1 signature can't be used here
    bytes32 public constant FEE_TYPEHASH = keccak256("Fee(address to,uint256 amount)");
    bytes32 public constant ACCEPT_TYPEHASH = keccak256("Accept(uint256 issue,uint256 weight,bytes32 nonce)");
    bytes32 public constant REFUSE_SIMILAR_TYPEHASH =
        keccak256("RefuseSimilar(uint256 issue,uint256 openBounty,bytes32 nonce)");
    bytes32 public constant JUNK_TYPEHASH = keccak256("Junk(uint256 issue,bytes32 nonce)");
    bytes32 internal constant VERDICT_TYPEHASH = keccak256(
        "Verdict(bytes32 repo,bytes32 base,bytes32 fix,uint256 bounty,uint256 submission,uint8 tier,uint8 outcome,bytes32 receiptHash,bytes32 seed,bytes32 nonce)"
    );
    bytes32 public constant RESULT_TYPEHASH = keccak256(
        "Result(Verdict verdict,Fee[] fees)Fee(address to,uint256 amount)Verdict(bytes32 repo,bytes32 base,bytes32 fix,uint256 bounty,uint256 submission,uint8 tier,uint8 outcome,bytes32 receiptHash,bytes32 seed,bytes32 nonce)"
    );
    bytes32 public constant APPEAL_RESULT_TYPEHASH = keccak256(
        "AppealResult(uint256 appeal,uint256 bounty,bool cleared,Fee[] jurors,bytes32 nonce)Fee(address to,uint256 amount)"
    );
    bytes32 public constant MERGED_TYPEHASH = keccak256(
        "Merged(Verdict verdict,uint256 weight)Verdict(bytes32 repo,bytes32 base,bytes32 fix,uint256 bounty,uint256 submission,uint8 tier,uint8 outcome,bytes32 receiptHash,bytes32 seed,bytes32 nonce)"
    );
    uint8 internal constant TIER_ISSUE = 1; // 2 of 3 (S2); a constitution verdict (5 of 7) is tier 2, never taken here
    bytes32 public constant CHALLENGE_UPHELD_TYPEHASH =
        keccak256("ChallengeUpheld(uint256 bounty,uint256 epoch,bytes32 nonce)");

    Config internal config;
    Verdicts public immutable verdicts; // the oracle keys and their quorum (S10)
    Heads public immutable heads; // the head registry, deployed by RaceV2 and moved only by it (S1)
    uint256 public immutable inflationPct; // a registered weight above this % of the merge estimate forfeits the finder's fee
    address[] public feeCoins;
    mapping(address coin => bool) public isFeeCoin;
    uint256 public immutable start;
    /// The check-fee meter (task 5.7, S15): with one, a check deposit is the worst case in its fee coin and the judges
    /// are paid their measured usage plus the agreed service fee; without one (0), v1's flat deposit and signed list.
    IFees public immutable meter;

    Issue[] internal _issues;
    Bounty[] internal _bounties;
    Submission[] internal _submissions;
    Appeal[] internal _appeals;
    mapping(uint256 bounty => uint256[]) internal _bySubmission;
    mapping(uint256 bounty => mapping(uint256 epoch => Award)) public awards;
    mapping(uint256 bounty => mapping(address coin => PotRace)) internal _potRace;
    mapping(uint256 bounty => mapping(address coin => mapping(uint256 epoch => uint256))) public prices;
    mapping(uint256 bounty => mapping(address coin => mapping(uint256 epoch => uint256))) public instalmentsPaid;
    mapping(uint256 bounty => mapping(address coin => bool)) public settled;
    mapping(uint256 bounty => mapping(address solver => uint256)) public attemptedOn; // day + 1, 0 = none
    mapping(bytes32 fix => bool) public paidFix;

    event Registered(uint256 indexed issue, address indexed reporter);
    event IssueClosed(uint256 indexed issue, IssueState state);
    event BountyOpened(uint256 indexed bounty, uint256 indexed issue);
    event RefusedSimilar(uint256 indexed issue, uint256 indexed openBounty);
    event StateChanged(uint256 indexed bounty, State state);
    event Locked(uint256 indexed bounty, uint256 bps);
    event Attempted(uint256 indexed bounty, address indexed solver);
    event Committed(uint256 indexed bounty, uint256 indexed submission, address indexed solver);
    event TooLate(uint256 indexed bounty, address indexed solver);
    event Decided(uint256 indexed submission, Outcome outcome);
    event AppealDecided(uint256 indexed appeal, bool cleared);
    event Awarded(uint256 indexed bounty, uint256 indexed epoch, address winner);
    event ClawedBack(uint256 indexed bounty, uint256 indexed epoch, uint256 earned);

    // Raised by Verdicts (same selectors as v1), declared here so callers can match them on this contract.
    error NotOracle();
    error TooFewSignatures();
    error DuplicateSigner();
    error Replayed();
    error BadParams();
    error NotFeeCoin(address coin);
    error WrongState(uint256 bounty, State state);
    error NotYet();
    error Refused();
    error WrongTier();

    /// The verdicts' contract (its keys and quorum fixed there), the head registry, the inflation tolerance and the
    /// start of the day count are fixed here. start_ = 0 starts the count now; a later version may pass an earlier
    /// version's start to keep its days (D15).
    constructor(
        Config memory config_,
        address[] memory feeCoins_,
        uint256 bountyCap_,
        uint256 totalCap_,
        Verdicts verdicts_,
        uint256 inflationPct_,
        uint256 start_,
        Heads heads_,
        IFees meter_
    ) Baskets(bountyCap_, totalCap_) {
        if (address(verdicts_).code.length == 0 || inflationPct_ < 100 || start_ > block.timestamp) {
            revert BadParams();
        }
        if (config_.releaseEveryDays == 0 || config_.instalments == 0) revert BadParams();
        verdicts = verdicts_;
        heads = heads_;
        meter = meter_;
        inflationPct = inflationPct_;
        config = config_;
        start = start_ == 0 ? block.timestamp : start_;
        for (uint256 i; i < feeCoins_.length; ++i) {
            _see(feeCoins_[i]);
            feeCoins.push(feeCoins_[i]);
            isFeeCoin[feeCoins_[i]] = true;
        }
        _issues.push(); // ids start at 1
        _bounties.push();
        _submissions.push();
        _appeals.push();
    }

    // ---------- views ----------

    /// The EIP-712 domain: this contract on this chain, so a signature can't be used on another deployment or chain.
    function domainSeparator() public view returns (bytes32) {
        return keccak256(abi.encode(DOMAIN_TYPEHASH, NAME_HASH, VERSION_HASH, block.chainid, address(this)));
    }

    function day() public view returns (uint256) {
        return (block.timestamp - start) / 1 days;
    }

    /// The rising price's share, in bps, on offer now (or locked).
    function offerBps(uint256 b) public view returns (uint256) {
        Bounty storage bt = _bounties[b];
        if (bt.locked) return bt.lockBps;
        uint256 bps = config.startPriceBps + config.riseBpsPerDay * (day() - bt.offerFrom);
        return bps < BPS ? bps : BPS;
    }

    /// pof's price_cap for one coin's pot: what it holds, less the registration (refunded from it if solved), with
    /// room for the finder's fee.
    function capOf(uint256 b, address coin, uint256 h) public view returns (uint256) {
        Issue storage i = _issues[_bounties[b].issue];
        if (coin == i.coin) h = h > i.registration ? h - i.registration : 0;
        return h * BPS / (BPS + config.finderFeeBps);
    }

    /// The price on offer in one coin now: the offer's share of the cap. The first submission locks the share, not
    /// the amount, so later pledges raise the price and every funder pays the same fraction (D14).
    function lockedPrice(uint256 b, address coin) public view returns (uint256) {
        return capOf(b, coin, held(b, coin)) * offerBps(b) / BPS;
    }

    /// An award's price in one coin: the locked share of the cap at the win. The pot at the win is what it holds
    /// less what earlier awards earned and haven't pulled yet (pof pays instalments as they fall due, so its bounty
    /// never holds them).
    function priceOf(uint256 b, address coin, uint256 epoch) public view returns (uint256) {
        if (epoch <= _potRace[b][coin].snappedEpochs) return prices[b][coin][epoch];
        return _priceNow(b, coin, epoch);
    }

    /// What earlier awards (before `epoch`) earned in one coin and haven't been paid.
    function unpaidBefore(uint256 b, address coin, uint256 epoch) public view returns (uint256 total) {
        for (uint256 e = 1; e < epoch; ++e) {
            total += _instalmentsTotal(priceOf(b, coin, e), earned(b, e)) - instalmentsPaid[b][coin][e];
        }
    }

    function _priceNow(uint256 b, address coin, uint256 epoch) internal view returns (uint256) {
        return capOf(b, coin, held(b, coin) - unpaidBefore(b, coin, epoch)) * _bounties[b].lockBps / BPS;
    }

    /// Instalments earned by an award: one at each release after its window, up to all of them.
    function earned(uint256 b, uint256 epoch) public view returns (uint256) {
        Award storage a = awards[b][epoch];
        if (a.closed) return a.earned;
        uint256 d = day();
        if (a.winner == address(0) || d < a.windowEnd) return 0;
        uint256 n = d / config.releaseEveryDays - a.windowEnd / config.releaseEveryDays;
        return n < config.instalments ? n : config.instalments;
    }

    /// What the first `k` instalments of a price come to: price // n each, the last whatever is left.
    function _instalmentsTotal(uint256 price, uint256 k) internal view returns (uint256) {
        return k >= config.instalments ? price : price / config.instalments * k;
    }

    // ---------- internals ----------

    function _settleForRefund(uint256 b, address coin) internal override returns (bool) {
        return _settle(b, coin);
    }

    function _settle(uint256 b, address coin) internal returns (bool) {
        Bounty storage bt = _bounties[b];
        if (bt.state == State.Merged && earned(b, bt.epoch) >= config.instalments) {
            _setState(b, State.Paid);
            _closePaid(b);
        }
        if (bt.state != State.Paid && bt.state != State.Refunded && bt.state != State.Unsolved) return false;
        if (settled[b][coin]) return true;
        settled[b][coin] = true;
        for (uint256 e = 1; e <= bt.epoch; ++e) {
            _payInstalments(b, coin, e);
        }
        if (bt.state == State.Paid) {
            Issue storage i = _issues[bt.issue];
            uint256 fee = bt.inflated ? 0 : priceOf(b, coin, bt.epoch) * config.finderFeeBps / BPS;
            uint256 h = held(b, coin);
            if (fee > h) fee = h;
            if (fee != 0) _pay(b, coin, i.reporter, fee);
            if (coin == i.coin) {
                uint256 refund = i.registration < held(b, coin) ? i.registration : held(b, coin);
                if (refund != 0) _pay(b, coin, i.reporter, refund);
            }
            // S6: the winner's checks for its fix, from what the pot holds once the award is paid (task 5.7)
            if (address(meter) != address(0) && coin == meter.coin()) {
                Submission storage w = _submissions[bt.winner];
                uint256 back = w.deposit < held(b, coin) ? w.deposit : held(b, coin);
                if (back != 0) _pay(b, coin, w.solver, back);
            }
        }
        return true;
    }

    /// The bounty closed paid: its issue stake returns. A registered weight above inflationPct of the merge estimate
    /// (#58 D3, amended) forfeits the reporter's finder's fee: it stays in the pot (in _settle). Coin only (S6): no
    /// token records the close. A junk issue's reporter has none.
    function _closePaid(uint256 b) internal {
        Bounty storage bt = _bounties[b];
        Issue storage i = _issues[bt.issue];
        if (i.state == IssueState.Posted) _closeIssue(bt.issue, IssueState.Rewarded, i.reporter);
        bt.inflated = bt.weight * 100 > bt.mergeWeight * inflationPct;
    }

    function _payInstalments(uint256 b, address coin, uint256 epoch) internal {
        Award storage a = awards[b][epoch];
        if (a.winner == address(0)) revert Refused();
        _touch(b, coin);
        uint256 due = _instalmentsTotal(priceOf(b, coin, epoch), earned(b, epoch)) - instalmentsPaid[b][coin][epoch];
        if (due == 0) return;
        instalmentsPaid[b][coin][epoch] += due;
        _pay(b, coin, a.winner, due);
    }

    /// Before a pot changes: snapshot every award's price not yet stored (the pot hasn't changed since those were
    /// set, so the current amount is theirs).
    function _touch(uint256 b, address coin) internal {
        Bounty storage bt = _bounties[b];
        PotRace storage pr = _potRace[b][coin];
        while (pr.snappedEpochs < bt.epoch) {
            uint256 e = pr.snappedEpochs + 1;
            prices[b][coin][e] = _priceNow(b, coin, e);
            pr.snappedEpochs = e;
        }
    }

    function _lock(uint256 b) internal {
        Bounty storage bt = _bounties[b];
        if (bt.locked) return;
        bt.lockBps = offerBps(b);
        bt.locked = true;
        emit Locked(b, bt.lockBps);
    }

    function _submit(uint256 b, address solver, bytes32 commitment, address coin) internal returns (uint256 id) {
        uint256 deposit;
        if (address(meter) == address(0)) {
            deposit = _units(coin, config.checkDeposit);
        } else {
            if (coin != meter.coin()) revert NotFeeCoin(coin); // S15: the version's one fee coin
            deposit = _units(coin, meter.maxDepositFor(b));
        }
        if (deposit != 0) _hold(coin, solver, deposit);
        id = _submissions.length;
        // The draw's seed (5.3): the commitment, the submission's id and the block's RANDAO value, which the solver
        // doesn't know when it signs the commitment, so it can't grind a salt for friendly judges (design S2's note).
        bytes32 seed = keccak256(abi.encode(block.prevrandao, commitment, id));
        _submissions.push(
            Submission(
                b,
                day(),
                solver,
                commitment,
                coin,
                deposit,
                Outcome.None,
                bytes32(0),
                false,
                bytes32(0),
                bytes32(0),
                seed
            )
        );
        _bySubmission[b].push(id);
        emit Committed(b, id, solver);
    }

    /// D4: walk the queue in commitment order; the first pass wins once everything before it is decided.
    function _decide(uint256 b) internal {
        Bounty storage bt = _bounties[b];
        uint256[] storage list = _bySubmission[b];
        while (bt.state == State.Open && bt.next < list.length) {
            Submission storage s = _submissions[list[bt.next]];
            if (s.outcome == Outcome.None) return;
            if (s.outcome == Outcome.Pass) {
                bt.winner = list[bt.next];
                bt.mergeBy = day() + config.mergeDays;
                bt.next += 1;
                _setState(b, State.Won);
                return;
            }
            bt.next += 1;
        }
    }

    function _reopen(uint256 b) internal {
        Bounty storage bt = _bounties[b];
        bt.idleSince = day();
        _setState(b, State.Open);
        _decide(b); // a pass already waiting behind the old winner wins now
    }

    function _open(uint256 b) internal {
        Bounty storage bt = _bounties[b];
        bt.offerFrom = day();
        bt.idleSince = day();
        _setState(b, State.Open);
    }

    function _stopAttempt(uint256 b, address solver) internal {
        Bounty storage bt = _bounties[b];
        if (attemptedOn[b][solver] == 0) return;
        attemptedOn[b][solver] = 0;
        bt.attempting -= 1;
    }

    /// At least the quorum of distinct oracle keys signed this action's digest, which this contract hasn't taken
    /// before: checked and spent in Verdicts (S10), before the action runs (a revert undoes both).
    function _authorize(bytes32 structHash, Signed calldata auth) internal {
        _authorizeSigs(structHash, auth.sigs);
    }

    function _authorizeSigs(bytes32 structHash, bytes[] calldata sigs) internal {
        verdicts.authorize(MessageHashUtils.toTypedDataHash(domainSeparator(), structHash), sigs);
    }

    /// A verdict's issue tier (S2, task 5.3): 2 of the 3 judges Verdicts draws with the submission's seed, the keys
    /// whose operators are parties recused (`isParty`).
    function _authorizeDrawn(bytes32 structHash, Verdict calldata v, bytes[] calldata sigs) internal {
        verdicts.authorizeDrawn(
            MessageHashUtils.toTypedDataHash(domainSeparator(), structHash), v.seed, v.bounty, v.submission, sigs
        );
    }

    /// The verdict v2's fields that this contract checks itself (S11): the issue tier only (a constitution verdict
    /// can't be relayed here: its tier differs, and the tier is signed), the right bounty, and the bounty's repository.
    function _checkVerdict(Verdict calldata v, uint256 b) internal view {
        if (v.tier != TIER_ISSUE) revert WrongTier();
        if (v.bounty != b || b == 0 || v.repo != _issues[_bounties[b].issue].repo) revert Refused();
        if (v.seed != _submissions[v.submission].seed || _submissions[v.submission].bounty != b) revert Refused();
    }

    /// The verdict's EIP-712 struct hash: every field is static, so the struct encodes in place.
    function _verdictHash(Verdict calldata v) internal pure returns (bytes32) {
        return keccak256(abi.encode(VERDICT_TYPEHASH, v));
    }

    function _hashFees(Fee[] calldata fees) internal pure returns (bytes32) {
        bytes32[] memory hashes = new bytes32[](fees.length);
        for (uint256 i; i < fees.length; ++i) {
            hashes[i] = keccak256(abi.encode(FEE_TYPEHASH, fees[i].to, fees[i].amount));
        }
        return keccak256(abi.encodePacked(hashes));
    }

    function _payFees(address coin, uint256 deposit, Fee[] calldata fees) internal returns (uint256 left) {
        left = deposit;
        for (uint256 i; i < fees.length; ++i) {
            if (fees[i].amount > left) revert Refused();
            left -= fees[i].amount;
            _release(coin, fees[i].amount, fees[i].to);
        }
    }

    /// A metered result (task 5.7, S15): the meter's charge for submission `id`'s checks, released from its deposit
    /// as credits (never more than the deposit), the rest returned. The deposit then records what the checks were
    /// charged: the winner's refund at settlement (S6). With a meter, the judges sign an empty fee list.
    function _payMeter(uint256 id, uint256 signedFees, uint256 gasUsed) internal returns (uint256 left) {
        if (signedFees != 0) revert Refused();
        Submission storage s = _submissions[id];
        (address[] memory to, uint256[] memory micro) = meter.settle(id, msg.sender, gasUsed);
        left = s.deposit;
        for (uint256 i; i < to.length; ++i) {
            uint256 a = _units(s.coin, micro[i]);
            if (a > left) a = left;
            left -= a;
            _release(s.coin, a, to[i]);
        }
        s.deposit -= left;
    }

    function _releaseIssue(uint256 id) internal {
        Issue storage i = _issues[id];
        if (i.state == IssueState.Posted) _closeIssue(id, IssueState.Returned, i.reporter);
    }

    function _closeIssue(uint256 id, IssueState state, address to) internal {
        Issue storage i = _issues[id];
        i.state = state;
        _release(i.coin, i.stake, to);
        emit IssueClosed(id, state);
    }

    function _setState(uint256 b, State s) internal {
        _bounties[b].state = s;
        emit StateChanged(b, s);
    }

    function _feeCoin(address coin) internal view {
        if (!isFeeCoin[coin]) revert NotFeeCoin(coin);
    }

    /// Micro-coins to a fee coin's smallest units.
    function _units(address coin, uint256 micro) internal view returns (uint256) {
        return micro * unit[coin] / 1e6;
    }
}
