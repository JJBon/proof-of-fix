// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {IValidators} from "../../src/v3/IValidators.sol";
import {Panels} from "../../src/v3/Panels.sol";
import {PanelScores} from "../../src/v3/PanelScores.sol";
import {Status, Kind, Submission, Panel} from "../../src/v3/PanelsBase.sol";
import {PanelsSetup} from "./helpers/PanelsSetup.sol";
import {console} from "forge-std/Test.sol";

/// proof-of-fix#251 contract batch 3, #132 task 10.4 (D20) and the second draw of 11.4 (D27), with ADR 0007's values:
/// seats by rank (SEAT_MARGIN 5 points), the family cap only while CAP_MIN_FAMILIES (3) families are seated, contenders
/// shadowing, the draw's snapshot against grinding, and a challenge among few families closed by a second draw of the
/// original size. Each scenario of specs/judge-scores ("Seats go to the best-scoring families") and specs/judge-panels
/// ("A challenge among few families gets a second draw") is tested by its spec name.
contract SeatsV3Test is PanelsSetup {
    uint256 internal nextId = 5000;
    address internal challenger = makeAddr("challenger");

    function setUp() public {
        _deployVersion(3, false);
        usd.mint(address(race), 10_000e6);
    }

    function _id() internal returns (uint256) {
        return nextId++;
    }

    /// Family `f` gets a Scored score of `pct` % over 100 counted verdicts on passed outcomes (as Panels records them at
    /// finality).
    function _score(bytes32 f, uint256 pct) internal {
        vm.startPrank(address(pn));
        for (uint256 i; i < 100; ++i) {
            scores.recordCounted(f, true, i < pct);
        }
        vm.stopPrank();
    }

    function _famOf(address key) internal view returns (bytes32) {
        return reg.validator(key).family;
    }

    function _same(uint256 k, bool v) internal pure returns (bool[] memory out) {
        out = new bool[](k);
        for (uint256 i; i < k; ++i) {
            out[i] = v;
        }
    }

    // ---------- the seat rule (D20) ----------

    function test_seatRuleValues() public view {
        assertEq(scores.SEAT_MARGIN(), 0.05e18); // 5 points (ADR 0007)
        assertEq(scores.CAP_MIN_FAMILIES(), 3);
        assertEq(scores.SCORE_MIN(), 0.7e18);
    }

    /// Scenario "One family far ahead": the best family scores 88 % and the next 80 % (above SCORE_MIN, more than 5
    /// points behind): only the best family's validators sit on counted panels; the other's shadow-judge.
    function test_oneFamilyFarAhead() public {
        _network(8, 2, 3); // families 0 and 1, four validators each besides the genesis (family 0)
        _score(_family(0), 88);
        _score(_family(1), 80);
        assertTrue(scores.isSeated(_family(0)));
        assertFalse(scores.isSeated(_family(1)));
        assertFalse(scores.isBarred(_family(1))); // a contender, not barred
        assertEq(scores.contenderCount(), 1);
        assertEq(scores.seatedCount(), 1);
        assertEq(scores.unseatedCount(), 1);
        for (uint256 r; r < 3; ++r) {
            uint256 id = _id();
            uint256 pid = _openAndDraw(id, 100e6);
            assertTrue(pid != 0);
            address[] memory js = pn.judges(pid);
            for (uint256 i; i < js.length; ++i) {
                assertEq(_famOf(js[i]), _family(0), "only the seated family judges");
            }
            uint256 sp = pn.submission(id).shadowPid;
            if (sp != 0) {
                address[] memory ss = pn.judges(sp);
                for (uint256 i; i < ss.length; ++i) {
                    assertEq(_famOf(ss[i]), _family(1), "the contender shadow-judges");
                }
            }
            _nextCapWindow();
        }
    }

    /// One family alone may hold every seat while it is more than SEAT_MARGIN ahead: with fewer than three families
    /// seated the family cap doesn't apply, so a panel of 5 is all one family's.
    function test_oneSeatedFamilyFillsAPanel() public {
        _network(8, 2, 3);
        _score(_family(0), 88);
        _score(_family(1), 80);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 200e6);
        assertGe(pn.panel(pid).k, 3);
        assertFalse(scores.capApplies(block.number));
    }

    /// Scenario "Three families level": 75 %, 75 % and 74 % are all seated, and the family cap applies to their panels.
    function test_threeFamiliesLevel() public {
        _network(12, 3, 3);
        _score(_family(0), 75);
        _score(_family(1), 75);
        _score(_family(2), 74);
        assertEq(scores.seatedCount(), 3);
        assertEq(scores.contenderCount(), 0);
        assertTrue(scores.capApplies(block.number));
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 200e6);
        address[] memory js = pn.judges(pid);
        uint256 k = js.length;
        assertGe(k, 3);
        for (uint256 i; i < k; ++i) {
            uint256 same;
            for (uint256 j; j < k; ++j) {
                if (_famOf(js[j]) == _famOf(js[i])) ++same;
            }
            assertLe(same, (k - 1) / 2, "the family cap");
        }
    }

    /// The margin is the best Scored family's: a family 5 points behind is seated, 6 behind isn't; and seats follow the
    /// scores as they move.
    function test_marginFollowsTheBest() public {
        _score(_family(0), 90);
        _score(_family(1), 85);
        _score(_family(2), 84);
        assertTrue(scores.isSeated(_family(1)));
        assertFalse(scores.isSeated(_family(2)));
        assertEq(scores.bestScore(), 0.9e18);
        // the best family falls back: the others are within the margin again
        vm.startPrank(address(pn));
        for (uint256 i; i < 10; ++i) {
            scores.recordCounted(_family(0), true, false);
        }
        vm.stopPrank();
        assertTrue(scores.isSeated(_family(2)));
        assertEq(scores.contenderCount(), 0);
    }

    /// A Neutral family (fewer than SCORE_MIN_VERDICTS counted verdicts) is seated: it can't be ranked yet (D23's
    /// contender start for a new family isn't built), and a barred family isn't seated whatever its rank.
    function test_neutralSeatedBarredNot() public {
        _score(_family(0), 90);
        assertTrue(scores.isSeated(_family(3))); // never scored
        _score(_family(4), 60); // barred: below SCORE_MIN
        assertTrue(scores.isBarred(_family(4)));
        assertFalse(scores.isSeated(_family(4)));
    }

    /// Against grinding: a family seated by rank only after a draw's snapshot isn't drawn by it, and a cap that
    /// switched after the snapshot applies to it (a change made once the seed is known only removes validators).
    function test_seatsAtTheSnapshot() public {
        _network(8, 2, 3);
        _score(_family(0), 90);
        _score(_family(1), 84); // a contender
        uint256 id = _id();
        _open(id, 100e6); // the snapshot: family 1 isn't seated
        vm.roll(block.number + 1);
        vm.startPrank(address(pn));
        for (uint256 i; i < 10; ++i) {
            scores.recordCounted(_family(0), true, false); // family 0 falls: family 1 is seated now
        }
        vm.stopPrank();
        assertTrue(scores.isSeated(_family(1)));
        uint256 snap = pn.submission(id).snap.blockNo;
        assertFalse(scores.isSeatedSince(_family(1), snap));
        uint256 pid = _draw(id);
        address[] memory js = pn.judges(pid);
        for (uint256 i; i < js.length; ++i) {
            assertEq(_famOf(js[i]), _family(0), "a family seated after the snapshot isn't drawn by it");
        }
        // the cap: two seated now; a third seated after a snapshot switches it on, and that draw applies it
        _knowFamilies(3);
        assertTrue(scores.capApplies(snap)); // switched after the snapshot: applied
        assertTrue(scores.capChangedAt() > snap);
    }

    // ---------- the second draw among few families (D27) ----------

    /// Scenario "One family holds every seat": a panel of 7 of the one seated family passes a fix, a challenge is filed,
    /// and that family has only 3 validators outside the panel: a second draw of 7 from the family's validators, the
    /// original judges not excluded, judges the challenge, and the verdict becomes final when it is resolved.
    function test_oneFamilyHoldsEverySeat() public {
        _network(9, 1, 3); // ten validators of family 0
        _knowFamilies(1);
        assertTrue(scores.fewFamilies());
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 300e6);
        assertEq(pn.panel(pid).k, 7);
        _judge(pid, _same(7, true));
        assertEq(uint256(pn.submission(id).status), uint256(Status.Window));
        race.challenge(id, challenger, keccak256("a failing test"));
        _rollPast(pn.submission(id).challengeBlock);
        vm.recordLogs();
        pn.drawChallenge(id);
        uint256 cpid = pn.submission(id).challengePid;
        assertTrue(cpid != 0, "a second draw, not a wait");
        Panel memory cp = pn.panel(cpid);
        assertEq(cp.k, 7, "of the original size");
        assertEq(uint256(cp.kind), uint256(Kind.Challenge));
        uint256 again;
        address[] memory cjs = pn.judges(cpid);
        address[] memory ojs = pn.judges(pid);
        for (uint256 i; i < 7; ++i) {
            if (_contains(ojs, cjs[i])) ++again;
        }
        assertGe(again, 4, "the original judges are not excluded (only 3 others exist)");
        _judge(cpid, _same(7, true)); // the same family repeats its verdict: the second draw ends the wait
        Submission memory s = pn.submission(id);
        assertFalse(s.challengeOpen);
        assertTrue(s.pass);
        _finalize(id);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Final));
    }

    /// A challenge among one family closed by its second draw reverses a k = 3 pass when the second panel fails it.
    function test_secondDrawReversesAPass() public {
        _network(3, 1, 3); // four validators of one family: a panel of 3, one outside it
        _knowFamilies(1);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 100e6);
        assertEq(pn.panel(pid).k, 3);
        _judge(pid, _same(3, true));
        race.challenge(id, challenger, keccak256("a failing test"));
        _rollPast(pn.submission(id).challengeBlock);
        pn.drawChallenge(id);
        uint256 cpid = pn.submission(id).challengePid;
        assertEq(pn.panel(cpid).k, 3);
        _judge(cpid, _same(3, false));
        assertFalse(pn.submission(id).pass);
        assertTrue(pn.submission(id).lastUpheld);
    }

    /// Not for a lone verdict: among one family a k = 1 verdict's challenge waits for a fresh panel of 3 (a second draw
    /// of one could seat its judge on its own verdict; the k = 1 hold waits for its challengers anyway).
    function test_aLoneVerdictsChallengeWaits() public {
        _knowFamilies(1);
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 40e6); // the genesis validator alone
        assertEq(pn.panel(pid).k, 1);
        bool[] memory v = new bool[](1);
        v[0] = true;
        _judge(pid, v);
        _network(2, 1, 3); // two more of its family: no fresh panel of 3
        race.challenge(id, challenger, keccak256("a failing test"));
        _rollPast(pn.submission(id).challengeBlock);
        pn.drawChallenge(id);
        assertEq(pn.submission(id).challengePid, 0);
        assertTrue(pn.submission(id).challengeEpoch != 0);
    }

    /// Scenario "Three families seated": a challenge that can't draw its larger panel waits, as any challenge does.
    function test_threeFamiliesSeatedWait() public {
        _knowFamilies(3);
        assertFalse(scores.fewFamilies());
        _network(5, 3, 3); // six validators: a panel of 5, one outside it, no fresh panel of 7
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 100e6);
        uint256 k = pn.panel(pid).k;
        assertEq(k, 5);
        _judge(pid, _same(k, true));
        race.challenge(id, challenger, keccak256("a failing test"));
        _rollPast(pn.submission(id).challengeBlock);
        pn.drawChallenge(id);
        assertEq(pn.submission(id).challengePid, 0, "it waits");
        assertTrue(pn.submission(id).challengeEpoch != 0);
    }

    // ---------- gas ----------

    /// What seats by rank add: a draw reads each member's seat (and the cap's switch once), and each counted verdict
    /// at finality re-ranks the known families (a family's first verdict also registers it, once).
    function test_gasSeats() public {
        _network(12, 3, 3);
        _score(_family(0), 75);
        _score(_family(1), 75);
        _score(_family(2), 74);
        uint256 id = _id();
        _open(id, 200e6);
        uint256 sb = pn.submission(id).seedBlock;
        vm.roll(sb + 1);
        vm.setBlockhash(sb, keccak256("seed"));
        uint256 g = gasleft();
        pn.draw(id);
        console.log("draw (k = 7, three seated families, the cap on):", g - gasleft());
        uint256 pid = pn.submission(id).pid;
        _judge(pid, _same(pn.panel(pid).k, true));
        _runAudits(id, true);
        vm.warp(pn.submission(id).finalAt);
        g = gasleft();
        pn.finalize(id);
        console.log("finalize (k = 7, three Scored families re-ranked at each verdict):", g - gasleft());
        vm.prank(address(pn));
        g = gasleft();
        scores.recordCounted(_family(0), true, true);
        console.log("recordCounted (a Scored family, three known):", g - gasleft());
    }
}
