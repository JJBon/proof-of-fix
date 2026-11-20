// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Script} from "forge-std/Script.sol";
import {console} from "forge-std/console.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {Validators} from "../src/v3/Validators.sol";
import {IValidators} from "../src/v3/IValidators.sol";
import {FeesV3} from "../src/v3/FeesV3.sol";
import {IFeesV3, IFeesV3Validators} from "../src/v3/IFeesV3.sol";
import {Panels} from "../src/v3/Panels.sol";
import {IPanelsRegistry, IPanelsFees, IPanelScores} from "../src/v3/IPanels.sol";
import {PanelScores} from "../src/v3/PanelScores.sol";
import {PoolV3} from "../src/v3/PoolV3.sol";
import {RaceV3} from "../src/v3/RaceV3.sol";
import {RaceV3Annex} from "../src/v3/RaceV3Annex.sol";
import {RaceV3Endings} from "../src/v3/RaceV3Endings.sol";
import {RaceV3Base} from "../src/v3/RaceV3Base.sol";
import {Windows, WindowsLib} from "../src/v3/Windows.sol";
import {TestCoin} from "../src/v3/TestCoin.sol";
import {CoinFaucet} from "../src/v3/CoinFaucet.sol";
import {RegistryMaker} from "./RegistryMaker.sol";

