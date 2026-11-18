// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {OraclesV2} from "./helpers/OraclesV2.sol";
import {RaceV2 as Race} from "../../src/v2/RaceV2.sol";
import {RaceV2Base} from "../../src/v2/RaceV2Base.sol";
import {RaceV2Annex} from "../../src/v2/RaceV2Annex.sol";
import {Verdicts, IParties} from "../../src/v2/Verdicts.sol";
import {genesis} from "./helpers/GenesisV2.sol";
import {MockCoin} from "../mocks/MockCoin.sol";

/// proof-of-fix#85 task 5.3 (design S2): the tiers on-chain. 7 keys; the issue tier draws 3 by the submission's seed
/// and passes with 2; the constitution tier needs 5 of those who sit; the owner's seat (one key, its operator's
/// disclosed account) is recused where the owner is a party. Spec scenarios (checking delta): "Two of three", "Four of
/// seven", "The draw is reproducible", "The owner solves a bounty", "The owner writes an ADR"; and the task's unit
/// tests: too few signatures, a judge not drawn, a recused key. The ABI listing (no function changing the counts) is
/// SplitV2Test.test_verdictsHaveNoPrivilegedCall.
contract TiersV2Test is OraclesV2 {
    uint256 constant C = 1e6;

    Race race;
    Verdicts verdicts;
    MockCoin usd;
    address owner = makeAddr("owner"); // the owner's disclosed account; its seat is oracleSet[OWNER_SEAT]
    address reporter = makeAddr("reporter");
    address alice = makeAddr("alice");
    address solver1 = makeAddr("solver1");
    uint256 constant OWNER_SEAT = 3;

    event KeyRecused(address indexed consumer, bytes32 indexed digest, address key);

    function setUp() public {
        usd = new MockCoin("Mock USD", "mUSD", 6);
        address[] memory feeCoins = new address[](1);
        feeCoins[0] = address(usd);
        _makeOracles(7, 5); // S2: JUDGES = 7, CONSTITUTION_QUORUM = 5
        operatorAccounts.push(owner);
        operatorKeys.push(oracleSet[OWNER_SEAT]);
        RaceV2Base.Config memory c;
        c.infrastructure = makeAddr("infra");
        c.insurance = makeAddr("insurance");
        c.registrationFee = 2e6;
        c.issueStake = 5e6;
        c.attemptFee = 0.5e6;
        c.evaluationFee = 2e6;
        c.checkDeposit = 6.6e6;
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
        race = _newRace(c, feeCoins, 1_000, 100_000);
        verdicts = race.verdicts();
    }

    // ---------- helpers ----------

    function _fund(address who, uint256 amount) internal {
        usd.mint(who, amount);
        vm.prank(who);
        usd.approve(address(race), type(uint256).max);
    }

    /// An accepted issue reported by `rep`, its bounty funded by `funder` with 100 credits.
    function _openBounty(address rep, address funder) internal returns (uint256 b) {
        _fund(rep, 7 * C);
        vm.prank(rep);
        uint256 i = race.register(address(usd), REPO);
        b = _accept(race, i);
        _fund(funder, 100 * C);
        vm.prank(funder);
        race.pledge(b, address(usd), 100 * C);
    }

    /// `who` commits `fix` on bounty b in a block whose RANDAO value is `randao`.
    function _commit(address who, uint256 b, bytes32 fix, uint256 randao) internal returns (uint256) {
        _fund(who, 10 * C);
        vm.prevrandao(bytes32(randao));
        vm.prank(who);
        return race.commit(b, keccak256(abi.encode(fix, bytes32("salt"), who)), address(usd));
    }

    function _secretOf(address key) internal view returns (uint256) {
        for (uint256 i; i < oracleSet.length; ++i) {
            if (oracleSet[i] == key) return oracleSecrets[i];
        }
        revert("not a key");
    }

    function _contains(address[] memory set, address k) internal pure returns (bool) {
        for (uint256 i; i < set.length; ++i) {
            if (set[i] == k) return true;
        }
        return false;
    }

    /// Two keys in address order.
    function _sorted(address a, address b) internal view returns (uint256[] memory s) {
        s = new uint256[](2);
        (s[0], s[1]) = a < b ? (_secretOf(a), _secretOf(b)) : (_secretOf(b), _secretOf(a));
    }

    function _resultSigs(RaceV2Base.Verdict memory v, uint256[] memory secrets) internal view returns (bytes[] memory) {
        return _signWith(race, _resultHash(v, new RaceV2Base.Fee[](0)), bytes32(0), secrets).sigs;
    }

    /// A key of the set that wasn't drawn.
    function _undrawn(address[] memory judges) internal view returns (address) {
        for (uint256 i; i < oracleSet.length; ++i) {
            if (!_contains(judges, oracleSet[i])) return oracleSet[i];
        }
        revert("all drawn");
    }

    // ---------- the counts (S2) ----------

    function test_countsAreFixed() public view {
        assertEq(verdicts.ISSUE_JUDGES(), 3);
        assertEq(verdicts.ISSUE_QUORUM(), 2);
        assertEq(verdicts.quorum(), 5);
        assertEq(verdicts.keys().length, 7);
        assertEq(verdicts.seatOf(owner), oracleSet[OWNER_SEAT]);
        assertEq(verdicts.operatorsOf(oracleSet[OWNER_SEAT])[0], owner);
    }

    /// The operators are fixed with the keys: each a nonzero account for a key of the set, once.
    function test_operatorsChecked() public {
        address[] memory accounts = new address[](1);
        address[] memory seats = new address[](1);
        accounts[0] = owner;
        seats[0] = makeAddr("not a key");
        vm.expectRevert(Verdicts.BadOracleSet.selector);
        new Verdicts(genesis(oracleSet, 5, accounts, seats));
        seats[0] = oracleSet[0];
        accounts[0] = address(0);
        vm.expectRevert(Verdicts.BadOracleSet.selector);
        new Verdicts(genesis(oracleSet, 5, accounts, seats));
        accounts = new address[](2);
        seats = new address[](2);
        (accounts[0], accounts[1]) = (owner, owner); // one seat per account
        (seats[0], seats[1]) = (oracleSet[0], oracleSet[1]);
        vm.expectRevert(Verdicts.BadOracleSet.selector);
        new Verdicts(genesis(oracleSet, 5, accounts, seats));
        vm.expectRevert(Verdicts.BadOracleSet.selector); // pairwise
        new Verdicts(genesis(oracleSet, 5, new address[](1), new address[](0)));
        address[] memory two = new address[](2);
        (two[0], two[1]) = (oracleSet[0], oracleSet[1]);
        vm.expectRevert(Verdicts.BadOracleSet.selector); // fewer keys than the issue tier draws
        new Verdicts(genesis(two, 2, new address[](0), new address[](0)));
    }

    // ---------- the issue tier: 3 drawn from 7, 2 to pass ----------

    /// Scenario "Two of three": 2 of the 3 drawn judges sign and the result counts; the third's dissent doesn't stop
    /// it.
    function test_twoOfThreeDrawnPass() public {
        uint256 b = _openBounty(reporter, alice);
        uint256 id = _commit(solver1, b, "fix1", 1);
        (RaceV2Base.Verdict memory v,) = _signResult(race, id, RaceV2Base.Outcome.Pass, "fix1", new RaceV2Base.Fee[](0));
        (address[] memory judges,) = verdicts.drawn(v.seed, b, id, address(race));
        assertEq(judges.length, 3);
        race.result(v, new RaceV2Base.Fee[](0), _resultSigs(v, _sorted(judges[0], judges[2])));
        assertEq(uint256(race.bounty(b).state), uint256(RaceV2Base.State.Won));
    }

    /// One drawn judge isn't enough.
    function test_tooFewSignatures() public {
        uint256 b = _openBounty(reporter, alice);
        uint256 id = _commit(solver1, b, "fix1", 1);
        (RaceV2Base.Verdict memory v,) = _signResult(race, id, RaceV2Base.Outcome.Pass, "fix1", new RaceV2Base.Fee[](0));
        (address[] memory judges,) = verdicts.drawn(v.seed, b, id, address(race));
        uint256[] memory one = new uint256[](1);
        one[0] = _secretOf(judges[0]);
        vm.expectRevert(Verdicts.TooFewSignatures.selector);
        race.result(v, new RaceV2Base.Fee[](0), _resultSigs(v, one));
    }

    /// A judge not drawn can't count, even with a drawn one beside it, nor can two keys that weren't drawn; the
    /// version's whole-set quorum (5 of 7) doesn't stand in for the draw either.
    function test_aJudgeNotDrawnIsRefused() public {
        uint256 b = _openBounty(reporter, alice);
        uint256 id = _commit(solver1, b, "fix1", 1);
        (RaceV2Base.Verdict memory v,) = _signResult(race, id, RaceV2Base.Outcome.Pass, "fix1", new RaceV2Base.Fee[](0));
        (address[] memory judges,) = verdicts.drawn(v.seed, b, id, address(race));
        address outsider = _undrawn(judges);
        vm.expectRevert(Verdicts.NotDrawn.selector);
        race.result(v, new RaceV2Base.Fee[](0), _resultSigs(v, _sorted(judges[0], outsider)));
        uint256[] memory five = new uint256[](5);
        for (uint256 i; i < 5; ++i) {
            five[i] = oracleSecrets[i]; // the first five keys in address order: at least two weren't drawn
        }
        vm.expectRevert(Verdicts.NotDrawn.selector);
        race.result(v, new RaceV2Base.Fee[](0), _resultSigs(v, five));
        race.result(v, new RaceV2Base.Fee[](0), _resultSigs(v, _sorted(judges[1], judges[2])));
    }

    /// Scenario "The draw is reproducible": recomputed from the recorded seed and the keys, it yields the same 3; the
    /// seed is the one fixed at the commit (the RANDAO value, the commitment and the id), so another block draws
    /// another seed.
    function test_drawIsReproducible() public {
        uint256 b = _openBounty(reporter, alice);
        uint256 id = _commit(solver1, b, "fix1", 42);
        RaceV2Base.Submission memory s = race.submission(id);
        assertEq(s.seed, keccak256(abi.encode(uint256(42), s.commitment, id)));
        (address[] memory a,) = verdicts.drawn(s.seed, b, id, address(race));
        (address[] memory again,) = verdicts.drawn(s.seed, b, id, address(race));
        assertEq(keccak256(abi.encode(a)), keccak256(abi.encode(again)));
        uint256 id2 = _commit(makeAddr("solver2"), b, "fix1", 43);
        assertTrue(race.submission(id2).seed != s.seed);
    }

    /// The draw spreads the work over all 7 seats (S2: "the work and the fees spread across all 7 operators").
    function test_drawSpreadsOverTheSeats() public view {
        uint256[7] memory count;
        for (uint256 i; i < 700; ++i) {
            (address[] memory judges,) = verdicts.drawn(keccak256(abi.encode(i)), 0, 0, address(this));
            assertEq(judges.length, 3);
            for (uint256 j; j < 3; ++j) {
                for (uint256 k; k < 7; ++k) {
                    if (judges[j] == oracleSet[k]) ++count[k];
                }
            }
        }
        for (uint256 k; k < 7; ++k) {
            assertGt(count[k], 240); // 300 expected (700 draws × 3/7)
            assertLt(count[k], 360);
        }
    }

    // ---------- the owner's seat recuses (checking delta "The owner holds at most one seat and recuses") ----------

    /// Whether the owner's seat is a party here: nobody is a party in this test contract's own subjects.
    function isParty(uint256, uint256, address) external pure returns (bool) {
        return false;
    }

    /// A commit by `who` whose seed reaches the owner's seat in the draw (drawn, or recused if `who` is the owner),
    /// trying RANDAO values: each try is a new submission of `who`'s.
    function _commitDrawingTheOwner(address who, uint256 b) internal returns (uint256 id) {
        for (uint256 r = 1;; ++r) {
            id = _commit(who, b, bytes32(r), r);
            (address[] memory judges, address[] memory recused) =
                verdicts.drawn(race.submission(id).seed, b, id, address(race));
            if (_contains(recused, oracleSet[OWNER_SEAT]) || _contains(judges, oracleSet[OWNER_SEAT])) return id;
        }
    }

    /// Scenario "The owner solves a bounty": the owner's seat would be drawn, but the owner is the solver, so it's
    /// recused, the next key in the shuffle sits, the record shows the recusal, and the owner's key can't sign.
    function test_theOwnersSeatRecusesWhenTheOwnerSolves() public {
        uint256 b = _openBounty(reporter, alice);
        uint256 id = _commitDrawingTheOwner(owner, b);
        RaceV2Base.Submission memory s = race.submission(id);
        assertEq(s.solver, owner, "the owner's own submission");
        (RaceV2Base.Verdict memory v,) =
            _signResult(race, id, RaceV2Base.Outcome.Pass, bytes32(uint256(id)), new RaceV2Base.Fee[](0));
        (address[] memory judges, address[] memory recused) = verdicts.drawn(v.seed, b, id, address(race));
        assertEq(judges.length, 3, "three still sit");
        assertEq(recused.length, 1);
        assertEq(recused[0], oracleSet[OWNER_SEAT]);
        assertFalse(_contains(judges, oracleSet[OWNER_SEAT]));
        vm.expectRevert(Verdicts.NotDrawn.selector);
        race.result(v, new RaceV2Base.Fee[](0), _resultSigs(v, _sorted(judges[0], oracleSet[OWNER_SEAT])));
        bytes[] memory sigs = _resultSigs(v, _sorted(judges[0], judges[1]));
        bytes32 digest = _digest(race, _resultHash(v, new RaceV2Base.Fee[](0)));
        vm.expectEmit(address(verdicts));
        emit KeyRecused(address(race), digest, oracleSet[OWNER_SEAT]);
        race.result(v, new RaceV2Base.Fee[](0), sigs);
    }

    /// Funders and reporters are parties too: the owner's seat isn't drawn on a bounty the owner funded or reported.
    function test_theOwnersSeatRecusesAsFunderOrReporter() public {
        uint256 funded = _openBounty(reporter, owner);
        uint256 reported = _openBounty(owner, alice);
        for (uint256 r = 1; r < 40; ++r) {
            uint256 id = _commit(makeAddr(string.concat("s", vm.toString(r))), funded, bytes32(r), r);
            (address[] memory judges,) = verdicts.drawn(race.submission(id).seed, funded, id, address(race));
            assertFalse(_contains(judges, oracleSet[OWNER_SEAT]));
            id = _commit(makeAddr(string.concat("t", vm.toString(r))), reported, bytes32(r), r);
            (judges,) = verdicts.drawn(race.submission(id).seed, reported, id, address(race));
            assertFalse(_contains(judges, oracleSet[OWNER_SEAT]));
        }
        assertTrue(race.isParty(funded, 0, owner));
        assertTrue(race.isParty(reported, 0, owner));
        assertFalse(race.isParty(funded, 0, solver1));
    }

    /// Where the owner isn't a party, the owner's seat is drawn like any other.
    function test_theOwnersSeatJudgesOtherwise() public {
        uint256 b = _openBounty(reporter, alice);
        uint256 id = _commitDrawingTheOwner(solver1, b);
        (address[] memory judges, address[] memory recused) = verdicts.drawn(race.submission(id).seed, b, id, address(race));
        assertTrue(_contains(judges, oracleSet[OWNER_SEAT]));
        assertEq(recused.length, 0);
    }

    // ---------- the EIP-170 split: RaceV2Annex runs only in RaceV2's storage ----------

    /// The actions moved to RaceV2Annex run through RaceV2 (its storage, balances and caller) and refuse a direct call.
    function test_annexRunsOnlyThroughTheRace() public {
        RaceV2Annex annex = RaceV2Annex(race.annex());
        vm.expectRevert(RaceV2Base.Refused.selector);
        annex.timeOut(1);
        vm.expectRevert(RaceV2Base.Refused.selector);
        annex.mergeExpired(1);
        vm.expectRevert(RaceV2Base.Refused.selector);
        annex.withdrawIssue(1);
        // Through the race they act on the race's state.
        uint256 b = _openBounty(reporter, alice);
        uint256 id = _commit(solver1, b, "fix1", 1);
        vm.warp(block.timestamp + 7 days);
        race.timeOut(id); // the delegated call times the race's submission out
        assertEq(uint256(race.submission(id).outcome), uint256(RaceV2Base.Outcome.TimedOut));
        assertEq(annex.pledged(b, address(usd), alice), 0, "the annex's own storage holds nothing");
        assertEq(race.pledged(b, address(usd), alice), 100 * C);
    }

    // ---------- the constitution tier: 5 of the 7, or of the 6 who sit ----------

    /// Five keys' signatures in address order, from the set's keys at `idx`.
    function _five(bytes32 digest, uint256[5] memory idx) internal view returns (bytes[] memory sigs) {
        sigs = new bytes[](5);
        for (uint256 i; i < 5; ++i) {
            (uint8 v, bytes32 r, bytes32 s) = vm.sign(oracleSecrets[idx[i]], digest);
            sigs[i] = abi.encodePacked(r, s, v);
        }
    }

    /// Scenario "Four of seven": 4 signatures fail; 5 pass.
    function test_constitutionTierNeedsFiveOfSeven() public {
        TierConsumer c = new TierConsumer(verdicts, owner);
        bytes32 d = keccak256("an ADR");
        bytes[] memory five = _five(d, [uint256(0), 1, 2, 4, 5]);
        bytes[] memory four = new bytes[](4);
        for (uint256 i; i < 4; ++i) {
            four[i] = five[i];
        }
        vm.expectRevert(Verdicts.TooFewSignatures.selector);
        c.adr(d, four);
        c.adr(d, five);
        assertTrue(verdicts.used(address(c), d));
    }

    /// Scenario "The owner writes an ADR": the owner's seat doesn't sit, so its signature is refused, and the ADR still
    /// needs 5 of the 6 others.
    function test_theOwnersSeatRecusesOnItsOwnADR() public {
        TierConsumer c = new TierConsumer(verdicts, owner);
        c.setOwnerIsParty(true);
        bytes32 d = keccak256("the owner's ADR");
        vm.expectRevert(Verdicts.Recused.selector);
        c.adr(d, _five(d, [uint256(0), 1, 2, OWNER_SEAT, 4])); // the owner's seat among them
        bytes[] memory five = _five(d, [uint256(0), 1, 2, 4, 5]);
        bytes[] memory four = new bytes[](4);
        for (uint256 i; i < 4; ++i) {
            four[i] = five[i];
        }
        vm.expectRevert(Verdicts.TooFewSignatures.selector);
        c.adr(d, four);
        c.adr(d, five);
    }
}

/// A consumer of the constitution tier for the tests: the owner is a party to its subject when told so.
contract TierConsumer is IParties {
    Verdicts immutable verdicts;
    address immutable owner;
    bool ownerIsParty;

    constructor(Verdicts verdicts_, address owner_) {
        verdicts = verdicts_;
        owner = owner_;
    }

    function setOwnerIsParty(bool p) external {
        ownerIsParty = p;
    }

    function isParty(uint256, uint256, address account) external view returns (bool) {
        return ownerIsParty && account == owner;
    }

    function adr(bytes32 digest, bytes[] calldata sigs) external {
        verdicts.authorizeAll(digest, 7, 0, sigs);
    }
}
