// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {OraclesV2} from "./helpers/OraclesV2.sol";
import {genesis} from "./helpers/GenesisV2.sol";
import {RaceV2 as Race} from "../../src/v2/RaceV2.sol";
import {RaceV2Base} from "../../src/v2/RaceV2Base.sol";
import {Verdicts} from "../../src/v2/Verdicts.sol";
import {Fees} from "../../src/v2/Fees.sol";
import {IFees} from "../../src/v2/IFees.sol";
import {QuoterV2} from "../../src/v2/QuoterV2.sol";
import {MockCoin} from "../mocks/MockCoin.sol";

/// proof-of-fix#85 task 5.7 (design S15, S6): check fees. Spec scenarios (oracle-network delta):
/// - "Check fees: costs passed through per unit, plus one agreed service fee": "One judge pads its usage", "A heavier
///   check costs more at the same prices", "The deposit's ceiling";
/// - "The price table and the service fee change only within bounds": "A price jump", "A service fee above the cap",
///   "A price update's notice"; and #105's 2× genesis cap;
/// - bounty-market "Checks paid by the contributor": "The solver pays its checks", "The winner is refunded".
/// Every expected amount is computed here again from the unit prices, independently of the contract's arithmetic.
contract FeesV2Test is OraclesV2 {
    uint256 constant C = 1e6;
    uint256 constant BPS = 10_000;
    uint256 constant FAMILIES = 7;
    uint256 constant BASE = 3 * FAMILIES; // vCPU-s, GB-s, storage MB, ETH, SERVICE_FEE follow the families' entries

    Race race;
    Fees meter;
    Verdicts verdicts;
    MockCoin usd;
    address reporter = makeAddr("reporter");
    address alice = makeAddr("alice");
    address solver1 = makeAddr("solver1");
    address solver2 = makeAddr("solver2");
    address relayer = makeAddr("relayer");

    // the families' public prices (pof.costs JUDGE, 2026-10-30), micro-coins per million tokens: input, cached, output
    uint256[21] TOKENS = [
        uint256(4_000_000), 200_000, 20_000_000, // anthropic
        2_000_000, 100_000, 10_000_000, // openai
        2_000_000, 200_000, 12_000_000, // google
        1_320_000, 44_000, 3_960_000, // deepseek
        1_500_000, 1_500_000, 4_500_000, // qwen
        500_000, 50_000, 1_500_000, // mistral
        500_000, 500_000, 770_000 // llama
    ];
    uint256 constant VCPU = 11_244_444; // per million vCPU-seconds (Fargate, pof.checkgas)
    uint256 constant GB = 1_234_722; // per million GB-seconds
    uint256 constant STORAGE = 269_531_250; // per million MB (a year of S3)
    uint256 constant ETH = 2_700_000_000; // micro-coins per ETH
    uint256 constant SERVICE = 50_000; // $0.05 (owner, 2026-11-01)

    uint64 constant CAP_IN = 140_000;
    uint64 constant CAP_OUT = 16_000;
    uint64 constant CAP_MB = 20;
    uint64 constant GAS_ALLOWANCE = 1_000_000;
    uint64 constant GAS_OVERHEAD = 50_000;
    uint64 constant MAX_GAS_PRICE = 1 gwei;

    function setUp() public {
        usd = new MockCoin("Mock USD", "mUSD", 6);
        _makeOracles(7, 5);
        for (uint256 i; i < 7; ++i) {
            operatorAccounts.push(makeAddr(string.concat("operator", vm.toString(i))));
            operatorKeys.push(oracleSet[i]);
        }
        (race, meter) = _deploy(false);
        verdicts = race.verdicts();
    }

    // ---------- helpers ----------

    function _prices() internal view returns (uint256[] memory p) {
        p = new uint256[](BASE + 5);
        for (uint256 i; i < BASE; ++i) {
            p[i] = TOKENS[i];
        }
        (p[BASE], p[BASE + 1], p[BASE + 2], p[BASE + 3], p[BASE + 4]) = (VCPU, GB, STORAGE, ETH, SERVICE);
    }

    function _profile() internal pure returns (Fees.Profile memory) {
        return Fees.Profile(keccak256("python:3.12 test image"), 2_000, 4_096, 1_200); // 2 vCPU, 4 GB, 20 minutes
    }

    /// A metered RaceV2: its Verdicts (7 seats, quorum 5, one operator account each), its Fees, then the race.
    function _deploy(bool single) internal returns (Race r, Fees m) {
        address[] memory feeCoins = new address[](1);
        feeCoins[0] = address(usd);
        Verdicts.Genesis memory vg = genesis(oracleSet, oracleQuorum, operatorAccounts, operatorKeys);
        Verdicts v = new Verdicts(vg);
        Fees.Genesis memory g;
        g.coin = address(usd);
        g.families = vg.families;
        g.prices = _prices();
        g.caps = Fees.Caps(CAP_IN, CAP_OUT, CAP_MB, GAS_ALLOWANCE, GAS_OVERHEAD, MAX_GAS_PRICE);
        g.repos = new bytes32[](1);
        g.repos[0] = REPO;
        g.profiles = new Fees.Profile[](1);
        g.profiles[0] = _profile();
        g.defaultProfile = _profile();
        g.ciSingleRun = single;
        m = new Fees(v, g);
        bytes32[] memory repos = new bytes32[](1);
        bytes32[] memory hs = new bytes32[](1);
        repos[0] = REPO;
        hs[0] = GENESIS_HEAD;
        r = new Race(_config(), feeCoins, 1_000, 100_000, v, 300, 0, repos, hs, GENESIS_CONSTITUTION, m);
    }

    function _config() internal returns (RaceV2Base.Config memory c) {
        c.infrastructure = makeAddr("infra");
        c.insurance = makeAddr("insurance");
        c.registrationFee = 2e6;
        c.issueStake = 5e6;
        c.attemptFee = 0.5e6;
        c.evaluationFee = 2e6;
        c.checkDeposit = 6.6e6; // unused with a meter
        c.appealFee = 2e6;
        c.appealDeposit = 5e6;
        c.startPriceBps = 5_000;
        c.riseBpsPerDay = 1_000;
        c.finderFeeBps = 1_765;
        c.idleDays = 28;
        c.resultDays = 7;
        c.mergeDays = 14;
        c.windowDays = 7;
        c.releaseEveryDays = 7;
        c.instalments = 4;
    }

    function _fund(address who, uint256 amount) internal {
        usd.mint(who, amount);
        vm.prank(who);
        usd.approve(address(race), type(uint256).max);
    }

    function _openBounty() internal returns (uint256 b) {
        _fund(reporter, 7 * C);
        vm.prank(reporter);
        uint256 i = race.register(address(usd), REPO);
        b = _accept(race, i);
        _fund(alice, 100 * C);
        vm.prank(alice);
        race.pledge(b, address(usd), 100 * C);
    }

    function _commit(address who, uint256 b, bytes32 fix) internal returns (uint256) {
        _fund(who, 50 * C);
        vm.prank(who);
        return race.commit(b, keccak256(abi.encode(fix, bytes32("salt"), who)), address(usd));
    }

    function _usage(uint64 input, uint64 cached, uint64 output, uint64 vcpu, uint64 gb, uint64 mb)
        internal
        pure
        returns (Fees.Usage memory u)
    {
        u = Fees.Usage(keccak256(abi.encode(input, output, vcpu)), input, cached, output, vcpu, gb, mb);
    }

    /// The drawn judges of submission `id`, in draw order, and their secrets.
    function _judges(uint256 id) internal view returns (address[] memory js, uint256[] memory ks) {
        RaceV2Base.Submission memory s = race.submission(id);
        (js,) = verdicts.drawn(s.seed, s.bounty, id, address(race));
        ks = new uint256[](js.length);
        for (uint256 j; j < js.length; ++j) {
            for (uint256 i; i < oracleSet.length; ++i) {
                if (oracleSet[i] == js[j]) ks[j] = oracleSecrets[i];
            }
        }
    }

    function _sign(uint256 secret, bytes32 digest) internal pure returns (bytes memory) {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(secret, digest);
        return abi.encodePacked(r, s, v);
    }

    function _report(uint256 id, uint256 secret, Fees.Usage memory u) internal {
        meter.report(id, u, _sign(secret, meter.usageDigest(id, u)));
    }

    /// A seat's family index and its operator account.
    function _seatOfKey(address k) internal view returns (uint256 fam, address op) {
        for (uint256 i; i < 7; ++i) {
            if (oracleSet[i] == k) {
                Verdicts.Seat memory seat = verdicts.seat(_seatIndex(k));
                for (uint256 f; f < FAMILIES; ++f) {
                    if (meter.families()[f] == seat.family) fam = f;
                }
                op = operatorAccounts[i];
            }
        }
    }

    function _seatIndex(address k) internal view returns (uint256) {
        for (uint256 s; s < verdicts.seatCount(); ++s) {
            if (verdicts.seat(s).key == k) return s;
        }
        revert("no seat");
    }

    /// One judge's expected pay for the (already capped, median) usage at its family's prices: tokens, sandbox,
    /// storage, each rounded down, plus the service fee (the contract rounds the same way).
    function _pay(uint256 fam, Fees.Usage memory m, bool ci) internal view returns (uint256) {
        uint256 i = 3 * fam;
        uint256 tokens =
            ((uint256(m.input) - m.cached) * TOKENS[i] + uint256(m.cached) * TOKENS[i + 1] + uint256(m.output) * TOKENS[i + 2]) / 1e6;
        uint256 run = ci ? (uint256(m.vcpuSeconds) * VCPU + uint256(m.gbSeconds) * GB) / 1e6 : 0;
        return tokens + run + uint256(m.storageMb) * STORAGE / 1e6 + SERVICE;
    }

    /// The deposit's worst case, from the prices again: 3 judges at the dearest family's caps, each with its storage
    /// and service fee, `runs` CI runs at the profile's limits, and the gas allowance.
    function _expectedDeposit(uint256 runs) internal view returns (uint256) {
        uint256 ai;
        for (uint256 f; f < FAMILIES; ++f) {
            uint256 a = uint256(CAP_IN) * TOKENS[3 * f] + uint256(CAP_OUT) * TOKENS[3 * f + 2];
            if (a > ai) ai = a;
        }
        uint256 perJudge = _up(ai + uint256(CAP_MB) * STORAGE) + SERVICE;
        uint256 run = _up(uint256(2_400) * VCPU + uint256(4_800) * GB); // 2 vCPU × 1,200 s; 4 GB × 1,200 s
        uint256 gas = _up(uint256(GAS_ALLOWANCE) * MAX_GAS_PRICE * ETH / 1e12);
        return 3 * perJudge + runs * run + gas;
    }

    function _up(uint256 x) internal pure returns (uint256) {
        return (x + 1e6 - 1) / 1e6;
    }

    function _owed(address who) internal view returns (uint256) {
        return race.owed(who, address(usd));
    }

    /// A price update signed by the first `k` seats in address order (the constitution tier: 5 of 7).
    function _update(uint256[] memory next, uint256 k) internal returns (bytes32 nonce, bytes[] memory sigs) {
        nonce = _nonce();
        bytes32 digest = meter.updateDigest(keccak256(abi.encodePacked(next)), keccak256("public price lists"), nonce);
        sigs = new bytes[](k);
        for (uint256 i; i < k; ++i) {
            sigs[i] = _sign(oracleSecrets[i], digest);
        }
    }

    function _propose(uint256[] memory next, uint256 k) internal {
        (bytes32 nonce, bytes[] memory sigs) = _update(next, k);
        meter.propose(next, keccak256("public price lists"), nonce, sigs);
    }

    /// The same, expecting the meter to refuse it.
    function _proposeRefused(uint256[] memory next, uint256 k, bytes memory err) internal {
        (bytes32 nonce, bytes[] memory sigs) = _update(next, k);
        vm.expectRevert(err);
        meter.propose(next, keccak256("public price lists"), nonce, sigs);
    }

    // ---------- the deposit's ceiling ----------

    /// Spec scenario "The deposit's ceiling": the commit takes the worst case of the caps and the CI profile, plus the
    /// service fees and the gas allowance, in the version's fee coin.
    function test_depositIsTheWorstCase() public {
        uint256 b = _openBounty();
        uint256 expected = _expectedDeposit(3);
        assertEq(meter.maxDepositFor(b), expected);
        uint256 id = _commit(solver1, b, "fix1");
        assertEq(race.submission(id).deposit, expected);
        assertEq(usd.balanceOf(solver1), 50 * C - expected);
        assertEq(race.totalDeposits(address(usd)), expected + 5 * C); // with the issue's stake
    }

    /// The quote shows the maximum check cost, the service fee and the judges per check.
    function test_quoteShowsTheMaximumCheckCost() public {
        uint256 b = _openBounty();
        QuoterV2 q = new QuoterV2();
        QuoterV2.Quote memory quote = q.quote(race, b, address(usd));
        assertTrue(quote.metered);
        assertEq(quote.checkDeposit, _expectedDeposit(3));
        assertEq(quote.serviceFee, SERVICE);
        assertEq(quote.judges, 3);
    }

    /// A metered version takes check deposits in its one fee coin only (S15).
    function test_otherCoinRefused() public {
        MockCoin eur = new MockCoin("Mock EUR", "mEUR", 6);
        address[] memory feeCoins = new address[](2);
        (feeCoins[0], feeCoins[1]) = (address(usd), address(eur));
        Verdicts.Genesis memory vg = genesis(oracleSet, oracleQuorum, operatorAccounts, operatorKeys);
        Verdicts v = new Verdicts(vg);
        Fees.Genesis memory g;
        g.coin = address(usd);
        g.families = vg.families;
        g.prices = _prices();
        g.caps = Fees.Caps(CAP_IN, CAP_OUT, CAP_MB, GAS_ALLOWANCE, GAS_OVERHEAD, MAX_GAS_PRICE);
        g.defaultProfile = _profile();
        Fees m = new Fees(v, g);
        bytes32[] memory repos = new bytes32[](1);
        bytes32[] memory hs = new bytes32[](1);
        (repos[0], hs[0]) = (REPO, GENESIS_HEAD);
        Race r = new Race(_config(), feeCoins, 1_000, 100_000, v, 300, 0, repos, hs, GENESIS_CONSTITUTION, m);
        race = r;
        meter = m;
        verdicts = v;
        uint256 b = _openBounty();
        eur.mint(solver1, 50 * C);
        vm.startPrank(solver1);
        eur.approve(address(r), type(uint256).max);
        vm.expectRevert(abi.encodeWithSelector(RaceV2Base.NotFeeCoin.selector, address(eur)));
        r.commit(b, keccak256("c"), address(eur));
        vm.stopPrank();
    }

    /// A meter serves one race, and only a fee coin of it.
    function test_meterBindsOnce() public {
        vm.expectRevert(Fees.AlreadyBound.selector);
        meter.bind();
        vm.expectRevert(Fees.NotRace.selector);
        meter.settle(1, relayer, 0);
        MockCoin other = new MockCoin("Other", "OTH", 6);
        Verdicts.Genesis memory vg = genesis(oracleSet, oracleQuorum, operatorAccounts, operatorKeys);
        Verdicts v = new Verdicts(vg);
        Fees.Genesis memory g;
        g.coin = address(other); // not one of the race's fee coins
        g.families = vg.families;
        g.prices = _prices();
        g.caps = Fees.Caps(CAP_IN, CAP_OUT, CAP_MB, GAS_ALLOWANCE, GAS_OVERHEAD, MAX_GAS_PRICE);
        g.defaultProfile = _profile();
        Fees m = new Fees(v, g);
        address[] memory feeCoins = new address[](1);
        feeCoins[0] = address(usd);
        vm.expectRevert(RaceV2Base.BadParams.selector);
        new Race(_config(), feeCoins, 1_000, 100_000, v, 300, 0, new bytes32[](0), new bytes32[](0), GENESIS_CONSTITUTION, m);
    }

    // ---------- the charge ----------

    /// Spec scenarios "One judge pads its usage" and "The solver pays its checks": two judges report 4,000 tokens and
    /// the third 40,000; every counted judge is paid the median (4,000) at its own family's prices, plus the service
    /// fee, to its operator's account; the relayer its gas; the rest of the deposit returns to the solver.
    function test_padderChangesNothing() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, "fix1");
        uint256 deposit = race.submission(id).deposit;
        (address[] memory js, uint256[] memory ks) = _judges(id);
        _report(id, ks[0], _usage(4_000, 0, 1_000, 300, 600, 2));
        _report(id, ks[1], _usage(40_000, 0, 1_000, 300, 600, 2)); // the padder
        _report(id, ks[2], _usage(4_000, 0, 1_000, 300, 600, 2));
        vm.txGasPrice(0.05 gwei);
        (RaceV2Base.Verdict memory v, bytes[] memory sigs) =
            _signResult(race, id, RaceV2Base.Outcome.Fail, "fix1", new RaceV2Base.Fee[](0));
        vm.prank(relayer);
        race.result(v, new RaceV2Base.Fee[](0), sigs);

        Fees.Usage memory mid = _usage(4_000, 0, 1_000, 300, 600, 2);
        uint256 charged;
        for (uint256 j; j < 3; ++j) {
            (uint256 fam, address op) = _seatOfKey(js[j]);
            uint256 pay = _pay(fam, mid, true);
            assertEq(_owed(op), pay, "the median at its own family's prices, plus the service fee");
            charged += pay;
        }
        uint256 gas = _owed(relayer);
        assertGt(gas, 0);
        assertLe(gas, uint256(GAS_ALLOWANCE) * 0.05 gwei * ETH / 1e18);
        charged += gas;
        assertEq(_owed(solver1), deposit - charged, "the rest of the deposit returns");
        assertEq(race.submission(id).deposit, charged, "what the checks were charged");
        assertTrue(meter.settled(id));
        _assertBooks();
    }

    /// Spec scenario "A heavier check costs more at the same prices".
    function test_heavierCheckCostsMore() public {
        uint256 b1 = _openBounty();
        uint256 b2 = _openBounty();
        uint256 id1 = _commit(solver1, b1, "fix1");
        uint256 id2 = _commit(solver2, b2, "fix2");
        (, uint256[] memory k1) = _judges(id1);
        (, uint256[] memory k2) = _judges(id2);
        for (uint256 j; j < 3; ++j) {
            _report(id1, k1[j], _usage(3_000, 0, 500, 60, 120, 1));
            _report(id2, k2[j], _usage(40_000, 0, 4_000, 600, 1_200, 5));
        }
        uint256 d1 = race.submission(id1).deposit;
        uint256 d2 = race.submission(id2).deposit;
        assertEq(d1, d2, "the same deposit: the same worst case");
        _result(race, id1, RaceV2Base.Outcome.Fail, "fix1", new RaceV2Base.Fee[](0));
        _result(race, id2, RaceV2Base.Outcome.Fail, "fix2", new RaceV2Base.Fee[](0));
        assertGt(race.submission(id2).deposit, race.submission(id1).deposit);
        assertGt(_owed(solver1), _owed(solver2));
    }

    /// A report above the caps is charged at the caps (a run that hit one stopped there).
    function test_reportsAreCapped() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, "fix1");
        (address[] memory js, uint256[] memory ks) = _judges(id);
        Fees.Usage memory huge = _usage(1_000_000, 5_000, 100_000, 100_000, 100_000, 999);
        for (uint256 j; j < 3; ++j) {
            _report(id, ks[j], huge);
        }
        _result(race, id, RaceV2Base.Outcome.Fail, "fix1", new RaceV2Base.Fee[](0));
        Fees.Usage memory capped = _usage(CAP_IN, 5_000, CAP_OUT, 2_400, 4_800, CAP_MB);
        (uint256 fam, address op) = _seatOfKey(js[0]);
        assertEq(_owed(op), _pay(fam, capped, true));
        assertGe(_owed(solver1), 0);
        _assertBooks();
    }

    /// Two reports: the median of two is their mean, rounded down; a drawn judge that doesn't report isn't paid.
    function test_twoReportsAndASilentJudge() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, "fix1");
        (address[] memory js, uint256[] memory ks) = _judges(id);
        _report(id, ks[0], _usage(3_001, 0, 1_000, 100, 200, 1));
        _report(id, ks[1], _usage(4_000, 0, 2_000, 200, 400, 2));
        _result(race, id, RaceV2Base.Outcome.Fail, "fix1", new RaceV2Base.Fee[](0));
        Fees.Usage memory mid = _usage(3_500, 0, 1_500, 150, 300, 1);
        for (uint256 j; j < 2; ++j) {
            (uint256 fam, address op) = _seatOfKey(js[j]);
            assertEq(_owed(op), _pay(fam, mid, true));
        }
        (, address silent) = _seatOfKey(js[2]);
        assertEq(_owed(silent), 0);
        assertEq(meter.reports(id).length, 2);
    }

    /// With CI_SINGLE_RUN the tests run once: that run is charged once, at its own measurement, to its node.
    function test_singleAttestedRun() public {
        (race, meter) = _deploy(true);
        verdicts = race.verdicts();
        uint256 b = _openBounty();
        assertEq(meter.maxDepositFor(b), _expectedDeposit(1));
        uint256 id = _commit(solver1, b, "fix1");
        (address[] memory js, uint256[] memory ks) = _judges(id);
        _report(id, ks[0], _usage(4_000, 0, 1_000, 0, 0, 2));
        _report(id, ks[1], _usage(4_000, 0, 1_000, 900, 1_800, 2)); // the one that ran the tests
        _report(id, ks[2], _usage(4_000, 0, 1_000, 0, 0, 2));
        _result(race, id, RaceV2Base.Outcome.Fail, "fix1", new RaceV2Base.Fee[](0));
        Fees.Usage memory mid = _usage(4_000, 0, 1_000, 0, 0, 2);
        (uint256 f0, address o0) = _seatOfKey(js[0]);
        (uint256 f1, address o1) = _seatOfKey(js[1]);
        assertEq(_owed(o0), _pay(f0, mid, false));
        assertEq(_owed(o1), _pay(f1, mid, false) + (uint256(900) * VCPU + uint256(1_800) * GB) / 1e6);
    }

    /// With a meter the judges sign an empty fee list: their pay comes from their usage.
    function test_signedFeeListRefused() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, "fix1");
        RaceV2Base.Fee[] memory fees = new RaceV2Base.Fee[](1);
        fees[0] = RaceV2Base.Fee(relayer, 1 * C);
        (RaceV2Base.Verdict memory v, bytes[] memory sigs) =
            _signResult(race, id, RaceV2Base.Outcome.Fail, "fix1", fees);
        vm.expectRevert(RaceV2Base.Refused.selector);
        race.result(v, fees, sigs);
    }

    // ---------- reports ----------

    function test_reportByAKeyNotDrawnRefused() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, "fix1");
        (address[] memory js,) = _judges(id);
        uint256 outsider;
        for (uint256 i; i < oracleSet.length; ++i) {
            bool drawn;
            for (uint256 j; j < js.length; ++j) {
                if (js[j] == oracleSet[i]) drawn = true;
            }
            if (!drawn) outsider = oracleSecrets[i];
        }
        Fees.Usage memory u = _usage(4_000, 0, 1_000, 300, 600, 2);
        bytes memory sig = _sign(outsider, meter.usageDigest(id, u));
        vm.expectRevert(Fees.NotDrawn.selector);
        meter.report(id, u, sig);
        (, uint256 stranger) = makeAddrAndKey("stranger");
        sig = _sign(stranger, meter.usageDigest(id, u));
        vm.expectRevert(Fees.NotDrawn.selector);
        meter.report(id, u, sig);
    }

    function test_reportTwiceAndAfterTheResultRefused() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, "fix1");
        (, uint256[] memory ks) = _judges(id);
        _report(id, ks[0], _usage(4_000, 0, 1_000, 300, 600, 2));
        Fees.Usage memory again = _usage(5_000, 0, 1_000, 300, 600, 2);
        bytes memory sig = _sign(ks[0], meter.usageDigest(id, again));
        vm.expectRevert(Fees.AlreadyReported.selector);
        meter.report(id, again, sig);
        _result(race, id, RaceV2Base.Outcome.Fail, "fix1", new RaceV2Base.Fee[](0));
        Fees.Usage memory late = _usage(4_000, 0, 1_000, 300, 600, 2);
        sig = _sign(ks[1], meter.usageDigest(id, late));
        vm.expectRevert(Fees.AlreadySettled.selector);
        meter.report(id, late, sig);
    }

    /// A report's signature binds its submission: it can't be moved to another.
    function test_reportBindsItsSubmission() public {
        uint256 b = _openBounty();
        uint256 id1 = _commit(solver1, b, "fix1");
        uint256 id2 = _commit(solver2, b, "fix2");
        (, uint256[] memory ks) = _judges(id1);
        Fees.Usage memory u = _usage(4_000, 0, 1_000, 300, 600, 2);
        bytes memory sig = _sign(ks[0], meter.usageDigest(id1, u));
        vm.expectRevert(); // recovers another key: not drawn for id2 (or not a seat at all)
        meter.report(id2, u, sig);
    }

    // ---------- the relayer's gas ----------

    /// Gas is reimbursed at the transaction's price, at most MAX_GAS_PRICE, within the deposit's allowance.
    function test_relayerGasBounded() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, "fix1");
        vm.txGasPrice(100 gwei); // above MAX_GAS_PRICE: counted at 1 gwei
        (RaceV2Base.Verdict memory v, bytes[] memory sigs) =
            _signResult(race, id, RaceV2Base.Outcome.Fail, "fix1", new RaceV2Base.Fee[](0));
        vm.prank(relayer);
        race.result(v, new RaceV2Base.Fee[](0), sigs);
        uint256 gas = _owed(relayer);
        assertGt(gas, uint256(GAS_OVERHEAD) * 1 gwei * ETH / 1e18);
        assertLe(gas, uint256(GAS_ALLOWANCE) * 1 gwei * ETH / 1e18);
    }

    // ---------- the winner's refund (S6) ----------

    /// Spec scenario "The winner is refunded": the winner's checks for its fix come back from the bounty once it's
    /// paid, from what the pot still holds after the price and the reporter's dues.
    function test_winnerRefundedAtSettlement() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, "fix1");
        (, uint256[] memory ks) = _judges(id);
        for (uint256 j; j < 3; ++j) {
            _report(id, ks[j], _usage(4_000, 0, 1_000, 300, 600, 2));
        }
        uint256 deposit = race.submission(id).deposit;
        _result(race, id, RaceV2Base.Outcome.Pass, "fix1", new RaceV2Base.Fee[](0));
        uint256 checks = race.submission(id).deposit;
        assertEq(_owed(solver1), deposit - checks);
        vm.warp(race.start() + 1 days);
        _merged(race, b);
        uint256 price = race.priceOf(b, address(usd), 1);
        vm.warp(race.start() + 35 days);
        race.settle(b, address(usd));
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Paid));
        assertEq(_owed(solver1), deposit - checks + price + checks, "the price, and its checks back");
        _assertBooks();
    }

    // ---------- price updates (S15) ----------

    function _scaled(uint256[] memory p, uint256 bps) internal pure returns (uint256[] memory out) {
        out = new uint256[](p.length);
        for (uint256 i; i < p.length; ++i) {
            out[i] = p[i] * bps / BPS;
        }
    }

    /// Spec scenario "A price jump": an entry raised 40 % is refused; 25 % passes.
    function test_priceJumpRefused() public {
        uint256[] memory next = _prices();
        next[0] = next[0] * 14 / 10;
        _proposeRefused(next, 5, abi.encodeWithSelector(Fees.OutOfBounds.selector, 0));
        next = _prices();
        next[0] = next[0] * 125 / 100;
        _propose(next, 5);
        assertEq(meter.pending().prices[0], next[0]);
    }

    /// Spec scenario "A service fee above the cap": within 25 % of the current one but above SERVICE_FEE_CAP.
    function test_serviceFeeAboveTheCapRefused() public {
        uint256 last = BASE + 4;
        uint256[] memory p = _prices();
        // walk the fee up 25 % a week, within 2× genesis, until the next step would pass $0.25 (2× genesis is $0.10:
        // the 2× cap binds first, so build a version whose genesis fee is $0.20 to reach the $0.25 cap)
        p[last] = 200_000;
        Verdicts.Genesis memory vg = genesis(oracleSet, oracleQuorum, operatorAccounts, operatorKeys);
        Verdicts v = new Verdicts(vg);
        Fees.Genesis memory g;
        g.coin = address(usd);
        g.families = vg.families;
        g.prices = p;
        g.caps = Fees.Caps(CAP_IN, CAP_OUT, CAP_MB, GAS_ALLOWANCE, GAS_OVERHEAD, MAX_GAS_PRICE);
        g.defaultProfile = _profile();
        meter = new Fees(v, g);
        uint256[] memory next = _scaled(p, BPS);
        next[last] = 250_001; // +25 % is 250,000: one micro-coin over the cap
        _proposeRefused(next, 5, abi.encodeWithSelector(Fees.OutOfBounds.selector, last));
        next[last] = 250_000;
        _propose(next, 5);
        // and a genesis fee above the cap is refused at deployment
        p[last] = 250_001;
        g.prices = p;
        vm.expectRevert(Fees.BadParams.selector);
        new Fees(v, g);
    }

    /// #105: no entry above 2× its genesis value, however many 25 % steps.
    function test_twiceGenesisCap() public {
        uint256[] memory p = _prices();
        for (uint256 step; step < 3; ++step) {
            p = _scaled(p, 12_500); // 1.25, 1.5625, 1.953 × genesis
            _propose(p, 5);
            vm.warp(vm.getBlockTimestamp() + 7 days);
            meter.applyUpdate();
        }
        uint256[] memory next = _scaled(p, 12_500); // 2.44 × genesis
        _proposeRefused(next, 5, abi.encodeWithSelector(Fees.OutOfBounds.selector, 0));
    }

    /// An update needs the constitution tier (5 of 7), one at a time.
    function test_updateNeedsFiveSeatsAndOneAtATime() public {
        uint256[] memory next = _scaled(_prices(), 11_000);
        _proposeRefused(next, 4, abi.encodeWithSelector(Verdicts.TooFewSignatures.selector));
        _propose(next, 5);
        _proposeRefused(next, 5, abi.encodeWithSelector(Fees.AlreadyPending.selector));
        vm.expectRevert(Fees.TooEarly.selector);
        meter.applyUpdate();
    }

    /// Spec scenario "A price update's notice": attempts in the next 7 days are still charged at the old prices.
    function test_noticeKeepsTheOldPrices() public {
        uint256[] memory next = _scaled(_prices(), 12_500);
        _propose(next, 5);
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, "fix1");
        // the deposit already covers the pending table: it's the dearer of the two
        assertEq(race.submission(id).deposit, _expectedDepositScaled(12_500));
        (address[] memory js, uint256[] memory ks) = _judges(id);
        Fees.Usage memory u = _usage(4_000, 0, 1_000, 300, 600, 2);
        for (uint256 j; j < 3; ++j) {
            _report(id, ks[j], u);
        }
        uint256 t = vm.getBlockTimestamp();
        vm.warp(t + 6 days);
        _result(race, id, RaceV2Base.Outcome.Fail, "fix1", new RaceV2Base.Fee[](0));
        (uint256 fam, address op) = _seatOfKey(js[0]);
        assertEq(_owed(op), _pay(fam, u, true), "the old prices during the notice");
        assertEq(meter.prices()[0], TOKENS[0]);
        vm.warp(t + 7 days);
        assertEq(meter.prices()[0], next[0], "in force from its effective time");
    }

    function _expectedDepositScaled(uint256 bps) internal view returns (uint256) {
        uint256 ai;
        for (uint256 f; f < FAMILIES; ++f) {
            uint256 a = uint256(CAP_IN) * (TOKENS[3 * f] * bps / BPS) + uint256(CAP_OUT) * (TOKENS[3 * f + 2] * bps / BPS);
            if (a > ai) ai = a;
        }
        uint256 perJudge = _up(ai + uint256(CAP_MB) * (STORAGE * bps / BPS)) + SERVICE * bps / BPS;
        uint256 run = _up(uint256(2_400) * (VCPU * bps / BPS) + uint256(4_800) * (GB * bps / BPS));
        uint256 gas = _up(uint256(GAS_ALLOWANCE) * MAX_GAS_PRICE * (ETH * bps / BPS) / 1e12);
        return 3 * perJudge + 3 * run + gas;
    }

    // ---------- withdrawals and the books ----------

    /// An operator pulls its fees in the fee coin (Article 5.3: credits, pulled).
    function test_operatorWithdrawsItsFees() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, "fix1");
        (address[] memory js, uint256[] memory ks) = _judges(id);
        for (uint256 j; j < 3; ++j) {
            _report(id, ks[j], _usage(4_000, 0, 1_000, 300, 600, 2));
        }
        _result(race, id, RaceV2Base.Outcome.Fail, "fix1", new RaceV2Base.Fee[](0));
        (, address op) = _seatOfKey(js[0]);
        uint256 fee = _owed(op);
        assertGt(fee, 0);
        vm.prank(op);
        race.withdraw(address(usd), op);
        assertEq(usd.balanceOf(op), fee);
        assertEq(_owed(op), 0);
        _assertBooks();
    }

    /// Deposits always equal charges, repayments and refunds: for any usage, what the judges, the relayer and the
    /// solver are credited adds up to the deposit, and the contract stays solvent.
    function testFuzz_chargesPlusRefundEqualTheDeposit(
        uint64[3] memory input,
        uint64[3] memory output,
        uint64[3] memory vcpu,
        uint8 reports,
        uint64 gasPrice
    ) public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, "fix1");
        uint256 deposit = race.submission(id).deposit;
        (address[] memory js, uint256[] memory ks) = _judges(id);
        uint256 n = uint256(reports) % 4;
        for (uint256 j; j < n; ++j) {
            uint64 cpu = uint64(bound(vcpu[j], 0, type(uint32).max));
            _report(id, ks[j], _usage(input[j], input[j] / 3, output[j], cpu, cpu * 2, 3));
        }
        vm.txGasPrice(bound(gasPrice, 0, 10 gwei));
        (RaceV2Base.Verdict memory v, bytes[] memory sigs) =
            _signResult(race, id, RaceV2Base.Outcome.Fail, "fix1", new RaceV2Base.Fee[](0));
        vm.prank(relayer);
        race.result(v, new RaceV2Base.Fee[](0), sigs);
        uint256 credited = _owed(solver1) + _owed(relayer);
        for (uint256 j; j < 3; ++j) {
            (, address op) = _seatOfKey(js[j]);
            credited += _owed(op);
        }
        assertEq(credited, deposit);
        assertEq(race.submission(id).deposit, deposit - _owed(solver1));
        _assertBooks();
    }

    function _assertBooks() internal view {
        assertTrue(race.solvent(address(usd)));
        assertEq(
            usd.balanceOf(address(race)),
            race.totalHeld(address(usd)) + race.totalOwed(address(usd)) + race.totalDeposits(address(usd))
        );
    }

    /// A meter is keyless: no function changes its caps, its CI profiles or its coin; prices change only through
    /// `propose` (the constitution tier, within bounds) and `applyUpdate`; `bind` once, by its race; `settle` by it.
    function test_noPrivilegedCall() public view {
        string memory json = vm.readFile("out/Fees.sol/Fees.json");
        string[24] memory allowed = [
            "bind", "settle", "report", "propose", "applyUpdate", "isParty",
            "verdicts", "coin", "ciSingleRun", "race", "genesis", "settled", "usageDigest", "updateDigest",
            "domainSeparator", "families", "prices", "pending", "caps", "serviceFee", "profileOf", "reports",
            "maxDepositFor", "maxDeposit"
        ];
        string[7] memory constants =
            ["BPS", "PRICE_STEP_MAX_BPS", "PRICE_DELAY", "PRICE_CAP_MULTIPLE", "SERVICE_FEE_CAP", "USAGE_TYPEHASH", "PRICE_UPDATE_TYPEHASH"];
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
                ok = keccak256(bytes(name)) == keccak256(bytes(allowed[j]));
            }
            for (uint256 j; j < constants.length && !ok; ++j) {
                ok = keccak256(bytes(name)) == keccak256(bytes(constants[j]));
            }
            assertTrue(ok, string.concat("unexpected external function: ", name));
            ++n;
        }
        assertEq(n, allowed.length + constants.length);
    }

    function _unused() internal pure returns (IFees) {
        return IFees(address(0));
    }
}
