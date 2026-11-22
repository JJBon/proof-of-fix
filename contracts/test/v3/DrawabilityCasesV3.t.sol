// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {console} from "forge-std/Test.sol";
import {Status, Submission} from "../../src/v3/PanelsBase.sol";
import {DrawabilitySetup} from "./helpers/DrawabilitySetup.sol";

/// Every row of reports/challenge-drawability-v1.md's tables 1 and 2 as a test (proof-of-fix#251, contract batch 4,
/// task 3.26): 7 and 15 validators bonded $250, spread (each its own operator account and host, three TEE types),
/// bounties of $10, $25, $50 and $125, and 1, 2 and 3 families (3 both before and after all are known), under the
/// strict settings (#132's: every cap `Strict`, `kTop` 7, `Larger`) and the launch's (every cap `Off`, `kTop` 3,
/// `Same`). Each case reports what k is, whether its audit, its challenge, its test dispute and an appeal draw, and how
/// the challenge and the dispute end; one `CASE` line each in the log, from which the report's table is regenerated:
///
///   CASE n=<7|15> families=<1|2|3> known=<0-3> rules=<strict|launch> bounty=<$> k=<k> audit=<none|drawn|stuck>
///        challenge=<fresh|second|none>:<counted|lapsed> dispute=<...>:<...> appeal=<k>
///
/// What the decisions (L23-L25) require, asserted here: every challenge and dispute ends (counted or lapsed, never
/// open); with the launch's rules k = 3, the audit is drawn and the challenge and the dispute are drawn and counted at 7
/// and 15 validators; with the strict rules k = 7, and at 7 validators the challenge is judged by D27's second draw
/// while fewer than three families are known, and lapses at CHALLENGE_DEADLINE once all three are (it waited forever
/// before batch 4).
///
/// **A lone wrong pass caught by its audit (#251 contract batch 5, #290)**, at 7 and 15 validators under the launch's
/// rules: an outage leaves only the genesis validator drawable, so a fix to a $10, $25 or $50 bounty gets k = 1 and
/// a wrong lone pass; by its count `m` of the others are back (3, 4, 5, 6, and 14 at 15), and the network stays so.
/// A keeper then starts its window when it may, draws its audits (honest: they catch it), ends each challenge as
/// `_endChallenge` does (retried until CHALLENGE_DEADLINE, else lapsed), files a watcher's challenge in the window
/// once the audits are in while the pass stands (up to MAX_REDRAWS lapses), and finalizes. Where the verdict is still held, the rest of the network comes back and the
/// keeper goes on. One `LONE` line a case:
///
///   LONE n=<7|15> m=<m> bounty=<$> id=<id> count=<held|window> audits=<drawn>/<due> end=<reversed|paid|held|refunded>
///        recovered=<reversed|paid|refunded|->
///
/// Asserted: the wrong pass is never paid (`paid`: final as a pass). Before batch 5 the hold ended at m = 3, its
/// audits took two of the three, and their challenge lapsed: paid at m = 3 and 4 (and at 5 with a random audit).
contract DrawabilityCasesV3Test is DrawabilitySetup {
    // ---------- 7 validators ----------

    function test_n7_strict_oneFamily() public {
        _row(7, 1, 1, false);
    }

    function test_n7_strict_twoFamilies() public {
        _row(7, 2, 2, false);
    }

    function test_n7_strict_threeFamiliesTwoKnown() public {
        _row(7, 3, 2, false);
    }

    function test_n7_strict_threeFamiliesAllKnown() public {
        _row(7, 3, 3, false);
    }

    function test_n7_launch_oneFamily() public {
        _row(7, 1, 1, true);
    }

    function test_n7_launch_twoFamilies() public {
        _row(7, 2, 2, true);
    }

    function test_n7_launch_threeFamiliesTwoKnown() public {
        _row(7, 3, 2, true);
    }

    function test_n7_launch_threeFamiliesAllKnown() public {
        _row(7, 3, 3, true);
    }

    // ---------- 15 validators ----------

    function test_n15_strict_oneFamily() public {
        _row(15, 1, 1, false);
    }

    function test_n15_strict_twoFamilies() public {
        _row(15, 2, 2, false);
    }

    function test_n15_strict_threeFamiliesTwoKnown() public {
        _row(15, 3, 2, false);
    }

    function test_n15_strict_threeFamiliesAllKnown() public {
        _row(15, 3, 3, false);
    }

    function test_n15_launch_oneFamily() public {
        _row(15, 1, 1, true);
    }

    function test_n15_launch_twoFamilies() public {
        _row(15, 2, 2, true);
    }

    function test_n15_launch_threeFamiliesTwoKnown() public {
        _row(15, 3, 2, true);
    }

    function test_n15_launch_threeFamiliesAllKnown() public {
        _row(15, 3, 3, true);
    }

    // ---------- a lone wrong pass caught by its audit (batch 5) ----------

    function test_n7_launch_loneWrongPassAudited() public {
        _loneRow(7);
    }

    function test_n15_launch_loneWrongPassAudited() public {
        _loneRow(15);
    }

    // ---------- the cases ----------

    struct Case {
        uint256 n;
        uint256 families;
        uint256 known;
        bool launch;
        uint256 bounty;
    }

    function _row(uint256 n, uint256 families, uint256 known, bool launch) internal {
        _deployRules(launch ? _launch() : _strict(), _spread());
        _layout(n, families, _spread());
        _knowFamilies(known);
        uint256[4] memory bounties = [uint256(10e6), 25e6, 50e6, 125e6];
        for (uint256 i; i < 4; ++i) {
            uint256 snap = vm.snapshotState();
            _case(Case(n, families, known, launch, bounties[i]));
            vm.revertToState(snap);
        }
    }

    function _case(Case memory x) internal {
        uint256 id = _id();
        uint256 pid = _verdict(id, x.bounty, true);
        assertTrue(pid != 0, "drawn");
        uint256 k = pn.panel(pid).k;
        assertEq(k, x.launch ? 3 : 7, "k: kTop with the launch's rules, 7 with the strict ones");
        // its random audit, if due: drawn from outside the panel, or stuck (L19's release then applies)
        _rollPast(pn.submission(id).auditBlock);
        pn.drawAudits(id);
        Submission memory s = pn.submission(id);
        string memory audit = s.auditsDue == 0 ? "none" : s.auditsDrawn == s.auditsDue ? "drawn" : "stuck";
        if (x.launch || x.n == 15) assertEq(s.auditsDrawn, s.auditsDue, "an audit due is drawn");
        else assertEq(s.auditsDrawn, 0, "7 of 7 seated: nobody to audit");
        uint256 snap = vm.snapshotState();
        (uint256 cEnd, uint256 cHow) = _challengeCase(id, EVIDENCE);
        vm.revertToState(snap);
        (uint256 dEnd, uint256 dHow) = _challengeCase(id, TEST_HASH);
        vm.revertToState(snap);
        _expect(x, cEnd, cHow);
        _expect(x, dEnd, dHow);
        // an appeal is a new submission at the same bounty, drawn as any (the original judges allowed)
        uint256 apid = _openAndDraw(_id(), x.bounty);
        uint256 ak = apid == 0 ? 0 : pn.panel(apid).k;
        assertEq(ak, k, "an appeal draws like the verdict");
        console.log(
            string.concat(
                "CASE n=",
                vm.toString(x.n),
                " families=",
                vm.toString(x.families),
                " known=",
                vm.toString(x.known),
                x.launch ? " rules=launch" : " rules=strict",
                " bounty=",
                vm.toString(x.bounty / 1e6),
                " k=",
                vm.toString(k),
                " audit=",
                audit,
                string.concat(" challenge=", _how(cHow), ":", _end(cEnd)),
                string.concat(" dispute=", _how(dHow), ":", _end(dEnd), " appeal=", vm.toString(ak))
            )
        );
    }

    /// A challenge (or, with a test's hash, a D21 dispute) of the verdict, ended as a keeper would end it.
    function _challengeCase(uint256 id, bytes32 evidence) internal returns (uint256 ending, uint256 how) {
        uint256 cpid = _challenge(id, evidence);
        (ending, how) = _endChallenge(id, cpid, true);
        assertFalse(pn.submission(id).challengeOpen, "every challenge ends");
    }

    function _expect(Case memory x, uint256 ending, uint256 how) internal pure {
        bool famCap = x.known >= 3;
        if (x.launch) {
            require(ending == 1, "launch: the challenge is drawn and counted");
            require(famCap ? how == 1 : how != 0, "launch: a fresh panel (or D27's second draw before 3 families)");
        } else if (x.n == 7) {
            if (famCap) require(ending == 2 && how == 0, "strict, 7, three known families: it lapses");
            else require(ending == 1 && how == 2, "strict, 7, fewer than three known: D27's second draw");
        } else {
            require(ending == 1 || ending == 2, "strict, 15: it ends");
            if (!famCap) require(ending == 1, "strict, 15, fewer than three known: fresh or the second draw");
        }
    }

    function _how(uint256 how) internal pure returns (string memory) {
        return how == 1 ? "fresh" : how == 2 ? "second" : "none";
    }

    function _end(uint256 ending) internal pure returns (string memory) {
        return ending == 1 ? "counted" : "lapsed";
    }

    // ---------- the lone cases ----------

    uint256 internal constant LONE_SEEDS = 4; // ids a bounty and `m`

    function _loneRow(uint256 n) internal {
        _deployRules(_launch(), _spread());
        address[] memory keys = _layout(n, 1, _spread());
        _knowFamilies(1);
        for (uint256 i = 1; i < n; ++i) {
            vm.prank(keys[i]);
            pn.setCapacity(keys[i], 0); // the outage: paused, as if absent (L16)
        }
        vm.roll(vm.getBlockNumber() + pn.CAP_DELAY() + 1);
        uint256[5] memory ms = [uint256(3), 4, 5, 6, n - 1];
        uint256[3] memory bounties = [uint256(10e6), 25e6, 50e6];
        uint256 paid;
        for (uint256 j; j < 5; ++j) {
            if (j > 0 && ms[j] <= ms[j - 1]) continue;
            for (uint256 b; b < 3; ++b) {
                for (uint256 t; t < LONE_SEEDS; ++t) {
                    uint256 snap = vm.snapshotState();
                    if (_loneCase(n, ms[j], bounties[b], 1000 * ms[j] + 10 * b + t + 1, keys)) ++paid;
                    vm.revertToState(snap);
                }
            }
        }
        assertEq(paid, 0, "a lone wrong pass caught by its audit is never paid");
    }

    /// One case; returns whether the wrong pass was paid.
    function _loneCase(uint256 n, uint256 m, uint256 bounty, uint256 id, address[] memory keys)
        internal
        returns (bool paid)
    {
        uint256 pid = _openAndDraw(id, bounty);
        for (uint256 r; pid == 0 && r < 8; ++r) {
            // its sample missed the one drawable validator (8 tries a seat over the roster): it waits, and is drawn
            // again from a fresh seed at its retry time (L19)
            vm.warp(pn.submission(id).retryAt);
            pn.draw(id);
            pid = _draw(id);
        }
        require(pid != 0 && pn.panel(pid).k == 1, "the outage: k = 1, the genesis validator alone");
        _resume(keys, 1, m + 1);
        _judge(pid, _all(1, true)); // a wrong lone pass
        Submission memory s = pn.submission(id);
        string memory counted = s.status == Status.Held ? "held" : "window";
        string memory end = _keep(id);
        paid = keccak256(bytes(end)) == keccak256("paid");
        string memory recovered = "-";
        if (keccak256(bytes(end)) == keccak256("held")) {
            _resume(keys, m + 1, n);
            recovered = _keep(id);
            if (keccak256(bytes(recovered)) == keccak256("paid")) paid = true;
        }
        s = pn.submission(id);
        console.log(
            string.concat(
                "LONE n=",
                vm.toString(n),
                " m=",
                vm.toString(m),
                " bounty=",
                vm.toString(bounty / 1e6),
                " id=",
                vm.toString(id),
                string.concat(" count=", counted, " audits=", vm.toString(s.auditsDrawn), "/", vm.toString(s.auditsDue)),
                string.concat(" end=", end, " recovered=", recovered)
            )
        );
    }

    /// Validators keys[from .. to) back at the default capacity.
    function _resume(address[] memory keys, uint256 from, uint256 to) internal {
        uint256 checks = pn.CHECKS_DEFAULT();
        for (uint256 i = from; i < to; ++i) {
            vm.prank(keys[i]);
            pn.setCapacity(keys[i], checks);
        }
        vm.roll(vm.getBlockNumber() + pn.CAP_DELAY() + 1);
    }

    /// A keeper on submission `id`, the network as it is, honest auditors and challengers (the fix fails) and a
    /// watcher that files a challenge in the window while the pass stands. Returns how it ends: `reversed` or `paid`
    /// (final), `refunded`, or `held` when nothing more can move it.
    function _keep(uint256 id) internal returns (string memory) {
        for (uint256 step; step < 24; ++step) {
            Submission memory s = pn.submission(id);
            if (s.status == Status.Final) return s.pass ? "paid" : "reversed";
            if (s.status == Status.Released) return "refunded";
            if (s.challengeOpen) {
                _endChallenge(id, s.challengePid != 0 ? s.challengePid : _drawChallenge(id), false);
                continue;
            }
            bool auditsDue = !(s.auditDecided && s.auditsDrawn == s.auditsDue);
            bool auditsWait = s.auditWaits && reg.epoch() + 1 == s.auditEpoch;
            if (s.status == Status.Held) {
                try pn.startWindow(id) {
                    continue;
                } catch {}
                if (auditsDue && !auditsWait && _audit(id) != 0) continue;
                return "held";
            }
            if (auditsDue) {
                if (!auditsWait && _audit(id) != 0) continue;
                uint256 at = pn.submission(id).auditStuckAt;
                if (at == 0) return "held";
                vm.warp(at + pn.STUCK_GRACE() + 1);
                pn.releaseAudits(id);
                continue;
            }
            if (s.pass && s.lapses < pn.MAX_REDRAWS() && vm.getBlockTimestamp() < s.finalAt) {
                race.challenge(id, challenger, EVIDENCE); // the watcher, once the audits are in
                continue;
            }
            if (vm.getBlockTimestamp() < s.finalAt) vm.warp(s.finalAt);
            pn.finalize(id);
        }
        revert("the keeper didn't settle it");
    }

    /// Its audits drawn now, every auditor voting that the fix fails; returns how many were drawn.
    function _audit(uint256 id) internal returns (uint256) {
        return _runAudits(id, !pn.submission(id).pass);
    }
}
