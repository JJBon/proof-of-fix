// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Test} from "forge-std/Test.sol";
import {IERC20Errors} from "@openzeppelin/contracts/interfaces/draft-IERC6093.sol";
import {Oracles} from "./helpers/Oracles.sol";
import {Race} from "../src/Race.sol";
import {Token} from "../src/Token.sol";
import {MockCoin} from "./mocks/MockCoin.sol";

/// Task 3.5 (design D15; local-contract's "Upgrades by migration"): two versions of the token side by side. Here
/// this test contract is both versions' Race: it records closes and keeps the clock (`day`), which both read. The
/// Race-level migration, two real Races sharing the schedule, is MigrationRaceTest below.
contract MigrationTest is Test {
    uint256 constant E = 10_000e6; // pof's TOKENS emission
    uint256 public day;

    Token v1;
    address founder = makeAddr("founder");
    address s1 = makeAddr("solver1");
    address s2 = makeAddr("solver2");
    address r1 = makeAddr("reporter1");

    function setUp() public {
        v1 = _version(Token(address(0)));
    }

    function _version(Token previous) internal returns (Token) {
        return new Token(address(this), founder, E, 100, 100, 208, 1_500, 7, 300, 7, previous);
    }

    function _toPeriod(uint256 p) internal {
        day = p * 7;
    }

    /// The first day period p's claims are open: a week after it ends.
    function _toClaims(uint256 p) internal {
        day = (p + 1) * 7 + 7;
    }

    function _claimAll(Token t, uint256 p) internal {
        if (t.totalWeight(p) == 0) return;
        uint256 n = t.closeCount(p);
        uint256 big = t.largest(p);
        for (uint256 i; i < n; ++i) {
            if (i != big) t.claim(p, i);
        }
        t.claim(p, big);
        t.claimFounder(p);
    }

    /// v1 tokens for `who`: a close of its own in period p, claimed.
    function _earnV1(uint256 p, address who) internal {
        _toPeriod(p);
        v1.record(100 + p, p, 10, 10, who, address(0));
        _toClaims(p);
        _claimAll(v1, p);
    }

    // ---------- the swap ----------

    /// Scenario "A holder swaps": the v1 tokens are burned and the holder gets the same number of v2 tokens.
    function test_aHolderSwaps() public {
        _earnV1(0, s1);
        Token v2 = _version(v1);
        uint256 had = v1.balanceOf(s1);
        uint256 supply1 = v1.totalSupply();
        vm.startPrank(s1);
        v1.approve(address(v2), 600e6);
        v2.swap(600e6);
        vm.stopPrank();
        assertEq(v1.balanceOf(s1), had - 600e6);
        assertEq(v1.totalSupply(), supply1 - 600e6); // burned, not held
        assertEq(v1.balanceOf(address(v2)), 0);
        assertEq(v2.balanceOf(s1), 600e6);
        assertEq(v2.totalSupply(), 600e6);
        assertEq(v2.swapped(), 600e6);
        assertEq(v1.totalSupply() + v2.totalSupply(), supply1); // the versions together: no more than v1 minted
        assertEq(v2.minted(0), 0); // a swap isn't emission
    }

    /// The swap burns only what the holder approved and holds; the first version has nothing to swap from.
    function test_swapNeedsTheHoldersTokens() public {
        _earnV1(0, s1);
        Token v2 = _version(v1);
        vm.prank(s1);
        vm.expectRevert(abi.encodeWithSelector(IERC20Errors.ERC20InsufficientAllowance.selector, address(v2), 0, 1));
        v2.swap(1);
        vm.prank(s2); // holds none
        v1.approve(address(v2), 1);
        vm.prank(s2);
        vm.expectRevert(abi.encodeWithSelector(IERC20Errors.ERC20InsufficientBalance.selector, s2, 0, 1));
        v2.swap(1);
        vm.prank(s1);
        vm.expectRevert(Token.Refused.selector);
        v1.swap(1);
    }

    /// The swap stays open forever: years of periods later, a v1 holder still swaps.
    function test_theSwapStaysOpen() public {
        _earnV1(0, s1);
        Token v2 = _version(v1);
        day = 7 * 520;
        uint256 had = v1.balanceOf(s1);
        vm.startPrank(s1);
        v1.approve(address(v2), had);
        v2.swap(had);
        vm.stopPrank();
        assertEq(v2.balanceOf(s1), had);
        assertEq(v1.totalSupply(), v1.balanceOf(founder)); // the founder's share, not swapped
    }

    /// Versions chain: v3 continues v2, which continues v1. A v1 holder swaps through v2 into v3.
    function test_swapThroughTheChain() public {
        _earnV1(0, s1);
        Token v2 = _version(v1);
        Token v3 = _version(v2);
        uint256 had = v1.balanceOf(s1);
        vm.startPrank(s1);
        v1.approve(address(v2), had);
        v2.swap(had);
        v2.approve(address(v3), had);
        v3.swap(had);
        vm.stopPrank();
        assertEq(v1.balanceOf(s1) + v2.totalSupply(), 0);
        assertEq(v3.balanceOf(s1), had);
        assertEq(v1.totalSupply() + v3.totalSupply(), v1.minted(0));
    }

    // ---------- one schedule across versions ----------

    /// Scenario "Two versions run at once": both close paid bounties in the same period; their combined mint for it
    /// is the schedule's emission, all of it v1's (the oldest version with a close in it). In the next period only v2
    /// has closes, and it gets the whole emission.
    function test_twoVersionsRunAtOnce() public {
        Token v2 = _version(v1);
        _toPeriod(3);
        v1.record(1, 3, 4, 4, s1, r1);
        v2.record(1, 3, 40, 40, s2, r1);
        _toPeriod(4);
        v2.record(2, 4, 5, 5, s2, r1);
        _toClaims(4);
        for (uint256 p = 3; p <= 4; ++p) {
            _claimAll(v2, p); // v2 claims before v1 has minted anything: what v1 will mint still counts
            _claimAll(v1, p);
        }
        assertEq(v1.minted(3) + v2.minted(3), v1.emission(3));
        assertEq(v2.minted(3), 0);
        assertEq(v2.committed(3), 0);
        assertEq(v1.minted(4) + v2.minted(4), v1.emission(4));
        assertEq(v2.minted(4), v2.emission(4));
        assertEq(v1.totalSupply() + v2.totalSupply(), v1.emission(3) + v1.emission(4));
    }

    /// Scenario "v1 still pays its pending claims": a v1 close whose period ends after v2 is deployed, and after
    /// holders start swapping, is still claimed in v1; v2 leaves that period's emission to it.
    function test_v1StillPaysItsPendingClaims() public {
        _earnV1(0, s2);
        _toPeriod(2);
        v1.record(1, 2, 7, 7, s1, r1);
        Token v2 = _version(v1); // deployed with v1's close pending
        v2.record(1, 2, 3, 3, s2, r1);
        uint256 had = v1.balanceOf(s2);
        vm.startPrank(s2);
        v1.approve(address(v2), had);
        v2.swap(had);
        vm.stopPrank();
        _toClaims(2);
        _claimAll(v2, 2);
        _claimAll(v1, 2);
        uint256 pool = v1.emission(2) - v1.founderShare(2);
        assertEq(v1.balanceOf(s1) + v1.balanceOf(r1), pool);
        assertEq(v1.balanceOf(r1), pool * 1_500 / 10_000);
        assertEq(v2.minted(2), 0);
        assertEq(v2.balanceOf(s2), had); // only its swap
    }

    /// The founder's share continues in v2, and isn't doubled: one share of each period's emission, from whichever
    /// version mints it, for the published 208 periods in all.
    function test_theFoundersShareIsntDoubled() public {
        Token v2 = _version(v1);
        _toPeriod(1);
        v1.record(1, 1, 5, 5, s1, r1);
        v2.record(1, 1, 5, 5, s2, r1);
        _toPeriod(2);
        v2.record(2, 2, 5, 5, s2, r1);
        _toPeriod(208);
        v1.record(3, 208, 5, 5, s1, r1);
        v2.record(3, 208, 5, 5, s2, r1);
        _toClaims(208);
        for (uint256 p = 1; p <= 2; ++p) {
            _claimAll(v1, p);
            _claimAll(v2, p);
        }
        _claimAll(v1, 208);
        _claimAll(v2, 208);
        assertEq(v1.balanceOf(founder), v1.emission(1) / 100);
        assertEq(v2.balanceOf(founder), v1.emission(2) / 100);
        assertEq(v1.founderShare(208) + v2.founderShare(208), 0); // the published periods are over in every version
    }

    /// Three versions: each period's emission goes, whole, to the oldest version with a close in it.
    function test_theOldestVersionWithACloseTakesThePeriod() public {
        Token v2 = _version(v1);
        Token v3 = _version(v2);
        _toPeriod(1);
        v2.record(1, 1, 5, 5, s1, r1);
        v3.record(1, 1, 5, 5, s2, r1);
        _toPeriod(2);
        v3.record(2, 2, 5, 5, s2, r1);
        _toClaims(2);
        for (uint256 p = 1; p <= 2; ++p) {
            _claimAll(v3, p);
            _claimAll(v2, p);
        }
        assertEq(v2.minted(1), v1.emission(1));
        assertEq(v3.minted(1), 0);
        assertEq(v3.minted(2), v1.emission(2));
        assertEq(v2.minted(2) + v1.minted(1) + v1.minted(2), 0);
    }

    /// A new version keeps the schedule: the emission and its decay, the founder and its share and periods, the
    /// period length and the grace, from the same start. Only its own close rules (the reporter's share, the tolerance) may differ.
    function test_aNewVersionKeepsTheSchedule() public {
        vm.warp(block.timestamp + 30 days);
        vm.expectRevert(Token.BadParams.selector);
        new Token(address(this), founder, E + 1, 100, 100, 208, 1_500, 7, 300, 7, v1);
        vm.expectRevert(Token.BadParams.selector);
        new Token(address(this), founder, E, 50, 100, 208, 1_500, 7, 300, 7, v1);
        vm.expectRevert(Token.BadParams.selector);
        new Token(address(this), s1, E, 100, 100, 208, 1_500, 7, 300, 7, v1); // another founder
        vm.expectRevert(Token.BadParams.selector);
        new Token(address(this), founder, E, 100, 200, 208, 1_500, 7, 300, 7, v1);
        vm.expectRevert(Token.BadParams.selector);
        new Token(address(this), founder, E, 100, 100, 416, 1_500, 7, 300, 7, v1);
        vm.expectRevert(Token.BadParams.selector);
        new Token(address(this), founder, E, 100, 100, 208, 1_500, 14, 300, 7, v1);
        vm.expectRevert(Token.BadParams.selector);
        new Token(address(this), founder, E, 100, 100, 208, 1_500, 7, 300, 14, v1);
        Token v2 = new Token(address(this), founder, E, 100, 100, 208, 1_000, 7, 200, 7, v1);
        assertEq(v2.start(), v1.start()); // deployed 30 days later, on v1's day 0
        assertEq(address(v2.previous()), address(v1));
    }

    /// Fuzzed: in each of 6 periods, either version, both or neither close bounties of random weights; claimed in
    /// a random order, the versions together mint each period's emission, or nothing, never more.
    function testFuzz_oneScheduleAcrossVersions(uint256 seed) public {
        Token v2 = _version(v1);
        bool[6] memory any;
        for (uint256 p; p < 6; ++p) {
            _toPeriod(p);
            uint256 r = uint256(keccak256(abi.encode(seed, p)));
            for (uint256 k; k < r % 4; ++k) {
                v1.record(k, p, (r >> (8 + k * 8)) % 50, (r >> (40 + k * 8)) % 50, s1, r1);
            }
            for (uint256 k; k < (r >> 2) % 4; ++k) {
                v2.record(k, p, (r >> (72 + k * 8)) % 50, (r >> (104 + k * 8)) % 50, s2, r1);
            }
            any[p] = v1.totalWeight(p) + v2.totalWeight(p) != 0;
        }
        _toClaims(5);
        uint256 total;
        for (uint256 p; p < 6; ++p) {
            if (uint256(keccak256(abi.encode(seed, p, "order"))) % 2 == 0) {
                _claimAll(v1, p);
                _claimAll(v2, p);
            } else {
                _claimAll(v2, p);
                _claimAll(v1, p);
            }
            assertEq(v1.minted(p) + v2.minted(p), any[p] ? v1.emission(p) : 0);
            assertEq(v1.committed(p) + v2.committed(p), any[p] ? v1.emission(p) : 0);
            total += v1.minted(p) + v2.minted(p);
        }
        assertEq(v1.totalSupply() + v2.totalSupply(), total);
    }
}

