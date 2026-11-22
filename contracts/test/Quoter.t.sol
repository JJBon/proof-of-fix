// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Oracles} from "./helpers/Oracles.sol";
import {Race} from "../src/Race.sol";
import {Quoter} from "../src/Quoter.sol";
import {MockCoin} from "./mocks/MockCoin.sol";

/// Task 3.2: the quote a solver reads before paying for an attempt. Its agreement with pof's `Market.quote` is the
/// replay's (Replay.t.sol checks every exported quote); these tests pin its rules on their own.
contract QuoterTest is Oracles {
    uint256 constant C = 1e6;
    uint256 constant BPS = 10_000;
    uint256 constant FINDER = 1_765;

    Race race;
    Quoter quoter;
    MockCoin usd;
    address reporter = makeAddr("reporter");
    address alice = makeAddr("alice");
    address solver = makeAddr("solver");

    function setUp() public {
        usd = new MockCoin("Mock USD", "mUSD", 6);
        address[] memory feeCoins = new address[](1);
        feeCoins[0] = address(usd);
        _makeOracles(3, 2);
        Race.Config memory c;
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
        c.finderFeeBps = FINDER;
        c.idleDays = 28;
        c.resultDays = 7;
        c.mergeDays = 14;
        c.windowDays = 7;
        c.releaseEveryDays = 7;
        c.instalments = 4;
        race = _newRace(c, feeCoins, 1_000, 100_000);
        quoter = new Quoter();
    }

    function _fund(address who, uint256 amount) internal {
        usd.mint(who, amount);
        vm.prank(who);
        usd.approve(address(race), type(uint256).max);
    }

    function _toDay(uint256 d) internal {
        vm.warp(race.start() + d * 1 days);
    }

    /// An accepted issue, its bounty funded with 100 credits by alice.
    function _open() internal returns (uint256 b) {
        _fund(reporter, 7 * C);
        vm.prank(reporter);
        b = _accept(race, race.register(address(usd)));
        _fund(alice, 1_000 * C);
        vm.prank(alice);
        race.pledge(b, address(usd), 100 * C);
    }

    function _q(uint256 b) internal view returns (Quoter.Quote memory) {
        return quoter.quote(race, b, address(usd));
    }

    function test_openQuoteRisesUntilTheFirstAttemptLocksIt() public {
        uint256 b = _open();
        Quoter.Quote memory q = _q(b);
        uint256 cap = (100 * C - 2 * C) * BPS / (BPS + FINDER); // the registration is refunded from the pot
        assertEq(uint256(q.state), uint256(Race.State.Open));
        assertEq(q.cap, cap);
        assertEq(q.offerBps, 5_000);
        assertEq(q.price, cap * 5_000 / BPS);
        assertFalse(q.locked);
        assertEq(q.sunsetDay, 28);
        assertEq(q.attemptFee, 0.5e6);
        assertEq(q.checkDeposit, 6.6e6);
        assertEq(q.evaluationFee, 2e6);
        assertEq(q.appealFee, 2e6);

        _toDay(2);
        assertEq(_q(b).offerBps, 7_000, "rises 10 points a day");
        _fund(solver, 10 * C);
        vm.prank(solver);
        race.attempt(b, address(usd));
        q = _q(b);
        assertEq(q.offerBps, 7_000);
        assertTrue(q.locked);
        assertEq(q.attempting, 1);
        assertEq(q.sunsetDay, 28, "an attempt doesn't move the sunset (#74)");

        _toDay(5);
        vm.prank(alice);
        race.pledge(b, address(usd), 100 * C);
        q = _q(b);
        assertEq(q.offerBps, 7_000, "the share stays locked");
        assertEq(q.price, (200 * C - 2 * C) * BPS / (BPS + FINDER) * 7_000 / BPS, "a later pledge raises the price");
    }

    function test_instalmentsAndFinderFeeSplitThePrice() public {
        uint256 b = _open();
        Quoter.Quote memory q = _q(b);
        assertEq(q.instalments, 4);
        assertEq(q.instalment, q.price / 4);
        assertEq(q.instalment * 3 + q.lastInstalment, q.price, "the last instalment takes the remainder");
        assertEq(q.finderFee, q.price * FINDER / BPS);
    }

    function test_wonThenMergedQuotesTheAward() public {
        uint256 b = _open();
        _toDay(1);
        _fund(solver, 20 * C);
        vm.prank(solver);
        uint256 id = race.commit(b, keccak256(abi.encode(bytes32("fix"), bytes32("salt"), solver)), address(usd));
        uint256 open = _q(b).price;
        _result(race, id, Race.Outcome.Pass, bytes32("fix"), new Race.Fee[](0));
        Quoter.Quote memory q = _q(b);
        assertEq(uint256(q.state), uint256(Race.State.Won));
        assertEq(q.price, open, "the win pays the price on offer when it locked");
        assertEq(q.sunsetDay, 0, "only an open bounty sunsets");

        _toDay(3);
        _merged(race, b);
        q = _q(b);
        assertEq(uint256(q.state), uint256(Race.State.Merged));
        assertEq(q.price, race.priceOf(b, address(usd), race.bounty(b).epoch));
        assertEq(q.price, open);
    }

    function test_aClosedBountyQuotesNothing() public {
        uint256 b = _open();
        _toDay(28);
        race.sunset(b);
        Quoter.Quote memory q = _q(b);
        assertEq(uint256(q.state), uint256(Race.State.Unsolved));
        assertEq(q.price, 0);
        assertEq(q.cap, 0);
        assertEq(q.sunsetDay, 0);
        assertEq(q.finderFee, 0);
    }
}
