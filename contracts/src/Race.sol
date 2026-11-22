// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Baskets} from "./Baskets.sol";
import {OracleAuth} from "./OracleAuth.sol";
import {Token} from "./Token.sol";

/// The race on-chain (proof-of-fix#56, design D4 and D9-D12; bounty-market's race as in pof/market.py): anyone
/// registers an issue with its fee and stake; the registration check opens its bounty, or refuses it while a similar
/// issue's bounty is open (D12). Whoever opened it doesn't fund it: anyone pledges a basket while it's open, so the
/// market sets its value. Its price opens at a share of every coin and rises daily until the first attempt locks the
/// share (later pledges still raise the price, D14), and the passing submission with the earliest commitment wins. Paid on merge, in instalments at each release after
/// the challenge window; an upheld challenge reopens the bounty with what's unpaid. A fix paid once can't win again
/// (D10), and a bounty nobody takes sunsets (D11).
///
/// Results come signed (D3, phase 2): anyone relays one with signatures from at least the quorum of the oracle keys
/// fixed at deployment, over an EIP-712 digest binding the chain, this contract, the action, every argument and a
/// nonce; each digest is taken once. No key can be added or removed: a new oracle set is a new version (D15).
/// Its token (D15) is fixed here too: when a bounty closes paid, the Race records the close with its weight, the
/// smaller of the oracles' estimates at registration and at merge (#58 D3; the token weighs it). A registered weight
/// above the token's inflationPct of the merge estimate forfeits the reporter's share: its finder's fee stays in the
/// pot (refunded by input) and its tokens go to the solver.
/// No owner, admin, upgrade or pause: everything is fixed at deployment. No market fee (D9). Nothing loops over a
/// bounty's coins or funders: every payout from a pot is computed per coin when someone touches that pot, from the
/// pot's held amount at the win (snapshotted on the first change after it).
contract Race is Baskets {
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

    bytes32 internal constant DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    bytes32 internal constant NAME_HASH = keccak256("proof-of-fix Race");
    bytes32 internal constant VERSION_HASH = keccak256("1");
    bytes32 public constant FEE_TYPEHASH = keccak256("Fee(address to,uint256 amount)");
    bytes32 public constant ACCEPT_TYPEHASH = keccak256("Accept(uint256 issue,uint256 weight,bytes32 nonce)");
    bytes32 public constant REFUSE_SIMILAR_TYPEHASH =
        keccak256("RefuseSimilar(uint256 issue,uint256 openBounty,bytes32 nonce)");
    bytes32 public constant JUNK_TYPEHASH = keccak256("Junk(uint256 issue,bytes32 nonce)");
    bytes32 public constant RESULT_TYPEHASH = keccak256(
        "Result(uint256 submission,uint256 bounty,uint8 outcome,bytes32 fix,Fee[] fees,bytes32 nonce)Fee(address to,uint256 amount)"
    );
    bytes32 public constant APPEAL_RESULT_TYPEHASH = keccak256(
        "AppealResult(uint256 appeal,uint256 bounty,bool cleared,Fee[] jurors,bytes32 nonce)Fee(address to,uint256 amount)"
    );
    bytes32 public constant MERGED_TYPEHASH = keccak256("Merged(uint256 bounty,uint256 submission,uint256 weight,bytes32 nonce)");
    bytes32 public constant CHALLENGE_UPHELD_TYPEHASH =
        keccak256("ChallengeUpheld(uint256 bounty,uint256 epoch,bytes32 nonce)");

    Config internal config;
    Token public immutable token;
    address[] internal _oracleKeys;
    mapping(address key => bool) public isOracle;
    uint256 public immutable quorum;
    mapping(bytes32 digest => bool) public usedDigest;
    address[] public feeCoins;
    mapping(address coin => bool) public isFeeCoin;
    uint256 public immutable start;

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

    error NotOracle();
    error TooFewSignatures();
    error DuplicateSigner();
    error Replayed();
    error BadOracleSet();
    error BadToken();
    error NotFeeCoin(address coin);
    error WrongState(uint256 bounty, State state);
    error NotYet();
    error Refused();

    /// The oracle keys and their quorum are fixed here. A quorum above half the keys means two conflicting results
    /// for the same thing can't both gather it.
    constructor(
        Config memory config_,
        address[] memory feeCoins_,
        uint256 bountyCap_,
        uint256 totalCap_,
        address[] memory oracleKeys_,
        uint256 quorum_,
        Token token_
    ) Baskets(bountyCap_, totalCap_) {
        // the token's only recorder is this Race, on this Race's releases (D15)
        if (token_.race() != address(this) || token_.periodDays() != config_.releaseEveryDays) revert BadToken();
        token = token_;
        if (quorum_ == 0 || quorum_ > oracleKeys_.length || 2 * quorum_ <= oracleKeys_.length) revert BadOracleSet();
        for (uint256 i; i < oracleKeys_.length; ++i) {
            address k = oracleKeys_[i];
            if (k == address(0) || isOracle[k]) revert BadOracleSet();
            isOracle[k] = true;
            _oracleKeys.push(k);
        }
        quorum = quorum_;
        config = config_;
        start = token_.start(); // the schedule's start: a later version keeps the first one's days and periods (D15)
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

    function getConfig() external view returns (Config memory) {
        return config;
    }

    function oracleKeys() external view returns (address[] memory) {
        return _oracleKeys;
    }

    /// The EIP-712 domain: this contract on this chain, so a signature can't be used on another deployment or chain.
    function domainSeparator() public view returns (bytes32) {
        return keccak256(abi.encode(DOMAIN_TYPEHASH, NAME_HASH, VERSION_HASH, block.chainid, address(this)));
    }

    function day() public view returns (uint256) {
        return (block.timestamp - start) / 1 days;
    }

    function issue(uint256 id) external view returns (Issue memory) {
        return _issues[id];
    }

    function bounty(uint256 id) external view returns (Bounty memory) {
        return _bounties[id];
    }

    function submission(uint256 id) external view returns (Submission memory) {
        return _submissions[id];
    }

    function submissionsOf(uint256 b) external view returns (uint256[] memory) {
        return _bySubmission[b];
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

    // ---------- issues ----------

    /// Anyone registers an issue: the registration fee (the AI check, refunded with the finder's fee if solved) and
    /// the issue stake (back with the fee if solved, or if it's never solved; lost if junk), both in one fee coin. The
    /// check's result opens its bounty (`accept`) or refuses it (`refuseSimilar`).
    function register(address coin) external nonReentrant returns (uint256 id) {
        _feeCoin(coin);
        uint256 fee = _units(coin, config.registrationFee);
        uint256 stake = _units(coin, config.issueStake);
        if (fee != 0) _collect(coin, msg.sender, fee, config.infrastructure);
        if (stake != 0) _hold(coin, msg.sender, stake);
        id = _issues.length;
        _issues.push(Issue(msg.sender, coin, fee, stake, 0, IssueState.Posted));
        emit Registered(id, msg.sender);
    }

    /// An issue no bounty was opened for (the check hasn't answered): its reporter takes the stake back.
    function withdrawIssue(uint256 id) external nonReentrant {
        Issue storage i = _issues[id];
        if (i.reporter != msg.sender || i.state != IssueState.Posted || i.bounty != 0) revert Refused();
        _closeIssue(id, IssueState.Returned, msg.sender);
    }

    /// The oracles found the issue junk: its stake goes to insurance, and its bounty, if still open, refunds.
    function junk(uint256 id, Signed calldata auth) external nonReentrant {
        _authorize(keccak256(abi.encode(JUNK_TYPEHASH, id, auth.nonce)), auth);
        Issue storage i = _issues[id];
        if (i.state != IssueState.Posted) revert Refused();
        _closeIssue(id, IssueState.Forfeited, config.insurance);
        if (i.bounty != 0) {
            State s = _bounties[i.bounty].state;
            if (s == State.Open) _setState(i.bounty, State.Refunded);
        }
    }

    // ---------- bounties ----------

    /// The registration check passed: the issue's bounty opens at once, with no target (D12). Its price rises over
    /// whatever its funders put in. The check's importance estimate is the bounty's registered weight (#58 D3).
    function accept(uint256 issueId, uint256 weight, Signed calldata auth) external nonReentrant returns (uint256 b) {
        _authorize(keccak256(abi.encode(ACCEPT_TYPEHASH, issueId, weight, auth.nonce)), auth);
        Issue storage i = _issues[issueId];
        if (i.state != IssueState.Posted || i.bounty != 0) revert Refused();
        b = _bounties.length;
        _bounties.push();
        _bounties[b].issue = issueId;
        _bounties[b].weight = weight;
        i.bounty = b;
        emit BountyOpened(b, issueId);
        _open(b);
    }

    /// The registration check found the issue similar to one whose bounty is still open or being paid (D12): no
    /// bounty opens, the fee stays spent on the check, and the stake returns. Funders add to the open one.
    function refuseSimilar(uint256 issueId, uint256 openBounty, Signed calldata auth) external nonReentrant {
        _authorize(keccak256(abi.encode(REFUSE_SIMILAR_TYPEHASH, issueId, openBounty, auth.nonce)), auth);
        Issue storage i = _issues[issueId];
        State s = _bounties[openBounty].state;
        if (i.state != IssueState.Posted || i.bounty != 0) revert Refused();
        if (s != State.Open && s != State.Won && s != State.Merged) revert WrongState(openBounty, s);
        _closeIssue(issueId, IssueState.Returned, i.reporter);
        emit RefusedSimilar(issueId, openBounty);
    }

    /// A pledge in any coin, from anyone, while the bounty is open: the market sets its value (D12).
    function pledge(uint256 b, address coin, uint256 amount) external nonReentrant {
        Bounty storage bt = _bounties[b];
        if (bt.state != State.Open) revert WrongState(b, bt.state);
        _touch(b, coin);
        _pledge(b, coin, amount);
    }

    /// D11: an open bounty with no submission waiting for its result closes unsolved idleDays after it opened,
    /// reopened or had a submission checked; its funds return by input and the issue stake returns. Attempts in
    /// progress don't hold it open (owner, 2026-10-29): an attempt every few days for its fee can't keep a dead bounty
    /// alive; they end with it. Anyone can call it.
    function sunset(uint256 b) external nonReentrant {
        Bounty storage bt = _bounties[b];
        if (bt.state != State.Open || bt.next < _bySubmission[b].length) revert NotYet();
        if (day() < bt.idleSince + config.idleDays) revert NotYet();
        _setState(b, State.Unsolved);
        _releaseIssue(bt.issue);
    }

    // ---------- the race ----------

    /// Starts an attempt: the attempt fee, never refunded (#64). The first attempt locks the rising price's share
    /// (D14 measured locking on the first submission instead: funders paid 30 % more and fake attempts paid).
    function attempt(uint256 b, address coin) external nonReentrant {
        Bounty storage bt = _bounties[b];
        if (bt.state != State.Open) revert WrongState(b, bt.state);
        _feeCoin(coin);
        uint256 fee = _units(coin, config.attemptFee);
        if (fee != 0) _collect(coin, msg.sender, fee, config.infrastructure);
        _lock(b);
        if (attemptedOn[b][msg.sender] == 0) bt.attempting += 1;
        attemptedOn[b][msg.sender] = day() + 1;
        emit Attempted(b, msg.sender);
    }

    /// An attempt ends without a submission. It doesn't restart the idle clock.
    function stop(uint256 b) external nonReentrant {
        _stopAttempt(b, msg.sender);
    }

    /// A sealed submission: keccak256(fix hash, salt, solver), with the check deposit. While the bounty is open it
    /// joins the queue in commitment order; once it's won, it isn't checked and pays the evaluation fee (#64).
    function commit(uint256 b, bytes32 commitment, address coin) external nonReentrant returns (uint256 id) {
        Bounty storage bt = _bounties[b];
        _feeCoin(coin);
        if (bt.state == State.Won || bt.state == State.Merged || bt.state == State.Paid) {
            _collect(coin, msg.sender, _units(coin, config.evaluationFee), config.infrastructure);
            emit TooLate(b, msg.sender);
            return 0;
        }
        if (bt.state != State.Open) revert WrongState(b, bt.state);
        _stopAttempt(b, msg.sender); // the idle clock restarts on its result, unless it's a duplicate
        _lock(b);
        id = _submit(b, msg.sender, commitment, coin);
    }

    /// The author of a failed or split-rejected submission appeals once: the appeal fee, and the same fix checked
    /// again (by the second jury) as a new submission with a new deposit. A split rejection is where the checks
    /// most often wrong a good fix (owner, 2026-10-29: 70 % of them were good in the simulation).
    function appeal(uint256 id, address coin) external nonReentrant returns (uint256 newId) {
        Submission storage s = _submissions[id];
        Bounty storage bt = _bounties[s.bounty];
        bool rejected = s.outcome == Outcome.Fail || s.outcome == Outcome.Split;
        if (s.solver != msg.sender || !rejected || s.appealed) revert Refused();
        if (bt.state != State.Open) revert WrongState(s.bounty, bt.state);
        _feeCoin(coin);
        s.appealed = true;
        _collect(coin, msg.sender, _units(coin, config.appealFee), config.infrastructure);
        newId = _submit(s.bounty, msg.sender, s.commitment, coin);
        _submissions[newId].appealed = true;
    }

    /// A submitter whose fix was rejected as a duplicate appeals to a jury from different providers, posting the
    /// appeal deposit; the appeal fee and the jurors' fees come from it (#64).
    function appealDuplicate(uint256 b, bytes32 fix, address coin) external nonReentrant returns (uint256 id) {
        Bounty storage bt = _bounties[b];
        if (bt.state != State.Open) revert WrongState(b, bt.state);
        _feeCoin(coin);
        uint256 deposit = _units(coin, config.appealDeposit);
        _hold(coin, msg.sender, deposit);
        id = _appeals.length;
        _appeals.push(Appeal(b, msg.sender, fix, coin, deposit, false));
    }

    // ---------- results (signed by the oracle quorum, D3) ----------

    /// A submission's result. Its oracle fees are paid from its deposit; a duplicate also pays the evaluation fee;
    /// the rest returns. A pass for a fix already paid on another bounty counts as a duplicate (D10). The earliest
    /// commitment that passes, once every earlier one is decided, wins.
    function result(uint256 id, Outcome outcome, bytes32 fix, Fee[] calldata fees, Signed calldata auth)
        external
        nonReentrant
    {
        Submission storage s = _submissions[id];
        _authorize(
            keccak256(abi.encode(RESULT_TYPEHASH, id, s.bounty, uint8(outcome), fix, _hashFees(fees), auth.nonce)), auth
        );
        if (s.solver == address(0) || s.outcome != Outcome.None || outcome == Outcome.None) revert Refused();
        if (outcome == Outcome.Pass && paidFix[fix]) outcome = Outcome.Duplicate;
        uint256 left = _payFees(s.coin, s.deposit, fees);
        if (outcome == Outcome.Duplicate) {
            uint256 fee = _units(s.coin, config.evaluationFee);
            if (fee > left) fee = left;
            _release(s.coin, fee, config.infrastructure);
            left -= fee;
        }
        _release(s.coin, left, s.solver);
        s.outcome = outcome;
        s.fix = fix;
        // A checked fix that failed is progress, and the bounty is open to everyone again: its idle clock restarts.
        // A duplicate isn't (owner, 2026-10-29): repeating one can't keep a dead bounty from its sunset.
        if ((outcome == Outcome.Fail || outcome == Outcome.Split) && _bounties[s.bounty].state == State.Open) {
            _bounties[s.bounty].idleSince = day();
        }
        emit Decided(id, outcome);
        _decide(s.bounty);
    }

    /// A duplicate appeal's verdict: the appeal fee and the jurors' fees from its deposit, the rest back. A cleared
    /// fix is checked like any the next time it's submitted (the oracles' record).
    function appealResult(uint256 id, bool cleared, Fee[] calldata jurors, Signed calldata auth)
        external
        nonReentrant
    {
        Appeal storage a = _appeals[id];
        _authorize(
            keccak256(abi.encode(APPEAL_RESULT_TYPEHASH, id, a.bounty, cleared, _hashFees(jurors), auth.nonce)), auth
        );
        if (a.solver == address(0) || a.decided) revert Refused();
        a.decided = true;
        uint256 fee = _units(a.coin, config.appealFee);
        if (fee > a.deposit) fee = a.deposit;
        _release(a.coin, fee, config.infrastructure);
        uint256 left = _payFees(a.coin, a.deposit - fee, jurors);
        _release(a.coin, left, a.solver);
        emit AppealDecided(id, cleared);
    }

    /// A submission with no result after resultDays (most likely never revealed to the oracles) fails, so it can't
    /// hold up the queue or the sunset. Its deposit pays the evaluation fee and the rest returns. Anyone can call it.
    function timeOut(uint256 id) external nonReentrant {
        Submission storage s = _submissions[id];
        if (s.solver == address(0) || s.outcome != Outcome.None) revert Refused();
        if (day() < s.day + config.resultDays) revert NotYet();
        uint256 fee = _units(s.coin, config.evaluationFee);
        if (fee > s.deposit) fee = s.deposit;
        _release(s.coin, fee, config.infrastructure);
        _release(s.coin, s.deposit - fee, s.solver);
        s.outcome = Outcome.TimedOut;
        emit Decided(id, Outcome.TimedOut);
        _decide(s.bounty);
    }

    /// Solved = merged: the winning fix was merged in the opted-in repository. Its award starts, the challenge
    /// window opens, and the fix counts as paid (D10). The signed result names the winning submission, so a merge
    /// signed for an earlier winner can't merge a later one, and carries the second, independent importance estimate
    /// (#58 D3).
    function merged(uint256 b, uint256 winner, uint256 weight, Signed calldata auth) external nonReentrant {
        _authorize(keccak256(abi.encode(MERGED_TYPEHASH, b, winner, weight, auth.nonce)), auth);
        Bounty storage bt = _bounties[b];
        if (bt.state != State.Won) revert WrongState(b, bt.state);
        if (bt.winner != winner) revert Refused();
        bt.mergeWeight = weight;
        Submission storage s = _submissions[bt.winner];
        bt.epoch += 1;
        awards[b][bt.epoch] = Award(s.solver, s.fix, day() + config.windowDays, false, 0);
        paidFix[s.fix] = true;
        _setState(b, State.Merged);
        emit Awarded(b, bt.epoch, s.solver);
    }

    /// A winning fix not merged by its deadline: nothing is paid and the bounty reopens.
    function mergeExpired(uint256 b) external nonReentrant {
        Bounty storage bt = _bounties[b];
        if (bt.state != State.Won || day() <= bt.mergeBy) revert NotYet();
        _reopen(b);
    }

    /// An upheld challenge (in the window, or after it while instalments are unpaid): the award keeps what it has
    /// earned, the rest stays in the bounty, and the bounty reopens at its locked price (pof's slash and claw_back).
    function challengeUpheld(uint256 b, uint256 epoch, Signed calldata auth) external nonReentrant {
        _authorize(keccak256(abi.encode(CHALLENGE_UPHELD_TYPEHASH, b, epoch, auth.nonce)), auth);
        Bounty storage bt = _bounties[b];
        if (bt.state != State.Merged) revert WrongState(b, bt.state);
        uint256 e = bt.epoch;
        if (e != epoch) revert Refused(); // signed for another award
        uint256 n = earned(b, e);
        if (n >= config.instalments) revert Refused(); // fully paid: nothing to claw back
        Award storage a = awards[b][e];
        a.earned = n;
        a.closed = true;
        emit ClawedBack(b, e, n);
        _reopen(b);
    }

    // ---------- payouts ----------

    /// Credits an award's earned instalments in one coin to its winner. Anyone can call it.
    function claimInstalments(uint256 b, address coin, uint256 epoch) public nonReentrant {
        _payInstalments(b, coin, epoch);
    }

    /// Once the bounty's outcome is final, pays what's still due from one coin's pot: earned instalments, and if it
    /// was paid, the finder's fee and the registration refund. Refunds by input can then start (claimRefund).
    /// Anyone can call it.
    function settle(uint256 b, address coin) external nonReentrant returns (bool) {
        return _settle(b, coin);
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
        }
        return true;
    }

    /// The bounty closed paid: its issue stake returns, and its close is recorded with the token, which weighs it
    /// and tells whether the registration was inflated (#58 D3, amended): then the reporter's tokens go to the solver
    /// and its finder's fee stays in the pot (in _settle). A junk issue's reporter has none.
    function _closePaid(uint256 b) internal {
        Bounty storage bt = _bounties[b];
        Issue storage i = _issues[bt.issue];
        address reporter;
        if (i.state == IssueState.Posted) {
            reporter = i.reporter;
            _closeIssue(bt.issue, IssueState.Rewarded, reporter);
        }
        // its period is its last instalment's release, fixed by the merge day, whenever it's settled (owner, 2026-10-29)
        Award storage a = awards[b][bt.epoch];
        uint256 period = a.windowEnd / config.releaseEveryDays + config.instalments;
        bt.inflated = token.record(b, period, bt.weight, bt.mergeWeight, a.winner, reporter);
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
        uint256 deposit = _units(coin, config.checkDeposit);
        if (deposit != 0) _hold(coin, solver, deposit);
        id = _submissions.length;
        _submissions.push(Submission(b, day(), solver, commitment, coin, deposit, Outcome.None, bytes32(0), false));
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

    /// At least the quorum of distinct oracle keys signed this action's digest, which hasn't been used before. The
    /// digest is marked used before the action runs (a revert undoes both). The check lives in the linked library
    /// OracleAuth (#93: Race under EIP-170), on this contract's storage.
    function _authorize(bytes32 structHash, Signed calldata auth) internal {
        OracleAuth.authorize(usedDigest, isOracle, quorum, domainSeparator(), structHash, auth.sigs);
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
