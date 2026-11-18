// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Oracles} from "../test/helpers/Oracles.sol";
import {Race} from "../src/Race.sol";
import {Quoter} from "../src/Quoter.sol";
import {Token} from "../src/Token.sol";
import {MockCoin} from "../test/mocks/MockCoin.sol";
import {console} from "forge-std/console.sol";

/// Task 3.3 (design D8, phase 4): the chain side of the local bounty loop (scripts/bounty-loop.sh). The deployment,
/// and the oracle stand-in's signed results: the test oracle keys of task 3.1 ("oracle0".."oracle2", quorum 2 of 3)
/// sign each result's EIP-712 digest, and whoever runs the script relays it (`--private-key`). Run only against the
/// loop's throwaway anvil or the private devnet, never a public chain. On the devnet (#93, `bounty-loop.sh --devnet`)
/// the oracle keys come from the environment instead: ORACLE_KEYS (comma-separated, from OpenBao) and
/// ORACLE_QUORUM.
/// Each function prints `NAME=value` lines the bot reads.
contract LoopScript is Oracles {
    uint256 constant C = 1e6;
    uint256 constant ORACLE_FEE = 0.3e6; // each signing oracle's fee for checking a submission, from its deposit

    /// The oracle set: the devnet's keys from the environment (#93), else the test keys "oracle0".."oracle2", 2 of 3.
    function _oracles() internal {
        uint256[] memory keys = vm.envOr("ORACLE_KEYS", ",", new uint256[](0));
        if (keys.length == 0) return _makeOracles(3, 2);
        delete oracleSecrets;
        delete oracleSet;
        for (uint256 i; i < keys.length; ++i) {
            oracleSet.push(vm.addr(keys[i]));
            oracleSecrets.push(keys[i]);
            for (uint256 j = oracleSet.length - 1; j > 0 && oracleSet[j - 1] > oracleSet[j]; --j) {
                (oracleSet[j - 1], oracleSet[j]) = (oracleSet[j], oracleSet[j - 1]);
                (oracleSecrets[j - 1], oracleSecrets[j]) = (oracleSecrets[j], oracleSecrets[j - 1]);
            }
        }
        oracleQuorum = vm.envUint("ORACLE_QUORUM");
    }

    /// The coin, the Token and its Race, the Quoter, and 1,000 coins to each holder. The token's rules are pof's
    /// TOKENS (the Oracles helper's), its founder the address given; its only recorder is the Race deployed right
    /// after it, whose address is known in advance (D15: nothing links them later).
    function deploy(address infrastructure, address insurance, address founder_, address[] calldata holders)
        external
    {
        _oracles();
        vm.startBroadcast();
        (, address deployer,) = vm.readCallers();
        MockCoin usd = new MockCoin("Mock USD", "mUSD", 6);
        address[] memory feeCoins = new address[](1);
        feeCoins[0] = address(usd);
        Race.Config memory c = _config(infrastructure, insurance);
        Token token = new Token(
            vm.computeCreateAddress(deployer, vm.getNonce(deployer) + 1), founder_, tokenEmission, tokenDecayBps,
            founderBps, founderPeriods, reporterBps, c.releaseEveryDays, inflationPct,
            graceDays, Token(address(0))
        );
        Race race = new Race(c, feeCoins, 1_000, 100_000, oracleSet, oracleQuorum, token);
        Quoter quoter = new Quoter();
        for (uint256 i; i < holders.length; ++i) {
            usd.mint(holders[i], 1_000 * C);
        }
        vm.stopBroadcast();
        console.log(string.concat("COIN=", vm.toString(address(usd))));
        console.log(string.concat("RACE=", vm.toString(address(race))));
        console.log(string.concat("QUOTER=", vm.toString(address(quoter))));
        console.log(string.concat("TOKEN=", vm.toString(address(token))));
        for (uint256 i; i < oracleQuorum; ++i) {
            console.log(string.concat("ORACLE", vm.toString(i), "=", vm.toString(oracleSet[i])));
        }
    }

    /// The registration check passed: the issue's bounty opens, with the check's importance estimate (#58 D3).
    function accept(Race race, uint256 issueId, uint256 weight, bytes32 nonce) external {
        _oracles();
        Race.Signed memory a = _signed(race, _acceptHash(issueId, weight, nonce), nonce);
        vm.startBroadcast();
        uint256 b = race.accept(issueId, weight, a);
        vm.stopBroadcast();
        console.log(string.concat("BOUNTY=", vm.toString(b)));
    }

    /// A submission's checked result (1 pass, 2 fail): the signing oracles' fees come from its deposit.
    function result(Race race, uint256 id, uint8 outcome, bytes32 fix, bytes32 nonce) external {
        _oracles();
        Race.Fee[] memory fees = new Race.Fee[](oracleQuorum);
        for (uint256 i; i < oracleQuorum; ++i) {
            fees[i] = Race.Fee(oracleSet[i], ORACLE_FEE);
        }
        Race.Outcome o = Race.Outcome(outcome);
        Race.Signed memory a =
            _signed(race, _resultHash(id, race.submission(id).bounty, o, fix, fees, nonce), nonce);
        vm.startBroadcast();
        race.result(id, o, fix, fees, a);
        vm.stopBroadcast();
        console.log(string.concat("STATE=", vm.toString(uint256(race.bounty(race.submission(id).bounty).state))));
    }

    /// The winning fix was merged in the repository: its award starts, with the second importance estimate (#58 D3).
    function merged(Race race, uint256 b, uint256 weight, bytes32 nonce) external {
        _oracles();
        uint256 winner = race.bounty(b).winner;
        Race.Signed memory a = _signed(race, _mergedHash(b, winner, weight, nonce), nonce);
        vm.startBroadcast();
        race.merged(b, winner, weight, a);
        vm.stopBroadcast();
        console.log(string.concat("STATE=", vm.toString(uint256(race.bounty(b).state))));
    }

    /// pof's defaults for the race, with no market fee (D9), as in Quote.s.sol.
    function _config(address infrastructure, address insurance) internal pure returns (Race.Config memory c) {
        c.infrastructure = infrastructure;
        c.insurance = insurance;
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
    }
}
