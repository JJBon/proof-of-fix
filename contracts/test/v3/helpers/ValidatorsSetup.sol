// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {Test} from "forge-std/Test.sol";
import {stdStorage, StdStorage} from "forge-std/StdStorage.sol";
import {Validators} from "../../../src/v3/Validators.sol";
import {IValidators} from "../../../src/v3/IValidators.sol";
import {Pool} from "../../../src/v2/Pool.sol";
import {MockCoin} from "../../mocks/MockCoin.sol";

// The genesis lists of the test versions (D6's launch types, the official checker image).
bytes32 constant TDX = keccak256("intel-tdx");
bytes32 constant SEV_SNP = keccak256("amd-sev-snp");
bytes32 constant NITRO = keccak256("aws-nitro-enclaves");
bytes32 constant SGX = keccak256("intel-sgx");
bytes32 constant IMAGE = keccak256("the official checker image (test)");
bytes32 constant OTHER_IMAGE = keccak256("a checker image nobody listed");
bytes32 constant FAMILY_A = keccak256("family-a");
bytes32 constant FAMILY_B = keccak256("family-b");

/// The consumer bound to the registry in the tests: Panels doesn't exist yet (task 3.2), so this harness binds itself
/// in its constructor, as Panels will, and forwards each hook.
contract PanelsHarness {
    Validators public immutable validators;

    constructor(Validators v) {
        validators = v;
        v.bind();
    }

    function recordShadow(address key, bool revealed) external {
        validators.recordShadow(key, revealed);
    }

    function scoreShadow(address key, bool agreed) external {
        validators.scoreShadow(key, agreed);
    }

    function recordCounted(address key, bool hasSeal, bool revealed) external {
        validators.recordCounted(key, hasSeal, revealed);
    }

    function verdictOpened(address key) external {
        validators.verdictOpened(key);
    }

    function verdictFinal(address key) external {
        validators.verdictFinal(key);
    }

    function challengeOpened(address key) external {
        validators.challengeOpened(key);
    }

    function challengeClosed(address key) external {
        validators.challengeClosed(key);
    }

    function slashFault(address key, IValidators.Fault fault, address challenger) external {
        validators.slashFault(key, fault, challenger);
    }

    function adrPassed(uint256 id, bool removal, bytes32 commitment) external {
        validators.adrPassed(id, removal, commitment);
    }
}

/// A registry whose list holds zkTLS, as an adding ADR makes it (task 3.4): the verifier path is in the code, only
/// the list keeps it off at launch. Test-only; no deployed version has this constructor.
contract ValidatorsWithZkTls is Validators {
    constructor(Genesis memory g) Validators(g) {
        _list(_proofs[PROOF_ZKTLS]);
    }
}

