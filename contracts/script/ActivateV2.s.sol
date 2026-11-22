// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Script} from "forge-std/Script.sol";
import {console} from "forge-std/console.sol";
import {Verdicts} from "../src/v2/Verdicts.sol";

/// A seat's published key takes the seat, once its delay has passed (proof-of-fix#85 task 5.4): the same call as
/// scripts/devnet.sh activate-v2 sends with cast, for its remote mode (#150), where the sender's key stays off every
/// command line. It arrives on stdin, then in this script's environment:
///   ACTIVATE_SENDER_PK   the sender's key
///   ACTIVATE_RECORD      the v2 deployment record (under ./deployments)
///   ACTIVATE_SEAT        the seat's index
contract ActivateV2Script is Script {
    function run() external {
        string memory record = vm.readFile(string.concat("./", vm.envString("ACTIVATE_RECORD")));
        Verdicts verdicts = Verdicts(vm.parseJsonAddress(record, ".verdicts"));
        uint256 seat = vm.envUint("ACTIVATE_SEAT");
        vm.startBroadcast(vm.envUint("ACTIVATE_SENDER_PK"));
        verdicts.activate(seat);
        vm.stopBroadcast();
        console.log(string.concat("seat ", vm.toString(seat), ": activated"));
    }
}
