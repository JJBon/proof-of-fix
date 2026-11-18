// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Test} from "forge-std/Test.sol";
import {Verdicts} from "../../src/v2/Verdicts.sol";
import {genesis} from "./helpers/GenesisV2.sol";
import {Heads} from "../../src/v2/Heads.sol";
import {Pool} from "../../src/v2/Pool.sol";
import {MockCoin} from "../mocks/MockCoin.sol";
import {FeeCoin} from "../mocks/FeeCoin.sol";

/// v2 (proof-of-fix#85, task 5.1, design S10): the contracts split out of the race. Verdicts (the quorum shared by every
/// v2 contract), Heads (the head registry's genesis) and Pool (the sponsors' pot, with no way out but its rules).
contract SplitV2Test is Test {
    uint256[] secrets;
    address[] keys;
    Verdicts verdicts;

    function setUp() public {
        for (uint256 i; i < 3; ++i) {
            (address a, uint256 k) = makeAddrAndKey(string.concat("judge", vm.toString(i)));
            keys.push(a);
            secrets.push(k);
            for (uint256 j = keys.length - 1; j > 0 && keys[j - 1] > keys[j]; --j) {
                (keys[j - 1], keys[j]) = (keys[j], keys[j - 1]);
                (secrets[j - 1], secrets[j]) = (secrets[j], secrets[j - 1]);
            }
        }
        verdicts = new Verdicts(genesis(keys, 2, new address[](0), new address[](0)));
    }

    function _sigs(bytes32 digest, uint256[] memory order) internal view returns (bytes[] memory sigs) {
        sigs = new bytes[](order.length);
        for (uint256 i; i < order.length; ++i) {
            (uint8 v, bytes32 r, bytes32 s) = vm.sign(secrets[order[i]], digest);
            sigs[i] = abi.encodePacked(r, s, v);
        }
    }

    function _pair(uint256 a, uint256 b) internal pure returns (uint256[] memory o) {
        o = new uint256[](2);
        o[0] = a;
        o[1] = b;
    }

    // ---------- Verdicts ----------

    /// The quorum's rules, as v1's OracleAuth: enough distinct keys, in increasing order, each digest once per caller.
    function test_verdictsQuorumRules() public {
        bytes32 d = keccak256("a verdict");
        vm.expectRevert(Verdicts.TooFewSignatures.selector);
        verdicts.authorize(d, _sigs(d, new uint256[](1)));
        vm.expectRevert(Verdicts.DuplicateSigner.selector); // out of order (or the same key twice)
        verdicts.authorize(d, _sigs(d, _pair(1, 0)));
        (, uint256 outsider) = makeAddrAndKey("outsider");
        bytes[] memory forged = _sigs(d, _pair(0, 1));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(outsider, d);
        forged[1] = abi.encodePacked(r, s, v);
        vm.expectRevert(Verdicts.NotOracle.selector);
        verdicts.authorize(d, forged);
        verdicts.authorize(d, _sigs(d, _pair(0, 1)));
        assertTrue(verdicts.used(address(this), d));
        vm.expectRevert(Verdicts.Replayed.selector);
        verdicts.authorize(d, _sigs(d, _pair(0, 2)));
        vm.prank(address(0xCAFE)); // another caller has its own digests
        verdicts.authorize(d, _sigs(d, _pair(0, 2)));
    }

    /// Every external function of Verdicts, from the compiled ABI (task 5.3: "no function changing the counts"). No key,
    /// count, quorum or operator can be added, removed or changed (5.4 brings the entrenched rotation rule): the only
    /// state-changing functions are the three authorizations, which change nothing but the caller's spent digests.
    function test_verdictsHaveNoPrivilegedCall() public view {
        // Task 5.4 (S13): seats change only by a key's rotation (or a vacant seat's join), its activation after the
        // delay, and a suspension the seat's own key can lift; nothing adds, removes or replaces a seat's operator,
        // family or provider, the counts, or the allowed images and attestation types.
        string[30] memory allowed = [
            // the version's quorum, the issue tier drawn by seed, the constitution tier (D3, S2)
            "authorize", "authorizeDrawn", "authorizeAll",
            // a seat's key: rotation or join, activation, suspension and its lifting (S13)
            "rotate", "activate", "suspend", "resume",
            // views: the draw, the keys, the seats, the operators' disclosed accounts, the counts (constants), the
            // lists, the pending keys, the digests to sign and the spent digests
            "drawn", "keys", "operatorsOf", "operatorsOfSeat", "seatOf", "isOracle", "isActive", "seat", "seatCount",
            "quorum", "used", "pending", "allowedImage", "acceptedType", "domainSeparator", "rotateDigest",
            "suspendDigest", "resumeDigest", "ISSUE_JUDGES", "ISSUE_QUORUM", "KEY_ROTATION_DELAY", "PROVIDER_SEAT_CAP",
            "NO_ATTESTATION"
        ];
        string memory json = vm.readFile("out/Verdicts.sol/Verdicts.json");
        uint256 found;
        for (uint256 i;; ++i) {
            string memory key = string.concat(".abi[", vm.toString(i), "]");
            if (!vm.keyExistsJson(json, key)) break;
            if (keccak256(bytes(vm.parseJsonString(json, string.concat(key, ".type")))) != keccak256("function")) {
                continue;
            }
            string memory name = vm.parseJsonString(json, string.concat(key, ".name"));
            bool ok;
            for (uint256 j; j < allowed.length && !ok; ++j) {
                ok = keccak256(bytes(name)) == keccak256(bytes(allowed[j]));
            }
            assertTrue(ok, string.concat("unexpected external function: ", name));
            ++found;
        }
        assertEq(found, allowed.length);
    }

    // ---------- Heads ----------

    function test_headsGenesis() public {
        bytes32[] memory repos = new bytes32[](2);
        bytes32[] memory commits = new bytes32[](2);
        repos[0] = keccak256("rad:proof-of-fix");
        repos[1] = keccak256("rad:heartwood");
        commits[0] = bytes32(bytes20(hex"1cb8c28fee0040cd20deda7fcde3d88765c749b4"));
        commits[1] = bytes32(bytes20(hex"935253d000000000000000000000000000000000"));
        Heads h = new Heads(verdicts, repos, commits, keccak256("CONSTITUTION.md at genesis"), address(this));
        assertEq(h.repos().length, 2);
        Heads.Head memory g = h.head(repos[0]);
        assertEq(g.commit, commits[0]);
        assertEq(g.constitution, keccak256("CONSTITUTION.md at genesis"));
        assertEq(g.movedAt, block.timestamp);
        assertEq(address(h.verdicts()), address(verdicts));
        vm.expectRevert(abi.encodeWithSelector(Heads.UnknownRepo.selector, bytes32(uint256(1))));
        h.head(bytes32(uint256(1)));
    }

    function test_headsGenesisChecked() public {
        bytes32[] memory repos = new bytes32[](2);
        bytes32[] memory commits = new bytes32[](2);
        repos[0] = keccak256("a");
        repos[1] = keccak256("a"); // twice
        commits[0] = bytes32(uint256(1));
        commits[1] = bytes32(uint256(2));
        vm.expectRevert(Heads.BadParams.selector);
        new Heads(verdicts, repos, commits, keccak256("c"), address(this));
        repos[1] = keccak256("b");
        commits[1] = bytes32(0); // no commit
        vm.expectRevert(Heads.BadParams.selector);
        new Heads(verdicts, repos, commits, keccak256("c"), address(this));
        commits[1] = bytes32(uint256(2));
        vm.expectRevert(Heads.BadParams.selector); // no constitution
        new Heads(verdicts, repos, commits, bytes32(0), address(this));
        vm.expectRevert(Heads.BadParams.selector); // not a contract
        new Heads(Verdicts(address(0xBEEF)), repos, commits, keccak256("c"), address(this));
        vm.expectRevert(Heads.BadParams.selector); // no mover
        new Heads(verdicts, repos, commits, keccak256("c"), address(0));
    }

    /// Since 5.2 one write: `move`, for its mover only (the RaceV2 that created it, on a verdict v2). The rest are views.
    function test_headsHaveOneWrite() public view {
        string[6] memory allowed = ["verdicts", "mover", "repos", "isRepo", "head", "move"];
        _onlyFunctions("out/Heads.sol/Heads.json", allowed, 6);
    }

    // ---------- Pool ----------

    function test_poolFundedByAnyone() public {
        MockCoin usd = new MockCoin("Mock USD", "mUSD", 6);
        address[] memory coins = new address[](1);
        coins[0] = address(usd);
        Pool p = new Pool(coins);
        address sponsor = makeAddr("sponsor");
        usd.mint(sponsor, 100e6);
        vm.startPrank(sponsor);
        usd.approve(address(p), type(uint256).max);
        assertEq(p.fund(address(usd), 40e6), 40e6);
        vm.stopPrank();
        assertEq(p.held(address(usd)), 40e6);
        assertEq(p.funded(address(usd)), 40e6);
        assertEq(p.fundedBy(address(usd), sponsor), 40e6);
        assertEq(usd.balanceOf(address(p)), 40e6);
        MockCoin other = new MockCoin("Other", "OTH", 6);
        vm.expectRevert(abi.encodeWithSelector(Pool.NotFeeCoin.selector, address(other)));
        p.fund(address(other), 1);
    }

    /// A coin that charges on transfer is credited with what arrived.
    function test_poolCountsWhatArrived() public {
        FeeCoin fee = new FeeCoin();
        address[] memory coins = new address[](1);
        coins[0] = address(fee);
        Pool p = new Pool(coins);
        fee.mint(address(this), 100e6);
        fee.approve(address(p), type(uint256).max);
        assertEq(p.fund(address(fee), 100e6), 99e6);
        assertEq(p.held(address(fee)), 99e6);
        assertEq(fee.balanceOf(address(p)), 99e6);
    }

    /// Spec "The sponsors' pool": no withdraw function, no owner. Its only write is fund.
    function test_poolHasNoWayOut() public view {
        string[6] memory allowed = ["fund", "coins", "isFeeCoin", "held", "funded", "fundedBy"];
        _onlyFunctions("out/Pool.sol/Pool.json", allowed, 6);
    }

    /// The ABI's functions are exactly the allowed ones (the first n entries).
    function _onlyFunctions(string memory artifact, string[6] memory allowed, uint256 n) internal view {
        string memory json = vm.readFile(artifact);
        uint256 found;
        for (uint256 i;; ++i) {
            string memory key = string.concat(".abi[", vm.toString(i), "]");
            if (!vm.keyExistsJson(json, key)) break;
            if (keccak256(bytes(vm.parseJsonString(json, string.concat(key, ".type")))) != keccak256("function")) {
                continue;
            }
            string memory name = vm.parseJsonString(json, string.concat(key, ".name"));
            bool ok;
            for (uint256 j; j < n && !ok; ++j) {
                ok = keccak256(bytes(name)) == keccak256(bytes(allowed[j]));
            }
            assertTrue(ok, string.concat("unexpected external function: ", name));
            ++found;
        }
        assertEq(found, n);
    }
}
