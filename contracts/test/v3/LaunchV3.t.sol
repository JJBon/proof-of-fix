// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Validators} from "../../src/v3/Validators.sol";
import {IValidators} from "../../src/v3/IValidators.sol";
import {FeesV3} from "../../src/v3/FeesV3.sol";
import {IFeesV3, IFeesV3Validators} from "../../src/v3/IFeesV3.sol";
import {Panels} from "../../src/v3/Panels.sol";
import {Status, Kind, Submission} from "../../src/v3/PanelsBase.sol";
import {IPanelsRegistry, IPanelsFees, IPanelScores} from "../../src/v3/IPanels.sol";
import {PanelScores} from "../../src/v3/PanelScores.sol";
import {PoolV3} from "../../src/v3/PoolV3.sol";
import {RaceV3} from "../../src/v3/RaceV3.sol";
import {RaceV3Annex} from "../../src/v3/RaceV3Annex.sol";
import {RaceV3Base} from "../../src/v3/RaceV3Base.sol";
import {Windows, WindowsLib} from "../../src/v3/Windows.sol";
import {LaunchChain} from "../../src/v3/LaunchChain.sol";
import {Heads} from "../../src/v2/Heads.sol";
import {RaceV3Setup} from "./helpers/RaceV3Setup.sol";
import {ValidatorsSetup, PanelsHarness, FAMILY_A, FAMILY_B} from "./helpers/ValidatorsSetup.sol";
import {suiteWindows, TEST_REPO, TEST_GENESIS_HEAD} from "./helpers/SuiteWindows.sol";

