// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Test, console} from "forge-std/Test.sol";
import {IFeesV3} from "../../src/v3/IFeesV3.sol";
import {TEST_REPO} from "./helpers/SuiteWindows.sol";
import {IValidators} from "../../src/v3/IValidators.sol";
import {Status, Kind, Submission, Panel, Seat} from "../../src/v3/PanelsBase.sol";
import {PanelsSetup} from "./helpers/PanelsSetup.sol";
import {PanelRulesLib} from "../../src/v3/PanelRules.sol";

/// Random sequences of draws, silences, joins, leaves, pauses and time on the real Panels (proof-of-fix#251, task
/// 3.13; specs/panel-liveness, "No submission is ever stuck"). Honest validators seal, reveal and post receipts when
/// drawn; silent ones never do. A keeper makes every call anyone may make. The handler deploys its own version (the
/// signing helpers are PanelsSetup's). Since contract batch 4 (task 3.24, L25) also challenges and test disputes,
/// on 7 or 15 validators under the strict or the launch's panel rules (`ChallengeLiveness*` below); the keeper then
/// draws, redraws and lapses challenges and releases stuck challenge panels too.
contract LivenessHandler is PanelsSetup {
    address[] public keys; // every validator ever added (the genesis one first)
    mapping(address => bool) public silent;
    uint256[] public ids;
    uint256 internal added;
    // how deep the runs go
    uint256 public releases;
    uint256 public redrawn;
    uint256 public finals;
    // challenges (batch 4)
    uint256 public challenges;
    uint256 public lapsed;
    uint256 public challengeDraws;
    /// A keeper pass left a challenge with no panel past its CHALLENGE_DEADLINE (it must lapse at once).
    bool public overdue;
    uint256 internal joinMax;
    address internal challenger = makeAddr("challenger");

    /// `extra` validators beside the genesis one, the launch's rules or the strict ones. The original run: 3, strict,
    /// up to 9 joins; the challenge runs: 6 or 14 (7 or 15 validators), up to 6 joins.
    constructor(uint256 extra, bool launch) {
        rules = launch ? PanelRulesLib.launch() : PanelRulesLib.strict();
        _deployVersion(3, false);
        keys.push(genesisKey);
        for (uint256 i; i < extra; ++i) {
            keys.push(_addSpread(++added, FAMILIES, 3));
        }
        joinMax = extra == 3 ? 9 : extra + 6;
        fees.bind(); // the handler stands for the race: each check opens in FeesV3 at its epoch (v3.1 polish, F1)
    }

    function idCount() external view returns (uint256) {
        return ids.length;
    }

    function panelsAddress() external view returns (address) {
        return address(pn);
    }

    // ---------- the parties ----------

    /// A submission above k = 1's limit ($50), so its panel is 3 or more and never held (the hold is not L19's).
    function open(uint256 seed) external {
        if (ids.length >= 10) return;
        uint256 id = ids.length + 1;
        ids.push(id);
        fees.open(id);
        _open(id, 60e6 + seed % 190e6);
    }

    // ---------- a family priced later (v3.1 polish, F1, task 1.3) ----------

    bytes32[] public later; // the families announced by `price`, each priced at a later roll
    uint256 public laterSeats; // seats of a later family on a paid panel (checks opened after its first price)

    /// A new family: a validator of it joins and is announced, and every active validator of an earlier family posts
    /// a table pricing it (three counting tables of other families give it a first price at the next roll, which the
    /// keeper makes). Checks opened before that roll must never seat it on a paid panel.
    function price(uint256 seed) external {
        if (later.length >= 3) return;
        bytes32 fam = keccak256(abi.encode("a later family", later.length));
        later.push(fam);
        address k = _add(keccak256(abi.encode("later host", later.length)), fam, _tee(seed % 3), 1, FULL_BOND);
        keys.push(k);
        fees.announce(k);
        bytes32[] memory priced = fees.pricedFamilies();
        uint256 n = priced.length + later.length;
        bytes32[] memory fs = new bytes32[](n);
        uint256[3][] memory ts = new uint256[3][](n);
        for (uint256 i; i < n; ++i) {
            fs[i] = i < priced.length ? priced[i] : later[i - priced.length];
            ts[i] = [uint256(4_000_000), 200_000, 20_000_000];
        }
        uint256[4] memory sh = [uint256(11_244_444), 1_234_722, 269_531_250, 2_700_000_000];
        for (uint256 i; i < keys.length; ++i) {
            address v = keys[i];
            if (reg.validator(v).state != IValidators.State.Active || _isLater(reg.validator(v).family)) continue;
            vm.prank(v);
            fees.post(sh, fs, ts);
        }
    }

    function _isLater(bytes32 fam) internal view returns (bool) {
        for (uint256 i; i < later.length; ++i) {
            if (later[i] == fam) return true;
        }
        return false;
    }

    /// The invariant's count: seats on counted, audit and challenge panels whose family wasn't priced at their check's
    /// epoch, and panels whose pay at that epoch (`checkCost`, the audit's and the challenge's pay; `settle` prices a
    /// counted panel alike) reverts. Both must stay 0.
    function unpricedSeats() external view returns (uint256 bad) {
        uint256 n = pn.panelCount();
        for (uint256 pid = 1; pid <= n; ++pid) {
            Panel memory p = pn.panel(pid);
            if (p.kind == Kind.Shadow) continue;
            address[] memory js = pn.judges(pid);
            uint256 e = fees.drawEpoch(p.id);
            IFeesV3.Report[] memory rs = new IFeesV3.Report[](js.length);
            uint256 m;
            for (uint256 i; i < js.length; ++i) {
                if (js[i] == address(0)) continue; // an empty seat
                bytes32 fam = reg.validator(js[i]).family;
                if (!fees.isPriced(fam) || fees.pricedFrom(fam) > e) ++bad;
                rs[m].payee = js[i];
                rs[m++].family = fam;
            }
            if (m == 0) continue;
            assembly ("memory-safe") {
                mstore(rs, m)
            }
            try fees.checkCost(p.id, TEST_REPO, rs) {} catch {
                ++bad;
            }
        }
    }

    /// Seats of the later families so far (the depth of the runs: a later family does get seated, for checks opened
    /// after its first price).
    function laterSeated() external view returns (uint256 seated) {
        uint256 n = pn.panelCount();
        for (uint256 pid = 1; pid <= n; ++pid) {
            if (pn.panel(pid).kind == Kind.Shadow) continue;
            address[] memory js = pn.judges(pid);
            for (uint256 i; i < js.length; ++i) {
                if (js[i] != address(0) && _isLater(reg.validator(js[i]).family)) ++seated;
            }
        }
    }

    function join(uint256 seed) external {
        if (added >= joinMax) return;
        address k = _addSpread(++added, FAMILIES, 3);
        keys.push(k);
        silent[k] = seed % 3 == 0;
    }

    function leave(uint256 seed) external {
        address k = keys[1 + seed % (keys.length - 1)];
        IValidators.State s = reg.validator(k).state;
        if (s != IValidators.State.Active && s != IValidators.State.BelowFloor) return;
        vm.prank(k);
        reg.leave(k);
    }

    function goSilent(uint256 seed) external {
        address k = keys[seed % keys.length];
        silent[k] = !silent[k];
    }

    function pause(uint256 seed) external {
        address k = keys[seed % keys.length];
        vm.prank(k);
        try pn.setCapacity(k, (seed >> 8) % 2 == 0 ? 0 : 5) {} catch {}
    }

    /// A challenge (or, `test`, a D21 dispute: the same path in Panels) of a counted verdict in its window or held.
    function challenge(uint256 seed) external {
        _file(seed, keccak256("evidence"));
    }

    function dispute(uint256 seed) external {
        _file(seed, keccak256("a failing test"));
    }

    function _file(uint256 seed, bytes32 evidence) internal {
        if (ids.length == 0) return;
        uint256 id = ids[seed % ids.length];
        try race.challenge(id, challenger, evidence) {
            ++challenges;
        } catch {}
    }

    function passTime(uint256 seed) external {
        vm.warp(vm.getBlockTimestamp() + 1 + seed % (30 * pn.REVEAL_WINDOW())); // up to 30 hours (or minutes)
        vm.roll(vm.getBlockNumber() + 1 + (seed >> 8) % 300);
    }

    // ---------- the keeper and the honest judges ----------

    function keep() public {
        // the pricing periods that ended, closed (one part a call)
        while (vm.getBlockTimestamp() >= fees.start() + (fees.rolled() + 1) * 1 days) {
            fees.roll();
        }
        for (uint256 j; j < ids.length; ++j) {
            _keepSubmission(ids[j]);
        }
        _track();
        for (uint256 i; i < live.length; ++i) {
            _sealHonest(live[i]);
        }
        for (uint256 i; i < live.length; ++i) {
            _revealHonest(live[i]);
        }
        _track();
        for (uint256 i; i < live.length; ++i) {
            _deadlines(live[i]);
        }
        _track();
        for (uint256 i; i < live.length; ++i) {
            _sealHonest(live[i]); // a replacement just seated seals at once, as an honest node would
        }
    }

    uint256[] internal live; // judging panels not yet counted or closed (shadows aren't judged here)
    uint256 internal scanned;

    function _track() internal {
        uint256 n = pn.panelCount();
        for (uint256 pid = scanned + 1; pid <= n; ++pid) {
            if (pn.panel(pid).kind != Kind.Shadow) live.push(pid);
        }
        scanned = n;
        for (uint256 i; i < live.length;) {
            Panel memory p = pn.panel(live[i]);
            if (p.counted || p.closed) {
                live[i] = live[live.length - 1];
                live.pop();
            } else {
                ++i;
            }
        }
    }

    function _keepSubmission(uint256 id) internal {
        Submission memory s = pn.submission(id);
        if (s.status == Status.Waiting && _try(abi.encodeCall(pn.draw, (id)))) s = pn.submission(id); // re-targeted
        for (uint256 t; t < 2 && s.status == Status.Sealed; ++t) {
            // a keeper draws as soon as the seed block is past (a seed block over 256 blocks back re-targets first)
            _rollPast(s.seedBlock);
            _try(abi.encodeCall(pn.draw, (id)));
            s = pn.submission(id);
            if (s.status == Status.Judging && s.redraws != 0) ++redrawn;
        }
        if ((s.status == Status.Held || s.status == Status.Window) && s.challengeOpen && s.challengePid == 0) {
            // a challenge waiting for a panel: drawn from its seed block, redrawn at a registry change or its retry
            // time, lapsed past its deadline (L25)
            bool waits = s.challengeEpoch != 0 && reg.epoch() + 1 == s.challengeEpoch
                && block.timestamp < s.challengeRetryAt;
            for (uint256 t; t < 2 && !waits; ++t) {
                s = pn.submission(id);
                if (!s.challengeOpen || s.challengePid != 0) break;
                if (s.challengeEpoch == 0) _rollPast(s.challengeBlock);
                _try(abi.encodeCall(pn.drawChallenge, (id)));
                if (pn.submission(id).challengePid != 0) ++challengeDraws;
            }
            if (_try(abi.encodeCall(pn.lapseChallenge, (id)))) ++lapsed;
            s = pn.submission(id);
            if (s.challengeOpen && s.challengePid == 0 && block.timestamp > s.challengeBy) overdue = true;
        }
        if (s.status == Status.Held) {
            _try(abi.encodeCall(pn.startWindow, (id)));
        } else if (s.status == Status.Window) {
            if (!s.auditWaits) _rollPast(s.auditBlock);
            _try(abi.encodeCall(pn.drawAudits, (id)));
            _try(abi.encodeCall(pn.releaseAudits, (id)));
            if (_try(abi.encodeCall(pn.finalize, (id)))) ++finals;
        }
    }

    function _sealHonest(uint256 pid) internal {
        Panel memory p = pn.panel(pid);
        if (p.k == 0 || p.counted || p.closed || p.kind == Kind.Shadow || block.timestamp > p.sealBy) return;
        for (uint256 i; i < p.k; ++i) {
            Seat memory x = pn.seat(pid, i);
            if (x.key == address(0) || x.hasSeal || silent[x.key]) continue;
            _seal(pid, x.key, true); // honest judges agree: no audit or challenge disagrees
        }
    }

    function _revealHonest(uint256 pid) internal {
        Panel memory p = pn.panel(pid);
        if (p.k == 0 || p.counted || p.closed || p.kind == Kind.Shadow) return;
        if (p.seats < p.k || p.nSealed < p.k || block.timestamp > p.revealBy) return;
        if (block.timestamp <= p.sealBy) vm.warp(p.sealBy + 1);
        for (uint256 i; i < p.k; ++i) {
            Seat memory x = pn.seat(pid, i);
            if (x.key == address(0) || x.revealed || silent[x.key]) continue;
            _reveal(pid, x.key);
            if (pn.panel(pid).counted) return;
            _receipt(pid, x.key);
            if (pn.panel(pid).counted) return;
        }
    }

    function _deadlines(uint256 pid) internal {
        Panel memory p = pn.panel(pid);
        if (p.k == 0 || p.counted || p.closed || p.kind == Kind.Shadow) return;
        _try(abi.encodeCall(pn.advance, (pid)));
        if (pn.panel(pid).seats < p.k) _try(abi.encodeCall(pn.refill, (pid)));
        if (_try(abi.encodeCall(pn.release, (pid)))) ++releases;
    }

    function _try(bytes memory call) internal returns (bool ok) {
        (ok,) = address(pn).call(call);
    }

    // ---------- the end of a run ----------

    /// Liveness: the silences stay, but every pause lifts and honest validators of every family join (with too few
    /// eligible, or families that can't fill a panel, a submission rightly waits with its redraw scheduled, which
    /// the invariant allows; here the network can judge); then the keeper and time alone bring every submission to
    /// final or refunded within a bounded number of rounds.
    function settleAll() external {
        for (uint256 i; i < keys.length; ++i) {
            vm.prank(keys[i]);
            try pn.setCapacity(keys[i], 5) {} catch {}
        }
        vm.roll(vm.getBlockNumber() + 2 * pn.CAP_DELAY());
        for (uint256 i; i < keys.length; ++i) {
            (uint256 checks,,,) = pn.capacity(keys[i]);
            if (checks != 0) continue;
            vm.prank(keys[i]);
            pn.setCapacity(keys[i], 5);
        }
        vm.roll(vm.getBlockNumber() + pn.CAP_DELAY());
        // honest validators of every family, each on its own host, active: any panel the network may draw (up to
        // 7, under the family and TEE-type caps) can be filled by honest judges, so nothing waits for want of them
        for (uint256 f; f < FAMILIES; ++f) {
            address k = _add(keccak256(abi.encode("honest host", f)), _family(f), _tee(f % 3), 1, FULL_BOND);
            require(reg.validator(k).state == IValidators.State.Active, "an honest validator qualified");
            keys.push(k);
        }
        // a reveal window a step (an hour, or a minute in the minutes run), so honest judges never miss a deadline
        for (uint256 r; r < 600; ++r) {
            keep();
            if (_allDone()) return;
            vm.warp(vm.getBlockTimestamp() + pn.REVEAL_WINDOW());
            vm.roll(vm.getBlockNumber() + 20);
        }
    }

    function _allDone() internal view returns (bool) {
        for (uint256 j; j < ids.length; ++j) {
            Status st = pn.submission(ids[j]).status;
            if (st != Status.Final && st != Status.Released) return false;
        }
        return true;
    }

    function allDone() external view returns (bool) {
        return _allDone();
    }

    /// Submissions final, and refunded (Released).
    function tally() external view returns (uint256 final_, uint256 released) {
        for (uint256 j; j < ids.length; ++j) {
            Status st = pn.submission(ids[j]).status;
            if (st == Status.Final) ++final_;
            if (st == Status.Released) ++released;
        }
    }
}

