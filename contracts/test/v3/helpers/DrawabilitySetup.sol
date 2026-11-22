// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {IValidators} from "../../../src/v3/IValidators.sol";
import {Status, Kind, Submission, Panel} from "../../../src/v3/PanelsBase.sol";
import {PanelRules, PanelRulesLib, Cap, ChallengeSize} from "../../../src/v3/PanelRules.sol";
import {PanelsSetup} from "./PanelsSetup.sol";
import {SEV_SNP} from "./ValidatorsSetup.sol";

/// The launch layouts of reports/challenge-drawability-v1.md (#251 contract batch 4, tasks 3.22-3.26): a deployment
/// with given panel rules, and validators bonded $250 (L17) laid out spread (each its own operator account and host,
/// three TEE types) or as the owner's (one operator account, one host value, or one TEE type).
abstract contract DrawabilitySetup is PanelsSetup {
    uint256 internal constant BOND = 250e6; // L17: a single judge's bounty limit is then $125
    bytes32 internal constant ONE_HOST = keccak256("the owner's one host value");
    bytes32 internal constant EVIDENCE = keccak256("a re-run that disagrees");
    bytes32 internal constant TEST_HASH = keccak256("a test that fails on the fixed code"); // a D21 dispute's evidence

    address internal owner = makeAddr("the owner's operator account");
    address internal challenger = makeAddr("challenger");
    uint256 internal nextId = 1;

    struct Layout {
        bool oneOperator; // every validator, the genesis one too, on the owner's operator account
        bool oneHost; // every validator but the genesis one on one host value
        bool oneTee; // every validator but the genesis one (TDX) on SEV-SNP
        uint8 level; // the added validators' level (0: A)
    }

    function _spread() internal pure returns (Layout memory) {}

    function _launch() internal pure returns (PanelRules memory) {
        return PanelRulesLib.launch();
    }

    function _strict() internal pure returns (PanelRules memory) {
        return PanelRulesLib.strict();
    }

    /// Deploys with rules `r`, the genesis validator laid out as `l` says.
    function _deployRules(PanelRules memory r, Layout memory l) internal {
        rules = r;
        genesisOperator = l.oneOperator ? owner : address(0);
        _deployVersion(3, false);
        usd.mint(address(race), 10_000e6);
    }

    /// `n` validators in all, the genesis one first: validator i of family i % `families`, laid out as `l`, bonded
    /// $250 and active.
    function _layout(uint256 n, uint256 families, Layout memory l) internal returns (address[] memory keys) {
        keys = new address[](n);
        keys[0] = genesisKey;
        for (uint256 i = 1; i < n; ++i) {
            keys[i] = _addLaid(i, families, l);
        }
    }

    function _addLaid(uint256 i, uint256 families, Layout memory l) internal returns (address key) {
        key = _nextKey();
        IValidators.Registration memory r = _reg(
            key,
            l.oneOperator ? owner : makeAddr(string.concat("op-", vm.toString(key))),
            l.oneHost ? ONE_HOST : keccak256(abi.encode("host", i, key)),
            _family(i % families)
        );
        r.teeType = l.oneTee ? SEV_SNP : _tee(i % 3);
        r.level = l.level == 0 ? 1 : l.level;
        _register(r, BOND, key);
        _qualifyV(key);
    }

    function _id() internal returns (uint256) {
        return nextId++;
    }

    function _all(uint256 k, bool v) internal pure returns (bool[] memory out) {
        out = new bool[](k);
        for (uint256 i; i < k; ++i) {
            out[i] = v;
        }
    }

    /// A counted verdict: drawn, every judge votes `pass`. Returns its panel (0 if the submission waits).
    function _verdict(uint256 id, uint256 bounty, bool pass) internal returns (uint256 pid) {
        pid = _openAndDraw(id, bounty);
        if (pid == 0) return 0;
        _judge(pid, _all(pn.panel(pid).k, pass));
    }

    /// Files a challenge (with `evidence`: a test's hash makes it a D21 dispute, the same path in Panels) and draws it;
    /// returns its panel (0 if it waits).
    function _challenge(uint256 id, bytes32 evidence) internal returns (uint256) {
        race.challenge(id, challenger, evidence);
        return _drawChallenge(id);
    }

    function _drawChallenge(uint256 id) internal returns (uint256) {
        _rollPast(pn.submission(id).challengeBlock);
        pn.drawChallenge(id);
        return pn.submission(id).challengePid;
    }

    /// A waiting challenge redrawn by its clock (L25): at its retry time it re-targets, then it draws from the new seed
    /// block. Returns its panel (0 if it waits again).
    function _retryChallenge(uint256 id) internal returns (uint256) {
        Submission memory s = pn.submission(id);
        if (vm.getBlockTimestamp() < s.challengeRetryAt) vm.warp(s.challengeRetryAt);
        pn.drawChallenge(id); // re-targets
        return _drawChallenge(id);
    }

    /// How a challenge ends, driven as a keeper would: its panel judged (every judge votes `pass`), or, waiting, redrawn
    /// at each retry time until CHALLENGE_DEADLINE, then lapsed. Returns 1 counted, 2 lapsed; `how` is how it was
    /// drawn (0 never, 1 fresh, 2 D27's second draw).
    function _endChallenge(uint256 id, uint256 cpid, bool pass) internal returns (uint256 ending, uint256 how) {
        while (cpid == 0) {
            Submission memory s = pn.submission(id);
            if (s.challengeEpoch == 0 || s.challengeRetryAt > s.challengeBy) break;
            cpid = _retryChallenge(id);
        }
        if (cpid == 0) {
            vm.warp(pn.submission(id).challengeBy + 1);
            pn.lapseChallenge(id);
            return (2, 0);
        }
        how = pn.panel(cpid).ex == 0 ? 2 : 1;
        _judge(cpid, _all(pn.panel(cpid).k, pass));
        return (1, how);
    }

    /// The validators outside panel `pid` (and its auditors and replaced judges) among `keys`.
    function _outside(address[] memory keys, uint256 pid) internal view returns (uint256 n) {
        address[] memory js = pn.judges(pid);
        for (uint256 i; i < keys.length; ++i) {
            if (!_contains(js, keys[i])) ++n;
        }
    }

    /// Pauses `key` (capacity 0) and waits CAP_DELAY blocks for it to take effect (L16).
    function _pause(address key, uint256 checks) internal {
        vm.prank(key);
        pn.setCapacity(key, checks);
        vm.roll(vm.getBlockNumber() + pn.CAP_DELAY() + 1);
    }
}