/// proof-of-fix#251, contract batch 1 (tasks 3.1, 3.4, 3.8, 3.10; specs/deployment-binding): one repository and one
/// chain fixed at construction, the windows as constructor parameters, and the known findings of open problems 7.5.
/// Each scenario of the spec is tested under its name.
contract LaunchBindingV3Test is RaceV3Setup {
    bytes32 constant FIX = keccak256("fix");

    function setUp() public {
        _deployRace(3);
    }

    function _heads() internal view returns (Heads h) {
        (,,,, h,,) = rc.contracts();
    }

    // ---------- One repository, fixed at construction (3.1) ----------

    /// Scenario "Deployed for proof-of-fix": the head registry lists exactly that repository, with that commit as its
    /// genesis head, and no function adds another (Heads' only writer is `move`, by the race).
    function test_deployedForProofOfFix() public view {
        Heads h = _heads();
        bytes32[] memory repos = h.repos();
        assertEq(repos.length, 1);
        assertEq(repos[0], TEST_REPO);
        assertEq(h.head(TEST_REPO).commit, TEST_GENESIS_HEAD);
        assertEq(h.head(TEST_REPO).submission, 0);
        assertEq(rc.repo(), TEST_REPO);
        assertEq(fees.repo(), TEST_REPO);
        assertEq(h.mover(), address(rc));
        assertFalse(h.isRepo(keccak256("rad:another")));
    }

    /// Scenario "No repository given": a zero repository id or a zero genesis head, and nothing is deployed.
    function test_noRepositoryGiven() public {
        RaceV3Annex ax = new RaceV3Annex(_config(), 625, 100_000, pn, pool3, block.timestamp);
        vm.expectRevert(Heads.BadParams.selector); // Heads refuses a zero repository or head first
        this.deployRace(bytes32(0), TEST_GENESIS_HEAD, ax);
        vm.expectRevert(Heads.BadParams.selector);
        this.deployRace(TEST_REPO, bytes32(0), ax);
    }

    // Panels, RaceV3 and its annex link libraries or are too large to inline, so a test's `new` of them is a cheatcode
    // deployment: an expected revert must wrap an external call, or the rest of the test silently doesn't run.

    function deployRace(bytes32 repo, bytes32 head, RaceV3Annex ax) external returns (RaceV3) {
        return new RaceV3(_config(), 625, 100_000, pn, pool3, block.timestamp, repo, head, "c", ax);
    }

    function deployAnnex() external returns (RaceV3Annex) {
        return new RaceV3Annex(_config(), 625, 100_000, pn, pool3, block.timestamp);
    }

    function deployFees(FeesV3.Genesis memory g) external returns (FeesV3) {
        return new FeesV3(IFeesV3Validators(address(reg)), scores, g);
    }

    /// A registry with no genesis validator (nothing to pull), from this contract.
    function deployValidators(Validators.Genesis memory g) external returns (Validators) {
        return new Validators(g);
    }

    function deployScores() external returns (PanelScores) {
        return new PanelScores();
    }

    function deployPool(address[] memory coins) external returns (PoolV3) {
        return new PoolV3(coins);
    }

    /// FeesV3 keeps one CI profile, the deployment's repository's: another is refused, and a race for another
    /// repository than FeesV3's can't be built.
    function test_feesKeepsOneProfile() public {
        assertEq(fees.profileOf(TEST_REPO).timeoutSeconds, 1_200);
        vm.expectRevert(abi.encodeWithSelector(FeesV3.UnknownRepo.selector, keccak256("rad:another")));
        fees.profileOf(keccak256("rad:another"));
        vm.expectRevert(abi.encodeWithSelector(FeesV3.UnknownRepo.selector, bytes32(0)));
        fees.maxDeposit(bytes32(0), 7);
        FeesV3.Genesis memory g = _feesGenesis();
        g.repo = bytes32(0);
        vm.expectRevert(FeesV3.BadParams.selector);
        this.deployFees(g);
        RaceV3Annex ax = new RaceV3Annex(_config(), 625, 100_000, pn, pool3, block.timestamp);
        vm.expectRevert(RaceV3Base.BadParams.selector);
        this.deployRace(keccak256("rad:another"), TEST_GENESIS_HEAD, ax);
    }

    // ---------- Other repositories are refused (3.1) ----------

    /// Scenario "An issue for another repository": the call reverts, and no fee or stake is taken.
    function test_anIssueForAnotherRepository() public {
        _fund(reporter, 100 * C);
        uint256 before = usd.balanceOf(reporter);
        uint256 infraBefore = _owed(infra);
        vm.prank(reporter);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.register(keccak256("rad:another"), false);
        assertEq(usd.balanceOf(reporter), before);
        assertEq(_owed(infra), infraBefore);
    }

    /// Scenario "An issue with no repository": the call reverts, so no bounty can be won without moving the head.
    function test_anIssueWithNoRepository() public {
        _fund(reporter, 100 * C);
        uint256 before = usd.balanceOf(reporter);
        vm.prank(reporter);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.register(bytes32(0), false);
        vm.prank(reporter);
        vm.expectRevert(RaceV3Base.Refused.selector);
        rc.register(bytes32(0), true);
        assertEq(usd.balanceOf(reporter), before);
    }

    /// Every bounty is in the one repository, and every merge moves its head (#251 L9: at finality, not at the claim):
    /// a second fix on the old base is stale at its merge.
    function test_everyMergeMovesTheOneHead() public {
        uint256 b1 = _openBounty();
        uint256 b2 = _openBounty();
        uint256 s1 = _commit(solver1, b1, FIX);
        uint256 s2 = _commit(solver2, b2, keccak256("another fix"));
        _judgeCheck(s1, true);
        _judgeCheck(s2, true);
        rc.claim(b1, FIX, TEST_GENESIS_HEAD, "salt");
        rc.claim(b2, keccak256("another fix"), TEST_GENESIS_HEAD, "salt"); // both claimed: the head hasn't moved
        assertEq(_heads().head(TEST_REPO).commit, TEST_GENESIS_HEAD);
        _final(s1);
        _final(s2);
        rc.merge(b1);
        assertEq(_heads().head(TEST_REPO).commit, FIX);
        vm.expectRevert(abi.encodeWithSelector(Heads.StaleVerdict.selector, TEST_REPO, TEST_GENESIS_HEAD, FIX));
        rc.merge(b2);
        assertEq(uint256(rc.bounty(b2).state), uint256(RaceV3Base.State.Merged)); // it keeps its place until mergeBy
    }

    // ---------- Sepolia only (3.8) ----------

    /// Scenario "Deploying on Sepolia": the whole version is constructed on 11155111, with no `simulated` type, and
    /// reports chain id 11155111.
    function test_deployingOnSepolia() public {
        vm.chainId(11_155_111);
        _deployRace(3);
        assertEq(rc.chainId(), 11_155_111);
        assertEq(block.chainid, 11_155_111);
        assertFalse(reg.acceptedProofType(reg.PROOF_SIMULATED()));
    }

    /// The two local test chains construct the same bytecode (L2 option 1): tests and devnets only.
    function test_theLocalTestChainsConstruct() public {
        uint256[2] memory ids = [uint256(31_337), 7_193];
        for (uint256 i; i < ids.length; ++i) {
            vm.chainId(ids[i]);
            _deployRace(0);
            assertEq(rc.chainId(), ids[i]);
        }
    }

    /// Scenario "Deploying on mainnet or another public chain": every v3 constructor reverts.
    function test_deployingOnMainnetOrAnotherChain() public {
        uint256[5] memory ids = [uint256(1), 10, 8453, 137, 17_000];
        // dependencies built on a test chain, so each constructor's own check is what refuses
        Validators.Genesis memory vg = _genesis(false, new IValidators.Registration[](0), 0);
        address[] memory coins = new address[](1);
        coins[0] = address(usd);
        uint256 checked;
        for (uint256 i; i < ids.length; ++i) {
            vm.chainId(ids[i]);
            bytes memory wrong = abi.encodeWithSelector(LaunchChain.WrongChain.selector, ids[i]);
            vm.expectRevert(wrong);
            this.deployValidators(vg);
            vm.expectRevert(wrong);
            this.deployScores();
            vm.expectRevert(wrong);
            this.deployPool(coins);
            vm.expectRevert(wrong);
            this.deployFees(_feesGenesis());
            vm.expectRevert(wrong);
            this.deployPanels(reg, scores, vg.teeTypes, vg.windows);
            vm.expectRevert(wrong);
            this.deployAnnex();
            ++checked;
        }
        assertEq(checked, ids.length); // every chain checked, to the last constructor
        vm.chainId(31_337);
        RaceV3Annex ax = new RaceV3Annex(_config(), 625, 100_000, pn, pool3, block.timestamp);
        vm.chainId(1);
        vm.expectRevert(abi.encodeWithSelector(LaunchChain.WrongChain.selector, 1));
        this.deployRace(TEST_REPO, TEST_GENESIS_HEAD, ax);
    }

    function testFuzz_onlySepoliaAndTheLocalChains(uint64 id) public {
        vm.assume(id != 11_155_111 && id != 31_337 && id != 7_193 && id != 0);
        vm.chainId(id);
        vm.expectRevert(abi.encodeWithSelector(LaunchChain.WrongChain.selector, uint256(id)));
        this.deployScores();
    }

    // ---------- The waiting windows are set at construction (3.4) ----------

    /// The production values (design L4's table, ADR 0004) give exactly what the constants gave.
    function test_productionWindowsAreTheConstantsTheyReplace() public {
        _deployWith(WindowsLib.production());
        assertEq(pn.SEAL_WINDOW(), 2 hours);
        assertEq(pn.REVEAL_WINDOW(), 1 hours);
        assertEq(pn.ADR_WINDOW(), 14 days);
        assertEq(pn.REMOVAL_WINDOW(), 48 hours);
        assertEq(pn.K1_WINDOW_MIN(), 7 days);
        uint256[4] memory ks = [uint256(1), 3, 5, 7];
        uint256[4] memory a = [uint256(168 hours), 24 hours, 12 hours, 6 hours];
        uint256[4] memory c = [uint256(336 hours), 72 hours, 48 hours, 24 hours];
        for (uint256 i; i < 4; ++i) {
            assertEq(pn.windowOf(ks[i], 1), a[i]);
            assertEq(pn.windowOf(ks[i], 2), 2 * a[i]);
            assertEq(pn.windowOf(ks[i], 3), c[i]);
        }
        assertEq(reg.UNBONDING_DELAY(), 504 hours);
        Windows memory w = pn.windows();
        assertEq(keccak256(abi.encode(w)), keccak256(abi.encode(WindowsLib.production())));
        assertEq(reg.windowsHash(), keccak256(abi.encode(w)));
    }

    /// Scenario "A test deployment with short windows": its verdicts become final after those minutes, and its
    /// unbonding delay is the longest of them plus the published margin.
    function test_aTestDeploymentWithShortWindows() public {
        Windows memory w = WindowsLib.inMinutes();
        _deployWith(w);
        assertEq(reg.UNBONDING_DELAY(), 336 minutes + 7 days);
        uint256 id = _register();
        uint256 check = rc.issue(id).check;
        uint256 pid = _draw(check);
        assertEq(pn.panel(pid).k, 3);
        assertEq(pn.panel(pid).sealBy, vm.getBlockTimestamp() + 2 minutes);
        assertEq(pn.panel(pid).revealBy, vm.getBlockTimestamp() + 3 minutes);
        _judge(pid, _votes(3, 3));
        Submission memory s = pn.submission(check);
        assertEq(s.finalAt, vm.getBlockTimestamp() + 24 minutes); // CHALLENGE_WINDOW[3, A]
        _runAudits(check, true);
        if (vm.getBlockTimestamp() < s.finalAt) vm.warp(s.finalAt);
        pn.finalize(check);
        assertEq(uint256(pn.submission(check).status), uint256(Status.Final));
        // a validator leaving waits the derived delay, not 504 h
        address key = pn.judges(pid)[1];
        vm.prank(key);
        reg.leave(key);
        vm.warp(block.timestamp + 336 minutes + 7 days - 1);
        vm.expectRevert(Validators.TooEarly.selector);
        reg.withdraw(key);
        vm.warp(block.timestamp + 1);
        reg.withdraw(key);
    }

    /// Scenario "No change after deployment": no function changes a window (the ABIs list no setter; the
    /// noFunctionChangesAParameter tests list every function), and the windows read back the same after every action.
    function test_noChangeAfterDeployment() public {
        bytes32 before = keccak256(abi.encode(pn.windows()));
        uint256 delay = reg.UNBONDING_DELAY();
        uint256 b = _openBounty();
        uint256 s1 = _commit(solver1, b, FIX);
        _judgeCheck(s1, true);
        rc.claim(b, FIX, _head(), "salt");
        _final(s1);
        rc.merge(b);
        assertEq(keccak256(abi.encode(pn.windows())), before);
        assertEq(reg.UNBONDING_DELAY(), delay);
        string[2] memory abis = ["out/Panels.sol/Panels.json", "out/Validators.sol/Validators.json"];
        for (uint256 a; a < 2; ++a) {
            string memory json = vm.readFile(abis[a]);
            for (uint256 i;; ++i) {
                string memory key = string.concat(".abi[", vm.toString(i), "]");
                if (!vm.keyExistsJson(json, key)) break;
                if (keccak256(bytes(vm.parseJsonString(json, string.concat(key, ".type")))) != keccak256("function")) {
                    continue;
                }
                bytes memory name = bytes(vm.parseJsonString(json, string.concat(key, ".name")));
                bool setter = name.length > 3 && name[0] == "s" && name[1] == "e" && name[2] == "t" && name[3] >= "A"
                    && name[3] <= "Z";
                // a validator's own capacity (L16, #253): its own setting, which changes no window
                if (keccak256(name) == keccak256("setCapacity")) continue;
                assertFalse(setter, string(name));
            }
        }
    }

    /// Scenario "Windows out of order": k = 3's window longer than k = 1's at level A, and the constructor reverts.
    function test_windowsOutOfOrder() public {
        Windows memory w = WindowsLib.production();
        w.challenge[0][1] = w.challenge[0][0] + 1; // k = 3 above k = 1, level A
        _expectBadWindows(w);
        w = WindowsLib.production();
        w.challenge[0][3] = w.challenge[0][2] + 1; // k = 7 above k = 5
        _expectBadWindows(w);
        w = WindowsLib.production();
        w.challenge[1][1] = w.challenge[0][1] - 1; // level B's below level A's
        _expectBadWindows(w);
        w = WindowsLib.production();
        w.challenge[2][0] = w.challenge[1][0] - 1; // level C's below level B's
        _expectBadWindows(w);
        w = WindowsLib.production();
        w.k1Min = w.challenge[0][0] + 1; // k = 1's below the published minimum
        _expectBadWindows(w);
        w = WindowsLib.production();
        w.seal = 0; // every window nonzero
        _expectBadWindows(w);
        w = WindowsLib.production();
        w.k1Min = 0;
        _expectBadWindows(w);
        w = WindowsLib.production();
        w.removal = uint256(type(uint32).max) + 1;
        _expectBadWindows(w);
        w = WindowsLib.production();
        w.stuckGrace = 0; // L19's and L16's times nonzero too
        _expectBadWindows(w);
        w = WindowsLib.production();
        w.retryDelay = 0;
        _expectBadWindows(w);
        w = WindowsLib.production();
        w.capWindow = 0;
        _expectBadWindows(w);
        w = WindowsLib.production();
        w.maxRedraws = 0; // MAX_REDRAWS from 1 to 255
        _expectBadWindows(w);
        w = WindowsLib.production();
        w.maxRedraws = 256;
        _expectBadWindows(w);
        assertEq(badWindowCases, 13); // every case ran to its end
    }

    uint256 internal badWindowCases;

    /// Panels' windows must be exactly the registry's, whose unbonding delay derives from them.
    function test_panelsTakesTheRegistrysWindows() public {
        Validators.Genesis memory g = _genesis(false, new IValidators.Registration[](0), 0);
        Validators fresh = _create(g); // not bound yet
        Windows memory other = suiteWindows(); // a copy: g.windows stays the registry's
        other.seal += 1;
        PanelScores sc = new PanelScores();
        vm.expectRevert(Panels.BadParams.selector);
        this.deployPanels(fresh, sc, g.teeTypes, other);
        Panels p = this.deployPanels(fresh, sc, g.teeTypes, g.windows); // the registry's own windows construct
        assertEq(keccak256(abi.encode(p.windows())), fresh.windowsHash());
    }

    /// `new Panels` through an external call: Panels links libraries, so a test's `new Panels` is a cheatcode
    /// deployment, and an expected revert must wrap a call for the rest of the test to run.
    function deployPanels(Validators r, PanelScores sc, bytes32[] memory tees, Windows memory w)
        external
        returns (Panels)
    {
        return new Panels(IPanelsRegistry(address(r)), IPanelsFees(address(fees)), IPanelScores(address(sc)), tees, w);
    }

    /// Fuzz: any windows in order deploy, read back as given, and derive the unbonding delay.
    /// forge-config: default.fuzz.runs = 64
    function testFuzz_windowsInOrderDeploy(uint32[15] memory x) public {
        Windows memory w;
        w.seal = bound(x[0], 1, 1 days);
        w.reveal = bound(x[1], 1, 1 days);
        w.adr = bound(x[2], 1, 60 days);
        w.removal = bound(x[3], 1, 60 days);
        w.k1Min = bound(x[4], 1, 30 days);
        w.stuckGrace = bound(x[0], 1, 7 days);
        w.retryDelay = bound(x[1], 1, 7 days);
        w.maxRedraws = bound(x[2], 1, 255);
        w.capWindow = bound(x[3], 1, 1 days);
        for (uint256 l; l < 3; ++l) {
            for (uint256 i; i < 4; ++i) {
                uint256 lo = l > 0 ? w.challenge[l - 1][i] : 1;
                uint256 hi = i > 0 ? w.challenge[l][i - 1] : 60 days;
                if (i == 0 && lo < w.k1Min) lo = w.k1Min;
                if (lo > hi) return; // not an ordered set: skip
                w.challenge[l][i] = bound(x[5 + (4 * l + i) % 10], lo, hi);
            }
        }
        _deployWith(w);
        assertEq(keccak256(abi.encode(pn.windows())), keccak256(abi.encode(w)));
        assertEq(reg.UNBONDING_DELAY(), w.challenge[2][0] + 7 days);
    }

    function _expectBadWindows(Windows memory w) internal {
        Validators.Genesis memory g = _genesis(false, new IValidators.Registration[](0), 0);
        g.windows = w;
        vm.expectRevert(WindowsLib.BadWindows.selector);
        this.deployValidators(g);
        vm.expectRevert(WindowsLib.BadWindows.selector);
        this.deployPanels(reg, scores, g.teeTypes, w);
        ++badWindowCases;
    }

    /// The race's version again, with windows `w` (registry and Panels) and 3 validators besides the genesis one.
    function _deployWith(Windows memory w) internal {
        // _genesis reads suiteWindows(); the registry (and Panels, from its genesis) get `w` through this override
        _windowsOverride = w;
        _useOverride = true;
        _deployRace(3);
        _useOverride = false;
    }

    Windows internal _windowsOverride;
    bool internal _useOverride;

    function _genesis(bool simulated, IValidators.Registration[] memory gs, uint256 bond)
        internal
        override
        returns (Validators.Genesis memory g)
    {
        g = super._genesis(simulated, gs, bond);
        if (_useOverride) g.windows = _windowsOverride;
    }

    // ---------- Known findings (3.10, open problems 7.5) ----------

    /// `drawAudits` refuses repeat calls: with no auditor in a snapshot of the registry as it is, the audits wait, and
    /// every call is refused until the registry changes (a re-check that moves nobody isn't a change); then one call
    /// re-targets and the next draws.
    function test_drawAuditsRefusesRepeatCalls() public {
        _deployRace(0); // the genesis validator alone: a lone verdict, held, and nobody to audit it
        uint256 check = rc.issue(_register()).check;
        uint256 pid = _draw(check);
        assertEq(pn.panel(pid).k, 1);
        _judge(pid, _votes(1, 1));
        Submission memory s = pn.submission(check);
        assertEq(uint256(s.status), uint256(Status.Held));
        assertEq(s.auditsDue, 2);
        _rollPast(s.auditBlock);
        pn.drawAudits(check);
        s = pn.submission(check);
        assertTrue(s.auditWaits);
        assertEq(s.auditsDrawn, 0);
        uint256 block0 = s.auditBlock;
        vm.roll(block.number + 300); // even with the audit block gone
        vm.expectRevert(Panels.NothingChanged.selector);
        pn.drawAudits(check);
        reg.recheck(new address[](0));
        vm.expectRevert(Panels.NothingChanged.selector);
        pn.drawAudits(check);
        assertEq(pn.submission(check).auditBlock, block0); // nobody rolled a fresh audit block
        address auditor = _addSpread(1, 7, 3); // the registry changes
        pn.drawAudits(check); // re-targets
        s = pn.submission(check);
        assertFalse(s.auditWaits);
        assertGt(s.auditBlock, block.number);
        vm.expectRevert(); // the new audit block isn't past yet
        pn.drawAudits(check);
        _rollPast(s.auditBlock);
        pn.drawAudits(check);
        s = pn.submission(check);
        assertEq(s.auditsDrawn, 1);
        assertEq(pn.judges(pn.panelCount())[0], auditor);
        assertTrue(s.auditWaits); // the second auditor: nobody else, so it waits again
        vm.expectRevert(Panels.NothingChanged.selector);
        pn.drawAudits(check);
    }

    /// A draw whose snapshot is older than the registry re-targets at once, as before: a validator added after the
    /// count becomes an auditor without waiting for another change.
    function test_aStaleAuditSnapshotRetargetsAtOnce() public {
        _deployRace(0);
        uint256 check = rc.issue(_register()).check;
        uint256 pid = _draw(check);
        _judge(pid, _votes(1, 1));
        address auditor = _addSpread(1, 7, 3); // after the count's snapshot
        Submission memory s = pn.submission(check);
        _rollPast(s.auditBlock);
        pn.drawAudits(check);
        s = pn.submission(check);
        assertFalse(s.auditWaits);
        assertEq(s.auditsDrawn, 0);
        _rollPast(s.auditBlock);
        pn.drawAudits(check);
        assertEq(pn.submission(check).auditsDrawn, 1);
        assertEq(pn.judges(pn.panelCount())[0], auditor);
    }
}