/// forge-config: default.invariant.runs = 24
/// forge-config: default.invariant.depth = 40
contract LivenessInvariantV3Test is Test {
    LivenessHandler handler;

    function setUp() public {
        handler = new LivenessHandler(3, false);
        bytes4[] memory sel = new bytes4[](8);
        sel[0] = LivenessHandler.open.selector;
        sel[1] = LivenessHandler.join.selector;
        sel[2] = LivenessHandler.leave.selector;
        sel[3] = LivenessHandler.goSilent.selector;
        sel[4] = LivenessHandler.pause.selector;
        sel[5] = LivenessHandler.passTime.selector;
        sel[6] = LivenessHandler.keep.selector;
        sel[7] = LivenessHandler.price.selector;
        targetContract(address(handler));
        targetSelector(FuzzSelector(address(handler), sel));
    }

    /// L19's invariant: every submission is, at every moment, in exactly one of: drawn with a live deadline (sealed
    /// for its seed, or judging on a panel that isn't closed), waiting with a scheduled redraw, counted (held or in its
    /// window), final, or refunded. Its status is one value, so "exactly one" is that each status carries its schedule.
    function invariant_noSubmissionIsStuck() public view {
        _check();
    }

    /// v3.1 polish, F1 (task 1.3): every seated validator of a counted, audit or challenge panel is of a family priced
    /// at its check's epoch, and that panel's pay at the epoch never reverts `Unpriced`, whatever families were priced
    /// since (the `price` action).
    function invariant_seatsPricedAtTheirChecksEpoch() public view {
        assertEq(handler.unpricedSeats(), 0);
    }

    function _check() internal view {
        _checkLiveness(handler);
    }

    /// L19's invariant as L25 restates it: also, a counted verdict frozen by one challenge has that challenge drawn
    /// with a live deadline (its panel open), or waiting with a scheduled redraw (RETRY_DELAY at most), or about to
    /// be drawn from its seed block; every challenge has its CHALLENGE_DEADLINE; and a verdict has at most MAX_REDRAWS
    /// lapsed challenges.
    function _checkLiveness(LivenessHandler h) internal view {
        PanelsLike pn = PanelsLike(h.panelsAddress());
        for (uint256 j; j < h.idCount(); ++j) {
            uint256 id = h.ids(j);
            Submission memory s = pn.submission(id);
            Status st = s.status;
            if (st == Status.Sealed) {
                assertGt(s.seedBlock, 0, "sealed: a seed block");
            } else if (st == Status.Waiting) {
                assertGt(s.retryAt, 0, "waiting: a scheduled redraw");
                assertLe(s.retryAt, block.timestamp + 24 hours, "waiting: within RETRY_DELAY");
            } else if (st == Status.Judging) {
                Panel memory p = pn.panel(s.pid);
                assertEq(p.id, id, "judging: its panel");
                assertTrue(!p.closed && !p.counted, "judging: a live panel");
                assertGt(p.revealBy, 0, "judging: a deadline");
            } else if (st == Status.Held || st == Status.Window) {
                assertTrue(pn.panel(s.pid).counted, "counted");
                if (st == Status.Window) assertGt(s.finalAt, 0, "a window's end");
            } else {
                assertTrue(st == Status.Final || st == Status.Released, "final or refunded");
            }
            assertLe(s.redraws, 3, "at most MAX_REDRAWS released rounds");
            assertLe(s.lapses, 3, "at most MAX_REDRAWS lapsed challenges");
            if (!s.challengeOpen) continue;
            assertTrue(st == Status.Held || st == Status.Window, "a challenge freezes a counted verdict");
            assertGt(s.challengeBy, 0, "a challenge has a deadline");
            if (s.challengePid != 0) {
                Panel memory cp = pn.panel(s.challengePid);
                assertEq(uint256(cp.kind), uint256(Kind.Challenge));
                assertTrue(!cp.closed && !cp.counted, "a challenge panel: live");
                assertGt(cp.revealBy, 0, "a challenge panel: a deadline");
            } else if (s.challengeEpoch != 0) {
                assertGt(s.challengeRetryAt, 0, "a waiting challenge: a scheduled redraw");
                assertLe(s.challengeRetryAt, block.timestamp + 24 hours, "within RETRY_DELAY");
            } else {
                assertGt(s.challengeBlock, 0, "a challenge before its draw: a seed block");
            }
        }
    }

    /// After every run: with the silences kept but room and three honest validators added, every submission ends
    /// final or refunded.
    function afterInvariant() public {
        handler.settleAll();
        _check();
        assertTrue(handler.allDone(), "every submission final or refunded");
        assertFalse(handler.overdue(), "no challenge outlived its deadline without a panel");
    }

    /// A scripted run of the `price` action (v3.1 polish, F1): checks opened before a later family's first price never
    /// seat it, while checks opened after do; every pay at a check's epoch stays priced.
    function test_theHandlerPricesALaterFamily() public {
        uint256 hour = PanelsLike(handler.panelsAddress()).REVEAL_WINDOW();
        handler.join(1);
        handler.join(2);
        handler.open(0);
        handler.open(7);
        handler.price(0);
        handler.passTime(25 * hour);
        handler.keep(); // the roll gives the later family its first price
        for (uint256 i; i < 4; ++i) {
            handler.open(11 * i);
        }
        for (uint256 i; i < 12; ++i) {
            handler.passTime(20 * hour);
            handler.keep();
            _check();
            assertEq(handler.unpricedSeats(), 0);
        }
        handler.settleAll();
        assertEq(handler.unpricedSeats(), 0);
        assertTrue(handler.allDone());
        console.log("seats of the later family:", handler.laterSeated());
    }

    /// A scripted run reaching the paths: an honest panel's verdict final; then, with two validators silent, stuck
    /// rounds released and redrawn; and the invariant after each step.
    function test_theHandlerReachesTheReleasePaths() public {
        uint256 hour = PanelsLike(handler.panelsAddress()).REVEAL_WINDOW(); // an hour, or a minute in the minutes run
        handler.join(1);
        handler.join(2);
        handler.open(0);
        handler.keep();
        for (uint256 i; i < 4; ++i) {
            handler.passTime(20 * hour);
            handler.keep();
            _check();
        }
        handler.goSilent(1);
        handler.goSilent(2);
        handler.goSilent(3); // three of six silent: a panel of 5 can't replace them all
        handler.open(100);
        for (uint256 i; i < 12; ++i) {
            handler.passTime(20 * hour);
            handler.keep();
            _check();
        }
        handler.settleAll();
        _check();
        assertTrue(handler.allDone());
        (uint256 final_, uint256 released) = handler.tally();
        assertGt(final_, 0, "a verdict final");
        assertGt(handler.releases(), 0, "a stuck round released");
        final_;
        released;
    }
}

