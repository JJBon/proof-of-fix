// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Test} from "forge-std/Test.sol";
import {SolverBook} from "../../src/v3/SolverBook.sol";

/// The replay against the simulation (proof-of-fix#251 contract batch 3; #132 task 12.5, launch tasks 3.3 and 3.6):
/// report v5's R(minus)+F rows and the launch's pledge gate, exported by `pof.sim.openval.bookreplay` on fixed seeds,
/// replayed on a `SolverBook` at the run's times. This test plays its race (the book's only writer), calling it as
/// RaceV3 does: a claim at each commitment (`openClaim`), the merge of a final pass (`paid`), a reversed pass
/// (`reversed`, then its claim closed at finality), a final fail or a withdrawal (`closeClaim`), an upheld test
/// (`disputeUpheld`). Checked exactly, event by event:
/// - every claim the cap let in or refused (REP_BASE $50, REP_MULT 1), and every reputation after a pass or a reversal
///   (2 × its bounty off, not below zero), in micro-coins;
/// - with the gate, the count of active solvers (ACTIVE_WINDOW 26 weeks) at every issue the run listed, and whether
///   pledges were open.
/// Files: `L` (the long con, Opus 5.5 seated alone, 3 honest solvers, no gate) and `YS` (the sybil of three with free
/// identities under the gate, 1 honest solver), seed 1. The export's own integer mirror and its refusals of runs the
/// replay couldn't follow are tested in tests/test_openval_bookreplay.py.
contract ReplaySolversV3Test is Test {
    uint256 constant OPEN = 1;
    uint256 constant PASS = 2;
    uint256 constant REVERSED = 3;
    uint256 constant FAIL = 4;
    uint256 constant WITHDRAWN = 5;
    uint256 constant ACTIVE = 6;
    uint256 constant DISPUTE = 7;
    uint256 constant GATE = 8;

    struct Cols {
        uint256[] kinds;
        uint256[] ts;
        uint256[] sids;
        uint256[] whos;
        uint256[] micros;
        uint256[] oks;
        uint256[] reps;
        uint256[] counts;
    }

    function test_replayLongConSeed1() public {
        (uint256 opened,,) = _replay("v3-book-L-1.json");
        assertGt(opened, 0);
    }

    function test_replaySybilOfThreeSeed1() public {
        (,, uint256 gates) = _replay("v3-book-YS-1.json");
        assertGt(gates, 0);
    }

    function _who(uint256 w) internal pure returns (address) {
        return address(uint160(0x50_0000 + w));
    }

    function _cols(string memory json) internal pure returns (Cols memory c) {
        c.kinds = vm.parseJsonUintArray(json, ".kinds");
        c.ts = vm.parseJsonUintArray(json, ".ts");
        c.sids = vm.parseJsonUintArray(json, ".sids");
        c.whos = vm.parseJsonUintArray(json, ".whos");
        c.micros = vm.parseJsonUintArray(json, ".micros");
        c.oks = vm.parseJsonUintArray(json, ".oks");
        c.reps = vm.parseJsonUintArray(json, ".reps");
        c.counts = vm.parseJsonUintArray(json, ".counts");
    }

    function _replay(string memory file) internal returns (uint256 opened, uint256 refused, uint256 gates) {
        string memory json = vm.readFile(string.concat("test/data/", file));
        SolverBook book = new SolverBook(vm.parseJsonUint(json, ".activeWindow"));
        Cols memory c = _cols(json);
        assertEq(c.kinds.length, vm.parseJsonUint(json, ".n"));
        uint256 t0 = 1_000_000; // a constant base (a local copy of block.timestamp is re-read after a warp under via-IR)
        uint256 fake = type(uint128).max;
        for (uint256 i; i < c.kinds.length; ++i) {
            vm.warp(t0 + c.ts[i]);
            uint256 k = c.kinds[i];
            address who = _who(c.whos[i]);
            string memory at = string.concat(file, ", event ", vm.toString(i));
            if (k == OPEN) {
                bool ok;
                try book.openClaim(c.sids[i], who, c.micros[i]) {
                    ok = true;
                    ++opened;
                } catch (bytes memory err) {
                    assertEq(bytes4(err), SolverBook.OverCap.selector, at);
                    ++refused;
                }
                assertEq(ok, c.oks[i] == 1, string.concat(at, ": the cap"));
            } else if (k == PASS) {
                book.paid(c.sids[i], who, c.micros[i]);
                assertEq(book.reputation(who), c.reps[i], string.concat(at, ": reputation after a pass"));
            } else if (k == REVERSED) {
                book.reversed(c.sids[i], who, c.micros[i]);
                book.closeClaim(c.sids[i]);
                assertEq(book.reputation(who), c.reps[i], string.concat(at, ": reputation after a reversal"));
            } else if (k == FAIL || k == WITHDRAWN) {
                book.closeClaim(c.sids[i]);
                assertEq(book.reputation(who), c.reps[i], at);
            } else if (k == ACTIVE) {
                book.paid(++fake, who, 0);
            } else if (k == DISPUTE) {
                book.disputeUpheld(who);
            } else if (k == GATE) {
                ++gates;
                assertEq(book.activeCount(), c.counts[i], string.concat(at, ": the active solvers"));
                assertEq(book.pledgesOpen(), c.counts[i] >= 3, at);
            }
        }
    }
}
