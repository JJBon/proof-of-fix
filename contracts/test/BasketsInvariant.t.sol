// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {Test} from "forge-std/Test.sol";
import {BasketsHarness} from "./mocks/BasketsHarness.sol";
import {MockCoin} from "./mocks/MockCoin.sol";
import {FrozenCoin} from "./mocks/FrozenCoin.sol";
import {FeeCoin} from "./mocks/FeeCoin.sol";
import {LyingCoin} from "./mocks/LyingCoin.sol";

/// Random sequences of calls on Baskets (design D6's invariant suite). Every call may revert; fail_on_revert is off.
contract BasketsHandler is Test {
    BasketsHarness public baskets;
    address[] public coins;
    address[] public actors;
    uint256 public constant BOUNTIES = 3;
    LyingCoin public lying; // set only in the suite where balances can shrink

    /// A payout (withdraw) that went through while its coin was insolvent and the mode stayed off.
    uint256 public paidInsolventLive;

    constructor(BasketsHarness baskets_, address[] memory coins_, LyingCoin lying_) {
        baskets = baskets_;
        coins = coins_;
        lying = lying_;
        for (uint256 i; i < 4; ++i) {
            actors.push(address(uint160(0xA000 + i)));
        }
    }

    function _coin(uint256 seed) internal view returns (address) {
        return coins[seed % coins.length];
    }

    function _actor(uint256 seed) internal view returns (address) {
        return actors[seed % actors.length];
    }

    function actorCount() external view returns (uint256) {
        return actors.length;
    }

    function coinCount() external view returns (uint256) {
        return coins.length;
    }

    function pledge(uint256 actor, uint256 bounty, uint256 coin, uint256 amount) external {
        address a = _actor(actor);
        address c = _coin(coin);
        amount = bound(amount, 1, 300 * 10 ** MockCoin(c).decimals());
        MockCoin(c).mint(a, amount);
        vm.startPrank(a);
        MockCoin(c).approve(address(baskets), amount);
        baskets.pledge(1 + bounty % BOUNTIES, c, amount);
        vm.stopPrank();
    }

    function pay(uint256 bounty, uint256 coin, uint256 to, uint256 amount) external {
        uint256 b = 1 + bounty % BOUNTIES;
        address c = _coin(coin);
        amount = bound(amount, 0, baskets.held(b, c));
        baskets.pay(b, c, _actor(to), amount);
    }

    function collect(uint256 actor, uint256 coin, uint256 to, uint256 amount) external {
        address a = _actor(actor);
        address c = _coin(coin);
        amount = bound(amount, 1, 50 * 10 ** MockCoin(c).decimals());
        MockCoin(c).mint(a, amount);
        vm.startPrank(a);
        MockCoin(c).approve(address(baskets), amount);
        baskets.collect(c, amount, _actor(to));
        vm.stopPrank();
    }

    /// What the handler holds as deposits, per coin (a ghost total).
    mapping(address coin => uint256) public deposits;

    function hold(uint256 actor, uint256 coin, uint256 amount) external {
        address a = _actor(actor);
        address c = _coin(coin);
        amount = bound(amount, 1, 50 * 10 ** MockCoin(c).decimals());
        MockCoin(c).mint(a, amount);
        vm.startPrank(a);
        MockCoin(c).approve(address(baskets), amount);
        baskets.hold(c, amount);
        vm.stopPrank();
        deposits[c] += amount;
    }

    function release(uint256 coin, uint256 amount, uint256 to) external {
        address c = _coin(coin);
        amount = bound(amount, 0, deposits[c]);
        baskets.release(c, amount, _actor(to));
        deposits[c] -= amount;
    }

    function close(uint256 bounty) external {
        baskets.close(1 + bounty % BOUNTIES);
    }

    function claimRefund(uint256 actor, uint256 bounty, uint256 coin) external {
        vm.prank(_actor(actor));
        baskets.claimRefund(1 + bounty % BOUNTIES, _coin(coin));
    }

    function withdraw(uint256 actor, uint256 coin, uint256 to) external {
        address c = _coin(coin);
        bool wasSolvent = baskets.solvent(c);
        vm.prank(_actor(actor));
        baskets.withdraw(c, address(uint160(0xB000 + to % 8)));
        if (!wasSolvent && !baskets.withdrawOnly(c)) paidInsolventLive += 1;
    }

    function offerSwap(uint256 actor, uint256 to, uint256 want, uint256 wantAmount, uint256 give, uint256 amount)
        external
    {
        address a = _actor(actor);
        address g = _coin(give);
        amount = bound(amount, 1, 50 * 10 ** MockCoin(g).decimals());
        MockCoin(g).mint(a, amount);
        vm.startPrank(a);
        MockCoin(g).approve(address(baskets), amount);
        baskets.offerSwap(_actor(to), _coin(want), bound(wantAmount, 1, 1e24), g, amount);
        vm.stopPrank();
    }

    function acceptSwap(uint256 actor, uint256 id) external {
        uint256 n = baskets.swapCount();
        if (n == 0) return;
        vm.prank(_actor(actor));
        baskets.acceptSwap(1 + id % n);
    }

    function cancelSwap(uint256 actor, uint256 id) external {
        uint256 n = baskets.swapCount();
        if (n == 0) return;
        vm.prank(_actor(actor));
        baskets.cancelSwap(1 + id % n);
    }

    function freeze(uint256 coin, uint256 actor, bool on) external {
        address c = _coin(coin);
        if (c.code.length == 0) return;
        try FrozenCoin(c).freeze(_actor(actor), on) {} catch {}
    }

    function pause(uint256 coin, bool on) external {
        try FrozenCoin(_coin(coin)).pause(on) {} catch {}
    }

    function check() external {
        baskets.check();
    }

    /// Only in the shrinking suite: the lying coin's balance in the contract drops.
    function shrink(uint256 amount) external {
        if (address(lying) == address(0)) return;
        lying.shrink(address(baskets), bound(amount, 1, 1e6));
    }
}