/// proof-of-fix#251, contract batch 1 (tasks 3.7 and 3.8; specs/validator-admission's delta, specs/deployment-binding):
/// a bond below the floor is a visible state, and a TEE-only deployment refuses zkTLS at genesis and by ADR.
contract BelowFloorV3Test is ValidatorsSetup {
    address internal genesisKey;
    uint256 internal adrId;

    event WentBelowFloor(address indexed key, uint256 bond);
    event BackAboveFloor(address indexed key, uint256 bond);

    function setUp() public {
        _deployCoinAndPool();
        genesisKey = _newKey("genesis");
        _deploy(genesisKey);
    }

    // ---------- A validator below the bond floor is visibly inactive (3.7) ----------

    /// Scenario "A silence slash on a floor bond": in the same transaction an event names the validator and its bond
    /// ($95), the registry reports it below the floor, and the active count falls by one. It isn't drawn.
    function test_aSilenceSlashOnAFloorBond() public {
        address key = _active(100e6);
        uint256 active = reg.activeCount();
        uint256 eligible = reg.eligibleCount(10e6);
        vm.expectEmit(address(reg));
        emit WentBelowFloor(key, 95e6);
        panels.recordCounted(key, false, false);
        assertEq(_bond(key), 95e6);
        assertTrue(_state(key) == IValidators.State.BelowFloor);
        assertFalse(reg.isActive(key));
        assertEq(reg.activeCount(), active - 1);
        assertFalse(reg.isDrawable(key));
        assertEq(reg.eligibleCount(10e6), eligible - 1);
        assertFalse(reg.canShadow(key)); // not a candidate either
    }

    /// Scenario "Topping up": an event says it is active again, it counts as active, and it can be drawn without
    /// qualifying again. A top-up that stays below the floor changes nothing.
    function test_toppingUp() public {
        address key = _active(100e6);
        panels.recordCounted(key, false, false);
        uint256 active = reg.activeCount();
        _topUp(key, 4e6); // $99: still below
        assertTrue(_state(key) == IValidators.State.BelowFloor);
        assertEq(reg.activeCount(), active);
        usd.mint(address(this), 1e6);
        usd.approve(address(reg), 1e6);
        vm.expectEmit(address(reg));
        emit BackAboveFloor(key, 100e6);
        reg.topUp(key, 1e6);
        assertTrue(_state(key) == IValidators.State.Active);
        assertTrue(reg.isActive(key));
        assertEq(reg.activeCount(), active + 1);
        assertTrue(reg.isDrawable(key));
        assertEq(reg.progress(key).scored, 0); // no qualification ran
    }

    /// Scenario "Leaving instead of topping up": it enters the leaving state, stays slashable until the delay ends and
    /// its verdicts are final, and then its remaining bond is withdrawable.
    function test_leavingInsteadOfToppingUp() public {
        address key = _active(100e6);
        panels.verdictOpened(key);
        panels.recordCounted(key, false, false);
        uint256 active = reg.activeCount();
        address op = reg.validator(key).operator;
        vm.prank(op);
        reg.leave(key);
        assertTrue(_state(key) == IValidators.State.Leaving);
        assertEq(reg.activeCount(), active); // it wasn't counted
        panels.recordCounted(key, true, false); // still slashable
        assertEq(_bond(key), 90e6);
        vm.warp(block.timestamp + reg.UNBONDING_DELAY());
        vm.expectRevert(Validators.Locked.selector);
        reg.withdraw(key);
        panels.verdictFinal(key);
        uint256 before = usd.balanceOf(op);
        reg.withdraw(key);
        assertEq(usd.balanceOf(op), before + 90e6);
        assertTrue(_state(key) == IValidators.State.Exited);
    }

    /// Its misses still count toward the reveal-rate floor: suspended from BelowFloor, it becomes a candidate, and the
    /// active count isn't taken down twice.
    function test_suspendedBelowTheFloor() public {
        address key = _active(100e6);
        uint256 active = reg.activeCount();
        for (uint256 i; i < 6; ++i) {
            panels.recordCounted(key, false, false);
        }
        assertTrue(_state(key) == IValidators.State.Candidate);
        assertEq(reg.activeCount(), active - 1);
        assertEq(_bond(key), 70e6);
        // it qualifies again below the floor: below the floor at once, never counted
        _qualify(key);
        assertTrue(_state(key) == IValidators.State.BelowFloor);
        assertEq(reg.activeCount(), active - 1);
    }

    /// A false verdict takes the whole bond: below the floor at 0, and back with a top-up of the floor.
    function test_aWholeBondSlash() public {
        address key = _active(500e6);
        panels.slashFault(key, IValidators.Fault.FalseVerdict, address(0));
        assertTrue(_state(key) == IValidators.State.BelowFloor);
        _topUp(key, 100e6);
        assertTrue(_state(key) == IValidators.State.Active);
    }

    function _topUp(address key, uint256 amount) internal {
        usd.mint(address(this), amount);
        usd.approve(address(reg), amount);
        reg.topUp(key, amount);
    }

    // ---------- Only TEE proof types in this deployment (3.8) ----------

    function _teeOnly() internal returns (Validators v, PanelsHarness h) {
        Validators.Genesis memory g = _genesis(false, new IValidators.Registration[](0), 0);
        g.teeOnly = true;
        v = _create(g);
        h = new PanelsHarness(v);
        assertTrue(v.teeOnly());
    }

    /// Scenario "A zkTLS registration": on a TEE-only deployment it reverts.
    function test_aZkTlsRegistration() public {
        (reg, panels) = _teeOnly();
        address key = _nextKey();
        IValidators.Registration memory r = _reg(key, makeAddr("zk op"), keccak256("a home PC"), FAMILY_B);
        r.proofType = keccak256("zktls");
        r.teeType = bytes32(0);
        r.level = 0;
        r.attestation = bytes32(0);
        bytes memory sig = _sign(reg, key, r);
        usd.mint(address(this), 100e6);
        usd.approve(address(reg), 100e6);
        vm.expectRevert(Validators.ProofTypeNotAccepted.selector);
        reg.register(r, 100e6, sig);
    }

    /// Scenario "An ADR that adds zkTLS": applying it reverts, and the accepted proof types are unchanged. Another
    /// ADR still applies.
    function test_anAdrThatAddsZkTls() public {
        (reg, panels) = _teeOnly();
        IValidators.Change[] memory cs = new IValidators.Change[](2);
        cs[0] = IValidators.Change(IValidators.Op.AddProofType, reg.PROOF_ZKTLS(), 0);
        cs[1] = IValidators.Change(IValidators.Op.AddNotary, keccak256("notary"), 0);
        bytes32 text = keccak256("switch zkTLS on");
        panels.adrPassed(1, false, reg.adrCommitment(text, cs));
        vm.expectRevert(Validators.TeeOnly.selector);
        reg.applyAdr(1, text, cs);
        assertFalse(reg.acceptedProofType(reg.PROOF_ZKTLS()));
        assertTrue(reg.acceptedProofType(reg.PROOF_TEE()));
        IValidators.Change[] memory img = new IValidators.Change[](1);
        img[0] = IValidators.Change(IValidators.Op.AddImage, keccak256("next image"), 0);
        panels.adrPassed(2, false, reg.adrCommitment(text, img));
        reg.applyAdr(2, text, img);
        assertTrue(reg.allowedImage(keccak256("next image")));
    }

    /// Without the flag (a fork, or a test deployment) the same ADR lists zkTLS: the flag is what refuses it.
    function test_withoutTheFlagZkTlsCanBeAdded() public {
        assertFalse(reg.teeOnly());
        IValidators.Change[] memory cs = new IValidators.Change[](2);
        cs[0] = IValidators.Change(IValidators.Op.AddProofType, reg.PROOF_ZKTLS(), 0);
        cs[1] = IValidators.Change(IValidators.Op.AddNotary, keccak256("notary"), 0);
        bytes32 text = keccak256("switch zkTLS on");
        panels.adrPassed(1, false, reg.adrCommitment(text, cs));
        reg.applyAdr(1, text, cs);
        assertTrue(reg.acceptedProofType(reg.PROOF_ZKTLS()));
    }

    /// On Sepolia a TEE-only deployment constructs, and `simulated` stays refused, at genesis and by ADR.
    function test_onSepoliaSimulatedStaysRefused() public {
        vm.chainId(11_155_111);
        (reg, panels) = _teeOnly();
        assertFalse(reg.acceptedProofType(reg.PROOF_SIMULATED()));
        IValidators.Change[] memory cs = new IValidators.Change[](1);
        cs[0] = IValidators.Change(IValidators.Op.AddProofType, reg.PROOF_SIMULATED(), 0);
        bytes32 text = keccak256("simulated on Sepolia");
        panels.adrPassed(1, false, reg.adrCommitment(text, cs));
        vm.expectRevert(Validators.NoVerifier.selector);
        reg.applyAdr(1, text, cs);
        Validators.Genesis memory g = _genesis(true, new IValidators.Registration[](0), 0);
        vm.expectRevert(Validators.BadParams.selector);
        _create(g);
    }
}
