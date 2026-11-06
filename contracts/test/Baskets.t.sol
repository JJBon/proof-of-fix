// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {Test} from "forge-std/Test.sol";
import {Baskets} from "../src/Baskets.sol";
import {BasketsHarness} from "./mocks/BasketsHarness.sol";
import {MockCoin} from "./mocks/MockCoin.sol";
import {FrozenCoin} from "./mocks/FrozenCoin.sol";
import {FeeCoin} from "./mocks/FeeCoin.sol";
import {LyingCoin} from "./mocks/LyingCoin.sol";
import {NoDecimalsCoin} from "./mocks/NoDecimalsCoin.sol";

/// Task 2.1: baskets (design D5, D6; spec "Baskets with per-coin pull payouts" and "Safety without a key").
contract BasketsTest is Test {
    uint256 constant B = 1; // a bounty
    uint256 constant CREDIT = 1e6; // one simulation credit in a 6-decimal coin (design D2)

    BasketsHarness baskets;
    MockCoin usd;
    FrozenCoin fusd;
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");
    address carol = makeAddr("carol");
    address winner = makeAddr("winner");

    function setUp() public {
        baskets = new BasketsHarness(1_000, 100_000); // design D6: 1,000 a bounty, 100,000 in total
        usd = new MockCoin("Mock USD", "mUSD", 6);
        fusd = new FrozenCoin();
    }

    function _pledge(address funder, address coin, uint256 amount) internal {
        MockCoin(coin).mint(funder, amount);
        vm.startPrank(funder);
        MockCoin(coin).approve(address(baskets), amount);
        baskets.pledge(B, coin, amount);
        vm.stopPrank();
    }

    function _assertExact(address coin) internal view {
        assertEq(
            MockCoin(coin).balanceOf(address(baskets)),
            baskets.totalHeld(coin) + baskets.totalOwed(coin) + baskets.totalDeposits(coin)
        );
    }

    // ---------- pledges ----------

    function test_pledgeCreditsWhatArrived() public {
        _pledge(alice, address(usd), 40 * CREDIT);
        _pledge(bob, address(usd), 60 * CREDIT);
        assertEq(baskets.held(B, address(usd)), 100 * CREDIT);
        assertEq(baskets.pledged(B, address(usd), alice), 40 * CREDIT);
        assertEq(baskets.pot(B, address(usd)).funders, 2);
        _assertExact(address(usd));
    }

    /// Spec scenario "A fee-on-transfer token".
    function test_feeOnTransferRefused() public {
        FeeCoin fee = new FeeCoin();
        fee.mint(alice, 100 * CREDIT);
        vm.startPrank(alice);
        fee.approve(address(baskets), 100 * CREDIT);
        vm.expectRevert(abi.encodeWithSelector(Baskets.ShortReceived.selector, 100 * CREDIT, 99 * CREDIT));
        baskets.pledge(B, address(fee), 100 * CREDIT);
        vm.stopPrank();
    }

    function test_coinWithoutDecimalsRefused() public {
        NoDecimalsCoin odd = new NoDecimalsCoin();
        vm.expectRevert(abi.encodeWithSelector(Baskets.UnsupportedCoin.selector, address(odd)));
        baskets.pledge(B, address(odd), 1);
    }

    function test_zeroPledgeRefused() public {
        vm.expectRevert(Baskets.ZeroAmount.selector);
        baskets.pledge(B, address(usd), 0);
    }

    // ---------- caps ----------

    /// Spec scenario "Over the cap": a bounty's cap, in whole coins of each coin.
    function test_overBountyCapRefused() public {
        _pledge(alice, address(usd), 1_000 * CREDIT);
        usd.mint(bob, 1);
        vm.startPrank(bob);
        usd.approve(address(baskets), 1);
        vm.expectRevert(abi.encodeWithSelector(Baskets.OverBountyCap.selector, address(usd)));
        baskets.pledge(B, address(usd), 1);
        vm.stopPrank();
    }

    /// Spec scenario "Over the cap": the total, across bounties.
    function test_overTotalCapRefused() public {
        for (uint256 b = 1; b <= 100; ++b) {
            usd.mint(alice, 1_000 * CREDIT);
            vm.startPrank(alice);
            usd.approve(address(baskets), 1_000 * CREDIT);
            baskets.pledge(b, address(usd), 1_000 * CREDIT);
            vm.stopPrank();
        }
        usd.mint(bob, 1);
        vm.startPrank(bob);
        usd.approve(address(baskets), 1);
        vm.expectRevert(abi.encodeWithSelector(Baskets.OverTotalCap.selector, address(usd)));
        baskets.pledge(101, address(usd), 1);
        vm.stopPrank();
    }

    /// The caps count whole coins, so an 18-decimal coin gets the same 1,000 coins.
    function test_capScalesWithDecimals() public {
        MockCoin eth = new MockCoin("Mock ETH", "mETH", 18);
        _pledge(alice, address(eth), 1_000 ether);
        assertEq(baskets.unit(address(eth)), 1e18);
        eth.mint(bob, 1);
        vm.startPrank(bob);
        eth.approve(address(baskets), 1);
        vm.expectRevert(abi.encodeWithSelector(Baskets.OverBountyCap.selector, address(eth)));
        baskets.pledge(B, address(eth), 1);
        vm.stopPrank();
    }

    // ---------- payouts ----------

    function test_payNeverMoreThanThePot() public {
        _pledge(alice, address(usd), 10 * CREDIT);
        vm.expectRevert(abi.encodeWithSelector(Baskets.OverPot.selector, B, address(usd)));
        baskets.pay(B, address(usd), winner, 10 * CREDIT + 1);
    }

    function test_withdrawPullsTheCredit() public {
        _pledge(alice, address(usd), 10 * CREDIT);
        baskets.pay(B, address(usd), winner, 7 * CREDIT);
        vm.prank(winner);
        baskets.withdraw(address(usd), winner);
        assertEq(usd.balanceOf(winner), 7 * CREDIT);
        assertEq(baskets.owed(winner, address(usd)), 0);
        _assertExact(address(usd));
        vm.prank(winner);
        vm.expectRevert(Baskets.NothingOwed.selector);
        baskets.withdraw(address(usd), winner);
    }

    /// Spec scenario "A frozen coin": the winner pulls the other coin; the frozen coin's share stays claimable.
    function test_frozenCoinDoesntBlockTheOthers() public {
        _pledge(alice, address(usd), 100 * CREDIT);
        _pledge(alice, address(fusd), 100 * CREDIT);
        baskets.pay(B, address(usd), winner, 70 * CREDIT);
        baskets.pay(B, address(fusd), winner, 70 * CREDIT);
        fusd.freeze(winner, true);

        vm.startPrank(winner);
        baskets.withdraw(address(usd), winner);
        vm.expectRevert(abi.encodeWithSelector(FrozenCoin.Frozen.selector, winner));
        baskets.withdraw(address(fusd), winner);
        vm.stopPrank();

        assertEq(usd.balanceOf(winner), 70 * CREDIT);
        assertEq(baskets.owed(winner, address(fusd)), 70 * CREDIT); // still claimable
        _assertExact(address(fusd));
    }

    /// Owner's choice (#59 on #56): a credit is pulled to any address, so an address frozen by the issuer names another.
    function test_frozenAddressPullsToAnother() public {
        _pledge(alice, address(fusd), 100 * CREDIT);
        baskets.pay(B, address(fusd), winner, 70 * CREDIT);
        fusd.freeze(winner, true);
        address fresh = makeAddr("fresh");
        vm.prank(winner);
        baskets.withdraw(address(fusd), fresh);
        assertEq(fusd.balanceOf(fresh), 70 * CREDIT);
    }

    /// Owner's choice (#59 on #56): a coin paused for everyone is swapped for another, if the credit's owner agrees.
    function test_pausedCoinSwappedForAnother() public {
        _pledge(alice, address(fusd), 100 * CREDIT);
        baskets.pay(B, address(fusd), winner, 70 * CREDIT);
        fusd.pause(true);

        usd.mint(alice, 65 * CREDIT);
        vm.startPrank(alice);
        usd.approve(address(baskets), 65 * CREDIT);
        uint256 id = baskets.offerSwap(winner, address(fusd), 70 * CREDIT, address(usd), 65 * CREDIT);
        vm.stopPrank();

        vm.prank(bob);
        vm.expectRevert(abi.encodeWithSelector(Baskets.NotYours.selector, id));
        baskets.acceptSwap(id);

        vm.prank(winner);
        baskets.acceptSwap(id);
        assertEq(baskets.owed(winner, address(usd)), 65 * CREDIT);
        assertEq(baskets.owed(winner, address(fusd)), 0);
        assertEq(baskets.owed(alice, address(fusd)), 70 * CREDIT); // alice waits for the unpause

        vm.prank(winner);
        baskets.withdraw(address(usd), winner);
        assertEq(usd.balanceOf(winner), 65 * CREDIT);
        _assertExact(address(usd));
        _assertExact(address(fusd));
    }

    function test_swapCancelledReturnsThePayment() public {
        usd.mint(alice, 5 * CREDIT);
        vm.startPrank(alice);
        usd.approve(address(baskets), 5 * CREDIT);
        uint256 id = baskets.offerSwap(winner, address(fusd), 1, address(usd), 5 * CREDIT);
        assertEq(baskets.owed(alice, address(usd)), 0);
        baskets.cancelSwap(id);
        vm.stopPrank();
        assertEq(baskets.owed(alice, address(usd)), 5 * CREDIT);
        vm.prank(winner);
        vm.expectRevert(abi.encodeWithSelector(Baskets.NotYours.selector, id));
        baskets.acceptSwap(id);
        _assertExact(address(usd));
    }

    function test_swapNeedsTheCredit() public {
        usd.mint(alice, 5 * CREDIT);
        vm.startPrank(alice);
        usd.approve(address(baskets), 5 * CREDIT);
        uint256 id = baskets.offerSwap(winner, address(fusd), 1, address(usd), 5 * CREDIT);
        vm.stopPrank();
        vm.prank(winner);
        vm.expectRevert(Baskets.NothingOwed.selector);
        baskets.acceptSwap(id);
    }

    // ---------- refunds by input ----------

    function test_refundsOnlyWhenTheRaceSaysSo() public {
        _pledge(alice, address(usd), 10 * CREDIT);
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(Baskets.NotRefundable.selector, B, address(usd)));
        baskets.claimRefund(B, address(usd));
    }

    /// As pof's _refund_inputs: each funder's share of what's left, rounded down, the remainder to the last funder
    /// (here the highest address), whatever order they claim in.
    function test_refundByInputRounding() public {
        _pledge(alice, address(usd), 1);
        _pledge(bob, address(usd), 1);
        _pledge(carol, address(usd), 1);
        // 3 units pledged, 1 paid out to leave 2: each gets 2 * 1 / 3 = 0, the last funder the remainder 2.
        baskets.pay(B, address(usd), winner, 1);
        baskets.close(B);
        address last = _max(_max(alice, bob), carol);
        address[3] memory order = [carol, alice, bob];
        for (uint256 i; i < 3; ++i) {
            vm.prank(order[i]);
            baskets.claimRefund(B, address(usd));
        }
        assertEq(baskets.owed(last, address(usd)), 2);
        assertEq(baskets.held(B, address(usd)), 0);
        _assertExact(address(usd));
    }

    function test_noPledgeOrPayOnceRefunding() public {
        _pledge(alice, address(usd), 10 * CREDIT);
        _pledge(bob, address(usd), 10 * CREDIT);
        baskets.close(B);
        vm.prank(alice);
        baskets.claimRefund(B, address(usd));
        vm.expectRevert(abi.encodeWithSelector(Baskets.PotRefunding.selector, B, address(usd)));
        baskets.pay(B, address(usd), winner, 1);
        usd.mint(carol, 1);
        vm.startPrank(carol);
        usd.approve(address(baskets), 1);
        vm.expectRevert(abi.encodeWithSelector(Baskets.PotRefunding.selector, B, address(usd)));
        baskets.pledge(B, address(usd), 1);
        vm.stopPrank();
        vm.prank(alice);
        vm.expectRevert(Baskets.NothingOwed.selector);
        baskets.claimRefund(B, address(usd));
    }

    /// Any pledges, any payout, any claim order: the refunds add up to exactly what was left, each funder gets its
    /// share rounded down, and the last funder the remainder.
    function testFuzz_refundsAddUp(uint64[5] memory amounts, uint256 paidSeed, uint256 orderSeed) public {
        address[5] memory funders;
        uint256 total;
        for (uint256 i; i < 5; ++i) {
            funders[i] = address(uint160(0x1000 + i * 7919));
            amounts[i] = uint64(bound(amounts[i], 1, 100 * CREDIT));
            _pledge(funders[i], address(usd), amounts[i]);
            total += amounts[i];
        }
        uint256 paid = bound(paidSeed, 0, total);
        if (paid != 0) baskets.pay(B, address(usd), winner, paid);
        baskets.close(B);
        uint256 left = total - paid;
        for (uint256 k; k < 5; ++k) {
            uint256 j = (orderSeed % 5 + k * 3) % 5; // a permutation of 0..4
            vm.prank(funders[j]);
            baskets.claimRefund(B, address(usd));
        }
        uint256 sum;
        uint256 floors;
        for (uint256 i; i < 5; ++i) {
            uint256 got = baskets.owed(funders[i], address(usd));
            uint256 floor_ = left * amounts[i] / total;
            floors += floor_;
            if (i != 4) assertEq(got, floor_); // funders[4] has the highest address
            sum += got;
        }
        assertEq(sum, left);
        assertEq(baskets.owed(funders[4], address(usd)), left * amounts[4] / total + (left - floors));
        _assertExact(address(usd));
    }

    function _max(address a, address b) internal pure returns (address) {
        return a > b ? a : b;
    }

    // ---------- withdraw-only ----------

    /// Spec scenario "An invariant breaks": the coin is withdraw-only, forever; pledges and payouts in it are refused;
    /// its credits and refunds are still pulled; the other coins carry on (owner, 2026-10-26).
    function test_invariantBreakStopsOnlyThatCoin() public {
        LyingCoin lying = new LyingCoin();
        _pledge(alice, address(lying), 10 * CREDIT);
        baskets.pay(B, address(lying), winner, 4 * CREDIT);
        _pledge(alice, address(usd), 10 * CREDIT);
        assertTrue(baskets.check());

        lying.shrink(address(baskets), 1);
        assertFalse(baskets.solvent(address(lying)));
        assertFalse(baskets.check());
        assertTrue(baskets.withdrawOnly(address(lying)));
        assertFalse(baskets.withdrawOnly(address(usd)));

        lying.mint(bob, 1);
        vm.startPrank(bob);
        lying.approve(address(baskets), 1);
        vm.expectRevert(abi.encodeWithSelector(Baskets.WithdrawOnlyMode.selector, address(lying)));
        baskets.pledge(B, address(lying), 1);
        vm.stopPrank();
        vm.expectRevert(abi.encodeWithSelector(Baskets.WithdrawOnlyMode.selector, address(lying)));
        baskets.pay(B, address(lying), winner, 1);

        // The other coin carries on.
        baskets.pay(B, address(usd), winner, 3 * CREDIT);
        _pledge(bob, address(usd), 1 * CREDIT);

        // The stopped coin's credits are still pulled, and its pots refund without the race saying so; the
        // shrunk unit is a loss to whoever pulls last.
        vm.prank(winner);
        baskets.withdraw(address(lying), winner);
        vm.prank(alice);
        baskets.claimRefund(B, address(lying));
        assertEq(lying.balanceOf(winner), 4 * CREDIT);
        assertEq(baskets.owed(alice, address(lying)), 6 * CREDIT);
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(Baskets.NotRefundable.selector, B, address(usd)));
        baskets.claimRefund(B, address(usd));
    }

    /// A payout checks its coin first: the withdrawal that finds the break switches the mode on.
    function test_withdrawChecksFirst() public {
        LyingCoin lying = new LyingCoin();
        _pledge(alice, address(lying), 10 * CREDIT);
        baskets.pay(B, address(lying), winner, 4 * CREDIT);
        lying.shrink(address(baskets), 1);
        vm.prank(winner);
        baskets.withdraw(address(lying), winner);
        assertTrue(baskets.withdrawOnly(address(lying)));
    }

    /// A hostile coin's issuer (here: balanceOf reverts) stops only its own coin.
    function test_hostileCoinStopsOnlyItself() public {
        LyingCoin hostile = new LyingCoin();
        _pledge(alice, address(usd), 10 * CREDIT);
        _pledge(bob, address(hostile), 1);
        hostile.breakBalanceOf(true);
        assertFalse(baskets.check());
        assertTrue(baskets.withdrawOnly(address(hostile)));
        assertFalse(baskets.withdrawOnly(address(usd)));
        baskets.pay(B, address(usd), winner, 1);
        assertEq(baskets.owed(winner, address(usd)), 1);
    }

    function test_withdrawOnlyRefusesSwapsInThatCoin() public {
        LyingCoin lying = new LyingCoin();
        _pledge(alice, address(lying), 10 * CREDIT);
        baskets.pay(B, address(lying), winner, 4 * CREDIT);
        usd.mint(alice, 2 * CREDIT);
        vm.startPrank(alice);
        usd.approve(address(baskets), 2 * CREDIT);
        uint256 id = baskets.offerSwap(winner, address(lying), 4 * CREDIT, address(usd), 1 * CREDIT);
        lying.shrink(address(baskets), 1);
        baskets.check();
        vm.expectRevert(abi.encodeWithSelector(Baskets.WithdrawOnlyMode.selector, address(lying)));
        baskets.offerSwap(winner, address(lying), 1, address(usd), 1 * CREDIT);
        vm.stopPrank();
        vm.prank(winner);
        vm.expectRevert(abi.encodeWithSelector(Baskets.WithdrawOnlyMode.selector, address(lying)));
        baskets.acceptSwap(id);
        vm.prank(alice);
        baskets.cancelSwap(id); // the offer's payment comes back
        assertEq(baskets.owed(alice, address(usd)), 1 * CREDIT);
    }
}
