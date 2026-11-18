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

/// Random races on RaceV3 (task 3.5; v2's RaceV2Invariant in v3's terms): every step a reporter, funder, solver,
/// challenger, judge or keeper could take, in any order, with days passing and periods rolling. Panels' verdicts are
/// scripted (ReplayPanels: any k from 1 to K_MAX, passes and fails, reversals before finality, audits, finality), so
/// the runs reach the race's money paths quickly; RaceV3, its annex, FeesV3 and the pool are the real contracts.
/// Payouts that should always go through (settle, instalments, refunds of a final bounty, a final deposit's return)
/// are counted when they revert.
contract RaceV3Handler is Test {
    uint256 constant SECP_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141;
    bytes32 constant USAGE_TAG = keccak256("proof-of-fix v3 usage");

    RaceV3 public rc;
    ReplayPanels public pn;
    FeesV3 public fees;
    MockCoin public usd;
    address[] public actors;
    address[] public keys;
    mapping(address => uint256) internal secretOf;
    uint256 public issues;
    uint256 public subs; // the race's check ids run from 1 to this
    uint256 public stuck;
    string public lastStuck;
    // how deep the runs go
    uint256 public results;
    uint256 public claims;
    uint256 public clawbacks;
    uint256 public paidSettles;
    uint256 public refunds;
    uint256 public finished;
    uint256 public overCharged; // a result that took more than the deposit had

    constructor(RaceV3 rc_, ReplayPanels pn_, FeesV3 fees_, MockCoin usd_, ReplayRegistry reg) {
        rc = rc_;
        pn = pn_;
        fees = fees_;
        usd = usd_;
        for (uint256 i; i < 5; ++i) {
            address a = address(uint160(0xC000 + i));
            actors.push(a);
            usd.mint(a, 1e15);
            vm.prank(a);
            usd.approve(address(rc), type(uint256).max);
        }
        address[] memory act = new address[](9);
        for (uint256 i; i < 9; ++i) {
            uint256 sk = uint256(keccak256(abi.encode("invariant judge", i))) % SECP_N;
            address a = vm.addr(sk);
            secretOf[a] = sk;
            keys.push(a);
            act[i] = a;
            reg.setFamily(a, keccak256(bytes(i % 2 == 0 ? "anthropic" : "openai")));
        }
        reg.setActive(act);
    }

    function _actor(uint256 seed) internal view returns (address) {
        return actors[seed % actors.length];
    }

    function _bounties() internal view returns (uint256) {
        uint256 n;
        for (uint256 i = 1; i <= issues; ++i) {
            if (rc.issue(i).bounty != 0) ++n;
        }
        return n;
    }

    /// A bounty id among those opened, from a seed (0 if none).
    function _bounty(uint256 seed) internal view returns (uint256 b) {
        uint256 n = _bounties();
        return n == 0 ? 0 : 1 + seed % n;
    }

    /// A check from a seed, searching on for one `ok` accepts (0 if none).
    function _sub(uint256 seed, uint8 want) internal view returns (uint256) {
        for (uint256 j; j < subs; ++j) {
            uint256 id = 1 + (seed % subs + j) % subs;
            RaceV3Base.Submission memory s = rc.submission(id);
            Status st = pn.submission(id).status;
            bool ok = want == 0 ? (s.solver != address(0) && !s.paid && s.outcome == RaceV3Base.Outcome.None
                && st == Status.Sealed)
                : want == 1 ? (s.paid && st == Status.Window)
                : (s.paid && !s.done && st == Status.Final && block.timestamp > pn.submission(id).finalAt + 1 days);
            if (ok) return id;
        }
        return 0;
    }

    /// A bounty from a seed in state `st`, searching on (0 if none).
    function _bountyIn(uint256 seed, RaceV3Base.State st) internal view returns (uint256) {
        uint256 n = _bounties();
        for (uint256 j; j < n; ++j) {
            uint256 b = 1 + (seed % n + j) % n;
            if (rc.bounty(b).state == st) return b;
        }
        return 0;
    }

    function _fix(uint256 id) internal pure returns (bytes32) {
        return keccak256(abi.encode("fix", id));
    }

    // ---------- the parties ----------

    function register(uint256 seed, bool pass) external {
        vm.prank(_actor(seed));
        uint256 i = rc.register(bytes32(0), false);
        ++issues;
        uint256 check = rc.issue(i).check;
        subs = check;
        pn.setStatus(check, Status.Final, pass, 0);
        rc.openBounty(i);
    }

    function pledge(uint256 seed, uint256 amount) external {
        uint256 b = _bounty(seed);
        if (b == 0 || rc.bounty(b).state != RaceV3Base.State.Open) return;
        vm.prank(_actor(seed >> 8));
        rc.pledge(b, bound(amount, 1, 200e6));
    }

    function attempt(uint256 seed) external {
        uint256 b = _bounty(seed);
        if (b == 0 || rc.bounty(b).state != RaceV3Base.State.Open) return;
        vm.prank(_actor(seed >> 8));
        rc.attempt(b);
    }

    function commit(uint256 seed) external {
        uint256 b = _bounty(seed);
        if (b == 0) return;
        RaceV3Base.State st = rc.bounty(b).state;
        if (st != RaceV3Base.State.Open && st != RaceV3Base.State.Won && st != RaceV3Base.State.Merged) return;
        address who = _actor(seed >> 8);
        uint256 next = subs + 1;
        vm.prank(who);
        uint256 id = rc.commit(b, keccak256(abi.encode(_fix(next), bytes32(0), bytes32("salt"), who)));
        if (id != 0) subs = id;
    }

    /// Panels counts a verdict: k judges (1 to 7) report and the result is posted.
    function judge(uint256 seed, bool pass) external {
        uint256 id = _sub(seed, 0);
        if (id == 0) return;
        RaceV3Base.Submission memory s = rc.submission(id);
        uint256 k = 1 + 2 * ((seed >> 8) % 4);
        uint256 pid = _panel(id, Kind.Counted, k, seed >> 16);
        pn.setStatus(id, Status.Window, pass, pid);
        uint256 deposit = s.deposit;
        rc.result(id);
        if (rc.submission(id).charged > deposit) ++overCharged;
        ++results;
    }

    /// A counted verdict reversed by an auditor's challenge, before its finality: the challenge panel is paid and the
    /// race follows.
    function reverse(uint256 seed) external {
        uint256 id = _sub(seed, 1);
        if (id == 0) return;
        RaceV3Base.Submission memory s = rc.submission(id);
        bool wasPass = pn.submission(id).pass;
        uint256 cpid = _panel(id, Kind.Challenge, 3, seed >> 8);
        pn.setStatus(id, Status.Window, !wasPass, pn.submission(id).pid);
        uint256 ep = s.bounty == 0 ? 0 : rc.bounty(s.bounty).epoch;
        rc.payPanel(cpid);
        if (wasPass && s.bounty != 0 && ep != 0 && rc.award(s.bounty, ep).closed) ++clawbacks;
    }

    function audit(uint256 seed) external {
        if (subs == 0) return;
        uint256 id = 1 + seed % subs;
        if (!rc.submission(id).paid) return;
        rc.payPanel(_panel(id, Kind.Audit, 1, seed >> 8));
    }

    function finalize(uint256 seed) external {
        uint256 id = _sub(seed, 1);
        if (id == 0) return;
        pn.setStatus(id, Status.Final, pn.submission(id).pass, pn.submission(id).pid);
    }

    function claim(uint256 seed) external {
        uint256 b = _bountyIn(seed, RaceV3Base.State.Won);
        if (b == 0) return;
        uint256 id = rc.bounty(b).winner;
        if (!pn.submission(id).pass) {
            rc.sync(id);
            return;
        }
        rc.claim(b, _fix(id), bytes32(0), "salt");
        ++claims;
    }

    function withdraw(uint256 seed) external {
        if (subs == 0) return;
        uint256 id = 1 + seed % subs;
        RaceV3Base.Submission memory s = rc.submission(id);
        if (s.bounty == 0 || s.outcome != RaceV3Base.Outcome.None || pn.submission(id).pid != 0) return;
        vm.prank(s.solver);
        rc.withdraw(id);
    }

    function mergeExpired(uint256 seed) external {
        uint256 b = _bounty(seed);
        if (b == 0) return;
        RaceV3Base.Bounty memory bt = rc.bounty(b);
        if (bt.state == RaceV3Base.State.Won && rc.day() > bt.mergeBy) rc.mergeExpired(b);
    }

    function sunset(uint256 seed) external {
        uint256 b = _bounty(seed);
        if (b == 0) return;
        RaceV3Base.Bounty memory bt = rc.bounty(b);
        if (bt.state != RaceV3Base.State.Open || bt.next < rc.submissionsOf(b).length) return;
        if (rc.day() < bt.idleSince + 28) return;
        rc.sunset(b);
    }

    // ---------- payouts that must go through ----------

    function settle(uint256 seed) external {
        uint256 b = _bountyIn(seed, RaceV3Base.State.Merged);
        if (b == 0) b = _bounty(seed);
        if (b == 0) return;
        RaceV3Base.State st = rc.bounty(b).state;
        try rc.settle(b) returns (bool ok) {
            if (ok && rc.bounty(b).state == RaceV3Base.State.Paid) ++paidSettles;
        } catch {
            if (st == RaceV3Base.State.Paid || st == RaceV3Base.State.Unsolved) _stuck("settle");
        }
    }

    function instalments(uint256 seed) external {
        uint256 b = _bountyIn(seed, RaceV3Base.State.Merged);
        if (b == 0) return;
        uint256 e = rc.bounty(b).epoch;
        if (e == 0 || rc.pot(b, address(usd)).refunding) return;
        try rc.claimInstalments(b, e) {}
        catch {
            _stuck("instalments");
        }
    }

    function refund(uint256 seed) external {
        uint256 b = _bounty(seed);
        if (b == 0) return;
        address who = _actor(seed >> 8);
        if (rc.pledged(b, address(usd), who) == 0 || rc.refundedTo(b, address(usd), who)) return;
        RaceV3Base.State st = rc.bounty(b).state;
        bool fin = st == RaceV3Base.State.Paid || st == RaceV3Base.State.Unsolved;
        vm.prank(who);
        try rc.claimRefund(b, address(usd)) {
            ++refunds;
        } catch {
            if (fin) _stuck("refund");
        }
    }

    function finish(uint256 seed) external {
        uint256 id = _sub(seed, 2);
        if (id == 0) return;
        try rc.finish(id) {
            ++finished;
        } catch {
            _stuck("finish");
        }
    }

    // ---------- time ----------

    function passDays(uint256 daysRaw) external {
        vm.warp(block.timestamp + bound(daysRaw, 1, 10) * 1 days);
        if (block.timestamp >= fees.start() + (fees.rolled() + 1) * 1 days) fees.roll();
    }

    // ---------- helpers ----------

    function _panel(uint256 id, Kind kind, uint256 k, uint256 seed) internal returns (uint256 pid) {
        address[] memory js = new address[](k);
        for (uint256 i; i < k; ++i) {
            js[i] = keys[(seed + i) % keys.length];
        }
        pid = pn.newPanel(id, kind, js, false);
        for (uint256 i; i < k; ++i) {
            _report(pid, js[i], seed + i);
        }
    }

    function _report(uint256 pid, address key, uint256 seed) internal {
        IFeesV3.Usage memory u = IFeesV3.Usage(
            keccak256(abi.encode("receipt", pid, key)),
            uint64(seed % 200_000),
            uint64((seed >> 20) % 30_000),
            uint64((seed >> 40) % 20_000),
            uint64((seed >> 60) % 3_000),
            uint64((seed >> 80) % 6_000),
            uint64((seed >> 100) % 30)
        );
        bytes32 subject = keccak256(abi.encode(USAGE_TAG, address(rc), pid, key));
        bytes32 digest = keccak256(abi.encode(subject, keccak256(abi.encode(u))));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(secretOf[key], digest);
        rc.report(pid, key, u, abi.encodePacked(r, s, v));
    }

    function _stuck(string memory what) internal {
        ++stuck;
        lastStuck = what;
    }
}

