// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {Oracles} from "./helpers/Oracles.sol";
import {Race} from "../src/Race.sol";
import {Token} from "../src/Token.sol";
import {Quoter} from "../src/Quoter.sol";
import {MockCoin} from "./mocks/MockCoin.sol";

/// Task 2.6 (design D7): a simulated race run replays on the contract to identical balances. The files in test/data
/// are `python3 -m pof.sim market run --contract --export-events` (pof/sim/export.py): every call of the run that
/// moves money, with what each account it touched holds after it, as pof's ledger has it. An account's net is its
/// wallet plus its credits less what it was minted; a bounty's pot is its bounty account plus its escrow; the
/// deposits are the issue stakes and the submissions' accounts. The criterion is exact equality, checked after every
/// event; a mismatch names the event, its kind, day and pof's ledger seq. This test contract relays the results,
/// signed by the oracle quorum's test keys (D3); relaying moves no money. After each event its bounty's quote
/// (task 3.2) must equal pof's `Market.quote`.
contract ReplayTest is Oracles {
    uint256 constant MINT = 1e15; // every account's wallet: no simulated payment is refused for lack of funds

    /// One event, read from the file's columns (pof/sim/export.py EVENT_FIELDS). Nothing is decoded as a struct:
    /// vm.parseJson doesn't keep an object's fields in a dependable order, so every table is one array per field.
    struct Ev {
        uint256 amount;
        uint256 bounty;
        uint256 day;
        uint256 deposits;
        uint256 expFrom;
        uint256 expTo;
        uint256 feeFrom;
        uint256 feeTo;
        uint256 fix;
        uint256 funFrom;
        uint256 funTo;
        uint256 heldFrom;
        uint256 heldTo;
        uint256 issue;
        uint256 kind;
        uint256 outcome;
        uint256 price;
        uint256 prev;
        uint256 seq;
        uint256 sub;
        uint256 weight; // accept: the registered weight; merged: the merge estimate (#58 D3)
        uint256 who;
    }

    // pof/sim/export.py KINDS
    uint256 constant REGISTER = 1;
    uint256 constant ACCEPT = 2;
    uint256 constant WITHDRAW_ISSUE = 3;
    uint256 constant PLEDGE = 4;
    uint256 constant ATTEMPT = 5;
    uint256 constant STOP = 6;
    uint256 constant SUBMIT = 7;
    uint256 constant APPEAL = 8;
    uint256 constant TOO_LATE = 9;
    uint256 constant DUPLICATE = 10;
    uint256 constant APPEAL_DUPLICATE = 11;
    uint256 constant MERGED = 12;
    uint256 constant INSTALMENT = 13;
    uint256 constant SETTLE = 14;
    uint256 constant SUNSET = 15;

    Race race;
    Quoter quoter;
    MockCoin usd;
    string json;
    uint256 qi; // the next row of the quotes table
    mapping(bytes32 column => uint256[]) cols; // "<table>.<field>" -> its values

    function test_replaySeed1() public {
        _replay("race-1.json");
    }

    function test_replaySeed2() public {
        _replay("race-2.json");
    }

    function test_replaySeed3() public {
        _replay("race-3.json");
    }

    function test_replaySeed4() public {
        _replay("race-4.json");
    }

    function test_replaySeed9() public {
        _replay("race-9.json");
    }

    function test_replaySeed8() public {
        _replay("race-8.json");
    }

    function test_replaySeed10() public {
        _replay("race-10.json");
    }

    function test_replaySeed15() public {
        _replay("race-15.json");
    }

    function test_replaySeed60() public {
        _replay("race-60.json");
    }

    // Task 3.4: with the emission on (pof's TOKENS on the contract's shape), the token's balances too. 15 has a
    // registration inflated beyond the tolerance; all have bounties of 0 coin that closed paid.

    function test_replayTokensSeed1() public {
        _replay("tokens-1.json");
    }

    function test_replayTokensSeed5() public {
        _replay("tokens-5.json");
    }

    function test_replayTokensSeed7() public {
        _replay("tokens-7.json");
    }

    function test_replayTokensSeed15() public {
        _replay("tokens-15.json");
    }

    // ---------- setup ----------

    /// Race.t.sol's configuration: pof's defaults for the race, with no market fee (D9). The export must agree.
    function _config(uint256 infra, uint256 insurance) internal pure returns (Race.Config memory c) {
        c.infrastructure = _addr(infra);
        c.insurance = _addr(insurance);
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

    uint256 constant c_releaseEveryDays = 7;

    function _param(string memory key) internal view returns (uint256) {
        return vm.parseJsonUint(json, string.concat(".params.", key));
    }

    /// The simulation ran with the contract's configuration (catches drift between pof's params and the contract's).
    function _checkParams(Race.Config memory c) internal view {
        assertEq(_param("registrationFee"), c.registrationFee, "registrationFee");
        assertEq(_param("issueStake"), c.issueStake, "issueStake");
        assertEq(_param("attemptFee"), c.attemptFee, "attemptFee");
        assertEq(_param("evaluationFee"), c.evaluationFee, "evaluationFee");
        assertEq(_param("checkDeposit"), c.checkDeposit, "checkDeposit");
        assertEq(_param("appealFee"), c.appealFee, "appealFee");
        assertEq(_param("startPriceBps"), c.startPriceBps, "startPriceBps");
        assertEq(_param("riseBpsPerDay"), c.riseBpsPerDay, "riseBpsPerDay");
        assertEq(_param("finderFeeBps"), c.finderFeeBps, "finderFeeBps");
        assertEq(_param("idleDays"), c.idleDays, "idleDays");
        assertEq(_param("windowDays"), c.windowDays, "windowDays");
        assertEq(_param("releaseEveryDays"), c.releaseEveryDays, "releaseEveryDays");
        assertEq(_param("instalments"), c.instalments, "instalments");
        assertEq(_param("marketFeeBps"), 0, "marketFeeBps");
    }

    function _addr(uint256 i) internal pure returns (address) {
        return address(uint160(0x1000000 + i)); // name order is address order (the refund's remainder)
    }

    function _replay(string memory file) internal {
        json = vm.readFile(string.concat(vm.projectRoot(), "/test/data/", file));
        Race.Config memory c = _config(vm.parseJsonUint(json, ".infra"), vm.parseJsonUint(json, ".insurance"));
        _checkParams(c);
        usd = new MockCoin("Mock USD", "mUSD", 6);
        address[] memory feeCoins = new address[](1);
        feeCoins[0] = address(usd);
        _makeOracles(3, 2);
        _tokenParams();
        race = _newRace(c, feeCoins, 1e12, 1e15);
        quoter = new Quoter();
        uint256 n = vm.parseJsonUint(json, ".accounts");
        for (uint256 i; i < n; ++i) {
            usd.mint(_addr(i), MINT);
            vm.prank(_addr(i));
            usd.approve(address(race), type(uint256).max);
        }
        _load();
        uint256 today;
        uint256 count = _col("events.kind").length;
        for (uint256 i; i < count; ++i) {
            Ev memory ev = _ev(i);
            if (ev.day != today) {
                assertGt(ev.day, today, "days only increase");
                today = ev.day;
                vm.warp(race.start() + today * 1 days);
            }
            string memory where = _at(i, ev);
            _apply(ev, where);
            _expect("expects", ev.expFrom, ev.expTo, where);
            _held("held", ev.heldFrom, ev.heldTo, where);
            assertEq(race.totalDeposits(address(usd)), ev.deposits, string.concat(where, ": deposits"));
            _quotes(i, where);
        }
        assertEq(qi, _col("quotes.event").length, "every quote checked");
        _expect("final", 0, _col("final.account").length, "final");
        _held("finalHeld", 0, _col("finalHeld.bounty").length, "final");
        assertEq(race.totalDeposits(address(usd)), vm.parseJsonUint(json, ".finalDeposits"), "final: deposits");
        _tokens();
    }

    function _tok(string memory key) internal view returns (uint256) {
        return vm.parseJsonUint(json, string.concat(".token.", key));
    }

    /// The token the simulation ran with (pof's TOKENS, or the emission off).
    function _tokenParams() internal {
        tokenEmission = _tok("emission");
        tokenDecayBps = _tok("decayBps");
        founderBps = _tok("founderBps");
        founderPeriods = _tok("founderPeriods");
        reporterBps = _tok("reporterBps");
        inflationPct = _tok("inflationPct");
        founder = _tok("hasFounder") == 1 ? _addr(_tok("founder")) : address(0);
    }

    /// Every period's closes and the founder's share claimed once the period's claims are open (pof mints at the next
    /// release, and its last period when the run ends; the contract waits graceDays more): each period minted what pof's TokenBook minted, from as many
    /// closes, and every holder holds what it holds there.
    function _tokens() internal {
        Token t = race.token();
        uint256[] storage periods = _col("token.periods.period");
        uint256 n = periods.length;
        if (n > 1) vm.warp(race.start() + ((periods[n - 1] + 1) * c_releaseEveryDays + graceDays) * 1 days);
        for (uint256 k = 1; k < n; ++k) {
            uint256 p = periods[k];
            string memory where = string.concat("token period ", vm.toString(p));
            assertEq(t.closeCount(p), _col("token.periods.closes")[k], string.concat(where, ": closes"));
            uint256 big = t.largest(p);
            for (uint256 i; i < t.closeCount(p); ++i) {
                if (i != big) t.claim(p, i);
            }
            t.claim(p, big);
            if (t.founderShare(p) != 0) t.claimFounder(p);
            assertEq(t.minted(p), _col("token.periods.minted")[k], string.concat(where, ": minted"));
        }
        uint256[] storage holders = _col("token.holders.account");
        for (uint256 k = 1; k < holders.length; ++k) {
            assertEq(
                t.balanceOf(_addr(holders[k])), _col("token.holders.balance")[k],
                string.concat("token: account ", vm.toString(holders[k]))
            );
        }
        assertEq(t.totalSupply(), _tok("supply"), "token: supply");
    }

    string[22] FIELDS = [
        "amount", "bounty", "day", "deposits", "expFrom", "expTo", "feeFrom", "feeTo", "fix", "funFrom", "funTo",
        "heldFrom", "heldTo", "issue", "kind", "outcome", "price", "prev", "seq", "sub", "weight", "who"
    ];

    function _load() internal {
        for (uint256 i; i < FIELDS.length; ++i) _read(string.concat("events.", FIELDS[i]));
        _read("expects.account");
        _read("expects.neg");
        _read("expects.value");
        _read("held.amount");
        _read("held.bounty");
        _read("fees.amount");
        _read("fees.to");
        _read("funders.account");
        _read("final.account");
        _read("final.neg");
        _read("final.value");
        _read("finalHeld.amount");
        _read("finalHeld.bounty");
        _read("token.periods.period");
        _read("token.periods.closes");
        _read("token.periods.minted");
        _read("token.holders.account");
        _read("token.holders.balance");
        for (uint256 i; i < QUOTE_FIELDS.length; ++i) _read(string.concat("quotes.", QUOTE_FIELDS[i]));
    }

    // pof/sim/export.py QUOTE_FIELDS
    string[11] QUOTE_FIELDS = [
        "attempting", "bounty", "cap", "event", "finderFee", "instalment", "lastInstalment", "offerBps", "price", "state",
        "sunsetDay"
    ];

    /// The quotes pof gave after event i, against Quoter.quote. pof's "won" is the contract's Won or Merged; the cap,
    /// share, attempts and sunset day are an open bounty's (after the merge pof's pot is the escrow).
    function _quotes(uint256 i, string memory where) internal {
        uint256[] storage evs = _col("quotes.event");
        for (; qi < evs.length && evs[qi] == i; ++qi) {
            uint256 b = _v("quotes", "bounty", qi);
            Quoter.Quote memory q = quoter.quote(race, b, address(usd));
            string memory at = string.concat(where, ": quote of bounty ", vm.toString(b), " ");
            uint256 state = _v("quotes", "state", qi);
            if (state == uint256(Race.State.Won)) {
                assertTrue(q.state == Race.State.Won || q.state == Race.State.Merged, string.concat(at, "state"));
            } else {
                assertEq(uint256(q.state), state, string.concat(at, "state"));
            }
            assertEq(q.price, _v("quotes", "price", qi), string.concat(at, "price"));
            assertEq(q.instalment, _v("quotes", "instalment", qi), string.concat(at, "instalment"));
            assertEq(q.lastInstalment, _v("quotes", "lastInstalment", qi), string.concat(at, "last instalment"));
            assertEq(q.finderFee, _v("quotes", "finderFee", qi), string.concat(at, "finder's fee"));
            if (state == uint256(Race.State.Open)) {
                assertEq(q.cap, _v("quotes", "cap", qi), string.concat(at, "cap"));
                assertEq(q.offerBps, _v("quotes", "offerBps", qi), string.concat(at, "share"));
                assertEq(q.attempting, _v("quotes", "attempting", qi), string.concat(at, "attempts"));
                assertEq(q.sunsetDay, _v("quotes", "sunsetDay", qi), string.concat(at, "sunset day"));
            }
        }
    }

    function _read(string memory column) internal {
        cols[keccak256(bytes(column))] = vm.parseJsonUintArray(json, string.concat(".", column));
    }

    function _col(string memory column) internal view returns (uint256[] storage) {
        return cols[keccak256(bytes(column))];
    }

    function _v(string memory table, string memory field, uint256 i) internal view returns (uint256) {
        return _col(string.concat(table, ".", field))[i];
    }

    function _ev(uint256 i) internal view returns (Ev memory ev) {
        uint256[22] memory v;
        for (uint256 f; f < FIELDS.length; ++f) v[f] = _v("events", FIELDS[f], i);
        ev = Ev(v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7], v[8], v[9], v[10], v[11], v[12], v[13], v[14], v[15],
            v[16], v[17], v[18], v[19], v[20], v[21]);
    }

    function _at(uint256 i, Ev memory ev) internal pure returns (string memory) {
        return string.concat(
            "event ", vm.toString(i), " (kind ", vm.toString(ev.kind), ", day ", vm.toString(ev.day), ", pof seq ",
            vm.toString(ev.seq), ")"
        );
    }

    // ---------- events ----------

    function _apply(Ev memory ev, string memory where) internal {
        address who = _addr(ev.who);
        uint256 k = ev.kind;
        if (k == REGISTER) {
            vm.prank(who);
            assertEq(race.register(address(usd)), ev.issue, string.concat(where, ": issue id"));
        } else if (k == ACCEPT) {
            assertEq(_accept(race, ev.issue, ev.weight), ev.bounty, string.concat(where, ": bounty id"));
        } else if (k == WITHDRAW_ISSUE) {
            vm.prank(who);
            race.withdrawIssue(ev.issue);
        } else if (k == PLEDGE) {
            vm.prank(who);
            race.pledge(ev.bounty, address(usd), ev.amount);
        } else if (k == ATTEMPT) {
            vm.prank(who);
            race.attempt(ev.bounty, address(usd));
        } else if (k == STOP) {
            vm.prank(who);
            race.stop(ev.bounty);
        } else if (k == SUBMIT || k == APPEAL) {
            vm.prank(who);
            uint256 id = k == SUBMIT
                ? race.commit(ev.bounty, bytes32(ev.fix), address(usd))
                : race.appeal(ev.prev, address(usd));
            assertEq(id, ev.sub, string.concat(where, ": submission id"));
            assertEq(race.lockedPrice(ev.bounty, address(usd)), ev.price, string.concat(where, ": price"));
            _result(race, id, Race.Outcome(ev.outcome), bytes32(ev.fix), _fees(ev));
        } else if (k == TOO_LATE) {
            vm.prank(who);
            assertEq(race.commit(ev.bounty, bytes32(ev.fix), address(usd)), 0, string.concat(where, ": late"));
        } else if (k == DUPLICATE) {
            vm.prank(who);
            uint256 id = race.commit(ev.bounty, bytes32(ev.fix), address(usd));
            assertEq(id, ev.sub, string.concat(where, ": submission id"));
            _result(race, id, Race.Outcome.Duplicate, bytes32(ev.fix), _fees(ev));
        } else if (k == APPEAL_DUPLICATE) {
            vm.prank(who);
            uint256 id = race.appealDuplicate(ev.bounty, bytes32(ev.fix), address(usd));
            assertEq(id, ev.prev, string.concat(where, ": appeal id"));
            _appealResult(race, id, ev.bounty, ev.outcome == 1, _fees(ev));
        } else if (k == MERGED) {
            _merged(race, ev.bounty, ev.weight);
        } else if (k == INSTALMENT) {
            race.claimInstalments(ev.bounty, address(usd), race.bounty(ev.bounty).epoch);
        } else if (k == SETTLE) {
            assertTrue(race.settle(ev.bounty, address(usd)), string.concat(where, ": settled"));
            _refunds(ev);
        } else if (k == SUNSET) {
            race.sunset(ev.bounty);
            _refunds(ev);
        } else {
            revert(string.concat(where, ": unknown kind"));
        }
    }

    function _fees(Ev memory ev) internal view returns (Race.Fee[] memory out) {
        out = new Race.Fee[](ev.feeTo - ev.feeFrom);
        for (uint256 i = ev.feeFrom; i < ev.feeTo; ++i) {
            out[i - ev.feeFrom] = Race.Fee(_addr(_v("fees", "to", i)), _v("fees", "amount", i));
        }
    }

    /// Every funder claims its refund (the contract pulls per funder; pof pays them all at the close).
    function _refunds(Ev memory ev) internal {
        for (uint256 i = ev.funFrom; i < ev.funTo; ++i) {
            vm.prank(_addr(_v("funders", "account", i)));
            race.claimRefund(ev.bounty, address(usd));
        }
    }

    // ---------- checks ----------

    function _net(address a) internal view returns (int256) {
        return int256(usd.balanceOf(a)) + int256(race.owed(a, address(usd))) - int256(MINT);
    }

    /// Each account's net: its wallet plus its credits, less what it was minted.
    function _expect(string memory t, uint256 from, uint256 to, string memory where) internal view {
        for (uint256 i = from; i < to; ++i) {
            uint256 account = _v(t, "account", i);
            int256 want = _v(t, "neg", i) == 1 ? -int256(_v(t, "value", i)) : int256(_v(t, "value", i));
            assertEq(_net(_addr(account)), want, string.concat(where, ": account ", vm.toString(account)));
        }
    }

    /// Each bounty's pot: pof's bounty account and its escrow.
    function _held(string memory t, uint256 from, uint256 to, string memory where) internal view {
        for (uint256 i = from; i < to; ++i) {
            uint256 b = _v(t, "bounty", i);
            assertEq(race.held(b, address(usd)), _v(t, "amount", i), string.concat(where, ": bounty ", vm.toString(b)));
        }
    }
}
