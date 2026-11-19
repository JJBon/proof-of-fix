// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Test, console} from "forge-std/Test.sol";
import {FeesV3} from "../../src/v3/FeesV3.sol";
import {IFeesV3, IFeesV3Scores} from "../../src/v3/IFeesV3.sol";
import {MockValidators, MockScores} from "./helpers/FeesV3Mocks.sol";

/// #132 task 3.3: FeesV3, v3's check-fee meter (design D9, D14, D19). Every scenario of specs/check-pricing (open
/// families included), the service-fee scenarios of specs/judge-scores, a fuzz test that no sequence of posts moves a
/// price by more than PRICE_STEP_MAX per period, and roll's gas with a few dozen posters and families. The test
/// contract is the race (it binds the meter); Validators and Panels are mocks of the views FeesV3 reads. Expected
/// amounts are computed here again from the unit prices.
contract FeesV3Test is Test {
    uint256 constant BPS = 10_000;
    uint256 constant WAD = 1e18;
    bytes32 constant FA = "anthropic/claude";
    bytes32 constant FB = "openai/gpt";
    bytes32 constant FC = "meta/llama";
    bytes32 constant FD = "newlab/model"; // a family no one used at deployment
    bytes32 constant FE = "otherlab/model";
    bytes32 constant REPO = keccak256("repo");

    uint64 constant CAP_IN = 140_000;
    uint64 constant CAP_OUT = 16_000;
    uint64 constant CAP_MB = 20;
    uint64 constant GAS_ALLOWANCE = 1_000_000;
    uint64 constant GAS_OVERHEAD = 50_000;
    uint64 constant MAX_GAS_PRICE = 1 gwei;

    // the genesis table (v2's list prices, 2026-10-30): micro-coins per million units; ETH in micro-coins per ETH
    uint256[4] S = [uint256(11_244_444), 1_234_722, 269_531_250, 2_700_000_000]; // vCPU-s, GB-s, storage MB, ETH
    uint256[3][3] T = [
        [uint256(4_000_000), 200_000, 20_000_000], // anthropic
        [uint256(2_000_000), 100_000, 10_000_000], // openai
        [uint256(500_000), 500_000, 770_000] // llama
    ];

    FeesV3 fees;
    MockValidators vals;
    MockScores sc;
    address usd = makeAddr("usd");

    function setUp() public {
        vals = new MockValidators();
        sc = new MockScores();
        fees = _deploy(false);
        fees.bind();
    }

    // ---------- helpers ----------

    function _fams() internal pure returns (bytes32[] memory f) {
        f = new bytes32[](3);
        (f[0], f[1], f[2]) = (FA, FB, FC);
    }

    function _deploy(bool single) internal returns (FeesV3) {
        FeesV3.Genesis memory g;
        g.coin = usd;
        g.shared = S;
        g.families = _fams();
        g.tokens = new uint256[3][](3);
        for (uint256 i; i < 3; ++i) {
            g.tokens[i] = T[i];
        }
        g.caps = IFeesV3.Caps(CAP_IN, CAP_OUT, CAP_MB, GAS_ALLOWANCE, GAS_OVERHEAD, MAX_GAS_PRICE);
        g.repo = REPO;
        g.profile = _profile();
        g.ciSingleRun = single;
        return new FeesV3(vals, sc, g);
    }

    function _profile() internal pure returns (IFeesV3.Profile memory) {
        return IFeesV3.Profile(keccak256("python:3.12 test image"), 2_000, 4_096, 1_200); // 2 vCPU, 4 GB, 20 min
    }

    function _v(uint256 i) internal pure returns (address) {
        return address(uint160(0x10000 + i));
    }

    /// Validators 0..n-1 active, of the genesis families in turn.
    function _activate(uint256 n) internal {
        for (uint256 i; i < n; ++i) {
            _activateAs(i, _fams()[i % 3]);
        }
    }

    function _activateAs(uint256 i, bytes32 family) internal {
        vals.setFamily(_v(i), family);
        vals.setActive(_v(i), true);
    }

    function _shared(uint256 bps) internal view returns (uint256[4] memory s) {
        for (uint256 j; j < 4; ++j) {
            s[j] = S[j] * bps / BPS;
        }
    }

    function _tokens(uint256 f, uint256 bps) internal view returns (uint256[3] memory t) {
        for (uint256 j; j < 3; ++j) {
            t[j] = T[f][j] * bps / BPS;
        }
    }

    /// A full table: the shared units at `sharedBps` and the three genesis families' tokens at `tokenBps`.
    function _post(uint256 i, uint256 tokenBps, uint256 sharedBps) internal {
        uint256[3][] memory toks = new uint256[3][](3);
        for (uint256 f; f < 3; ++f) {
            toks[f] = _tokens(f, tokenBps);
        }
        _postRaw(i, _shared(sharedBps), _fams(), toks);
    }

    /// A full table at `bps`, plus `extra` priced at `extraTokens`.
    function _postWith(uint256 i, uint256 bps, bytes32 extra, uint256[3] memory extraTokens) internal {
        bytes32[] memory fs = new bytes32[](4);
        uint256[3][] memory toks = new uint256[3][](4);
        for (uint256 f; f < 3; ++f) {
            fs[f] = _fams()[f];
            toks[f] = _tokens(f, bps);
        }
        (fs[3], toks[3]) = (extra, extraTokens);
        _postRaw(i, _shared(bps), fs, toks);
    }

    function _postRaw(uint256 i, uint256[4] memory sh, bytes32[] memory fs, uint256[3][] memory toks) internal {
        vm.prank(_v(i));
        fees.post(sh, fs, toks);
    }

    /// Closes the oldest open period (warping to its end if needed).
    function _roll() internal {
        uint256 end = fees.start() + (fees.rolled() + 1) * 1 days;
        if (block.timestamp < end) vm.warp(end);
        fees.roll();
    }

    function _tp(bytes32 f, uint256 j) internal view returns (uint256) {
        return fees.tokenPrices(f)[j];
    }

    function _sp(uint256 j) internal view returns (uint256) {
        return fees.sharedPrices()[j];
    }

    function _genesisPrices() internal view returns (bool) {
        for (uint256 j; j < 4; ++j) {
            if (_sp(j) != S[j]) return false;
        }
        for (uint256 f; f < 3; ++f) {
            for (uint256 j; j < 3; ++j) {
                if (_tp(_fams()[f], j) != T[f][j]) return false;
            }
        }
        return true;
    }

    function _sorted(uint256[] memory xs) internal pure returns (uint256[] memory a) {
        a = new uint256[](xs.length);
        for (uint256 i; i < xs.length; ++i) {
            a[i] = xs[i];
        }
        for (uint256 i = 1; i < a.length; ++i) {
            for (uint256 j = i; j > 0 && a[j - 1] > a[j]; --j) {
                (a[j - 1], a[j]) = (a[j], a[j - 1]);
            }
        }
    }

    function _lowerMedian(uint256[] memory xs) internal pure returns (uint256) {
        return _sorted(xs)[(xs.length - 1) / 2];
    }

    function _usage(uint64 input, uint64 cached, uint64 output, uint64 vcpu, uint64 gb, uint64 mb)
        internal
        pure
        returns (IFeesV3.Usage memory)
    {
        return IFeesV3.Usage(keccak256(abi.encode(input, output, vcpu)), input, cached, output, vcpu, gb, mb);
    }

    function _report(address payee, bytes32 family, IFeesV3.Usage memory u)
        internal
        pure
        returns (IFeesV3.Report memory)
    {
        return IFeesV3.Report(payee, family, u);
    }

    /// One judge's usage at shared units `sh` and its family's token prices `t`.
    function _usageCost(uint256[4] memory sh, uint256[3] memory t, IFeesV3.Usage memory u)
        internal
        pure
        returns (uint256)
    {
        uint256 tokens = ((uint256(u.input) - u.cached) * t[0] + uint256(u.cached) * t[1] + uint256(u.output) * t[2]) / 1e6;
        uint256 run = (uint256(u.vcpuSeconds) * sh[0] + uint256(u.gbSeconds) * sh[1]) / 1e6;
        return tokens + run + uint256(u.storageMb) * sh[2] / 1e6;
    }

    /// A period with `submitted` attempts opened (ids from `firstId`), `waits` of them waiting and `seated` validators
    /// drawn, then closed.
    function _period(uint256 firstId, uint256 submitted, uint256 waits, uint256 seated) internal {
        for (uint256 i; i < submitted; ++i) {
            fees.open(firstId + i);
            if (i < waits) fees.waited(firstId + i);
        }
        address[] memory js = new address[](seated);
        for (uint256 i; i < seated; ++i) {
            js[i] = _v(i);
        }
        fees.drawn(js);
        _roll();
    }

    // ---------- Validators post cost tables for every unit ----------

    /// "A provider cuts its prices": validators post new tables; their latest replace their earlier ones, with no
    /// proposal or vote, and the next period's prices follow.
    function test_providerCutsItsPrices() public {
        _activate(5);
        for (uint256 i; i < 5; ++i) {
            _post(i, BPS, BPS);
        }
        for (uint256 i; i < 5; ++i) {
            _post(i, 9_000, BPS); // a provider cuts its token prices by 10 %
        }
        (uint256[3] memory t, bool current) = fees.postedTokens(_v(0), FA);
        assertTrue(current);
        assertEq(t[0], T[0][0] * 9_000 / BPS);
        assertEq(fees.posters().length, 5); // one table each: the latest
        _roll();
        for (uint256 f; f < 3; ++f) {
            for (uint256 j; j < 3; ++j) {
                assertEq(_tp(_fams()[f], j), T[f][j] * 9_000 / BPS);
            }
        }
        for (uint256 j; j < 4; ++j) {
            assertEq(_sp(j), S[j]);
        }
    }

    /// "A table without another family's price": a table with its own family's token price but not the other priced
    /// families' doesn't count; nor does one missing a shared unit, or a later table that drops a family.
    function test_tableWithoutAnotherFamilysPriceDoesntCount() public {
        _activate(5);
        _post(0, 5_000, 5_000);
        _post(1, 5_000, 5_000);
        for (uint256 i = 2; i < 5; ++i) {
            bytes32[] memory own = new bytes32[](1);
            uint256[3][] memory toks = new uint256[3][](1);
            (own[0], toks[0]) = (FA, _tokens(0, 5_000)); // only anthropic's token prices
            _postRaw(i, _shared(5_000), own, toks);
        }
        _roll(); // 2 tables count: fewer than MEDIAN_MIN_POSTERS
        assertTrue(_genesisPrices());
        _post(2, 5_000, 5_000); // its latest table now has every unit
        _roll();
        assertEq(_tp(FA, 0), T[0][0] * 7_500 / BPS);
        // a shared unit at 0, or a family's entry dropped by a later table: the table stops counting
        uint256[4] memory sh = _shared(5_000);
        sh[3] = 0;
        bytes32[] memory fs = _fams();
        uint256[3][] memory toks = new uint256[3][](3);
        for (uint256 f; f < 3; ++f) {
            toks[f] = _tokens(f, 5_000);
        }
        _postRaw(2, sh, fs, toks);
        (, bool current) = fees.postedShared(_v(2));
        assertFalse(current);
        uint256 before = _tp(FA, 0);
        _roll();
        assertEq(_tp(FA, 0), before);
        vm.prank(_v(3));
        vm.expectRevert(FeesV3.BadTable.selector);
        fees.post(sh, fs, new uint256[3][](2));
    }

    /// A candidate's, a suspended or a leaving validator's table doesn't count: only active validators post, and a
    /// poster that stops being active drops out until it posts again.
    function test_onlyActiveValidatorsTablesCount() public {
        vals.setFamily(_v(9), FA); // a candidate
        vm.expectRevert(FeesV3.NotActive.selector);
        _post(9, 5_000, 5_000);
        _activate(3);
        for (uint256 i; i < 3; ++i) {
            _post(i, 5_000, 5_000);
        }
        vals.setActive(_v(2), false); // suspended, or leaving
        _roll();
        assertTrue(_genesisPrices());
        assertEq(fees.posters().length, 2);
        vals.setActive(_v(2), true); // back, but its old table doesn't count until it posts again
        _roll();
        assertTrue(_genesisPrices());
        _post(2, 5_000, 5_000);
        _roll();
        assertEq(_tp(FA, 0), T[0][0] * 7_500 / BPS);
    }

    // ---------- Unit prices are the median of the posted tables ----------

    /// "One validator posts an absurd price": of 15, one at 100 × the others' token price. The median moves by at most
    /// one rank, and stays within the range of the other 14 validators' values.
    function test_oneAbsurdPrice() public {
        _activate(15);
        uint256[] memory honest = new uint256[](14);
        uint256[] memory all = new uint256[](15);
        for (uint256 i; i < 14; ++i) {
            uint256 bps = 9_300 + 100 * ((i * 5) % 14); // distinct, within ±7 %
            _post(i, bps, BPS);
            honest[i] = T[0][0] * bps / BPS;
            all[i] = honest[i];
        }
        _post(14, 1_000_000, BPS); // 100 ×
        all[14] = T[0][0] * 100;
        _roll();
        uint256 p = _tp(FA, 0);
        assertEq(p, _lowerMedian(all));
        uint256[] memory sorted = _sorted(honest);
        assertTrue(p == sorted[6] || p == sorted[7], "more than one rank");
        assertGe(p, sorted[0]);
        assertLe(p, sorted[13]);
    }

    /// "Three validators of one family inflate its price": among 24 counting validators, the three post 100 × its list
    /// price. The family's token price follows the median of all 24 tables, within the range of the other 21's.
    function test_threeValidatorsOfOneFamilyInflate() public {
        uint256[] memory others = new uint256[](21);
        for (uint256 i; i < 21; ++i) {
            _activateAs(i, i % 2 == 0 ? FB : FC);
            uint256 bps = 9_000 + 100 * i; // every family's list price as each sees it, ±10 %
            _post(i, bps, BPS);
            others[i] = bps;
        }
        for (uint256 i = 21; i < 24; ++i) {
            _activateAs(i, FA); // anthropic's validators, inflating anthropic's price
            bytes32[] memory fs = _fams();
            uint256[3][] memory toks = new uint256[3][](3);
            for (uint256 f; f < 3; ++f) {
                toks[f] = _tokens(f, f == 0 ? 1_000_000 : BPS);
            }
            _postRaw(i, _shared(BPS), fs, toks);
        }
        _roll();
        for (uint256 j; j < 3; ++j) {
            uint256[] memory all = new uint256[](24);
            for (uint256 i; i < 21; ++i) {
                all[i] = T[0][j] * others[i] / BPS;
            }
            for (uint256 i = 21; i < 24; ++i) {
                all[i] = T[0][j] * 100;
            }
            assertEq(_tp(FA, j), _lowerMedian(all));
            assertGe(_tp(FA, j), T[0][j] * 9_000 / BPS);
            assertLe(_tp(FA, j), T[0][j] * 11_000 / BPS);
        }
    }

    /// "An even count": the lower of the two middle values is the median.
    function test_evenCountTakesTheLowerMiddle() public {
        _activate(4);
        _post(0, 9_000, 9_000);
        _post(1, 9_500, 9_500);
        _post(2, 10_500, 10_500);
        _post(3, 11_000, 11_000);
        _roll();
        for (uint256 j; j < 4; ++j) {
            assertEq(_sp(j), S[j] * 9_500 / BPS);
        }
        for (uint256 f; f < 3; ++f) {
            for (uint256 j; j < 3; ++j) {
                assertEq(_tp(_fams()[f], j), T[f][j] * 9_500 / BPS);
                assertTrue(_tp(_fams()[f], j) != (T[f][j] * 9_500 / BPS + T[f][j] * 10_500 / BPS) / 2);
            }
        }
    }

    /// "A real price drop": every validator's token price falls by half; the unit price falls by the step each period
    /// until it reaches the new median (3 periods), then stays.
    function test_realPriceDrop() public {
        _activate(5);
        for (uint256 i; i < 5; ++i) {
            _post(i, 5_000, BPS);
        }
        uint256 expected = T[0][2];
        for (uint256 d; d < 3; ++d) {
            _roll();
            uint256 stepped = (expected * 7_500 + BPS - 1) / BPS; // down by 25 % of itself, rounded toward it
            expected = stepped > T[0][2] / 2 ? stepped : T[0][2] / 2;
            assertEq(_tp(FA, 2), expected);
            assertEq(_sp(0), S[0]); // the shared units didn't move
        }
        assertEq(expected, T[0][2] / 2);
        _roll();
        assertEq(_tp(FA, 2), T[0][2] / 2);
    }

    /// "Too few tables": fewer than MEDIAN_MIN_POSTERS posters of a unit leave its price as it is.
    function test_tooFewTables() public {
        _roll(); // none
        assertTrue(_genesisPrices());
        _activate(2);
        _post(0, 5_000, 5_000);
        _post(1, 5_000, 5_000);
        _roll();
        assertTrue(_genesisPrices());
    }

    /// PRICE_CAP_X: whatever the median, no price goes above twice its genesis value.
    function test_neverAboveTwiceGenesis() public {
        _activate(3);
        for (uint256 i; i < 3; ++i) {
            _post(i, 100_000, 100_000); // 10 ×
        }
        for (uint256 d; d < 6; ++d) {
            _roll();
        }
        for (uint256 j; j < 4; ++j) {
            assertEq(_sp(j), 2 * S[j]);
        }
        for (uint256 f; f < 3; ++f) {
            for (uint256 j; j < 3; ++j) {
                assertEq(_tp(_fams()[f], j), 2 * T[f][j]);
            }
        }
    }

    // ---------- Any model family can be priced, by the other validators (D19) ----------

    /// "A new provider's model": a validator registers with a family no one used; the other validators' nodes post its
    /// list price; it's priced at the end of that period, at the lower median. Until then it isn't priced (Panels
    /// draws none of its validators) and the meter refuses it; from the next period a table must price it to count.
    function test_aNewProvidersModel() public {
        vals.setFamily(_v(50), FD); // the new family's first validator: a candidate
        fees.announce(_v(50));
        assertFalse(fees.isPriced(FD));
        assertEq(fees.pendingFamilies().length, 1);
        fees.open(1);
        vm.expectRevert(abi.encodeWithSelector(FeesV3.Unpriced.selector, FD));
        fees.shadowCost(1, REPO, FD, _usage(1, 0, 1, 0, 0, 0));
        _activate(5);
        uint256[3] memory list = [uint256(3_000_000), 300_000, 15_000_000];
        for (uint256 i; i < 5; ++i) {
            uint256[3] memory seen;
            for (uint256 j; j < 3; ++j) {
                seen[j] = list[j] * (9_800 + 100 * i) / BPS; // 98 % to 102 % of its list price
            }
            _postWith(i, BPS, FD, seen);
        }
        _roll();
        assertTrue(fees.isPriced(FD));
        assertEq(fees.pricedFrom(FD), 1);
        assertEq(fees.pendingFamilies().length, 0);
        for (uint256 j; j < 3; ++j) {
            assertEq(_tp(FD, j), list[j] * 10_000 / BPS); // the lower median of five
            assertEq(fees.firstPrice(FD, j), _tp(FD, j));
        }
        // an attempt opened before it was priced still can't charge it; one opened after can
        vm.expectRevert(abi.encodeWithSelector(FeesV3.Unpriced.selector, FD));
        fees.shadowCost(1, REPO, FD, _usage(1, 0, 1, 0, 0, 0));
        fees.open(2);
        assertEq(fees.shadowCost(2, REPO, FD, _usage(100_000, 0, 0, 0, 0, 0)), list[0] / 10);
        // now tables must price it: five tables without it don't count
        for (uint256 i; i < 5; ++i) {
            _post(i, 5_000, 5_000);
        }
        _roll();
        assertTrue(_genesisPrices());
        for (uint256 i; i < 3; ++i) {
            _postWith(i, 5_000, FD, list);
        }
        _roll();
        assertEq(_tp(FA, 0), T[0][0] * 7_500 / BPS);
        fees.announce(_v(50)); // a priced family: announcing changes nothing
        assertEq(fees.pendingFamilies().length, 0);
    }

    /// "A new family's own validators set its price": only its own validators post a price for it, at 100 × its list
    /// price. It stays unpriced until enough validators of other families price it; then the median, with its own
    /// validators' values among them, is the others' price.
    function test_aNewFamilysOwnValidatorsSetItsPrice() public {
        uint256[3] memory list = [uint256(3_000_000), 300_000, 15_000_000];
        uint256[3] memory inflated = [list[0] * 100, list[1] * 100, list[2] * 100];
        for (uint256 i; i < 3; ++i) {
            _activateAs(10 + i, FD); // its own validators (active here only to show their tables can't price it)
            _postWith(10 + i, BPS, FD, inflated);
        }
        _activate(2);
        _postWith(0, BPS, FD, list);
        _postWith(1, BPS, FD, list);
        fees.announce(_v(10));
        _roll(); // 5 tables price it, but only 2 of other families
        assertFalse(fees.isPriced(FD));
        _activateAs(2, FC);
        _postWith(2, BPS, FD, list);
        _roll(); // 3 of other families
        assertTrue(fees.isPriced(FD));
        for (uint256 j; j < 3; ++j) {
            assertEq(_tp(FD, j), list[j]); // the lower median of 3 × list and 3 × 100 × list
        }
    }

    /// "An inflated first price": the median is 10 × the dearest priced family's token price; the first price is twice
    /// that (per token unit), and it moves by at most the step per period after that, never above twice its first.
    function test_anInflatedFirstPrice() public {
        uint256[3] memory top;
        for (uint256 j; j < 3; ++j) {
            for (uint256 f; f < 3; ++f) {
                if (T[f][j] > top[j]) top[j] = T[f][j];
            }
        }
        uint256[3] memory tenfold = [top[0] * 10, top[1] * 10, top[2] * 10];
        _activate(3);
        vals.setFamily(_v(50), FD);
        fees.announce(_v(50));
        for (uint256 i; i < 3; ++i) {
            _postWith(i, BPS, FD, tenfold);
        }
        _roll();
        for (uint256 j; j < 3; ++j) {
            assertEq(_tp(FD, j), 2 * top[j]);
            assertEq(fees.firstPrice(FD, j), 2 * top[j]);
        }
        _roll();
        for (uint256 j; j < 3; ++j) {
            assertEq(_tp(FD, j), 2 * top[j] * 12_500 / BPS); // one step
        }
        for (uint256 d; d < 5; ++d) {
            _roll();
        }
        for (uint256 j; j < 3; ++j) {
            assertEq(_tp(FD, j), 4 * top[j]); // twice its first price
        }
    }

    /// Announcing needs a registered key; a family nobody prices leaves the queue after PENDING_PERIODS periods, and
    /// anyone may announce it again.
    function test_announcedFamilyWaitsThenLeavesTheQueue() public {
        vm.expectRevert(FeesV3.NotRegistered.selector);
        fees.announce(_v(77));
        vals.setFamily(_v(50), FD);
        fees.announce(_v(50));
        fees.announce(_v(50)); // already waiting: nothing changes
        assertEq(fees.pendingFamilies().length, 1);
        for (uint256 d; d < fees.PENDING_PERIODS() - 1; ++d) {
            _roll();
            assertEq(fees.pendingFamilies().length, 1);
        }
        _roll();
        assertEq(fees.pendingFamilies().length, 0);
        assertFalse(fees.isPriced(FD));
        fees.announce(_v(50));
        assertEq(fees.pendingFamilies().length, 1);
    }

    // ---------- The service fee ----------

    /// "A new version": the service fee is the ceiling until the queue rules move it.
    function test_newVersionStartsAtTheCeiling() public {
        assertEq(fees.serviceFee(), fees.FEE_CEILING());
        vals.setActiveCount(10);
        _period(1, 20, 2, 10); // a shortage can't take it above the ceiling
        assertEq(fees.serviceFee(), fees.FEE_CEILING());
        _period(100, 20, 0, 10); // no wait, nobody idle: it stays
        assertEq(fees.serviceFee(), fees.FEE_CEILING());
    }

    /// "Not enough validators": more than WAIT_HIGH of a period's submissions waited, so the fee rises one step.
    function test_notEnoughValidatorsRaisesTheFee() public {
        vals.setActiveCount(10);
        _period(1, 0, 0, 0); // idle: 250,000 → 237,500
        assertEq(fees.serviceFee(), 237_500);
        _period(100, 20, 1, 10); // exactly 5 % waited: no rise
        assertEq(fees.serviceFee(), 237_500);
        _period(200, 20, 2, 10); // 10 %
        assertEq(fees.serviceFee(), 249_375);
        _period(300, 20, 2, 0); // the wait rule first, whatever the idle share; then the ceiling
        assertEq(fees.serviceFee(), 250_000);
    }

    /// "Too many idle validators": no wait and more than IDLE_HIGH (40 %) not drawn: one step down, to the floor at
    /// most.
    function test_tooManyIdleValidatorsLowerTheFee() public {
        vals.setActiveCount(10);
        _period(1, 10, 0, 6); // exactly 40 % idle: no fall
        assertEq(fees.serviceFee(), 250_000);
        _period(100, 10, 0, 5); // 50 %
        assertEq(fees.serviceFee(), 237_500);
        uint256 last = fees.serviceFee();
        for (uint256 d; d < 100; ++d) {
            _period(1_000 + d, 0, 0, 0);
            uint256 f = fees.serviceFee();
            assertGe(f, fees.FEE_FLOOR());
            assertTrue(f == fees.FEE_FLOOR() || f == last * 9_500 / BPS);
            last = f;
        }
        assertEq(fees.serviceFee(), fees.FEE_FLOOR());
    }

    /// The same validator drawn twice in a period counts once; replacements count; it counts again the next period.
    function test_drawnCountsEachValidatorOncePerPeriod() public {
        address[] memory js = new address[](4);
        (js[0], js[1], js[2], js[3]) = (_v(0), _v(1), _v(0), _v(2));
        fees.drawn(js);
        fees.drawn(js);
        assertEq(fees.period(0).drawn, 3);
        _roll();
        fees.drawn(js);
        assertEq(fees.period(1).drawn, 3);
    }

    // ---------- Every wait counts toward the fee's rise ----------

    /// "A big bounty waits for large bonds" and "A small bounty waits for anyone": a wait counts whatever its bounty
    /// and whatever kept it from being drawn (the meter isn't told either), and two of 20 raise the fee.
    function test_everyWaitCountsWhateverItsBounty() public {
        vals.setActiveCount(10);
        _period(1, 0, 0, 0);
        uint256 before = fees.serviceFee();
        for (uint256 i; i < 20; ++i) {
            fees.open(100 + i);
        }
        fees.waited(100); // a $500 bounty: no validator with a $1,250 bond free
        fees.waited(101); // a $40 bounty: no validator eligible
        assertEq(fees.period(1).waited, 2);
        _roll();
        assertEq(fees.serviceFee(), before * 10_500 / BPS);
    }

    /// "A long wait": a submission waiting across three periods counts once, in the period it started waiting.
    function test_longWaitCountsOnce() public {
        fees.open(1);
        fees.waited(1);
        _roll();
        fees.waited(1);
        _roll();
        fees.waited(1);
        assertEq(fees.period(0).waited, 1);
        assertEq(fees.period(1).waited, 0);
        assertEq(fees.period(2).waited, 0);
    }

    /// "A panel stalls": a counted judge silent and no eligible validator left to replace it: the submission counts as
    /// having waited, once.
    function test_stalledPanelCountsOnce() public {
        fees.open(1);
        fees.stalled(1);
        fees.stalled(1);
        assertEq(fees.period(0).waited, 1);
        _roll();
        fees.stalled(1);
        assertEq(fees.period(1).waited, 0);
    }

    // ---------- No account or vote sets a price ----------

    /// "A cartel proposes higher fees": there's nothing to propose or vote on. The meter's only state-changing calls
    /// are the race's hooks, `post` (unit costs only: no entry for the service fee), `announce` and `roll` (anyone, by
    /// the rules); no owner, admin or setter. Refusing work is the draw's business (Panels, Validators).
    function test_noProposalVoteOrSetter() public view {
        string memory json = vm.readFile("out/FeesV3.sol/FeesV3.json");
        string[10] memory writers =
            ["bind", "open", "waited", "stalled", "drawn", "settle", "post", "announce", "roll", "rollPart"];
        uint256 n;
        for (uint256 i;; ++i) {
            string memory key = string.concat(".abi[", vm.toString(i), "]");
            if (!vm.keyExistsJson(json, key)) break;
            if (keccak256(bytes(vm.parseJsonString(json, string.concat(key, ".type")))) != keccak256("function")) {
                continue;
            }
            bytes32 mut = keccak256(bytes(vm.parseJsonString(json, string.concat(key, ".stateMutability"))));
            if (mut == keccak256("view") || mut == keccak256("pure")) continue;
            string memory name = vm.parseJsonString(json, string.concat(key, ".name"));
            bool ok;
            for (uint256 j; j < writers.length && !ok; ++j) {
                ok = keccak256(bytes(name)) == keccak256(bytes(writers[j]));
            }
            assertTrue(ok, string.concat("unexpected state-changing function: ", name));
            ++n;
        }
        assertEq(n, writers.length);
    }

    /// The race's hooks are the race's alone, and it binds once; a period closes only once it has ended, one a call.
    function test_hooksAreTheRacesAndRollWaits() public {
        address other = makeAddr("other");
        vm.startPrank(other);
        vm.expectRevert(FeesV3.AlreadyBound.selector);
        fees.bind();
        vm.expectRevert(FeesV3.NotRace.selector);
        fees.open(1);
        vm.expectRevert(FeesV3.NotRace.selector);
        fees.waited(1);
        vm.expectRevert(FeesV3.NotRace.selector);
        fees.stalled(1);
        vm.expectRevert(FeesV3.NotRace.selector);
        fees.drawn(new address[](0));
        vm.expectRevert(FeesV3.NotRace.selector);
        fees.settle(1, REPO, new IFeesV3.Report[](0), other, 0);
        vm.stopPrank();
        vm.expectRevert(FeesV3.TooEarly.selector);
        fees.roll();
        vm.warp(block.timestamp + 3 days);
        fees.roll();
        fees.roll();
        fees.roll();
        assertEq(fees.rolled(), 3);
        vm.expectRevert(FeesV3.TooEarly.selector);
        fees.roll();
        fees.open(1);
        vm.expectRevert(FeesV3.AlreadyOpen.selector);
        fees.open(1);
        vm.expectRevert(FeesV3.NotOpen.selector);
        fees.settle(2, REPO, new IFeesV3.Report[](0), other, 0);
        fees.settle(1, REPO, new IFeesV3.Report[](0), other, 0);
        vm.expectRevert(FeesV3.AlreadySettled.selector);
        fees.settle(1, REPO, new IFeesV3.Report[](0), other, 0);
    }

    // ---------- An attempt is charged the prices it was quoted ----------

    /// "Prices change during a check": the fee rises and the unit prices fall at the end of a period while an attempt
    /// is being judged; it is charged the fee and prices it was quoted. A later attempt pays the new ones.
    function test_attemptChargedItsQuote() public {
        vals.setActiveCount(10);
        _period(1, 0, 0, 0); // the fee below the ceiling: 237,500
        uint256[4] memory quotedShared = fees.sharedPrices();
        uint256[3] memory quotedTokens = fees.tokenPrices(FA);
        uint256 quotedFee = fees.serviceFee();
        fees.open(7); // the attempt starts
        _activate(3);
        for (uint256 i; i < 3; ++i) {
            _post(i, 5_000, 5_000);
        }
        _period(100, 20, 2, 10); // a shortage, and lower posted costs
        assertEq(fees.serviceFee(), quotedFee * 10_500 / BPS);
        assertLt(_tp(FA, 0), quotedTokens[0]);
        fees.open(8); // a later attempt
        IFeesV3.Usage memory u = _usage(100_000, 20_000, 8_000, 600, 1_200, 5);
        IFeesV3.Report[] memory rs = new IFeesV3.Report[](1);
        rs[0] = _report(_v(0), FA, u); // neutral family: 1 ×
        (, uint256[] memory micro) = fees.settle(7, REPO, rs, address(0), 0);
        assertEq(micro[0], _usageCost(quotedShared, quotedTokens, u) + quotedFee);
        assertEq(fees.epochOf(7), 1);
        (, micro) = fees.settle(8, REPO, rs, address(0), 0);
        assertEq(micro[0], _usageCost(fees.sharedPrices(), fees.tokenPrices(FA), u) + fees.serviceFee());
        assertEq(fees.depositFor(8, REPO, 1), fees.maxDeposit(REPO, 1));
        assertEq(fees.depositFor(9, REPO, 1), fees.maxDeposit(REPO, 1)); // not open yet: the prices in force
        assertTrue(fees.depositFor(7, REPO, 1) != fees.maxDeposit(REPO, 1)); // its own epoch's
    }

    // ---------- The formula: v2's, with the score factor on the service fee ----------

    /// v2's median rule carries over: one padder among three changes nothing; each judge's tokens at its own family's
    /// prices; the relayer's gas within the allowance at the ETH price.
    function test_padderChangesNothingAndTokensAtOwnFamily() public {
        fees.open(1);
        IFeesV3.Usage memory honest = _usage(100_000, 20_000, 8_000, 600, 1_200, 5);
        IFeesV3.Report[] memory rs = new IFeesV3.Report[](3);
        rs[0] = _report(_v(0), FA, honest);
        rs[1] = _report(_v(1), FB, _usage(140_000, 0, 16_000, 2_400, 4_800, 20)); // pads to the caps
        rs[2] = _report(_v(2), FC, honest);
        vm.txGasPrice(2 gwei); // above the cap: counted at MAX_GAS_PRICE
        (address[] memory to, uint256[] memory micro) = fees.settle(1, REPO, rs, address(this), 2_000_000);
        for (uint256 k; k < 3; ++k) {
            assertEq(to[k], _v(k));
            assertEq(micro[k], _usageCost(S, T[k], honest) + fees.FEE_CEILING());
        }
        assertEq(to[3], address(this));
        assertEq(micro[3], uint256(GAS_ALLOWANCE) * MAX_GAS_PRICE * S[3] / 1e18);
    }

    /// "A better model earns more" (judge-scores): factors 1.5 × and 0.8 × after normalisation; each judge gets its
    /// metered usage in full, and 1.5 × and 0.8 × the market service fee.
    function test_betterModelEarnsMore() public {
        sc.set(FA, IFeesV3Scores.ScoreState.Scored, 0.9e18); // raw 0.5 + 0.2 / 0.3 × 1.5 = 1.5
        sc.set(FB, IFeesV3Scores.ScoreState.Scored, 0.76e18); // raw 0.5 + 0.06 / 0.3 × 1.5 = 0.8
        assertEq(fees.factorOf(FA), 1.5e18);
        assertEq(fees.factorOf(FB), 0.8e18);
        fees.open(1);
        IFeesV3.Usage memory u = _usage(100_000, 20_000, 8_000, 600, 1_200, 5);
        IFeesV3.Report[] memory rs = new IFeesV3.Report[](2);
        rs[0] = _report(_v(0), FA, u);
        rs[1] = _report(_v(1), FB, u);
        (, uint256[] memory micro) = fees.settle(1, REPO, rs, address(0), 0);
        uint256 fee = fees.FEE_CEILING();
        assertEq(micro[0], _usageCost(S, T[0], u) + fee * 15 / 10);
        assertEq(micro[1], _usageCost(S, T[1], u) + fee * 8 / 10);
    }

    /// "Scores don't raise the price of a check" (judge-scores): the factors are normalised by the previous period's
    /// counted seats, so over a period with the same seats they average 1 ×.
    function test_scoresDontRaiseThePriceOfACheck() public {
        sc.set(FA, IFeesV3Scores.ScoreState.Scored, 0.9e18); // raw 1.5
        sc.set(FB, IFeesV3Scores.ScoreState.Scored, 0.94e18); // raw 1.7
        sc.set(FC, IFeesV3Scores.ScoreState.Scored, 0.76e18); // raw 0.8
        IFeesV3.Usage memory none;
        IFeesV3.Report[] memory rs = new IFeesV3.Report[](3);
        (rs[0], rs[1], rs[2]) = (_report(_v(0), FA, none), _report(_v(1), FB, none), _report(_v(2), FC, none));
        fees.open(1);
        fees.settle(1, REPO, rs, address(0), 0); // period 0: the seats' raw factors average 4/3
        assertEq(fees.period(0).seats, 3);
        _roll();
        assertEq(fees.norm(), uint256(4e18) / 3);
        fees.open(2);
        (, uint256[] memory micro) = fees.settle(2, REPO, rs, address(0), 0);
        uint256 fee = fees.serviceFee();
        assertApproxEqAbs(micro[0] + micro[1] + micro[2], 3 * fee, 3); // 1.125 ×, 1.275 ×, 0.6 ×: 1 × on average
    }

    /// A new family is paid the neutral 1 ×; a recovering one SCORE_FACTOR_MIN; a score below SCORE_MIN the minimum;
    /// no factor goes above SCORE_FACTOR_MAX; a period with no scored seat keeps the normaliser.
    function test_neutralRecoveringAndBounds() public {
        sc.set(FA, IFeesV3Scores.ScoreState.Neutral, 0);
        sc.set(FB, IFeesV3Scores.ScoreState.Recovering, 0.99e18);
        sc.set(FC, IFeesV3Scores.ScoreState.Barred, 0.5e18);
        assertEq(fees.factorOf(FA), WAD);
        assertEq(fees.factorOf(FB), 0.5e18);
        assertEq(fees.factorOf(FC), 0.5e18);
        sc.set(FC, IFeesV3Scores.ScoreState.Scored, 1e18);
        assertEq(fees.factorOf(FC), 2e18);
        assertEq(fees.rawFactor(0.7e18), 0.5e18);
        assertEq(fees.rawFactor(0.8e18), 1e18);
        sc.set(FC, IFeesV3Scores.ScoreState.Scored, 0.6e18);
        IFeesV3.Usage memory none;
        IFeesV3.Report[] memory rs = new IFeesV3.Report[](2);
        (rs[0], rs[1]) = (_report(_v(0), FA, none), _report(_v(2), FC, none));
        fees.open(1);
        fees.settle(1, REPO, rs, address(0), 0);
        assertEq(fees.period(0).seats, 1); // the neutral seat isn't a scored one
        _roll();
        assertEq(fees.norm(), 0.5e18);
        sc.set(FC, IFeesV3Scores.ScoreState.Scored, 0.9e18);
        assertEq(fees.factorOf(FC), 2e18); // 1.5 / 0.5 = 3, bounded
        _roll(); // no scored seat: the normaliser carries over
        assertEq(fees.norm(), 0.5e18);
    }

    /// CI_SINGLE_RUN: one attested run is paid, at its own measurement.
    function test_singleRun() public {
        FeesV3 m = _deploy(true);
        m.bind();
        m.open(1);
        IFeesV3.Usage memory ran = _usage(100_000, 0, 8_000, 600, 1_200, 5);
        IFeesV3.Usage memory skipped = _usage(100_000, 0, 8_000, 0, 0, 5);
        IFeesV3.Report[] memory rs = new IFeesV3.Report[](2);
        (rs[0], rs[1]) = (_report(_v(0), FA, skipped), _report(_v(1), FA, ran));
        (, uint256[] memory micro) = m.settle(1, REPO, rs, address(0), 0);
        assertEq(micro[1] - micro[0], (600 * S[0] + 1_200 * S[1]) / 1e6);
    }

    /// A shadow's usage at the attempt's prices, capped, with no service fee; an unpriced family is refused.
    function test_shadowCostIsUsageOnly() public {
        fees.open(1);
        IFeesV3.Usage memory u = _usage(200_000, 0, 8_000, 600, 1_200, 5); // input above the cap
        IFeesV3.Usage memory capped = _usage(CAP_IN, 0, 8_000, 600, 1_200, 5);
        assertEq(fees.shadowCost(1, REPO, FB, u), _usageCost(S, T[1], capped));
        vm.expectRevert(abi.encodeWithSelector(FeesV3.Unpriced.selector, FD));
        fees.shadowCost(1, REPO, FD, u);
        IFeesV3.Report[] memory rs = new IFeesV3.Report[](1);
        rs[0] = _report(_v(0), FD, u);
        vm.expectRevert(abi.encodeWithSelector(FeesV3.Unpriced.selector, FD));
        fees.settle(1, REPO, rs, address(0), 0);
    }

    /// The deposit covers every settlement: any usage, any k up to K_MAX, any scores, the gas at its cap.
    function testFuzz_settlementWithinDeposit(uint256 seed, uint8 kRaw) public {
        uint256 k = 1 + uint256(kRaw) % 7;
        vm.txGasPrice(MAX_GAS_PRICE * 3);
        fees.open(1);
        IFeesV3.Report[] memory rs = new IFeesV3.Report[](k);
        bytes32[3] memory fs = [FA, FB, FC];
        for (uint256 i; i < k; ++i) {
            uint256 r = uint256(keccak256(abi.encode(seed, i)));
            IFeesV3.Usage memory u = _usage(
                uint64(r), uint64(r >> 64), uint64(r >> 128), uint64(r >> 192), uint64(r >> 32), uint64(r >> 96)
            );
            bytes32 f = fs[r % 3];
            sc.set(f, IFeesV3Scores.ScoreState((r >> 8) % 4), (r >> 16) % (WAD + 1));
            rs[i] = _report(_v(i), f, u);
        }
        (, uint256[] memory micro) = fees.settle(1, REPO, rs, address(0), type(uint64).max);
        uint256 total;
        for (uint256 i; i < micro.length; ++i) {
            total += micro[i];
        }
        assertLe(total, fees.depositFor(1, REPO, k));
    }

    // ---------- The step bound, fuzzed ----------

    /// No sequence of posts moves a price by more than PRICE_STEP_MAX per period, or above PRICE_CAP_X × its first
    /// value, and no new family starts above PRICE_CAP_X × the dearest priced family: eight validators of five
    /// families (two of them new) going active and inactive, posting tables with missing units and families, zeros,
    /// ones, huge values and anything between, for twelve periods.
    function testFuzz_noPostsMoveAPriceMoreThanTheStep(uint256 seed) public {
        bytes32[5] memory all = [FA, FB, FC, FD, FE];
        vals.setFamily(_v(100), FD);
        vals.setFamily(_v(101), FE);
        for (uint256 v; v < 8; ++v) {
            vals.setFamily(_v(v), all[v % 5]);
        }
        uint256 step = fees.PRICE_STEP_MAX_BPS();
        for (uint256 d; d < 12; ++d) {
            fees.announce(_v(100));
            fees.announce(_v(101));
            for (uint256 v; v < 8; ++v) {
                uint256 r = uint256(keccak256(abi.encode(seed, d, v)));
                if (r % 4 == 0) vals.setActive(_v(v), !vals.active(_v(v)));
                if (!vals.active(_v(v)) || r % 3 == 0) continue;
                _postRandom(v, r);
            }
            uint256[4] memory sh = fees.sharedPrices();
            uint256[3][5] memory before;
            bool[5] memory was;
            uint256[3] memory top;
            for (uint256 f; f < 5; ++f) {
                was[f] = fees.isPriced(all[f]);
                if (!was[f]) continue;
                before[f] = fees.tokenPrices(all[f]);
                for (uint256 j; j < 3; ++j) {
                    if (before[f][j] > top[j]) top[j] = before[f][j];
                }
            }
            _roll();
            for (uint256 j; j < 4; ++j) {
                _assertStep(sh[j], fees.sharedPrices()[j], fees.firstPrice(0, j), step);
            }
            for (uint256 f; f < 5; ++f) {
                if (!fees.isPriced(all[f])) continue;
                uint256[3] memory next = fees.tokenPrices(all[f]);
                for (uint256 j; j < 3; ++j) {
                    if (was[f]) {
                        _assertStep(before[f][j], next[j], fees.firstPrice(all[f], j), step);
                    } else {
                        assertLe(next[j], 2 * top[j], "a first price above twice the dearest family");
                        assertGt(next[j], 0);
                    }
                }
            }
        }
    }

    function _assertStep(uint256 old, uint256 next, uint256 first, uint256 step) internal pure {
        uint256 moved = next > old ? next - old : old - next;
        assertLe(moved * BPS, old * step, "moved more than the step");
        assertLe(next, 2 * first, "above the cap");
        assertGt(next, 0);
    }

    function _postRandom(uint256 v, uint256 r) internal {
        bytes32[5] memory all = [FA, FB, FC, FD, FE];
        uint256[4] memory sh;
        for (uint256 j; j < 4; ++j) {
            sh[j] = _randomValue(uint256(keccak256(abi.encode(r, "s", j))), S[j]);
        }
        bytes32[] memory fs = new bytes32[](5);
        uint256[3][] memory toks = new uint256[3][](5);
        uint256 n;
        for (uint256 f; f < 5; ++f) {
            uint256 x = uint256(keccak256(abi.encode(r, "f", f)));
            if (x % 7 == 0) continue; // a family left out
            fs[n] = all[f];
            for (uint256 j; j < 3; ++j) {
                toks[n][j] = _randomValue(uint256(keccak256(abi.encode(x, j))), T[f < 3 ? f : 0][j]);
            }
            ++n;
        }
        assembly ("memory-safe") {
            mstore(fs, n)
            mstore(toks, n)
        }
        _postRaw(v, sh, fs, toks);
    }

    function _randomValue(uint256 x, uint256 ref) internal pure returns (uint256) {
        uint256 mode = x % 6;
        if (mode == 0) return x % 50 == 0 ? 0 : 1;
        if (mode == 1) return x >> 8;
        if (mode == 2) return type(uint256).max;
        return 1 + ref * ((x >> 8) % 1_000) / 100; // 0 to 10 ×
    }

    // ---------- Gas ----------

    /// `roll` and `post` with a few dozen posters and families: 36 active validators posting the shared units and 16
    /// families' tokens (12 priced, 4 new families announced and priced in this roll).
    function test_rollGasWithDozensOfPostersAndFamilies() public {
        uint256 priced = 12;
        uint256 fresh = 4;
        FeesV3.Genesis memory g;
        g.coin = usd;
        g.shared = S;
        g.families = new bytes32[](priced);
        g.tokens = new uint256[3][](priced);
        for (uint256 f; f < priced; ++f) {
            g.families[f] = bytes32(f + 1);
            g.tokens[f] = T[f % 3];
        }
        g.caps = IFeesV3.Caps(CAP_IN, CAP_OUT, CAP_MB, GAS_ALLOWANCE, GAS_OVERHEAD, MAX_GAS_PRICE);
        g.repo = REPO;
        g.profile = _profile();
        FeesV3 m = new FeesV3(vals, sc, g);
        for (uint256 f; f < fresh; ++f) {
            vals.setFamily(_v(200 + f), bytes32(priced + f + 1));
            m.announce(_v(200 + f));
        }
        bytes32[] memory fs = new bytes32[](priced + fresh);
        for (uint256 f; f < priced + fresh; ++f) {
            fs[f] = bytes32(f + 1);
        }
        uint256 postGas;
        uint256 repostGas;
        for (uint256 i; i < 36; ++i) {
            _activateAs(i, bytes32((i % priced) + 1));
            uint256[3][] memory toks = new uint256[3][](priced + fresh);
            for (uint256 f; f < priced + fresh; ++f) {
                toks[f] = _tokens(f % 3, 9_000 + 50 * i);
            }
            vm.prank(_v(i));
            uint256 g0 = gasleft();
            m.post(_shared(9_000 + 50 * i), fs, toks);
            postGas = g0 - gasleft();
            for (uint256 f; f < priced + fresh; ++f) {
                toks[f] = _tokens(f % 3, 9_100 + 50 * i);
            }
            vm.prank(_v(i));
            g0 = gasleft();
            m.post(_shared(9_100 + 50 * i), fs, toks);
            repostGas = g0 - gasleft();
        }
        vm.warp(m.start() + 1 days);
        uint256 g1 = gasleft();
        m.roll();
        uint256 rollGas = g1 - gasleft();
        assertEq(m.pricedFamilies().length, priced + fresh);
        vm.warp(m.start() + 2 days);
        g1 = gasleft();
        m.roll();
        uint256 roll2Gas = g1 - gasleft();
        console.log("post, first (16 families):", postGas);
        console.log("post, again (16 families):", repostGas);
        console.log("roll, 36 posters, 12 priced + 4 new families:", rollGas);
        console.log("roll, 36 posters, 16 priced families:", roll2Gas);
        assertLt(rollGas, 15_000_000);
        assertLt(roll2Gas, 15_000_000);
    }

    /// Task 3.5: `roll` in bounded parts. At #222's size (36 posters, 12 priced families and 4 new ones, then 16 priced),
    /// each `rollPart` stays under ROLL_PART_GAS (1.5M), a period closes after its last part, and while it's under way
    /// a post or an announcement waits. The parts give the same prices as `roll` in one call on a twin meter.
    function test_rollPartsAreBounded() public {
        (FeesV3 a, bytes32[] memory fs) = _dozens();
        (FeesV3 b,) = _dozens();
        uint256 most;
        uint256 parts;
        for (uint256 day = 1; day <= 2; ++day) {
            vm.warp(a.start() + day * 1 days);
            b.roll();
            uint256 before = a.rolled();
            while (a.rolled() == before) {
                uint256 g = gasleft();
                a.rollPart();
                g -= gasleft();
                if (g > most) most = g;
                ++parts;
                if (a.rolled() == before) {
                    vm.prank(_v(0));
                    vm.expectRevert(FeesV3.RollInProgress.selector);
                    a.post(_shared(1), fs, new uint256[3][](0));
                    vm.expectRevert(FeesV3.RollInProgress.selector);
                    a.announce(_v(0));
                }
            }
            assertEq(a.rollPhase(), 0);
        }
        console.log("roll parts for two periods:", parts);
        console.log("the largest part's gas:", most);
        assertLt(most, a.ROLL_PART_GAS());
        assertGt(parts, 4);
        assertEq(a.pricedFamilies().length, 16);
        assertEq(a.serviceFee(), b.serviceFee());
        assertEq(keccak256(abi.encode(a.sharedPrices())), keccak256(abi.encode(b.sharedPrices())));
        for (uint256 f; f < fs.length; ++f) {
            assertEq(keccak256(abi.encode(a.tokenPrices(fs[f]))), keccak256(abi.encode(b.tokenPrices(fs[f]))));
            assertEq(a.firstPrice(fs[f], 0), b.firstPrice(fs[f], 0));
        }
    }

    /// #222's benchmark: 36 active validators posting the shared units and 16 families' tokens (12 priced at genesis, 4
    /// announced), each having posted twice.
    function _dozens() internal returns (FeesV3 m, bytes32[] memory fs) {
        uint256 priced = 12;
        uint256 fresh = 4;
        FeesV3.Genesis memory g;
        g.coin = usd;
        g.shared = S;
        g.families = new bytes32[](priced);
        g.tokens = new uint256[3][](priced);
        for (uint256 f; f < priced; ++f) {
            g.families[f] = bytes32(f + 1);
            g.tokens[f] = T[f % 3];
        }
        g.caps = IFeesV3.Caps(CAP_IN, CAP_OUT, CAP_MB, GAS_ALLOWANCE, GAS_OVERHEAD, MAX_GAS_PRICE);
        g.repo = REPO;
        g.profile = _profile();
        m = new FeesV3(vals, sc, g);
        for (uint256 f; f < fresh; ++f) {
            vals.setFamily(_v(200 + f), bytes32(priced + f + 1));
            m.announce(_v(200 + f));
        }
        fs = new bytes32[](priced + fresh);
        for (uint256 f; f < priced + fresh; ++f) {
            fs[f] = bytes32(f + 1);
        }
        for (uint256 i; i < 36; ++i) {
            _activateAs(i, bytes32((i % priced) + 1));
            uint256[3][] memory toks = new uint256[3][](priced + fresh);
            for (uint256 f; f < priced + fresh; ++f) {
                toks[f] = _tokens(f % 3, 9_100 + 50 * i);
            }
            vm.prank(_v(i));
            m.post(_shared(9_100 + 50 * i), fs, toks);
        }
    }
}
