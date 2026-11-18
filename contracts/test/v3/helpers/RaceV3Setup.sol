// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Validators} from "../../../src/v3/Validators.sol";
import {IValidators} from "../../../src/v3/IValidators.sol";
import {FeesV3} from "../../../src/v3/FeesV3.sol";
import {IFeesV3, IFeesV3Validators} from "../../../src/v3/IFeesV3.sol";
import {Panels} from "../../../src/v3/Panels.sol";
import {Status, Kind, Submission, Panel} from "../../../src/v3/PanelsBase.sol";
import {IPanelsRegistry, IPanelsFees, IPanelScores} from "../../../src/v3/IPanels.sol";
import {PanelScores} from "../../../src/v3/PanelScores.sol";
import {PoolV3} from "../../../src/v3/PoolV3.sol";
import {RaceV3} from "../../../src/v3/RaceV3.sol";
import {RaceV3Annex} from "../../../src/v3/RaceV3Annex.sol";
import {RaceV3Base} from "../../../src/v3/RaceV3Base.sol";
import {MockCoin} from "../../mocks/MockCoin.sol";
import {PanelsSetup} from "./PanelsSetup.sol";

/// The whole v3 version for the race's tests (task 3.5): the registry with one genesis validator (level A, TDX,
/// family 0, $1,250), PanelScores, FeesV3 (PanelsSetup's genesis prices), Panels, the sponsors' pool PoolV3, and RaceV3
/// with its annex, bound in the deployment order of reports/contract-v3.md. Helpers run a check through Panels: the
/// draw, the judges' seals, reveals and receipts, their usage reports, the result, audits and finality.
abstract contract RaceV3Setup is PanelsSetup {
    uint256 internal constant C = 1e6; // one coin (6 decimals)
    uint256 internal constant FINDER = 1_765;
    bytes32 internal constant USAGE_TAG = keccak256("proof-of-fix v3 usage");

    RaceV3 internal rc;
    PoolV3 internal pool3;
    address internal infra = makeAddr("infra");
    address internal insurance = makeAddr("insurance");
    address internal reporter = makeAddr("reporter");
    address internal alice = makeAddr("alice");
    address internal bob = makeAddr("bob");
    address internal solver1 = makeAddr("solver1");
    address internal solver2 = makeAddr("solver2");
    address internal relayer = makeAddr("relayer");

    /// v2's race configuration (RaceV2.t.sol), with v3's challenge stake.
    function _config() internal view returns (RaceV3Base.Config memory c) {
        c.infrastructure = infra;
        c.insurance = insurance;
        c.registrationFee = 2e6;
        c.issueStake = 5e6;
        c.attemptFee = 0.5e6;
        c.evaluationFee = 2e6;
        c.appealFee = 2e6;
        c.challengeStake = 10e6;
        c.startPriceBps = 5_000;
        c.riseBpsPerDay = 1_000;
        c.finderFeeBps = FINDER;
        c.idleDays = 28;
        c.resultDays = 7;
        c.mergeDays = 14;
        c.releaseEveryDays = 7;
        c.instalments = 4;
    }

    /// The version, with `n` spread validators besides the genesis one (each its own host, family and full bond).
    function _deployRace(uint256 n) internal {
        _deployRaceWith(n, new bytes32[](0), new bytes32[](0));
    }

    function _deployRaceWith(uint256 n, bytes32[] memory repos, bytes32[] memory commits) internal {
        usd = new MockCoin("Test USD", "tUSD", 6);
        address[] memory coins = new address[](1);
        coins[0] = address(usd);
        pool3 = new PoolV3(coins);
        pool = pool3;
        genesisKey = _newKey("genesis");
        IValidators.Registration[] memory gs = new IValidators.Registration[](1);
        gs[0] = _reg(genesisKey, makeAddr("genesis operator"), keccak256("host-genesis"), _family(0));
        Validators.Genesis memory g = _genesis(false, gs, FULL_BOND);
        reg = _create(g);
        scores = new PanelScores();
        fees = new FeesV3(IFeesV3Validators(address(reg)), scores, _feesGenesis());
        pn = new Panels(
            IPanelsRegistry(address(reg)), IPanelsFees(address(fees)), IPanelScores(address(scores)), g.teeTypes
        );
        RaceV3Annex ax = new RaceV3Annex(_config(), 625, 100_000, pn, pool3, block.timestamp);
        rc = new RaceV3(_config(), 625, 100_000, pn, pool3, block.timestamp, repos, commits, keccak256("c"), ax);
        _network(n, FAMILIES, 3);
    }

    // ---------- money ----------

    function _fund(address who, uint256 amount) internal {
        usd.mint(who, amount);
        vm.prank(who);
        usd.approve(address(rc), type(uint256).max);
    }

    function _owed(address who) internal view returns (uint256) {
        return rc.owed(who, address(usd));
    }

    function _assertBooks() internal view {
        assertEq(
            usd.balanceOf(address(rc)),
            rc.totalHeld(address(usd)) + rc.totalOwed(address(usd)) + rc.totalDeposits(address(usd)),
            "the race's books"
        );
    }

    function _toDay(uint256 d) internal {
        (,,,,,, uint256 st) = rc.contracts();
        vm.warp(st + d * 1 days);
    }

    // ---------- the race ----------

    function _register() internal returns (uint256 i) {
        _fund(reporter, 100 * C);
        vm.prank(reporter);
        i = rc.register(bytes32(0), false);
    }

    /// A registered issue whose check passes and becomes final: its bounty opens; alice pledges 100.
    function _openBounty() internal returns (uint256 b) {
        uint256 i = _register();
        _check(rc.issue(i).check, true);
        b = rc.openBounty(i);
        _pledge(alice, b, 100 * C);
    }

    function _pledge(address who, uint256 b, uint256 amount) internal {
        _fund(who, amount);
        vm.prank(who);
        rc.pledge(b, amount);
    }

    function _commitment(bytes32 fix, address who) internal pure returns (bytes32) {
        return keccak256(abi.encode(fix, bytes32(0), bytes32("salt"), who));
    }

    function _commit(address who, uint256 b, bytes32 fix) internal returns (uint256) {
        _fund(who, 100 * C);
        vm.prank(who);
        return rc.commit(b, _commitment(fix, who));
    }

    function _claim(uint256 b, bytes32 fix, address who) internal {
        rc.claim(b, fix, bytes32(0), bytes32("salt"));
        who;
    }

    // ---------- a check through Panels ----------

    function _usage(uint256 pid, address key) internal pure returns (IFeesV3.Usage memory u) {
        u.receipt = keccak256(abi.encode("receipt", pid, key));
        u.input = 28_500;
        u.cached = 7_000;
        u.output = 4_000;
        u.vcpuSeconds = 960;
        u.gbSeconds = 1_920;
        u.storageMb = 1;
    }

    function _reportSeat(uint256 pid, address key) internal {
        IFeesV3.Usage memory u = _usage(pid, key);
        bytes32 subject = keccak256(abi.encode(USAGE_TAG, address(rc), pid, key));
        rc.report(pid, key, u, _statementSig(key, subject, keccak256(abi.encode(u))));
    }

    function _reportAll(uint256 pid) internal {
        address[] memory js = pn.judges(pid);
        for (uint256 i; i < js.length; ++i) {
            _reportSeat(pid, js[i]);
        }
    }

    /// Draws check `id`, its judges vote `pass` (all alike), report, and the result is posted; returns its panel.
    function _judgeCheck(uint256 id, bool pass) internal returns (uint256 pid) {
        pid = _draw(id);
        require(pid != 0, "no panel");
        uint256 k = pn.panel(pid).k;
        _judge(pid, pass ? _votes(k, k) : _votes(k, 0));
        _reportAll(pid);
        vm.prank(relayer);
        rc.result(id);
    }

    /// Audits agreeing (each audit panel reported and paid), then the window passes and Panels finalizes it.
    function _final(uint256 id) internal {
        uint256 before = pn.panelCount();
        _runAudits(id, true);
        for (uint256 q = before + 1; q <= pn.panelCount(); ++q) {
            Panel memory p = pn.panel(q);
            if (p.kind != Kind.Audit || p.id != id) continue;
            _reportAll(q);
            rc.payPanel(q);
        }
        uint256 at = pn.submission(id).finalAt;
        if (vm.getBlockTimestamp() < at) vm.warp(at);
        pn.finalize(id);
    }

    /// The whole check: judged, posted and final.
    function _check(uint256 id, bool pass) internal returns (uint256 pid) {
        pid = _judgeCheck(id, pass);
        _final(id);
    }
}
