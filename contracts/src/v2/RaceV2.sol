// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {RaceV2Base} from "./RaceV2Base.sol";
import {RaceV2Annex} from "./RaceV2Annex.sol";
import {Verdicts} from "./Verdicts.sol";
import {Heads} from "./Heads.sol";
import {IFees} from "./IFees.sol";

/// The race on-chain, v2 (proof-of-fix#85, design S10): v1's Race (#56: D4, D9-D12, D14) split under EIP-170 and
/// coin-only. The race itself is unchanged: anyone registers an issue with its fee and stake; the registration check
/// opens its bounty, or refuses it while a similar issue's bounty is open (D12). Anyone pledges a basket while it's
/// open; its price opens at a share of every coin and rises daily until the first attempt locks the share (later
/// pledges still raise the price, D14); the passing submission with the earliest commitment wins. Paid on merge, in
/// instalments at each release after the challenge window; an upheld challenge reopens the bounty with what's unpaid.
/// A fix paid once can't win again (D10), and a bounty nobody takes sunsets (D11).
///
/// What changes from v1:
/// - Coin only (S6): no token and no Token calls. A paid close no longer records a token weight. The inflation rule
///   (#58 D3, amended) still applies to the coin: a registered weight above inflationPct of the merge estimate
///   forfeits the reporter's finder's fee, which stays in the pot (refunded by input).
/// - The verdicts' quorum is the shared contract Verdicts (S10): the same rules and errors as v1's OracleAuth, one key
///   set for every v2 contract. Results are signed over this contract's EIP-712 domain, version "2".
/// - The day count starts at a time fixed at deployment (by default the deployment), not a token's start.
/// - The verdict v2 (task 5.2, S1, S11): a submission's result and its merge are signed as one EIP-712 struct naming
///   the repository, the base commit it was checked on, the fix commit, the bounty, the submission, the tier, the
///   outcome, the receipt's hash, the draw's seed and a nonce. An issue registers in a repository of the head registry
///   (Heads, deployed by this contract) or outside it (repo 0: a project with human maintainers, S8). A merge in a
///   registered repository moves its head only if the verdict's base is the head; a stale one is refused whole, so the
///   winner keeps its place and its locked share, rebases, and the judges sign a verdict on the rebased fix.

