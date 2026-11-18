// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Validators} from "../../../src/v3/Validators.sol";
import {IValidators} from "../../../src/v3/IValidators.sol";
import {FeesV3} from "../../../src/v3/FeesV3.sol";
import {IFeesV3, IFeesV3Validators} from "../../../src/v3/IFeesV3.sol";
import {Panels} from "../../../src/v3/Panels.sol";
import {Status, Tier, Kind, Submission, Panel} from "../../../src/v3/PanelsBase.sol";
import {IPanelsRegistry, IPanelsFees, IPanelsHost, IPanelScores} from "../../../src/v3/IPanels.sol";
import {PanelScores} from "../../../src/v3/PanelScores.sol";
import {ValidatorsSetup, ValidatorsWithZkTls, TDX, SEV_SNP, NITRO, SGX, IMAGE} from "./ValidatorsSetup.sol";

bytes32 constant IBM_SE = keccak256("ibm-secure-execution");
bytes32 constant ZKTLS = keccak256("zktls");

interface IERC20Approve {
    function approve(address spender, uint256 amount) external returns (bool);
}

/// The race as Panels sees it in these tests: it binds Panels, opens and withdraws submissions, and answers who the
/// parties are (set by the test).
contract MockRace is IPanelsHost {
    Panels public immutable panels;
    mapping(uint256 => mapping(address => bool)) public party;

    constructor(Panels p) {
        panels = p;
        p.bind();
    }

    function setParty(uint256 id, address account, bool on) external {
        party[id][account] = on;
    }

    function isParty(uint256 id, address account) external view returns (bool) {
        return party[id][account];
    }

    function open(uint256 id, bytes32 commitment, uint256 bounty) external {
        panels.open(id, commitment, bounty);
    }

    function openHidden(uint256 id, bytes32 commitment, uint256 bounty) external {
        panels.openHidden(id, commitment, bounty);
    }

    /// The race pays the ADR deposit itself (from its author, in the real race).
    function openConstitution(uint256 id, bytes32 commitment, Tier tier, uint256 bounty, address author)
        external
    {
        IERC20Approve(panels.coin()).approve(address(panels), type(uint256).max);
        panels.openConstitution(id, commitment, tier, bounty, author);
    }

    function challenge(uint256 id, address challenger, bytes32 evidence) external {
        panels.challenge(id, challenger, evidence);
    }

    function withdraw(uint256 id) external {
        panels.withdraw(id);
    }
}

