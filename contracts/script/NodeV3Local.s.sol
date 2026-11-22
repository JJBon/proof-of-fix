// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Script} from "forge-std/Script.sol";
import {console} from "forge-std/console.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
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
import {PanelRules, PanelRulesLib, Cap, ChallengeSize} from "../src/v3/PanelRules.sol";
import {MockCoin} from "../test/mocks/MockCoin.sol";
import {CoinFaucet} from "../src/v3/CoinFaucet.sol";
import {RegistryMaker} from "./RegistryMaker.sol";

/// v3 on a throwaway local chain, for the oracle node's own test (proof-of-fix#139, task 4.1 of #132;
/// scripts/node-v3-e2e.sh): a test coin, PoolV3, Validators with one genesis validator of the `simulated` proof type
/// (D18: chain 31337 only; the contracts refuse it elsewhere), PanelScores, FeesV3, Panels, RaceV3Annex and RaceV3, in
/// the order of reports/contract-v3.md. It is also the throwaway local devnet's deployment beside v2 (#140, task 5.1:
/// scripts/devnet.sh deploy-v3), whose record says so (`testOnly`, the proof types, v2's race). It is not the AWS
/// devnet's (task 5.2 writes that): every value here is a test value, and the coin is one anyone can mint, unless
/// LOCAL_COIN asks for the launch's own test coin.
///   LOCAL_GENESIS_PK      the genesis validator's key: a throwaway test key, it signs its registration here
///   LOCAL_ATTESTATION     the genesis validator's attestation hash (the node's simulated quote, hashed)
///   LOCAL_GENESIS_RAD_NODE the genesis validator's Radicle node key, bytes32 (the Ed25519 key its did:key names;
///                         #251, L11). Default 0: no node, its seat isn't counted as a delegate
///   LOCAL_FAMILIES        the model families priced from the start, comma-separated names (hashed); the first
///                         is the genesis validator's. Default "fake". A family not priced isn't drawn (D19), and a
///                         network this small can't price a new one (it takes three tables from other families)
///   LOCAL_RECORD          where to write the addresses (under ./deployments)
///   LOCAL_BESIDE          v2's race on the same chain, for the record (default: none)
///   LOCAL_RID             the one repository's Radicle RID; its id is keccak256 of it (#251, L1; default
///                         "rad:local-devnet", a name only: nothing is published)
///   LOCAL_GENESIS_HEAD    that repository's genesis head, bytes32 (a git SHA-1 left-aligned; default a test value)
///   LOCAL_WINDOWS         "production" (default: ADR 0004's, what Sepolia uses) or "minutes" (every hour a minute)
///   LOCAL_TEE_ONLY        refuse zkTLS by ADR as Sepolia does (#251, L10; default true)
///   LOCAL_PANEL_CAPS      the operator, host and TEE-type caps (#251 batch 4, L23): "strict" (default) or "launch"
///                         (all off, as on Sepolia)
///   LOCAL_K_TOP           the largest issue-tier panel (L24): odd, 1 to 7 (default 7; Sepolia 3)
///   LOCAL_CHALLENGE_SIZE  "larger" (default, D4) or "same" (L24, Sepolia's)
///   LOCAL_COIN            "mock" (default: a coin anyone may mint, for runs that fund many keys freely) or "test"
///                         (#251 L17, task 4.6: Sepolia's coin, CoinFaucet and the TestCoin it creates, POFTEST, with
///                         no minter but the faucet's 20 coins every 2 hours; its genesis mint is the genesis bond, to
///                         the registry maker, and LOCAL_GENESIS_MINT micro-coins to LOCAL_GENESIS_MINT_TO, from
///                         which the run funds its keys). The record then names the faucet
///   LOCAL_EXTRA_IMAGE     one more accepted checker image digest, bytes32 (default none): the measured checker disk's
///                         `image_digest` (validator-kit/sevsnp, #251 L21), so a real SEV-SNP host registers with it
///                         on the release candidate's test chain (task 7.0). The record lists the accepted images
/// The record lists the chain id, the repository, its genesis head, every window and the unbonding delay (#251, L4),
/// and the liveness values (L19: STUCK_GRACE, RETRY_DELAY, MAX_REDRAWS; L16: the capacity's window; L25: the
/// challenges' deadline), and the panel rules (`panelRules`, as Panels reads them back). RaceV3Annex
/// deploys its RaceV3Endings itself (contract batch 2).
contract NodeV3LocalScript is Script {
    bytes32 constant TDX = keccak256("intel-tdx");
    bytes32 constant IMAGE = keccak256("devnet checker image");
    uint256 constant GENESIS_BOND = 1_250e6;
    bytes32 constant DEFAULT_HEAD = bytes32(bytes20(keccak256("local genesis head")));

    function run() external {
        uint256 pk = vm.envUint("LOCAL_GENESIS_PK");
        address key = vm.addr(pk);
        string[] memory one = new string[](1);
        one[0] = "fake";
        string[] memory names = vm.envOr("LOCAL_FAMILIES", ",", one);
        bytes32[] memory families = new bytes32[](names.length);
        for (uint256 i; i < names.length; ++i) {
            families[i] = keccak256(bytes(names[i]));
        }
        bytes32 family = families[0];
        string memory rid = vm.envOr("LOCAL_RID", string("rad:local-devnet"));
        bytes32 repo = keccak256(bytes(rid));
        bytes32 head = vm.envOr("LOCAL_GENESIS_HEAD", DEFAULT_HEAD);
        string memory which = vm.envOr("LOCAL_WINDOWS", string("production"));
        Windows memory w;
        if (keccak256(bytes(which)) == keccak256("minutes")) w = WindowsLib.inMinutes();
        else if (keccak256(bytes(which)) == keccak256("production")) w = WindowsLib.production();
        else revert("LOCAL_WINDOWS: production or minutes");

        vm.startBroadcast();
        bool testCoin = _testCoin();
        // the test coin's genesis mint names the registry maker, so the maker comes first; the mock's order is kept
        RegistryMaker maker = testCoin ? new RegistryMaker() : RegistryMaker(address(0));
        (IERC20 usd, address faucet) = _coin(testCoin, address(maker));
        address[] memory coins = new address[](1);
        coins[0] = address(usd);
        PoolV3 pool = new PoolV3(coins);

        if (!testCoin) maker = new RegistryMaker();
        Validators.Genesis memory g;
        g.coin = address(usd);
        g.pool = address(pool);
        g.proofTypes = new bytes32[](2);
        g.proofTypes[0] = keccak256("tee");
        g.proofTypes[1] = keccak256("simulated");
        g.teeTypes = new bytes32[](3);
        g.teeTypes[0] = TDX;
        g.teeTypes[1] = keccak256("amd-sev-snp");
        g.teeTypes[2] = keccak256("aws-nitro-enclaves");
        bytes32 extra = vm.envOr("LOCAL_EXTRA_IMAGE", bytes32(0));
        g.images = new bytes32[](extra == bytes32(0) || extra == IMAGE ? 1 : 2);
        g.images[0] = IMAGE;
        if (g.images.length == 2) g.images[1] = extra;
        g.validators = new IValidators.Registration[](1);
        g.validators[0] = IValidators.Registration({
            key: key,
            operator: key,
            proofType: keccak256("simulated"),
            teeType: TDX,
            level: 1,
            attestation: vm.envBytes32("LOCAL_ATTESTATION"),
            image: IMAGE,
            host: keccak256("genesis-host"),
            family: family,
            firmware: 0,
            radNode: vm.envOr("LOCAL_GENESIS_RAD_NODE", bytes32(0))
        });
        g.signatures = new bytes[](1);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk, _digest(maker.next(), g.validators[0]));
        g.signatures[0] = abi.encodePacked(r, s, v);
        g.bonds = new uint256[](1);
        g.bonds[0] = GENESIS_BOND;
        g.windows = w;
        g.teeOnly = vm.envOr("LOCAL_TEE_ONLY", true);
        if (!testCoin) MockCoin(address(usd)).mint(address(maker), GENESIS_BOND);
        Validators reg =
            Validators(maker.make(usd, GENESIS_BOND, abi.encodePacked(type(Validators).creationCode, abi.encode(g))));

        PanelScores scores = new PanelScores();
        FeesV3 fees = new FeesV3(IFeesV3Validators(address(reg)), scores, _fees(address(usd), families, repo));
        Panels panels = new Panels(
            IPanelsRegistry(address(reg)), IPanelsFees(address(fees)), IPanelScores(address(scores)), g.teeTypes, w, _rules()
        );
        uint256 start = block.timestamp;
        // the endings first, then the annex that checks them (#251 contract batch 3: EIP-3860)
        RaceV3Endings endings = new RaceV3Endings(_config(), 625, 100_000, panels, pool, start);
        RaceV3Annex annex = new RaceV3Annex(_config(), 625, 100_000, panels, pool, start, endings);
        RaceV3 race = new RaceV3(_config(), 625, 100_000, panels, pool, start, repo, head, keccak256("local"), annex);
        vm.stopBroadcast();
        _record(race, address(usd), faucet, reg, panels, fees, pool, key, rid, repo, head, which, w);
        console.log(string.concat("RACE=", vm.toString(address(race))));
    }

    /// LOCAL_COIN: "mock" (default) or "test".
    function _testCoin() internal view returns (bool) {
        bytes32 kind = keccak256(bytes(vm.envOr("LOCAL_COIN", string("mock"))));
        if (kind == keccak256("test")) return true;
        if (kind != keccak256("mock")) revert("LOCAL_COIN: mock or test");
        return false;
    }

    /// The fee coin and its faucet (0 for the mock): the mock, or CoinFaucet's TestCoin with its genesis mint.
    function _coin(bool testCoin, address maker) internal returns (IERC20 coin, address faucet) {
        if (!testCoin) return (IERC20(address(new MockCoin("Local USD", "lUSD", 6))), address(0));
        address[] memory to = new address[](2);
        uint256[] memory amounts = new uint256[](2);
        (to[0], amounts[0]) = (maker, GENESIS_BOND);
        (to[1], amounts[1]) = (vm.envAddress("LOCAL_GENESIS_MINT_TO"), vm.envUint("LOCAL_GENESIS_MINT"));
        CoinFaucet f = new CoinFaucet(to, amounts);
        return (IERC20(address(f.coin())), address(f));
    }

    function _record(
        RaceV3 race,
        address usd,
        address faucet,
        Validators reg,
        Panels panels,
        FeesV3 fees,
        PoolV3 pool,
        address key,
        string memory rid,
        bytes32 repo,
        bytes32 head,
        string memory which,
        Windows memory w
    ) internal {
        string memory binding = string.concat(
            ', "rid": "',
            rid,
            '", "repo": "',
            vm.toString(repo),
            '", "genesisHead": "',
            vm.toString(head),
            '", "teeOnly": ',
            reg.teeOnly() ? "true" : "false",
            ', "windowsKind": "',
            which,
            '", "windows": ',
            _windowsJson(w),
            ', "unbondingDelay": ',
            vm.toString(reg.UNBONDING_DELAY()),
            ', "panelRules": ',
            _rulesJson(panels.panelRules()),
            _imagesJson(reg)
        );

        string memory record = string.concat(
            '{"version": 3, "testOnly": true, "proofTypes": ["tee", "simulated"], "besideV2": "',
            vm.toString(vm.envOr("LOCAL_BESIDE", address(0))),
            '", "chainId": ',
            vm.toString(block.chainid),
            ', "race": "',
            vm.toString(address(race)),
            '", "coin": "',
            vm.toString(usd),
            faucet == address(0) ? "" : string.concat('", "faucet": "', vm.toString(faucet)),
            '", "registry": "',
            vm.toString(address(reg)),
            '", "panels": "',
            vm.toString(address(panels)),
            '", "fees": "',
            vm.toString(address(fees)),
            '", "pool": "',
            vm.toString(address(pool)),
            '", "solverBook": "',
            vm.toString(address(race.solverBook())),
            '", "judgeFee": ',
            vm.toString(race.getConfig().judgeFee),
            ', "genesis": "',
            vm.toString(key),
            '", "genesisRadNode": "',
            vm.toString(reg.radNodeOf(key)),
            '"',
            binding,
            "}"
        );
        vm.writeFile(string.concat("./deployments/", vm.envString("LOCAL_RECORD")), record);
    }

    /// The accepted checker images, as the registry reads them back (`allowedImage`).
    function _imagesJson(Validators reg) internal view returns (string memory) {
        bytes32 extra = vm.envOr("LOCAL_EXTRA_IMAGE", bytes32(0));
        string memory out = string.concat(', "images": ["', vm.toString(IMAGE), '"');
        if (extra != bytes32(0) && extra != IMAGE && reg.allowedImage(extra)) {
            out = string.concat(out, ', "', vm.toString(extra), '"');
        }
        return string.concat(out, "]");
    }

    function _rules() internal view returns (PanelRules memory r) {
        r = PanelRulesLib.strict();
        bytes32 caps = keccak256(bytes(vm.envOr("LOCAL_PANEL_CAPS", string("strict"))));
        if (caps == keccak256("launch")) (r.operatorCap, r.hostCap, r.teeCap) = (Cap.Off, Cap.Off, Cap.Off);
        else if (caps != keccak256("strict")) revert("LOCAL_PANEL_CAPS: strict or launch");
        r.kTop = vm.envOr("LOCAL_K_TOP", uint256(7));
        bytes32 size = keccak256(bytes(vm.envOr("LOCAL_CHALLENGE_SIZE", string("larger"))));
        if (size == keccak256("same")) r.challengeSize = ChallengeSize.Same;
        else if (size != keccak256("larger")) revert("LOCAL_CHALLENGE_SIZE: larger or same");
    }

    /// The panel rules as DeploySepolia's record names them.
    function _rulesJson(PanelRules memory r) internal pure returns (string memory) {
        return string.concat(
            '{"operatorCap": "',
            r.operatorCap == Cap.Strict ? "strict" : "off",
            '", "hostCap": "',
            r.hostCap == Cap.Strict ? "strict" : "off",
            '", "teeCap": "',
            r.teeCap == Cap.Strict ? "strict" : "off",
            '", "kTop": ',
            vm.toString(r.kTop),
            ', "challengeSize": "',
            r.challengeSize == ChallengeSize.Same ? "same" : "larger",
            '"}'
        );
    }

    /// The windows in seconds: {"seal", "reveal", "challenge": [[A k=1,3,5,7], [B ...], [C ...]], "adr", "removal",
    /// "k1Min", and L19's and L16's "stuckGrace", "retryDelay", "maxRedraws" (a count) and "capWindow"}.
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
            ', "challengeDeadline": ',
            vm.toString(w.challengeDeadline),
            "}"
        );
    }

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

    /// The contract tests' prices (test/v3/helpers/PanelsSetup.sol): the list prices of 2026-10-30 and Fargate's rates.
    function _fees(address coin, bytes32[] memory families, bytes32 repo)
        internal
        pure
        returns (FeesV3.Genesis memory g)
    {
        g.coin = coin;
        g.shared = [uint256(11_244_444), 1_234_722, 269_531_250, 2_700_000_000];
        g.families = families;
        g.tokens = new uint256[3][](families.length);
        for (uint256 i; i < families.length; ++i) {
            g.tokens[i] = [uint256(4_000_000), 200_000, 20_000_000];
        }
        g.caps = IFeesV3.Caps(140_000, 16_000, 20, 1_000_000, 50_000, 1 gwei);
        g.repo = repo;
        g.profile = IFeesV3.Profile(keccak256("image"), 2_000, 4_096, 1_200);
    }

    /// The contract tests' race configuration (test/v3/helpers/RaceV3Setup.sol), with Sepolia's fees (owner,
    /// 2026-11-19): the pure taxi fare (`judgeFee` 0) and no attempt, evaluation or appeal fee.
    function _config() internal pure returns (RaceV3Base.Config memory c) {
        c.infrastructure = address(0x1F);
        c.insurance = address(0x15);
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
        c.judgeFee = 0; // the taxi fare: a fix's deposit's rest returns to its solver
    }
}
