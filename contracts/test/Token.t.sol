// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Test} from "forge-std/Test.sol";
import {Token} from "../src/Token.sol";

/// Task 3.4 (design D15; #58's token-emission spec and local-contract's "The token, with fixed rules"): the token on
/// its own. This test contract is its Race: it records closes and keeps the clock (`day`). The Race's own recording
/// (weights, inflation, clawback, 0 coin) is tested in Race.t.sol.
contract TokenTest is Test {
    uint256 constant BPS = 10_000;
    uint256 constant E = 10_000e6; // pof's TOKENS emission
    uint256 public day;

    Token token;
    address founder = makeAddr("founder");
    address s1 = makeAddr("solver1");
    address s2 = makeAddr("solver2");
    address r1 = makeAddr("reporter1");

    function setUp() public {
        token = _token(E, 100, 100, 208);
    }

    function _token(uint256 emission, uint256 decay, uint256 fBps, uint256 fPeriods) internal returns (Token) {
        return new Token(address(this), founder, emission, decay, fBps, fPeriods, 1_500, 7, 300, 7, Token(address(0)));
    }

    function _toPeriod(uint256 p) internal {
        day = p * 7;
    }

    /// The first day period p's claims are open: a week after it ends.
    function _toClaims(uint256 p) internal {
        day = (p + 1) * 7 + 7;
    }

    function _claimAll(Token t, uint256 p) internal {
        uint256 n = t.closeCount(p);
        uint256 big = t.largest(p);
        for (uint256 i; i < n; ++i) {
            if (i != big) t.claim(p, i);
        }
        t.claim(p, big);
        if (t.founderShare(p) != 0) t.claimFounder(p);
    }

    // ---------- the emission ----------

    /// Scenario "Two bounties close in a period": 1,000 with no founder's share, weights 3 and 1: 750 and 250.
    function test_twoBountiesClose() public {
        Token t = new Token(address(this), address(0), 1_000, 100, 0, 0, 0, 7, 300, 7, Token(address(0)));
        t.record(1, day / 7, 3, 3, s1, address(0));
        t.record(2, day / 7, 1, 1, s2, address(0));
        _toClaims(0);
        _claimAll(t, 0);
        assertEq(t.balanceOf(s1), 750);
        assertEq(t.balanceOf(s2), 250);
        assertEq(t.totalSupply(), 1_000);
        assertEq(t.minted(0), 1_000);
    }

    /// Scenario "Nothing closes": nothing is minted, not even the founder's share; the next period's emission is the
    /// schedule's.
    function test_nothingCloses() public {
        _toClaims(0);
        vm.expectRevert(Token.Refused.selector);
        token.claimFounder(0);
        t2_record(1, 10);
        _toClaims(1);
        _claimAll(token, 1);
        assertEq(token.minted(0), 0);
        assertEq(token.minted(1), token.emission(1));
        assertEq(token.emission(1), E - E / 100); // decayed once, as if period 0 had minted
        assertEq(token.totalSupply(), token.emission(1));
    }

    function t2_record(uint256 p, uint256 w) internal {
        _toPeriod(p);
        token.record(1, day / 7, w, w, s1, r1);
    }

    /// Scenario "Activity can't inflate the supply": 40 closes mint the same total as one.
    function test_activityCantInflate() public {
        for (uint256 i; i < 40; ++i) {
            token.record(i + 1, day / 7, 1 + i % 7, 1 + i % 7, i % 2 == 0 ? s1 : s2, r1);
        }
        _toClaims(0);
        _claimAll(token, 0);
        assertEq(token.minted(0), E);
        assertEq(token.totalSupply(), E);
    }

    /// Scenario "The split": 1,000 tokens give the reporter 150 and the solver 850.
    function test_theSplit() public {
        Token t = new Token(address(this), address(0), 1_000, 100, 0, 0, 1_500, 7, 300, 7, Token(address(0)));
        t.record(1, day / 7, 5, 5, s1, r1);
        _toClaims(0);
        t.claim(0, 0);
        assertEq(t.balanceOf(r1), 150);
        assertEq(t.balanceOf(s1), 850);
    }

    /// The rounding remainder goes to the first close with the largest weight, which claims last.
    function test_remainderToTheFirstLargest() public {
        Token t = new Token(address(this), address(0), 1_000, 100, 0, 0, 0, 7, 300, 7, Token(address(0)));
        t.record(1, day / 7, 1, 1, s1, address(0));
        t.record(2, day / 7, 1, 1, s2, address(0));
        t.record(3, day / 7, 1, 1, r1, address(0));
        _toClaims(0);
        assertEq(t.largest(0), 0);
        vm.expectRevert(Token.NotYet.selector); // its remainder needs the others claimed first
        t.claim(0, 0);
        t.claim(0, 1);
        t.claim(0, 2);
        t.claim(0, 0);
        assertEq(t.balanceOf(s2), 333);
        assertEq(t.balanceOf(r1), 333);
        assertEq(t.balanceOf(s1), 334);
    }

    /// A period's tokens are claimed once it has ended, once each.
    function test_claimsWaitAndDontRepeat() public {
        token.record(1, day / 7, 4, 4, s1, r1);
        vm.expectRevert(Token.NotYet.selector);
        token.claim(0, 0);
        _toClaims(0);
        token.claim(0, 0);
        vm.expectRevert(Token.Refused.selector);
        token.claim(0, 0);
        token.claimFounder(0);
        vm.expectRevert(Token.Refused.selector);
        token.claimFounder(0);
    }

    /// A period whose closes all weigh nothing mints nothing.
    function test_noWeightNoMint() public {
        token.record(1, day / 7, 0, 0, s1, r1);
        _toClaims(0);
        vm.expectRevert(Token.Refused.selector);
        token.claim(0, 0);
        vm.expectRevert(Token.Refused.selector);
        token.claimFounder(0);
    }

    /// The emission decays by 1 % a period, rounded down, as pof's TokenBook.
    function test_schedule() public view {
        uint256 e = E;
        for (uint256 p; p < 300; ++p) {
            assertEq(token.emission(p), e);
            e -= e * 100 / BPS;
        }
    }

    // ---------- the period, fixed by date (owner, 2026-10-29) ----------

    /// A period's claims open a week after it ends, so its closes can be recorded first.
    function test_claimsWaitForTheGrace() public {
        token.record(1, 0, 4, 4, s1, r1);
        day = 7; // period 0 has ended
        vm.expectRevert(Token.NotYet.selector);
        token.claim(0, 0);
        day = 13;
        vm.expectRevert(Token.NotYet.selector);
        token.claimFounder(0);
        assertFalse(token.claimsOpen(0));
        day = 14;
        token.claim(0, 0);
        token.claimFounder(0);
        assertEq(token.minted(0), E);
    }

    /// A close counts in the period the Race gives it, its last instalment's release, even if recorded later.
    function test_aCloseCountsInItsPeriod() public {
        day = 10; // period 1, within period 0's grace
        token.record(1, 0, 4, 4, s1, r1);
        assertEq(token.closeCount(0), 1);
        assertEq(token.closeCount(1), 0);
        vm.expectRevert(Token.Refused.selector); // not before its last instalment's release
        token.record(2, 2, 4, 4, s1, r1);
    }

    /// Recorded after its period's claims opened, a close is refused: that period's split can't change, and it
    /// isn't credited to a later period either (a solver could choose that period by waiting). Nothing is minted for
    /// it; the supply stays within the schedule.
    function test_aLateCloseIsRefused() public {
        token.record(1, 0, 4, 4, s1, r1);
        _toClaims(0);
        token.claim(0, 0);
        vm.expectEmit(address(token));
        emit Token.TooLate(0, 2);
        assertTrue(token.record(2, 0, 400, 100, s2, r1)); // still says whether it was inflated
        assertEq(token.closeCount(0), 1);
        assertEq(token.closeCount(2), 0);
        assertEq(token.totalWeight(0), 4);
        token.claimFounder(0);
        assertEq(token.totalSupply(), E);
        assertEq(token.balanceOf(s2), 0);
    }

    // ---------- the weight ----------

    /// Scenario "An inflated estimate": the smaller of the two estimates is the weight; within 300 % the reporter
    /// keeps its share.
    function test_theSmallerEstimate() public {
        assertFalse(token.record(1, day / 7, 300, 100, s1, r1)); // exactly 300 %: within
        Token.Close memory c = token.closesOf(0)[0];
        assertEq(c.weight, 100);
        assertEq(c.reporter, r1);
        assertFalse(token.record(2, day / 7, 90, 200, s2, r1)); // the merge estimate higher: the registration counts
        assertEq(token.closesOf(0)[1].weight, 90);
    }

    /// Scenario "Inflated beyond the tolerance": the reporter's tokens go to the solver.
    function test_inflatedBeyondTheTolerance() public {
        assertTrue(token.record(1, day / 7, 301, 100, s1, r1));
        assertEq(token.closesOf(0)[0].reporter, address(0));
        _toClaims(0);
        token.claim(0, 0);
        assertEq(token.balanceOf(r1), 0);
        assertEq(token.balanceOf(s1), E - E / 100);
    }

    // ---------- the founder's share ----------

    /// Scenario "Above the cap": a founder's share above the owner's cap (5 %, rule 3) is refused.
    function test_founderAboveTheCap() public {
        vm.expectRevert(Token.BadParams.selector);
        _token(E, 100, 501, 208);
        _token(E, 100, 500, 208);
    }

    /// The founder's share: 1 % of the period's emission, only in periods that mint.
    function test_founderShare() public {
        token.record(1, day / 7, 4, 4, s1, r1);
        _toClaims(0);
        _claimAll(token, 0);
        assertEq(token.balanceOf(founder), E / 100);
        assertEq(token.balanceOf(s1) + token.balanceOf(r1), E - E / 100);
    }

    /// Scenario "The share ends": after the published periods the whole emission goes to solved bounties.
    function test_theShareEnds() public {
        Token t = _token(E, 100, 100, 2);
        for (uint256 p; p < 3; ++p) {
            _toPeriod(p);
            t.record(p + 1, day / 7, 1, 1, s1, address(0));
        }
        _toClaims(2);
        for (uint256 p; p < 3; ++p) {
            t.claim(p, 0);
            if (p < 2) t.claimFounder(p);
        }
        assertEq(t.founderShare(2), 0);
        assertEq(t.minted(2), t.emission(2));
        assertEq(t.balanceOf(founder), t.emission(0) / 100 + t.emission(1) / 100);
    }

    // ---------- only its Race ----------

    /// Scenario "Only its Race mints": nobody else records a close, and there is no other way to mint.
    function test_onlyItsRaceRecords() public {
        vm.prank(s1);
        vm.expectRevert(Token.NotRace.selector);
        token.record(1, day / 7, 100, 100, s1, s1);
    }

    /// Scenario "Within the schedule": however many closes, a period never mints more than its emission.
    function testFuzz_withinTheSchedule(uint8 n, uint256 seed) public {
        uint256 count = uint256(n) % 30 + 1;
        for (uint256 i; i < count; ++i) {
            uint256 w = uint256(keccak256(abi.encode(seed, i))) % 1e12;
            token.record(i + 1, day / 7, w, w, i % 2 == 0 ? s1 : s2, i % 3 == 0 ? address(0) : r1);
        }
        _toClaims(0);
        if (token.totalWeight(0) == 0) return;
        _claimAll(token, 0);
        assertEq(token.minted(0), token.emission(0));
        assertEq(token.totalSupply(), token.emission(0));
    }

    /// No admin, pause or rule change: the token's external functions are the ERC-20's (with burning), the Race's
    /// record, the claims, the migration's swap and views.
    function test_noPrivilegedCall() public view {
        string memory json = vm.readFile("out/Token.sol/Token.json");
        string[41] memory allowed = [
            // ERC-20, and a holder burning its own (or approved) tokens, which the next version's swap uses
            "name", "symbol", "decimals", "totalSupply", "balanceOf", "transfer", "allowance", "approve",
            "transferFrom", "burn", "burnFrom",
            // its Race only
            "record",
            // anyone
            "claim", "claimFounder", "swap",
            // the migration's views (D15)
            "previous", "start", "swapped", "available", "committed",
            // views
            "race", "founder", "firstEmission", "decayBps", "founderBps", "founderPeriods", "reporterBps",
            "periodDays", "currentPeriod", "emission", "founderShare", "closesOf", "closeCount", "largest",
            "totalWeight", "founderClaimed", "minted", "MAX_FOUNDER_BPS", "inflationPct", "graceDays", "claimsOpen"
        ];
        uint256 n;
        for (uint256 i;; ++i) {
            string memory key = string.concat(".abi[", vm.toString(i), "]");
            if (!vm.keyExistsJson(json, key)) break;
            if (keccak256(bytes(vm.parseJsonString(json, string.concat(key, ".type")))) != keccak256("function")) {
                continue;
            }
            string memory name = vm.parseJsonString(json, string.concat(key, ".name"));
            bool ok;
            for (uint256 j; j < allowed.length && !ok; ++j) {
                ok = bytes(allowed[j]).length != 0 && keccak256(bytes(name)) == keccak256(bytes(allowed[j]));
            }
            assertTrue(ok, string.concat("unexpected external function: ", name));
            ++n;
        }
        assertEq(n, 41);
    }
}