interface PanelsLike {
    function submission(uint256 id) external view returns (Submission memory);
    function panel(uint256 pid) external view returns (Panel memory);
    function REVEAL_WINDOW() external view returns (uint256);
}

/// The restated invariant with challenges, test disputes, silences, pauses, joins and leaves (proof-of-fix#251, contract
/// batch 4, task 3.24; specs/panel-liveness, "Any sequence with challenges"): on 7 or 15 validators, under the strict
/// rules (#132's: a challenge of a panel of 7 at 7 validators can't be drawn fresh, and lapses) and the launch's
/// (panels of 3, same-size fresh challenges). Every challenge ends, and every submission ends final or refunded.
abstract contract ChallengeLivenessBase is Test {
    LivenessHandler handler;

    function _setUpWith(uint256 extra, bool launch) internal {
        handler = new LivenessHandler(extra, launch);
        bytes4[] memory sel = new bytes4[](10);
        sel[0] = LivenessHandler.open.selector;
        sel[1] = LivenessHandler.join.selector;
        sel[2] = LivenessHandler.leave.selector;
        sel[3] = LivenessHandler.goSilent.selector;
        sel[4] = LivenessHandler.pause.selector;
        sel[5] = LivenessHandler.passTime.selector;
        sel[6] = LivenessHandler.keep.selector;
        sel[7] = LivenessHandler.challenge.selector;
        sel[8] = LivenessHandler.dispute.selector;
        sel[9] = LivenessHandler.price.selector;
        targetContract(address(handler));
        targetSelector(FuzzSelector(address(handler), sel));
    }

    function invariant_noSubmissionOrChallengeIsStuck() public view {
        LivenessChecks.check(handler);
    }

    /// v3.1 polish, F1 (task 1.3), with challenges: as `LivenessInvariantV3Test`'s.
    function invariant_seatsPricedAtTheirChecksEpoch() public view {
        require(handler.unpricedSeats() == 0, "a seat of a family priced after its check's epoch");
    }

    function afterInvariant() public {
        handler.settleAll();
        LivenessChecks.check(handler);
        assertTrue(handler.allDone(), "every submission final or refunded");
        assertFalse(handler.overdue(), "no challenge outlived its deadline without a panel");
    }

    /// A scripted run reaching the challenge paths: verdicts, then challenges and disputes with a third of the
    /// validators silent and one paused; the invariant after each step; then everything ends.
    function test_theHandlerReachesTheChallengePaths() public {
        uint256 hour = PanelsLike(handler.panelsAddress()).REVEAL_WINDOW();
        for (uint256 i; i < 4; ++i) {
            handler.open(i * 37);
        }
        handler.keep();
        handler.passTime(3 * hour);
        handler.keep();
        for (uint256 i; i < 4; ++i) {
            handler.challenge(i);
            handler.dispute(i + 1);
        }
        handler.goSilent(1);
        handler.goSilent(2);
        handler.pause(3);
        for (uint256 i; i < 30; ++i) {
            handler.passTime(8 * hour);
            handler.keep();
            LivenessChecks.check(handler);
        }
        handler.settleAll();
        LivenessChecks.check(handler);
        assertTrue(handler.allDone());
        assertGt(handler.challenges(), 0, "challenges filed");
        assertFalse(handler.overdue());
    }
}