/// A registry, a meter, Panels and a race for the panel tests. The registry's genesis validator is level A, TDX, family
/// F0, bonded $1,250 (every tier). Validators added by the tests are active (qualified through Panels' hooks, which
/// only Panels may call, by pranking it), each with its own operator and, unless told, its own host.
abstract contract PanelsSetup is ValidatorsSetup {
    uint256 internal constant FAMILIES = 7;
    uint256 internal constant FULL_BOND = 1_250e6;

    FeesV3 internal fees;
    PanelScores internal scores;
    Panels internal pn;
    MockRace internal race;
    address internal genesisKey;
    mapping(uint256 pid => mapping(address key => bool)) internal voteOf;

    function _family(uint256 i) internal pure returns (bytes32) {
        return keccak256(abi.encode("family", i));
    }

    function _tee(uint256 i) internal pure returns (bytes32) {
        bytes32[5] memory t = [TDX, SEV_SNP, NITRO, SGX, IBM_SE];
        return t[i % 5];
    }

    /// Deploys the version with `teeTypes` accepted (3: D6's launch types; 5: with SGX and IBM Secure Execution) and
    /// `zk` listing zkTLS (as an adding ADR will; test-only registry), FAMILIES priced families, and binds the race.
    function _deployVersion(uint256 teeTypes, bool zk) internal {
        _deployCoinAndPool();
        genesisKey = _newKey("genesis");
        IValidators.Registration[] memory gs = new IValidators.Registration[](1);
        gs[0] = _reg(genesisKey, makeAddr("genesis operator"), keccak256("host-genesis"), _family(0));
        Validators.Genesis memory g = _genesis(false, gs, FULL_BOND);
        g.teeTypes = new bytes32[](teeTypes);
        for (uint256 i; i < teeTypes; ++i) {
            g.teeTypes[i] = _tee(i);
        }
        if (zk) {
            vm.prank(deployer);
            reg = new ValidatorsWithZkTls(g);
        } else {
            reg = _create(g);
        }
        scores = new PanelScores();
        fees = new FeesV3(IFeesV3Validators(address(reg)), scores, _feesGenesis());
        pn = new Panels(
            IPanelsRegistry(address(reg)), IPanelsFees(address(fees)), IPanelScores(address(scores)), g.teeTypes
        );
        race = new MockRace(pn);
    }

    function _feesGenesis() internal view returns (FeesV3.Genesis memory g) {
        g.coin = address(usd);
        g.shared = [uint256(11_244_444), 1_234_722, 269_531_250, 2_700_000_000];
        g.families = new bytes32[](FAMILIES);
        g.tokens = new uint256[3][](FAMILIES);
        for (uint256 i; i < FAMILIES; ++i) {
            g.families[i] = _family(i);
            g.tokens[i] = [uint256(4_000_000), 200_000, 20_000_000];
        }
        g.caps = IFeesV3.Caps(140_000, 16_000, 20, 1_000_000, 50_000, 1 gwei);
        g.defaultProfile = IFeesV3.Profile(keccak256("image"), 2_000, 4_096, 1_200);
    }

    /// An active validator: TEE `tee` at `level` (or zkTLS when `tee` is 0), on `host`, of `family`, bonded `bond`.
    function _add(bytes32 host, bytes32 family, bytes32 tee, uint8 level, uint256 bond) internal returns (address key) {
        key = _addCandidate(host, family, tee, level, bond);
        _qualifyV(key);
    }

    function _addCandidate(bytes32 host, bytes32 family, bytes32 tee, uint8 level, uint256 bond)
        internal
        returns (address key)
    {
        key = _nextKey();
        IValidators.Registration memory r = _reg(key, makeAddr(string.concat("op-", vm.toString(key))), host, family);
        if (tee == 0) {
            r.proofType = ZKTLS;
            r.teeType = 0;
            r.attestation = 0;
            r.level = 0;
        } else {
            r.teeType = tee;
            r.level = level;
        }
        _register(r, bond, key);
    }

    /// The i-th of a spread network: its own host, family i mod `families`, TEE type i mod `types`, level A, full bond.
    function _addSpread(uint256 i, uint256 families, uint256 types) internal returns (address) {
        return _add(keccak256(abi.encode("host", i)), _family(i % families), _tee(i % types), 1, FULL_BOND);
    }

    /// `n` spread validators besides the genesis one (whose family is 0 and TEE type TDX).
    function _network(uint256 n, uint256 families, uint256 types) internal returns (address[] memory keys) {
        keys = new address[](n);
        for (uint256 i; i < n; ++i) {
            keys[i] = _addSpread(i + 1, families, types);
        }
    }

    function _qualifyV(address key) internal {
        vm.startPrank(address(pn));
        for (uint256 i; i < 20; ++i) {
            reg.recordShadow(key, true);
            reg.scoreShadow(key, true);
        }
        vm.stopPrank();
    }

    // ---------- submissions and draws ----------

    function _open(uint256 id, uint256 bounty) internal {
        race.open(id, keccak256(abi.encode("commitment", id)), bounty);
    }

    /// Rolls past the seed block, gives it a hash, and draws; returns the panel id (0 if it waits).
    function _draw(uint256 id) internal returns (uint256) {
        uint256 sb = pn.submission(id).seedBlock;
        if (vm.getBlockNumber() <= sb) vm.roll(sb + 1);
        vm.setBlockhash(sb, keccak256(abi.encode("block", sb)));
        pn.draw(id);
        Submission memory s = pn.submission(id);
        return s.status == Status.Judging ? s.pid : 0;
    }

    function _seedFor(uint256 id) internal view returns (bytes32) {
        Submission memory s = pn.submission(id);
        return pn.seedOf(keccak256(abi.encode("block", uint256(s.seedBlock))), s.commitment, s.bounty, id);
    }

    function _openAndDraw(uint256 id, uint256 bounty) internal returns (uint256) {
        _open(id, bounty);
        return _draw(id);
    }

    // ---------- the judges' statements ----------

    function _salt(uint256 pid, address key) internal pure returns (bytes32) {
        return keccak256(abi.encode("salt", pid, key));
    }

    function _stmt(address key, bytes32 tag, uint256 pid, bytes32 content) internal view returns (bytes memory) {
        return _signDigest(key, pn.statementDigest(pn.subjectOf(tag, pid, key), content));
    }

    mapping(uint256 pid => mapping(address key => uint8)) internal maskOf;

    function _seal(uint256 pid, address key, bool vote) internal {
        _sealMask(pid, key, vote, 0);
    }

    function _sealMask(uint256 pid, address key, bool vote, uint8 mask) internal {
        voteOf[pid][key] = vote;
        maskOf[pid][key] = mask;
        bytes32 c = pn.commitmentOf(pid, key, vote, mask, _salt(pid, key));
        pn.seal(pid, key, c, _stmt(key, pn.SEAL_TAG(), pid, c));
    }

    function _reveal(uint256 pid, address key) internal {
        _revealReverts(pid, key, bytes4(0));
    }

    /// The reveal, expected to revert with `err` (none if 0); the signature is made before the expectation.
    function _revealReverts(uint256 pid, address key, bytes4 err) internal {
        bool vote = voteOf[pid][key];
        uint8 mask = maskOf[pid][key];
        bytes32 salt = _salt(pid, key);
        bytes memory sig = _stmt(key, pn.REVEAL_TAG(), pid, keccak256(abi.encode(vote, mask, salt)));
        if (err != 0) vm.expectRevert(err);
        pn.reveal(pid, key, vote, mask, salt, sig);
    }

    function _receipt(uint256 pid, address key) internal {
        _receiptReverts(pid, key, bytes4(0));
    }

    function _receiptReverts(uint256 pid, address key, bytes4 err) internal {
        bytes32 r = keccak256(abi.encode("receipt", pid, key));
        bytes memory sig = _stmt(key, pn.RECEIPT_TAG(), pid, r);
        if (err != 0) vm.expectRevert(err);
        pn.receipt(pid, key, r, sig);
    }

    /// Every seated judge seals `votes[i]` (slot order), then all reveal with receipts after the seal window.
    function _judge(uint256 pid, bool[] memory votes) internal {
        address[] memory js = pn.judges(pid);
        for (uint256 i; i < js.length; ++i) {
            _seal(pid, js[i], votes[i]);
        }
        vm.warp(pn.panel(pid).sealBy + 1);
        for (uint256 i; i < js.length; ++i) {
            _reveal(pid, js[i]);
            _receipt(pid, js[i]);
        }
    }

    function _votes(uint256 k, uint256 passes) internal pure returns (bool[] memory v) {
        v = new bool[](k);
        for (uint256 i; i < passes; ++i) {
            v[i] = true;
        }
    }

    function _rollPast(uint256 b) internal {
        if (vm.getBlockNumber() <= b) vm.roll(b + 1);
        vm.setBlockhash(b, keccak256(abi.encode("block", b)));
    }

    /// Draws the verdict's audits from its audit block (a second try from a re-targeted block and snapshot when the
    /// first finds nobody) and has every auditor drawn judge `agree`ing with it; returns how many were drawn now.
    function _runAudits(uint256 id, bool agree) internal returns (uint256 drawn) {
        Submission memory s = pn.submission(id);
        uint256 before = pn.panelCount();
        for (uint256 t; t < 2; ++t) {
            s = pn.submission(id);
            if (s.auditDecided && s.auditsDrawn == s.auditsDue) break;
            _rollPast(s.auditBlock);
            pn.drawAudits(id);
        }
        bool vote = agree ? s.pass : !s.pass;
        uint256 last = pn.panelCount();
        uint256 sealBy;
        for (uint256 q = before + 1; q <= last; ++q) {
            Panel memory p = pn.panel(q);
            if (p.kind != Kind.Audit || p.id != id) continue;
            _seal(q, pn.judges(q)[0], vote);
            sealBy = p.sealBy;
            ++drawn;
        }
        if (drawn == 0) return 0;
        vm.warp(sealBy + 1);
        for (uint256 q = before + 1; q <= last; ++q) {
            Panel memory p = pn.panel(q);
            if (p.kind != Kind.Audit || p.id != id) continue;
            _reveal(q, pn.judges(q)[0]);
            _receipt(q, pn.judges(q)[0]);
        }
    }

    /// Audits (agreeing), then waits out the window and finalizes.
    function _finalize(uint256 id) internal {
        _runAudits(id, true);
        uint256 at = pn.submission(id).finalAt;
        if (vm.getBlockTimestamp() < at) vm.warp(at);
        pn.finalize(id);
    }

    function _contains(address[] memory xs, address x) internal pure returns (bool) {
        for (uint256 i; i < xs.length; ++i) {
            if (xs[i] == x) return true;
        }
        return false;
    }
}
