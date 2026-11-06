// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {OraclesV2} from "./helpers/OraclesV2.sol";
import {RaceV2 as Race} from "../../src/v2/RaceV2.sol";
import {RaceV2Base} from "../../src/v2/RaceV2Base.sol";
import {Heads} from "../../src/v2/Heads.sol";
import {MockCoin} from "../mocks/MockCoin.sol";

/// proof-of-fix#85 task 5.2 (design S1, S11): the verdict v2 and the head registry. Spec scenarios:
/// - oracle-network "A verdict binds its base commit and its receipt": "A verdict checked on an old head", "An issue
///   verdict offered as a constitution verdict";
/// - self-healing "The canonical head on-chain": "The head moves", "A stale verdict".
contract VerdictV2Test is OraclesV2 {
    uint256 constant C = 1e6;

    Race race;
    Heads heads;
    MockCoin usd;
    address reporter = makeAddr("reporter");
    address alice = makeAddr("alice");
    address solver1 = makeAddr("solver1");
    address solver2 = makeAddr("solver2");

    bytes32 constant FIX_A = bytes32(bytes20(keccak256("fix A")));
    bytes32 constant FIX_B = bytes32(bytes20(keccak256("fix B")));
    bytes32 constant FIX_B_REBASED = bytes32(bytes20(keccak256("fix B, rebased on fix A")));

    event HeadMoved(
        bytes32 indexed repo, bytes32 indexed base, bytes32 indexed commit, uint256 bounty, uint256 submission, bytes32 verdict
    );

    function setUp() public {
        usd = new MockCoin("Mock USD", "mUSD", 6);
        address[] memory feeCoins = new address[](1);
        feeCoins[0] = address(usd);
        _makeOracles(3, 2);
        RaceV2Base.Config memory c;
        c.infrastructure = makeAddr("infra");
        c.insurance = makeAddr("insurance");
        c.registrationFee = 2e6;
        c.issueStake = 5e6;
        c.attemptFee = 0.5e6;
        c.evaluationFee = 2e6;
        c.checkDeposit = 6.6e6;
        c.appealFee = 2e6;
        c.appealDeposit = 5e6;
        c.startPriceBps = 5_000;
        c.riseBpsPerDay = 1_000;
        c.finderFeeBps = 1_765;
        c.idleDays = 28;
        c.resultDays = 7;
        c.mergeDays = 14;
        c.windowDays = 7;
        c.releaseEveryDays = 7;
        c.instalments = 4;
        race = _newRace(c, feeCoins, 1_000, 100_000);
        heads = race.heads();
    }

    // ---------- helpers ----------

    function _fund(address who, uint256 amount) internal {
        usd.mint(who, amount);
        vm.prank(who);
        usd.approve(address(race), type(uint256).max);
    }

    /// An accepted issue in `repo` (0: outside the registry), its bounty open with 100 credits.
    function _openBounty(bytes32 repo) internal returns (uint256 b) {
        _fund(reporter, 7 * C);
        vm.prank(reporter);
        uint256 i = race.register(address(usd), repo);
        b = _accept(race, i);
        _fund(alice, 100 * C);
        vm.prank(alice);
        race.pledge(b, address(usd), 100 * C);
    }

    function _commit(address who, uint256 b, bytes32 fix) internal returns (uint256) {
        _fund(who, 10 * C);
        vm.prank(who);
        return race.commit(b, keccak256(abi.encode(fix, bytes32("salt"), who)), address(usd));
    }

    /// A bounty in REPO won by `who` with `fix`, its result checked on the current head.
    function _won(address who, bytes32 fix) internal returns (uint256 b, uint256 id) {
        b = _openBounty(REPO);
        id = _commit(who, b, fix);
        _result(race, id, RaceV2Base.Outcome.Pass, fix, new RaceV2Base.Fee[](0));
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Won));
    }

    function _sign(RaceV2Base.Verdict memory v, uint256 weight) internal view returns (bytes[] memory) {
        return _sigs(race, _mergedHash(v, weight));
    }

    // ---------- the head moves (self-healing "The head moves") ----------

    /// A verdict checked on the head moves it to the fix, recorded with its bounty, submission and verdict.
    function test_headMovesOnAVerdictCheckedOnTheHead() public {
        (uint256 b, uint256 id) = _won(solver1, FIX_A);
        (RaceV2Base.Verdict memory v, bytes[] memory sigs) = _signMerged(race, b);
        assertEq(v.base, GENESIS_HEAD);
        vm.expectEmit(address(heads));
        emit HeadMoved(REPO, GENESIS_HEAD, FIX_A, b, id, _verdictHash(v));
        race.merged(v, 0, sigs);
        Heads.Head memory h = heads.head(REPO);
        assertEq(h.commit, FIX_A);
        assertEq(h.bounty, b);
        assertEq(h.submission, id);
        assertEq(h.verdict, _verdictHash(v));
        assertEq(h.constitution, GENESIS_CONSTITUTION);
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Merged));
        (, bytes32 fix,,,) = race.awards(b, 1);
        assertEq(fix, FIX_A);
        assertTrue(race.paidFix(FIX_A));
    }

    /// The result records the base it was checked on and the receipt's hash (S11).
    function test_resultRecordsBaseAndReceipt() public {
        uint256 b = _openBounty(REPO);
        uint256 id = _commit(solver1, b, FIX_A);
        (RaceV2Base.Verdict memory v, bytes[] memory sigs) = _signResult(race, id, RaceV2Base.Outcome.Fail, FIX_A, new RaceV2Base.Fee[](0));
        race.result(v, new RaceV2Base.Fee[](0), sigs);
        RaceV2Base.Submission memory s = race.submission(id);
        assertEq(s.base, GENESIS_HEAD);
        assertEq(s.receipt, v.receiptHash);
        assertEq(s.fix, FIX_A);
    }

    /// The receipt's hash, the base and the seed are signed: a relayer can't swap any of them.
    function test_receiptBaseAndSeedAreSigned() public {
        uint256 b = _openBounty(REPO);
        uint256 id = _commit(solver1, b, FIX_A);
        (RaceV2Base.Verdict memory v, bytes[] memory sigs) = _signResult(race, id, RaceV2Base.Outcome.Pass, FIX_A, new RaceV2Base.Fee[](0));
        RaceV2Base.Verdict memory t = _copy(v);
        t.receiptHash = keccak256("another receipt");
        vm.expectRevert(RaceV2Base.NotOracle.selector);
        race.result(t, new RaceV2Base.Fee[](0), sigs);
        t = _copy(v);
        t.base = FIX_B;
        vm.expectRevert(RaceV2Base.NotOracle.selector);
        race.result(t, new RaceV2Base.Fee[](0), sigs);
        t = _copy(v);
        t.seed = keccak256("another draw");
        vm.expectRevert(RaceV2Base.Refused.selector); // the seed must be the submission's, fixed at its commit (5.3)
        race.result(t, new RaceV2Base.Fee[](0), sigs);
        race.result(v, new RaceV2Base.Fee[](0), sigs);
    }

    // ---------- stale verdicts (oracle-network "A verdict checked on an old head", self-healing "A stale verdict") ----------

    /// Two fixes won on the genesis head: the first merge moves the head, so the second's verdict is stale. It's
    /// refused whole (nothing spent, nothing moved), the winner keeps its place and locked share, and a verdict on the
    /// rebased fix, checked on the new head, merges it.
    function test_staleVerdictRefusedAndTheWinnerKeepsItsPlace() public {
        (uint256 b1,) = _won(solver1, FIX_A);
        (uint256 b2, uint256 id2) = _won(solver2, FIX_B);
        (RaceV2Base.Verdict memory stale, bytes[] memory staleSigs) = _signMerged(race, b2); // checked on GENESIS_HEAD
        _merged(race, b1);
        assertEq(heads.head(REPO).commit, FIX_A);

        uint256 lock = race.bounty(b2).lockBps;
        uint256 mergeBy = race.bounty(b2).mergeBy;
        vm.expectRevert(abi.encodeWithSelector(Heads.StaleVerdict.selector, REPO, GENESIS_HEAD, FIX_A));
        race.merged(stale, 0, staleSigs);
        assertEq(heads.head(REPO).commit, FIX_A); // the head didn't move
        RaceV2Base.Bounty memory bt = race.bounty(b2);
        assertEq(uint256(bt.state), uint256(RaceV2Base.State.Won)); // still won,
        assertEq(bt.winner, id2); // by the same submission,
        assertEq(bt.lockBps, lock); // at the same locked share,
        assertEq(bt.mergeBy, mergeBy); // with the same deadline
        assertEq(bt.epoch, 0);
        // The stale verdict's digest wasn't spent (the revert undid it), but it can never pass: its base is gone.
        assertFalse(race.verdicts().used(address(race), _digest(race, _mergedHash(stale, 0))));

        // The solver rebases; the judges check the rebased fix on the new head and sign its merge.
        RaceV2Base.Verdict memory rebased = _copy(stale);
        rebased.base = FIX_A;
        rebased.fix = FIX_B_REBASED;
        rebased.receiptHash = keccak256("the rebased fix's receipt");
        rebased.nonce = _nonce();
        race.merged(rebased, 0, _sign(rebased, 0));
        Heads.Head memory h = heads.head(REPO);
        assertEq(h.commit, FIX_B_REBASED);
        assertEq(h.bounty, b2);
        assertEq(h.submission, id2);
        assertEq(uint256(race.bounty(b2).state), uint256(RaceV2Base.State.Merged));
        (address winner, bytes32 fix,,,) = race.awards(b2, 1);
        assertEq(winner, solver2);
        assertEq(fix, FIX_B_REBASED);
        assertTrue(race.paidFix(FIX_B)); // the checked fix and its rebased commit both count as paid (D10)
        assertTrue(race.paidFix(FIX_B_REBASED));
    }

    /// A pass checked on an old base still wins its place in the queue; only the head's move needs the current base.
    function test_aPassOnAnOldBaseStillWins() public {
        (uint256 b1,) = _won(solver1, FIX_A);
        _merged(race, b1);
        uint256 b2 = _openBounty(REPO);
        uint256 id = _commit(solver2, b2, FIX_B);
        RaceV2Base.Verdict memory v = _verdict(race, b2, id, RaceV2Base.Outcome.Pass, FIX_B);
        v.base = GENESIS_HEAD; // checked before fix A landed
        race.result(v, new RaceV2Base.Fee[](0), _sigs(race, _resultHash(v, new RaceV2Base.Fee[](0))));
        assertEq(race.bounty(b2).winner, id);
        assertEq(race.submission(id).base, GENESIS_HEAD);
    }

    // ---------- the tier (oracle-network "An issue verdict offered as a constitution verdict") ----------

    /// Only issue-tier verdicts count here, and the tier is signed: a constitution-tier verdict is refused, and an
    /// issue verdict relabelled (or the reverse) no longer matches its signatures.
    function test_theTierIsSignedAndChecked() public {
        uint256 b = _openBounty(REPO);
        uint256 id = _commit(solver1, b, FIX_A);
        RaceV2Base.Verdict memory v = _verdict(race, b, id, RaceV2Base.Outcome.Pass, FIX_A);
        v.tier = TIER_CONSTITUTION;
        bytes[] memory constitutionSigs = _sigs(race, _resultHash(v, new RaceV2Base.Fee[](0)));
        vm.expectRevert(RaceV2Base.WrongTier.selector); // a constitution verdict isn't taken by the race
        race.result(v, new RaceV2Base.Fee[](0), constitutionSigs);
        v.tier = TIER_ISSUE; // relabelled as an issue verdict: the signatures were for tier 2
        vm.expectRevert(RaceV2Base.NotOracle.selector);
        race.result(v, new RaceV2Base.Fee[](0), constitutionSigs);
        bytes[] memory issueSigs = _sigs(race, _resultHash(v, new RaceV2Base.Fee[](0)));
        v.tier = TIER_CONSTITUTION; // and an issue verdict offered as a constitution one is refused on its tier
        vm.expectRevert(RaceV2Base.WrongTier.selector);
        race.result(v, new RaceV2Base.Fee[](0), issueSigs);
        v.tier = TIER_ISSUE;
        race.result(v, new RaceV2Base.Fee[](0), issueSigs);
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Won));
    }

    // ---------- the repository ----------

    /// A verdict names the bounty's repository: another one is refused, signed or not.
    function test_theRepositoryMustBeTheBountys() public {
        (uint256 b,) = _won(solver1, FIX_A);
        (RaceV2Base.Verdict memory v,) = _signMerged(race, b);
        v.repo = bytes32(0); // as if outside the registry
        bytes[] memory sigs = _sign(v, 0);
        vm.expectRevert(RaceV2Base.Refused.selector);
        race.merged(v, 0, sigs);
        assertEq(heads.head(REPO).commit, GENESIS_HEAD);
    }

    /// An issue registers in a repository of the registry or outside it (0), never in an unknown one.
    function test_registerInAKnownRepositoryOnly() public {
        _fund(reporter, 7 * C);
        vm.prank(reporter);
        vm.expectRevert(RaceV2Base.Refused.selector);
        race.register(address(usd), keccak256("not in the registry"));
        vm.prank(reporter);
        uint256 i = race.register(address(usd), REPO);
        assertEq(race.issue(i).repo, REPO);
    }

    /// Outside the registry (S8: a project with human maintainers) a merge records the fix and moves no head.
    function test_outsideTheRegistryNoHeadMoves() public {
        uint256 b = _openBounty(bytes32(0));
        uint256 id = _commit(solver1, b, FIX_A);
        _result(race, id, RaceV2Base.Outcome.Pass, FIX_A, new RaceV2Base.Fee[](0));
        _merged(race, b);
        assertEq(heads.head(REPO).commit, GENESIS_HEAD);
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Merged));
        (, bytes32 fix,,,) = race.awards(b, 1);
        assertEq(fix, FIX_A);
    }

    // ---------- the merge ----------

    /// A merge verdict must pass, name the winner and a fix.
    function test_aMergeMustBeAPassOfTheWinner() public {
        (uint256 b,) = _won(solver1, FIX_A);
        (RaceV2Base.Verdict memory v,) = _signMerged(race, b);
        RaceV2Base.Verdict memory t = _copy(v);
        t.outcome = uint8(RaceV2Base.Outcome.Fail);
        bytes[] memory sigs = _sign(t, 0);
        vm.expectRevert(RaceV2Base.Refused.selector);
        race.merged(t, 0, sigs);
        t = _copy(v);
        t.fix = bytes32(0);
        sigs = _sign(t, 0);
        vm.expectRevert(RaceV2Base.Refused.selector);
        race.merged(t, 0, sigs);
        t = _copy(v);
        t.fix = GENESIS_HEAD; // the base itself: no change
        sigs = _sign(t, 0);
        vm.expectRevert(Heads.BadParams.selector);
        race.merged(t, 0, sigs);
        race.merged(v, 0, _sign(v, 0));
    }

    // ---------- the registry's writes ----------

    /// Only the race that created it moves a head: no one else, the owner and the oracles included.
    function test_onlyTheRaceMovesAHead() public {
        assertEq(heads.mover(), address(race));
        vm.expectRevert(Heads.NotMover.selector);
        heads.move(REPO, GENESIS_HEAD, FIX_A, 1, 1, bytes32(0));
        vm.prank(oracleSet[0]);
        vm.expectRevert(Heads.NotMover.selector);
        heads.move(REPO, GENESIS_HEAD, FIX_A, 1, 1, bytes32(0));
        assertEq(heads.head(REPO).commit, GENESIS_HEAD);
    }

    /// Too few signatures on a merge: the head doesn't move.
    function test_aMergeNeedsTheQuorum() public {
        (uint256 b,) = _won(solver1, FIX_A);
        (RaceV2Base.Verdict memory v,) = _signMerged(race, b);
        uint256[] memory one = new uint256[](1);
        one[0] = oracleSecrets[0];
        RaceV2Base.Signed memory a = _signWith(race, _mergedHash(v, 0), v.nonce, one);
        vm.expectRevert(RaceV2Base.TooFewSignatures.selector);
        race.merged(v, 0, a.sigs);
        assertEq(heads.head(REPO).commit, GENESIS_HEAD);
    }

    /// Gas of a merge that moves a head, against one outside the registry (reported in the PR).
    function test_gasPerMerge() public {
        (uint256 b,) = _won(solver1, FIX_A);
        (RaceV2Base.Verdict memory v, bytes[] memory sigs) = _signMerged(race, b);
        race.merged(v, 0, sigs);
        emit log_named_uint("merged, head moved, 2 of 3", vm.lastFrameGas().gasTotalUsed);
        uint256 b2 = _openBounty(bytes32(0));
        uint256 id = _commit(solver2, b2, FIX_B);
        _result(race, id, RaceV2Base.Outcome.Pass, FIX_B, new RaceV2Base.Fee[](0));
        (v, sigs) = _signMerged(race, b2);
        race.merged(v, 0, sigs);
        emit log_named_uint("merged, outside the registry, 2 of 3", vm.lastFrameGas().gasTotalUsed);
    }
}
