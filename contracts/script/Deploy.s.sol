// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Script} from "forge-std/Script.sol";
import {console} from "forge-std/console.sol";
import {Race} from "../src/Race.sol";
import {Quoter} from "../src/Quoter.sol";
import {Token} from "../src/Token.sol";
import {MockCoin} from "../test/mocks/MockCoin.sol";

/// The devnet deployment (proof-of-fix#93): a test coin, the Token, its Race (linked to the OracleAuth library, which
/// forge deploys first) and the Quoter, with the oracle keys and quorum fixed here for good (D3, D15). Run it through
/// scripts/devnet.sh deploy, which passes the roles' addresses in the environment and the deployer's key on stdin:
///   DEPLOY_INFRASTRUCTURE, DEPLOY_INSURANCE, DEPLOY_FOUNDER  addresses
///   DEPLOY_ORACLES                                           the oracle keys' addresses, comma-separated
///   DEPLOY_QUORUM                                            signatures needed (above half the keys)
///   DEPLOY_COMMIT                                            the git commit deployed, for the record
///   DEPLOY_KEYS                                              where the keys came from (openbao or insecure-local)
///   DEPLOY_RECORD                                            where to write the record (under ./deployments)
/// The coin is a test coin anyone can mint: devnet only, never a public chain (rule 1).
contract DeployScript is Script {
    uint256 constant C = 1e6;

    function run() external {
        address infrastructure = vm.envAddress("DEPLOY_INFRASTRUCTURE");
        address insurance = vm.envAddress("DEPLOY_INSURANCE");
        address founder = vm.envAddress("DEPLOY_FOUNDER");
        address[] memory oracles = vm.envAddress("DEPLOY_ORACLES", ",");
        uint256 quorum = vm.envUint("DEPLOY_QUORUM");

        vm.startBroadcast();
        (, address deployer,) = vm.readCallers();
        MockCoin usd = new MockCoin("Devnet USD", "dUSD", 6);
        address[] memory feeCoins = new address[](1);
        feeCoins[0] = address(usd);
        Race.Config memory c = config(infrastructure, insurance);
        // The token's only recorder is the Race deployed right after it, whose address is known in advance (D15).
        Token token = new Token(
            vm.computeCreateAddress(deployer, vm.getNonce(deployer) + 1), founder, 10_000 * C, 100, 100, 208, 1_500,
            c.releaseEveryDays, 300, 7, Token(address(0))
        );
        Race race = new Race(c, feeCoins, 1_000, 100_000, oracles, quorum, token);
        Quoter quoter = new Quoter();
        vm.stopBroadcast();

        console.log(string.concat("COIN=", vm.toString(address(usd))));
        console.log(string.concat("TOKEN=", vm.toString(address(token))));
        console.log(string.concat("RACE=", vm.toString(address(race))));
        console.log(string.concat("QUOTER=", vm.toString(address(quoter))));
        record(usd, token, race, quoter, oracles, quorum);
    }

    /// pof's defaults for the race, with no market fee (D9), as in Loop.s.sol and Quote.s.sol.
    function config(address infrastructure, address insurance) public pure returns (Race.Config memory c) {
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

    /// The deployment record: what was deployed, where, from which commit, and the runtime code hashes to check it by.
    function record(MockCoin usd, Token token, Race race, Quoter quoter, address[] memory oracles, uint256 quorum)
        internal
    {
        string memory k = "deployment";
        vm.serializeUint(k, "chainId", block.chainid);
        vm.serializeUint(k, "block", block.number);
        vm.serializeString(k, "commit", vm.envOr("DEPLOY_COMMIT", string("")));
        // Where the keys came from: "openbao" (the owner's devnet keys) or "insecure-local" (anvil's public mnemonic).
        vm.serializeString(k, "keys", vm.envOr("DEPLOY_KEYS", string("openbao")));
        vm.serializeAddress(k, "coin", address(usd));
        vm.serializeAddress(k, "token", address(token));
        vm.serializeAddress(k, "race", address(race));
        vm.serializeAddress(k, "quoter", address(quoter));
        vm.serializeBytes32(k, "raceCodehash", address(race).codehash);
        vm.serializeBytes32(k, "tokenCodehash", address(token).codehash);
        vm.serializeBytes32(k, "quoterCodehash", address(quoter).codehash);
        vm.serializeUint(k, "raceCodeSize", address(race).code.length);
        vm.serializeAddress(k, "oracles", oracles);
        string memory json = vm.serializeUint(k, "quorum", quorum);
        vm.writeJson(json, string.concat("./", vm.envOr("DEPLOY_RECORD", string("deployments/devnet.json"))));
    }
}
