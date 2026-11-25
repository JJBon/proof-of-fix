// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {console} from "forge-std/Test.sol";
import {Vm} from "forge-std/Vm.sol";
import {IValidators} from "../../src/v3/IValidators.sol";
import {Panels} from "../../src/v3/Panels.sol";
import {Status, Kind, Submission, Panel} from "../../src/v3/PanelsBase.sol";
import {FeesV3} from "../../src/v3/FeesV3.sol";
import {RaceV3Base} from "../../src/v3/RaceV3Base.sol";
import {RaceV3Setup} from "./helpers/RaceV3Setup.sol";
import {DrawabilitySetup} from "./helpers/DrawabilitySetup.sol";
import {TEST_REPO} from "./helpers/SuiteWindows.sol";

// The family the regressions price after their checks opened (F1).
bytes32 constant FRESH = keccak256("fresh/model");

/// proof-of-fix#251, the v3.1 polish (openspec/changes/proof-of-fix-251-v31-polish, VP1, task 1.1): a family priced
/// after a check's epoch is never seated on its paid panels, since FeesV3 charges the check at that epoch and every pay
/// path (`result`, `payPanel`, `settleChallenge`) reverted `Unpriced(family)` for it, for good (the audit's F1).
/// `PanelsDraw.fill` compares `pricedFrom(family)` with `min(drawEpoch(id), snapshot's rolled)`.
///
/// Each regression opens its checks in epoch 0, then a roll gives the fresh family its first price (epoch 1), then a
/// snapshot taken after that roll draws: a re-targeted counted draw, a `refill`, the audits, a challenge. On the code
/// before the fix each seats the fresh family's validator and its pay reverts `Unpriced(FRESH)`.
contract PolishV31F1Test is RaceV3Setup {
    address[] internal posters;
    address internal freshKey;

    function setUp() public {
        _deployRace(0);
    }

    /// `n` validators besides the genesis one (families 1..n), every one a poster, and the fresh family's validator,
    /// announced. The posters' tables price every family and the fresh one: three counting tables of other families.
    function _scenario(uint256 n) internal {
        address[] memory ks = _network(n, FAMILIES, 3);
        posters.push(genesisKey);
        for (uint256 i; i < ks.length; ++i) {
            posters.push(ks[i]);
        }
        freshKey = _add(keccak256("host-fresh"), FRESH, _tee(1), 1, FULL_BOND);
        fees.announce(freshKey);
        _postAll();
    }

    function _postAll() internal {
        uint256 nf = FAMILIES + 1;
        bytes32[] memory fs = new bytes32[](nf);
        uint256[3][] memory ts = new uint256[3][](nf);
        for (uint256 i; i < FAMILIES; ++i) {
            fs[i] = _family(i);
            ts[i] = [uint256(4_000_000), 200_000, 20_000_000];
        }
        fs[FAMILIES] = FRESH;
        ts[FAMILIES] = [uint256(4_000_000), 200_000, 20_000_000];
        uint256[4] memory sh = [uint256(11_244_444), 1_234_722, 269_531_250, 2_700_000_000];
        for (uint256 i; i < posters.length; ++i) {
            vm.prank(posters[i]);
            fees.post(sh, fs, ts);
        }
    }

    /// Closes period 0 (one part a call, F2): the fresh family's first price, in force from epoch 1.
    function _priceFresh() internal {
        uint256 end = fees.start() + 1 days;
        if (vm.getBlockTimestamp() < end) vm.warp(end);
        while (fees.rolled() == 0) {
            fees.roll();
        }
        assertTrue(fees.isPriced(FRESH));
        assertEq(fees.pricedFrom(FRESH), 1);
        assertEq(fees.drawEpoch(0), 1, "an unopened check draws at the epoch in force");
    }

    /// Seals, reveals and receipts every seat of `pid` that hasn't sealed yet, then reveals the rest (a refilled panel).
    function _finishPanel(uint256 pid) internal {
        uint256 k = pn.panel(pid).k;
        for (uint256 i; i < k; ++i) {
            if (!pn.seat(pid, i).hasSeal) _seal(pid, pn.seat(pid, i).key, true);
        }
        vm.warp(pn.panel(pid).sealBy + 1);
        for (uint256 i; i < k; ++i) {
            _reveal(pid, pn.seat(pid, i).key);
            _receipt(pid, pn.seat(pid, i).key);
        }
    }

    // ---------- the paths ----------

    /// The audit's scenario: 12 registrations opened in epoch 0, the fresh family priced at epoch 1, the seed blocks
    /// aged out so every draw re-targets with a snapshot after that roll. Before the fix all 12 counted panels seated
    /// the fresh validator (k = 5 of the 5 eligible) and every `result` reverted. Now none does, and every result
    /// posts. A check opened after the first price seats it, and its result posts.
    function test_aRetargetedCountedDrawSeatsOnlyFamiliesPricedAtItsEpoch() public {
        _scenario(3);
        uint256 n = 12;
        uint256[] memory ids = new uint256[](n);
        for (uint256 j; j < n; ++j) {
            ids[j] = rc.issue(_register()).check;
        }
        assertEq(fees.epochOf(ids[0]), 0);
        assertEq(fees.drawEpoch(ids[0]), 0);
        _priceFresh();
        vm.roll(vm.getBlockNumber() + 300); // the seed blocks are gone: each draw re-targets, snapshot at epoch 1
        uint256 hits;
        for (uint256 j; j < n; ++j) {
            pn.draw(ids[j]); // re-target
            uint256 pid = _draw(ids[j]);
            assertTrue(pid != 0, "drawn from the families priced at epoch 0");
            if (_contains(pn.judges(pid), freshKey)) ++hits;
            uint256 k = pn.panel(pid).k;
            _judge(pid, _votes(k, k));
            _reportAll(pid);
            vm.prank(relayer);
            rc.result(ids[j]); // reverted Unpriced(FRESH) before the fix
            assertTrue(rc.submission(ids[j]).paid);
            _nextCapWindow();
        }
        assertEq(hits, 0, "a family priced after the check's epoch was seated");

        // a check opened in epoch 1 draws the fresh family (5 eligible, k = 5) and pays it
        uint256 id = rc.issue(_register()).check;
        assertEq(fees.drawEpoch(id), 1);
        uint256 pid2 = _draw(id);
        assertTrue(_contains(pn.judges(pid2), freshKey), "priced at the check's epoch: seated");
        uint256 k2 = pn.panel(pid2).k;
        _judge(pid2, _votes(k2, k2));
        _reportAll(pid2);
        vm.prank(relayer);
        rc.result(id);
        assertTrue(rc.submission(id).paid);
    }

    /// `refill` takes a new snapshot: after the roll it used to seat the fresh validator, the only one outside the
    /// panel, in a seat its judge missed, and `result` reverted. Now it refuses (`NotReady`) until a validator of a
    /// family priced at the check's epoch joins.
    function test_refillSeatsOnlyFamiliesPricedAtTheChecksEpoch() public {
        _scenario(2); // genesis + 2: the panel of 3 is every priced validator; the fresh one is outside it
        uint256 id = rc.issue(_register()).check;
        uint256 pid = _draw(id);
        assertEq(pn.panel(pid).k, 3);
        assertFalse(_contains(pn.judges(pid), freshKey));
        address[] memory js = pn.judges(pid);
        _seal(pid, js[0], true);
        _seal(pid, js[1], true); // the third misses its seal
        _priceFresh();
        vm.warp(vm.getBlockTimestamp() + 1);
        pn.advance(pid); // the miss vacated; the panel's own snapshot (epoch 0) finds nobody: stalled
        assertEq(pn.panel(pid).seats, 2);
        (bool ok,) = address(pn).call(abi.encodeCall(pn.refill, (pid)));
        if (!ok) {
            _addSpread(10, FAMILIES, 3); // a validator of a family priced at epoch 0 joins
            pn.refill(pid);
        }
        assertEq(pn.panel(pid).seats, 3);
        _finishPanel(pid);
        _reportAll(pid);
        vm.prank(relayer);
        rc.result(id); // reverted Unpriced(FRESH) before the fix
        assertTrue(rc.submission(id).paid);
        assertFalse(ok, "the fresh family's validator was the only one a new snapshot could seat");
        assertFalse(_contains(pn.judges(pid), freshKey));
    }

    /// A lone verdict counted after the roll: its audit snapshot (taken at the count) used to seat the fresh validator,
    /// the only one with room outside its panel, and `payPanel` reverted. Now its audits wait for validators of a
    /// family priced at the check's epoch, and each audit panel is paid.
    function test_auditsSeatOnlyFamiliesPricedAtTheChecksEpoch() public {
        _scenario(2);
        for (uint256 i = 1; i < posters.length; ++i) {
            vm.prank(posters[i]);
            pn.setCapacity(posters[i], 0); // paused: the genesis validator judges alone, and the fresh one is outside
        }
        vm.roll(vm.getBlockNumber() + pn.CAP_DELAY() + 1);
        uint256 id = rc.issue(_register()).check;
        _priceFresh();
        uint256 pid = _draw(id); // the snapshot at the opening (epoch 0): genesis alone, k = 1
        assertEq(pn.panel(pid).k, 1);
        _judge(pid, _votes(1, 1));
        _reportAll(pid);
        vm.prank(relayer);
        rc.result(id);
        Submission memory s = pn.submission(id);
        _rollPast(s.auditBlock);
        pn.drawAudits(id); // before the fix: the fresh validator as an auditor
        for (uint256 q = pid + 1; q <= pn.panelCount(); ++q) {
            if (pn.panel(q).kind != Kind.Audit) continue;
            address a = pn.judges(q)[0];
            _seal(q, a, true);
            vm.warp(pn.panel(q).sealBy + 1);
            _reveal(q, a);
            _receipt(q, a);
        }
        for (uint256 i; i < 3; ++i) {
            _addSpread(20 + i, FAMILIES, 3); // three of priced families join (the registry moves)
        }
        _runAudits(id, true);
        s = pn.submission(id);
        assertEq(s.auditsDrawn, s.auditsDue, "drawn from the families priced at epoch 0");
        uint256 audits;
        for (uint256 q = pid + 1; q <= pn.panelCount(); ++q) {
            Panel memory p = pn.panel(q);
            if (p.kind != Kind.Audit || p.id != id) continue;
            _reportAll(q);
            rc.payPanel(q); // reverted Unpriced(FRESH) before the fix
            assertFalse(_contains(pn.judges(q), freshKey), "a family priced after the check's epoch audits it");
            ++audits;
        }
        assertEq(audits, s.auditsDue);
    }

    /// A challenge filed after the roll snapshots then: its panel of 5 used to take the four validators outside the
    /// verdict's panel and the fresh one, and `settleChallenge` reverted. Now it waits for a fifth of a family priced
    /// at the check's epoch, and settles.
    function test_aChallengeSeatsOnlyFamiliesPricedAtTheChecksEpoch() public {
        _scenario(2);
        uint256 id = rc.issue(_register()).check;
        _priceFresh();
        uint256 pid = _draw(id); // the opening's snapshot: the three priced validators, k = 3
        assertEq(pn.panel(pid).k, 3);
        _judge(pid, _votes(3, 3));
        _reportAll(pid);
        vm.prank(relayer);
        rc.result(id);
        for (uint256 i; i < 4; ++i) {
            _addSpread(30 + i, FAMILIES, 3); // four outside the panel, families 2..5
        }
        _fund(bob, 100 * C);
        vm.prank(bob);
        rc.challenge(id, keccak256("evidence"));
        _rollPast(pn.submission(id).challengeBlock);
        pn.drawChallenge(id); // before the fix: the four and the fresh validator
        uint256 cpid = pn.submission(id).challengePid;
        if (cpid == 0) {
            _addSpread(34, FAMILIES, 3); // a fifth of a priced family: the registry moves, the challenge redraws
            pn.drawChallenge(id); // re-targets
            _rollPast(pn.submission(id).challengeBlock);
            pn.drawChallenge(id);
            cpid = pn.submission(id).challengePid;
        }
        assertTrue(cpid != 0, "drawn");
        uint256 kc = pn.panel(cpid).k;
        _judge(cpid, _votes(kc, kc));
        _reportAll(cpid);
        rc.settleChallenge(id, cpid); // reverted Unpriced(FRESH) before the fix
        assertEq(rc.challengeOf(id).challenger, address(0));
        assertFalse(_contains(pn.judges(cpid), freshKey), "a family priced after the check's epoch judged it");
    }

    /// A shadow of the fresh family is still drawn for a check opened before its first price (shadows need only a
    /// priced family: F12, by design) and its pay is nothing: `shadowCost` at the check's epoch refuses it, and the
    /// seat closes unpaid.
    function test_aFreshFamilyShadowIsDrawnAndPaidNothing() public {
        address[] memory ks = _network(2, FAMILIES, 3);
        posters.push(genesisKey);
        posters.push(ks[0]);
        posters.push(ks[1]);
        address cand = _addCandidate(keccak256("cand host fresh"), FRESH, _tee(1), 1, 200e6);
        fees.announce(cand);
        _postAll();
        _fund(address(this), 50 * C);
        usd.approve(address(pool3), 50 * C);
        pool3.fund(address(usd), 50 * C);
        uint256 id = rc.issue(_register()).check;
        _priceFresh();
        _draw(id);
        uint256 spid = pn.submission(id).shadowPid;
        assertTrue(spid != 0, "a shadow panel");
        address[] memory sh = pn.judges(spid);
        assertEq(sh.length, 1);
        assertEq(sh[0], cand, "the fresh family's candidate shadows");
        _seal(spid, cand, true);
        vm.warp(pn.panel(spid).sealBy + 1);
        _reveal(spid, cand);
        _receipt(spid, cand);
        _reportSeat(spid, cand);
        vm.expectRevert(abi.encodeWithSelector(FeesV3.Unpriced.selector, FRESH));
        fees.shadowCost(id, TEST_REPO, FRESH, _usage(spid, cand));
        address op = reg.validator(cand).operator;
        uint256 pooled = pool3.held(address(usd));
        rc.payShadow(spid, 0);
        assertEq(usd.balanceOf(op), 0, "paid nothing");
        assertEq(pool3.held(address(usd)), pooled);
        vm.expectRevert(RaceV3Base.Refused.selector); // the seat is closed
        rc.payShadow(spid, 0);
    }

    // ---------- payShadow's paying branch (for the keeper's PAY_SHADOW_GAS_FLOOR, task 2.2) ----------

    /// The gas `payShadow`'s paying branch takes (#323's scenario: two candidates shadow a bounty's fix, one reveals and
    /// reports): what it uses, the least limit that pays, and the storage slots it creates (the seat's paid mark in
    /// RaceV3, and the operator's coin balance on its first payment; EIP-8037 charges 97,920 each). Measured for the
    /// keeper's PAY_SHADOW_GAS_FLOOR (600,000, task 2.2), which is meant to be at least twice the branch: it is under
    /// forge's pre-8037 gas (≈222k), not with 8037's state gas for two new slots (≈418k; ≈320k for an operator already
    /// holding the coin). Pinned here: the pre-8037 bound, and the numbers logged.
    function test_payShadowsPayingBranchGas() public {
        _network(3, FAMILIES, 3); // RaceV3.t.sol's: every panel is k = 3
        _addCandidate(keccak256("cand host 1"), _family(1), _tee(0), 1, 200e6);
        _addCandidate(keccak256("cand host 2"), _family(2), _tee(1), 1, 200e6);
        uint256 b = _openBounty();
        _fund(address(this), 50 * C);
        usd.approve(address(pool3), 50 * C);
        pool3.fund(address(usd), 50 * C);
        uint256 id = _commit(solver1, b, keccak256("a fix"));
        _draw(id);
        uint256 spid = pn.submission(id).shadowPid;
        address[] memory sh = pn.judges(spid);
        for (uint256 i; i < 2; ++i) {
            _seal(spid, sh[i], true);
        }
        vm.warp(pn.panel(spid).sealBy + 1);
        _reveal(spid, sh[0]);
        _receipt(spid, sh[0]);
        _reportSeat(spid, sh[0]);
        address op = reg.validator(sh[0]).operator;
        uint256 least;
        for (uint256 gas = 20_000; gas <= 600_000; gas += 1_000) {
            uint256 s0 = vm.snapshotState();
            (bool ok,) = address(rc).call{gas: gas}(abi.encodeCall(rc.payShadow, (spid, 0)));
            bool paid = usd.balanceOf(op) > 0;
            vm.revertToState(s0);
            if (ok && paid) {
                least = gas;
                break;
            }
        }
        vm.startStateDiffRecording();
        uint256 g = gasleft();
        rc.payShadow(spid, 0);
        uint256 used = g - gasleft();
        Vm.AccountAccess[] memory acc = vm.stopAndReturnStateDiff();
        assertGt(usd.balanceOf(op), 0, "paid");
        uint256 created = _created(acc);
        uint256 under8037 = least + 97_920 * created;
        console.log("payShadow, paying: gas used, least limit that pays:", used, least);
        console.log("  new slots, least limit with 8037's state gas:", created, under8037);
        assertGt(least, 0);
        assertLe(2 * least, 600_000, "PAY_SHADOW_GAS_FLOOR below twice the paying branch (pre-8037)");
        assertLe(created, 2);
    }

    /// Storage slots zero before and nonzero after, over every account written.
    function _created(Vm.AccountAccess[] memory acc) internal view returns (uint256 n) {
        uint256 total;
        for (uint256 i; i < acc.length; ++i) {
            total += acc[i].storageAccesses.length;
        }
        address[] memory who = new address[](total);
        bytes32[] memory slots = new bytes32[](total);
        bytes32[] memory before = new bytes32[](total);
        bytes32[] memory last = new bytes32[](total);
        uint256 k;
        for (uint256 i; i < acc.length; ++i) {
            Vm.StorageAccess[] memory sa = acc[i].storageAccesses;
            for (uint256 j; j < sa.length; ++j) {
                if (!sa[j].isWrite || sa[j].reverted) continue;
                uint256 at = k;
                for (uint256 q; q < k; ++q) {
                    if (slots[q] == sa[j].slot && who[q] == sa[j].account) at = q;
                }
                if (at == k) {
                    (who[k], slots[k], before[k]) = (sa[j].account, sa[j].slot, sa[j].previousValue);
                    ++k;
                }
                last[at] = sa[j].newValue;
            }
        }
        for (uint256 q; q < k; ++q) {
            if (before[q] == 0 && last[q] != 0) {
                ++n;
                console.log("  a new slot of", who[q]);
            }
        }
    }
}

