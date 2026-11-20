// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Test} from "forge-std/Test.sol";
import {TestCoin} from "../../src/v3/TestCoin.sol";
import {CoinFaucet} from "../../src/v3/CoinFaucet.sol";
import {LaunchChain} from "../../src/v3/LaunchChain.sol";

/// proof-of-fix#251, task 3.17 (design L17 as amended on 2026-11-20; specs/deployment-binding, "The fee coin is a test
/// coin with no key" and "The faucet's rule is fixed"): the launch's own test coin and its keyless faucet. Each
/// scenario of the spec is tested under its name.
contract TestCoinV3Test is Test {
    address constant MAKER = address(0xB0);
    address constant OWNER = address(0x0E);
    address constant ALICE = address(0xA11CE);
    address constant BOB = address(0xB0B);

    uint256 constant T0 = 1_800_000_000;

    CoinFaucet faucet;
    TestCoin coin;

    function setUp() public {
        vm.warp(T0);
        faucet = _deploy();
        coin = faucet.coin();
    }

    /// The launch's genesis mint: the genesis validator's $250 bond to the registry maker, 4,750 to the recipient.
    function _deploy() internal returns (CoinFaucet) {
        (address[] memory to, uint256[] memory amounts) = _genesis();
        return new CoinFaucet(to, amounts);
    }

    function _genesis() internal pure returns (address[] memory to, uint256[] memory amounts) {
        to = new address[](2);
        amounts = new uint256[](2);
        (to[0], amounts[0]) = (MAKER, 250e6);
        (to[1], amounts[1]) = (OWNER, 4_750e6);
    }

    function deployFaucet(address[] memory to, uint256[] memory amounts) external returns (CoinFaucet) {
        return new CoinFaucet(to, amounts);
    }

    function deployCoin(address[] memory to, uint256[] memory amounts) external returns (TestCoin) {
        return new TestCoin(to, amounts);
    }

    // ---------- The fee coin is a test coin with no key ----------

    /// A test coin by its name and symbol, never "USD" or "USDC", with 6 decimals (the design's dollar arithmetic).
    function test_aTestCoinWithSixDecimals() public view {
        assertEq(coin.decimals(), 6);
        assertEq(coin.name(), "proof-of-fix test coin");
        assertEq(coin.symbol(), "POFTEST");
        assertEq(coin.faucet(), address(faucet));
    }

    /// Scenario "The genesis mint": the bond and the rest where the deploy named them, the supply 5,000 coins.
    function test_theGenesisMint() public view {
        assertEq(coin.balanceOf(MAKER), 250e6);
        assertEq(coin.balanceOf(OWNER), 4_750e6);
        assertEq(coin.totalSupply(), 5_000e6);
        assertEq(coin.genesisMint(), 5_000e6);
        assertEq(coin.balanceOf(address(faucet)), 0);
    }

    /// A genesis whose lists differ in length, or that mints to the zero address, deploys nothing.
    function test_aMalformedGenesisIsRefused() public {
        address[] memory to = new address[](1);
        uint256[] memory amounts = new uint256[](2);
        to[0] = OWNER;
        vm.expectRevert(TestCoin.BadGenesis.selector);
        this.deployFaucet(to, amounts);
        amounts = new uint256[](1);
        to[0] = address(0);
        vm.expectRevert(); // ERC20InvalidReceiver(0)
        this.deployFaucet(to, amounts);
    }

    /// No genesis at all: the faucet alone mints.
    function test_anEmptyGenesis() public {
        CoinFaucet f = this.deployFaucet(new address[](0), new uint256[](0));
        assertEq(f.coin().totalSupply(), 0);
        vm.prank(ALICE);
        f.claim();
        assertEq(f.coin().totalSupply(), 20e6);
    }

    /// Scenario "Anyone else mints": the deployer, the genesis recipient, a claimant and the token itself are refused,
    /// and the supply is unchanged.
    function test_anyoneElseMints() public {
        address[5] memory who = [address(this), OWNER, MAKER, ALICE, address(coin)];
        for (uint256 i; i < who.length; ++i) {
            vm.prank(who[i]);
            vm.expectRevert(abi.encodeWithSelector(TestCoin.NotFaucet.selector, who[i]));
            coin.mint(who[i], 1e6);
        }
        assertEq(coin.totalSupply(), 5_000e6);
    }

    function testFuzz_onlyTheFaucetMints(address caller, uint256 amount) public {
        vm.assume(caller != address(faucet));
        vm.prank(caller);
        vm.expectRevert(abi.encodeWithSelector(TestCoin.NotFaucet.selector, caller));
        coin.mint(caller, amount);
    }

    /// A token deployed on its own makes its deployer its "faucet": it isn't the deployment's coin, whose faucet is
    /// the CoinFaucet that created it (the record names both; anyone checks `coin.faucet() == faucet`).
    function test_theMinterIsTheCreator() public {
        TestCoin other = this.deployCoin(new address[](0), new uint256[](0));
        assertEq(other.faucet(), address(this));
        assertEq(address(faucet.coin().faucet()), address(faucet));
    }

    /// Keyless: the only state-changing functions are ERC-20's own, the faucet's mint, and the claim.
    function test_noPrivilegedCall() public view {
        _onlyWriters("out/TestCoin.sol/TestCoin.json", _coinWriters(), 4);
        string[] memory f = new string[](1);
        f[0] = "claim";
        _onlyWriters("out/CoinFaucet.sol/CoinFaucet.json", f, 1);
    }

    function _coinWriters() internal pure returns (string[] memory w) {
        w = new string[](4);
        (w[0], w[1], w[2], w[3]) = ("transfer", "transferFrom", "approve", "mint");
    }

    function _onlyWriters(string memory path, string[] memory writers, uint256 count) internal view {
        string memory json = vm.readFile(path);
        uint256 n;
        for (uint256 i;; ++i) {
            string memory key = string.concat(".abi[", vm.toString(i), "]");
            if (!vm.keyExistsJson(json, key)) break;
            if (keccak256(bytes(vm.parseJsonString(json, string.concat(key, ".type")))) != keccak256("function")) {
                continue;
            }
            bytes32 mut = keccak256(bytes(vm.parseJsonString(json, string.concat(key, ".stateMutability"))));
            if (mut == keccak256("view") || mut == keccak256("pure")) continue;
            string memory name = vm.parseJsonString(json, string.concat(key, ".name"));
            bool ok;
            for (uint256 j; j < writers.length && !ok; ++j) {
                ok = keccak256(bytes(name)) == keccak256(bytes(writers[j]));
            }
            assertTrue(ok, string.concat("unexpected state-changing function: ", name));
            ++n;
        }
        assertEq(n, count);
    }

    // ---------- The faucet's rule is fixed ----------

    function test_theRuleIsConstant() public view {
        assertEq(faucet.CLAIM_AMOUNT(), 20e6);
        assertEq(faucet.CLAIM_INTERVAL(), 2 hours);
    }

    /// Scenario "A first claim": 20 coins, and the next claim readable, 2 hours later.
    function test_aFirstClaim() public {
        assertEq(faucet.nextClaim(ALICE), 0);
        vm.expectEmit(address(faucet));
        emit CoinFaucet.Claimed(ALICE, 20e6, block.timestamp + 2 hours);
        vm.prank(ALICE);
        uint256 next = faucet.claim();
        assertEq(next, block.timestamp + 2 hours);
        assertEq(faucet.nextClaim(ALICE), next);
        assertEq(coin.balanceOf(ALICE), 20e6);
        assertEq(coin.totalSupply(), 5_020e6);
    }

    /// Scenario "A claim too soon": refused with the time of the next claim, nothing minted, up to the last second.
    function test_aClaimTooSoon() public {
        vm.prank(ALICE);
        uint256 next = faucet.claim();
        vm.prank(ALICE);
        vm.expectRevert(abi.encodeWithSelector(CoinFaucet.TooSoon.selector, next));
        faucet.claim();
        vm.warp(next - 1);
        vm.prank(ALICE);
        vm.expectRevert(abi.encodeWithSelector(CoinFaucet.TooSoon.selector, next));
        faucet.claim();
        assertEq(coin.balanceOf(ALICE), 20e6);
        assertEq(coin.totalSupply(), 5_020e6);
        assertEq(faucet.nextClaim(ALICE), next); // a refused claim doesn't push the wait further
    }

    /// Repeat claims: one every 2 hours, from the previous claim; a late claim waits 2 hours from itself.
    function test_repeatClaims() public {
        uint256 t0 = T0; // a constant: under via-IR a local read from block.timestamp can be re-read after a warp
        for (uint256 i; i < 12; ++i) {
            vm.warp(t0 + i * 2 hours);
            vm.prank(ALICE);
            faucet.claim();
        }
        assertEq(coin.balanceOf(ALICE), 240e6); // 12 claims a day, faucet-spam-v1's 240 a day per address
        vm.warp(t0 + 30 hours); // late: 8 hours after its 12th claim's wait ended
        vm.prank(ALICE);
        uint256 next = faucet.claim();
        assertEq(next, t0 + 32 hours);
        assertEq(coin.balanceOf(ALICE), 260e6);
    }

    /// The limit is per address: another address claims at once (addresses are free: trust point 6).
    function test_eachAddressHasItsOwnLimit() public {
        vm.prank(ALICE);
        faucet.claim();
        vm.prank(BOB);
        faucet.claim();
        assertEq(coin.balanceOf(BOB), 20e6);
        assertEq(coin.totalSupply(), 5_040e6);
    }

    /// The faucet mints only to the caller: a claim moves no one else's coins and names no recipient.
    function testFuzz_claimsOnlyForItself(address who, uint32 wait) public {
        vm.assume(who != address(0) && who != MAKER && who != OWNER);
        vm.prank(who);
        uint256 next = faucet.claim();
        vm.warp(block.timestamp + wait);
        vm.prank(who);
        if (wait < 2 hours) {
            vm.expectRevert(abi.encodeWithSelector(CoinFaucet.TooSoon.selector, next));
            faucet.claim();
            assertEq(coin.balanceOf(who), 20e6);
        } else {
            faucet.claim();
            assertEq(coin.balanceOf(who), 40e6);
        }
        assertEq(coin.balanceOf(OWNER), 4_750e6);
    }

    // ---------- Sepolia only ----------

    /// Scenario "Deploying the coin on mainnet": the faucet and the token both refuse chain 1 (and other public
    /// chains); Sepolia and the two local test ids construct.
    function test_deployingTheCoinOnMainnet() public {
        (address[] memory to, uint256[] memory amounts) = _genesis();
        uint256[5] memory ids = [uint256(1), 10, 8453, 137, 17_000];
        for (uint256 i; i < ids.length; ++i) {
            vm.chainId(ids[i]);
            bytes memory wrong = abi.encodeWithSelector(LaunchChain.WrongChain.selector, ids[i]);
            vm.expectRevert(wrong);
            this.deployFaucet(to, amounts);
            vm.expectRevert(wrong);
            this.deployCoin(to, amounts);
        }
        uint256[3] memory ok = [uint256(11_155_111), 31_337, 7_193];
        for (uint256 i; i < ok.length; ++i) {
            vm.chainId(ok[i]);
            CoinFaucet f = this.deployFaucet(to, amounts);
            assertEq(f.coin().totalSupply(), 5_000e6);
        }
    }

    function testFuzz_onlySepoliaAndTheLocalChains(uint64 id) public {
        vm.assume(id != 11_155_111 && id != 31_337 && id != 7_193 && id != 0);
        vm.chainId(id);
        vm.expectRevert(abi.encodeWithSelector(LaunchChain.WrongChain.selector, uint256(id)));
        this.deployFaucet(new address[](0), new uint256[](0));
    }

    /// EIP-170 and EIP-3860 for both, with the margins printed for reports/contract-v3.md.
    function test_sizesFit() public view {
        string[2] memory names = ["TestCoin", "CoinFaucet"];
        for (uint256 i; i < names.length; ++i) {
            string memory json = vm.readFile(string.concat("out/", names[i], ".sol/", names[i], ".json"));
            uint256 runtime = (bytes(vm.parseJsonString(json, ".deployedBytecode.object")).length - 2) / 2;
            uint256 init = (bytes(vm.parseJsonString(json, ".bytecode.object")).length - 2) / 2;
            assertLt(runtime, 24_577, names[i]);
            assertLt(init, 49_153, names[i]);
        }
    }
}
