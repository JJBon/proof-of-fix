// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {Script} from "forge-std/Script.sol";
import {console} from "forge-std/console.sol";
import {Race} from "../src/Race.sol";
import {DeployScript} from "./Deploy.s.sol";
import {MockCoin} from "../test/mocks/MockCoin.sol";
import {Oracles} from "../test/helpers/Oracles.sol";

/// The oracle path's scenarios against the devnet (proof-of-fix#93, comment 4603): the contract side of the signed
/// quorum (#75, design D3), run on a fork of the devnet's current state against the deployed Race. Nothing is
/// broadcast: the script registers issues and relays signed actions in the fork only. Run it through
/// `scripts/devnet.sh scenarios`, which reads the record and passes the oracle keys on stdin (ORACLE_KEYS):
///   SCENARIO_RECORD   the deployment record (deployments/devnet.json)
/// Each scenario logs `SCENARIO <name>: ok` or `... FAIL`, the gas lines log `GAS ...`, and the script reverts at the
/// end if any scenario failed.
contract ScenariosScript is Script {
    function run() external {
        string memory json = vm.readFile(string.concat("./", vm.envOr("SCENARIO_RECORD", string("deployments/devnet.json"))));
        OracleScenarios s = new OracleScenarios();
        s.run(
            Race(vm.parseJsonAddress(json, ".race")),
            MockCoin(vm.parseJsonAddress(json, ".coin")),
            vm.envUint("ORACLE_KEYS", ","),
            vm.parseJsonUint(json, ".quorum")
        );
        // The gas lines deploy a Race each, one call apiece: Osaka caps a transaction's gas (EIP-7825, about 16.8M).
        s.gasAt(7, 4, 4, 7);
        s.gasAt(5, 3, 3, 5);
        s.gasAt(3, 2, 3, 3);
        s.finish();
    }
}

