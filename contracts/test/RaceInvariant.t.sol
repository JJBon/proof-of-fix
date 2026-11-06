// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {Oracles} from "./helpers/Oracles.sol";
import {Race} from "../src/Race.sol";
import {MockCoin} from "./mocks/MockCoin.sol";

/// Random races: every step a solver, funder, reporter or the oracle could take, in any order, with days passing.
/// The handler relays results signed by the oracle quorum (the same test keys as the deployment's). Payouts that should always go through (settle, instalments, refunds of a final bounty)
/// are counted when they revert.
contract RaceHandler is Oracles {
    Race public race;
    MockCoin public usd;
    MockCoin public eth;
    address[] public actors;
    uint256 public bounties;
    uint256 public stuck; // a payout that reverted when it shouldn't have
    // How deep the runs go: merges, clawbacks, paid bounties settled, refunds.
    uint256 public merges;
    uint256 public clawbacks;
    uint256 public paidSettles;
    uint256 public refunds;
    uint256 public secondAwards;
    string public lastStuck;

    constructor(Race race_, MockCoin usd_, MockCoin eth_) {
        race = race_;
        usd = usd_;
        eth = eth_;
        _makeOracles(3, 2);
        for (uint256 i; i < 5; ++i) {
            address a = address(uint160(0xC000 + i));
            actors.push(a);
            vm.startPrank(a);
            usd.approve(address(race), type(uint256).max);
            eth.approve(address(race), type(uint256).max);
            vm.stopPrank();
        }
    }

    function _actor(uint256 seed) internal view returns (address) {
        return actors[seed % actors.length];
    }

    function _bounty(uint256 seed) internal view returns (uint256) {
        return bounties == 0 ? 0 : 1 + seed % bounties;
    }

    /// A bounty in the given state, searching from a random one; 0 if none.
    function _find(uint256 seed, Race.State state) internal view returns (uint256) {
        for (uint256 k; k < bounties; ++k) {
            uint256 b = 1 + (seed + k) % bounties;
            if (race.bounty(b).state == state) return b;
        }
        return 0;
    }

    function _coin(uint256 seed) internal view returns (MockCoin) {
        return seed % 2 == 0 ? usd : eth;
    }

    function actorCount() external view returns (uint256) {
        return actors.length;
    }

    function wait(uint256 daysAhead) external {
        vm.warp(block.timestamp + bound(daysAhead, 0, 20) * 1 days);
    }

    /// Anyone registers; the check (the handler, as oracle) opens the bounty, or refuses it as similar to an open one.
    function openBounty(uint256 actor, uint256 similar) external {
        address a = _actor(actor);
        usd.mint(a, 7e6);
        vm.prank(a);
        uint256 i = race.register(address(usd));
        uint256 open = _find(similar, Race.State.Open);
        if (open != 0 && similar % 4 == 0) {
            _refuseSimilar(race, i, open);
            return;
        }
        bounties = _accept(race, i);
    }

    function pledge(uint256 actor, uint256 b, uint256 coin, uint256 amount) external {
        address a = _actor(actor);
        MockCoin c = _coin(coin);
        amount = bound(amount, 1, 100 * 10 ** c.decimals());
        c.mint(a, amount);
        vm.prank(a);
        race.pledge(_bounty(b), address(c), amount);
    }

    function attempt(uint256 actor, uint256 b) external {
        address a = _actor(actor);
        usd.mint(a, 1e6);
        vm.prank(a);
        race.attempt(_bounty(b), address(usd));
    }

    function stop(uint256 actor, uint256 b) external {
        vm.prank(_actor(actor));
        race.stop(_bounty(b));
    }

    function commit(uint256 actor, uint256 b, uint256 fix) external {
        address a = _actor(actor);
        usd.mint(a, 7e6);
        vm.prank(a);
        race.commit(_bounty(b), keccak256(abi.encode(fix % 6, a)), address(usd));
    }

    function result(uint256 b, uint256 which, uint256 outcome, uint256 fix, uint256 fee) external {
        uint256 bt = _bounty(b);
        if (bt == 0) return;
        uint256[] memory subs = race.submissionsOf(bt);
        if (subs.length == 0) return;
        uint256 id = subs[which % subs.length];
        Race.Fee[] memory fees = new Race.Fee[](1);
        fees[0] = Race.Fee(address(0xF00), bound(fee, 0, 6.6e6));
        _result(race, id, Race.Outcome(1 + outcome % 4), bytes32(fix % 6), fees);
    }

    /// A solver commits a fix and it passes; anything committed before it is decided at random first (D4).
    function win(uint256 actor, uint256 b, uint256 fix, uint256 seed) external {
        uint256 bt = _find(b, Race.State.Open);
        if (bt == 0) return;
        address a = _actor(actor);
        usd.mint(a, 7e6);
        vm.prank(a);
        uint256 id = race.commit(bt, keccak256(abi.encode(fix % 6, a)), address(usd));
        uint256[] memory subs = race.submissionsOf(bt);
        Race.Fee[] memory none = new Race.Fee[](0);
        for (uint256 i; i < subs.length; ++i) {
            if (subs[i] == id || race.submission(subs[i]).outcome != Race.Outcome.None) continue;
            _result(race, subs[i], Race.Outcome(1 + (seed >> i) % 4), bytes32(uint256(7 + i)), none);
        }
        if (race.bounty(bt).state == Race.State.Open) _result(race, id, Race.Outcome.Pass, bytes32(fix % 6), none);
    }

    /// A submission left without a result times out once its time has passed.
    function timeOut(uint256 b, uint256 which) external {
        uint256 bt = _bounty(b);
        if (bt == 0) return;
        uint256[] memory subs = race.submissionsOf(bt);
        if (subs.length == 0) return;
        race.timeOut(subs[which % subs.length]);
    }

    function merged(uint256 b) external {
        uint256 bt = _find(b, Race.State.Won);
        if (bt == 0) return;
        _merged(race, bt);
        merges += 1;
        if (race.bounty(bt).epoch > 1) secondAwards += 1;
    }

    function mergeExpired(uint256 b) external {
        race.mergeExpired(_bounty(b));
    }

    /// Rarer than the other steps (one call in four), so that some awards live to be paid in full.
    function challengeUpheld(uint256 b) external {
        if (b % 4 != 0) return;
        uint256 bt = _find(b, Race.State.Merged);
        if (bt == 0) return;
        _challengeUpheld(race, bt);
        clawbacks += 1;
    }

    function sunset(uint256 b) external {
        race.sunset(_bounty(b));
    }

    function junk(uint256 b) external {
        uint256 bt = _bounty(b);
        if (bt == 0) return;
        _junk(race, race.bounty(bt).issue);
    }

    /// An award's instalments always pay.
    function claimInstalments(uint256 b, uint256 coin, uint256 epoch) external {
        uint256 bt = _bounty(b);
        if (bt == 0) return;
        uint256 n = race.bounty(bt).epoch;
        if (n == 0) return;
        try race.claimInstalments(bt, address(_coin(coin)), 1 + epoch % n) {}
        catch (bytes memory err) {
            _stuck("claimInstalments", err);
        }
    }

    /// A final bounty always settles, and then every funder's refund goes through.
    function settleAndRefund(uint256 b, uint256 coin) external {
        uint256 bt = _find(b, Race.State.Merged); // a merged bounty may be fully paid by now
        if (bt == 0) bt = _bounty(b);
        if (bt == 0) return;
        Race.State s = race.bounty(bt).state;
        bool fin = s == Race.State.Paid || s == Race.State.Refunded || s == Race.State.Unsolved;
        address c = address(_coin(coin));
        try race.settle(bt, c) returns (bool ok) {
            if (!ok) return;
            if (s == Race.State.Paid) paidSettles += 1;
        } catch (bytes memory err) {
            if (fin) _stuck("settle", err);
            return;
        }
        for (uint256 i; i < actors.length; ++i) {
            if (race.pledged(bt, c, actors[i]) == 0 || race.refundedTo(bt, c, actors[i])) continue;
            vm.prank(actors[i]);
            try race.claimRefund(bt, c) {
                refunds += 1;
            } catch (bytes memory err) {
                _stuck("claimRefund", err);
            }
        }
    }

    function withdraw(uint256 actor, uint256 coin) external {
        vm.prank(_actor(actor));
        race.withdraw(address(_coin(coin)), address(0xBEEF));
    }

    function _stuck(string memory what, bytes memory err) internal {
        stuck += 1;
        lastStuck = string.concat(what, ": ", vm.toString(err));
    }
}

