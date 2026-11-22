// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Script} from "forge-std/Script.sol";
import {console} from "forge-std/console.sol";
import {RaceV2} from "../src/v2/RaceV2.sol";
import {RaceV2Base} from "../src/v2/RaceV2Base.sol";
import {Verdicts} from "../src/v2/Verdicts.sol";
import {Heads} from "../src/v2/Heads.sol";
import {IFees} from "../src/v2/IFees.sol";
import {Fees} from "../src/v2/Fees.sol";
import {Pool} from "../src/v2/Pool.sol";
import {QuoterV2} from "../src/v2/QuoterV2.sol";
import {MockCoin} from "../test/mocks/MockCoin.sol";

/// The v2 devnet deployment (proof-of-fix#85, tasks 5.1-5.4 and 5.7, design S10, S13, S15): a test coin, Verdicts (the
/// seats, each with its family, provider and operators fixed for good, some vacant; the quorum; the allowed checker
/// images and attestation types; the issue tier draws 3 of the active keys, 5.3), Fees (the check-fee meter, 5.7: the
/// unit price table, SERVICE_FEE, the caps and this repository's CI profile; bound by the race), RaceV2
/// (coin only; it deploys its companion RaceV2Annex, 5.3), Heads (deployed by RaceV2 since 5.2, its only mover: the
/// genesis head of this repository and the constitution's hash), Pool
/// (the sponsors' pot) and QuoterV2. Beside v1, not instead of it: migration is task 5.13. Run it through
/// scripts/devnet.sh deploy-v2, which passes the roles' addresses in the environment and the deployer's key on stdin:
///   DEPLOY_INFRASTRUCTURE, DEPLOY_INSURANCE      addresses
///   DEPLOY_ORACLES                               the filled seats' keys' addresses, comma-separated
///   DEPLOY_VACANT                                optional: vacant seats appended after them (task 5.4: filled later
///                                                by the join flow, scripts/devnet.sh join-v2); default 0
///   DEPLOY_QUORUM                                signatures needed (above half the seats): the constitution tier
///   DEPLOY_FAMILIES, DEPLOY_PROVIDERS            optional: each seat's model family and provider, comma-separated
///                                                names (hashed); defaults family-<i> and devnet-<i>
///   DEPLOY_IMAGES                                optional: the allowed checker image digests (0x + 64 hex), comma-
///                                                separated; default keccak256("devnet checker image")
///   DEPLOY_ATTESTATION_TYPES                     optional: accepted attestation types, comma-separated names
///                                                (hashed); default "none,aws-nitro" (none: devnet only, rule 1)
///   DEPLOY_OPERATORS, DEPLOY_OPERATOR_KEYS       optional: operators' disclosed accounts and their seats' keys,
///                                                comma-separated, pairwise (a party's seat is recused, 5.3); or
///   DEPLOY_OPERATOR_SEATS                        their seats' indices instead of keys (needed for a vacant seat)
///   DEPLOY_COMMIT                                the git commit deployed: the record's, and the genesis head (S10)
///   DEPLOY_HEAD                                  optional: the repository's genesis head when it isn't DEPLOY_COMMIT
///                                                (a target at another commit: pof-sandbox, #150)
///   DEPLOY_REPO                                  the repository whose head Heads keeps (its id is the name's keccak)
///   DEPLOY_CONSTITUTION                          the constitution's hash at genesis (0x + 64 hex)
///   DEPLOY_KEYS                                  where the keys came from (openbao or insecure-local)
///   DEPLOY_RECORD                                where to write the record (under ./deployments)
///   DEPLOY_SENDER_PK                             optional: the deployer's key, from the script's environment instead of
///                                                forge's --private-key, off every command line (devnet.sh's remote mode)
///   DEPLOY_METER                                 optional: 0 for no check-fee meter (v1's flat check deposit); default 1
///                                                (task 5.7, S15: unit costs passed through plus SERVICE_FEE). The table's
///                                                token prices come from each seat's family name (the public price lists
///                                                of pof.costs, 2026-10-30; an unknown name gets the dearest family's), the
///                                                sandbox's from Fargate, the ETH price $2,700, SERVICE_FEE $0.05
///   DEPLOY_MAX_GAS_PRICE                         optional: the meter's MAX_GAS_PRICE in wei; default 0.05 gwei (a quiet
///                                                layer 2, reports/costs-v1.md)
/// The coin is a test coin anyone can mint: devnet only, never a public chain (rule 1).
contract DeployV2Script is Script {
    uint256 constant INFLATION_PCT = 300; // #58 D3, amended: above 300 % of the merge estimate forfeits the finder's fee

    struct Deployed {
        MockCoin usd;
        Verdicts verdicts;
        Fees meter;
        RaceV2 race;
        address annex;
        Heads heads;
        Pool pool;
        QuoterV2 quoter;
    }

    function run() external {
        address[] memory oracles = vm.envAddress("DEPLOY_ORACLES", ",");
        uint256 quorum = vm.envUint("DEPLOY_QUORUM");
        string memory commit = vm.envString("DEPLOY_COMMIT");
        bytes32 repo = keccak256(bytes(vm.envOr("DEPLOY_REPO", string("example-org/proof-of-fix"))));
        bytes32 genesis = vm.parseBytes32(string.concat("0x", vm.envOr("DEPLOY_HEAD", commit), "000000000000000000000000")); // SHA-1, left-aligned
        bytes32 constitution = vm.envBytes32("DEPLOY_CONSTITUTION");

        uint256 sender = vm.envOr("DEPLOY_SENDER_PK", uint256(0));

        Deployed memory d;
        if (sender != 0) vm.startBroadcast(sender);
        else vm.startBroadcast();
        d.usd = new MockCoin("Devnet USD", "dUSD", 6);
        address[] memory feeCoins = new address[](1);
        feeCoins[0] = address(d.usd);
        Verdicts.Genesis memory g = _genesis(oracles, quorum);
        d.verdicts = new Verdicts(g);
        // v1's configuration (Deploy.s.sol): the race itself is unchanged in 5.1.
        RaceV2Base.Config memory c = _config(vm.envAddress("DEPLOY_INFRASTRUCTURE"), vm.envAddress("DEPLOY_INSURANCE"));
        bytes32[] memory repos = new bytes32[](1);
        bytes32[] memory commits = new bytes32[](1);
        repos[0] = repo;
        commits[0] = genesis;
        // The check-fee meter (task 5.7): deployed before the race, which binds it in its constructor.
        if (vm.envOr("DEPLOY_METER", uint256(1)) != 0) d.meter = new Fees(d.verdicts, _fees(address(d.usd), g, repo));
        // RaceV2 deploys its head registry (task 5.2): Heads' mover is the race, fixed at its creation.
        d.race = new RaceV2(c, feeCoins, 1_000, 100_000, d.verdicts, INFLATION_PCT, 0, repos, commits, constitution, IFees(address(d.meter)));
        d.heads = d.race.heads();
        d.annex = d.race.annex();
        d.pool = new Pool(feeCoins);
        d.quoter = new QuoterV2();
        vm.stopBroadcast();

        console.log(string.concat("COIN=", vm.toString(address(d.usd))));
        console.log(string.concat("VERDICTS=", vm.toString(address(d.verdicts))));
        console.log(string.concat("RACE=", vm.toString(address(d.race))));
        console.log(string.concat("METER=", vm.toString(address(d.meter))));
        console.log(string.concat("ANNEX=", vm.toString(d.annex)));
        console.log(string.concat("HEADS=", vm.toString(address(d.heads))));
        console.log(string.concat("POOL=", vm.toString(address(d.pool))));
        console.log(string.concat("QUOTER=", vm.toString(address(d.quoter))));
        _record(d, oracles, quorum, repo, genesis, constitution);
    }

    /// The seats (task 5.4): the filled keys, then DEPLOY_VACANT vacant seats; families, providers, the allowed images
    /// and the accepted attestation types from the environment or their devnet defaults; the operators' accounts by
    /// their seats' keys or indices.
    function _genesis(address[] memory oracles, uint256 quorum) internal view returns (Verdicts.Genesis memory g) {
        uint256 vacant = vm.envOr("DEPLOY_VACANT", uint256(0));
        uint256 n = oracles.length + vacant;
        g.keys = new address[](n);
        for (uint256 i; i < oracles.length; ++i) {
            g.keys[i] = oracles[i];
        }
        g.quorum = quorum;
        string[] memory none = new string[](0);
        string[] memory families = vm.envOr("DEPLOY_FAMILIES", ",", none);
        string[] memory providers = vm.envOr("DEPLOY_PROVIDERS", ",", none);
        g.families = new bytes32[](n);
        g.providers = new bytes32[](n);
        for (uint256 i; i < n; ++i) {
            g.families[i] = keccak256(bytes(i < families.length ? families[i] : string.concat("family-", vm.toString(i))));
            g.providers[i] = keccak256(bytes(i < providers.length ? providers[i] : string.concat("devnet-", vm.toString(i))));
        }
        bytes32[] memory images = new bytes32[](1);
        images[0] = keccak256("devnet checker image");
        g.images = vm.envOr("DEPLOY_IMAGES", ",", images);
        string[] memory types = new string[](2);
        (types[0], types[1]) = ("none", "aws-nitro");
        types = vm.envOr("DEPLOY_ATTESTATION_TYPES", ",", types);
        g.attestationTypes = new bytes32[](types.length);
        for (uint256 i; i < types.length; ++i) {
            g.attestationTypes[i] = keccak256(bytes(types[i]));
        }
        g.operators = vm.envOr("DEPLOY_OPERATORS", ",", new address[](0));
        g.operatorSeats = vm.envOr("DEPLOY_OPERATOR_SEATS", ",", new uint256[](0));
        if (g.operatorSeats.length == 0) {
            address[] memory operatorKeys = vm.envOr("DEPLOY_OPERATOR_KEYS", ",", new address[](0));
            g.operatorSeats = new uint256[](operatorKeys.length);
            for (uint256 j; j < operatorKeys.length; ++j) {
                g.operatorSeats[j] = type(uint256).max; // a key not in the set: the constructor refuses it
                for (uint256 i; i < n; ++i) {
                    if (g.keys[i] == operatorKeys[j]) g.operatorSeats[j] = i;
                }
            }
        }
    }

    /// The meter's genesis (task 5.7, S15): a price per seat family (by its name), the sandbox, storage, ETH and
    /// SERVICE_FEE; the constitution's caps (twice reports/costs-v1.md's large review); this repository's CI profile
    /// (2 vCPU, 4 GB, 20 minutes, as pof.checkgas); CI_SINGLE_RUN off.
    function _fees(address coin, Verdicts.Genesis memory g, bytes32 repo) internal view returns (Fees.Genesis memory f) {
        string[] memory none = new string[](0);
        string[] memory names = vm.envOr("DEPLOY_FAMILIES", ",", none);
        uint256 n = g.families.length; // distinct: Verdicts refuses two seats of one family (S13)
        f.coin = coin;
        f.families = g.families;
        f.prices = new uint256[](3 * n + 5);
        for (uint256 i; i < n; ++i) {
            (f.prices[3 * i], f.prices[3 * i + 1], f.prices[3 * i + 2]) = _tokenPrices(i < names.length ? names[i] : "");
        }
        // the sandbox (Fargate, per million vCPU- and GB-seconds), storage (a year of S3, per million MB), ETH, the fee
        (f.prices[3 * n], f.prices[3 * n + 1], f.prices[3 * n + 2], f.prices[3 * n + 3], f.prices[3 * n + 4]) =
            (11_244_444, 1_234_722, 269_531_250, 2_700_000_000, 50_000);
        // RELAYER_GAS_OVERHEAD: what the result's call can't measure itself (the transaction's base and calldata, the
        // meter's settle and the credits after it): 536,636 gas with 3 reports on the devnet (FeesFlowV2, 2026-11-02).
        f.caps = Fees.Caps(
            140_000, 16_000, 20, 1_000_000, 540_000, uint64(vm.envOr("DEPLOY_MAX_GAS_PRICE", uint256(0.05 gwei)))
        );
        f.repos = new bytes32[](1);
        f.repos[0] = repo;
        f.profiles = new Fees.Profile[](1);
        f.profiles[0] = Fees.Profile(keccak256("python:3.12-alpine test image"), 2_000, 4_096, 1_200);
        f.defaultProfile = f.profiles[0];
    }

    /// A family's public prices, micro-coins per million tokens: input, cached, output (pof.costs JUDGE, 2026-10-30).
    function _tokenPrices(string memory name) internal pure returns (uint256, uint256, uint256) {
        bytes32 h = keccak256(bytes(name));
        if (h == keccak256("openai")) return (2_000_000, 100_000, 10_000_000);
        if (h == keccak256("google")) return (2_000_000, 200_000, 12_000_000);
        if (h == keccak256("deepseek")) return (1_320_000, 44_000, 3_960_000);
        if (h == keccak256("qwen")) return (1_500_000, 1_500_000, 4_500_000);
        if (h == keccak256("mistral")) return (500_000, 50_000, 1_500_000);
        if (h == keccak256("llama")) return (500_000, 500_000, 770_000);
        return (4_000_000, 200_000, 20_000_000); // anthropic, and any family not listed: the dearest
    }

    /// v1's configuration, field for field (Deploy.s.sol's config: pof's defaults, no market fee, D9).
    function _config(address infrastructure, address insurance) internal pure returns (RaceV2Base.Config memory c) {
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
    function _record(
        Deployed memory d,
        address[] memory oracles,
        uint256 quorum,
        bytes32 repo,
        bytes32 genesis,
        bytes32 constitution
    ) internal {
        string memory k = "deploymentV2";
        vm.serializeString(k, "version", "2");
        vm.serializeUint(k, "chainId", block.chainid);
        vm.serializeUint(k, "block", block.number);
        vm.serializeString(k, "commit", vm.envOr("DEPLOY_COMMIT", string("")));
        vm.serializeString(k, "keys", vm.envOr("DEPLOY_KEYS", string("openbao")));
        vm.serializeAddress(k, "coin", address(d.usd));
        vm.serializeAddress(k, "verdicts", address(d.verdicts));
        vm.serializeAddress(k, "race", address(d.race));
        vm.serializeAddress(k, "meter", address(d.meter));
        vm.serializeBytes32(k, "meterCodehash", address(d.meter).codehash);
        if (address(d.meter) != address(0)) {
            vm.serializeUint(k, "serviceFee", d.meter.serviceFee());
            vm.serializeUint(k, "maxCheckDeposit", d.meter.maxDeposit(repo));
        }
        vm.serializeAddress(k, "annex", d.annex);
        vm.serializeAddress(k, "heads", address(d.heads));
        vm.serializeAddress(k, "pool", address(d.pool));
        vm.serializeAddress(k, "quoter", address(d.quoter));
        vm.serializeBytes32(k, "verdictsCodehash", address(d.verdicts).codehash);
        vm.serializeBytes32(k, "raceCodehash", address(d.race).codehash);
        vm.serializeBytes32(k, "annexCodehash", d.annex.codehash);
        vm.serializeBytes32(k, "headsCodehash", address(d.heads).codehash);
        vm.serializeBytes32(k, "poolCodehash", address(d.pool).codehash);
        vm.serializeBytes32(k, "quoterCodehash", address(d.quoter).codehash);
        vm.serializeUint(k, "raceCodeSize", address(d.race).code.length);
        vm.serializeUint(k, "inflationPct", INFLATION_PCT);
        vm.serializeBytes32(k, "repo", repo);
        vm.serializeBytes32(k, "genesisHead", genesis);
        vm.serializeBytes32(k, "constitution", constitution);
        vm.serializeAddress(k, "oracles", oracles);
        vm.serializeUint(k, "seats", d.verdicts.seatCount());
        vm.serializeUint(k, "vacantSeats", d.verdicts.seatCount() - oracles.length);
        vm.serializeUint(k, "keyRotationDelay", d.verdicts.KEY_ROTATION_DELAY());
        string memory json = vm.serializeUint(k, "quorum", quorum);
        vm.writeJson(json, string.concat("./", vm.envOr("DEPLOY_RECORD", string("deployments/devnet-v2.json"))));
    }
}