/// The scenarios themselves, in a contract of their own (a forge script mustn't rely on its own address): it
/// registers issues, pays their fees in the test coin and relays the signed actions, all in the fork.
contract OracleScenarios is Oracles {
    Race internal race;
    MockCoin internal coin;
    uint256 internal failures;
    uint256 internal weight = 100;

    function run(Race race_, MockCoin coin_, uint256[] calldata keys, uint256 quorum) external {
        race = race_;
        coin = coin_;
        _oraclesFrom(keys, quorum);
        require(race.quorum() == oracleQuorum, "record and contract disagree on the quorum");
        for (uint256 i; i < oracleSet.length; ++i) {
            require(race.isOracle(oracleSet[i]), "a key from OpenBao is not one of the deployed oracles");
        }
        coin.mint(address(this), 1_000_000e6);
        coin.approve(address(race), type(uint256).max);

        _honestQuorum();
        _minorityDissent();
        _tooFewSigners();
        _unknownKey();
        _forgedSignature();
        _duplicateSigner();
        _replayed();
        _wrongChain();
        _wrongContract();
        _colludingMinority();
        console.log(string.concat("GAS accept, deployed Race (", vm.toString(oracleSet.length), " keys, quorum ",
            vm.toString(oracleQuorum), "), ", vm.toString(oracleQuorum), " signatures: ",
            vm.toString(_acceptGas(race, _first(oracleQuorum)))));
    }

    function finish() external view {
        console.log(string.concat("SCENARIOS failed: ", vm.toString(failures)));
        require(failures == 0, "oracle-path scenarios failed");
    }

    // ---------- scenarios ----------

    /// The quorum of distinct oracle keys signs: the bounty opens.
    function _honestQuorum() internal {
        uint256 issue = race.register(address(coin));
        bytes32 n = _nonce();
        Race.Signed memory a = _signWith(race, _acceptHash(issue, weight, n), n, _first(oracleQuorum));
        try race.accept(issue, weight, a) returns (uint256 b) {
            _check("honest quorum opens the bounty", race.issue(issue).bounty == b);
        } catch (bytes memory err) {
            _fail("honest quorum opens the bounty", err);
        }
    }

    /// Every key signs: a quorum plus the dissenters' agreement changes nothing; a dissenting minority signing another
    /// action (junk) alone doesn't reach the quorum.
    function _minorityDissent() internal {
        uint256 issue = race.register(address(coin));
        uint256 dissent = oracleSet.length - oracleQuorum; // the keys outside the quorum
        bytes32 j = _nonce();
        Race.Signed memory junkBy = _signWith(race, _junkHash(issue, j), j, _last(dissent));
        _expect("dissenting minority can't junk the issue", address(race), abi.encodeCall(race.junk, (issue, junkBy)),
            Race.TooFewSignatures.selector);
        bytes32 n = _nonce();
        Race.Signed memory a = _signWith(race, _acceptHash(issue, weight, n), n, _first(oracleQuorum));
        try race.accept(issue, weight, a) {
            _check("the quorum still opens it despite the dissent", race.issue(issue).bounty != 0);
        } catch (bytes memory err) {
            _fail("the quorum still opens it despite the dissent", err);
        }
    }

    /// One signature short of the quorum (operators offline): refused.
    function _tooFewSigners() internal {
        uint256 issue = race.register(address(coin));
        bytes32 n = _nonce();
        Race.Signed memory a = _signWith(race, _acceptHash(issue, weight, n), n, _first(oracleQuorum - 1));
        _expect("too few signers", address(race), abi.encodeCall(race.accept, (issue, weight, a)),
            Race.TooFewSignatures.selector);
    }

    /// A quorum where one key isn't in the deployed set: refused.
    function _unknownKey() internal {
        uint256 issue = race.register(address(coin));
        bytes32 n = _nonce();
        (, uint256 outsider) = makeAddrAndKey("not-an-oracle");
        uint256[] memory keys = _first(oracleQuorum);
        keys[oracleQuorum - 1] = outsider;
        Race.Signed memory a = _signSorted(_acceptHash(issue, weight, n), n, keys);
        _expect("a key outside the set", address(race), abi.encodeCall(race.accept, (issue, weight, a)),
            Race.NotOracle.selector);
    }

    /// A signature that isn't one (random bytes in the right length): refused by the signature check itself.
    function _forgedSignature() internal {
        uint256 issue = race.register(address(coin));
        bytes32 n = _nonce();
        Race.Signed memory a = _signWith(race, _acceptHash(issue, weight, n), n, _first(oracleQuorum));
        a.sigs[0] = abi.encodePacked(keccak256("forged r"), keccak256("forged s"), uint8(27));
        (bool ok,) = address(race).call(abi.encodeCall(race.accept, (issue, weight, a)));
        _check("a forged signature is refused", !ok && race.issue(issue).bounty == 0);
    }

    /// The same oracle twice to reach the quorum: refused.
    function _duplicateSigner() internal {
        uint256 issue = race.register(address(coin));
        bytes32 n = _nonce();
        uint256[] memory keys = _first(oracleQuorum);
        keys[1] = keys[0];
        Race.Signed memory a = _signWith(race, _acceptHash(issue, weight, n), n, keys);
        _expect("the same oracle twice", address(race), abi.encodeCall(race.accept, (issue, weight, a)),
            Race.DuplicateSigner.selector);
    }

    /// A signed action relayed again: refused (each digest is used once).
    function _replayed() internal {
        uint256 issue = race.register(address(coin));
        bytes32 n = _nonce();
        Race.Signed memory a = _signWith(race, _acceptHash(issue, weight, n), n, _first(oracleQuorum));
        race.accept(issue, weight, a);
        _expect("a replayed signature", address(race), abi.encodeCall(race.accept, (issue, weight, a)),
            Race.Replayed.selector);
    }

    /// The quorum signed the same action for another chain (mainnet's id): the signers recovered here aren't oracles.
    function _wrongChain() internal {
        uint256 issue = race.register(address(coin));
        bytes32 n = _nonce();
        bytes32 digest = _digestFor(1, address(race), _acceptHash(issue, weight, n));
        Race.Signed memory a = _signDigest(digest, n, _first(oracleQuorum));
        _expect("signed for another chain", address(race), abi.encodeCall(race.accept, (issue, weight, a)),
            Race.NotOracle.selector);
    }

    /// The quorum signed the same action for another Race (another verifying contract): refused here.
    function _wrongContract() internal {
        uint256 issue = race.register(address(coin));
        bytes32 n = _nonce();
        bytes32 digest = _digestFor(block.chainid, address(0xdead), _acceptHash(issue, weight, n));
        Race.Signed memory a = _signDigest(digest, n, _first(oracleQuorum));
        _expect("signed for another contract", address(race), abi.encodeCall(race.accept, (issue, weight, a)),
            Race.NotOracle.selector);
    }

    /// A colluding minority signs a bad verdict (junk an issue an honest quorum would accept): below the quorum.
    function _colludingMinority() internal {
        uint256 issue = race.register(address(coin));
        bytes32 j = _nonce();
        Race.Signed memory a = _signWith(race, _junkHash(issue, j), j, _first(oracleQuorum - 1));
        _expect("a colluding minority", address(race), abi.encodeCall(race.junk, (issue, a)),
            Race.TooFewSignatures.selector);
    }

    /// The gas of `accept` on a fresh Race with `n` keys and quorum `q` (deployed in the fork), for `from` to `to`
    /// signatures: the signature check's cost per extra signer is the difference between lines.
    function gasAt(uint256 n, uint256 q, uint256 from, uint256 to) external {
        _makeOracles(n, q);
        Race r = _raceWithCurrentOracles();
        coin.approve(address(r), type(uint256).max);
        uint256 previous;
        for (uint256 sigs = from; sigs <= to; ++sigs) {
            uint256 g = _acceptGas(r, _first(sigs));
            console.log(string.concat("GAS accept, ", vm.toString(n), " keys quorum ", vm.toString(q), ", ",
                vm.toString(sigs), " signatures: ", vm.toString(g),
                previous == 0 ? "" : string.concat(" (+", vm.toString(g - previous), ")")));
            previous = g;
        }
    }

    // ---------- helpers ----------

    function _acceptGas(Race r, uint256[] memory keys) internal returns (uint256 used) {
        uint256 issue = r.register(address(coin));
        bytes32 n = _nonce();
        Race.Signed memory a = _signWith(r, _acceptHash(issue, weight, n), n, keys);
        uint256 before = gasleft();
        r.accept(issue, weight, a);
        used = before - gasleft();
    }

    function _raceWithCurrentOracles() internal returns (Race) {
        DeployScript d = new DeployScript();
        address[] memory feeCoins = new address[](1);
        feeCoins[0] = address(coin);
        return _newRace(d.config(address(0xA11), address(0xB22)), feeCoins, 1_000, 100_000);
    }

    /// The oracle keys from the environment (OpenBao's, or anvil's with DEVNET_KEYS=insecure-local), sorted by
    /// address as the contract requires, and the deployed quorum.
    function _oraclesFrom(uint256[] calldata keys, uint256 quorum) internal {
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
        oracleQuorum = quorum;
    }

    /// The first k oracle keys, in address order.
    function _first(uint256 k) internal view returns (uint256[] memory keys) {
        keys = new uint256[](k);
        for (uint256 i; i < k; ++i) {
            keys[i] = oracleSecrets[i];
        }
    }

    /// The last k oracle keys, in address order.
    function _last(uint256 k) internal view returns (uint256[] memory keys) {
        keys = new uint256[](k);
        for (uint256 i; i < k; ++i) {
            keys[i] = oracleSecrets[oracleSecrets.length - k + i];
        }
    }

    /// Signatures from the given keys, put in signer-address order (so only the key itself can fail the check).
    function _signSorted(bytes32 structHash, bytes32 nonce, uint256[] memory keys)
        internal
        view
        returns (Race.Signed memory)
    {
        for (uint256 i = 1; i < keys.length; ++i) {
            for (uint256 j = i; j > 0 && vm.addr(keys[j - 1]) > vm.addr(keys[j]); --j) {
                (keys[j - 1], keys[j]) = (keys[j], keys[j - 1]);
            }
        }
        return _signWith(race, structHash, nonce, keys);
    }

    function _digestFor(uint256 chainId, address verifyingContract, bytes32 structHash) internal pure returns (bytes32) {
        bytes32 domain = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256("proof-of-fix Race"),
                keccak256("1"),
                chainId,
                verifyingContract
            )
        );
        return keccak256(abi.encodePacked("\x19\x01", domain, structHash));
    }

    function _signDigest(bytes32 digest, bytes32 nonce, uint256[] memory keys)
        internal
        pure
        returns (Race.Signed memory a)
    {
        a.nonce = nonce;
        a.sigs = new bytes[](keys.length);
        for (uint256 i; i < keys.length; ++i) {
            (uint8 v, bytes32 r, bytes32 s) = vm.sign(keys[i], digest);
            a.sigs[i] = abi.encodePacked(r, s, v);
        }
    }

    /// The call reverts with exactly this error.
    function _expect(string memory name, address to, bytes memory data, bytes4 selector) internal {
        (bool ok, bytes memory err) = to.call(data);
        if (!ok && err.length >= 4 && bytes4(err) == selector) {
            console.log(string.concat("SCENARIO ", name, ": ok"));
        } else {
            _fail(name, ok ? bytes("it succeeded") : err);
        }
    }

    function _check(string memory name, bool ok) internal {
        if (ok) {
            console.log(string.concat("SCENARIO ", name, ": ok"));
        } else {
            _fail(name, "");
        }
    }

    function _fail(string memory name, bytes memory detail) internal {
        ++failures;
        console.log(string.concat("SCENARIO ", name, ": FAIL ", vm.toString(detail)));
    }
}
