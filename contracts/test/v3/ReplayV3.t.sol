// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {Test} from "forge-std/Test.sol";
import {FeesV3} from "../../src/v3/FeesV3.sol";
import {IFeesV3, IFeesV3Validators} from "../../src/v3/IFeesV3.sol";
import {Panels} from "../../src/v3/Panels.sol";
import {Status, Kind} from "../../src/v3/PanelsBase.sol";
import {PoolV3} from "../../src/v3/PoolV3.sol";
import {RaceV3} from "../../src/v3/RaceV3.sol";
import {RaceV3Annex} from "../../src/v3/RaceV3Annex.sol";
import {RaceV3Base} from "../../src/v3/RaceV3Base.sol";
import {MockCoin} from "../mocks/MockCoin.sol";
import {MockScores} from "./helpers/FeesV3Mocks.sol";
import {ReplayRegistry, ReplayPanels} from "./helpers/ReplayStubs.sol";

/// Task 3.5's replay (proof-of-fix#138, #132): group 7's market (round 2's rules, `pricing.Baseline`), run in the
/// contracts' arithmetic by `pof.sim.openval.contract` and exported on fixed seeds, replays on RaceV3 and FeesV3 to the
/// micro-credit, as ReplayV2 does for v2's race.
///
/// The file is the simulation's calls in order: each submission (`commit`), each first wait and each stalled counted
/// panel (`signal`), each paid panel (counted: `report` by every judge, then `result`; an audit or an auditor's
/// challenge panel: `report`, then `payPanel`), the validators seated in each period (`signal` on a panel holding
/// them), and each period's close: the active validators post their tables and the period rolls. Checked exactly:
/// - every judge's pay, against the simulation's FeesV3 arithmetic (`ContractMarket.pay_micro`);
/// - every submission's counted charge from its deposit;
/// - after every roll, the service fee and every unit price against the simulation's;
/// - the race's books.
///
/// Scripted rather than replayed: Panels' draws. The simulation draws its panels from its own seeds; the contract draws
/// from block hashes the simulation can't know, so `ReplayPanels` seats exactly the judges the simulation paid. Every
/// submission has its own bounty (registered and opened in the first period, which the exporter checks has no waits:
/// the registration checks add to its submissions, which could only change a wait share), so no pass ends a queue.
contract ReplayV3Test is Test {
    uint256 constant C = 1e6;
    uint256 constant SECP_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141;
    bytes32 constant USAGE_TAG = keccak256("proof-of-fix v3 usage");
    uint256 constant COMMIT = 1;
    uint256 constant WAIT = 2;
    uint256 constant STALL = 3;
    uint256 constant COUNTED = 4;
    uint256 constant AUDIT = 5;
    uint256 constant CHALLENGE = 6;
    uint256 constant DRAWN = 7;
    uint256 constant CLOSE = 8;

    MockCoin usd;
    PoolV3 pool;
    ReplayRegistry reg;
    FeesV3 fees;
    ReplayPanels pn;
    RaceV3 rc;
    address solver = makeAddr("solver");
    address reporter = makeAddr("reporter");

    string json;
    uint256[] items;
    uint256[] kinds;
    uint256[] sids;
    uint256[] starts;
    uint256[] lens;
    bytes32[] fams;
    uint256[6] usage;
    uint256 nUnits;
    mapping(uint256 vid => address) keyOf;
    mapping(address => uint256) secretOf;
    mapping(uint256 sid => uint256) idOf;
    uint256[] bounties;
    uint256 nextBounty;
    uint256 helper; // a registration check whose scripted panel carries each period's seated validators
    uint256 period;
    uint256 paidPanels;
    uint256 closes;
    uint256 eth;

    function test_replaySeed1() public {
        _replay("v3-replay-1.json");
    }

    function test_replaySeed2() public {
        _replay("v3-replay-2.json");
    }

    function test_replaySeed3() public {
        _replay("v3-replay-3.json");
    }

    function test_replaySeed4() public {
        _replay("v3-replay-4.json");
    }

    // ---------- the replay ----------

    function _replay(string memory file) internal {
        vm.pauseGasMetering();
        json = vm.readFile(string.concat("test/data/", file));
        _load();
        _deploy();
        for (uint256 e; e < kinds.length; ++e) {
            uint256 kind = kinds[e];
            if (kind == COMMIT) _commit(sids[e]);
            else if (kind == WAIT) _signalAs(sids[e], Status.Waiting, Kind.Counted, new address[](0), false);
            else if (kind == STALL) _signalAs(sids[e], Status.Judging, Kind.Counted, new address[](0), true);
            else if (kind == COUNTED || kind == AUDIT || kind == CHALLENGE) _pay(e, kind);
            else if (kind == DRAWN) _drawn(e);
            else _close(e);
        }
        assertGt(paidPanels, 0);
        assertGt(closes, 0);
        assertEq(
            usd.balanceOf(address(rc)),
            rc.totalHeld(address(usd)) + rc.totalOwed(address(usd)) + rc.totalDeposits(address(usd)),
            "the race's books"
        );
    }

    function _load() internal {
        items = vm.parseJsonUintArray(json, ".items");
        kinds = vm.parseJsonUintArray(json, ".events.kind");
        sids = vm.parseJsonUintArray(json, ".events.sid");
        starts = vm.parseJsonUintArray(json, ".events.start");
        lens = vm.parseJsonUintArray(json, ".events.len");
        string[] memory names = vm.parseJsonStringArray(json, ".families");
        for (uint256 f; f < names.length; ++f) {
            fams.push(keccak256(bytes(names[f])));
        }
        uint256[] memory u = vm.parseJsonUintArray(json, ".usage");
        for (uint256 i; i < 6; ++i) {
            usage[i] = u[i];
        }
        nUnits = vm.parseJsonStringArray(json, ".units").length;
        eth = vm.parseJsonUint(json, ".eth");
        assertEq(nUnits, 3 * fams.length + 3, "the units: every family's tokens, then vCPU-s, GB-s and storage MB");
    }

    /// The version with the simulation's genesis table, the replay's registry and Panels, and every submission's
    /// bounty opened in the first period.
    function _deploy() internal {
        usd = new MockCoin("Test USD", "tUSD", 6);
        address[] memory coins = new address[](1);
        coins[0] = address(usd);
        pool = new PoolV3(coins);
        reg = new ReplayRegistry();
        uint256[] memory first = vm.parseJsonUintArray(json, ".first");
        FeesV3.Genesis memory g;
        g.coin = address(usd);
        uint256 t = 3 * fams.length;
        g.shared = [first[t], first[t + 1], first[t + 2], vm.parseJsonUint(json, ".eth")];
        g.families = fams;
        g.tokens = new uint256[3][](fams.length);
        for (uint256 f; f < fams.length; ++f) {
            g.tokens[f] = [first[3 * f], first[3 * f + 1], first[3 * f + 2]];
        }
        g.caps = IFeesV3.Caps(140_000, 16_000, 20, 1_000_000, 50_000, 1 gwei);
        g.defaultProfile = IFeesV3.Profile(keccak256("image"), 2_000, 4_096, 1_200);
        fees = new FeesV3(IFeesV3Validators(address(reg)), new MockScores(), g);
        assertEq(fees.serviceFee(), vm.parseJsonUint(json, ".fee"));
        pn = new ReplayPanels(address(fees), address(usd), address(pool), address(reg));
        RaceV3Base.Config memory c;
        c.infrastructure = makeAddr("infra");
        c.insurance = makeAddr("insurance");
        c.registrationFee = 2e6;
        c.issueStake = 5e6;
        c.attemptFee = 0.5e6;
        c.evaluationFee = 2e6;
        c.appealFee = 2e6;
        c.challengeStake = 10e6;
        c.startPriceBps = 5_000;
        c.riseBpsPerDay = 1_000;
        c.finderFeeBps = 1_765;
        c.idleDays = 28;
        c.resultDays = 7;
        c.mergeDays = 14;
        c.releaseEveryDays = 7;
        c.instalments = 4;
        Panels p = Panels(address(pn));
        RaceV3Annex ax = new RaceV3Annex(c, 625, 1e12, p, pool, block.timestamp);
        rc = new RaceV3(c, 625, 1e12, p, pool, block.timestamp, new bytes32[](0), new bytes32[](0), "c", ax);
        uint256[] memory vids = vm.parseJsonUintArray(json, ".vids");
        uint256[] memory vf = vm.parseJsonUintArray(json, ".vidFamily");
        for (uint256 i; i < vids.length; ++i) {
            uint256 sk = uint256(keccak256(abi.encode("pof v3 replay validator", vids[i]))) % SECP_N;
            address a = vm.addr(sk);
            keyOf[vids[i]] = a;
            secretOf[a] = sk;
            reg.setFamily(a, fams[vf[i]]);
        }
        usd.mint(address(this), 1e15);
        usd.approve(address(pool), type(uint256).max);
        pool.fund(address(usd), 1e12);
        _fund(solver);
        _fund(reporter);
        uint256 n = vm.parseJsonUint(json, ".subs");
        for (uint256 i; i <= n; ++i) {
            vm.prank(reporter);
            uint256 issueId = rc.register(bytes32(0), false);
            uint256 check = rc.issue(issueId).check;
            pn.setStatus(check, Status.Final, true, 0);
            if (i == n) {
                helper = check; // one more, never opened: its panel carries the seated validators
                break;
            }
            uint256 b = rc.openBounty(issueId);
            vm.prank(reporter);
            rc.pledge(b, C);
            bounties.push(b);
        }
    }

    function _fund(address who) internal {
        usd.mint(who, 1e15);
        vm.prank(who);
        usd.approve(address(rc), type(uint256).max);
    }

    function _commit(uint256 sid) internal {
        uint256 b = bounties[nextBounty++];
        vm.prank(solver);
        uint256 id = rc.commit(b, keccak256(abi.encode("sim submission", sid)));
        idOf[sid] = id;
        assertEq(fees.epochOf(id), period, "a submission is charged its period's quote");
    }

    /// Scripts submission `sid`'s status (and a panel of `keys`, or a stalled one) and lets the race signal FeesV3.
    function _signalAs(uint256 sid, Status st, Kind kind, address[] memory keys, bool stalled) internal {
        uint256 id = idOf[sid];
        uint256 pid = st == Status.Waiting ? 0 : pn.newPanel(id, kind, keys, stalled);
        pn.setStatus(id, st, false, pid);
        rc.signal(id);
    }

    /// A paid panel: every judge reports the simulation's usage; the counted panel's result, or an audit's or an
    /// auditor's challenge panel's pay; each judge gets exactly what the simulation paid it.
    function _pay(uint256 e, uint256 kind) internal {
        uint256 id = idOf[sids[e]];
        uint256 n = lens[e] / 2;
        address[] memory keys = new address[](n);
        uint256[] memory before = new uint256[](n);
        uint256 total;
        for (uint256 i; i < n; ++i) {
            keys[i] = keyOf[items[starts[e] + 2 * i]];
            before[i] = _has(keys[i]);
            total += items[starts[e] + 2 * i + 1];
        }
        Kind k = kind == COUNTED ? Kind.Counted : kind == AUDIT ? Kind.Audit : Kind.Challenge;
        uint256 pid = pn.newPanel(id, k, keys, false);
        for (uint256 i; i < n; ++i) {
            _report(pid, keys[i]);
        }
        uint256 charged = rc.submission(id).charged;
        if (kind == COUNTED) {
            pn.setStatus(id, Status.Window, false, pid);
            rc.result(id);
            assertEq(rc.submission(id).charged - charged, total, _at(e, "the counted charge"));
        } else {
            rc.payPanel(pid);
        }
        for (uint256 i; i < n; ++i) {
            assertEq(_has(keys[i]) - before[i], items[starts[e] + 2 * i + 1], _at(e, "a judge's pay"));
        }
        ++paidPanels;
    }

    /// What a validator holds: its credit in the race and its wallet (the pool pays what a deposit doesn't cover).
    function _has(address key) internal view returns (uint256) {
        return rc.owed(key, address(usd)) + usd.balanceOf(key);
    }

    function _report(uint256 pid, address key) internal {
        IFeesV3.Usage memory u = IFeesV3.Usage(
            keccak256(abi.encode("receipt", pid, key)),
            uint64(usage[0]),
            uint64(usage[1]),
            uint64(usage[2]),
            uint64(usage[3]),
            uint64(usage[4]),
            uint64(usage[5])
        );
        bytes32 subject = keccak256(abi.encode(USAGE_TAG, address(rc), pid, key));
        bytes32 digest = keccak256(abi.encode(subject, keccak256(abi.encode(u))));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(secretOf[key], digest);
        rc.report(pid, key, u, abi.encodePacked(r, s, v));
    }

    /// The period's seated validators (the simulation's active ones it drew), through a scripted panel.
    function _drawn(uint256 e) internal {
        address[] memory keys = new address[](lens[e]);
        for (uint256 i; i < keys.length; ++i) {
            keys[i] = keyOf[items[starts[e] + i]];
        }
        uint256 pid = pn.newPanel(helper, Kind.Counted, keys, false);
        pn.setStatus(helper, Status.Final, true, pid);
        rc.signal(helper);
        assertEq(fees.period(fees.currentPeriod()).drawn, keys.length, _at(e, "the period's drawn validators"));
    }

    /// The period's close: its active validators, each posting its table, then the roll; the fee and every unit price
    /// are the simulation's.
    function _close(uint256 e) internal {
        uint256 at = starts[e];
        uint256 fee = items[at];
        uint256 pricesAt = at + 1;
        uint256 n = items[at + 1 + nUnits];
        uint256 q = at + 2 + nUnits;
        address[] memory active = new address[](n);
        for (uint256 i; i < n; ++i) {
            active[i] = keyOf[items[q + i * (nUnits + 1)]];
        }
        vm.warp(fees.start() + (period + 1) * 1 days);
        reg.setActive(active);
        uint256 nf = fams.length;
        for (uint256 i; i < n; ++i) {
            uint256 row = q + i * (nUnits + 1) + 1;
            uint256[3][] memory toks = new uint256[3][](nf);
            for (uint256 f; f < nf; ++f) {
                toks[f] = [items[row + 3 * f], items[row + 3 * f + 1], items[row + 3 * f + 2]];
            }
            uint256 t = row + 3 * nf;
            vm.prank(active[i]);
            fees.post([items[t], items[t + 1], items[t + 2], eth], fams, toks);
        }
        fees.roll();
        ++period;
        ++closes;
        assertEq(fees.rolled(), period, _at(e, "one period closed"));
        assertEq(fees.serviceFee(), fee, _at(e, "the service fee"));
        uint256[4] memory sh = fees.sharedPrices();
        for (uint256 j; j < 3; ++j) {
            assertEq(sh[j], items[pricesAt + 3 * nf + j], _at(e, "a shared unit's price"));
        }
        for (uint256 f; f < nf; ++f) {
            uint256[3] memory tp = fees.tokenPrices(fams[f]);
            for (uint256 j; j < 3; ++j) {
                assertEq(tp[j], items[pricesAt + 3 * f + j], _at(e, "a token unit's price"));
            }
        }
    }

    function _at(uint256 e, string memory what) internal view returns (string memory) {
        return string.concat(what, " at event ", vm.toString(e), ", period ", vm.toString(period));
    }
}
