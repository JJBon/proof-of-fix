// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Test} from "forge-std/Test.sol";
import {IValidators} from "../../src/v3/IValidators.sol";
import {Status, Kind, Submission, Panel, Seat} from "../../src/v3/PanelsBase.sol";
import {PanelsSetup} from "./helpers/PanelsSetup.sol";

/// Random sequences of draws, silences, joins, leaves, pauses and time on the real Panels (proof-of-fix#251, task
/// 3.13; specs/panel-liveness, "No submission is ever stuck"). Honest validators seal, reveal and post receipts when
/// drawn; silent ones never do. A keeper makes every call anyone may make. The handler deploys its own version (the
/// signing helpers are PanelsSetup's).
contract LivenessHandler is PanelsSetup {
    address[] public keys; // every validator ever added (the genesis one first)
    mapping(address => bool) public silent;
    uint256[] public ids;
    uint256 internal added;
    // how deep the runs go
    uint256 public releases;
    uint256 public redrawn;
    uint256 public finals;

    constructor() {
        _deployVersion(3, false);
        keys.push(genesisKey);
        for (uint256 i; i < 3; ++i) {
            keys.push(_addSpread(++added, FAMILIES, 3));
        }
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
        _open(id, 60e6 + seed % 190e6);
    }

    function join(uint256 seed) external {
        if (added >= 9) return;
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

    function passTime(uint256 seed) external {
        vm.warp(vm.getBlockTimestamp() + 1 + seed % (30 * pn.REVEAL_WINDOW())); // up to 30 hours (or minutes)
        vm.roll(vm.getBlockNumber() + 1 + (seed >> 8) % 300);
    }

    // ---------- the keeper and the honest judges ----------

    function keep() public {
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
        handler = new LivenessHandler();
        bytes4[] memory sel = new bytes4[](7);
        sel[0] = LivenessHandler.open.selector;
        sel[1] = LivenessHandler.join.selector;
        sel[2] = LivenessHandler.leave.selector;
        sel[3] = LivenessHandler.goSilent.selector;
        sel[4] = LivenessHandler.pause.selector;
        sel[5] = LivenessHandler.passTime.selector;
        sel[6] = LivenessHandler.keep.selector;
        targetContract(address(handler));
        targetSelector(FuzzSelector(address(handler), sel));
    }

    /// L19's invariant: every submission is, at every moment, in exactly one of: drawn with a live deadline (sealed
    /// for its seed, or judging on a panel that isn't closed), waiting with a scheduled redraw, counted (held or in its
    /// window), final, or refunded. Its status is one value, so "exactly one" is that each status carries its schedule.
    function invariant_noSubmissionIsStuck() public view {
        _check();
    }

    function _check() internal view {
        PanelsLike pn = PanelsLike(handler.panelsAddress());
        for (uint256 j; j < handler.idCount(); ++j) {
            uint256 id = handler.ids(j);
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
        }
    }

    /// After every run: with the silences kept but room and three honest validators added, every submission ends
    /// final or refunded.
    function afterInvariant() public {
        handler.settleAll();
        _check();
        assertTrue(handler.allDone(), "every submission final or refunded");
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
