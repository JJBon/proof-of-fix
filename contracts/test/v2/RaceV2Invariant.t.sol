// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {OraclesV2} from "./helpers/OraclesV2.sol";
import {RaceV2 as Race} from "../../src/v2/RaceV2.sol";
import {RaceV2Base} from "../../src/v2/RaceV2Base.sol";
import {MockCoin} from "../mocks/MockCoin.sol";
import {Verdicts} from "../../src/v2/Verdicts.sol";
import {Fees} from "../../src/v2/Fees.sol";
import {genesis} from "./helpers/GenesisV2.sol";

/// v2 (proof-of-fix#85, task 5.1): v1's invariant suite on RaceV2, unchanged.
/// Random races: every step a solver, funder, reporter or the oracle could take, in any order, with days passing.
/// The handler relays results signed by the oracle quorum (the same test keys as the deployment's). Payouts that should always go through (settle, instalments, refunds of a final bounty)
/// are counted when they revert.
contract RaceHandlerV2 is OraclesV2 {
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
    // A metered race (task 5.7): results whose credits didn't add up to the deposit, and how many were checked.
    uint256 public badCharges;
    uint256 public meteredResults;

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
    function _find(uint256 seed, RaceV2Base.State state) internal view returns (uint256) {
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
        uint256 i = race.register(address(usd), bytes32(0));
        uint256 open = _find(similar, RaceV2Base.State.Open);
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
        if (address(race.meter()) != address(0)) {
            _meteredResult(id, RaceV2Base.Outcome(1 + outcome % 4), bytes32(fix % 6), fee);
            return;
        }
        RaceV2Base.Fee[] memory fees = new RaceV2Base.Fee[](1);
        fees[0] = RaceV2Base.Fee(address(0xF00), bound(fee, 0, 6.6e6));
        _result(race, id, RaceV2Base.Outcome(1 + outcome % 4), bytes32(fix % 6), fees);
    }

    /// A metered result (task 5.7): a random number of the drawn judges report a random usage; then the credits the
    /// result gives the judges, the relayer (this handler), the infrastructure and the solver must add up to the
    /// deposit, whatever the usage: deposits always equal charges, repayments and refunds.
    function _meteredResult(uint256 id, RaceV2Base.Outcome outcome, bytes32 fix, uint256 seed) internal {
        RaceV2Base.Submission memory s = race.submission(id);
        RaceV2Base.Fee[] memory none = new RaceV2Base.Fee[](0);
        if (s.solver == address(0) || s.outcome != RaceV2Base.Outcome.None) {
            _result(race, id, outcome, fix, none);
            return;
        }
        Fees m = Fees(address(race.meter()));
        (address[] memory js,) = race.verdicts().drawn(s.seed, s.bounty, id, address(race));
        uint256 n = seed % (js.length + 1);
        for (uint256 j; j < n; ++j) {
            uint256 r = uint256(keccak256(abi.encode(seed, j)));
            Fees.Usage memory u = Fees.Usage(
                bytes32(r),
                uint64(r % 200_000),
                uint64((r >> 20) % 10_000),
                uint64((r >> 40) % 20_000),
                uint64((r >> 60) % 4_000),
                uint64((r >> 80) % 8_000),
                uint64((r >> 100) % 30)
            );
            uint256 secret;
            for (uint256 i; i < oracleSet.length; ++i) {
                if (oracleSet[i] == js[j]) secret = oracleSecrets[i];
            }
            (uint8 v, bytes32 rr, bytes32 ss) = vm.sign(secret, m.usageDigest(id, u));
            m.report(id, u, abi.encodePacked(rr, ss, v));
        }
        uint256 before = _credits(s.solver, js);
        vm.txGasPrice(seed % 3 gwei);
        _result(race, id, outcome, fix, none);
        meteredResults += 1;
        if (_credits(s.solver, js) - before != s.deposit) badCharges += 1;
    }

    function _credits(address solver, address[] memory js) internal view returns (uint256 sum) {
        address c = address(usd);
        sum = race.owed(solver, c) + race.owed(address(this), c) + race.owed(race.getConfig().infrastructure, c);
        for (uint256 j; j < js.length; ++j) {
            sum += race.owed(js[j], c);
        }
    }

    /// A solver commits a fix and it passes; anything committed before it is decided at random first (D4).
    function win(uint256 actor, uint256 b, uint256 fix, uint256 seed) external {
        uint256 bt = _find(b, RaceV2Base.State.Open);
        if (bt == 0) return;
        address a = _actor(actor);
        usd.mint(a, 7e6);
        vm.prank(a);
        uint256 id = race.commit(bt, keccak256(abi.encode(fix % 6, a)), address(usd));
        uint256[] memory subs = race.submissionsOf(bt);
        RaceV2Base.Fee[] memory none = new RaceV2Base.Fee[](0);
        bool metered = address(race.meter()) != address(0);
        for (uint256 i; i < subs.length; ++i) {
            if (subs[i] == id || race.submission(subs[i]).outcome != RaceV2Base.Outcome.None) continue;
            RaceV2Base.Outcome o = RaceV2Base.Outcome(1 + (seed >> i) % 4);
            if (metered) _meteredResult(subs[i], o, bytes32(uint256(7 + i)), seed >> i);
            else _result(race, subs[i], o, bytes32(uint256(7 + i)), none);
        }
        if (race.bounty(bt).state == RaceV2Base.State.Open) {
            if (metered) _meteredResult(id, RaceV2Base.Outcome.Pass, bytes32(fix % 6), seed);
            else _result(race, id, RaceV2Base.Outcome.Pass, bytes32(fix % 6), none);
        }
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
        uint256 bt = _find(b, RaceV2Base.State.Won);
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
        uint256 bt = _find(b, RaceV2Base.State.Merged);
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
        uint256 bt = _find(b, RaceV2Base.State.Merged); // a merged bounty may be fully paid by now
        if (bt == 0) bt = _bounty(b);
        if (bt == 0) return;
        RaceV2Base.State s = race.bounty(bt).state;
        bool fin = s == RaceV2Base.State.Paid || s == RaceV2Base.State.Refunded || s == RaceV2Base.State.Unsolved;
        address c = address(_coin(coin));
        try race.settle(bt, c) returns (bool ok) {
            if (!ok) return;
            if (s == RaceV2Base.State.Paid) paidSettles += 1;
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
contract RaceV2InvariantTest is OraclesV2 {
    Race race;
    RaceHandlerV2 handler;
    MockCoin usd;
    MockCoin eth;

    function setUp() public {
        usd = new MockCoin("Mock USD", "mUSD", 6);
        eth = new MockCoin("Mock ETH", "mETH", 18);
        address[] memory feeCoins = new address[](1);
        feeCoins[0] = address(usd);
        RaceV2Base.Config memory c;
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
        race = _deployRace(c, feeCoins);
        handler = new RaceHandlerV2(race, usd, eth);
        targetContract(address(handler));
    }

    function _startPriceBps() internal pure virtual returns (uint256) {
        return 5_000;
    }

    /// The race under test: unmetered (v1's flat check deposit) here; RaceV2MeteredInvariantTest meters it.
    function _deployRace(RaceV2Base.Config memory c, address[] memory feeCoins) internal virtual returns (Race) {
        return _newRace(c, feeCoins, 1_000, 100_000);
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
            RaceV2Base.Bounty memory bt = race.bounty(b);
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
                RaceV2Base.State s = race.bounty(b).state;
                bool fin = s == RaceV2Base.State.Paid || s == RaceV2Base.State.Refunded || s == RaceV2Base.State.Unsolved;
                if (!fin || !race.pot(b, c).refunding) continue;
                if (race.pot(b, c).refunds == race.pot(b, c).funders) assertEq(race.held(b, c), 0);
            }
        }
    }
}

/// The price opens at 95 % of the cap, so awards take nearly the whole pot: what one award still owes squeezes the
/// next one's price (Race.unpaidBefore).
contract RaceV2HighPriceInvariantTest is RaceV2InvariantTest {
    function _startPriceBps() internal pure override returns (uint256) {
        return 9_500;
    }
}

/// Task 5.7 (S15): the same random races with a check-fee meter. Every result's credits (judges, relayer,
/// infrastructure, solver) add up to its deposit, and the books stay exact.
contract RaceV2MeteredInvariantTest is RaceV2InvariantTest {
    function _deployRace(RaceV2Base.Config memory c, address[] memory feeCoins) internal override returns (Race) {
        Verdicts.Genesis memory vg = genesis(oracleSet, oracleQuorum, operatorAccounts, operatorKeys);
        Verdicts v = new Verdicts(vg);
        Fees.Genesis memory g;
        g.coin = feeCoins[0];
        g.families = vg.families;
        g.prices = new uint256[](3 * vg.families.length + 5);
        for (uint256 i; i < vg.families.length; ++i) {
            (g.prices[3 * i], g.prices[3 * i + 1], g.prices[3 * i + 2]) = (4_000_000, 200_000, 20_000_000);
        }
        uint256 b = 3 * vg.families.length;
        (g.prices[b], g.prices[b + 1], g.prices[b + 2], g.prices[b + 3], g.prices[b + 4]) =
            (11_244_444, 1_234_722, 269_531_250, 2_700_000_000, 50_000);
        g.caps = Fees.Caps(140_000, 16_000, 20, 1_000_000, 50_000, 1 gwei);
        g.defaultProfile = Fees.Profile(keccak256("test image"), 2_000, 4_096, 1_200);
        Fees m = new Fees(v, g);
        return new Race(c, feeCoins, 1_000, 100_000, v, inflationPct, 0, new bytes32[](0), new bytes32[](0), GENESIS_CONSTITUTION, m);
    }

    function invariant_chargesEqualDeposits() public view {
        assertEq(handler.badCharges(), 0);
    }
}