/// The Sepolia deployment of v3 (proof-of-fix#251, task 3.9; design L3, L17, L18; specs/deployment-binding). Run it
/// through scripts/deploy-sepolia.sh, which reads the endpoint's chain id before anything is signed, refuses the local
/// ids for a non-local endpoint, checks the release-candidate record and the Radicle repository's genesis head
/// (`pofctl verify-head`), and passes `--broadcast` to forge only with `--broadcast-sepolia`. Run alone, forge
/// simulates and sends nothing unless given `--broadcast`.
///
/// `run()` checks again, before the first transaction: the chain (11155111, or the local test ids 31337 and 7193, as
/// LaunchChain); every contract's creation-code hash against the release-candidate record's (L18: it names the one
/// that differs); the genesis mint (at least the genesis bond); and the genesis validator's signature for the
/// registry's address. Then it deploys, in reports/contract-v3.md's order: CoinFaucet, which creates the fee coin,
/// TestCoin ("proof-of-fix test coin", POFTEST, 6 decimals; L17 as amended on 2026-11-20, in place of Circle's USDC),
/// with its genesis mint (the genesis validator's $250 bond to the registry maker's address, the rest to the recipient
/// named at deploy), the same coin on Sepolia and on the local ids; PoolV3, RegistryMaker (which creates Validators
/// with the one genesis validator and its $250 bond), PanelScores, FeesV3, Panels, RaceV3Endings, RaceV3Annex (which checks the endings) and RaceV3
/// (which deploys Heads and its SolverBook), with the production windows (L4: APPEAL_WINDOW 72 h and ACTIVE_WINDOW 26
/// weeks among them), TEE only (L10), the pure taxi fare (`judgeFee` 0: a solver pays only the metered validation,
/// owner 2026-11-19; no attempt, evaluation or appeal fee), and the reporter's fees paid to the sponsors' pool (L17,
/// rule 3). The deployer has no role afterwards (L3, D15). It writes the deployment record:
/// the chain id, every address, every constructor argument (decoded, and ABI-encoded as appended to the creation
/// code), the deployer, the bytecode hashes and the limit of the binding.
///
/// `hashes()` prints each contract's creation-code hash (`BYTECODE <name> <hash>`), for a release-candidate record.
///
/// The environment (scripts/deploy-sepolia.sh sets it from the deployment plan):
///   DEPLOY_DEPLOYER              the deploying address (it signs every transaction; no role afterwards)
///   DEPLOY_RECORD                where to write the record, under ./deployments
///   DEPLOY_RC_NAMES, _HASHES     the release-candidate record's contracts and creation-code hashes, comma-separated
///   DEPLOY_GENESIS_MINT          the test coin's genesis mint in micro-coins, in total (default 5,000 coins): the
///                                genesis bond goes to the registry maker, the rest to DEPLOY_GENESIS_MINT_TO
///   DEPLOY_GENESIS_MINT_TO       the genesis mint's recipient (default the deployer)
///   DEPLOY_RID                   the Radicle RID; the repository id is keccak256 of it
///   DEPLOY_GENESIS_HEAD          its genesis head, bytes32 (the commit's SHA-1, left-aligned)
///   DEPLOY_CONSTITUTION          keccak256 of CONSTITUTION.md at the release candidate
///   DEPLOY_FAMILIES              the model families priced from the start, comma-separated; the first is the genesis
///                                validator's
///   DEPLOY_TEE_TYPES             the accepted TEE types, comma-separated names
///   DEPLOY_IMAGES                the accepted checker images, comma-separated bytes32 digests
///   DEPLOY_GENESIS_KEY, _OPERATOR, _TEE_TYPE (a name), _LEVEL (1 = A, 2 = B), _ATTESTATION, _IMAGE, _HOST,
///   _FIRMWARE (default 0)        the genesis validator's registration (proof type `tee`)
///   DEPLOY_GENESIS_RAD_NODE      its Radicle node's Ed25519 public key, bytes32 (#251, L11: the key its did:key names;
///                                signed in the registration, stored on-chain); never 0 for the genesis validator
///   DEPLOY_GENESIS_SIG           its signature over the registration digest for the registry's address (printed as
///                                GENESIS_DIGEST); or, on a local endpoint only, DEPLOY_GENESIS_PK, a test key, to sign
///                                here (the wrapper refuses it for any other endpoint)
contract DeploySepoliaScript is Script {
    uint256 internal constant SEPOLIA = 11_155_111;
    /// The test coin's genesis mint by default: 5,000 coins (L17, 2026-11-20): 15 launch validators' $250 bonds
    /// (3,750, the genesis validator's included) and 1,250 to seed bounties.
    uint256 internal constant GENESIS_MINT = 5_000e6;
    uint256 internal constant N = 11;
    /// The judges' fee on Sepolia: 0, the pure taxi fare (owner, 2026-11-19; ADR 0007's D30 for the launch). A fix posts
    /// FeesV3's worst-case deposit, its judges are paid by the meter, and the rest returns to the solver. The race's
    /// `Config.judgeFee`, a constructor argument of RaceV3, RaceV3Annex and RaceV3Endings; a flat fee (above 0) is left
    /// to a later mainnet decision.
    uint256 internal constant JUDGES_FEE = 0;
    /// The CI profile's time limit for one check, its two test runs together (#251 L22, task 4.10).
    uint32 internal constant SEPOLIA_TIMEOUT_S = 2_400;
    /// The genesis validator's bond, $250 (L17): a single judge's bounty limit is then $125.
    uint256 internal constant GENESIS_BOND = 250e6;
    uint256 internal constant BOUNTY_CAP = 625;
    uint256 internal constant TOTAL_CAP = 100_000;
    /// The limit of the binding (deployment-binding, "The binding is stated as a limit of this deployment").
    string internal constant LIMIT = "The repository check (one repository, keccak256 of its Radicle RID) and the chain "
        "check (Sepolia, chain id 11155111) bind this deployment only. The code is open: a fork can remove both checks "
        "and deploy it anywhere without them.";

    struct Deployed {
        address coin;
        CoinFaucet faucet;
        PoolV3 pool;
        RegistryMaker maker;
        Validators reg;
        PanelScores scores;
        FeesV3 fees;
        Panels panels;
        RaceV3Endings endings;
        RaceV3Annex annex;
        RaceV3 race;
        uint256 start;
    }

    struct Plan {
        address deployer;
        bool local;
        string rid;
        bytes32 repo;
        bytes32 head;
        bytes32 constitution;
        string[] familyNames;
        bytes32[] families;
        string[] teeNames;
        bytes32[] teeTypes;
        bytes32[] images;
        string genesisTee;
        Windows windows;
        uint256 genesisMint;
        address genesisMintTo;
    }

    // ---------- the release candidate's contracts ----------

    // RaceV3's creation code holds Heads' and SolverBook's (it deploys both), so its hash covers them; CoinFaucet's holds
    // TestCoin's, which is listed too (L17, 2026-11-20).
    function _names() internal pure returns (string[N] memory) {
        return [
            "TestCoin",
            "CoinFaucet",
            "PoolV3",
            "RegistryMaker",
            "Validators",
            "PanelScores",
            "FeesV3",
            "Panels",
            "RaceV3Endings",
            "RaceV3Annex",
            "RaceV3"
        ];
    }

    function _codes() internal pure returns (bytes[N] memory) {
        return [
            type(TestCoin).creationCode,
            type(CoinFaucet).creationCode,
            type(PoolV3).creationCode,
            type(RegistryMaker).creationCode,
            type(Validators).creationCode,
            type(PanelScores).creationCode,
            type(FeesV3).creationCode,
            type(Panels).creationCode,
            type(RaceV3Endings).creationCode,
            type(RaceV3Annex).creationCode,
            type(RaceV3).creationCode
        ];
    }

    /// Each contract's creation-code hash, as a release-candidate record lists them.
    function hashes() external pure {
        string[N] memory names = _names();
        bytes[N] memory codes = _codes();
        for (uint256 i; i < N; ++i) {
            console.log(string.concat("BYTECODE ", names[i], " ", vm.toString(keccak256(codes[i]))));
        }
    }

    /// L18: every contract this script deploys has the record's creation-code hash, and the record names no other.
    function _checkReleaseCandidate() internal view {
        string[] memory names = vm.envString("DEPLOY_RC_NAMES", ",");
        bytes32[] memory want = vm.envBytes32("DEPLOY_RC_HASHES", ",");
        if (names.length != want.length || names.length != N) {
            revert("release candidate: the record must name exactly the 11 contracts this script deploys");
        }
        string[N] memory ours = _names();
        bytes[N] memory codes = _codes();
        for (uint256 i; i < N; ++i) {
            bool found;
            for (uint256 j; j < names.length; ++j) {
                if (keccak256(bytes(names[j])) != keccak256(bytes(ours[i]))) continue;
                found = true;
                if (want[j] != keccak256(codes[i])) {
                    revert(string.concat("release candidate: the bytecode of ", ours[i], " differs from the record"));
                }
            }
            if (!found) revert(string.concat("release candidate: the record has no bytecode hash for ", ours[i]));
        }
    }

    // ---------- the deployment ----------

    function run() external {
        uint256 id = block.chainid;
        if (id != SEPOLIA && id != 31_337 && id != 7_193) {
            revert(string.concat("chain ", vm.toString(id), " refused: Sepolia (11155111) only"));
        }
        _checkReleaseCandidate();
        Plan memory p = _plan(id != SEPOLIA);
        IValidators.Registration memory r = _registration(p);

        // the addresses before anything is sent: the faucet (which creates the coin) and the pool come first, then
        // the maker, which the genesis mint pays the genesis bond to
        uint64 nonce = vm.getNonce(p.deployer);
        address makerAt = vm.computeCreateAddress(p.deployer, nonce + 2);
        address registryAt = vm.computeCreateAddress(makerAt, 1);
        bytes memory sig = _signature(registryAt, r);

        Deployed memory d = _deploy(p, r, sig, makerAt);
        _record(p, r, sig, d);
        console.log(string.concat("RACE=", vm.toString(address(d.race))));
    }

    function _plan(bool local) internal view returns (Plan memory p) {
        p.deployer = vm.envAddress("DEPLOY_DEPLOYER");
        p.local = local;
        p.rid = vm.envString("DEPLOY_RID");
        if (bytes(p.rid).length == 0) revert("no Radicle RID");
        p.repo = keccak256(bytes(p.rid));
        p.head = vm.envBytes32("DEPLOY_GENESIS_HEAD");
        if (p.head == bytes32(0)) revert("no genesis head");
        p.constitution = vm.envBytes32("DEPLOY_CONSTITUTION");
        p.familyNames = vm.envString("DEPLOY_FAMILIES", ",");
        p.families = _hashed(p.familyNames);
        p.teeNames = vm.envString("DEPLOY_TEE_TYPES", ",");
        p.teeTypes = _hashed(p.teeNames);
        p.images = vm.envBytes32("DEPLOY_IMAGES", ",");
        p.genesisTee = vm.envString("DEPLOY_GENESIS_TEE_TYPE");
        p.windows = WindowsLib.production();
        p.genesisMint = vm.envOr("DEPLOY_GENESIS_MINT", GENESIS_MINT);
        if (p.genesisMint < GENESIS_BOND) revert("the genesis mint is less than the genesis bond (250 coins)");
        p.genesisMintTo = vm.envOr("DEPLOY_GENESIS_MINT_TO", p.deployer);
        if (p.genesisMintTo == address(0)) revert("no recipient for the genesis mint");
    }

    function _registration(Plan memory p) internal view returns (IValidators.Registration memory r) {
        r = IValidators.Registration({
            key: vm.envAddress("DEPLOY_GENESIS_KEY"),
            operator: vm.envAddress("DEPLOY_GENESIS_OPERATOR"),
            proofType: keccak256("tee"),
            teeType: keccak256(bytes(p.genesisTee)),
            level: uint8(vm.envUint("DEPLOY_GENESIS_LEVEL")),
            attestation: vm.envBytes32("DEPLOY_GENESIS_ATTESTATION"),
            image: vm.envBytes32("DEPLOY_GENESIS_IMAGE"),
            host: vm.envBytes32("DEPLOY_GENESIS_HOST"),
            family: p.families[0],
            firmware: uint32(vm.envOr("DEPLOY_GENESIS_FIRMWARE", uint256(0))),
            radNode: vm.envBytes32("DEPLOY_GENESIS_RAD_NODE")
        });
        if (r.radNode == bytes32(0)) revert("no Radicle node key for the genesis validator");
    }

    /// The genesis validator's signature for the registry at `registryAt`: given (its key stays in its enclave), or
    /// made here from a local test key. Printed first, so a validator can sign what the dry run shows.
    function _signature(address registryAt, IValidators.Registration memory r) internal view returns (bytes memory sig) {
        bytes32 digest = _digest(registryAt, r);
        console.log(string.concat("GENESIS_REGISTRY=", vm.toString(registryAt)));
        console.log(string.concat("GENESIS_DIGEST=", vm.toString(digest)));
        uint256 pk = vm.envOr("DEPLOY_GENESIS_PK", uint256(0));
        if (pk != 0) {
            (uint8 v, bytes32 rr, bytes32 s) = vm.sign(pk, digest);
            sig = abi.encodePacked(rr, s, v);
        } else {
            sig = vm.envOr("DEPLOY_GENESIS_SIG", bytes(""));
        }
        (address signer, ECDSA.RecoverError err,) = ECDSA.tryRecover(digest, sig);
        if (err != ECDSA.RecoverError.NoError || signer != r.key) {
            revert(
                string.concat(
                    "the genesis validator's signature is missing or isn't over GENESIS_DIGEST ",
                    vm.toString(digest),
                    " (the registry at ",
                    vm.toString(registryAt),
                    ")"
                )
            );
        }
    }

    /// The test coin's genesis mint (L17): the genesis bond to the registry maker, which bonds it into Validators at
    /// construction; the rest to the recipient named at deploy.
    function _mint(Plan memory p, address makerAt) internal pure returns (address[] memory to, uint256[] memory amounts) {
        to = new address[](2);
        amounts = new uint256[](2);
        (to[0], amounts[0]) = (makerAt, GENESIS_BOND);
        (to[1], amounts[1]) = (p.genesisMintTo, p.genesisMint - GENESIS_BOND);
    }

    function _deploy(Plan memory p, IValidators.Registration memory r, bytes memory sig, address makerAt)
        internal
        returns (Deployed memory d)
    {
        vm.startBroadcast(p.deployer);
        (address[] memory to, uint256[] memory amounts) = _mint(p, makerAt);
        d.faucet = new CoinFaucet(to, amounts);
        d.coin = address(d.faucet.coin());
        d.pool = new PoolV3(_one(d.coin));
        d.maker = new RegistryMaker();
        require(address(d.maker) == makerAt, "the registry maker isn't where the genesis signature expects it");
        require(IERC20(d.coin).balanceOf(makerAt) == GENESIS_BOND, "the registry maker doesn't hold the genesis bond");
        d.reg = Validators(
            d.maker.make(
                IERC20(d.coin),
                GENESIS_BOND,
                abi.encodePacked(type(Validators).creationCode, abi.encode(_genesis(p, r, sig, d)))
            )
        );
        d.scores = new PanelScores();
        d.fees = new FeesV3(IFeesV3Validators(address(d.reg)), d.scores, _fees(d.coin, p));
        d.panels = new Panels(
            IPanelsRegistry(address(d.reg)), IPanelsFees(address(d.fees)), IPanelScores(address(d.scores)), p.teeTypes, p.windows
        );
        d.start = block.timestamp;
        RaceV3Base.Config memory c = _config(address(d.pool));
        d.endings = new RaceV3Endings(c, BOUNTY_CAP, TOTAL_CAP, d.panels, d.pool, d.start);
        d.annex = new RaceV3Annex(c, BOUNTY_CAP, TOTAL_CAP, d.panels, d.pool, d.start, d.endings);
        d.race = new RaceV3(c, BOUNTY_CAP, TOTAL_CAP, d.panels, d.pool, d.start, p.repo, p.head, p.constitution, d.annex);
        vm.stopBroadcast();
    }

    function _genesis(Plan memory p, IValidators.Registration memory r, bytes memory sig, Deployed memory d)
        internal
        pure
        returns (Validators.Genesis memory g)
    {
        g.coin = d.coin;
        g.pool = address(d.pool);
        g.proofTypes = new bytes32[](1);
        g.proofTypes[0] = keccak256("tee");
        g.teeTypes = p.teeTypes;
        g.images = p.images;
        g.validators = new IValidators.Registration[](1);
        g.validators[0] = r;
        g.signatures = new bytes[](1);
        g.signatures[0] = sig;
        g.bonds = new uint256[](1);
        g.bonds[0] = GENESIS_BOND;
        g.windows = p.windows;
        g.teeOnly = true;
    }

    /// The contract tests' prices (test/v3/helpers/PanelsSetup.sol, as NodeV3Local): the list prices of 2026-10-30
    /// and Fargate's rates. They move by FeesV3's own rules once validators post their tables.
    function _fees(address coin, Plan memory p) internal pure returns (FeesV3.Genesis memory g) {
        g.coin = coin;
        g.shared = [uint256(11_244_444), 1_234_722, 269_531_250, 2_700_000_000];
        g.families = p.families;
        g.tokens = new uint256[3][](p.families.length);
        for (uint256 i; i < p.families.length; ++i) {
            g.tokens[i] = [uint256(4_000_000), 200_000, 20_000_000];
        }
        g.caps = IFeesV3.Caps(140_000, 16_000, 20, 1_000_000, 50_000, 1 gwei);
        g.repo = p.repo;
        // The time limit is the whole check's, and each of its two runs gets half (#251 L22): 2,400 s gives each run
        // 1,200 s, about 2.3 times the 513 s one run of proof-of-fix's suite took in the sandbox (1 vCPU, 2026-11-19),
        // so the suite can grow. FeesV3's worst-case deposit stays a true bound.
        g.profile = IFeesV3.Profile(keccak256("image"), 2_000, 4_096, SEPOLIA_TIMEOUT_S);
    }

    /// The race's configuration: the contract tests' amounts and days (as NodeV3Local), with the infrastructure fees
    /// and a junk issue's stake paid to the sponsors' pool, not to any address of the owner (L17, rule 3). A solver pays
    /// only the metered validation on Sepolia (owner, 2026-11-19): no attempt, evaluation (late submission) or appeal
    /// fee, and the taxi fare (`judgeFee` 0). The reporter's registration fee and issue stake stay.
    function _config(address pool) internal pure returns (RaceV3Base.Config memory c) {
        c.infrastructure = pool;
        c.insurance = pool;
        c.registrationFee = 2e6;
        c.issueStake = 5e6;
        c.attemptFee = 0;
        c.evaluationFee = 0;
        c.appealFee = 0;
        c.challengeStake = 10e6;
        c.startPriceBps = 5_000;
        c.riseBpsPerDay = 1_000;
        c.finderFeeBps = 1_765;
        c.idleDays = 28;
        c.resultDays = 7;
        c.mergeDays = 14;
        c.releaseEveryDays = 7;
        c.instalments = 4;
        c.judgeFee = JUDGES_FEE;
    }

    // ---------- the record ----------

    function _record(Plan memory p, IValidators.Registration memory r, bytes memory sig, Deployed memory d) internal {
        string memory o = "record";
        vm.serializeUint(o, "version", 3);
        vm.serializeString(o, "network", p.local ? "local" : "sepolia");
        vm.serializeUint(o, "chainId", block.chainid);
        vm.serializeAddress(o, "deployer", p.deployer);
        vm.serializeString(o, "limit", LIMIT);
        vm.serializeString(o, "rid", p.rid);
        vm.serializeBytes32(o, "repo", p.repo);
        vm.serializeBytes32(o, "genesisHead", p.head);
        vm.serializeBytes32(o, "constitution", p.constitution);
        vm.serializeAddress(o, "coin", d.coin);
        vm.serializeString(o, "coinKind", "the project's test coin, no value (TestCoin, minted only by its faucet)");
        vm.serializeString(o, "testCoin", _testCoin(p, d));
        vm.serializeBool(o, "teeOnly", d.reg.teeOnly());
        vm.serializeString(o, "proofTypes", "tee");
        vm.serializeString(o, "windowsKind", "production");
        vm.serializeString(o, "windows", _windowsJson(p.windows));
        vm.serializeUint(o, "unbondingDelay", d.reg.UNBONDING_DELAY());
        vm.serializeUint(o, "genesisBond", GENESIS_BOND);
        vm.serializeString(o, "judgesFee", _judgesFee());
        vm.serializeString(o, "addresses", _addresses(d));
        vm.serializeString(o, "constructorArgs", _args(p, r, sig, d));
        string memory out = vm.serializeString(o, "bytecode", _hashesJson());
        vm.writeJson(out, string.concat("./deployments/", vm.envString("DEPLOY_RECORD")));
    }

    function _judgesFee() internal returns (string memory) {
        string memory o = "judgesFee";
        vm.serializeString(o, "mode", "taxi");
        vm.serializeUint(o, "judgeFee", JUDGES_FEE);
        vm.serializeUint(o, "amount", JUDGES_FEE);
        vm.serializeBool(o, "inBytecode", true);
        vm.serializeString(o, "parameter", "Config.judgeFee (RaceV3, RaceV3Annex and RaceV3Endings); 0 = the taxi fare");
        vm.serializeUint(o, "attemptFee", 0);
        vm.serializeUint(o, "evaluationFee", 0);
        vm.serializeUint(o, "appealFee", 0);
        return vm.serializeString(
            o,
            "note",
            "The pure taxi fare (owner, 2026-11-19; ADR 0007, D30 for the launch): a fix's submission posts FeesV3's "
            "worst-case deposit, its judges are paid by the meter, and whatever is left returns to the solver, pass or "
            "fail, withdrawn or not. A solver pays only the metered validation: no attempt, evaluation or appeal fee, "
            "no appeal stake. A flat judges' fee is left to a later mainnet decision."
        );
    }

    /// The coin, its genesis mint and its faucet's rule (L17, 2026-11-20).
    function _testCoin(Plan memory p, Deployed memory d) internal returns (string memory) {
        TestCoin c = TestCoin(d.coin);
        string memory o = "testCoin";
        vm.serializeAddress(o, "address", d.coin);
        vm.serializeAddress(o, "faucet", address(d.faucet));
        vm.serializeString(o, "name", c.name());
        vm.serializeString(o, "symbol", c.symbol());
        vm.serializeUint(o, "decimals", c.decimals());
        vm.serializeString(o, "genesisMint", _genesisMintJson(p, d));
        vm.serializeString(o, "faucetRule", _faucetRuleJson(d));
        return vm.serializeString(
            o,
            "note",
            "A test coin with no value: no sale, no market. After the genesis mint, the faucet's fixed rule is the only "
            "way new coins come into existence; neither contract has an owner, admin, pause, setter or upgrade."
        );
    }

    function _genesisMintJson(Plan memory p, Deployed memory d) internal returns (string memory) {
        string memory o = "genesisMint";
        vm.serializeUint(o, "total", p.genesisMint);
        vm.serializeUint(o, "genesisBond", GENESIS_BOND);
        vm.serializeAddress(o, "genesisBondTo", address(d.maker));
        vm.serializeString(o, "genesisBondNote", "to the registry maker, which bonds it into Validators at construction");
        vm.serializeUint(o, "rest", p.genesisMint - GENESIS_BOND);
        return vm.serializeAddress(o, "restTo", p.genesisMintTo);
    }

    function _faucetRuleJson(Deployed memory d) internal returns (string memory) {
        string memory o = "faucetRule";
        vm.serializeUint(o, "claimAmount", d.faucet.CLAIM_AMOUNT());
        vm.serializeUint(o, "claimIntervalSeconds", d.faucet.CLAIM_INTERVAL());
        vm.serializeString(o, "per", "address");
        vm.serializeString(o, "who", "anyone, for itself (claim() mints to the caller)");
        return vm.serializeBool(o, "onlyMinter", true);
    }

    function _addresses(Deployed memory d) internal returns (string memory) {
        string memory o = "addresses";
        vm.serializeAddress(o, "coin", d.coin);
        vm.serializeAddress(o, "faucet", address(d.faucet));
        vm.serializeAddress(o, "pool", address(d.pool));
        vm.serializeAddress(o, "registryMaker", address(d.maker));
        vm.serializeAddress(o, "registry", address(d.reg));
        vm.serializeAddress(o, "scores", address(d.scores));
        vm.serializeAddress(o, "fees", address(d.fees));
        vm.serializeAddress(o, "panels", address(d.panels));
        vm.serializeAddress(o, "annex", address(d.annex));
        vm.serializeAddress(o, "endings", address(d.endings));
        vm.serializeAddress(o, "race", address(d.race));
        vm.serializeAddress(o, "solverBook", address(d.race.solverBook()));
        // RaceV3's constructor creates its Heads, the race's first creation
        return vm.serializeAddress(o, "heads", vm.computeCreateAddress(address(d.race), 1));
    }

    function _hashesJson() internal returns (string memory out) {
        string[N] memory names = _names();
        bytes[N] memory codes = _codes();
        for (uint256 i; i < N; ++i) {
            out = vm.serializeBytes32("bytecode", names[i], keccak256(codes[i]));
        }
    }

    /// Every constructor argument, decoded and as the ABI encoding appended to the creation code.
    function _args(Plan memory p, IValidators.Registration memory r, bytes memory sig, Deployed memory d)
        internal
        returns (string memory)
    {
        string memory o = "constructorArgs";
        vm.serializeString(o, "CoinFaucet", _faucetArgs(p, d));
        vm.serializeString(o, "TestCoin", _coinArgs(p, d));
        vm.serializeString(o, "PoolV3", _poolArgs(d));
        vm.serializeString(o, "RegistryMaker", _noArgs("RegistryMaker"));
        vm.serializeString(o, "Validators", _validatorsArgs(p, r, sig, d));
        vm.serializeString(o, "PanelScores", _noArgs("PanelScores"));
        vm.serializeString(o, "FeesV3", _feesArgs(p, d));
        vm.serializeString(o, "Panels", _panelsArgs(p, d));
        vm.serializeString(o, "RaceV3Endings", _endingsArgs(d));
        vm.serializeString(o, "RaceV3Annex", _annexArgs(d));
        return vm.serializeString(o, "RaceV3", _raceArgs(p, d));
    }

    function _noArgs(string memory key) internal returns (string memory) {
        return vm.serializeBytes(string.concat("args.", key), "encoded", "");
    }

    function _faucetArgs(Plan memory p, Deployed memory d) internal returns (string memory) {
        string memory o = "args.CoinFaucet";
        (address[] memory to, uint256[] memory amounts) = _mint(p, address(d.maker));
        vm.serializeAddress(o, "genesisTo", to);
        vm.serializeUint(o, "genesisAmounts", amounts);
        vm.serializeString(o, "deploys", "TestCoin(genesisTo, genesisAmounts), its first creation; its only minter");
        return vm.serializeBytes(o, "encoded", abi.encode(to, amounts));
    }

    function _coinArgs(Plan memory p, Deployed memory d) internal returns (string memory) {
        string memory o = "args.TestCoin";
        (address[] memory to, uint256[] memory amounts) = _mint(p, address(d.maker));
        vm.serializeAddress(o, "to", to);
        vm.serializeUint(o, "amounts", amounts);
        vm.serializeString(o, "createdBy", "CoinFaucet's constructor (the faucet is the creator, fixed as its minter)");
        return vm.serializeBytes(o, "encoded", abi.encode(to, amounts));
    }

    function _poolArgs(Deployed memory d) internal returns (string memory) {
        string memory o = "args.PoolV3";
        vm.serializeAddress(o, "coins", _one(d.coin));
        return vm.serializeBytes(o, "encoded", abi.encode(_one(d.coin)));
    }

    function _validatorsArgs(Plan memory p, IValidators.Registration memory r, bytes memory sig, Deployed memory d)
        internal
        returns (string memory)
    {
        string memory o = "args.Validators";
        Validators.Genesis memory g = _genesis(p, r, sig, d);
        vm.serializeAddress(o, "coin", g.coin);
        vm.serializeAddress(o, "pool", g.pool);
        vm.serializeString(o, "proofTypeNames", _strings1("tee"));
        vm.serializeBytes32(o, "proofTypes", g.proofTypes);
        vm.serializeString(o, "teeTypeNames", p.teeNames);
        vm.serializeBytes32(o, "teeTypes", g.teeTypes);
        vm.serializeUint(o, "firmware", new uint256[](0));
        vm.serializeBytes32(o, "images", g.images);
        vm.serializeString(o, "validators", _registrationJson(p, r));
        vm.serializeBytes(o, "signature", sig);
        vm.serializeUint(o, "bonds", g.bonds);
        vm.serializeString(o, "windows", _windowsJson(g.windows));
        vm.serializeBool(o, "teeOnly", g.teeOnly);
        vm.serializeString(o, "createdBy", "RegistryMaker.make(coin, genesisBond, creation code ++ encoded)");
        return vm.serializeBytes(o, "encoded", abi.encode(g));
    }

    function _registrationJson(Plan memory p, IValidators.Registration memory r) internal returns (string memory) {
        string memory o = "args.genesisValidator";
        vm.serializeAddress(o, "key", r.key);
        vm.serializeAddress(o, "operator", r.operator);
        vm.serializeString(o, "proofTypeName", "tee");
        vm.serializeBytes32(o, "proofType", r.proofType);
        vm.serializeString(o, "teeTypeName", p.genesisTee);
        vm.serializeBytes32(o, "teeType", r.teeType);
        vm.serializeUint(o, "level", r.level);
        vm.serializeBytes32(o, "attestation", r.attestation);
        vm.serializeBytes32(o, "image", r.image);
        vm.serializeBytes32(o, "host", r.host);
        vm.serializeString(o, "familyName", p.familyNames[0]);
        vm.serializeBytes32(o, "family", r.family);
        vm.serializeUint(o, "firmware", r.firmware);
        return vm.serializeBytes32(o, "radNode", r.radNode);
    }

    function _feesArgs(Plan memory p, Deployed memory d) internal returns (string memory) {
        string memory o = "args.FeesV3";
        FeesV3.Genesis memory g = _fees(d.coin, p);
        vm.serializeAddress(o, "validators", address(d.reg));
        vm.serializeAddress(o, "scores", address(d.scores));
        vm.serializeAddress(o, "coin", g.coin);
        uint256[] memory shared = new uint256[](4);
        for (uint256 i; i < 4; ++i) {
            shared[i] = g.shared[i];
        }
        vm.serializeUint(o, "shared", shared);
        vm.serializeString(o, "familyNames", p.familyNames);
        vm.serializeBytes32(o, "families", g.families);
        uint256[] memory tokens = new uint256[](3 * g.tokens.length);
        for (uint256 i; i < g.tokens.length; ++i) {
            for (uint256 j; j < 3; ++j) {
                tokens[3 * i + j] = g.tokens[i][j];
            }
        }
        vm.serializeUint(o, "tokensFlat", tokens);
        vm.serializeString(o, "caps", _capsJson(g.caps));
        vm.serializeBytes32(o, "repo", g.repo);
        vm.serializeString(o, "profile", _profileJson(g.profile));
        vm.serializeBool(o, "ciSingleRun", g.ciSingleRun);
        return vm.serializeBytes(o, "encoded", abi.encode(address(d.reg), address(d.scores), g));
    }

    function _capsJson(IFeesV3.Caps memory c) internal returns (string memory) {
        string memory o = "args.caps";
        vm.serializeUint(o, "inputTokens", c.inputTokens);
        vm.serializeUint(o, "outputTokens", c.outputTokens);
        vm.serializeUint(o, "storageMb", c.storageMb);
        vm.serializeUint(o, "gasAllowance", c.gasAllowance);
        vm.serializeUint(o, "gasOverhead", c.gasOverhead);
        return vm.serializeUint(o, "maxGasPrice", c.maxGasPrice);
    }

    function _profileJson(IFeesV3.Profile memory f) internal returns (string memory) {
        string memory o = "args.profile";
        vm.serializeBytes32(o, "image", f.image);
        vm.serializeUint(o, "milliVcpus", f.milliVcpus);
        vm.serializeUint(o, "memoryMb", f.memoryMb);
        return vm.serializeUint(o, "timeoutSeconds", f.timeoutSeconds);
    }

    function _panelsArgs(Plan memory p, Deployed memory d) internal returns (string memory) {
        string memory o = "args.Panels";
        vm.serializeAddress(o, "validators", address(d.reg));
        vm.serializeAddress(o, "fees", address(d.fees));
        vm.serializeAddress(o, "scores", address(d.scores));
        vm.serializeBytes32(o, "teeTypes", p.teeTypes);
        vm.serializeString(o, "windows", _windowsJson(p.windows));
        return vm.serializeBytes(
            o, "encoded", abi.encode(address(d.reg), address(d.fees), address(d.scores), p.teeTypes, p.windows)
        );
    }

    function _endingsArgs(Deployed memory d) internal returns (string memory) {
        string memory o = "args.RaceV3Endings";
        RaceV3Base.Config memory c = _config(address(d.pool));
        vm.serializeString(o, "config", _configJson(c));
        vm.serializeUint(o, "bountyCap", BOUNTY_CAP);
        vm.serializeUint(o, "totalCap", TOTAL_CAP);
        vm.serializeAddress(o, "panels", address(d.panels));
        vm.serializeAddress(o, "pool", address(d.pool));
        vm.serializeUint(o, "start", d.start);
        return vm.serializeBytes(
            o, "encoded", abi.encode(c, BOUNTY_CAP, TOTAL_CAP, address(d.panels), address(d.pool), d.start)
        );
    }

    function _annexArgs(Deployed memory d) internal returns (string memory) {
        string memory o = "args.RaceV3Annex";
        RaceV3Base.Config memory c = _config(address(d.pool));
        vm.serializeString(o, "config", _configJson(c));
        vm.serializeUint(o, "bountyCap", BOUNTY_CAP);
        vm.serializeUint(o, "totalCap", TOTAL_CAP);
        vm.serializeAddress(o, "panels", address(d.panels));
        vm.serializeAddress(o, "pool", address(d.pool));
        vm.serializeUint(o, "start", d.start);
        vm.serializeAddress(o, "endings", address(d.endings));
        return vm.serializeBytes(
            o,
            "encoded",
            abi.encode(c, BOUNTY_CAP, TOTAL_CAP, address(d.panels), address(d.pool), d.start, address(d.endings))
        );
    }

    function _raceArgs(Plan memory p, Deployed memory d) internal returns (string memory) {
        string memory o = "args.RaceV3";
        RaceV3Base.Config memory c = _config(address(d.pool));
        vm.serializeString(o, "config", _configJson(c));
        vm.serializeUint(o, "bountyCap", BOUNTY_CAP);
        vm.serializeUint(o, "totalCap", TOTAL_CAP);
        vm.serializeAddress(o, "panels", address(d.panels));
        vm.serializeAddress(o, "pool", address(d.pool));
        vm.serializeUint(o, "start", d.start);
        vm.serializeBytes32(o, "repo", p.repo);
        vm.serializeBytes32(o, "genesisHead", p.head);
        vm.serializeBytes32(o, "constitution", p.constitution);
        vm.serializeAddress(o, "annex", address(d.annex));
        vm.serializeString(
            o,
            "deploys",
            "Heads(panels, [repo], [genesisHead], constitution, race), then SolverBook(panels.ACTIVE_WINDOW())"
        );
        return vm.serializeBytes(
            o,
            "encoded",
            abi.encode(
                c,
                BOUNTY_CAP,
                TOTAL_CAP,
                address(d.panels),
                address(d.pool),
                d.start,
                p.repo,
                p.head,
                p.constitution,
                address(d.annex)
            )
        );
    }

    function _configJson(RaceV3Base.Config memory c) internal returns (string memory) {
        string memory o = "args.config";
        vm.serializeAddress(o, "infrastructure", c.infrastructure);
        vm.serializeAddress(o, "insurance", c.insurance);
        vm.serializeUint(o, "registrationFee", c.registrationFee);
        vm.serializeUint(o, "issueStake", c.issueStake);
        vm.serializeUint(o, "attemptFee", c.attemptFee);
        vm.serializeUint(o, "evaluationFee", c.evaluationFee);
        vm.serializeUint(o, "appealFee", c.appealFee);
        vm.serializeUint(o, "challengeStake", c.challengeStake);
        vm.serializeUint(o, "startPriceBps", c.startPriceBps);
        vm.serializeUint(o, "riseBpsPerDay", c.riseBpsPerDay);
        vm.serializeUint(o, "finderFeeBps", c.finderFeeBps);
        vm.serializeUint(o, "idleDays", c.idleDays);
        vm.serializeUint(o, "resultDays", c.resultDays);
        vm.serializeUint(o, "mergeDays", c.mergeDays);
        vm.serializeUint(o, "releaseEveryDays", c.releaseEveryDays);
        vm.serializeUint(o, "instalments", c.instalments);
        return vm.serializeUint(o, "judgeFee", c.judgeFee);
    }

    /// The windows in seconds, as NodeV3Local records them: "challenge" is [[A k=1,3,5,7], [B ...], [C ...]].
    function _windowsJson(Windows memory w) internal pure returns (string memory j) {
        j = string.concat('{"seal": ', vm.toString(w.seal), ', "reveal": ', vm.toString(w.reveal), ', "challenge": [');
        for (uint256 l; l < 3; ++l) {
            j = string.concat(j, l == 0 ? "[" : ", [");
            for (uint256 i; i < 4; ++i) {
                j = string.concat(j, i == 0 ? "" : ", ", vm.toString(w.challenge[l][i]));
            }
            j = string.concat(j, "]");
        }
        j = string.concat(
            j,
            '], "adr": ',
            vm.toString(w.adr),
            ', "removal": ',
            vm.toString(w.removal),
            ', "k1Min": ',
            vm.toString(w.k1Min),
            ', "stuckGrace": ',
            vm.toString(w.stuckGrace),
            ', "retryDelay": ',
            vm.toString(w.retryDelay),
            ', "maxRedraws": ',
            vm.toString(w.maxRedraws),
            ', "capWindow": ',
            vm.toString(w.capWindow),
            ', "appeal": ',
            vm.toString(w.appeal),
            ', "active": ',
            vm.toString(w.active),
            "}"
        );
    }

    // ---------- helpers ----------

    /// The registration digest for a registry at `verifying` (Validators' own, before the registry exists).
    function _digest(address verifying, IValidators.Registration memory r) internal view returns (bytes32) {
        bytes32 domain = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256("proof-of-fix Validators"),
                keccak256("3"),
                block.chainid,
                verifying
            )
        );
        bytes32 h = keccak256(
            abi.encode(
                keccak256(
                    "Registration(address key,address operator,bytes32 proofType,bytes32 teeType,uint8 level,bytes32 attestation,bytes32 image,bytes32 host,bytes32 family,uint32 firmware,bytes32 radNode)"
                ),
                r.key,
                r.operator,
                r.proofType,
                r.teeType,
                r.level,
                r.attestation,
                r.image,
                r.host,
                r.family,
                r.firmware,
                r.radNode
            )
        );
        return keccak256(abi.encodePacked("\x19\x01", domain, h));
    }

    function _hashed(string[] memory names) internal pure returns (bytes32[] memory out) {
        out = new bytes32[](names.length);
        for (uint256 i; i < names.length; ++i) {
            out[i] = keccak256(bytes(names[i]));
        }
    }

    function _one(address a) internal pure returns (address[] memory out) {
        out = new address[](1);
        out[0] = a;
    }

    function _strings1(string memory s) internal pure returns (string[] memory out) {
        out = new string[](1);
        out[0] = s;
    }
}
