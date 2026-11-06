// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {Test} from "forge-std/Test.sol";
import {OraclesV2} from "./helpers/OraclesV2.sol";
import {Baskets} from "../../src/Baskets.sol";
import {RaceV2 as Race} from "../../src/v2/RaceV2.sol";
import {RaceV2Base} from "../../src/v2/RaceV2Base.sol";
import {IFees} from "../../src/v2/IFees.sol";
import {Verdicts} from "../../src/v2/Verdicts.sol";
import {genesis} from "./helpers/GenesisV2.sol";
import {MockCoin} from "../mocks/MockCoin.sol";
import {FrozenCoin} from "../mocks/FrozenCoin.sol";
import {LyingCoin} from "../mocks/LyingCoin.sol";

/// v2 (proof-of-fix#85, task 5.1): v1's Race suite ported to RaceV2 (coin only, the quorum in Verdicts). Every v1
/// test runs unchanged except the token's (v2 has none): the inflation rule is kept on the coin side (the finder's
/// fee), and the oracle set's checks moved to Verdicts.
/// v1: tasks 2.2 and 2.4: the race (spec "The race on-chain", "Solved means merged"; bounty-market "One fix, one payout",
/// "Idle bounties sunset" and "Anyone opens a bounty, the market funds it"). This test contract is the phase-1 oracle.
contract RaceV2Test is OraclesV2 {
    uint256 constant C = 1e6; // one credit in a 6-decimal coin
    uint256 constant BPS = 10_000;
    uint256 constant FINDER = 1_765; // the reporter's fee, of the price: 15 % of the payout (D12)

    Race race;
    MockCoin usd; // the fee coin
    MockCoin eth; // another basket coin, 18 decimals
    address infra = makeAddr("infra");
    address insurance = makeAddr("insurance");
    address oracleA = makeAddr("oracleA");
    address reporter = makeAddr("reporter");
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");
    address solver1 = makeAddr("solver1");
    address solver2 = makeAddr("solver2");

    function setUp() public {
        usd = new MockCoin("Mock USD", "mUSD", 6);
        eth = new MockCoin("Mock ETH", "mETH", 18);
        address[] memory feeCoins = new address[](1);
        feeCoins[0] = address(usd);
        _makeOracles(3, 2);
        race = _newRace(_config(), feeCoins, 1_000, 100_000);
    }

    /// pof's defaults for the race, with no market fee (D9).
    function _config() internal view returns (RaceV2Base.Config memory c) {
        c.infrastructure = infra;
        c.insurance = insurance;
        c.registrationFee = 2e6;
        c.issueStake = 5e6;
        c.attemptFee = 0.5e6;
        c.evaluationFee = 2e6;
        c.checkDeposit = 6.6e6;
        c.appealFee = 2e6;
        c.appealDeposit = 5e6;
        c.startPriceBps = 5_000;
        c.riseBpsPerDay = 1_000;
        c.finderFeeBps = FINDER;
        c.idleDays = 28;
        c.resultDays = 7;
        c.mergeDays = 14;
        c.windowDays = 7;
        c.releaseEveryDays = 7;
        c.instalments = 4;
    }

    // ---------- helpers ----------

    function _toDay(uint256 d) internal {
        vm.warp(race.start() + d * 1 days);
    }

    function _fund(address who, MockCoin coin, uint256 amount) internal {
        coin.mint(who, amount);
        vm.prank(who);
        coin.approve(address(race), type(uint256).max);
    }

    function _register() internal returns (uint256) {
        _fund(reporter, usd, 7 * C);
        vm.prank(reporter);
        return race.register(address(usd), bytes32(0));
    }

    /// An issue the registration check accepted, its bounty open with 100 credits of usd from alice.
    function _openBounty() internal returns (uint256 b) {
        b = _accept(race, _register());
        _pledge(alice, usd, b, 100 * C);
    }

    function _pledge(address who, MockCoin coin, uint256 b, uint256 amount) internal {
        _fund(who, coin, amount);
        vm.prank(who);
        race.pledge(b, address(coin), amount);
    }

    function _commit(address who, uint256 b, bytes32 fix) internal returns (uint256) {
        _fund(who, usd, 10 * C);
        vm.prank(who);
        return race.commit(b, keccak256(abi.encode(fix, bytes32("salt"), who)), address(usd));
    }

    function _noRepos() internal pure returns (bytes32[] memory) {
        return new bytes32[](0);
    }

    function _noFees() internal pure returns (RaceV2Base.Fee[] memory) {
        return new RaceV2Base.Fee[](0);
    }

    function _decide(uint256 id, RaceV2Base.Outcome o, bytes32 fix) internal {
        _result(race, id, o, fix, _noFees());
    }

    function _owed(address who, MockCoin coin) internal view returns (uint256) {
        return race.owed(who, address(coin));
    }

    function _assertBooks(MockCoin coin) internal view {
        assertEq(
            coin.balanceOf(address(race)),
            race.totalHeld(address(coin)) + race.totalOwed(address(coin)) + race.totalDeposits(address(coin))
        );
    }

    // ---------- registration and pledges ----------

    function test_registerPaysTheFeeAndHoldsTheStake() public {
        uint256 i = _register();
        assertEq(_owed(infra, usd), 2 * C);
        assertEq(race.totalDeposits(address(usd)), 5 * C);
        assertEq(race.issue(i).reporter, reporter);
        _assertBooks(usd);
    }

    function test_feesOnlyInFeeCoins() public {
        _fund(reporter, eth, 10 ether);
        vm.prank(reporter);
        vm.expectRevert(abi.encodeWithSelector(RaceV2Base.NotFeeCoin.selector, address(eth)));
        race.register(address(eth), bytes32(0));
    }

    /// D12: the registration check opens the bounty at once, with no target; anyone funds it, in any coin, while it's
    /// open, and the price rises over whatever it holds.
    function test_checkOpensItAndTheMarketFundsIt() public {
        _toDay(3);
        uint256 b = _accept(race, _register());
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Open));
        assertEq(race.bounty(b).offerFrom, 3);
        assertEq(race.lockedPrice(b, address(usd)), 0); // nothing in it yet: nothing to win
        _pledge(alice, usd, b, 60 * C);
        _toDay(4);
        _pledge(bob, eth, b, 5 ether);
        assertEq(race.held(b, address(eth)), 5 ether);
        _win(b, solver1, "fix1");
        _fund(bob, usd, 1 * C);
        vm.prank(bob);
        vm.expectRevert(abi.encodeWithSelector(RaceV2Base.WrongState.selector, b, RaceV2Base.State.Won));
        race.pledge(b, address(usd), 1 * C); // won: closed to funding
    }

    function test_onlyTheCheckOpensABounty() public {
        uint256 i = _register();
        bytes32 n = _nonce();
        uint256[] memory outsider = new uint256[](2);
        outsider[0] = 0xA11CE;
        outsider[1] = 0xB0B;
        vm.prank(alice);
        vm.expectRevert(RaceV2Base.NotOracle.selector); // signed by keys that aren't the oracles'
        race.accept(i, 0, _signWith(race, _acceptHash(i, n), n, outsider));
        vm.prank(alice); // anyone relays a signed result
        _accept(race, i);
        vm.expectRevert(RaceV2Base.Refused.selector); // once
        _accept(race, i);
    }

    /// bounty-market scenario "A similar issue is open": no bounty, the fee spent on the check, the stake back.
    function test_similarOpenIssueRefused() public {
        uint256 b = _openBounty();
        uint256 i2 = _register();
        _refuseSimilar(race, i2, b);
        assertEq(uint256(race.issue(i2).state), uint256(RaceV2Base.IssueState.Returned));
        assertEq(_owed(reporter, usd), 5 * C); // the second stake back
        assertEq(_owed(infra, usd), 4 * C); // both checks paid
        vm.expectRevert(RaceV2Base.Refused.selector);
        _accept(race, i2);
        _assertBooks(usd);
    }

    /// bounty-market scenario "After it closes": a new bounty may open once the similar one is closed.
    function test_similarClosedIssueOpens() public {
        uint256 b = _openBounty();
        _toDay(28);
        race.sunset(b);
        uint256 i2 = _register();
        vm.expectRevert(abi.encodeWithSelector(RaceV2Base.WrongState.selector, b, RaceV2Base.State.Unsolved));
        _refuseSimilar(race, i2, b);
        assertEq(uint256(race.bounty(_accept(race, i2)).state), uint256(RaceV2Base.State.Open));
    }

    function test_reporterWithdrawsBeforeTheCheck() public {
        uint256 i = _register();
        vm.prank(reporter);
        race.withdrawIssue(i);
        assertEq(_owed(reporter, usd), 5 * C);
        vm.expectRevert(RaceV2Base.Refused.selector);
        _accept(race, i);
    }

    function test_junkForfeitsTheStakeAndRefunds() public {
        uint256 b = _openBounty();
        _junk(race, race.bounty(b).issue);
        assertEq(_owed(insurance, usd), 5 * C);
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Refunded));
        vm.prank(alice);
        race.claimRefund(b, address(usd));
        assertEq(_owed(alice, usd), 100 * C);
    }

    // ---------- the price ----------

    /// Spec scenario "The price locked": the first paid attempt on the third day locks 70 % of each coin's cap.
    function test_priceLockedOnTheThirdDay() public {
        uint256 b = _openBounty();
        _pledge(bob, eth, b, 10 ether);
        _toDay(2);
        assertEq(race.offerBps(b), 7_000);
        _fund(solver1, usd, 1 * C);
        vm.prank(solver1);
        race.attempt(b, address(usd));
        assertEq(_owed(infra, usd), 2 * C + C / 2); // registration + attempt fee
        _toDay(9);
        assertEq(race.offerBps(b), 7_000); // locked
        // usd: (100 - 2 registration) * BPS / (BPS + FINDER), eth: 10 * BPS / (BPS + FINDER); 70 % of each.
        assertEq(race.lockedPrice(b, address(usd)), (98 * C * BPS / (BPS + FINDER)) * 7_000 / BPS);
        assertEq(race.lockedPrice(b, address(eth)), (10 ether * BPS / (BPS + FINDER)) * 7_000 / BPS);
    }

    function test_priceRisesToTheWhole() public {
        uint256 b = _openBounty();
        _toDay(30);
        assertEq(race.offerBps(b), BPS);
    }

    /// A top-up after the lock raises the cap but not the locked price.
    /// D14: the share is locked, not the amount, so a pledge after the lock raises the price at that share.
    function test_topUpAfterTheLockRaisesThePrice() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, "fix1"); // locks 50 % on day 0
        _decide(id, RaceV2Base.Outcome.Fail, "fix1");
        _toDay(3);
        _pledge(bob, usd, b, 50 * C);
        assertEq(race.offerBps(b), 5_000);
        assertEq(race.lockedPrice(b, address(usd)), (148 * C * BPS / (BPS + FINDER)) * 5_000 / BPS);
        _win(b, solver2, "fix2");
        _merged(race, b);
        assertEq(race.priceOf(b, address(usd), 1), (148 * C * BPS / (BPS + FINDER)) * 5_000 / BPS);
    }

    // ---------- submissions ----------

    /// Spec scenario "Ordered by commitment": the earlier commitment wins whatever order the results arrive in.
    function test_orderedByCommitment() public {
        uint256 b = _openBounty();
        uint256 first = _commit(solver1, b, "fix1");
        vm.roll(block.number + 1);
        uint256 second = _commit(solver2, b, "fix2");
        _decide(second, RaceV2Base.Outcome.Pass, "fix2");
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Open)); // waits for the earlier one
        _decide(first, RaceV2Base.Outcome.Pass, "fix1");
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Won));
        assertEq(race.bounty(b).winner, first);
    }

    function test_earlierFailLetsTheNextPassWin() public {
        uint256 b = _openBounty();
        uint256 first = _commit(solver1, b, "fix1");
        uint256 second = _commit(solver2, b, "fix2");
        _decide(second, RaceV2Base.Outcome.Pass, "fix2");
        _decide(first, RaceV2Base.Outcome.Fail, "fix1");
        assertEq(race.bounty(b).winner, second);
    }

    function test_depositPaysTheChecksAndTheRestReturns() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, "fix1");
        assertEq(race.totalDeposits(address(usd)), 5 * C + 6.6e6);
        RaceV2Base.Fee[] memory fees = new RaceV2Base.Fee[](2);
        fees[0] = RaceV2Base.Fee(oracleA, 1.5e6);
        fees[1] = RaceV2Base.Fee(infra, 1e6);
        _result(race, id, RaceV2Base.Outcome.Fail, "fix1", fees);
        assertEq(_owed(oracleA, usd), 1.5e6);
        assertEq(_owed(solver1, usd), 6.6e6 - 2.5e6);
        _assertBooks(usd);
    }

    function test_feesAboveTheDepositRefused() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, "fix1");
        RaceV2Base.Fee[] memory fees = new RaceV2Base.Fee[](1);
        fees[0] = RaceV2Base.Fee(oracleA, 6.6e6 + 1);
        (RaceV2Base.Verdict memory v, bytes[] memory sigs) = _signResult(race, id, RaceV2Base.Outcome.Fail, "fix1", fees);
        vm.expectRevert(RaceV2Base.Refused.selector);
        race.result(v, fees, sigs);
    }

    function test_duplicatePaysTheEvaluationFee() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, "fix1");
        _decide(id, RaceV2Base.Outcome.Duplicate, "fix1");
        assertEq(_owed(infra, usd), 2 * C + 2 * C);
        assertEq(_owed(solver1, usd), 4.6e6);
    }

    /// #64: arriving after the bounty is won costs the evaluation fee, unchecked.
    function test_lateSubmissionPaysTheFee() public {
        uint256 b = _openBounty();
        _decide(_commit(solver1, b, "fix1"), RaceV2Base.Outcome.Pass, "fix1");
        _fund(solver2, usd, 10 * C);
        vm.prank(solver2);
        uint256 id = race.commit(b, bytes32("late"), address(usd));
        assertEq(id, 0);
        assertEq(usd.balanceOf(solver2), 8 * C);
        assertEq(_owed(infra, usd), 2 * C + 2 * C);
    }

    // ---------- signed results (task 3.1, D3) ----------

    /// Spec scenario "Too few signatures": refused, and the submission's state doesn't change.
    function test_tooFewSignaturesRefused() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, "fix1");
        uint256[] memory one = new uint256[](1);
        one[0] = oracleSecrets[0];
        RaceV2Base.Verdict memory v = _verdict(race, b, id, RaceV2Base.Outcome.Pass, "fix1");
        RaceV2Base.Signed memory a = _signWith(race, _resultHash(v, _noFees()), v.nonce, one);
        vm.expectRevert(RaceV2Base.TooFewSignatures.selector);
        race.result(v, _noFees(), a.sigs);
        assertEq(uint256(race.submission(id).outcome), uint256(RaceV2Base.Outcome.None));
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Open));
    }

    /// Spec scenario "Too few signatures", by another route: one key signing twice counts once.
    function test_duplicateSignerRefused() public {
        uint256 i = _register();
        bytes32 n = _nonce();
        uint256[] memory twice = new uint256[](2);
        twice[0] = oracleSecrets[0];
        twice[1] = oracleSecrets[0];
        vm.expectRevert(RaceV2Base.DuplicateSigner.selector);
        race.accept(i, 0, _signWith(race, _acceptHash(i, n), n, twice));
        uint256[] memory reversed = new uint256[](2); // signatures out of address order
        reversed[0] = oracleSecrets[1];
        reversed[1] = oracleSecrets[0];
        vm.expectRevert(RaceV2Base.DuplicateSigner.selector);
        race.accept(i, 0, _signWith(race, _acceptHash(i, n), n, reversed));
    }

    /// Spec scenario "Wrong bounty": a result signed for one submission can't decide another.
    function test_resultForAnotherSubmissionRefused() public {
        uint256 b1 = _openBounty();
        uint256 b2 = _openBounty();
        uint256 id1 = _commit(solver1, b1, "fix1");
        uint256 id2 = _commit(solver2, b2, "fix2");
        (RaceV2Base.Verdict memory v, bytes[] memory sigs) = _signResult(race, id1, RaceV2Base.Outcome.Pass, "fix1", _noFees());
        RaceV2Base.Verdict memory other = _copy(v);
        other.submission = id2;
        other.bounty = b2;
        vm.expectRevert(RaceV2Base.Refused.selector); // its seed is id1's draw, not id2's (5.3); the digest differs too
        race.result(other, _noFees(), sigs);
        other = _copy(v);
        other.fix = "fix2";
        vm.expectRevert(RaceV2Base.NotOracle.selector); // nor another outcome, fix or fees for the same submission
        race.result(other, _noFees(), sigs);
        other = _copy(v);
        other.submission = id2; // the right bounty is checked before the signatures: id2 is b2's
        vm.expectRevert(RaceV2Base.Refused.selector);
        race.result(other, _noFees(), sigs);
        race.result(v, _noFees(), sigs);
        assertEq(uint256(race.bounty(b1).state), uint256(RaceV2Base.State.Won));
        assertEq(uint256(race.bounty(b2).state), uint256(RaceV2Base.State.Open));
    }

    /// Spec scenario "Replayed signature": each signed result is taken once.
    function test_replayedSignatureRefused() public {
        uint256 i = _register();
        RaceV2Base.Signed memory a = _signAccept(race, i);
        race.accept(i, 0, a);
        vm.expectRevert(RaceV2Base.Replayed.selector);
        race.accept(i, 0, a);
    }

    /// A signature for one action can't serve another, or another deployment.
    function test_crossActionAndCrossContractReplayRefused() public {
        uint256 i = _register();
        RaceV2Base.Signed memory a = _signAccept(race, i);
        vm.expectRevert(RaceV2Base.NotOracle.selector); // accept's signature as junk's
        race.junk(i, a);
        address[] memory feeCoins = new address[](1);
        feeCoins[0] = address(usd);
        Race other = _newRace(_config(), feeCoins, 1_000, 100_000);
        usd.mint(reporter, 7 * C);
        vm.startPrank(reporter);
        usd.approve(address(other), type(uint256).max);
        uint256 j = other.register(address(usd), bytes32(0));
        vm.stopPrank();
        assertEq(j, i);
        vm.expectRevert(RaceV2Base.NotOracle.selector); // the same oracles, but the digest binds the contract
        other.accept(j, 0, a);
        race.accept(i, 0, a);
    }

    /// A merge signed for an earlier winner can't merge a later one.
    function test_mergeBindsTheWinner() public {
        uint256 b = _openBounty();
        _win(b, solver1, "fix1");
        (RaceV2Base.Verdict memory v, bytes[] memory sigs) = _signMerged(race, b);
        _toDay(15);
        race.mergeExpired(b);
        _win(b, solver2, "fix2");
        vm.expectRevert(RaceV2Base.Refused.selector);
        race.merged(v, 0, sigs);
        _merged(race, b);
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Merged));
    }

    /// A high-s twin of a valid signature is refused (no malleability).
    function test_malleableSignatureRefused() public {
        uint256 i = _register();
        RaceV2Base.Signed memory a = _signAccept(race, i);
        bytes memory sig = a.sigs[0];
        bytes32 r;
        bytes32 sv;
        uint8 v;
        assembly {
            r := mload(add(sig, 32))
            sv := mload(add(sig, 64))
            v := byte(0, mload(add(sig, 96)))
        }
        uint256 order = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141;
        a.sigs[0] = abi.encodePacked(r, bytes32(order - uint256(sv)), v == 27 ? uint8(28) : uint8(27));
        vm.expectRevert(); // OpenZeppelin's ECDSAInvalidSignatureS
        race.accept(i, 0, a);
    }

    /// The oracle set is fixed at deployment, in Verdicts: a quorum above half the keys, no repeated or zero key.
    function test_oracleSetChecked() public {
        address[] memory keys = new address[](4);
        for (uint256 k; k < 4; ++k) {
            keys[k] = makeAddr(string.concat("key", vm.toString(k)));
        }
        vm.expectRevert(Verdicts.BadOracleSet.selector); // 2 of 4 is half, not a majority
        new Verdicts(genesis(keys, 2, new address[](0), new address[](0)));
        vm.expectRevert(Verdicts.BadOracleSet.selector);
        new Verdicts(genesis(keys, 5, new address[](0), new address[](0)));
        keys[3] = keys[0];
        vm.expectRevert(Verdicts.BadOracleSet.selector);
        new Verdicts(genesis(keys, 3, new address[](0), new address[](0)));
        assertEq(race.verdicts().quorum(), 2);
        assertEq(race.verdicts().keys().length, 3);
    }

    /// RaceV2's own parameters: a deployed Verdicts, a tolerance of at least 100 %, a start not in the future, and
    /// releases and instalments that aren't zero.
    function test_paramsChecked() public {
        address[] memory feeCoins = new address[](1);
        feeCoins[0] = address(usd);
        Verdicts v = race.verdicts();
        vm.expectRevert(RaceV2Base.BadParams.selector); // not a contract
        new Race(_config(), feeCoins, 1_000, 100_000, Verdicts(address(0xBEEF)), 300, 0, _noRepos(), _noRepos(), GENESIS_CONSTITUTION, IFees(address(0)));
        vm.expectRevert(RaceV2Base.BadParams.selector); // below the merge estimate itself
        new Race(_config(), feeCoins, 1_000, 100_000, v, 99, 0, _noRepos(), _noRepos(), GENESIS_CONSTITUTION, IFees(address(0)));
        vm.expectRevert(RaceV2Base.BadParams.selector); // in the future
        new Race(_config(), feeCoins, 1_000, 100_000, v, 300, block.timestamp + 1, _noRepos(), _noRepos(), GENESIS_CONSTITUTION, IFees(address(0)));
        RaceV2Base.Config memory c = _config();
        c.instalments = 0;
        vm.expectRevert(RaceV2Base.BadParams.selector);
        new Race(c, feeCoins, 1_000, 100_000, v, 300, 0, _noRepos(), _noRepos(), GENESIS_CONSTITUTION, IFees(address(0)));
        vm.warp(block.timestamp + 30 days);
        Race later = new Race(_config(), feeCoins, 1_000, 100_000, v, 300, race.start(), _noRepos(), _noRepos(), GENESIS_CONSTITUTION, IFees(address(0))); // keeps an earlier start
        assertEq(later.start(), race.start());
        assertEq(later.day(), 30);
    }

    /// Two RaceV2s may share one Verdicts: each spends only its own digests, and a digest binds its contract.
    function test_sharedVerdictsKeepDigestsApart() public {
        address[] memory feeCoins = new address[](1);
        feeCoins[0] = address(usd);
        Race other = new Race(_config(), feeCoins, 1_000, 100_000, race.verdicts(), 300, 0, _noRepos(), _noRepos(), GENESIS_CONSTITUTION, IFees(address(0)));
        uint256 i = _register();
        usd.mint(reporter, 7 * C);
        vm.startPrank(reporter);
        usd.approve(address(other), type(uint256).max);
        uint256 j = other.register(address(usd), bytes32(0));
        vm.stopPrank();
        RaceV2Base.Signed memory a = _signAccept(race, i);
        vm.expectRevert(RaceV2Base.NotOracle.selector); // signed over race's domain
        other.accept(j, 0, a);
        race.accept(i, 0, a);
        assertTrue(race.verdicts().used(address(race), _digest(race, _acceptHash(i, a.nonce))));
        assertFalse(race.verdicts().used(address(other), _digest(race, _acceptHash(i, a.nonce))));
        other.accept(j, 0, _signAccept(other, j));
    }

    /// Anyone may call Verdicts.authorize, but only ever spends its own digests: it can't burn a Race's.
    function test_aStrangerCantSpendARacesDigest() public {
        uint256 i = _register();
        RaceV2Base.Signed memory a = _signAccept(race, i);
        race.verdicts().authorize(_digest(race, _acceptHash(i, a.nonce)), a.sigs); // the stranger's own namespace
        race.accept(i, 0, a); // still good for the race
        assertEq(uint256(race.bounty(1).state), uint256(RaceV2Base.State.Open));
    }

    /// Gas of one signed result at 2-of-3 and 3-of-5 (reported in the PR).
    function test_gasPerSignedResult() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, "fix1");
        (RaceV2Base.Verdict memory v, bytes[] memory sigs) = _signResult(race, id, RaceV2Base.Outcome.Fail, "fix1", _noFees());
        race.result(v, _noFees(), sigs);
        emit log_named_uint("result, 2 of 3", vm.lastFrameGas().gasTotalUsed);
        _makeOracles(5, 3);
        address[] memory feeCoins = new address[](1);
        feeCoins[0] = address(usd);
        race = _newRace(_config(), feeCoins, 1_000, 100_000);
        b = _openBounty();
        id = _commit(solver1, b, "fix1");
        (v, sigs) = _signResult(race, id, RaceV2Base.Outcome.Fail, "fix1", _noFees());
        race.result(v, _noFees(), sigs);
        emit log_named_uint("result, 3 of 5", vm.lastFrameGas().gasTotalUsed);
    }

    function test_resultOnlyOnce() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, "fix1");
        _decide(id, RaceV2Base.Outcome.Fail, "fix1");
        (RaceV2Base.Verdict memory v, bytes[] memory sigs) = _signResult(race, id, RaceV2Base.Outcome.Pass, "fix1", _noFees());
        vm.expectRevert(RaceV2Base.Refused.selector);
        race.result(v, _noFees(), sigs);
    }

    // ---------- appeals ----------

    function test_authorAppealsOnce() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, "fix1");
        _decide(id, RaceV2Base.Outcome.Fail, "fix1");
        _fund(solver1, usd, 10 * C); // the first deposit's rest is a credit, not in the wallet
        vm.prank(solver1);
        uint256 again = race.appeal(id, address(usd));
        assertEq(race.submission(again).commitment, race.submission(id).commitment);
        assertEq(_owed(infra, usd), 2 * C + 2 * C); // registration + appeal fee
        _decide(again, RaceV2Base.Outcome.Fail, "fix1");
        vm.prank(solver1);
        vm.expectRevert(RaceV2Base.Refused.selector);
        race.appeal(again, address(usd));
        vm.prank(solver1);
        vm.expectRevert(RaceV2Base.Refused.selector);
        race.appeal(id, address(usd));
    }

    /// Owner, 2026-10-29: a split rejection (a split jury, inconclusive CI) is appealable like a failure, once.
    function test_splitRejectionAppealsOnce() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, "fix1");
        _decide(id, RaceV2Base.Outcome.Split, "fix1");
        _fund(solver1, usd, 10 * C);
        vm.prank(solver1);
        uint256 again = race.appeal(id, address(usd));
        assertEq(_owed(infra, usd), 2 * C + 2 * C); // registration + appeal fee
        _decide(again, RaceV2Base.Outcome.Pass, "fix1");
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Won));
        vm.prank(solver1);
        vm.expectRevert(RaceV2Base.Refused.selector);
        race.appeal(id, address(usd));
    }

    function test_duplicateCantBeAppealedAsAFailure() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, "fix1");
        _decide(id, RaceV2Base.Outcome.Duplicate, "fix1");
        vm.prank(solver1);
        vm.expectRevert(RaceV2Base.Refused.selector);
        race.appeal(id, address(usd));
    }

    function test_duplicateAppealPaysItsJury() public {
        uint256 b = _openBounty();
        _fund(solver1, usd, 10 * C);
        vm.prank(solver1);
        uint256 a = race.appealDuplicate(b, "fix1", address(usd));
        RaceV2Base.Fee[] memory jurors = new RaceV2Base.Fee[](3);
        jurors[0] = RaceV2Base.Fee(makeAddr("j1"), 0.3e6);
        jurors[1] = RaceV2Base.Fee(makeAddr("j2"), 0.3e6);
        jurors[2] = RaceV2Base.Fee(makeAddr("j3"), 0.4e6);
        _appealResult(race, a, b, true, jurors);
        assertEq(_owed(infra, usd), 2 * C + 2 * C);
        assertEq(_owed(solver1, usd), 5e6 - 2e6 - 1e6);
        vm.expectRevert(RaceV2Base.Refused.selector);
        _appealResult(race, a, b, true, jurors);
        _assertBooks(usd);
    }

    // ---------- merge, instalments, clawback ----------

    function _win(uint256 b, address solver, bytes32 fix) internal returns (uint256 id) {
        id = _commit(solver, b, fix);
        _decide(id, RaceV2Base.Outcome.Pass, fix);
    }

    /// Spec scenario "Not merged": nothing is paid, and the bounty reopens after the merge deadline.
    function test_notMergedReopens() public {
        uint256 b = _openBounty();
        _win(b, solver1, "fix1");
        _toDay(14);
        vm.expectRevert(RaceV2Base.NotYet.selector);
        race.mergeExpired(b);
        _toDay(15);
        race.mergeExpired(b);
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Open));
        assertEq(race.bounty(b).epoch, 0);
        assertEq(race.held(b, address(usd)), 100 * C);
    }

    /// The whole loop: merged on day 1, window to day 8, instalments at the releases on days 14, 21, 28 and 35;
    /// then the finder's fee, the registration refund and the issue stake to the reporter, and the rest by input.
    function test_paidInInstalmentsThenRefunded() public {
        uint256 b = _openBounty();
        _pledge(bob, usd, b, 50 * C);
        _win(b, solver1, "fix1"); // locked at 50 % on day 0
        _toDay(1);
        _merged(race, b);
        uint256 price = race.priceOf(b, address(usd), 1);
        assertEq(price, (148 * C * BPS / (BPS + FINDER)) * 5_000 / BPS);

        _toDay(13);
        assertEq(race.earned(b, 1), 0);
        _toDay(14);
        assertEq(race.earned(b, 1), 1);
        race.claimInstalments(b, address(usd), 1);
        assertEq(_owed(solver1, usd), 6.6e6 + price / 4); // the deposit back + one instalment
        _toDay(35);
        assertEq(race.earned(b, 1), 4);

        vm.prank(alice);
        race.claimRefund(b, address(usd)); // settles first: the rest of the price, the finder's fee, the refunds
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Paid));
        assertEq(_owed(solver1, usd), 6.6e6 + price);
        uint256 finder = price * FINDER / BPS;
        assertEq(_owed(reporter, usd), finder + 2 * C + 5 * C);
        uint256 left = 150 * C - price - finder - 2 * C;
        vm.prank(bob);
        race.claimRefund(b, address(usd));
        assertEq(_owed(alice, usd) + _owed(bob, usd), left);
        assertEq(race.held(b, address(usd)), 0);
        assertTrue(race.paidFix("fix1"));
        _assertBooks(usd);
    }

    /// Spec scenario "Clawed back": an upheld challenge after two instalments; the bounty reopens with the rest.
    function test_clawedBackReopens() public {
        uint256 b = _openBounty();
        _win(b, solver1, "fix1");
        _merged(race, b);
        uint256 price = race.priceOf(b, address(usd), 1);
        _toDay(14);
        race.claimInstalments(b, address(usd), 1);
        _toDay(21);
        _challengeUpheld(race, b);
        assertEq(race.earned(b, 1), 2);
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Open));
        race.claimInstalments(b, address(usd), 1);
        assertEq(race.instalmentsPaid(b, address(usd), 1), price / 4 * 2);
        _toDay(60);
        race.claimInstalments(b, address(usd), 1); // nothing more, ever
        assertEq(race.instalmentsPaid(b, address(usd), 1), price / 4 * 2);
        assertEq(race.held(b, address(usd)), 100 * C - price / 4 * 2);

        // a second solver wins again at the locked price, at most what the pot's cap is now
        _win(b, solver2, "fix2");
        _merged(race, b);
        uint256 locked = race.lockedPrice(b, address(usd));
        uint256 cap = race.capOf(b, address(usd), race.held(b, address(usd)));
        assertEq(race.priceOf(b, address(usd), 2), locked < cap ? locked : cap);
        _assertBooks(usd);
    }

    /// An earlier award's earned instalments, not yet pulled when the bounty is won again, are kept out of the next
    /// award's price: both are paid in full and the refunds still open.
    function test_unclaimedEarlierAwardIsReserved() public {
        uint256 b = _openBounty();
        _toDay(5); // the price rises to 100 % before the lock
        _win(b, solver1, "fix1");
        _merged(race, b);
        _toDay(21);
        _challengeUpheld(race, b); // two instalments earned, none pulled
        uint256 first = race.priceOf(b, address(usd), 1);
        _win(b, solver2, "fix2");
        _merged(race, b);
        uint256 second = race.priceOf(b, address(usd), 2);
        assertEq(race.unpaidBefore(b, address(usd), 2), first / 4 * 2);
        assertLe(second, race.capOf(b, address(usd), race.held(b, address(usd)) - first / 4 * 2));
        _toDay(70);
        vm.prank(alice);
        race.claimRefund(b, address(usd));
        assertEq(_owed(solver1, usd), 6.6e6 + first / 4 * 2);
        assertEq(_owed(solver2, usd), 6.6e6 + second);
        assertEq(race.held(b, address(usd)), 0);
        _assertBooks(usd);
    }

    function test_upheldInTheWindowPaysNothing() public {
        uint256 b = _openBounty();
        _win(b, solver1, "fix1");
        _merged(race, b);
        _toDay(5);
        _challengeUpheld(race, b);
        _toDay(40);
        race.claimInstalments(b, address(usd), 1);
        assertEq(race.instalmentsPaid(b, address(usd), 1), 0);
    }

    function test_nothingToClawBackOnceFullyPaid() public {
        uint256 b = _openBounty();
        _win(b, solver1, "fix1");
        _merged(race, b);
        _toDay(35);
        RaceV2Base.Signed memory a = _signUpheld(race, b);
        vm.expectRevert(RaceV2Base.Refused.selector);
        race.challengeUpheld(b, 1, a);
    }

    // ---------- D10: one fix, one payout ----------

    /// bounty-market scenario "A later bounty on the same issue": once the first is paid, a new bounty may open for
    /// it (a regression, say), but the fix it paid can't win it; a different fix can.
    function test_paidFixCantWinALaterBounty() public {
        uint256 b1 = _openBounty();
        _win(b1, solver1, "fix1");
        _merged(race, b1);
        _toDay(35);
        race.settle(b1, address(usd));
        assertEq(uint256(race.bounty(b1).state), uint256(RaceV2Base.State.Paid));
        uint256 b2 = _openBounty();
        uint256 id = _commit(solver2, b2, "fix1");
        _decide(id, RaceV2Base.Outcome.Pass, "fix1");
        assertEq(uint256(race.submission(id).outcome), uint256(RaceV2Base.Outcome.Duplicate));
        assertEq(uint256(race.bounty(b2).state), uint256(RaceV2Base.State.Open));
        _win(b2, solver2, "fix2");
        assertEq(uint256(race.bounty(b2).state), uint256(RaceV2Base.State.Won));
    }

    // ---------- D11: idle sunset ----------

    /// bounty-market scenario "Nobody takes it".
    function test_idleBountySunsets() public {
        uint256 b = _openBounty();
        _toDay(27);
        vm.expectRevert(RaceV2Base.NotYet.selector);
        race.sunset(b);
        _toDay(28);
        vm.prank(makeAddr("anyone"));
        race.sunset(b);
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Unsolved));
        assertEq(_owed(reporter, usd), 5 * C); // the stake back, no fee
        vm.prank(alice);
        race.claimRefund(b, address(usd));
        assertEq(_owed(alice, usd), 100 * C);
    }

    /// Owner, 2026-10-29: attempts don't keep a dead bounty alive. Fresh attempts every few days, by two solvers,
    /// don't move its sunset; the attempts in progress end with it.
    function test_attemptsDontKeepItAlive() public {
        uint256 b = _openBounty();
        for (uint256 d = 2; d < 28; d += 5) {
            _toDay(d);
            address who = d % 2 == 0 ? solver1 : solver2;
            _fund(who, usd, 1 * C);
            vm.prank(who);
            race.attempt(b, address(usd));
        }
        _toDay(27);
        vm.expectRevert(RaceV2Base.NotYet.selector);
        race.sunset(b);
        _toDay(28);
        race.sunset(b);
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Unsolved));
        _fund(solver1, usd, 7 * C); // an attempt in progress ends with it: nothing more can be submitted
        vm.prank(solver1);
        vm.expectRevert(abi.encodeWithSelector(RaceV2Base.WrongState.selector, b, RaceV2Base.State.Unsolved));
        race.commit(b, keccak256("late"), address(usd));
        _assertBooks(usd);
    }

    /// Stopping and starting again doesn't restart the clock either.
    function test_stopAndReattemptDontDelayIt() public {
        uint256 b = _openBounty();
        for (uint256 d = 1; d < 28; d += 3) {
            _toDay(d);
            _fund(solver1, usd, 1 * C);
            vm.startPrank(solver1);
            race.attempt(b, address(usd));
            _toDay(d + 1);
            race.stop(b);
            vm.stopPrank();
        }
        _toDay(28);
        race.sunset(b);
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Unsolved));
    }

    /// Owner, 2026-10-29: a duplicate isn't progress, so repeating one every few days can't keep a dead bounty from
    /// its sunset; a checked failure restarts the idle clock.
    function test_duplicatesDontKeepItAlive() public {
        uint256 b = _openBounty();
        for (uint256 d = 3; d < 28; d += 6) {
            _toDay(d);
            _fund(solver1, usd, 1 * C);
            vm.prank(solver1);
            race.attempt(b, address(usd));
            _toDay(d + 1);
            _decide(_commit(solver1, b, "dup"), RaceV2Base.Outcome.Duplicate, "dup");
        }
        _toDay(28);
        race.sunset(b);
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Unsolved));
    }

    function test_checkedFailureRestartsTheIdleClock() public {
        uint256 b = _openBounty();
        _toDay(10);
        _decide(_commit(solver1, b, "fix1"), RaceV2Base.Outcome.Fail, "fix1");
        _toDay(37);
        vm.expectRevert(RaceV2Base.NotYet.selector);
        race.sunset(b);
        _toDay(38);
        race.sunset(b);
    }

    /// A split rejection is checked too: it restarts the clock, and later attempts don't.
    function test_checkedSplitRestartsTheIdleClock() public {
        uint256 b = _openBounty();
        _toDay(20);
        _decide(_commit(solver1, b, "fix1"), RaceV2Base.Outcome.Split, "fix1");
        _toDay(30);
        _fund(solver2, usd, 1 * C);
        vm.prank(solver2);
        race.attempt(b, address(usd));
        _toDay(47);
        vm.expectRevert(RaceV2Base.NotYet.selector);
        race.sunset(b);
        _toDay(48); // 28 days from the result on day 20, not from the attempt on day 30
        race.sunset(b);
    }

    function test_waitingResultBlocksSunset() public {
        uint256 b = _openBounty();
        _commit(solver1, b, "fix1");
        _toDay(100);
        vm.expectRevert(RaceV2Base.NotYet.selector);
        race.sunset(b);
    }

    /// D14: a submission never revealed (no result in time) can't hold up the queue: anyone times it out, it pays
    /// the evaluation fee, and the next passing submission wins.
    function test_unrevealedSubmissionTimesOut() public {
        uint256 b = _openBounty();
        uint256 stale = _commit(solver1, b, "never revealed");
        uint256 id = _commit(solver2, b, "fix2");
        _decide(id, RaceV2Base.Outcome.Pass, "fix2");
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Open)); // waiting on the earlier commitment
        _toDay(6);
        vm.expectRevert(RaceV2Base.NotYet.selector);
        race.timeOut(stale);
        _toDay(7);
        vm.prank(makeAddr("anyone"));
        race.timeOut(stale);
        assertEq(uint256(race.submission(stale).outcome), uint256(RaceV2Base.Outcome.TimedOut));
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Won));
        assertEq(race.bounty(b).winner, id);
        assertEq(_owed(solver1, usd), 6.6e6 - 2 * C); // the deposit less the evaluation fee
        vm.expectRevert(RaceV2Base.Refused.selector); // decided: no result, no second timeout
        race.timeOut(stale);
        vm.expectRevert(RaceV2Base.Refused.selector);
        race.timeOut(id);
        _assertBooks(usd);
    }

    // ---------- baskets in the race ----------

    /// Spec scenario "A frozen coin", through the race: the winner pulls the other coin; the frozen one stays.
    function test_frozenCoinInAWinningBasket() public {
        FrozenCoin fusd = new FrozenCoin();
        uint256 b = _openBounty();
        _pledge(bob, MockCoin(address(fusd)), b, 100 * C);
        _win(b, solver1, "fix1");
        _merged(race, b);
        _toDay(35);
        race.settle(b, address(usd));
        race.settle(b, address(fusd));
        fusd.freeze(solver1, true);
        vm.startPrank(solver1);
        race.withdraw(address(usd), solver1);
        vm.expectRevert(abi.encodeWithSelector(FrozenCoin.Frozen.selector, solver1));
        race.withdraw(address(fusd), solver1);
        vm.stopPrank();
        assertGt(_owed(solver1, MockCoin(address(fusd))), 0);
    }

    /// A coin that goes withdraw-only mid-race: its pot refunds by input; the other coin still pays the winner.
    function test_withdrawOnlyCoinRefundsItsPot() public {
        LyingCoin lying = new LyingCoin();
        uint256 b = _openBounty();
        _pledge(bob, MockCoin(address(lying)), b, 100 * C);
        _win(b, solver1, "fix1");
        _merged(race, b);
        lying.shrink(address(race), 1);
        race.check();
        vm.prank(bob);
        race.claimRefund(b, address(lying));
        assertEq(_owed(bob, MockCoin(address(lying))), 100 * C);
        _toDay(35);
        race.settle(b, address(usd));
        assertGt(_owed(solver1, usd), 0);
    }

    // ---------- no privileged call ----------

    /// Spec scenario "No privileged call": every external function, from the compiled ABI. Anything that changes
    /// parameters, moves others' funds or upgrades code would show up here. Nothing is gated by caller: oracle
    /// results are relayed by anyone, and only the quorum's signatures make them count (D3).
    // ---------- coin only (S6): no token; the inflation rule on the coin ----------

    /// An issue registered at weight `reg`, funded with `funds` (0: a 0-coin bounty), won by solver1, merged on day 0
    /// at weight `mergeW`, and settled paid on day 35 (its last instalment).
    function _paidBounty(uint256 reg, uint256 mergeW, uint256 funds) internal returns (uint256 b) {
        b = _accept(race, _register(), reg);
        if (funds != 0) _pledge(alice, usd, b, funds);
        _win(b, solver1, "fix1");
        _merged(race, b, mergeW);
        _toDay(35);
        assertTrue(race.settle(b, address(usd)));
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Paid));
    }

    /// v1's "An inflated estimate", coin side: within the tolerance the reporter keeps its finder's fee.
    function test_weightsWithinTheToleranceKeepTheFindersFee() public {
        uint256 b = _paidBounty(200, 90, 100 * C);
        assertFalse(race.bounty(b).inflated);
        assertEq(race.bounty(b).weight, 200);
        assertEq(race.bounty(b).mergeWeight, 90);
        uint256 price = race.priceOf(b, address(usd), 1);
        assertEq(_owed(reporter, usd), 5 * C + 2 * C + price * FINDER / BPS);
    }

    /// Scenario "Inflated beyond the tolerance": registered above 300 % of the merge estimate, the reporter forfeits
    /// its finder's fee (it stays in the pot for the funders); its stake and registration refund come back.
    function test_inflatedForfeitsTheReportersShare() public {
        uint256 b = _paidBounty(400, 100, 100 * C);
        assertTrue(race.bounty(b).inflated);
        assertEq(_owed(reporter, usd), 5 * C + 2 * C); // the stake and the registration refund, no finder's fee
        uint256 price = race.priceOf(b, address(usd), 1);
        vm.prank(alice);
        race.claimRefund(b, address(usd));
        assertEq(_owed(alice, usd), 100 * C - price - 2 * C); // the fee went back to the funder
        _assertBooks(usd);
    }

    /// Within the tolerance (290 % of the merge estimate) the reporter is paid.
    function test_withinTheToleranceTheReporterIsPaid() public {
        uint256 b = _paidBounty(290, 100, 100 * C);
        assertFalse(race.bounty(b).inflated);
        assertGt(_owed(reporter, usd), 7 * C);
    }

    /// A bounty nobody funded, won and merged, closes paid with no coin: no token either (S6).
    function test_zeroCoinPaysNothing() public {
        uint256 b = _paidBounty(50, 50, 0);
        assertEq(race.priceOf(b, address(usd), 1), 0);
        assertEq(_owed(solver1, usd), 6.6e6); // its deposit back, nothing else
        assertEq(_owed(reporter, usd), 5 * C); // its stake; the registration refund comes from the pot, which is empty
    }

    /// The weights are part of the signed results: a relayer can't change them.
    function test_weightsAreSigned() public {
        uint256 i = _register();
        RaceV2Base.Signed memory a = _signAccept(race, i, 100);
        vm.expectRevert(RaceV2Base.NotOracle.selector); // a different digest: the signers recover to other addresses
        race.accept(i, 1_000, a);
        race.accept(i, 100, a);
        assertEq(race.bounty(1).weight, 100);
    }

    function test_noPrivilegedCall() public view {
        string memory json = vm.readFile("out/RaceV2.sol/RaceV2.json");
        string[] memory names = new string[](96);
        uint256 n;
        for (uint256 i;; ++i) {
            string memory key = string.concat(".abi[", vm.toString(i), "]");
            if (!vm.keyExistsJson(json, key)) break;
            if (keccak256(bytes(vm.parseJsonString(json, string.concat(key, ".type")))) != keccak256("function")) {
                continue;
            }
            names[n++] = vm.parseJsonString(json, string.concat(key, ".name"));
        }
        string[50] memory allowed = [
            // anyone
            "register", "withdrawIssue", "pledge", "sunset", "attempt", "stop", "commit", "timeOut",
            "appeal", "appealDuplicate", "mergeExpired", "claimInstalments", "settle", "claimRefund", "withdraw",
            "offerSwap", "cancelSwap", "acceptSwap", "check",
            // signed by the oracle quorum, relayed by anyone (D3)
            "accept", "refuseSimilar", "result", "appealResult", "merged", "challengeUpheld", "junk",
            // views
            "getConfig", "day", "issue", "bounty", "submission", "submissionsOf", "offerBps", "capOf", "lockedPrice",
            "priceOf", "unpaidBefore", "earned", "awards", "prices", "instalmentsPaid", "settled", "attemptedOn", "paidFix",
            "feeCoins", "isFeeCoin", "start", "bountyCap", "totalCap", "withdrawOnly"
        ];
        string[29] memory moreViews = [
            "unit", "coins", "totalHeld", "totalOwed", "totalDeposits", "owed", "pot", "held", "pledged",
            "refundedTo", "swaps", "swapCount", "coinCount", "solvent", "inflationPct",
            // who is a party to a verdict's subject (5.3, Verdicts' recusal), and the companion RaceV2Annex that runs
            // the rarely called actions above in this contract's storage, fixed at deployment (5.3)
            "isParty", "annex",
            // the verdicts' contract (its keys, quorum and used digests), the head registry it deployed (5.2), the
            // check-fee meter fixed at deployment (5.7) and the EIP-712 types (D3, S10)
            "verdicts", "heads", "meter", "domainSeparator", "FEE_TYPEHASH", "ACCEPT_TYPEHASH",
            "REFUSE_SIMILAR_TYPEHASH", "JUNK_TYPEHASH", "RESULT_TYPEHASH", "APPEAL_RESULT_TYPEHASH", "MERGED_TYPEHASH",
            "CHALLENGE_UPHELD_TYPEHASH"
        ];
        for (uint256 i; i < n; ++i) {
            bool ok;
            for (uint256 j; j < allowed.length && !ok; ++j) {
                ok = keccak256(bytes(names[i])) == keccak256(bytes(allowed[j]));
            }
            for (uint256 j; j < moreViews.length && !ok; ++j) {
                ok = keccak256(bytes(names[i])) == keccak256(bytes(moreViews[j]));
            }
            assertTrue(ok, string.concat("unexpected external function: ", names[i]));
        }
        assertEq(n, allowed.length + moreViews.length);
    }
}