/// pof's defaults (the price opens at 50 %).
contract RaceInvariantTest is Oracles {
    Race race;
    RaceHandler handler;
    MockCoin usd;
    MockCoin eth;

    function setUp() public {
        usd = new MockCoin("Mock USD", "mUSD", 6);
        eth = new MockCoin("Mock ETH", "mETH", 18);
        address[] memory feeCoins = new address[](1);
        feeCoins[0] = address(usd);
        Race.Config memory c;
        c.infrastructure = address(0x1F);
        c.insurance = address(0x15);
        c.registrationFee = 2e6;
        c.issueStake = 5e6;
        c.attemptFee = 0.5e6;
        c.evaluationFee = 2e6;
        c.checkDeposit = 6.6e6;
        c.appealFee = 2e6;
        c.appealDeposit = 5e6;
        c.startPriceBps = _startPriceBps();
        c.riseBpsPerDay = 1_000;
        c.finderFeeBps = 1_765;
        c.idleDays = 28;
        c.resultDays = 7;
        c.mergeDays = 14;
        c.windowDays = 7;
        c.releaseEveryDays = 7;
        c.instalments = 4;
        _makeOracles(3, 2);
        race = _newRace(c, feeCoins, 1_000, 100_000);
        handler = new RaceHandler(race, usd, eth);
        targetContract(address(handler));
    }

    function _startPriceBps() internal pure virtual returns (uint256) {
        return 5_000;
    }

    function invariant_booksExact() public view {
        address[2] memory coins = [address(usd), address(eth)];
        for (uint256 i; i < 2; ++i) {
            address c = coins[i];
            assertEq(
                MockCoin(c).balanceOf(address(race)),
                race.totalHeld(c) + race.totalOwed(c) + race.totalDeposits(c)
            );
            assertFalse(race.withdrawOnly(c));
        }
    }

    function invariant_payoutsNeverStuck() public view {
        assertEq(handler.stuck(), 0, handler.lastStuck());
    }

    /// Every pot covers what its awards still owe: earlier awards' earned and unpaid instalments, and the current
    /// award's whole price less what it was paid. So instalments, settling and refunds can always go through.
    function invariant_potsCoverAwards() public view {
        address[2] memory coins = [address(usd), address(eth)];
        for (uint256 b = 1; b <= handler.bounties(); ++b) {
            Race.Bounty memory bt = race.bounty(b);
            for (uint256 i; i < 2; ++i) {
                address c = coins[i];
                if (race.pot(b, c).refunding) continue;
                uint256 need = race.unpaidBefore(b, c, bt.epoch);
                if (bt.epoch != 0) {
                    (,,, bool closed,) = race.awards(b, bt.epoch);
                    uint256 price = race.priceOf(b, c, bt.epoch);
                    uint256 paid = race.instalmentsPaid(b, c, bt.epoch);
                    need += closed ? race.unpaidBefore(b, c, bt.epoch + 1) - race.unpaidBefore(b, c, bt.epoch)
                        : price - paid;
                }
                assertLe(need, race.held(b, c));
            }
        }
    }

    /// A settled pot whose funders were all refunded is empty.
    function invariant_settledPotsDrain() public view {
        address[2] memory coins = [address(usd), address(eth)];
        for (uint256 b = 1; b <= handler.bounties(); ++b) {
            for (uint256 i; i < 2; ++i) {
                address c = coins[i];
                Race.State s = race.bounty(b).state;
                bool fin = s == Race.State.Paid || s == Race.State.Refunded || s == Race.State.Unsolved;
                if (!fin || !race.pot(b, c).refunding) continue;
                if (race.pot(b, c).refunds == race.pot(b, c).funders) assertEq(race.held(b, c), 0);
            }
        }
    }
}

/// The price opens at 95 % of the cap, so awards take nearly the whole pot: what one award still owes squeezes the
/// next one's price (Race.unpaidBefore).
contract RaceHighPriceInvariantTest is RaceInvariantTest {
    function _startPriceBps() internal pure override returns (uint256) {
        return 9_500;
    }
}
