// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// The clock the token reads: its Race's days since deployment.
interface IRaceClock {
    function day() external view returns (uint256);
}

/// The protocol's token (proof-of-fix#56 design D15; the emission of #58, as pof/tokens.py TokenBook mints it): a fixed
/// emission each period (one release of its Race), decaying by a published share each period, minted only to the
/// bounties that closed paid in the period, by their AI weight. The founder's share comes off the top for a published
/// number of periods, only in periods that mint. There's no genesis, no admin, no pause and no rule change: everything
/// is fixed at deployment, and the only account that records a close is the Race fixed here.
///
/// A close's period is fixed by date, not by when it's recorded: the Race gives the period of the bounty's last
/// instalment's release, so settling later can't move it into a quieter period (owner, 2026-10-29). A period's claims
/// open graceDays after it ends, so its closes can be recorded first. A close recorded after its period's claims have
/// opened is refused (its tokens aren't minted): crediting it to a later period would let a solver choose that period
/// by waiting, and anyone (its solver, its reporter, any keeper) can settle it in the period and the grace after it.
///
/// Minting is pulled, not pushed: once a period's claims are open, anyone claims a close's tokens (they go to its
/// solver and reporter, not to the caller) and the founder's share. A close's tokens are the period's pool times its weight over
/// the period's weight, rounded down; the rounding remainder goes to the first close with the largest weight, so its
/// claim waits until every other close of the period is claimed (anyone can claim them). Each call is bounded; no call
/// loops over a period's closes. A period mints exactly its emission once all is claimed, or nothing if nothing closed.
///
/// A new version (D15, task 3.5) is this contract deployed again, by anyone, naming the version it continues
/// (`previous`). It keeps the previous version's schedule (the emission, its decay, the founder's share, the periods,
/// the grace and the start), swaps the previous version's tokens 1:1 by burning them, forever, and in each period mints
/// only what the schedule leaves after the previous version's mint in it (`committed`). So a period's emission goes,
/// whole, to the oldest version with a close of weight in it, and the versions together never mint more than one
/// schedule. Nothing links the versions but this constructor argument: which one is "the" token is what holders swap
/// into.
contract Token is ERC20 {
    uint256 internal constant BPS = 10_000;
    uint256 public constant MAX_FOUNDER_BPS = 500; // the owner's published cap (openspec rule 3)

    struct Close {
        uint256 bounty;
        address solver;
        address reporter; // none if it forfeited its share (junk, or an inflated weight)
        uint256 weight;
        bool claimed;
    }

    address public immutable race;
    Token public immutable previous; // the version this one continues (D15); none for the first
    uint256 public immutable start; // the schedule's start: the first version's deployment, every version's day 0
    address public immutable founder; // none: no founder's share
    uint256 public immutable firstEmission; // micro-tokens in period 0
    uint256 public immutable decayBps; // of the previous period's emission, each period
    uint256 public immutable founderBps;
    uint256 public immutable founderPeriods;
    uint256 public immutable reporterBps; // of a close's tokens, to its reporter
    uint256 public immutable periodDays; // a period is a release of the Race
    uint256 public immutable inflationPct; // a registered weight above this % of the merge estimate forfeits the reporter's share
    uint256 public immutable graceDays; // a period's claims open this long after it ends

    uint256[] internal _emissions; // memo: _emissions[p] is period p's emission
    mapping(uint256 period => Close[]) internal _closes;
    mapping(uint256 period => uint256) public totalWeight;
    mapping(uint256 period => uint256) internal _largest; // the first close with the largest weight, + 1
    mapping(uint256 period => uint256) internal _claimedOthers; // closes claimed, the largest aside
    mapping(uint256 period => uint256) internal _paidFloors; // what they got
    mapping(uint256 period => bool) public founderClaimed;
    mapping(uint256 period => uint256) public minted; // the founder's share included
    uint256 public swapped; // the previous version's tokens burned for these

    event Recorded(uint256 indexed period, uint256 indexed bounty, uint256 index, uint256 weight);
    event Claimed(uint256 indexed period, uint256 indexed index, uint256 amount);
    event TooLate(uint256 indexed period, uint256 indexed bounty); // recorded after its period's claims opened
    event Swapped(address indexed holder, uint256 amount);

    error NotRace();
    error NotYet();
    error Refused();
    error BadParams();

    constructor(
        address race_,
        address founder_,
        uint256 firstEmission_,
        uint256 decayBps_,
        uint256 founderBps_,
        uint256 founderPeriods_,
        uint256 reporterBps_,
        uint256 periodDays_,
        uint256 inflationPct_,
        uint256 graceDays_,
        Token previous_
    ) ERC20("proof-of-fix", "POF") {
        if (race_ == address(0) || periodDays_ == 0 || decayBps_ > BPS || reporterBps_ > BPS) revert BadParams();
        if (inflationPct_ < 100) revert BadParams(); // below the merge estimate itself
        if (founderBps_ > MAX_FOUNDER_BPS) revert BadParams(); // within the owner's published cap (rule 3)
        race = race_;
        founder = founder_;
        firstEmission = firstEmission_;
        decayBps = decayBps_;
        founderBps = founderBps_;
        founderPeriods = founderPeriods_;
        reporterBps = reporterBps_;
        periodDays = periodDays_;
        inflationPct = inflationPct_;
        graceDays = graceDays_;
        previous = previous_;
        if (address(previous_) == address(0)) {
            start = block.timestamp;
        } else {
            // the same schedule, from the same start (D15): only the version's own rules (the reporter's share, the
            // inflation tolerance) and its Race may differ
            if (
                previous_.firstEmission() != firstEmission_ || previous_.decayBps() != decayBps_
                    || previous_.founder() != founder_ || previous_.founderBps() != founderBps_
                    || previous_.founderPeriods() != founderPeriods_ || previous_.periodDays() != periodDays_
                    || previous_.graceDays() != graceDays_
            ) revert BadParams();
            start = previous_.start();
        }
        _emissions.push(firstEmission_);
    }

    /// Micro-tokens, on the scale of the simulation's credits.
    function decimals() public pure override returns (uint8) {
        return 6;
    }

    // ---------- the schedule ----------

    function currentPeriod() public view returns (uint256) {
        return IRaceClock(race).day() / periodDays;
    }

    /// Period p's claims open graceDays after it ends; from then on its closes are final.
    function claimsOpen(uint256 p) public view returns (bool) {
        return IRaceClock(race).day() >= (p + 1) * periodDays + graceDays;
    }

    /// Period p's emission: the first, less decayBps of the previous one each period, rounded down.
    function emission(uint256 p) public view returns (uint256 e) {
        uint256 n = _emissions.length;
        if (p < n) return _emissions[p];
        e = _emissions[n - 1];
        for (uint256 i = n; i <= p; ++i) {
            e -= e * decayBps / BPS;
        }
    }

    /// What period p's emission leaves this version: all of it, less what the previous versions mint in p.
    function available(uint256 p) public view returns (uint256) {
        uint256 e = emission(p);
        return address(previous) == address(0) ? e : e - previous.committed(p);
    }

    /// What this version mints in period p once it's all claimed (claimed or not yet): what's available to it if
    /// anything of weight closed in p, else nothing. Final once p's claims open, as no close is recorded after.
    function committed(uint256 p) public view returns (uint256) {
        return totalWeight[p] == 0 ? 0 : available(p);
    }

    /// The founder's part of what period p leaves this version, for the published number of periods: never more
    /// than its share of the schedule, across versions.
    function founderShare(uint256 p) public view returns (uint256) {
        if (founder == address(0) || p >= founderPeriods) return 0;
        return available(p) * founderBps / BPS;
    }

    function closesOf(uint256 p) external view returns (Close[] memory) {
        return _closes[p];
    }

    function closeCount(uint256 p) external view returns (uint256) {
        return _closes[p].length;
    }

    /// The close that takes period p's rounding remainder: the first with the largest weight.
    function largest(uint256 p) external view returns (uint256) {
        if (_largest[p] == 0) revert Refused();
        return _largest[p] - 1;
    }

    // ---------- burning (OpenZeppelin's ERC20Burnable, which isn't vendored) ----------

    /// A holder burns its own tokens.
    function burn(uint256 amount) external {
        _burn(msg.sender, amount);
    }

    /// Burns a holder's tokens within the caller's allowance: the next version's swap.
    function burnFrom(address holder, uint256 amount) external {
        _spendAllowance(holder, msg.sender, amount);
        _burn(holder, amount);
    }

    // ---------- migration ----------

    /// Swaps the previous version's tokens 1:1 (D15): they're burned (the holder approves this token first), and
    /// the same number of these is minted to the holder. Open forever.
    function swap(uint256 amount) external {
        if (address(previous) == address(0)) revert Refused();
        previous.burnFrom(msg.sender, amount);
        swapped += amount;
        _mint(msg.sender, amount);
        emit Swapped(msg.sender, amount);
    }

    // ---------- closes ----------

    /// A bounty closed paid in period p (its last instalment's release): it shares that period's emission by its
    /// weight, the smaller of the oracles' estimates at registration and at merge (#58 D3). A registration above
    /// inflationPct of the merge estimate forfeits the reporter's share to the solver; the Race forfeits its finder's
    /// fee too. Recorded after p's claims have opened, it's refused and mints nothing. Only the Race records.
    /// Returns whether the registration was inflated.
    function record(uint256 bounty, uint256 p, uint256 registered, uint256 atMerge, address solver, address reporter)
        external
        returns (bool inflated)
    {
        if (msg.sender != race) revert NotRace();
        if (p > currentPeriod()) revert Refused(); // a close isn't recorded before its last instalment's release
        inflated = registered * 100 > atMerge * inflationPct;
        if (claimsOpen(p)) {
            emit TooLate(p, bounty);
            return inflated;
        }
        if (inflated) reporter = address(0);
        uint256 weight = registered < atMerge ? registered : atMerge;
        Close[] storage cs = _closes[p];
        uint256 i = cs.length;
        cs.push(Close(bounty, solver, reporter, weight, false));
        totalWeight[p] += weight;
        if (_largest[p] == 0 || weight > cs[_largest[p] - 1].weight) _largest[p] = i + 1;
        emit Recorded(p, bounty, i, weight);
    }

    /// Mints close i of a period whose claims are open to its solver and reporter. Anyone calls it.
    function claim(uint256 p, uint256 i) external {
        uint256 w = totalWeight[p];
        if (!claimsOpen(p)) revert NotYet();
        Close storage c = _closes[p][i];
        if (w == 0 || c.claimed) revert Refused();
        _emission(p); // memo
        uint256 pool = available(p) - founderShare(p);
        uint256 amount;
        if (i == _largest[p] - 1) {
            if (_claimedOthers[p] != _closes[p].length - 1) revert NotYet(); // its remainder needs the others' floors
            amount = pool - _paidFloors[p];
        } else {
            amount = pool * c.weight / w;
            _paidFloors[p] += amount;
            _claimedOthers[p] += 1;
        }
        c.claimed = true;
        minted[p] += amount;
        uint256 toReporter = c.reporter == address(0) ? 0 : amount * reporterBps / BPS;
        if (toReporter != 0) _mint(c.reporter, toReporter);
        if (amount - toReporter != 0) _mint(c.solver, amount - toReporter);
        emit Claimed(p, i, amount);
    }

    /// Mints the founder's share of a finished period in which something closed with weight.
    function claimFounder(uint256 p) external {
        if (!claimsOpen(p)) revert NotYet();
        if (totalWeight[p] == 0 || founderClaimed[p]) revert Refused();
        founderClaimed[p] = true;
        uint256 amount = founderShare(p);
        _emission(p); // memo
        minted[p] += amount;
        if (amount != 0) _mint(founder, amount);
    }

    /// emission(p), extending the memo so later calls don't recompute the decay.
    function _emission(uint256 p) internal returns (uint256 e) {
        uint256 n = _emissions.length;
        if (p < n) return _emissions[p];
        e = _emissions[n - 1];
        for (uint256 i = n; i <= p; ++i) {
            e -= e * decayBps / BPS;
            _emissions.push(e);
        }
    }
}
