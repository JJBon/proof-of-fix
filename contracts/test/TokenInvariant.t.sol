// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {Test} from "forge-std/Test.sol";
import {Token} from "../src/Token.sol";

/// The handler is the token's Race: it records closes of random weights, lets time pass, and claims in any order.
contract TokenHandler is Test {
    Token public token;
    uint256 public day;
    address[4] internal people = [address(0xA1), address(0xA2), address(0xA3), address(0xA4)];
    uint256 public lastPeriod; // the latest period anything was recorded in

    constructor() {
        token = new Token(address(this), address(0xF0), 10_000e6, 100, 100, 3, 1_500, 7, 300, 7, Token(address(0)));
    }

    /// A close in the current period or up to 3 before it: late ones, after their period's claims opened, are
    /// refused.
    function record(uint256 weight, uint256 who, uint256 rep, uint256 back) external {
        weight = bound(weight, 0, 1e15);
        address reporter = rep % 3 == 0 ? address(0) : people[rep % 4];
        uint256 cur = token.currentPeriod();
        token.record(1, cur - bound(back, 0, cur < 3 ? cur : 3), weight, weight, people[who % 4], reporter);
        lastPeriod = cur;
    }

    function wait(uint256 d) external {
        day += bound(d, 1, 10);
    }

    function claim(uint256 p, uint256 i) external {
        uint256 cur = token.currentPeriod();
        if (cur == 0) return;
        p = bound(p, 0, cur - 1);
        if (!token.claimsOpen(p)) return;
        uint256 n = token.closeCount(p);
        if (n == 0 || token.totalWeight(p) == 0) return;
        i = bound(i, 0, n - 1);
        if (token.closesOf(p)[i].claimed) return;
        try token.claim(p, i) {} catch {} // the largest waits for the others: NotYet is fine
    }

    function claimFounder(uint256 p) external {
        uint256 cur = token.currentPeriod();
        if (cur == 0) return;
        p = bound(p, 0, cur - 1);
        if (!token.claimsOpen(p) || token.totalWeight(p) == 0 || token.founderClaimed(p)) return;
        token.claimFounder(p);
    }

    /// Claims every finished period completely (for the conservation check).
    function claimEverything() external {
        uint256 cur = token.currentPeriod();
        for (uint256 p; p < cur; ++p) {
            if (!token.claimsOpen(p) || token.totalWeight(p) == 0) continue;
            Token.Close[] memory cs = token.closesOf(p);
            uint256 big = token.largest(p);
            for (uint256 i; i < cs.length; ++i) {
                if (i != big && !cs[i].claimed) token.claim(p, i);
            }
            if (!cs[big].claimed) token.claim(p, big);
            if (!token.founderClaimed(p)) token.claimFounder(p);
        }
    }
}

/// Task 3.4 (D15): over random sequences of closes, waits and claims, no period mints more than its emission, the
/// supply is what the periods minted, and a period fully claimed mints exactly its emission (pof's
/// TokenBook.conserved()).
contract TokenInvariantTest is Test {
    TokenHandler handler;
    Token token;

    function setUp() public {
        handler = new TokenHandler();
        token = handler.token();
        bytes4[] memory selectors = new bytes4[](4);
        selectors[0] = TokenHandler.record.selector;
        selectors[1] = TokenHandler.wait.selector;
        selectors[2] = TokenHandler.claim.selector;
        selectors[3] = TokenHandler.claimFounder.selector;
        targetSelector(FuzzSelector(address(handler), selectors));
        targetContract(address(handler));
    }

    /// No period mints more than its emission, and the supply is the sum of what they minted, all from finished
    /// periods.
    function invariant_withinTheSchedule() public view {
        uint256 cur = token.currentPeriod();
        uint256 sum;
        for (uint256 p; p <= handler.lastPeriod() + 1 && p <= cur; ++p) {
            uint256 m = token.minted(p);
            assertLe(m, token.emission(p), "a period minted more than its emission");
            if (!token.claimsOpen(p)) assertEq(m, 0, "a period minted before its claims opened");
            sum += m;
        }
        assertEq(token.totalSupply(), sum, "the supply isn't what the periods minted");
    }

    /// At the end of each run, claimed in full, every finished period minted its emission, or nothing if nothing
    /// weighed in it (claiming at the end keeps the runs' partial claims in play).
    function afterInvariant() public {
        handler.claimEverything();
        uint256 cur = token.currentPeriod();
        for (uint256 p; p < cur; ++p) {
            if (!token.claimsOpen(p)) continue;
            uint256 want = token.totalWeight(p) == 0 ? 0 : token.emission(p);
            assertEq(token.minted(p), want, "a period's mint isn't its emission");
        }
    }
}
