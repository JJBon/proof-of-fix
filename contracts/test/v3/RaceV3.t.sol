// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {console} from "forge-std/Test.sol";
import {Baskets} from "../../src/Baskets.sol";
import {IFeesV3} from "../../src/v3/IFeesV3.sol";
import {FeesV3} from "../../src/v3/FeesV3.sol";
import {Panels} from "../../src/v3/Panels.sol";
import {Status, Kind, Submission, Panel, Seat} from "../../src/v3/PanelsBase.sol";
import {PoolV3} from "../../src/v3/PoolV3.sol";
import {RaceV3} from "../../src/v3/RaceV3.sol";
import {RaceV3Annex} from "../../src/v3/RaceV3Annex.sol";
import {RaceV3Endings} from "../../src/v3/RaceV3Endings.sol";
import {RaceV3Base} from "../../src/v3/RaceV3Base.sol";
import {Heads} from "../../src/v2/Heads.sol";
import {RaceV3Setup} from "./helpers/RaceV3Setup.sol";
import {TEST_REPO, TEST_GENESIS_HEAD} from "./helpers/SuiteWindows.sol";

/// proof-of-fix#138, task 3.5 of #132: RaceV3, v2's race judged by Panels and charged by FeesV3. v2's race suite
/// (RaceV2.t.sol) ported: every v2 rule that v3 keeps is tested here under its v2 name where it has one; the oracle
/// quorum's tests (signatures, replays, the signed fee list, the signed weights) have no counterpart, since nothing is
/// signed by a quorum any more. Added for v3: the parties fixed at the opening, the judges' reports and pay, the hold
/// and finality, the clawback by a reversed verdict, challenges and their stakes, audits and shadows paid, FeesV3's
/// queue signals, and the award capped at the bounty its panel judged.
contract RaceV3Test is RaceV3Setup {
    bytes32 constant FIX = keccak256("fix");
    bytes32 constant FIX2 = keccak256("fix2");

    function setUp() public {
        _deployRace(3); // the genesis validator and 3 more: every panel is k = 3
    }

    // ---------- registration and the registration check ----------

    function test_registerPaysTheFeeAndHoldsTheStake() public {
        uint256 i = _register();
        RaceV3Base.Issue memory is_ = rc.issue(i);
        assertEq(_owed(infra), 2 * C);
        uint256 deposit = fees.maxDeposit(TEST_REPO, 7);
        assertEq(rc.totalDeposits(address(usd)), 5 * C + deposit);
        assertEq(is_.reporter, reporter);
        assertEq(rc.submission(is_.check).deposit, deposit);
        assertEq(uint256(pn.submission(is_.check).status), uint256(Status.Sealed));
        assertEq(pn.submission(is_.check).bounty, 1);
        assertEq(fees.epochOf(is_.check), 0);
        _assertBooks();
    }

    /// The registration check passes and is final: the bounty opens at once and the market funds it.
    function test_checkOpensItAndTheMarketFundsIt() public {
        uint256 b = _openBounty();
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Open));
        assertEq(rc.held(b, address(usd)), 100 * C);
        assertEq(rc.issue(rc.bounty(b).issue).bounty, b);
        _assertBooks();
    }

    function test_onlyAFinalCheckOpensABounty() public {
        uint256 i = _register();
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.openBounty(i);
        uint256 id = rc.issue(i).check;
        _judgeCheck(id, true);
        vm.expectRevert(RaceV3Base.NotYet.selector); // counted, not final
        rc.openBounty(i);
        _final(id);
        rc.openBounty(i);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.openBounty(i);
    }

    /// The check fails: the issue is junk and its stake goes to insurance; no bounty opens.
    function test_junkForfeitsTheStake() public {
        uint256 i = _register();
        _check(rc.issue(i).check, false);
        assertEq(rc.openBounty(i), 0);
        assertEq(uint256(rc.issue(i).state), uint256(RaceV3Base.IssueState.Forfeited));
        assertEq(_owed(insurance), 5 * C);
        _assertBooks();
    }

    function test_reporterWithdrawsBeforeTheCheck() public {
        uint256 i = _register();
        uint256 id = rc.issue(i).check;
        uint256 deposit = rc.submission(id).deposit;
        vm.prank(alice);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.withdrawIssue(i);
        vm.prank(reporter);
        rc.withdrawIssue(i);
        assertEq(_owed(reporter), 5 * C + deposit);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Withdrawn));
        assertEq(rc.totalDeposits(address(usd)), 0);
        _assertBooks();
    }

    // ---------- the price ----------

    function test_priceLockedOnTheThirdDay() public {
        uint256 b = _openBounty();
        uint256 from = rc.bounty(b).offerFrom;
        _toDay(from + 3);
        assertEq(rc.offerBps(b), 8_000);
        _fund(solver1, C);
        vm.prank(solver1);
        rc.attempt(b);
        _toDay(from + 10);
        assertEq(rc.offerBps(b), 8_000);
        uint256 cap = (100 * C - 2 * C) * 10_000 / (10_000 + FINDER);
        assertEq(rc.lockedPrice(b), cap * 8_000 / 10_000);
    }

    function test_priceRisesToTheWhole() public {
        uint256 b = _openBounty();
        _toDay(rc.bounty(b).offerFrom + 30);
        assertEq(rc.offerBps(b), 10_000);
    }

    function test_topUpAfterTheLockRaisesThePrice() public {
        uint256 b = _openBounty();
        _fund(solver1, C);
        vm.prank(solver1);
        rc.attempt(b);
        uint256 p0 = rc.lockedPrice(b);
        _pledge(bob, b, 100 * C);
        assertGt(rc.lockedPrice(b), p0);
    }

    // ---------- the queue ----------

    function test_orderedByCommitment() public {
        uint256 b = _openBounty();
        uint256 s1 = _commit(solver1, b, FIX);
        uint256 s2 = _commit(solver2, b, FIX2);
        _judgeCheck(s2, true); // the later one passes first: it waits for the earlier one
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Open));
        _judgeCheck(s1, true);
        assertEq(rc.bounty(b).winner, s1);
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Won));
    }

    function test_earlierFailLetsTheNextPassWin() public {
        uint256 b = _openBounty();
        uint256 s1 = _commit(solver1, b, FIX);
        uint256 s2 = _commit(solver2, b, FIX2);
        _judgeCheck(s2, true);
        _judgeCheck(s1, false);
        assertEq(rc.bounty(b).winner, s2);
    }

    // ---------- the judges' pay ----------

    /// The counted judges are paid FeesV3's settlement from the fix's flat judges' fee at the result (#132 D30: in
    /// place of a deposit sized to the quote); its rest goes to the sponsors' pool after finality, never back.
    function test_depositPaysTheChecksAndTheRestReturns() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        uint256 deposit = rc.submission(id).deposit;
        uint256 pid = _draw(id);
        address[] memory js = pn.judges(pid);
        uint256[] memory before0 = new uint256[](3);
        for (uint256 i; i < 3; ++i) {
            before0[i] = _owed(reg.validator(js[i]).operator);
        }
        _judge(pid, _votes(3, 0));
        _reportAll(pid);
        vm.prank(relayer);
        rc.result(id);
        uint256 paid;
        for (uint256 i; i < js.length; ++i) {
            uint256 got = _owed(reg.validator(js[i]).operator) - before0[i];
            assertGt(got, 0);
            paid += got;
        }
        RaceV3Base.Submission memory s = rc.submission(id);
        assertEq(s.charged, paid + _owed(relayer));
        assertEq(s.deposit, deposit - s.charged);
        assertTrue(fees.settled(id));
        _final(id);
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.finish(id);
        vm.warp(block.timestamp + 1 days + 1);
        uint256 before = _owed(solver1);
        uint256 left = rc.submission(id).deposit;
        uint256 pooled = pool3.held(address(usd));
        assertEq(deposit, 40 * C); // JUDGE_FEE
        rc.finish(id);
        assertEq(_owed(solver1), before); // the fee isn't refunded
        assertEq(pool3.held(address(usd)), pooled + left);
        _assertBooks();
    }

    function test_resultWaitsForEveryReport() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        uint256 pid = _draw(id);
        _judge(pid, _votes(3, 3));
        address[] memory js = pn.judges(pid);
        _reportSeat(pid, js[0]);
        _reportSeat(pid, js[1]);
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.result(id);
        uint256 third = _owed(reg.validator(js[2]).operator);
        uint256 first = _owed(reg.validator(js[0]).operator);
        vm.warp(pn.panel(pid).revealBy + 1 days + 1); // the third never reports: it isn't paid
        rc.result(id);
        assertEq(_owed(reg.validator(js[2]).operator), third);
        assertGt(_owed(reg.validator(js[0]).operator), first);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.result(id);
    }

    function test_resultOnlyOnceAndOnlyCounted() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.result(id);
        _judgeCheck(id, true);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.result(id);
    }

    function test_reportsAreSignedByTheSeatAndBoundToItsReceipt() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        uint256 pid = _draw(id);
        _judge(pid, _votes(3, 3));
        address[] memory js = pn.judges(pid);
        IFeesV3.Usage memory u = _usage(pid, js[0]);
        bytes32 subject = keccak256(abi.encode(USAGE_TAG, address(rc), pid, js[0]));
        bytes memory sig = _statementSig(js[0], subject, keccak256(abi.encode(u)));
        bytes memory other = _statementSig(js[1], subject, keccak256(abi.encode(u)));
        vm.expectRevert(RaceV3Base.BadSignature.selector); // signed by another key
        rc.report(pid, js[0], u, other);
        IFeesV3.Usage memory wrong = _usage(pid, js[0]);
        wrong.receipt = keccak256("another receipt");
        vm.expectRevert(RaceV3Base.Refused.selector); // not its on-chain receipt
        rc.report(pid, js[0], wrong, sig);
        vm.expectRevert(RaceV3Base.Refused.selector); // not seated
        rc.report(pid, alice, u, sig);
        rc.report(pid, js[0], u, sig);
        vm.expectRevert(RaceV3Base.Refused.selector); // once a seat
        rc.report(pid, js[0], u, sig);
    }

    // ---------- the claim (merge) ----------

    function test_lateSubmissionPaysTheFee() public {
        uint256 b = _openBounty();
        uint256 s1 = _commit(solver1, b, FIX);
        _judgeCheck(s1, true);
        _fund(solver2, 10 * C);
        bytes32 c = _commitment(FIX2, solver2);
        vm.prank(solver2);
        assertEq(rc.commit(b, c), 0);
        assertEq(_owed(infra), 2 * C + 2 * C);
    }

    function test_claimOpensTheCommitment() public {
        uint256 b = _openBounty();
        uint256 s1 = _commit(solver1, b, FIX);
        _judgeCheck(s1, true);
        bytes32 base = _head();
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.claim(b, FIX2, base, "salt");
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.claim(b, FIX, base, "pepper");
        rc.claim(b, FIX, base, "salt");
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Merged));
        assertFalse(rc.paid(FIX)); // paid (merged) only at its finality (#251, L9)
        RaceV3Base.Award memory a = rc.award(b, 1);
        assertEq(a.winner, solver1);
        assertEq(a.sub, s1);
        assertFalse(a.merged);
        assertEq(rc.submission(s1).base, base);
        _finalAndMerge(b, s1);
        assertTrue(rc.paid(FIX));
        assertTrue(rc.award(b, 1).merged);
    }

    function test_notMergedReopens() public {
        uint256 b = _openBounty();
        uint256 s1 = _commit(solver1, b, FIX);
        _judgeCheck(s1, true);
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.mergeExpired(b);
        _toDay(rc.bounty(b).mergeBy + 1);
        rc.mergeExpired(b);
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Open));
    }

    /// Instalments start at the verdict's finality in Panels, one each release after it; then the bounty is paid,
    /// the reporter gets the finder's fee and the registration back, the winner its checks, and refunds open.
    function test_paidInInstalmentsFromFinalityThenRefunded() public {
        uint256 b = _openBounty();
        uint256 s1 = _commit(solver1, b, FIX);
        _judgeCheck(s1, true);
        rc.claim(b, FIX, _head(), "salt");
        uint256 price = rc.priceOf(b, 1);
        assertEq(rc.earned(b, 1), 0); // not final yet
        _toDay(rc.day() + 20);
        assertEq(rc.earned(b, 1), 0); // the window's audits and finality haven't happened
        uint256 owed0 = _owed(solver1);
        _final(s1);
        _toDay(rc.day() + 6);
        assertEq(rc.earned(b, 1), 0); // final, but not merged yet: nothing is paid (#251, L9)
        rc.merge(b);
        (,,,,,, uint256 st) = rc.contracts();
        uint256 f = (pn.submission(s1).finalAt - st) / 1 days; // the instalments count from the window's end
        _toDay(f + 6);
        assertEq(rc.earned(b, 1), (f + 6) / 7 - f / 7);
        rc.claimInstalments(b, 1);
        assertEq(_owed(solver1), owed0 + price / 4 * rc.earned(b, 1));
        _toDay(f + 35);
        assertEq(rc.earned(b, 1), 4);
        assertTrue(rc.settle(b));
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Paid));
        assertEq(rc.instalmentsPaid(b, 1), price);
        vm.prank(alice);
        rc.claimRefund(b, address(usd));
        _assertBooks();
    }

    function test_paidFixCantWinALaterBounty() public {
        uint256 b1 = _openBounty();
        uint256 s1 = _commit(solver1, b1, FIX);
        _judgeCheck(s1, true);
        rc.claim(b1, FIX, _head(), "salt");
        _finalAndMerge(b1, s1);
        uint256 b2 = _openBounty();
        uint256 s2 = _commit(solver2, b2, FIX);
        _judgeCheck(s2, true);
        assertEq(uint256(rc.bounty(b2).state), uint256(RaceV3Base.State.Won));
        uint256 infraBefore = _owed(infra);
        rc.claim(b2, FIX, _head(), "salt");
        assertEq(uint256(rc.submission(s2).outcome), uint256(RaceV3Base.Outcome.Duplicate));
        assertEq(uint256(rc.bounty(b2).state), uint256(RaceV3Base.State.Open));
        assertEq(_owed(infra), infraBefore + 2 * C);
    }

    // ---------- the parties, fixed at the opening ----------

    /// The reporter, the solver and the funders who pledged before the commitment are parties; a funder who pledges
    /// after it isn't, for that submission (a later one counts it), and nobody stops being one.
    function test_partiesFixedAtTheOpening() public {
        uint256 b = _openBounty();
        _pledge(bob, b, C);
        uint256 id = _commit(solver1, b, FIX);
        address carol = makeAddr("carol");
        _pledge(carol, b, C);
        assertTrue(rc.isParty(id, reporter));
        assertTrue(rc.isParty(id, solver1));
        assertTrue(rc.isParty(id, alice));
        assertTrue(rc.isParty(id, bob));
        assertFalse(rc.isParty(id, carol));
        assertFalse(rc.isParty(id, solver2));
        assertFalse(rc.isParty(id, address(0)));
        uint256 later = _commit(solver2, b, FIX2);
        assertTrue(rc.isParty(later, carol));
        assertFalse(rc.isParty(later, solver1));
        uint256 check = rc.issue(rc.bounty(b).issue).check;
        assertTrue(rc.isParty(check, reporter));
        assertFalse(rc.isParty(check, alice));
    }

    /// A validator whose operator funded the bounty before the commitment isn't drawn for it; three such leave only
    /// the genesis validator, so the panel steps down to k = 1, and its verdict is held: its three challengers would be
    /// parties too. A funder after the commitment recuses nobody.
    function test_aFunderBeforeTheCommitmentIsRecused() public {
        uint256 b = _openBounty();
        _fundersAreValidators(b);
        uint256 id = _commit(solver1, b, FIX);
        uint256 pid = _draw(id);
        assertEq(pn.panel(pid).k, 1);
        assertEq(pn.judges(pid)[0], genesisKey);
        _judge(pid, _votes(1, 1));
        assertEq(uint256(pn.submission(id).status), uint256(Status.Held));
    }

    /// The three validators besides the genesis one pledge to bounty `b`, from their operator accounts.
    function _fundersAreValidators(uint256 b) internal {
        for (uint256 i = 1; i <= 3; ++i) {
            address key = reg.validatorAt(i);
            _pledge(reg.validator(key).operator, b, C / 10);
        }
    }

    // ---------- finality: the hold and the instalments ----------

    /// Scenario "The genesis validator's first verdicts", through the race: a held k = 1 pass wins and is claimed,
    /// but earns nothing until three challengers exist, its window and its two audits have run, and it's final.
    function test_aHeldVerdictPaysNothingUntilFinal() public {
        uint256 b = _openBounty();
        _fundersAreValidators(b);
        uint256 id = _commit(solver1, b, FIX);
        uint256 pid = _draw(id);
        _judge(pid, _votes(1, 1));
        _reportAll(pid);
        rc.result(id);
        rc.claim(b, FIX, _head(), "salt");
        _toDay(rc.day() + 60);
        assertEq(rc.earned(b, 1), 0);
        vm.expectRevert(Panels.NotReady.selector);
        pn.startWindow(id);
        _network(3, FAMILIES, 3); // three more, not parties
        pn.startWindow(id);
        _finalAndMerge(b, id);
        _toDay(rc.day() + 28);
        assertEq(rc.earned(b, 1), 4);
        assertTrue(rc.settle(b));
        _assertBooks();
    }

    // ---------- the award never pays more than its panel judged ----------

    function test_awardCappedAtTheJudgedBounty() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        uint256 judged = rc.submission(id).judged;
        assertEq(judged, rc.lockedPrice(b));
        assertEq(pn.submission(id).bounty, judged);
        _pledge(bob, b, 400 * C); // after the commitment: the price rises above what the panel was sized for
        assertGt(rc.lockedPrice(b), judged);
        _judgeCheck(id, true);
        rc.claim(b, FIX, _head(), "salt");
        assertEq(rc.priceOf(b, 1), judged);
        _finalAndMerge(b, id);
        _toDay(rc.day() + 35);
        rc.settle(b);
        assertEq(rc.instalmentsPaid(b, 1), judged);
        vm.prank(bob);
        rc.claimRefund(b, address(usd)); // the rest returns to the funders
        assertGt(_owed(bob), 300 * C);
        _assertBooks();
    }

    // ---------- challenges ----------

    /// A pass challenged in its window and reversed by a fresh panel of 5: the award is clawed back (nothing earned),
    /// the bounty reopens, the challenger gets its stake and cover back, and the challenge panel is paid from the
    /// solver's deposit.
    function test_clawedBackReopens() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        _judgeCheck(id, true);
        rc.claim(b, FIX, _head(), "salt");
        _network(5, FAMILIES, 3);
        uint256 cpid = _challenge(id, false);
        uint256 deposit = rc.submission(id).deposit;
        rc.settleChallenge(id, cpid);
        assertEq(_owed(bob), 10 * C + _bobsCover);
        assertEq(rc.challengeOf(id).challenger, address(0));
        assertLt(rc.submission(id).deposit, deposit);
        assertEq(uint256(rc.submission(id).outcome), uint256(RaceV3Base.Outcome.Fail));
        assertTrue(rc.award(b, 1).closed);
        assertEq(rc.award(b, 1).earned, 0);
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Open));
        assertEq(rc.earned(b, 1), 0);
        _assertBooks();
    }

    /// A rejected challenge: the panel is paid from the challenger's cover, the rest of it returns, and the stake goes
    /// to the challenged panel's judges in equal shares. The award stands.
    function test_rejectedChallengePaysTheAccused() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        uint256 pid = _judgeCheck(id, true);
        rc.claim(b, FIX, _head(), "salt");
        _network(5, FAMILIES, 3);
        address[] memory js = pn.judges(pid);
        uint256[] memory before0 = new uint256[](3);
        for (uint256 i; i < 3; ++i) {
            before0[i] = _owed(reg.validator(js[i]).operator);
        }
        uint256 cpid = _challenge(id, true);
        rc.settleChallenge(id, cpid);
        uint256 stake = 10 * C;
        for (uint256 i; i < 3; ++i) {
            uint256 share = i == 0 ? stake - stake / 3 * 2 : stake / 3;
            assertEq(_owed(reg.validator(js[i]).operator), before0[i] + share);
        }
        assertLt(_owed(bob), _bobsCover);
        assertGt(_owed(bob), 0);
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Merged));
        assertFalse(rc.award(b, 1).closed);
        _assertBooks();
    }

    /// A failed fix whose fail a challenge reverses wins while the bounty is open, in its commitment's turn: the
    /// challenger is refunded and the panel paid from the solver's deposit.
    function test_aFailReversedToAPassWins() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        _judgeCheck(id, false);
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Open));
        _network(5, FAMILIES, 3);
        uint256 cpid = _challenge(id, true);
        rc.settleChallenge(id, cpid);
        assertEq(uint256(rc.submission(id).outcome), uint256(RaceV3Base.Outcome.Pass));
        assertEq(rc.bounty(b).winner, id);
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Won));
        assertEq(_owed(bob), 10 * C + _bobsCover);
    }

    function test_challengeRules() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        _fund(bob, 100 * C);
        vm.prank(bob);
        vm.expectRevert(Panels.WrongStatus.selector); // not counted yet
        rc.challenge(id, keccak256("evidence"));
        _judgeCheck(id, true);
        vm.prank(bob);
        rc.challenge(id, keccak256("evidence"));
        vm.prank(bob);
        vm.expectRevert(RaceV3Base.Refused.selector); // one at a time
        rc.challenge(id, keccak256("evidence"));
        uint256 last = pn.panelCount();
        vm.expectRevert(RaceV3Base.Refused.selector); // no panel yet
        rc.settleChallenge(id, last);
    }

    uint256 internal _bobsCover;

    /// Bob challenges check `id`; a fresh panel is drawn and votes `pass`, every seat reports; returns its panel.
    function _challenge(uint256 id, bool pass) internal returns (uint256 cpid) {
        _fund(bob, 100 * C);
        uint256 before = usd.balanceOf(bob);
        vm.prank(bob);
        rc.challenge(id, keccak256("evidence"));
        _bobsCover = before - usd.balanceOf(bob) - 10 * C;
        assertEq(_bobsCover, fees.depositFor(id, TEST_REPO, 7));
        _rollPast(pn.submission(id).challengeBlock);
        pn.drawChallenge(id);
        cpid = pn.submission(id).challengePid;
        uint256 kc = pn.panel(cpid).k;
        _judge(cpid, pass ? _votes(kc, kc) : _votes(kc, 0));
        _reportAll(cpid);
    }

    // ---------- audits and shadows ----------

    /// Every k = 1 verdict's two audits: each auditor is paid FeesV3's `checkCost` (unscaled fee) from the deposit's
    /// rest, once a panel.
    function test_auditsPaidFromTheDeposit() public {
        uint256 b = _openBounty();
        _fundersAreValidators(b);
        uint256 id = _commit(solver1, b, FIX);
        uint256 pid = _draw(id);
        _judge(pid, _votes(1, 1));
        _reportAll(pid);
        rc.result(id);
        _network(3, FAMILIES, 3);
        pn.startWindow(id);
        uint256 before = pn.panelCount();
        _runAudits(id, true);
        uint256 audits;
        for (uint256 q = before + 1; q <= pn.panelCount(); ++q) {
            if (pn.panel(q).kind != Kind.Audit) continue;
            ++audits;
            address op = reg.validator(pn.judges(q)[0]).operator;
            uint256 owed0 = _owed(op);
            uint256 dep0 = rc.submission(id).deposit;
            vm.expectRevert(RaceV3Base.NotYet.selector); // its report isn't in
            rc.payPanel(q);
            _reportAll(q);
            uint256 g = gasleft();
            rc.payPanel(q);
            console.log("payPanel (an audit):", g - gasleft());
            uint256 got = _owed(op) - owed0;
            assertGt(got, 0);
            assertEq(dep0 - rc.submission(id).deposit, got);
            vm.expectRevert(RaceV3Base.Refused.selector);
            rc.payPanel(q);
        }
        assertEq(audits, 2);
        vm.expectRevert(RaceV3Base.Refused.selector); // a counted panel isn't paid here
        rc.payPanel(pid);
    }

    /// Shadows (candidates) seated with a draw are repaid their capped usage from the sponsors' pool, once a seat, and
    /// only once revealed with a receipt and reported.
    function test_shadowsPaidFromThePool() public {
        address c1 = _addCandidate(keccak256("cand host 1"), _family(1), _tee(0), 1, 200e6);
        address c2 = _addCandidate(keccak256("cand host 2"), _family(2), _tee(1), 1, 200e6);
        uint256 b = _openBounty();
        _fund(address(this), 50 * C);
        usd.approve(address(pool3), 50 * C);
        pool3.fund(address(usd), 50 * C);
        uint256 id = _commit(solver1, b, FIX);
        _draw(id);
        uint256 spid = pn.submission(id).shadowPid;
        assertEq(pn.panel(spid).k, 2);
        address[] memory sh = pn.judges(spid);
        assertTrue((sh[0] == c1 && sh[1] == c2) || (sh[0] == c2 && sh[1] == c1));
        for (uint256 i; i < 2; ++i) {
            _seal(spid, sh[i], true);
        }
        vm.warp(pn.panel(spid).sealBy + 1);
        _reveal(spid, sh[0]);
        _receipt(spid, sh[0]);
        _reportSeat(spid, sh[0]);
        address op = reg.validator(sh[0]).operator;
        uint256 cost = fees.shadowCost(id, TEST_REPO, reg.validator(sh[0]).family, _usage(spid, sh[0]));
        uint256 g = gasleft();
        rc.payShadow(spid, 0);
        console.log("payShadow:", g - gasleft());
        assertEq(usd.balanceOf(op), cost);
        assertEq(pool3.held(address(usd)), 50 * C - cost);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.payShadow(spid, 0);
        vm.expectRevert(RaceV3Base.Refused.selector); // never revealed
        rc.payShadow(spid, 1);
    }

    // ---------- FeesV3's queue signals ----------

    /// A submission above k = 1's limit while only one validator isn't a party waits: it counts once as waited.
    /// A drawn panel's validators count as drawn.
    function test_signalsForwardedFromPanelsStatus() public {
        _reputation(solver1, 200 * C); // its claim is above REP_BASE (#132 D29)
        uint256 b = _openBounty();
        _fundersAreValidators(b);
        _pledge(bob, b, 100 * C); // the price is now above $50, k = 1's limit
        uint256 id = _commit(solver1, b, FIX);
        _draw(id);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Waiting));
        uint256 p = fees.currentPeriod();
        uint256 waited0 = fees.period(p).waited;
        rc.signal(id);
        rc.signal(id);
        assertEq(fees.period(p).waited, waited0 + 1);
        vm.prank(solver1);
        rc.withdraw(id);
        assertEq(uint256(rc.submission(id).outcome), uint256(RaceV3Base.Outcome.Withdrawn));
        uint256 b2 = _openBounty();
        vm.warp(vm.getBlockTimestamp() + 1 days); // a new pricing period, whatever the windows: nobody drawn in it yet
        uint256 id2 = _commit(solver2, b2, FIX2);
        _draw(id2);
        p = fees.currentPeriod();
        uint256 drawn0 = fees.period(p).drawn;
        rc.signal(id2);
        assertEq(fees.period(p).drawn, drawn0 + 3);
    }

    // ---------- withdrawals, time-outs and the sunset ----------

    /// Scenario "A withdrawn submission" (bounty-market, #132 D30): the fee isn't returned (it goes to the sponsors'
    /// pool whole), and no per-check charge is made.
    function test_withdrawReturnsTheWholeDeposit() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        uint256 deposit = rc.submission(id).deposit;
        uint256 bal = _owed(solver1);
        uint256 pooled = pool3.held(address(usd));
        vm.prank(solver2);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.withdraw(id);
        vm.prank(solver1);
        rc.withdraw(id);
        assertEq(_owed(solver1), bal);
        assertEq(rc.submission(id).charged, 0);
        assertEq(pool3.held(address(usd)), pooled + deposit);
        assertEq(uint256(pn.submission(id).status), uint256(Status.Withdrawn));
        _assertBooks();
    }

    function test_aSubmissionNoPanelTookTimesOut() public {
        _reputation(solver1, 200 * C); // its claim is above REP_BASE (#132 D29)
        uint256 b = _openBounty();
        _fundersAreValidators(b);
        _pledge(bob, b, 100 * C);
        uint256 id = _commit(solver1, b, FIX);
        _draw(id); // waits
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.timeOut(id);
        _toDay(rc.day() + 7);
        rc.timeOut(id);
        assertEq(uint256(rc.submission(id).outcome), uint256(RaceV3Base.Outcome.TimedOut));
        assertEq(rc.bounty(b).next, 1);
    }

    function test_aJudgedSubmissionCantBeWithdrawn() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        _draw(id);
        vm.prank(solver1);
        vm.expectRevert(Panels.WrongStatus.selector);
        rc.withdraw(id);
    }

    function test_idleBountySunsets() public {
        uint256 b = _openBounty();
        uint256 from = rc.bounty(b).idleSince;
        _toDay(from + 27);
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.sunset(b);
        _toDay(from + 28);
        rc.sunset(b);
        assertEq(uint256(rc.bounty(b).state), uint256(RaceV3Base.State.Unsolved));
        assertEq(uint256(rc.issue(rc.bounty(b).issue).state), uint256(RaceV3Base.IssueState.Returned));
        vm.prank(alice);
        rc.claimRefund(b, address(usd));
        assertEq(_owed(alice), 100 * C);
        _assertBooks();
    }

    function test_attemptsDontKeepItAlive() public {
        uint256 b = _openBounty();
        uint256 from = rc.bounty(b).idleSince;
        _fund(solver1, 10 * C);
        for (uint256 d = 1; d < 28; d += 5) {
            _toDay(from + d);
            vm.prank(solver1);
            rc.attempt(b);
        }
        _toDay(from + 28);
        rc.sunset(b);
    }

    function test_waitingResultBlocksSunsetAndAFailureRestartsTheClock() public {
        uint256 b = _openBounty();
        uint256 from = rc.bounty(b).idleSince;
        uint256 id = _commit(solver1, b, FIX);
        _toDay(from + 28);
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.sunset(b);
        _judgeCheck(id, false);
        assertEq(rc.bounty(b).idleSince, rc.day());
        vm.expectRevert(RaceV3Base.NotYet.selector);
        rc.sunset(b);
    }

    // ---------- appeals ----------

    function test_authorAppealsOnce() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        _judgeCheck(id, false);
        vm.prank(solver2);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.appeal(id, TEST);
        vm.prank(solver1);
        uint256 again = rc.appeal(id, TEST);
        assertEq(rc.submission(again).commitment, rc.submission(id).commitment);
        assertTrue(rc.submission(again).appealed);
        vm.prank(solver1);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.appeal(id, TEST);
        vm.prank(solver1);
        vm.expectRevert(RaceV3Base.Refused.selector); // an appeal isn't appealed
        rc.appeal(again, TEST);
        _judgeCheck(again, true);
        assertEq(rc.bounty(b).winner, again);
    }

    // ---------- the head registry ----------

    /// The commitment opens to (fix, base); the claim doesn't move the head, the merge at finality does, from that base.
    function test_mergeMovesTheHeadOnlyFromIt() public {
        bytes32 repo = TEST_REPO;
        _fund(reporter, 100 * C);
        vm.prank(reporter);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.register(keccak256("unknown repo"), false);
        vm.prank(reporter);
        uint256 i = rc.register(repo, false);
        _check(rc.issue(i).check, true);
        uint256 b = rc.openBounty(i);
        _pledge(alice, b, 100 * C);
        _fund(solver1, 100 * C);
        bytes32 base = TEST_GENESIS_HEAD;
        vm.prank(solver1);
        uint256 id = rc.commit(b, keccak256(abi.encode(FIX, base, bytes32("salt"), solver1)));
        _judgeCheck(id, true);
        (,,,, Heads h,,) = rc.contracts();
        vm.expectRevert(); // a base that isn't the commitment's
        rc.claim(b, FIX, keccak256("other"), "salt");
        rc.claim(b, FIX, base, "salt");
        assertEq(h.head(repo).commit, base); // not at the claim (#251, L9)
        _finalAndMerge(b, id);
        assertEq(h.head(repo).commit, FIX);
        assertEq(h.head(repo).submission, id);
        assertEq(h.head(repo).bounty, b);
    }

    /// An issue registered with hidden tests or a private repository: its registration check and every submission to
    /// its bounty are opened with Panels.openHidden (level A or B judges only, D10).
    function test_aHiddenIssuesChecksAreTeeOnly() public {
        _fund(reporter, 100 * C);
        vm.prank(reporter);
        uint256 i = rc.register(TEST_REPO, true);
        assertTrue(rc.issue(i).hidden);
        assertTrue(pn.submission(rc.issue(i).check).teeOnly);
        _check(rc.issue(i).check, true);
        uint256 b = rc.openBounty(i);
        _pledge(alice, b, 100 * C);
        uint256 id = _commit(solver1, b, FIX);
        assertTrue(pn.submission(id).teeOnly);
        uint256 open = _openBounty();
        assertFalse(pn.submission(_commit(solver2, open, FIX2)).teeOnly);
    }

    // ---------- gas ----------

    /// The gas of each race step (call frame only: without the transaction's 21,000 and its calldata), on a network
    /// of 4 (k = 3) with the real Panels, FeesV3 and pool. Logged for reports/contract-v3.md.
    function test_gasPerStep() public {
        _fund(reporter, 100 * C);
        uint256 g = gasleft();
        vm.prank(reporter);
        uint256 i = rc.register(TEST_REPO, false);
        console.log("register (with its check's deposit and Panels.open):", g - gasleft());
        _check(rc.issue(i).check, true);
        g = gasleft();
        uint256 b = rc.openBounty(i);
        console.log("openBounty:", g - gasleft());
        _fund(alice, 100 * C);
        vm.prank(alice);
        g = gasleft();
        rc.pledge(b, 100 * C);
        console.log("pledge (a first funder):", g - gasleft());
        _fund(solver1, 100 * C);
        vm.prank(solver1);
        g = gasleft();
        rc.attempt(b);
        console.log("attempt:", g - gasleft());
        bytes32 c = _commitment(FIX, solver1);
        vm.prank(solver1);
        g = gasleft();
        uint256 id = rc.commit(b, c);
        console.log("commit (deposit, FeesV3.open, Panels.open):", g - gasleft());
        uint256 pid = _draw(id);
        g = gasleft();
        rc.signal(id);
        console.log("signal (3 drawn):", g - gasleft());
        _judge(pid, _votes(3, 3));
        address[] memory js = pn.judges(pid);
        IFeesV3.Usage memory u = _usage(pid, js[0]);
        bytes memory sig = _statementSig(
            js[0], keccak256(abi.encode(USAGE_TAG, address(rc), pid, js[0])), keccak256(abi.encode(u))
        );
        g = gasleft();
        rc.report(pid, js[0], u, sig);
        console.log("report:", g - gasleft());
        _reportSeat(pid, js[1]);
        _reportSeat(pid, js[2]);
        g = gasleft();
        rc.result(id);
        console.log("result (k = 3: FeesV3.settle, 3 judges and the relayer paid, the queue):", g - gasleft());
        g = gasleft();
        rc.claim(b, FIX, _head(), "salt");
        console.log("claim (opens the commitment; the head waits for finality):", g - gasleft());
        uint256 before = pn.panelCount();
        _runAudits(id, true);
        for (uint256 q = before + 1; q <= pn.panelCount(); ++q) {
            if (pn.panel(q).kind != Kind.Audit) continue;
            _reportAll(q);
            g = gasleft();
            rc.payPanel(q);
            console.log("payPanel (an audit):", g - gasleft());
        }
        vm.warp(pn.submission(id).finalAt);
        pn.finalize(id);
        g = gasleft();
        rc.merge(b);
        console.log("merge (the head moves at finality, #251 L9):", g - gasleft());
        _toDay(rc.day() + 7);
        g = gasleft();
        rc.claimInstalments(b, 1);
        console.log("claimInstalments:", g - gasleft());
        _toDay(rc.day() + 28);
        g = gasleft();
        rc.settle(b);
        console.log("settle (paid: instalments, finder's fee, refunds of registration and checks):", g - gasleft());
        g = gasleft();
        rc.finish(id);
        console.log("finish (the deposit's rest):", g - gasleft());
        vm.prank(alice);
        g = gasleft();
        rc.claimRefund(b, address(usd));
        console.log("claimRefund:", g - gasleft());
        // a challenge, on a second bounty, with 5 more validators
        uint256 b2 = _openBounty();
        uint256 id2 = _commit(solver2, b2, FIX2);
        _judgeCheck(id2, true);
        _network(5, FAMILIES, 3);
        _fund(bob, 100 * C);
        vm.prank(bob);
        g = gasleft();
        rc.challenge(id2, keccak256("evidence"));
        console.log("challenge (stake and cover held, Panels.challenge):", g - gasleft());
        _rollPast(pn.submission(id2).challengeBlock);
        pn.drawChallenge(id2);
        uint256 cpid = pn.submission(id2).challengePid;
        _judge(cpid, _votes(5, 0));
        _reportAll(cpid);
        g = gasleft();
        rc.settleChallenge(id2, cpid);
        console.log("settleChallenge (upheld, a panel of 5 paid, the award clawed back):", g - gasleft());
    }

    // ---------- keyless ----------

    /// No owner, admin, setter or pause: every state-changing function is a race action anyone may call.
    function test_noPrivilegedCall() public view {
        string memory json = vm.readFile("out/RaceV3.sol/RaceV3.json");
        string[30] memory writers = [
            "register", "withdrawIssue", "openBounty", "pledge", "sunset", "attempt", "stop", "commit", "report",
            "result", "claim", "merge", "release", "claimInstalments", "settle", "appeal", "withdraw", "timeOut",
            "mergeExpired", "dispute", "close",
            "challenge", "settleChallenge", "sync", "payPanel", "payShadow", "signal", "finish",
            // Baskets: refunds, credits and swaps
            "claimRefund", "check"
        ];
        string[4] memory swaps = ["offerSwap", "cancelSwap", "acceptSwap", "withdraw"];
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
            for (uint256 j; j < swaps.length && !ok; ++j) {
                ok = keccak256(bytes(name)) == keccak256(bytes(swaps[j]));
            }
            assertTrue(ok, string.concat("unexpected state-changing function: ", name));
            ++n;
        }
        assertEq(n, 34); // two named withdraw: the race's and Baskets' credit withdrawal
    }

    /// The annex's actions run only in a race's storage, through its DELEGATECALL; and a race refuses an annex built
    /// for other contracts.
    function test_annexRunsOnlyThroughTheRace() public {
        RaceV3Annex ax = RaceV3Annex(rc.annex());
        vm.expectRevert(RaceV3Base.Refused.selector);
        ax.sync(1);
        RaceV3Endings en = RaceV3Endings(ax.endings());
        vm.expectRevert(RaceV3Base.Refused.selector);
        en.register(TEST_REPO, false);
        RaceV3Annex other = new RaceV3Annex(_config(), 625, 100_000, pn, pool3, block.timestamp + 0, new RaceV3Endings(_config(), 625, 100_000, pn, pool3, block.timestamp + 0));
        (,,,,,, uint256 st) = rc.contracts();
        if (st != block.timestamp) {
            vm.expectRevert(RaceV3Base.BadParams.selector);
            this.deployRace(_config(), 625, st, other);
        }
        RaceV3Annex wrongCap = new RaceV3Annex(_config(), 600, 100_000, pn, pool3, st, new RaceV3Endings(_config(), 600, 100_000, pn, pool3, st));
        vm.expectRevert(RaceV3Base.BadParams.selector);
        this.deployRace(_config(), 625, st, wrongCap);
    }

    // RaceV3 and its annex are cheatcode deployments in this suite (too large to inline): an expected revert wraps an
    // external call, or the rest of the test silently doesn't run (#251).

    function deployRace(RaceV3Base.Config memory c, uint256 cap, uint256 st, RaceV3Annex ax) external returns (RaceV3) {
        return new RaceV3(c, cap, 100_000, pn, pool3, st, TEST_REPO, TEST_GENESIS_HEAD, "c", ax);
    }

    function deployAnnex(RaceV3Base.Config memory c, uint256 cap, uint256 st) external returns (RaceV3Annex) {
        return new RaceV3Annex(c, cap, 100_000, pn, pool3, st, new RaceV3Endings(c, cap, 100_000, pn, pool3, st));
    }

    /// Panels judges bounties up to BOUNTY_MAX ($625): a race whose pots could hold more is refused.
    function test_paramsChecked() public {
        (,,,,,, uint256 st) = rc.contracts();
        vm.expectRevert(RaceV3Base.BadParams.selector);
        this.deployAnnex(_config(), 626, st);
        RaceV3Base.Config memory c = _config();
        c.instalments = 0;
        vm.expectRevert(RaceV3Base.BadParams.selector);
        this.deployAnnex(c, 625, st);
        this.deployAnnex(_config(), 625, st); // and the right parameters build one
    }

    /// EIP-170 for every runtime, and EIP-3860 for RaceV3's initcode (it deploys Heads; its annex is deployed first).
    function test_sizesFit() public view {
        string[3] memory names = ["RaceV3", "RaceV3Annex", "PoolV3"];
        for (uint256 i; i < names.length; ++i) {
            string memory json = vm.readFile(string.concat("out/", names[i], ".sol/", names[i], ".json"));
            uint256 runtime = (bytes(vm.parseJsonString(json, ".deployedBytecode.object")).length - 2) / 2;
            uint256 init = (bytes(vm.parseJsonString(json, ".bytecode.object")).length - 2) / 2;
            console.log(names[i], runtime, init);
            assertLt(runtime, 24_577, names[i]);
            assertLt(init, 49_153, names[i]);
        }
    }

    /// The race reads a few words of Panels' and the registry's records (RaceV3Base's S_, P_, X_ and V_ offsets): each
    /// word is checked here against the typed view, so a field added before them fails this test.
    function test_theRaceReadsPanelsRecordsRight() public {
        uint256 b = _openBounty();
        uint256 id = _commit(solver1, b, FIX);
        uint256 pid = _judgeCheck(id, true);
        bytes memory s = abi.encode(pn.submission(id));
        Submission memory ps = pn.submission(id);
        assertEq(_word(s, 3), uint256(ps.status));
        assertEq(_word(s, 5), ps.k);
        assertEq(_word(s, 7), ps.pass ? 1 : 0);
        assertEq(_word(s, 15), ps.finalAt);
        assertEq(_word(s, 16), ps.pid);
        bytes memory p = abi.encode(pn.panel(pid));
        Panel memory pp = pn.panel(pid);
        assertEq(_word(p, 0), pp.id);
        assertEq(_word(p, 3), pp.revealBy);
        assertEq(_word(p, 5), pp.k);
        assertEq(_word(p, 6), pp.seats);
        assertEq(_word(p, 9), pp.passes);
        assertEq(_word(p, 11), pp.counted ? 1 : 0);
        assertEq(_word(p, 12), uint256(pp.kind));
        bytes memory x = abi.encode(pn.seat(pid, 0));
        Seat memory xx = pn.seat(pid, 0);
        assertEq(_word(x, 0), uint256(uint160(xx.key)));
        assertEq(_word(x, 3), xx.revealed ? 1 : 0);
        assertEq(_word(x, 4), xx.receipted ? 1 : 0);
        assertEq(_word(x, 6), xx.mask);
        assertEq(bytes32(_word(x, 8)), xx.receipt);
        bytes memory v = abi.encode(reg.validator(xx.key));
        assertEq(_word(v, 5), uint256(uint160(reg.validator(xx.key).operator)));
        assertEq(bytes32(_word(v, 12)), reg.validator(xx.key).family);
    }

    function _word(bytes memory r, uint256 i) internal pure returns (uint256 x) {
        assembly ("memory-safe") {
            x := mload(add(r, mul(add(i, 1), 32)))
        }
    }
}
