// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {RaceV3Base} from "./RaceV3Base.sol";
import {RaceV3Annex} from "./RaceV3Annex.sol";
import {Heads} from "../v2/Heads.sol";
import {Verdicts} from "../v2/Verdicts.sol";
import {IFeesV3} from "./IFeesV3.sol";
import {Panels} from "./Panels.sol";
import {IValidators} from "./IValidators.sol";
import {PoolV3} from "./PoolV3.sol";
import {Status} from "./PanelsBase.sol";
import {SolverBook} from "./SolverBook.sol";

/// The race on-chain, v3 (proof-of-fix#138, task 3.5 of #132; design D1, D4, D5, D9, D13, D14; specs/judge-panels):
/// v2's race (RaceV2: bounties, attempts, sealed commitments, the rising price locked by the first attempt, the
/// earliest passing commitment wins, the claim, instalments, the clawback, Heads), judged by open validators through
/// `Panels` instead of v2's fixed `Verdicts`, and charged by `FeesV3` at market prices. No owner, no setter: Panels,
/// FeesV3 and the sponsors' pool (`PoolV3`) are bound once, from the constructor.
///
/// **One repository, one chain (#251, design L1, L2; specs/deployment-binding).** The race serves exactly one
/// repository, `repo` (keccak256 of its Radicle RID), fixed at construction with its genesis head: its head registry
/// holds that one entry and nothing adds another; an issue for any other repository, or for none, is refused, so every
/// bounty is in it and every merged fix moves its head. The constructor reverts off Sepolia (11155111) and the two local
/// test chains (LaunchChain); `chainId` reports where it runs. These checks bind this deployment, not the open code: a
/// fork can remove them.
///
/// **Every check is a Panels submission under the same id.** A fix's submission, and an issue's registration check
/// (judged at CHECK_BOUNTY, the lowest tier): each posts FeesV3's deposit for `kTop` counted judges (k is fixed only
/// at the draw), or, under a flat judges' fee (`Config.judgeFee` above 0, below), a fix pays that fee instead; FeesV3
/// fixes its prices (`open`), and Panels opens it with the bounty it's judged at: the price on offer at the
/// commitment. An award never pays more than that bounty, so a pledge made after the commitment can't put more
/// at stake than the panel was sized for (the rest returns to the funders).
///
/// **Its parties are fixed when it opens** (`isParty`, which Panels reads at every draw, audit, challenge and hold
/// check): the issue's reporter, the solver, and the funders who had pledged to the bounty by then. Nobody is added or
/// removed afterwards: a pledge made after the commitment doesn't recuse a judge, and a refund doesn't free one.
///
/// **The judges' pay (D4, D9, D14).** Each judge of a panel reports its metered usage, signed by its key as a registry
/// statement over its seat and bound to its on-chain receipt (`report`). Once Panels has counted the verdict, and every
/// seat has reported (or REPORT_WINDOW after the reveal deadline), anyone posts the result (`result`): FeesV3 pays each
/// counted judge the median of the reports at the check's prices plus the service fee scaled by its family's score (k =
/// 1 is its own median) and repays the relayer's gas, all from the deposit. Audits and challenge panels are paid
/// `checkCost` (the unscaled service fee) from the deposit's rest, and from the pool beyond it (`payPanel`); shadows
/// their capped usage from the pool (`payShadow`: one capped report a seated shadow, so a draw's shadows cost at most
/// their seats' quoted usage). After finality the deposit's rest returns to the solver (or reporter); under a flat
/// judges' fee, the rest of a fix's fee goes to the sponsors' pool instead (`finish`).
///
/// **The verdict (D4).** The counted verdict decides the queue at once (`result`): the earliest commitment that passes,
/// once every earlier one is decided, wins, and its solver claims it (`claim`): it opens the commitment,
/// keccak256(abi.encode(fix, base, salt, solver)), and its award starts. A verdict reversed by a challenge before its
/// finality claws the award back and reopens the bounty (`sync`); a failed verdict reversed to a pass wins if the
/// bounty is still open, in its commitment's turn.
///
/// **The head moves at finality (#251, design L9; specs/canonical-head).** Claiming doesn't move the head. Once the
/// winning verdict is final in Panels (its window passed with no challenge upheld, any k = 1 hold over), anyone calls
/// `merge`: the head moves to the fix if its `base` is still the head (S1's stale-base rule: otherwise it reverts whole,
/// and the winner keeps its place until mergeDays after the finality, when `mergeExpired` reopens the bounty). Final
/// verdicts aren't challenged any more, so the head never names a fix whose verdict was reversed. Instalments are
/// counted from the verdict's finality (`earned`) and paid once the fix is merged: a held verdict, a frozen window or
/// an unmerged fix pays nothing.
///
/// **Rebase in place (v3.1, #310, design RB1-RB13).** A claimed, unmerged award whose base is no longer the head is
/// re-submitted rebased onto the head (`rebase`): a new check of the rebased commit, opened in the clear, with a fix's
/// deposit and a claim of the original's judged bounty, judged by a fresh panel with its own full window. The award
/// keeps its place, epoch and price; `merge` moves the head to the rebased commit once both verdicts are final passes,
/// and the instalments count from the later finality. The winning solver may rebase at once, anyone else REBASE_GRACE
/// after the head last moved (a third party's rebase that merges is paid REBASE_SHARE_BPS of the price and its checks
/// at the bounty's payment). The solver's own rebase failed by its counted panel on the head reopens the bounty at once
/// (`mergeExpired`); any other ending only frees the award's one rebase slot; the merge deadline counts from the latest
/// passing rebase's finality, and a rebase in flight holds it.
///
/// **A check that can't be judged is refunded (#251, design L19; specs/panel-liveness).** When Panels releases its
/// rounds MAX_REDRAWS times, or at its deadline (resultDays after the commitment) once a round was released, anyone
/// calls `release`: the deposit's or fee's rest returns to the solver (no slash, no failed verdict, no reputation
/// lost), and the bounty (if it's open, or this check won it) is refunded to its funders by input, the issue stake back
/// to its reporter; a registration check's issue is returned the same way.
///
/// **Challenges (D4; specs/challenges).** Anyone challenges a verdict in its window (or held) with the published stake
/// plus its panel's worst-case cost (`challenge`); the race holds both. Upheld, both return and the panel is paid from
/// the deposit (and the pool); rejected, the panel is paid from the cover, its rest returns, and the stake goes to the
/// accused: the challenged panel's judges. The cover is priced for the largest challenge panel Panels' rules draw
/// (#251 batch 4, L24: `kTop` with same-size challenges, 3 on Sepolia; 7 with the defaults). A challenge that lapses in
/// Panels (L25: no panel by its CHALLENGE_DEADLINE, or its panel released after it) leaves the verdict standing, and its
/// stake and cover return whole with no reward (`settleLapse`).
///
/// **FeesV3's queue signals** come from Panels' status (`signal`, anyone, and at each result): a waiting submission,
/// a stalled counted panel, and the validators seated on a counted panel.
///
/// **Solvers (#251 contract batch 3; #132 D21, D24, D29, D30; launch L6; ADR 0007; specs/reputation,
/// specs/bounty-market).** The race keeps a `SolverBook`, deployed here, readable by anyone:
/// - the judges' fee (`Config.judgeFee`, D30). 0, the pure taxi fare (the Sepolia launch's): a fix posts FeesV3's
///   worst-case deposit, its judges are paid by the meter, and whatever is left returns to the solver, pass or fail,
///   withdrawn or not. Above 0, a flat fee (for a later mainnet decision): a fix pays it in place of the deposit, its
///   judges are paid from it at market prices, and its rest goes to the sponsors' pool, never back (unless the network
///   never judged it). Either way no solver's deposit is lost on rejection;
/// - its claim (the bounty it's judged at) must fit its solver's cap, REP_BASE + REP_MULT × reputation, or the commit
///   reverts; the claim closes at finality (`close`) or at the merge, which adds the bounty to the reputation; a pass
///   reversed takes twice its bounty off;
/// - a pass may be disputed with a failing test (`dispute`, D21): the stake is the larger of $5 and 10 % of the bounty;
///   upheld, the disputer gets its stake back and EVIDENCE_REWARD_BPS of the bounty from the pot; rejected, the stake
///   goes to the solver;
/// - a rejection may be appealed once with a test (`appeal`, D24), within APPEAL_WINDOW of its counted panel's reveal
///   deadline, with no stake (owner, 2026-11-19): a new submission judged by a fresh draw of the seated families,
///   paying its own metered checks as any submission does;
/// - pledges are refused while fewer than ACTIVE_SOLVERS_MIN solvers are active (L6): an identity is active for
///   ACTIVE_WINDOW after its fix is merged, or after its test dispute is upheld if it had a merged fix. Unfunded
///   bounties are raced as before, and funded ones continue whatever the count.
///
/// Coin only, one coin: the version's fee coin (Panels' bounty limits are in it, and no price feed converts another).
/// RaceV3 runs its rarely called actions in RaceV3Annex (DELEGATECALL, its address fixed here), as RaceV2 did.
contract RaceV3 is RaceV3Base {
    address public immutable annex;
    /// The deployment's one repository: keccak256 of its Radicle RID (#251, L1).
    bytes32 public immutable repo;

    /// The head registry's genesis (S10) is deployed here with one entry, `repo_` at `genesisHead_` (the commit of its
    /// Radicle `main` at deployment; both nonzero, #251 L1), and this contract fixed as its only mover; Panels, FeesV3
    /// and the pool are bound to this race once, and FeesV3's one CI profile must be `repo_`'s. The companion
    /// RaceV3Annex is deployed first (EIP-3860: RaceV3's initcode can't hold it) with the same Panels, pool, start and
    /// caps, which its fingerprint proves; `start_` is the same nonzero time for both.
    constructor(
        Config memory config_,
        uint256 bountyCap_,
        uint256 totalCap_,
        Panels panels_,
        PoolV3 pool_,
        uint256 start_,
        bytes32 repo_,
        bytes32 genesisHead_,
        bytes32 constitution_,
        RaceV3Annex annex_
    )
        RaceV3Base(
            config_,
            bountyCap_,
            totalCap_,
            panels_,
            pool_,
            new Heads(Verdicts(address(panels_)), _one(repo_), _one(genesisHead_), constitution_, address(this)),
            start_
        )
    {
        if (repo_ == bytes32(0) || genesisHead_ == bytes32(0) || fees.repo() != repo_) revert BadParams();
        if (address(annex_).code.length == 0 || annex_.fingerprint() != _fingerprint()) revert BadParams();
        repo = repo_;
        annex = address(annex_);
        book = new SolverBook(panels_.ACTIVE_WINDOW());
        panels_.bind();
        fees.bind();
        pool_.bind();
    }

    // ---------- views ----------

    /// The chain this deployment runs on: 11155111 (Sepolia), or a local test chain (#251, L2).
    function chainId() external view returns (uint256) {
        return block.chainid;
    }

    /// The solvers' reputations, claims and activity (#251 batch 3).
    function solverBook() external view returns (SolverBook) {
        return book;
    }

    function getConfig() external view returns (Config memory) {
        return config;
    }

    function contracts()
        external
        view
        returns (Panels, IFeesV3, PoolV3, IValidators, Heads, address coin_, uint256 start_)
    {
        return (panels, fees, pool, registry, heads, coin, start);
    }

    function day() external view returns (uint256) {
        return _day();
    }

    function offerBps(uint256 b) external view returns (uint256) {
        return _offerBps(b);
    }

    function lockedPrice(uint256 b) external view returns (uint256) {
        return _lockedPrice(b, coin);
    }

    function priceOf(uint256 b, uint256 epoch) external view returns (uint256) {
        return _priceOf(b, coin, epoch);
    }

    function earned(uint256 b, uint256 epoch) external view returns (uint256) {
        return _earned(b, epoch);
    }

    function award(uint256 b, uint256 epoch) external view returns (Award memory) {
        return awards[b][epoch];
    }

    function instalmentsPaid(uint256 b, uint256 epoch) external view returns (uint256) {
        return _instalmentsPaid[b][coin][epoch];
    }

    function challengeOf(uint256 id) external view returns (Challenge memory) {
        return challenges[id];
    }

    function paid(bytes32 fix) external view returns (bool) {
        return paidFix[fix];
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

    function usageOf(uint256 pid, uint256 slot) external view returns (IFeesV3.Usage memory) {
        return _usage[pid][slot];
    }

    /// Who takes part in check `id` (Panels' IPanelsHost), fixed when it opened: the issue's reporter, the solver,
    /// and the funders who had pledged to its bounty by then; for a rebase check also the winning solver whose fix it
    /// rebases (#310, RB6). A judge whose key or operator is a party is recused.
    function isParty(uint256 id, address account) external view returns (bool) {
        Submission storage s = _submissions[id];
        if (account == address(0)) return false;
        if (
            account == s.solver || account == _issues[s.issue != 0 ? s.issue : _bounties[s.bounty].issue].reporter
                || (s.rebaseOf != 0 && account == _submissions[s.rebaseOf].solver)
        ) {
            return true;
        }
        uint256 q = s.bounty == 0 ? 0 : pledgeOrder[s.bounty][account];
        return q != 0 && q <= s.pledges;
    }

    // ---------- issues ----------

    /// Anyone registers an issue in `repo` (the deployment's, `repo()`; any other is refused), with its registration
    /// check; `hidden` for hidden tests or a private repository, whose checks only TEE judges may take
    /// (RaceV3Endings.register).
    function register(bytes32, bool) external returns (uint256) {
        _delegate();
    }

    // ---------- bounties ----------

    /// A pledge in the fee coin, from anyone, while the bounty is open and at least ACTIVE_SOLVERS_MIN solvers are
    /// active (launch L6: otherwise it reverts with the count, and no coin moves). A first pledge takes the next place
    /// in the bounty's funder order, which fixes which checks it is a party to.
    function pledge(uint256 b, uint256 amount) external nonReentrant {
        Bounty storage bt = _bounties[b];
        if (bt.state != State.Open) revert WrongState(b, bt.state);
        uint256 n = book.activeAtLeast(ACTIVE_SOLVERS_MIN);
        if (n < ACTIVE_SOLVERS_MIN) revert TooFewActiveSolvers(n);
        if (pledgeOrder[b][msg.sender] == 0) pledgeOrder[b][msg.sender] = ++bt.pledges;
        _touch(b, coin);
        _pledge(b, coin, amount);
    }

    /// D11: an open bounty with no submission waiting for its result closes unsolved idleDays after it opened,
    /// reopened or had a submission checked; its funds return by input and the issue stake returns.
    function sunset(uint256 b) external nonReentrant {
        Bounty storage bt = _bounties[b];
        if (bt.state != State.Open || bt.next < _bySubmission[b].length) revert NotYet();
        if (_day() < bt.idleSince + config.idleDays) revert NotYet();
        _setState(b, State.Unsolved);
        Issue storage i = _issues[bt.issue];
        if (i.state == IssueState.Posted) _closeIssue(bt.issue, IssueState.Returned, i.reporter);
    }

    // ---------- the race ----------

    /// Starts an attempt: the attempt fee, never refunded. The first attempt locks the rising price's share.
    function attempt(uint256 b) external nonReentrant {
        Bounty storage bt = _bounties[b];
        if (bt.state != State.Open) revert WrongState(b, bt.state);
        uint256 fee = _units(config.attemptFee);
        if (fee != 0) _collect(coin, msg.sender, fee, config.infrastructure);
        _lock(b);
        if (attemptedOn[b][msg.sender] == 0) bt.attempting += 1;
        attemptedOn[b][msg.sender] = _day() + 1;
        emit Attempted(b, msg.sender);
    }

    /// An attempt ends without a submission. It doesn't restart the idle clock.
    function stop(uint256 b) external nonReentrant {
        _stopAttempt(b, msg.sender);
    }

    /// A sealed submission, keccak256(abi.encode(fix, base, salt, solver)), posting its check deposit (or the flat
    /// judges' fee), its claim (the price
    /// on offer now, which Panels judges it at) within its solver's cap (D29: over it, the commit reverts and costs
    /// nothing). While the bounty is open it joins the queue in commitment order; once it's won, it isn't
    /// checked and pays the evaluation fee.
    function commit(uint256 b, bytes32 commitment) external nonReentrant returns (uint256 id) {
        Bounty storage bt = _bounties[b];
        if (bt.state == State.Won || bt.state == State.Merged || bt.state == State.Paid) {
            uint256 fee = _units(config.evaluationFee);
            if (fee != 0) _collect(coin, msg.sender, fee, config.infrastructure); // 0 on Sepolia: no charge
            emit TooLate(b, msg.sender);
            return 0;
        }
        if (bt.state != State.Open) revert WrongState(b, bt.state);
        _stopAttempt(b, msg.sender);
        _lock(b);
        id = _submit(b, msg.sender, commitment);
    }

    // ---------- the judges' reports and the result ----------

    /// Seat `key`'s metered usage on panel `pid` (any kind), signed by `key` (RaceV3Endings.report).
    function report(uint256, address, IFeesV3.Usage calldata, bytes calldata) external {
        _delegate();
    }

    /// The counted verdict of check `id`, once Panels has counted it and its reports are in: FeesV3 pays each counted
    /// judge and the caller's gas from the fee or deposit (judges first), FeesV3 hears who was seated, and the verdict decides
    /// the queue. Anyone, once.
    function result(uint256 id) external nonReentrant {
        uint256 g = gasleft();
        Submission storage s = _submissions[id];
        bytes memory ps = _sub(id);
        if (s.solver == address(0) || s.paid) revert Refused();
        Status st = Status(_w(ps, S_STATUS));
        uint256 pid = _w(ps, S_PID);
        // a refunded check whose verdict had counted (its audits never drawn, L19) still pays its counted judges
        if (st != Status.Held && st != Status.Window && st != Status.Final && (st != Status.Released || pid == 0)) {
            revert NotYet();
        }
        address[] memory keys = panels.judges(pid);
        _reportsDue(pid, _w(_pan(pid), P_REVEAL_BY), keys);
        s.paid = true;
        (address[] memory to, uint256[] memory micro) =
            fees.settle(id, _repoOf(s), _reports(pid, keys), msg.sender, g - gasleft());
        uint256 left = s.deposit;
        for (uint256 i; i < to.length; ++i) {
            uint256 a = _units(micro[i]);
            if (a > left) a = left;
            left -= a;
            _release(coin, a, to[i]);
        }
        s.charged += s.deposit - left;
        s.deposit = left;
        fees.drawn(_seated(keys));
        if (s.outcome == Outcome.None) _decided(id, _w(ps, S_PASS) != 0 ? Outcome.Pass : Outcome.Fail);
    }

    /// The winner's commitment opened (fix, base, salt): its award starts. The head doesn't move here (#251, L9): it
    /// moves at the verdict's finality (`merge`). A fix already merged on a bounty is a duplicate: the evaluation fee
    /// from the deposit's rest, and the bounty reopens. Anyone holding the opening may call it.
    function claim(uint256 b, bytes32 fix, bytes32 base, bytes32 salt) external nonReentrant {
        Bounty storage bt = _bounties[b];
        if (bt.state != State.Won) revert WrongState(b, bt.state);
        uint256 id = bt.winner;
        Submission storage s = _submissions[id];
        if (keccak256(abi.encode(fix, base, salt, s.solver)) != s.commitment || fix == 0) revert Refused();
        (, bool pass,) = _verdict(id);
        if (!pass) revert Refused(); // reversed: `sync` reopens the bounty
        if (paidFix[fix]) {
            uint256 fee = _units(config.evaluationFee);
            if (fee > s.deposit) fee = s.deposit;
            s.deposit -= fee;
            _release(coin, fee, config.infrastructure);
            s.outcome = Outcome.Duplicate;
            emit Decided(id, Outcome.Duplicate);
            _reopen(b);
            return;
        }
        s.fix = fix;
        s.base = base;
        bt.epoch += 1;
        awards[b][bt.epoch] = Award(s.solver, fix, id, false, 0, false, 0, 0);
        _setState(b, State.Merged);
        emit Awarded(b, bt.epoch, s.solver);
    }

    /// Solved = merged (#251, L9): once the claimed fix's verdict is final and still a pass, the repository's head
    /// moves to it, if its base is still the head (a stale base reverts whole: the winner keeps its place, and may be
    /// rebased in place, `rebase`). Its instalments, counted from the finality, are then paid. Anyone, once.
    ///
    /// **Through a rebase (#310, RB5).** When the award's latest rebase check stands as a pass, the head moves to the
    /// rebased commit instead, once both verdicts are final, and records the rebase check's verdict; the original
    /// commit never becomes the head. Both commits count as paid, the bounty joins the winner's reputation, and the
    /// rebaser's claim closes with nothing gained.
    function merge(uint256 b) external nonReentrant {
        Bounty storage bt = _bounties[b];
        if (bt.state != State.Merged) revert WrongState(b, bt.state);
        Award storage a = awards[b][bt.epoch];
        uint256 id = a.sub;
        (Status st, bool pass,) = _verdict(id);
        if (st != Status.Final) revert NotYet();
        if (a.closed || a.merged || !pass) revert Refused(); // reversed: `sync` reopens the bounty
        Submission storage s = _submissions[id];
        uint256 m = id; // the check whose tree the head moves to
        uint256 r = a.rebase;
        if (r != 0) {
            (st, pass,) = _verdict(r);
            if (pass) {
                if (st != Status.Final) revert NotYet();
                m = r;
            }
        }
        Submission storage t = _submissions[m];
        heads.move(repo, t.base, t.fix, b, id, keccak256(abi.encode(address(panels), m)));
        a.merged = true;
        a.fix = t.fix;
        paidFix[s.fix] = true;
        paidFix[t.fix] = true;
        book.paid(id, s.solver, s.judged); // D29: its claim closes and its bounty joins its reputation; L6: active
        if (m != id) book.closeClaim(m);
        emit HeadMerged(b, bt.epoch, m, t.fix);
    }

    // ---------- payouts ----------

    /// Credits an award's earned instalments to its winner. Anyone can call it.
    function claimInstalments(uint256 b, uint256 epoch) public nonReentrant {
        _payInstalments(b, coin, epoch);
    }

    /// Once the bounty's outcome is final, pays what's still due from its pot: earned instalments, and if it was
    /// paid, the finder's fee, the registration refund and the winner's checks. Refunds by input can then start.
    function settle(uint256 b) external nonReentrant returns (bool) {
        return _settle(b, coin);
    }

    // ---------- delegated to RaceV3Annex, run in this contract's storage ----------

    // register, openBounty, report, withdrawIssue, withdraw, timeOut, rebase, release, payShadow, signal and finish run
    // in RaceV3Endings, which the annex reaches for any call it doesn't have (its fallback): one more DELEGATECALL,
    // still in this contract's storage. mergeExpired runs in the annex since #310 (EIP-170: the endings hold rebase).

    /// An issue's final registration check: a pass opens its bounty, a fail forfeits its stake
    /// (RaceV3Endings.openBounty).
    function openBounty(uint256) external returns (uint256) {
        _delegate();
    }

    /// The reporter withdraws an issue whose check no panel was seated for (RaceV3Endings.withdrawIssue).
    function withdrawIssue(uint256) external {
        _delegate();
    }

    /// The author of a rejected fix appeals once, with a failing-then-passing test and no stake (D24): the same
    /// commitment judged again by a fresh draw of the seated families, paying its metered checks (RaceV3Annex.appeal).
    function appeal(uint256, bytes32) external returns (uint256) {
        _delegate();
    }

    /// A failing-test dispute of a pass in its window, with its stake (D21; RaceV3Annex.dispute).
    function dispute(uint256, bytes32) external {
        _delegate();
    }

    /// A submission's open claim closes once its verdict is final or it ended (RaceV3Annex.close).
    function close(uint256) external {
        _delegate();
    }

    /// The solver withdraws a submission no panel was seated for: its deposit returns (a flat judges' fee goes to the
    /// sponsors' pool) (RaceV3Endings.withdraw).
    function withdraw(uint256) external {
        _delegate();
    }

    /// A submission no panel was seated for within resultDays ends; anyone (RaceV3Endings.timeOut).
    function timeOut(uint256) external {
        _delegate();
    }

    /// A winning fix not claimed, or a claimed one not merged, by its deadline (counted from its latest passing
    /// rebase's finality too), or whose solver's own rebase failed on the head: the bounty reopens
    /// (RaceV3Endings.mergeExpired).
    function mergeExpired(uint256) external {
        _delegate();
    }

    /// A claimed, unmerged award whose base is no longer the head, rebased in place onto the head (#310, RB2): a new
    /// check of the rebased commit, opened in the clear (RaceV3Endings.rebase).
    function rebase(uint256, bytes32, bytes32, bytes32) external returns (uint256) {
        _delegate();
    }

    /// A check Panels released for good, or one parked after a released round at its deadline: refunded (L19,
    /// RaceV3Endings.release).
    function release(uint256) external {
        _delegate();
    }

    /// A challenge of check `id`'s verdict, with its stake (RaceV3Annex.challenge).
    function challenge(uint256, bytes32) external {
        _delegate();
    }

    /// A filed challenge's panel decided: stakes and the panel's pay (RaceV3Annex.settleChallenge).
    function settleChallenge(uint256, uint256) external {
        _delegate();
    }

    /// A filed challenge that lapsed in Panels: its stake and cover back whole (L25, RaceV3Annex.settleLapse).
    function settleLapse(uint256) external {
        _delegate();
    }

    /// The race follows a verdict a challenge reversed (RaceV3Annex.sync).
    function sync(uint256) external {
        _delegate();
    }

    /// An audit's or an auditor's challenge panel paid, once (RaceV3Annex.payPanel).
    function payPanel(uint256) external {
        _delegate();
    }

    /// A revealed shadow's usage paid from the pool, once (RaceV3Endings.payShadow).
    function payShadow(uint256, uint256) external {
        _delegate();
    }

    /// FeesV3's queue signals from Panels' status (RaceV3Endings.signal).
    function signal(uint256) external {
        _delegate();
    }

    /// After finality: the deposit's rest back to its solver or reporter (a fix's flat judges' fee's rest, when
    /// `judgeFee` is above 0, to the sponsors' pool), and the fix's claim closed (RaceV3Endings.finish).
    function finish(uint256) external {
        _delegate();
    }

    function _one(bytes32 x) private pure returns (bytes32[] memory a) {
        a = new bytes32[](1);
        a[0] = x;
    }

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