/// Honest coins (plain, 18-decimal, freezable) plus a fee-on-transfer coin.
contract BasketsInvariantTest is Test {
    BasketsHarness baskets;
    BasketsHandler handler;
    FeeCoin fee;

    function setUp() public {
        baskets = new BasketsHarness(1_000, 100_000);
        fee = new FeeCoin();
        address[] memory coins = new address[](4);
        coins[0] = address(new MockCoin("Mock USD", "mUSD", 6));
        coins[1] = address(new MockCoin("Mock ETH", "mETH", 18));
        coins[2] = address(new FrozenCoin());
        coins[3] = address(fee);
        handler = new BasketsHandler(baskets, coins, LyingCoin(address(0)));
        targetContract(address(handler));
    }

    /// The books are exact: each coin's balance is what open pots hold plus the credits. That includes the
    /// fee-on-transfer coin: a transfer whose fee rounds to nothing gets in whole, and every short one is refused.
    function invariant_booksExact() public view {
        for (uint256 i; i < 4; ++i) {
            address c = handler.coins(i);
            assertEq(
                MockCoin(c).balanceOf(address(baskets)),
                baskets.totalHeld(c) + baskets.totalOwed(c) + baskets.totalDeposits(c)
            );
        }
        for (uint256 i; i < 4; ++i) {
            assertFalse(baskets.withdrawOnly(handler.coins(i)));
        }
    }

    /// totalHeld is the sum of the pots; totalOwed the sum of credits plus open swap offers; totalDeposits what was held.
    function invariant_totalsAreSums() public view {
        for (uint256 i; i < 4; ++i) {
            address c = handler.coins(i);
            uint256 heldSum;
            for (uint256 b = 1; b <= handler.BOUNTIES(); ++b) {
                heldSum += baskets.held(b, c);
            }
            assertEq(baskets.totalHeld(c), heldSum);
            uint256 owedSum;
            for (uint256 a; a < handler.actorCount(); ++a) {
                owedSum += baskets.owed(handler.actors(a), c);
            }
            for (uint256 id = 1; id <= baskets.swapCount(); ++id) {
                (address from,, address giveCoin, uint256 give,,) = baskets.swaps(id);
                if (from != address(0) && giveCoin == c) owedSum += give;
            }
            assertEq(baskets.totalOwed(c), owedSum);
            assertEq(baskets.totalDeposits(c), handler.deposits(c));
        }
    }

}

/// A coin whose balance in the contract can shrink: its solvency may break, but never without its mode switching on
/// before the next payout, and the other coin carries on (spec "Safety without a key").
contract BasketsShrinkInvariantTest is Test {
    BasketsHarness baskets;
    BasketsHandler handler;
    LyingCoin lying;

    function setUp() public {
        baskets = new BasketsHarness(1_000, 100_000);
        lying = new LyingCoin();
        address[] memory coins = new address[](2);
        coins[0] = address(new MockCoin("Mock USD", "mUSD", 6));
        coins[1] = address(lying);
        handler = new BasketsHandler(baskets, coins, lying);
        targetContract(address(handler));
    }

    function invariant_noPayoutWhileInsolventAndLive() public view {
        assertEq(handler.paidInsolventLive(), 0);
    }

    /// Only the shrinking coin can stop: the honest coin's books stay exact and it never goes withdraw-only.
    function invariant_otherCoinCarriesOn() public view {
        address usd = handler.coins(0);
        assertEq(
            MockCoin(usd).balanceOf(address(baskets)),
            baskets.totalHeld(usd) + baskets.totalOwed(usd) + baskets.totalDeposits(usd)
        );
        assertFalse(baskets.withdrawOnly(usd));
    }
}