/// proof-of-fix#251, the v3.1 polish: the k = 1 hold's price test (VP1, task 1.2), its threshold (VP14, F7, task 1.7),
/// `topUp`'s epoch (VP4, F8, task 1.5) and an announcement skipped by a starved refill (VP5, F9, task 1.6), on the real
/// Panels under the launch's rules (every cap `Off`, `kTop` 3, `Same`).
contract PolishV31PanelsTest is DrawabilitySetup {
    bytes32 internal constant NEVER = keccak256("never/priced");

    /// A validator of `family`, on a host and operator of its own, bonded $250 and active.
    function _addOf(uint256 i, bytes32 family) internal returns (address key) {
        key = _nextKey();
        IValidators.Registration memory r =
            _reg(key, makeAddr(string.concat("op-", vm.toString(key))), keccak256(abi.encode("host", i, key)), family);
        r.teeType = _tee(i % 3);
        r.level = 1;
        _register(r, BOND, key);
        _qualifyV(key);
    }

    function _topUp(address key, uint256 amount) internal {
        usd.mint(address(this), amount);
        usd.approve(address(reg), amount);
        reg.topUp(key, amount);
    }

    // ---------- the hold's price test (task 1.2) ----------

    /// A lone verdict of a check opened in epoch 0, counted after a roll priced a fresh family: six validators of that
    /// family and one of a family never priced are outside its panel, with room. None of them could sit on its
    /// challenge (the draw seats only families priced at the check's epoch), so it stays held (before the fix the
    /// hold counted all seven and started the window). Six of priced families end the hold.
    function test_theHoldCountsOnlyChallengersPricedAtTheChecksEpoch() public {
        _deployRules(_launch(), _spread());
        address[] memory ps = new address[](3);
        for (uint256 i; i < 3; ++i) {
            ps[i] = _addOf(1 + i, _family(1 + i)); // the posters, paused: no room, so outside the count
        }
        for (uint256 i; i < 3; ++i) {
            vm.prank(ps[i]);
            pn.setCapacity(ps[i], 0);
        }
        address[] memory fresh = new address[](6);
        for (uint256 i; i < 6; ++i) {
            fresh[i] = _addOf(10 + i, FRESH);
        }
        _addOf(20, NEVER);
        vm.roll(vm.getBlockNumber() + pn.CAP_DELAY() + 1);
        fees.announce(fresh[0]);
        bytes32[] memory fs = new bytes32[](FAMILIES + 1); // a table counts with every priced family (D19)
        uint256[3][] memory ts = new uint256[3][](FAMILIES + 1);
        for (uint256 i; i <= FAMILIES; ++i) {
            fs[i] = i == FAMILIES ? FRESH : _family(i);
            ts[i] = [uint256(4_000_000), 200_000, 20_000_000];
        }
        uint256[4] memory sh = [uint256(11_244_444), 1_234_722, 269_531_250, 2_700_000_000];
        for (uint256 i; i < 3; ++i) {
            vm.prank(ps[i]);
            fees.post(sh, fs, ts);
        }
        uint256 id = _id();
        fees.bind(); // this test stands for the race: the check opens in FeesV3 at epoch 0, as RaceV3's commit does
        fees.open(id);
        _open(id, 40e6);
        assertEq(fees.drawEpoch(id), 0);
        vm.warp(fees.start() + 1 days);
        while (fees.rolled() == 0) {
            fees.roll();
        }
        assertEq(fees.pricedFrom(FRESH), 1);
        uint256 pid = _draw(id); // the opening's snapshot: the genesis validator alone, k = 1
        assertEq(pn.panel(pid).k, 1);
        _judge(pid, _all(1, true));
        assertEq(uint256(pn.submission(id).status), uint256(Status.Held), "later-priced and unpriced don't count");
        vm.expectRevert(Panels.NotReady.selector);
        pn.startWindow(id);
        for (uint256 i; i < 5; ++i) {
            _addOf(30 + i, _family(i));
        }
        vm.expectRevert(Panels.NotReady.selector); // five payable challengers: 3 + 2 audits + the undecided one is six
        pn.startWindow(id);
        _addOf(35, _family(5));
        pn.startWindow(id);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Window));
    }

    // ---------- the hold's threshold (task 1.7, F7) ----------

    /// The k = 1 hold's real count at launch: CHALLENGE_K[1] (3) + the audits still to draw (K1_AUDITS, 2) + the random
    /// audit while undecided (1) = six validators with room outside its panel before its audits are drawn (seven in
    /// all with the judge), and three outside the judge and its auditors after. At exactly six, one validator pausing
    /// holds it; after the audits, at exactly three, one pausing holds it again.
    function test_theHoldsThresholdAtLaunch() public {
        _deployRules(_launch(), _spread());
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 40e6);
        assertEq(pn.panel(pid).k, 1);
        address[] memory keys = _layout(7, 7, _spread()); // six outside its panel: the threshold
        _pause(keys[6], 0);
        _judge(pid, _all(1, true));
        assertEq(uint256(pn.submission(id).status), uint256(Status.Held), "at six, one pause holds it");
        uint256 snap = vm.snapshotState();
        _pause(keys[6], 4);
        pn.startWindow(id); // six with room: 3 + 2 + 1
        assertEq(uint256(pn.submission(id).status), uint256(Status.Window));
        vm.revertToState(snap);

        _runAudits(id, true); // drawn from the five with room while it's held
        Submission memory s = pn.submission(id);
        assertTrue(s.auditDecided);
        assertEq(s.auditsDrawn, s.auditsDue);
        address[] memory ready = new address[](7);
        uint256 n;
        for (uint256 i = 1; i < 6; ++i) {
            if (!_seatedOnAudit(id, keys[i])) ready[n++] = keys[i];
        }
        if (n < 3) {
            _pause(keys[6], 4); // a random third audit took one more: the paused one makes three
            ready[n++] = keys[6];
        }
        assertEq(n, 3, "three with room outside the judge and its auditors");
        _pause(ready[0], 0);
        vm.expectRevert(Panels.NotReady.selector); // at three, one pause holds it
        pn.startWindow(id);
        _pause(ready[0], 4);
        pn.startWindow(id);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Window));
    }

    function _seatedOnAudit(uint256 id, address key) internal view returns (bool) {
        for (uint256 q = 1; q <= pn.panelCount(); ++q) {
            Panel memory p = pn.panel(q);
            if (p.kind == Kind.Audit && p.id == id && _contains(pn.judges(q), key)) return true;
        }
        return false;
    }

    // ---------- topUp's epoch (task 1.5, F8) ----------

    /// A submission that waits (a bounty above every reachable panel's limit) refuses a redraw until the registry
    /// changes. A one-micro-coin top-up changes nothing a draw reads: `epoch` and the refusal stay. A top-up across a
    /// tier moves the key's bucket: `epoch` moves and the redraw runs.
    function test_aTopUpMovesTheEpochOnlyWhenItChangesTheBucket() public {
        _deployRules(_launch(), _spread());
        address key = _addOf(1, _family(1)); // $250: bucket 4
        uint256 id = _id();
        _open(id, 600e6);
        _draw(id);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Waiting));
        vm.expectRevert(Panels.NothingChanged.selector);
        pn.draw(id);
        uint256 e = reg.epoch();
        _topUp(key, 1);
        assertEq(reg.epoch(), e, "one micro-coin: nothing changed");
        vm.expectRevert(Panels.NothingChanged.selector);
        pn.draw(id);
        _topUp(genesisKey, 1);
        assertEq(reg.epoch(), e);
        _topUp(key, 250e6 - 1); // $500: bucket 5
        assertEq(reg.epoch(), e + 1, "across a tier");
        pn.draw(id); // re-targets: the registry changed
    }

    /// A validator slashed below the floor and topped back up to it: Active again, its bucket back, `epoch` moves. A
    /// top-up that leaves it below the floor doesn't.
    function test_aTopUpRestoringTheFloorMovesTheEpoch() public {
        _deployRules(_launch(), _spread());
        address key = _addOf(1, _family(1));
        vm.prank(address(pn));
        reg.slashFault(key, IValidators.Fault.FalseVerdict, address(0)); // the whole bond: below the floor
        assertTrue(reg.validator(key).state == IValidators.State.BelowFloor);
        uint256 e = reg.epoch();
        _topUp(key, 50e6);
        assertTrue(reg.validator(key).state == IValidators.State.BelowFloor);
        assertEq(reg.epoch(), e, "still below the floor: nothing changed");
        _topUp(key, 50e6);
        assertTrue(reg.validator(key).state == IValidators.State.Active);
        assertTrue(reg.isDrawable(key));
        assertEq(reg.epoch(), e + 1, "back at the floor");
    }

    /// A candidate's bond feeds nothing a draw reads (`canShadow` reads its state, cooldown and standing, not its
    /// bond), so a candidate's top-up, small or large, never moves `epoch`.
    function test_aCandidatesTopUpDoesntMoveTheEpoch() public {
        _deployRules(_launch(), _spread());
        address cand = _addCandidate(keccak256("cand host"), _family(1), _tee(1), 1, 100e6);
        assertTrue(reg.canShadow(cand));
        uint256 e = reg.epoch();
        _topUp(cand, 1);
        _topUp(cand, 1_000e6);
        assertEq(reg.epoch(), e);
        assertTrue(reg.canShadow(cand));
    }

    // ---------- a starved announcement (task 1.6, F9: no code change) ----------

    /// `advance`'s refill (a stalled one: only `emit Stalled` follows the announcement) meets a validator of an
    /// unannounced family and announces it (`try fees.announce(key) {} catch {}`). Whatever gas the call gets, it
    /// either reverts or does the refill in full: the only thing a short limit can skip is the announcement (success is
    /// monotonic in the limit, so it isn't #325's shape), and the next draw that meets the validator announces it.
    function test_aStarvedAnnouncementIsSkippedAndRedoneByTheNextDraw() public {
        _deployRules(_launch(), _spread());
        _layout(3, 3, _spread()); // genesis + 2: the panel of 3 is every priced validator
        address never = _addOf(9, NEVER);
        vm.warp(fees.start() + 1 days);
        fees.rollPart(); // a roll under way: the draw's announcement is refused (RollInProgress) and caught
        uint256 id = _id();
        uint256 pid = _openAndDraw(id, 40e6);
        assertEq(pn.panel(pid).k, 3);
        assertFalse(_pending(NEVER), "the draw's announcement waited for the roll");
        while (fees.rolled() == 0) {
            fees.roll();
        }
        address[] memory js = pn.judges(pid);
        _seal(pid, js[0], true);
        _seal(pid, js[1], true);
        vm.warp(pn.panel(pid).sealBy + 1);

        uint256 full;
        {
            uint256 s0 = vm.snapshotState();
            uint256 g = gasleft();
            pn.advance(pid);
            full = g - gasleft();
            assertTrue(_pending(NEVER), "with the gas it needs, the refill announces");
            vm.revertToState(s0);
        }
        uint256 lowest;
        uint256 skipped;
        for (uint256 gas = full / 2; gas <= full + 100_000; gas += 500) {
            uint256 s1 = vm.snapshotState();
            (bool ok,) = address(pn).call{gas: gas}(abi.encodeCall(pn.advance, (pid)));
            if (ok) {
                if (lowest == 0) lowest = gas;
                assertEq(pn.panel(pid).seats, 2, "the refill's work done: the miss vacated, the panel stalled");
                if (!_pending(NEVER)) ++skipped;
            } else {
                assertEq(lowest, 0, "success is monotonic in the limit");
            }
            vm.revertToState(s1);
        }
        console.log("advance (refill, announcing):", full);
        console.log("the lowest limit that succeeds:", lowest);
        console.log("limits that skipped the announcement:", skipped);
        assertGt(lowest, 0);

        // the starved branch (reached under EIP-8037, where a first announcement's new slots cost ≈250-330k and the
        // 1/64 left covers the rest; forge's pre-8037 gas leaves too little, so above no limit skips it): the
        // announcement fails, the refill completes, and the family waits
        vm.mockCallRevert(address(fees), abi.encodeWithSelector(FeesV3.announce.selector), "");
        pn.advance(pid);
        vm.clearMockedCalls();
        assertEq(pn.panel(pid).seats, 2, "the refill's work done");
        assertFalse(_pending(NEVER), "the announcement skipped");
        // the next draw meeting it announces it
        _pause(js[0], 0);
        _pause(js[1], 0);
        uint256 id2 = _id();
        _openAndDraw(id2, 40e6);
        assertTrue(_pending(NEVER), "the next draw that meets it announces it");
    }

    function _pending(bytes32 family) internal view returns (bool) {
        bytes32[] memory ps = fees.pendingFamilies();
        for (uint256 i; i < ps.length; ++i) {
            if (ps[i] == family) return true;
        }
        return false;
    }
}
