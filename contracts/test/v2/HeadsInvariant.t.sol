// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {Test} from "forge-std/Test.sol";
import {OraclesV2} from "./helpers/OraclesV2.sol";
import {RaceV2 as Race} from "../../src/v2/RaceV2.sol";
import {RaceV2Base} from "../../src/v2/RaceV2Base.sol";
import {Heads} from "../../src/v2/Heads.sol";
import {MockCoin} from "../mocks/MockCoin.sol";

/// proof-of-fix#85 task 5.2 (design S1): random runs of wins, merges (current, stale or under-signed), expiries and
/// strangers calling the registry. The handler keeps the head it expects from the merges the quorum signed on the
/// current head; the invariant is that the registry agrees, so the head only ever moves by a quorum verdict.
contract HeadsHandler is OraclesV2 {
    Race public race;
    Heads public heads;
    MockCoin public usd;
    bytes32 public expectedHead;
    uint256 public expectedBounty;
    uint256 public moves; // merges that moved the head
    uint256 public refusedStale; // stale merges refused, as they should be
    uint256 public illegal; // a move that went through when it shouldn't have
    string public lastIllegal;
    uint256 internal commits;
    bytes32[] internal pastHeads;
    uint256 internal bounties;

    constructor(Race race_, MockCoin usd_) {
        race = race_;
        heads = race_.heads();
        usd = usd_;
        _makeOracles(3, 2);
        expectedHead = GENESIS_HEAD;
        usd.approve(address(race), type(uint256).max);
    }

    function REPO_ID() external pure returns (bytes32) {
        return REPO;
    }

    function _newCommit() internal returns (bytes32) {
        return bytes32(bytes20(keccak256(abi.encode("commit", ++commits))));
    }

    /// A Won bounty in REPO, searching from a random one; 0 if none.
    function _won(uint256 seed) internal view returns (uint256) {
        for (uint256 k; k < bounties; ++k) {
            uint256 b = 1 + (seed % bounties + k) % bounties;
            if (race.bounty(b).state == RaceV2Base.State.Won) return b;
        }
        return 0;
    }

    function wait(uint256 daysAhead) external {
        vm.warp(block.timestamp + bound(daysAhead, 0, 20) * 1 days);
    }

    /// An issue in REPO, accepted, funded, and won: its result checked on the current head or (oldBase) an older one.
    function openAndWin(bool oldBase) external {
        usd.mint(address(this), 120e6);
        uint256 i = race.register(address(usd), REPO);
        uint256 b = _accept(race, i);
        bounties = b;
        race.pledge(b, address(usd), 100e6);
        bytes32 fix = _newCommit();
        uint256 id = race.commit(b, keccak256(abi.encode(fix)), address(usd));
        RaceV2Base.Verdict memory v = _verdict(race, b, id, RaceV2Base.Outcome.Pass, fix);
        if (oldBase && pastHeads.length != 0) v.base = pastHeads[0];
        race.result(v, new RaceV2Base.Fee[](0), _sigs(race, _resultHash(v, new RaceV2Base.Fee[](0))));
    }

    /// The quorum's merge, checked on the current head (or rebased onto it): the head moves to a new commit.
    function mergeOnTheHead(uint256 seed) external {
        uint256 b = _won(seed);
        if (b == 0) return;
        uint256 w = race.bounty(b).winner;
        RaceV2Base.Verdict memory v = _verdict(race, b, w, RaceV2Base.Outcome.Pass, _newCommit()); // the rebased commit
        race.merged(v, 0, _sigs(race, _mergedHash(v, 0)));
        pastHeads.push(expectedHead);
        expectedHead = v.fix;
        expectedBounty = b;
        moves += 1;
    }

    /// The quorum's merge checked on an older head: refused, and nothing moves.
    function mergeStale(uint256 seed) external {
        uint256 b = _won(seed);
        if (b == 0 || pastHeads.length == 0) return;
        uint256 w = race.bounty(b).winner;
        RaceV2Base.Verdict memory v = _verdict(race, b, w, RaceV2Base.Outcome.Pass, _newCommit());
        v.base = pastHeads[seed % pastHeads.length];
        bytes[] memory sigs = _sigs(race, _mergedHash(v, 0));
        try race.merged(v, 0, sigs) {
            illegal += 1;
            lastIllegal = "a stale merge went through";
        } catch {
            refusedStale += 1;
        }
    }

    /// A merge signed by one key only: refused.
    function mergeUnderSigned(uint256 seed) external {
        uint256 b = _won(seed);
        if (b == 0) return;
        uint256 w = race.bounty(b).winner;
        RaceV2Base.Verdict memory v = _verdict(race, b, w, RaceV2Base.Outcome.Pass, _newCommit());
        uint256[] memory one = new uint256[](1);
        one[0] = oracleSecrets[seed % oracleSecrets.length];
        bytes[] memory sigs = _signWith(race, _mergedHash(v, 0), v.nonce, one).sigs;
        try race.merged(v, 0, sigs) {
            illegal += 1;
            lastIllegal = "an under-signed merge went through";
        } catch {}
    }

    /// Anyone, an oracle included, calling the registry directly with the right base: refused.
    function strangerMoves(uint256 who, bool oracle) external {
        address caller = oracle ? oracleSet[who % oracleSet.length] : address(uint160(bound(who, 1, type(uint160).max)));
        if (caller == address(race)) return;
        bytes32 base = heads.head(REPO).commit;
        bytes32 fix = _newCommit();
        vm.prank(caller);
        try heads.move(REPO, base, fix, 1, 1, bytes32(0)) {
            illegal += 1;
            lastIllegal = "a stranger moved the head";
        } catch {}
    }

    /// A won fix not merged in time: the bounty reopens, and the head stays.
    function expire(uint256 seed) external {
        uint256 b = _won(seed);
        if (b == 0) return;
        try race.mergeExpired(b) {} catch {}
    }
}

contract HeadsInvariantTest is Test {
    HeadsHandler handler;
    Race race;

    function setUp() public {
        MockCoin usd = new MockCoin("Mock USD", "mUSD", 6);
        address[] memory feeCoins = new address[](1);
        feeCoins[0] = address(usd);
        // The handler's oracles (same test keys) and the race it deploys through OraclesV2._newRace's genesis.
        HeadsDeployer d = new HeadsDeployer();
        race = d.deploy(feeCoins);
        handler = new HeadsHandler(race, usd);
        targetContract(address(handler));
    }

    /// The registry's head is exactly the last commit the quorum merged on the head: it never moves otherwise.
    /// forge-config: default.invariant.fail-on-revert = true
    function invariant_headMovesOnlyByAQuorumVerdict() public view {
        Heads.Head memory h = race.heads().head(handler.REPO_ID());
        assertEq(h.commit, handler.expectedHead());
        assertEq(h.bounty, handler.expectedBounty());
        assertEq(handler.illegal(), 0, handler.lastIllegal());
    }

}

/// Deploys a RaceV2 with the helper's genesis (REPO at GENESIS_HEAD) and the test oracles.
contract HeadsDeployer is OraclesV2 {
    function deploy(address[] memory feeCoins) external returns (Race) {
        _makeOracles(3, 2);
        RaceV2Base.Config memory c;
        c.infrastructure = address(0xFEE);
        c.insurance = address(0x1F5);
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
        return _newRace(c, feeCoins, 1_000_000, 100_000_000);
    }
}