/// Task 3.5 with real Races: v2 (a new Token and Race, deployed by anyone, here 3 days after v1) keeps v1's start, so
/// its days and periods are v1's. A bounty in each closes paid in period 5: v1 mints the period; v2's next close, in
/// period 6, mints v2's.
contract MigrationRaceTest is Oracles {
    uint256 constant C = 1e6;

    Race race1;
    Race race2;
    MockCoin usd;
    address reporter = makeAddr("reporter");
    address alice = makeAddr("alice");
    address solver1 = makeAddr("solver1");
    address solver2 = makeAddr("solver2");

    function _config() internal returns (Race.Config memory c) {
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
    }

    function setUp() public {
        usd = new MockCoin("Mock USD", "mUSD", 6);
        _makeOracles(3, 2);
        race1 = _newRace(_config(), _feeCoins(), 1_000, 100_000);
    }

    function _feeCoins() internal view returns (address[] memory f) {
        f = new address[](1);
        f[0] = address(usd);
    }

    function _toDay(uint256 d) internal {
        vm.warp(race1.start() + d * 1 days);
    }

    function _fund(Race race, address who, uint256 amount) internal {
        usd.mint(who, amount);
        vm.prank(who);
        usd.approve(address(race), type(uint256).max);
    }

    /// A bounty registered, accepted with weight w, funded, won by `solver` and merged today.
    function _wonAndMerged(Race race, address solver, bytes32 fix, uint256 w) internal returns (uint256 b) {
        _fund(race, reporter, 7 * C);
        vm.prank(reporter);
        uint256 i = race.register(address(usd));
        b = _accept(race, i, w);
        _fund(race, alice, 100 * C);
        vm.prank(alice);
        race.pledge(b, address(usd), 100 * C);
        _fund(race, solver, 10 * C);
        vm.prank(solver);
        uint256 id = race.commit(b, keccak256(abi.encode(fix, bytes32("salt"), solver)), address(usd));
        _result(race, id, Race.Outcome.Pass, fix, new Race.Fee[](0));
        _merged(race, b, w);
    }

    function _claimPeriod(Token t, uint256 p) internal {
        if (t.totalWeight(p) == 0) return;
        uint256 n = t.closeCount(p);
        uint256 big = t.largest(p);
        for (uint256 i; i < n; ++i) {
            if (i != big) t.claim(p, i);
        }
        t.claim(p, big);
        t.claimFounder(p);
    }

    function test_twoRacesShareTheSchedule() public {
        uint256 b1 = _wonAndMerged(race1, solver1, "fix1", 80); // day 0: last instalment's release on day 35
        _toDay(3);
        Token t1 = race1.token(); // anyone deploys a new version: it needs nothing from v1 but its address
        race2 = _newRace(_config(), _feeCoins(), 1_000, 100_000, t1);
        Token t2 = race2.token();
        assertEq(race2.start(), race1.start());
        assertEq(race2.day(), 3);
        assertEq(t2.currentPeriod(), t1.currentPeriod());
        uint256 b2 = _wonAndMerged(race2, solver2, "fix2", 60); // day 3: window to 10, release on day 35, period 5
        _toDay(10);
        uint256 b3 = _wonAndMerged(race2, solver2, "fix3", 50); // window to 17: last release on day 42, period 6
        _toDay(35);
        assertTrue(race1.settle(b1, address(usd)));
        assertTrue(race2.settle(b2, address(usd)));
        _toDay(42);
        assertTrue(race2.settle(b3, address(usd)));
        assertEq(t1.closeCount(5), 1);
        assertEq(t2.closeCount(5), 1);
        assertEq(t2.closeCount(6), 1);

        _toDay(7 * 7 + 7); // period 6's claims open
        _claimPeriod(t2, 5);
        _claimPeriod(t2, 6);
        _claimPeriod(t1, 5);
        assertEq(t1.minted(5), t1.emission(5)); // v1 had a close in period 5: the period is v1's
        assertEq(t2.minted(5), 0);
        assertEq(t2.minted(6), t1.emission(6)); // v1 had none in period 6: all of it is v2's
        assertEq(t1.balanceOf(founder) + t2.balanceOf(founder), t1.emission(5) / 100 + t1.emission(6) / 100);
        assertEq(t1.totalSupply() + t2.totalSupply(), t1.emission(5) + t1.emission(6));
        assertGt(t1.balanceOf(solver1), 0);
        assertGt(t2.balanceOf(solver2), 0);

        // v1's holder moves to v2
        uint256 had = t1.balanceOf(solver1);
        vm.startPrank(solver1);
        t1.approve(address(t2), had);
        t2.swap(had);
        vm.stopPrank();
        assertEq(t1.balanceOf(solver1), 0);
        assertEq(t2.balanceOf(solver1), had);
        assertEq(t1.totalSupply() + t2.totalSupply(), t1.emission(5) + t1.emission(6));
    }
}
