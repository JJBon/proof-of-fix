// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/// Creates the registry from an address known before it exists: the genesis validator signs its registration for the
/// registry's address, and the registry pulls the genesis bond from its creator. A contract's first creation is at
/// its nonce 1, whatever the deployer's own nonce is. Used by NodeV3Local and DeploySepolia (#251, task 3.9), in its
/// own file so its bytecode, which the Sepolia deployment's release-candidate record names, depends on nothing else.
/// It holds nothing once the registry exists and has no role after.
contract RegistryMaker {
    function make(IERC20 coin, uint256 bond, bytes calldata initcode) external returns (address made) {
        coin.approve(next(), bond);
        bytes memory code = initcode;
        assembly {
            made := create(0, add(code, 0x20), mload(code))
        }
        require(made != address(0), "the registry's constructor reverted");
    }

    function next() public view returns (address) {
        // keccak256(rlp([this, 1]))
        return address(uint160(uint256(keccak256(abi.encodePacked(bytes1(0xd6), bytes1(0x94), address(this), bytes1(0x01))))));
    }
}
