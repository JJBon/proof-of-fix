// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {Oracles} from "../test/helpers/Oracles.sol";
import {Race} from "../src/Race.sol";
import {Quoter} from "../src/Quoter.sol";
import {MockCoin} from "../test/mocks/MockCoin.sol";
import {console} from "forge-std/console.sol";

/// Task 3.2's CLI (design D8): prints what a solver pays to try a bounty and could earn. Run with
/// `scripts/contracts.sh quote`, in the pinned container with no network:
///   scripts/contracts.sh quote                     a demo on a throwaway chain: a bounty quoted as its price rises,
///                                                  after the first attempt locks it, and after a later pledge
///   scripts/contracts.sh quote --sig 'quote(address,uint256,address)' RACE BOUNTY COIN --rpc-url URL
///                                                  one bounty of a Race deployed on a local chain
/// Nothing is broadcast: the script only reads (the demo deploys in forge's own simulation).
contract QuoteScript is Oracles {
    uint256 constant C = 1e6;

    function run() external {
        MockCoin usd = new MockCoin("Mock USD", "mUSD", 6);
        address[] memory feeCoins = new address[](1);
        feeCoins[0] = address(usd);
        _makeOracles(3, 2);
        Race race = _newRace(_config(), feeCoins, 1_000, 100_000);
        Quoter quoter = new Quoter();
        address reporter = makeAddr("reporter");
        address funder = makeAddr("funder");
        address solver = makeAddr("solver");
        for (uint256 i; i < 3; ++i) {
            address a = [reporter, funder, solver][i];
            usd.mint(a, 1_000 * C);
            vm.prank(a);
            usd.approve(address(race), type(uint256).max);
        }
        vm.prank(reporter);
        uint256 b = _accept(race, race.register(address(usd)));
        vm.prank(funder);
        race.pledge(b, address(usd), 100 * C);
        _print("Day 0: opened, 100 mUSD pledged", quoter.quote(race, b, address(usd)));
        vm.warp(race.start() + 3 days);
        _print("Day 3: the share has risen", quoter.quote(race, b, address(usd)));
        vm.prank(solver);
        race.attempt(b, address(usd));
        _print("Day 3: the first attempt locked the share", quoter.quote(race, b, address(usd)));
        vm.warp(race.start() + 5 days);
        vm.prank(funder);
        race.pledge(b, address(usd), 50 * C);
        _print("Day 5: 50 mUSD more pledged", quoter.quote(race, b, address(usd)));
    }

    /// One bounty of a deployed Race, read over --rpc-url.
    function quote(address race, uint256 b, address coin) external {
        Quoter quoter = new Quoter();
        _print(string.concat("Bounty ", vm.toString(b)), quoter.quote(Race(race), b, coin));
    }

    function _config() internal returns (Race.Config memory c) {
        c.infrastructure = makeAddr("infra");
        c.insurance = makeAddr("insurance");
        c.registrationFee = 2e6;
        c.issueStake = 5e6;
        c.attemptFee = 0.5e6;
        c.evaluationFee = 2e6;
        c.checkDeposit = 6.6e6;
        c.appealFee = 2e6;
        c.appealDeposit = 5e6;
        c.startPriceBps = 5_000;
        c.riseBpsPerDay = 1_000;
        c.finderFeeBps = 1_765;
        c.idleDays = 28;
        c.resultDays = 7;
        c.mergeDays = 14;
        c.windowDays = 7;
        c.releaseEveryDays = 7;
        c.instalments = 4;
    }

    string[7] STATES = ["none", "open", "won (waiting for its merge)", "merged", "paid", "refunded", "unsolved"];

    function _print(string memory title, Quoter.Quote memory q) internal view {
        console.log("");
        console.log(title);
        console.log(string.concat("  state            ", STATES[uint256(q.state)], ", day ", vm.toString(q.day)));
        console.log(string.concat("  share of the cap ", _pct(q.offerBps), q.locked ? " (locked)" : " (rising)"));
        console.log(string.concat("  cap              ", _amount(q.cap)));
        console.log(string.concat("  price            ", _amount(q.price)));
        console.log(string.concat(
            "  paid in          ", vm.toString(q.instalments), " instalments of ", _amount(q.instalment), ", the last ",
            _amount(q.lastInstalment)
        ));
        console.log(string.concat("  finder's fee     ", _amount(q.finderFee), " (to the reporter)"));
        console.log(string.concat("  attempts         ", vm.toString(q.attempting), " in progress"));
        if (q.sunsetDay != 0) {
            console.log(string.concat("  sunsets on day   ", vm.toString(q.sunsetDay), " without a checked submission"));
        }
        console.log(string.concat(
            "  to try it        attempt ", _amount(q.attemptFee), ", check deposit ", _amount(q.checkDeposit),
            " (checks paid from it), appeal ", _amount(q.appealFee)
        ));
    }

    /// Micro-units as a decimal with six places.
    function _amount(uint256 micro) internal view returns (string memory) {
        uint256 frac = micro % C;
        string memory f = vm.toString(frac + C); // 1xxxxxx: keeps the leading zeros
        return string.concat(vm.toString(micro / C), ".", _slice(f, 1));
    }

    function _pct(uint256 bps) internal view returns (string memory) {
        return string.concat(vm.toString(bps / 100), ".", _slice(vm.toString(bps % 100 + 100), 1), " %");
    }

    function _slice(string memory s, uint256 from) internal pure returns (string memory) {
        bytes memory b = bytes(s);
        bytes memory out = new bytes(b.length - from);
        for (uint256 i; i < out.length; ++i) out[i] = b[i + from];
        return string(out);
    }
}
