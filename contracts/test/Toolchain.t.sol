// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {Test} from "forge-std/Test.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {MessageHashUtils} from "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";
import {MockCoin} from "./mocks/MockCoin.sol";

/// Task 1.1: the pinned toolchain and the vendored libraries work, on a local chain with keys made per run.
contract ToolchainTest is Test {
    using SafeERC20 for IERC20;

    MockCoin internal coin;

    function setUp() public {
        coin = new MockCoin("Mock USD", "mUSD", 6);
    }

    function test_localChain() public view {
        assertEq(block.chainid, 31337);
    }

    function test_safeTransferMovesTheAmount() public {
        address to = makeAddr("to");
        coin.mint(address(this), 1_000_000);
        IERC20(address(coin)).safeTransfer(to, 250_000);
        assertEq(coin.balanceOf(to), 250_000);
        assertEq(coin.balanceOf(address(this)), 750_000);
    }

    /// The signer's key is fuzzed, so no fixed key is relied on (spec: test keys generated for each run).
    function testFuzz_recoverSigner(uint256 key, bytes32 result) public pure {
        key = bound(key, 1, SECP256K1_ORDER - 1);
        bytes32 digest = MessageHashUtils.toEthSignedMessageHash(result);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(key, digest);
        assertEq(ECDSA.recover(digest, abi.encodePacked(r, s, v)), vm.addr(key));
    }
}