/// - The issue tier on-chain (task 5.3, S2): a result or a merge counts only with 2 of the 3 judges Verdicts draws
///   with the submission's seed, fixed when it's committed (the block's RANDAO value with the commitment and the id);
///   a judge whose operator is a party to the bounty (`isParty`: its reporter, the submission's solver or a funder)
///   is recused and the next in the draw sits. The verdict's signed seed must be the submission's.
///
/// No owner, admin, upgrade or pause: everything is fixed at deployment. No market fee (D9). Nothing loops over a
/// bounty's coins or funders: every payout from a pot is computed per coin when someone touches that pot, from the
/// pot's held amount at the win (snapshotted on the first change after it). (`isParty`, a view, checks the fee coins.)
///
/// Hooks for the later v2 tasks (not built here):
///   TODO(5.5) sealed verdicts, revealed within the windows.
///   TODO(5.6) receipt challenges (the receipt's hash is signed and recorded since 5.2).
///   TODO(5.7) check fees: unit costs passed through plus the agreed SERVICE_FEE, the maximum deposit, gas at cost;
///             they replace checkDeposit's fixed oracle fees (Fee[] in the result), and pay the rebased fix's
///             check (S1: the solver pays it, refunded at merge).
///   TODO(5.8) bonds and provable faults.
///   TODO(5.13) migration: v1's bounties finish in v1; new ones open here.
contract RaceV2 is RaceV2Base {
    /// The companion RaceV2Annex, deployed by the constructor: RaceV2 delegates its rarely called actions to it (the
    /// appeals, withdrawIssue, junk, refuseSimilar, timeOut, mergeExpired and challengeUpheld), which run in this
    /// contract's storage (EIP-170, task 5.3). Its address is fixed: no key, no upgrade.
    address public immutable annex;

    /// The verdicts' contract (its keys and quorum fixed there), the inflation tolerance and the start of the day
    /// count are fixed here. start_ = 0 starts the count now; a later version may pass an earlier version's start to
    /// keep its days (D15). The head registry's genesis (S10) and the companion RaceV2Annex are deployed here, each with
    /// this contract fixed as its only caller.
    constructor(
        Config memory config_,
        address[] memory feeCoins_,
        uint256 bountyCap_,
        uint256 totalCap_,
        Verdicts verdicts_,
        uint256 inflationPct_,
        uint256 start_,
        bytes32[] memory repos_,
        bytes32[] memory heads_,
        bytes32 constitution_,
        IFees meter_
    )
        RaceV2Base(
            config_,
            feeCoins_,
            bountyCap_,
            totalCap_,
            verdicts_,
            inflationPct_,
            start_,
            new Heads(verdicts_, repos_, heads_, constitution_, address(this)),
            meter_
        )
    {
        annex = address(
            new RaceV2Annex(config_, feeCoins_, bountyCap_, totalCap_, verdicts_, inflationPct_, start, heads, meter_)
        );
        if (address(meter_) != address(0)) {
            if (!isFeeCoin[meter_.coin()]) revert BadParams();
            meter_.bind(); // a meter serves one race: it settles only for this one from now on
        }
    }

    // ---------- views ----------

    function getConfig() external view returns (Config memory) {
        return config;
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

    /// Who takes part in a verdict's subject (Verdicts' IParties, task 5.3): the issue's reporter, the submission's
    /// solver, and anyone who pledged to the bounty in any fee coin. A judge whose operator is a party is recused.
    function isParty(uint256 b, uint256 id, address account) external view returns (bool) {
        if (account == _issues[_bounties[b].issue].reporter || account == _submissions[id].solver) return true;
        for (uint256 i; i < feeCoins.length; ++i) {
            if (pledged[b][feeCoins[i]][account] != 0) return true;
        }
        return false;
    }

    // The oracle keys, the quorum and the digests this contract has taken are read on `verdicts`
    // (keys(), quorum(), isOracle(key), used(address(this), digest)): no copies here, to keep room under EIP-170.

    // ---------- issues ----------

    /// Anyone registers an issue: the registration fee (the AI check, refunded with the finder's fee if solved) and
    /// the issue stake (back with the fee if solved, or if it's never solved; lost if junk), both in one fee coin. The
    /// check's result opens its bounty (`accept`) or refuses it (`refuseSimilar`). The issue is in `repo`, a repository
    /// of the head registry, or 0 for a project outside it (S8).
    function register(address coin, bytes32 repo) external nonReentrant returns (uint256 id) {
        _feeCoin(coin);
        if (repo != bytes32(0) && !heads.isRepo(repo)) revert Refused();
        uint256 fee = _units(coin, config.registrationFee);
        uint256 stake = _units(coin, config.issueStake);
        if (fee != 0) _collect(coin, msg.sender, fee, config.infrastructure);
        if (stake != 0) _hold(coin, msg.sender, stake);
        id = _issues.length;
        _issues.push(Issue(repo, msg.sender, coin, fee, stake, 0, IssueState.Posted));
        emit Registered(id, msg.sender);
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

    // ---------- results (signed by the oracle quorum, D3) ----------

    /// A submission's result, as a verdict v2 (S11): the issue tier's outcome for `v.submission`, checked on `v.base`,
    /// with its receipt's hash, both recorded. Its oracle fees are paid from its deposit; a duplicate also pays the
    /// evaluation fee; the rest returns. A pass for a fix already paid on another bounty counts as a duplicate (D10).
    /// The earliest commitment that passes, once every earlier one is decided, wins: a pass checked on an older base
    /// still wins its place; the head only moves at its merge, on a verdict checked on the head (S1).
    function result(Verdict calldata v, Fee[] calldata fees, bytes[] calldata sigs) external nonReentrant {
        uint256 g = gasleft();
        uint256 id = v.submission;
        Submission storage s = _submissions[id];
        _checkVerdict(v, s.bounty);
        _authorizeDrawn(keccak256(abi.encode(RESULT_TYPEHASH, _verdictHash(v), _hashFees(fees))), v, sigs);
        Outcome outcome = Outcome(v.outcome);
        bytes32 fix = v.fix;
        if (s.solver == address(0) || s.outcome != Outcome.None || outcome == Outcome.None) revert Refused();
        if (outcome == Outcome.Pass && paidFix[fix]) outcome = Outcome.Duplicate;
        uint256 left = address(meter) == address(0) ? _payFees(s.coin, s.deposit, fees) : _payMeter(id, fees.length, g - gasleft());
        if (outcome == Outcome.Duplicate) {
            uint256 fee = _units(s.coin, config.evaluationFee);
            if (fee > left) fee = left;
            _release(s.coin, fee, config.infrastructure);
            left -= fee;
        }
        _release(s.coin, left, s.solver);
        s.outcome = outcome;
        s.fix = fix;
        s.base = v.base;
        s.receipt = v.receiptHash;
        // A checked fix that failed is progress, and the bounty is open to everyone again: its idle clock restarts.
        // A duplicate isn't (owner, 2026-10-29): repeating one can't keep a dead bounty from its sunset.
        if ((outcome == Outcome.Fail || outcome == Outcome.Split) && _bounties[s.bounty].state == State.Open) {
            _bounties[s.bounty].idleSince = day();
        }
        emit Decided(id, outcome);
        _decide(s.bounty);
    }

    /// Solved = merged, as a verdict v2 (S1, S11): the issue tier passed the winning fix `v.fix` checked on `v.base`.
    /// In a repository of the head registry the head moves to it, only if `v.base` is the head: a stale verdict
    /// reverts whole, the winner keeps its place and its locked share, and its fix, rebased, is checked again and merged
    /// by a new verdict (so `v.fix` may be the rebased commit). Outside the registry (repo 0) it records the fix as
    /// merged upstream. Its award starts, the challenge window opens, and the fix counts as paid (D10). The verdict names
    /// the winning submission, so a merge signed for an earlier winner can't merge a later one, and the merge carries
    /// the second, independent importance estimate (#58 D3).
    function merged(Verdict calldata v, uint256 weight, bytes[] calldata sigs) external nonReentrant {
        uint256 b = v.bounty;
        Bounty storage bt = _bounties[b];
        _checkVerdict(v, b);
        bytes32 vh = _verdictHash(v);
        _authorizeDrawn(keccak256(abi.encode(MERGED_TYPEHASH, vh, weight)), v, sigs);
        if (bt.state != State.Won) revert WrongState(b, bt.state);
        if (bt.winner != v.submission || v.outcome != uint8(Outcome.Pass) || v.fix == bytes32(0)) revert Refused();
        if (v.repo != bytes32(0)) heads.move(v.repo, v.base, v.fix, b, v.submission, vh); // S1: base == head, or revert
        bt.mergeWeight = weight;
        Submission storage s = _submissions[bt.winner];
        bt.epoch += 1;
        awards[b][bt.epoch] = Award(s.solver, v.fix, day() + config.windowDays, false, 0);
        paidFix[s.fix] = true;
        paidFix[v.fix] = true; // the rebased commit too, if it differs
        _setState(b, State.Merged);
        emit Awarded(b, bt.epoch, s.solver);
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

    // ---------- delegated to RaceV2Annex, run in this contract's storage ----------

    /// The author of a failed or split-rejected submission appeals once (RaceV2Annex.appeal).
    function appeal(uint256, address) external returns (uint256) {
        _delegate();
    }

    /// A duplicate's appeal to a jury from different providers (RaceV2Annex.appealDuplicate).
    function appealDuplicate(uint256, bytes32, address) external returns (uint256) {
        _delegate();
    }

    /// A duplicate appeal's verdict, signed by the quorum (RaceV2Annex.appealResult).
    function appealResult(uint256, bool, Fee[] calldata, Signed calldata) external {
        _delegate();
    }

    /// An issue no bounty was opened for: its reporter takes the stake back (RaceV2Annex.withdrawIssue).
    function withdrawIssue(uint256) external {
        _delegate();
    }

    /// The registration check found the issue junk (RaceV2Annex.junk).
    function junk(uint256, Signed calldata) external {
        _delegate();
    }

    /// The registration check refused the issue while a similar issue's bounty is open (RaceV2Annex.refuseSimilar).
    function refuseSimilar(uint256, uint256, Signed calldata) external {
        _delegate();
    }

    /// A submission with no result after resultDays fails; anyone can call it (RaceV2Annex.timeOut).
    function timeOut(uint256) external {
        _delegate();
    }

    /// A winning fix not merged by its deadline: nothing is paid and the bounty reopens (RaceV2Annex.mergeExpired).
    function mergeExpired(uint256) external {
        _delegate();
    }

    /// An upheld challenge, signed by the quorum (RaceV2Annex.challengeUpheld).
    function challengeUpheld(uint256, uint256, Signed calldata) external {
        _delegate();
    }

    /// Runs this call's function in RaceV2Annex with this contract's storage, balances and caller (DELEGATECALL),
    /// and returns or reverts with whatever it does. The companion's address is fixed at deployment.
    function _delegate() internal {
        address target = annex;
        assembly ("memory-safe") {
            calldatacopy(0, 0, calldatasize())
            let ok := delegatecall(gas(), target, 0, calldatasize(), 0, 0)
            returndatacopy(0, 0, returndatasize())
            if iszero(ok) { revert(0, returndatasize()) }
            return(0, returndatasize())
        }
    }
}
