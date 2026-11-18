// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {RaceV3Base} from "./RaceV3Base.sol";
import {RaceV3Annex} from "./RaceV3Annex.sol";
import {Heads} from "../v2/Heads.sol";
import {Verdicts} from "../v2/Verdicts.sol";
import {IFeesV3} from "./IFeesV3.sol";
import {Panels} from "./Panels.sol";
import {IValidators} from "./IValidators.sol";
import {PoolV3} from "./PoolV3.sol";
import {Status} from "./PanelsBase.sol";

/// The race on-chain, v3 (proof-of-fix#138, task 3.5 of #132; design D1, D4, D5, D9, D13, D14; specs/judge-panels):
/// v2's race (RaceV2: bounties, attempts, sealed commitments, the rising price locked by the first attempt, the
/// earliest passing commitment wins, the claim, instalments, the clawback, Heads), judged by open validators through
/// `Panels` instead of v2's fixed `Verdicts`, and charged by `FeesV3` at market prices. No owner, no setter: Panels,
/// FeesV3 and the sponsors' pool (`PoolV3`) are bound once, from the constructor.
///
/// **Every check is a Panels submission under the same id.** A fix's submission, and an issue's registration check
/// (judged at CHECK_BOUNTY, the lowest tier): each posts FeesV3's deposit for K_MAX counted judges (k is fixed only at
/// the draw), FeesV3 fixes its prices (`open`), and Panels opens it with the bounty it's judged at: the price on offer
/// at the commitment. An award never pays more than that bounty, so a pledge made after the commitment can't put more
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
/// their seats' quoted usage). The deposit's rest returns after finality (`finish`).
///
/// **The verdict (D4).** The counted verdict decides the queue at once (`result`): the earliest commitment that passes,
/// once every earlier one is decided, wins, and its solver claims it (`claim`): it opens the commitment,
/// keccak256(abi.encode(fix, base, salt, solver)), and in a repository of the head registry the head moves to the fix
/// if `base` is still the head. Instalments start at the verdict's finality in Panels (`earned`): a k = 1 verdict held
/// for its challengers, or a window frozen by a challenge, pays nothing. A verdict reversed by a challenge before its
/// finality claws the award back and reopens the bounty (`sync`); a failed verdict reversed to a pass wins if the
/// bounty is still open, in its commitment's turn.
///
/// **Challenges (D4; specs/challenges).** Anyone challenges a verdict in its window (or held) with the published stake
/// plus its panel's worst-case cost (`challenge`); the race holds both. Upheld, both return and the panel is paid from
/// the deposit (and the pool); rejected, the panel is paid from the cover, its rest returns, and the stake goes to the
/// accused: the challenged panel's judges.
///
/// **FeesV3's queue signals** come from Panels' status (`signal`, anyone, and at each result): a waiting submission,
/// a stalled counted panel, and the validators seated on a counted panel.
///
/// Coin only, one coin: the version's fee coin (Panels' bounty limits are in it, and no price feed converts another).
/// RaceV3 runs its rarely called actions in RaceV3Annex (DELEGATECALL, its address fixed here), as RaceV2 did.
contract RaceV3 is RaceV3Base {
    address public immutable annex;

    error BadSignature();

    /// The head registry's genesis (S10) is deployed here with this contract fixed as its only mover; Panels, FeesV3
    /// and the pool are bound to this race once. The companion RaceV3Annex is deployed first (EIP-3860: RaceV3's
    /// initcode can't hold it) with the same Panels, pool, start and caps, which its fingerprint proves; `start_` is
    /// the same nonzero time for both.
    constructor(
        Config memory config_,
        uint256 bountyCap_,
        uint256 totalCap_,
        Panels panels_,
        PoolV3 pool_,
        uint256 start_,
        bytes32[] memory repos_,
        bytes32[] memory heads_,
        bytes32 constitution_,
        RaceV3Annex annex_
    )
        RaceV3Base(
            config_,
            bountyCap_,
            totalCap_,
            panels_,
            pool_,
            new Heads(Verdicts(address(panels_)), repos_, heads_, constitution_, address(this)),
            start_
        )
    {
        if (address(annex_).code.length == 0 || annex_.fingerprint() != _fingerprint()) revert BadParams();
        annex = address(annex_);
        panels_.bind();
        fees.bind();
        pool_.bind();
    }

    // ---------- views ----------

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
    /// and the funders who had pledged to its bounty by then. A judge whose key or operator is a party is recused.
    function isParty(uint256 id, address account) external view returns (bool) {
        Submission storage s = _submissions[id];
        if (account == address(0)) return false;
        if (account == s.solver || account == _issues[s.issue != 0 ? s.issue : _bounties[s.bounty].issue].reporter) {
            return true;
        }
        uint256 q = s.bounty == 0 ? 0 : pledgeOrder[s.bounty][account];
        return q != 0 && q <= s.pledges;
    }

    // ---------- issues ----------

    /// Anyone registers an issue in `repo`, with its registration check; `hidden` for hidden tests or a private
    /// repository, whose checks only TEE judges may take (RaceV3Annex.register).
    function register(bytes32, bool) external returns (uint256) {
        _delegate();
    }

    // ---------- bounties ----------

    /// A pledge in the fee coin, from anyone, while the bounty is open. A first pledge takes the next place in the
    /// bounty's funder order, which fixes which checks it is a party to.
    function pledge(uint256 b, uint256 amount) external nonReentrant {
        Bounty storage bt = _bounties[b];
        if (bt.state != State.Open) revert WrongState(b, bt.state);
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

    /// A sealed submission, keccak256(abi.encode(fix, base, salt, solver)), with its check deposit: Panels judges it at
    /// the price on offer now. While the bounty is open it joins the queue in commitment order; once it's won, it isn't
    /// checked and pays the evaluation fee.
    function commit(uint256 b, bytes32 commitment) external nonReentrant returns (uint256 id) {
        Bounty storage bt = _bounties[b];
        if (bt.state == State.Won || bt.state == State.Merged || bt.state == State.Paid) {
            _collect(coin, msg.sender, _units(config.evaluationFee), config.infrastructure);
            emit TooLate(b, msg.sender);
            return 0;
        }
        if (bt.state != State.Open) revert WrongState(b, bt.state);
        _stopAttempt(b, msg.sender);
        _lock(b);
        id = _submit(b, msg.sender, commitment);
    }

    // ---------- the judges' reports and the result ----------

    /// Seat `key`'s metered usage on panel `pid` (any kind), signed by `key` as a registry statement on the subject
    /// keccak256(USAGE_TAG, this race, pid, key) over keccak256(abi.encode(u)) (two usages for one seat are provable
    /// equivocation). Its receipt must be the seat's on-chain receipt. A replacement in the same seat reports its own.
    function report(uint256 pid, address key, IFeesV3.Usage calldata u, bytes calldata sig) external {
        address[] memory keys = panels.judges(pid);
        uint256 slot = keys.length;
        for (uint256 i; i < keys.length; ++i) {
            if (keys[i] == key && key != address(0)) slot = i;
        }
        if (slot == keys.length || reportedBy[pid][slot] == key) revert Refused();
        bytes memory x = _seat(pid, slot);
        if (_w(x, X_RECEIPTED) == 0 || bytes32(_w(x, X_RECEIPT)) != u.receipt) revert Refused();
        bytes32 subject = keccak256(abi.encode(USAGE_TAG, address(this), pid, key));
        if (ECDSA.recover(registry.statementDigest(subject, keccak256(abi.encode(u))), sig) != key) {
            revert BadSignature();
        }
        _usage[pid][slot] = u;
        reportedBy[pid][slot] = key;
        emit Reported(pid, slot, key, u.receipt);
    }

    /// The counted verdict of check `id`, once Panels has counted it and its reports are in: FeesV3 pays each counted
    /// judge and the caller's gas from the deposit (judges first), FeesV3 hears who was seated, and the verdict decides
    /// the queue. Anyone, once.
    function result(uint256 id) external nonReentrant {
        uint256 g = gasleft();
        Submission storage s = _submissions[id];
        bytes memory ps = _sub(id);
        if (s.solver == address(0) || s.paid) revert Refused();
        Status st = Status(_w(ps, S_STATUS));
        if (st != Status.Held && st != Status.Window && st != Status.Final) revert NotYet();
        uint256 pid = _w(ps, S_PID);
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

    /// Solved = merged: the winner's commitment opened. In a repository of the head registry the head moves to `fix`
    /// only if `base` is the head (a stale base reverts whole: the winner keeps its place until mergeBy). Its award
    /// starts; its instalments start at its verdict's finality. A fix already paid on a bounty is a duplicate: the
    /// evaluation fee from the deposit's rest, and the bounty reopens. Anyone holding the opening may call it.
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
        bytes32 repo = _issues[bt.issue].repo;
        if (repo != bytes32(0)) heads.move(repo, base, fix, b, id, keccak256(abi.encode(address(panels), id)));
        s.fix = fix;
        paidFix[fix] = true;
        bt.epoch += 1;
        awards[b][bt.epoch] = Award(s.solver, fix, id, false, 0);
        _setState(b, State.Merged);
        emit Awarded(b, bt.epoch, s.solver);
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

    /// An issue's final registration check: a pass opens its bounty, a fail forfeits its stake
    /// (RaceV3Annex.openBounty).
    function openBounty(uint256) external returns (uint256) {
        _delegate();
    }

    /// The reporter withdraws an issue whose check no panel was seated for (RaceV3Annex.withdrawIssue).
    function withdrawIssue(uint256) external {
        _delegate();
    }

    /// The author of a failed submission appeals once: the same commitment judged again (RaceV3Annex.appeal).
    function appeal(uint256) external returns (uint256) {
        _delegate();
    }

    /// The solver withdraws a submission no panel was seated for (RaceV3Annex.withdraw).
    function withdraw(uint256) external {
        _delegate();
    }

    /// A submission no panel was seated for within resultDays ends; anyone (RaceV3Annex.timeOut).
    function timeOut(uint256) external {
        _delegate();
    }

    /// A winning fix not claimed by its deadline: the bounty reopens (RaceV3Annex.mergeExpired).
    function mergeExpired(uint256) external {
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

    /// The race follows a verdict a challenge reversed (RaceV3Annex.sync).
    function sync(uint256) external {
        _delegate();
    }

    /// An audit's or an auditor's challenge panel paid, once (RaceV3Annex.payPanel).
    function payPanel(uint256) external {
        _delegate();
    }

    /// A revealed shadow's usage paid from the pool, once (RaceV3Annex.payShadow).
    function payShadow(uint256, uint256) external {
        _delegate();
    }

    /// FeesV3's queue signals from Panels' status (RaceV3Annex.signal).
    function signal(uint256) external {
        _delegate();
    }

    /// The deposit's rest back to the solver after finality (RaceV3Annex.finish).
    function finish(uint256) external {
        _delegate();
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
