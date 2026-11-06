// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {Script} from "forge-std/Script.sol";
import {console} from "forge-std/console.sol";
import {RaceV2} from "../src/v2/RaceV2.sol";
import {RaceV2Base} from "../src/v2/RaceV2Base.sol";
import {Verdicts} from "../src/v2/Verdicts.sol";
import {Heads} from "../src/v2/Heads.sol";
import {Fees} from "../src/v2/Fees.sol";
import {MockCoin} from "../test/mocks/MockCoin.sol";

/// One metered check on the devnet, end to end (proof-of-fix#85, task 5.7, design S15; #104's "the contract pays the
/// validator's check fee"). Run through scripts/devnet.sh fees-v2, in two phases, so the draw is read from the chain
/// (the commit's seed holds the block's RANDAO value, which only the chain knows):
///   FLOW_PHASE=commit   a reporter registers an issue in this repository, the quorum accepts it, a funder pledges
///                       100, and a solver commits a fix: its check deposit is the worst case (the quote)
///   FLOW_PHASE=check    the 3 judges drawn for the submission each sign their measured usage (one pads it), the bot
///                       relays the reports and the result (2 of 3 drawn judges), and one judge pulls its fee
/// Keys arrive in the environment from devnet.sh (from OpenBao, or anvil's mnemonic with DEVNET_KEYS=insecure-local):
/// FLOW_REPORTER_PK, FLOW_FUNDER_PK, FLOW_SOLVER_PK, FLOW_BOT_PK, FLOW_ORACLE_PKS (comma-separated). Devnet only.
contract FeesFlowV2Script is Script {
    string constant VERDICT_TYPE =
        "Verdict(bytes32 repo,bytes32 base,bytes32 fix,uint256 bounty,uint256 submission,uint8 tier,uint8 outcome,bytes32 receiptHash,bytes32 seed,bytes32 nonce)";
    bytes32 constant FIX = bytes32(bytes20(keccak256("the devnet's demo fix")));

    RaceV2 race;
    Fees meter;
    MockCoin coin;
    bytes32 repo;
    uint256 quorum;
    uint256[] oracles; // the oracle roles' keys

    function run() external {
        string memory json = vm.readFile(string.concat("./", vm.envOr("FLOW_RECORD", string("deployments/devnet-v2.json"))));
        race = RaceV2(vm.parseJsonAddress(json, ".race"));
        meter = Fees(vm.parseJsonAddress(json, ".meter"));
        coin = MockCoin(vm.parseJsonAddress(json, ".coin"));
        repo = vm.parseJsonBytes32(json, ".repo");
        quorum = vm.parseJsonUint(json, ".quorum");
        require(address(meter) != address(0), "this v2 deployment has no meter (DEPLOY_METER=0)");
        oracles = vm.envUint("FLOW_ORACLE_PKS", ",");
        if (keccak256(bytes(vm.envString("FLOW_PHASE"))) == keccak256("commit")) _commit();
        else _check();
    }

    // ---------- phase 1: an issue, a bounty, a pledge, a commit ----------

    function _commit() internal {
        uint256 reporterPk = vm.envUint("FLOW_REPORTER_PK");
        uint256 funderPk = vm.envUint("FLOW_FUNDER_PK");
        uint256 solverPk = vm.envUint("FLOW_SOLVER_PK");
        uint256 botPk = vm.envUint("FLOW_BOT_PK");

        vm.startBroadcast(reporterPk);
        coin.mint(vm.addr(reporterPk), 7e6);
        coin.approve(address(race), type(uint256).max);
        uint256 issue = race.register(address(coin), repo);
        vm.stopBroadcast();

        bytes32 nonce = keccak256(abi.encode("accept", issue, block.timestamp));
        bytes32 accept = keccak256(abi.encode(race.ACCEPT_TYPEHASH(), issue, uint256(0), nonce));
        vm.startBroadcast(botPk);
        uint256 b = race.accept(issue, 0, RaceV2Base.Signed(nonce, _quorumSigs(_digest(accept))));
        vm.stopBroadcast();

        vm.startBroadcast(funderPk);
        coin.mint(vm.addr(funderPk), 100e6);
        coin.approve(address(race), type(uint256).max);
        race.pledge(b, address(coin), 100e6);
        vm.stopBroadcast();

        uint256 quoted = meter.maxDepositFor(b);
        vm.startBroadcast(solverPk);
        coin.mint(vm.addr(solverPk), 20e6);
        coin.approve(address(race), type(uint256).max);
        uint256 id = race.commit(b, keccak256(abi.encode(FIX, bytes32("salt"), vm.addr(solverPk))), address(coin));
        vm.stopBroadcast();

        console.log("FLOW issue", issue);
        console.log("FLOW bounty", b);
        console.log("FLOW submission", id);
        console.log("FLOW quote: check deposit (micro-coins)", quoted);
        console.log("FLOW service fee per counted check", meter.serviceFee());
    }

    // ---------- phase 2: the judges' usage, the result, a judge pulls its fee ----------

    function _check() internal {
        uint256 botPk = vm.envUint("FLOW_BOT_PK");
        address bot = vm.addr(botPk);
        uint256 id = vm.envUint("FLOW_SUBMISSION");
        RaceV2Base.Submission memory s = race.submission(id);
        (address[] memory js,) = race.verdicts().drawn(s.seed, s.bounty, id, address(race));
        console.log("FLOW deposit taken at the commit", s.deposit);

        // what each drawn judge's attested node measured; the second pads its prompt tenfold
        Fees.Usage[3] memory us = [
            Fees.Usage(keccak256("receipt 0"), 28_500, 7_000, 4_000, 300, 600, 2),
            Fees.Usage(keccak256("receipt 1"), 285_000, 7_000, 4_000, 300, 600, 2),
            Fees.Usage(keccak256("receipt 2"), 28_000, 7_000, 3_900, 280, 560, 2)
        ];
        uint256[] memory owedBefore = new uint256[](js.length);
        vm.startBroadcast(botPk);
        for (uint256 j; j < js.length; ++j) {
            uint256 pk = _keyOf(js[j]);
            bytes32 d = meter.usageDigest(id, us[j]);
            (uint8 v, bytes32 r, bytes32 ss) = vm.sign(pk, d);
            meter.report(id, us[j], abi.encodePacked(r, ss, v));
            owedBefore[j] = race.owed(js[j], address(coin));
        }
        RaceV2Base.Verdict memory verdict = RaceV2Base.Verdict(
            repo,
            race.heads().head(repo).commit,
            FIX,
            s.bounty,
            id,
            1, // the issue tier
            uint8(RaceV2Base.Outcome.Pass),
            keccak256("the result's receipt"),
            s.seed,
            keccak256(abi.encode("result", id, block.timestamp))
        );
        bytes32 result = keccak256(abi.encode(race.RESULT_TYPEHASH(), _verdictHash(verdict), keccak256("")));
        uint256 solverBefore = race.owed(s.solver, address(coin));
        uint256 botBefore = race.owed(bot, address(coin));
        race.result(verdict, new RaceV2Base.Fee[](0), _drawnSigs(_digest(result), js));
        vm.stopBroadcast();

        uint256 charged;
        for (uint256 j; j < js.length; ++j) {
            uint256 pay = race.owed(js[j], address(coin)) - owedBefore[j];
            charged += pay;
            console.log("FLOW judge", vm.toString(js[j]));
            console.log("FLOW   paid (micro-coins)", pay);
        }
        uint256 gas = race.owed(bot, address(coin)) - botBefore;
        charged += gas;
        console.log("FLOW relayer's gas repaid", gas);
        console.log("FLOW checks charged", charged);
        console.log("FLOW refunded to the solver", race.owed(s.solver, address(coin)) - solverBefore);
        console.log("FLOW recorded for the winner's refund at settlement", race.submission(id).deposit);

        // the first judge pulls its fee (credits, pulled: Article 5.3)
        uint256 pk0 = _keyOf(js[0]);
        address j0 = vm.addr(pk0);
        uint256 balance = coin.balanceOf(j0);
        vm.startBroadcast(pk0);
        race.withdraw(address(coin), j0);
        vm.stopBroadcast();
        console.log("FLOW judge 0 withdrew (micro-coins)", coin.balanceOf(j0) - balance);
    }

    // ---------- signing ----------

    function _digest(bytes32 structHash) internal view returns (bytes32) {
        return keccak256(abi.encodePacked("\x19\x01", race.domainSeparator(), structHash));
    }

    function _verdictHash(RaceV2Base.Verdict memory v) internal pure returns (bytes32) {
        return keccak256(
            abi.encode(
                keccak256(bytes(VERDICT_TYPE)),
                v.repo,
                v.base,
                v.fix,
                v.bounty,
                v.submission,
                v.tier,
                v.outcome,
                v.receiptHash,
                v.seed,
                v.nonce
            )
        );
    }

    function _keyOf(address a) internal view returns (uint256) {
        for (uint256 i; i < oracles.length; ++i) {
            if (vm.addr(oracles[i]) == a) return oracles[i];
        }
        revert("a drawn judge isn't one of the oracle roles");
    }

    /// The version's quorum of the oracle roles, in increasing signer order.
    function _quorumSigs(bytes32 digest) internal view returns (bytes[] memory sigs) {
        address[] memory as_ = new address[](oracles.length);
        uint256[] memory ks = new uint256[](oracles.length);
        for (uint256 i; i < oracles.length; ++i) {
            (as_[i], ks[i]) = (vm.addr(oracles[i]), oracles[i]);
        }
        _sort(as_, ks);
        sigs = new bytes[](quorum);
        for (uint256 i; i < quorum; ++i) {
            (uint8 v, bytes32 r, bytes32 s) = vm.sign(ks[i], digest);
            sigs[i] = abi.encodePacked(r, s, v);
        }
    }

    /// 2 of the 3 drawn judges (the issue tier's quorum), in increasing signer order.
    function _drawnSigs(bytes32 digest, address[] memory js) internal view returns (bytes[] memory sigs) {
        address[] memory as_ = new address[](js.length);
        uint256[] memory ks = new uint256[](js.length);
        for (uint256 i; i < js.length; ++i) {
            (as_[i], ks[i]) = (js[i], _keyOf(js[i]));
        }
        _sort(as_, ks);
        uint256 need = race.verdicts().ISSUE_QUORUM();
        sigs = new bytes[](need);
        for (uint256 i; i < need; ++i) {
            (uint8 v, bytes32 r, bytes32 s) = vm.sign(ks[i], digest);
            sigs[i] = abi.encodePacked(r, s, v);
        }
    }

    function _sort(address[] memory as_, uint256[] memory ks) internal pure {
        for (uint256 i = 1; i < as_.length; ++i) {
            for (uint256 j = i; j > 0 && as_[j - 1] > as_[j]; --j) {
                (as_[j - 1], as_[j]) = (as_[j], as_[j - 1]);
                (ks[j - 1], ks[j]) = (ks[j], ks[j - 1]);
            }
        }
    }
}