/// The invariant's checks, shared by every run.
library LivenessChecks {
    function check(LivenessHandler h) internal view {
        PanelsLike pn = PanelsLike(h.panelsAddress());
        for (uint256 j; j < h.idCount(); ++j) {
            Submission memory s = pn.submission(h.ids(j));
            Status st = s.status;
            if (st == Status.Sealed) {
                require(s.seedBlock > 0, "sealed: a seed block");
            } else if (st == Status.Waiting) {
                require(s.retryAt > 0 && s.retryAt <= block.timestamp + 24 hours, "waiting: a scheduled redraw");
            } else if (st == Status.Judging) {
                Panel memory p = pn.panel(s.pid);
                require(p.id == h.ids(j) && !p.closed && !p.counted && p.revealBy > 0, "judging: a live panel");
            } else if (st == Status.Held || st == Status.Window) {
                require(pn.panel(s.pid).counted, "counted");
                require(st != Status.Window || s.finalAt > 0, "a window's end");
            } else {
                require(st == Status.Final || st == Status.Released, "final or refunded");
            }
            require(s.redraws <= 3 && s.lapses <= 3, "at most MAX_REDRAWS released rounds and lapsed challenges");
            if (!s.challengeOpen) continue;
            require(st == Status.Held || st == Status.Window, "a challenge freezes a counted verdict");
            require(s.challengeBy > 0, "a challenge has a deadline");
            if (s.challengePid != 0) {
                Panel memory cp = pn.panel(s.challengePid);
                require(cp.kind == Kind.Challenge && !cp.closed && !cp.counted && cp.revealBy > 0, "a live panel");
            } else if (s.challengeEpoch != 0) {
                require(
                    s.challengeRetryAt > 0 && s.challengeRetryAt <= block.timestamp + 24 hours, "a scheduled redraw"
                );
            } else {
                require(s.challengeBlock > 0, "a challenge before its draw: a seed block");
            }
        }
    }
}

/// forge-config: default.invariant.runs = 12
/// forge-config: default.invariant.depth = 40
contract ChallengeLivenessStrict7Test is ChallengeLivenessBase {
    function setUp() public {
        _setUpWith(6, false);
    }
}

/// forge-config: default.invariant.runs = 12
/// forge-config: default.invariant.depth = 40
contract ChallengeLivenessLaunch7Test is ChallengeLivenessBase {
    function setUp() public {
        _setUpWith(6, true);
    }
}

/// forge-config: default.invariant.runs = 8
/// forge-config: default.invariant.depth = 40
contract ChallengeLivenessStrict15Test is ChallengeLivenessBase {
    function setUp() public {
        _setUpWith(14, false);
    }
}

/// forge-config: default.invariant.runs = 8
/// forge-config: default.invariant.depth = 40
contract ChallengeLivenessLaunch15Test is ChallengeLivenessBase {
    function setUp() public {
        _setUpWith(14, true);
    }
}