/// forge-config: default.invariant.depth = 200
contract RaceV3InvariantTest is Test {
    RaceV3 rc;
    RaceV3Handler handler;
    MockCoin usd;
    PoolV3 pool;

    function setUp() public {
        usd = new MockCoin("Test USD", "tUSD", 6);
        address[] memory coins = new address[](1);
        coins[0] = address(usd);
        pool = new PoolV3(coins);
        ReplayRegistry reg = new ReplayRegistry();
        bytes32[] memory fams = new bytes32[](2);
        fams[0] = keccak256("anthropic");
        fams[1] = keccak256("openai");
        FeesV3.Genesis memory g;
        g.coin = address(usd);
        g.shared = [uint256(11_244_444), 1_234_722, 269_531_250, 2_700_000_000];
        g.families = fams;
        g.tokens = new uint256[3][](2);
        g.tokens[0] = [uint256(4_000_000), 200_000, 20_000_000];
        g.tokens[1] = [uint256(2_000_000), 100_000, 10_000_000];
        g.caps = IFeesV3.Caps(140_000, 16_000, 20, 1_000_000, 50_000, 1 gwei);
        g.defaultProfile = IFeesV3.Profile(keccak256("image"), 2_000, 4_096, 1_200);
        FeesV3 fees = new FeesV3(IFeesV3Validators(address(reg)), new MockScores(), g);
        ReplayPanels pn = new ReplayPanels(address(fees), address(usd), address(pool), address(reg));
        RaceV3Base.Config memory c;
        c.infrastructure = address(0x1F);
        c.insurance = address(0x15);
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
        RaceV3Annex ax = new RaceV3Annex(c, 625, 1e9, p, pool, block.timestamp);
        rc = new RaceV3(c, 625, 1e9, p, pool, block.timestamp, new bytes32[](0), new bytes32[](0), "c", ax);
        usd.mint(address(this), 1e12);
        usd.approve(address(pool), type(uint256).max);
        pool.fund(address(usd), 1e12);
        handler = new RaceV3Handler(rc, pn, fees, usd, reg);
        targetContract(address(handler));
    }

    function invariant_booksExact() public view {
        assertEq(
            usd.balanceOf(address(rc)),
            rc.totalHeld(address(usd)) + rc.totalOwed(address(usd)) + rc.totalDeposits(address(usd))
        );
        assertFalse(rc.withdrawOnly(address(usd)));
    }

    function invariant_payoutsNeverStuck() public view {
        assertEq(handler.stuck(), 0, handler.lastStuck());
    }

    /// The deposits the race holds are exactly the checks' deposits not yet returned, the issue stakes not yet closed
    /// and the challenges' holds; and no check was ever charged more than its deposit.
    function invariant_depositsAccounted() public view {
        uint256 sum;
        for (uint256 id = 1; id <= handler.subs(); ++id) {
            sum += rc.submission(id).deposit;
        }
        for (uint256 i = 1; i <= handler.issues(); ++i) {
            if (rc.issue(i).state == RaceV3Base.IssueState.Posted) sum += rc.issue(i).stake;
        }
        assertEq(rc.totalDeposits(address(usd)), sum);
        assertEq(handler.overCharged(), 0);
    }

    /// Every pot covers what its awards still owe, and no award is priced above the bounty its panel judged.
    function invariant_potsCoverAwards() public view {
        address c = address(usd);
        for (uint256 i = 1; i <= handler.issues(); ++i) {
            uint256 b = rc.issue(i).bounty;
            if (b == 0 || rc.pot(b, c).refunding) continue;
            RaceV3Base.Bounty memory bt = rc.bounty(b);
            if (bt.epoch == 0) continue;
            RaceV3Base.Award memory a = rc.award(b, bt.epoch);
            uint256 price = rc.priceOf(b, bt.epoch);
            assertLe(price, rc.submission(a.sub).judged);
            if (!a.closed) assertLe(price - rc.instalmentsPaid(b, bt.epoch), rc.held(b, c));
        }
    }

    /// A settled pot whose funders were all refunded is empty.
    function invariant_settledPotsDrain() public view {
        address c = address(usd);
        for (uint256 i = 1; i <= handler.issues(); ++i) {
            uint256 b = rc.issue(i).bounty;
            if (b == 0) continue;
            RaceV3Base.State s = rc.bounty(b).state;
            bool fin = s == RaceV3Base.State.Paid || s == RaceV3Base.State.Refunded || s == RaceV3Base.State.Unsolved;
            if (!fin || !rc.pot(b, c).refunding) continue;
            if (rc.pot(b, c).refunds == rc.pot(b, c).funders) assertEq(rc.held(b, c), 0);
        }
    }

    /// A winner is always a submission whose recorded verdict is a pass.
    function invariant_winnersPassed() public view {
        for (uint256 i = 1; i <= handler.issues(); ++i) {
            uint256 b = rc.issue(i).bounty;
            if (b == 0) continue;
            RaceV3Base.Bounty memory bt = rc.bounty(b);
            if (bt.state == RaceV3Base.State.Won || bt.state == RaceV3Base.State.Merged) {
                assertEq(uint256(rc.submission(bt.winner).outcome), uint256(RaceV3Base.Outcome.Pass));
            }
        }
    }

    /// A scripted run through the handler reaches every path the invariants guard (a paid settle, a refund, a
    /// clawback, a finished deposit), and the invariants hold after it.
    function test_theHandlerReachesEveryPath() public {
        handler.register(1, true);
        handler.register(2, true);
        handler.pledge(0, 100e6);
        handler.pledge(1, 100e6);
        handler.attempt(0);
        handler.commit(0); // bounty 1
        handler.commit(1); // bounty 2
        // a seed s starts the handler's search at check s % subs + 1
        handler.judge(handler.subs() - 2, true); // bounty 1's submission
        handler.judge(handler.subs() - 1, true); // bounty 2's
        handler.claim(0);
        handler.claim(1);
        assertEq(handler.claims(), 2);
        handler.reverse(handler.subs() - 1); // bounty 2's pass reversed before finality: clawed back
        assertEq(handler.clawbacks(), 1);
        handler.finalize(handler.subs() - 2);
        handler.audit(handler.subs() - 2);
        for (uint256 d; d < 6; ++d) {
            handler.passDays(7);
        }
        handler.instalments(0);
        handler.settle(0);
        assertEq(handler.paidSettles(), 1);
        handler.refund(0); // the funder of bounty 1 (actor 0)
        assertEq(handler.refunds(), 1);
        handler.finish(handler.subs() - 2);
        assertEq(handler.finished(), 1);
        invariant_booksExact();
        invariant_payoutsNeverStuck();
        invariant_depositsAccounted();
        invariant_potsCoverAwards();
        invariant_settledPotsDrain();
        invariant_winnersPassed();
    }
}