/// Keys, signatures and a deployed registry for the v3 tests.
abstract contract ValidatorsSetup is Test {
    using stdStorage for StdStorage;

    MockCoin internal usd;
    Pool internal pool;
    Validators internal reg;
    PanelsHarness internal panels;
    uint256 internal keyCount;
    /// Deploys the registries: an EOA, so its nonce (and the next registry's address, which genesis keys sign for)
    /// is known in setUp too.
    address internal deployer = makeAddr("deployer");
    mapping(address => uint256) internal secretOf;

    function _deployCoinAndPool() internal {
        usd = new MockCoin("Test USD", "tUSD", 6);
        address[] memory coins = new address[](1);
        coins[0] = address(usd);
        pool = new Pool(coins);
    }

    function _newKey(string memory name) internal returns (address a) {
        uint256 k;
        (a, k) = makeAddrAndKey(name);
        secretOf[a] = k;
    }

    function _nextKey() internal returns (address) {
        return _newKey(string.concat("validator", vm.toString(++keyCount)));
    }

    /// A level A TDX registration of `key`, its operator, host and family.
    function _reg(address key, address operator, bytes32 host, bytes32 family)
        internal
        pure
        returns (IValidators.Registration memory r)
    {
        r.key = key;
        r.operator = operator;
        r.proofType = keccak256("tee");
        r.teeType = TDX;
        r.level = 1;
        r.attestation = keccak256(abi.encode("attestation", key));
        r.image = IMAGE;
        r.host = host;
        r.family = family;
    }

    function _sign(Validators v, address signer, IValidators.Registration memory r) internal view returns (bytes memory) {
        return _signDigest(signer, _registrationDigest(address(v), r));
    }

    function _signDigest(address signer, bytes32 digest) internal view returns (bytes memory) {
        (uint8 v_, bytes32 r_, bytes32 s_) = vm.sign(secretOf[signer], digest);
        return abi.encodePacked(r_, s_, v_);
    }

    /// The registration digest, spelled out again here so a drift from the contract's constants fails the tests.
    function _registrationDigest(address verifying, IValidators.Registration memory r) internal view returns (bytes32) {
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
                    "Registration(address key,address operator,bytes32 proofType,bytes32 teeType,uint8 level,bytes32 attestation,bytes32 image,bytes32 host,bytes32 family,uint32 firmware)"
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
                r.firmware
            )
        );
        return keccak256(abi.encodePacked("\x19\x01", domain, h));
    }

    function _statementSig(address signer, bytes32 subject, bytes32 content) internal view returns (bytes memory) {
        return _signDigest(signer, reg.statementDigest(subject, content));
    }

    /// A genesis with the launch lists (TEE only; `simulated` too when asked) and the given genesis registrations,
    /// each bonded `bond` from this contract.
    function _genesis(bool simulated, IValidators.Registration[] memory gs, uint256 bond)
        internal
        returns (Validators.Genesis memory g)
    {
        g.coin = address(usd);
        g.pool = address(pool);
        g.proofTypes = new bytes32[](simulated ? 2 : 1);
        g.proofTypes[0] = keccak256("tee");
        if (simulated) g.proofTypes[1] = keccak256("simulated");
        g.teeTypes = new bytes32[](3);
        g.teeTypes[0] = TDX;
        g.teeTypes[1] = SEV_SNP;
        g.teeTypes[2] = NITRO;
        g.images = new bytes32[](1);
        g.images[0] = IMAGE;
        g.validators = gs;
        g.signatures = new bytes[](gs.length);
        g.bonds = new uint256[](gs.length);
        address next = vm.computeCreateAddress(deployer, vm.getNonce(deployer));
        for (uint256 i; i < gs.length; ++i) {
            g.signatures[i] = _signDigest(gs[i].key, _registrationDigest(next, gs[i]));
            g.bonds[i] = bond;
        }
        // the deployer's allowance is written, not approved: a pranked call would move its nonce (and the address)
        usd.mint(deployer, bond * gs.length);
        stdstore.target(address(usd)).sig(usd.allowance.selector).with_key(deployer).with_key(next).checked_write(
            bond * gs.length
        );
    }

    /// Deploys a registry from `deployer` (who pays the genesis bonds).
    function _create(Validators.Genesis memory g) internal returns (Validators v) {
        vm.prank(deployer);
        v = new Validators(g);
    }

    /// Deploys the registry with one genesis validator (level A, $1,250) and binds the harness.
    function _deploy(address genesisKey) internal {
        IValidators.Registration[] memory gs = new IValidators.Registration[](1);
        gs[0] = _reg(genesisKey, makeAddr("genesis operator"), keccak256("host-genesis"), FAMILY_A);
        Validators.Genesis memory g = _genesis(false, gs, 1_250e6);
        reg = _create(g);
        panels = new PanelsHarness(reg);
    }

    /// Registers `r` with `bond`, paid by `payer`.
    function _register(IValidators.Registration memory r, uint256 bond, address payer) internal {
        bytes memory sig = _sign(reg, r.key, r);
        usd.mint(payer, bond);
        vm.startPrank(payer);
        usd.approve(address(reg), bond);
        reg.register(r, bond, sig);
        vm.stopPrank();
    }

    /// A fresh key registered as a TDX candidate on its own host, bonded `bond`.
    function _candidate(uint256 bond) internal returns (address key) {
        key = _nextKey();
        _register(_reg(key, makeAddr(string.concat("op-", vm.toString(key))), keccak256(abi.encode(key)), FAMILY_A), bond, key);
    }

    /// Qualifies a candidate: QUALIFY_VERDICTS revealed shadow verdicts, all agreeing.
    function _qualify(address key) internal {
        for (uint256 i; i < 20; ++i) {
            panels.recordShadow(key, true);
            panels.scoreShadow(key, true);
        }
    }

    function _active(uint256 bond) internal returns (address key) {
        key = _candidate(bond);
        _qualify(key);
    }

    function _state(address key) internal view returns (IValidators.State) {
        return reg.validator(key).state;
    }

    function _bond(address key) internal view returns (uint256) {
        return reg.validator(key).bond;
    }
}
