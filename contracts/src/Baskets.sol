// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {IERC20Metadata} from "@openzeppelin/contracts/token/ERC20/extensions/IERC20Metadata.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuardTransient} from "@openzeppelin/contracts/utils/ReentrancyGuardTransient.sol";

/// Per-coin escrow for bounties (proof-of-fix#56 design D5 and D6, #59). A bounty holds a basket: one pot per coin,
/// credited with what actually arrived. Everything paid out becomes a credit pulled per coin, to any address its
/// owner names, so a coin that can't move doesn't hold up the others; a credit can also be swapped for another coin
/// when both sides agree. Nothing loops over a bounty's coins or funders: whoever is owed pulls per coin, so junk
/// coins or dust pledges cost only the one who touches them.
///
/// No owner, admin, upgrade or pause: the caps are fixed at deployment, and a coin's withdraw-only mode switches on by
/// itself when its balance stops covering what the contract owes in it. Only that coin stops (owner, 2026-10-26): with
/// any coin allowed, a hostile issuer can break its own coin's invariant, and that mustn't stop the others. The race (Race.sol) decides who is paid what;
/// this layer only refuses to pay out more than a pot holds.
abstract contract Baskets is ReentrancyGuardTransient {
    using SafeERC20 for IERC20;

    uint256 internal constant BPS = 10_000;
    /// More decimals than this would overflow the caps' scaling; such coins are refused.
    uint8 internal constant MAX_DECIMALS = 30;

    /// The most a bounty can hold in one coin, in whole coins (scaled by the coin's decimals). Without a price feed a
    /// cap can only count coins, not value (#59).
    uint256 public immutable bountyCap;
    /// The most the contract can hold in one coin (open pots plus credits), in whole coins.
    uint256 public immutable totalCap;

    /// Set once, forever, when a coin's invariant fails: its credits and refunds can still be pulled, nothing else in
    /// it moves. The other coins carry on.
    mapping(address coin => bool) public withdrawOnly;

    /// 10 ** decimals for every coin seen, 0 for the rest.
    mapping(address coin => uint256) public unit;
    /// Every coin ever pledged or paid in, in order, for check().
    address[] public coins;

    /// What open pots hold in each coin, the credits not yet pulled, and the deposits the race holds (stakes, check
    /// deposits): together, what the contract owes in it.
    mapping(address coin => uint256) public totalHeld;
    mapping(address coin => uint256) public totalOwed;
    mapping(address coin => uint256) public totalDeposits;
    mapping(address account => mapping(address coin => uint256)) public owed;

    struct Pot {
        uint256 received; // every pledge, as received
        uint256 paid; // paid out of the pot by the race
        uint256 refundLeft; // what returns to funders, fixed by the first refund
        uint256 refunded; // refunds credited so far, rounded down
        uint32 funders; // distinct funders
        uint32 refunds; // funders refunded so far
        bool refunding; // refunds have started: the race can't pay out of the pot any more
        address lastFunder; // the highest address among funders: it takes the rounding remainder (design D2)
    }

    mapping(uint256 bounty => mapping(address coin => Pot)) internal _pots;
    mapping(uint256 bounty => mapping(address coin => mapping(address funder => uint256))) public pledged;
    mapping(uint256 bounty => mapping(address coin => mapping(address funder => bool))) public refundedTo;

    /// A standing offer: `from` pays `give` of `giveCoin` for `to`'s credit of `want` in `wantCoin`.
    struct Swap {
        address from;
        address to;
        address giveCoin;
        uint256 give;
        address wantCoin;
        uint256 want;
    }

    mapping(uint256 id => Swap) public swaps;
    uint256 public swapCount;

    event Pledged(uint256 indexed bounty, address indexed coin, address indexed funder, uint256 amount);
    event Paid(uint256 indexed bounty, address indexed coin, address indexed to, uint256 amount);
    event Collected(address indexed coin, address indexed from, address indexed to, uint256 amount);
    event Refunded(uint256 indexed bounty, address indexed coin, address indexed funder, uint256 amount);
    event Withdrawn(address indexed account, address indexed coin, address to, uint256 amount);
    event SwapOffered(uint256 indexed id, address indexed from, address indexed to);
    event SwapCancelled(uint256 indexed id);
    event SwapAccepted(uint256 indexed id);
    event WithdrawOnly(address indexed coin, uint256 balance, uint256 owedInCoin);

    error WithdrawOnlyMode(address coin);
    error ZeroAmount();
    error ShortReceived(uint256 sent, uint256 received);
    error UnsupportedCoin(address coin);
    error OverBountyCap(address coin);
    error OverTotalCap(address coin);
    error OverPot(uint256 bounty, address coin);
    error PotRefunding(uint256 bounty, address coin);
    error NothingOwed();
    error NotRefundable(uint256 bounty, address coin);
    error NotYours(uint256 id);

    constructor(uint256 bountyCap_, uint256 totalCap_) {
        bountyCap = bountyCap_;
        totalCap = totalCap_;
    }

    modifier live(address coin) {
        if (withdrawOnly[coin]) revert WithdrawOnlyMode(coin);
        _;
    }

    // ---------- views ----------

    function pot(uint256 bounty, address coin) external view returns (Pot memory) {
        return _pots[bounty][coin];
    }

    /// What a pot still holds: received, less what was paid out and refunded.
    function held(uint256 bounty, address coin) public view returns (uint256) {
        Pot storage p = _pots[bounty][coin];
        return p.received - p.paid - p.refunded;
    }

    function coinCount() external view returns (uint256) {
        return coins.length;
    }

    /// Does the contract hold, in this coin, at least what it owes in it? A coin whose balanceOf reverts fails.
    function solvent(address coin) public view returns (bool) {
        try IERC20(coin).balanceOf(address(this)) returns (uint256 balance) {
            return balance >= totalHeld[coin] + totalOwed[coin] + totalDeposits[coin];
        } catch {
            return false;
        }
    }

    // ---------- anyone ----------

    /// Checks every coin's invariant; each that fails switches to withdraw-only, forever. True if all hold.
    function check() external nonReentrant returns (bool ok) {
        ok = true;
        for (uint256 i; i < coins.length; ++i) {
            if (!_checkCoin(coins[i])) ok = false;
        }
    }

    /// Pulls the caller's whole credit in one coin, to any address it names (one frozen by a coin's issuer can name
    /// another). A transfer that fails reverts, and the credit stays.
    function withdraw(address coin, address to) external nonReentrant {
        uint256 amount = owed[msg.sender][coin];
        if (amount == 0) revert NothingOwed();
        _checkCoin(coin); // design D6: before any payout
        owed[msg.sender][coin] = 0;
        totalOwed[coin] -= amount;
        IERC20(coin).safeTransfer(to, amount);
        emit Withdrawn(msg.sender, coin, to, amount);
    }

    /// Credits the caller's refund from a pot, in proportion to what it pledged, rounded down; the funder with the
    /// highest address also gets the remainder once every funder has been refunded (as pof's _refund_inputs). Open
    /// once the race has settled the pot (_settleForRefund), or to every funder once the coin is withdraw-only.
    function claimRefund(uint256 bounty, address coin) external nonReentrant {
        uint256 put = pledged[bounty][coin][msg.sender];
        if (put == 0 || refundedTo[bounty][coin][msg.sender]) revert NothingOwed();
        Pot storage p = _pots[bounty][coin];
        if (!p.refunding) {
            if (!withdrawOnly[coin] && !_settleForRefund(bounty, coin)) revert NotRefundable(bounty, coin);
            p.refunding = true;
            p.refundLeft = p.received - p.paid;
        }
        refundedTo[bounty][coin][msg.sender] = true;
        uint256 amount = p.refundLeft * put / p.received;
        p.refunds += 1;
        p.refunded += amount;
        totalHeld[coin] -= amount;
        _credit(msg.sender, coin, amount);
        emit Refunded(bounty, coin, msg.sender, amount);
        if (p.refunds == p.funders) {
            uint256 rest = p.refundLeft - p.refunded;
            if (rest != 0) {
                p.refunded += rest;
                totalHeld[coin] -= rest;
                _credit(p.lastFunder, coin, rest);
                emit Refunded(bounty, coin, p.lastFunder, rest);
            }
        }
    }

    /// Offers `give` of `giveCoin`, paid in now, for `to`'s credit of `want` in `wantCoin` (#59: a coin the bounty
    /// can't pay out is swapped for another, if its owner agrees). The payment waits as the offerer's own credit
    /// until the offer is accepted or cancelled.
    function offerSwap(address to, address wantCoin, uint256 want, address giveCoin, uint256 give)
        external
        nonReentrant
        live(wantCoin)
        live(giveCoin)
        returns (uint256 id)
    {
        if (give == 0 || want == 0) revert ZeroAmount();
        _receive(giveCoin, msg.sender, give);
        totalOwed[giveCoin] += give; // owed to the offerer until accepted or cancelled
        id = ++swapCount;
        swaps[id] = Swap(msg.sender, to, giveCoin, give, wantCoin, want);
        emit SwapOffered(id, msg.sender, to);
    }

    /// The offerer takes its payment back as a credit.
    function cancelSwap(uint256 id) external nonReentrant {
        Swap memory s = swaps[id];
        if (s.from != msg.sender) revert NotYours(id);
        delete swaps[id];
        owed[s.from][s.giveCoin] += s.give;
        emit SwapCancelled(id);
    }

    /// The credit's owner accepts: its credit in wantCoin goes to the offerer, the payment to it.
    function acceptSwap(uint256 id) external nonReentrant {
        Swap memory s = swaps[id];
        if (s.to != msg.sender) revert NotYours(id);
        if (withdrawOnly[s.wantCoin]) revert WithdrawOnlyMode(s.wantCoin);
        if (withdrawOnly[s.giveCoin]) revert WithdrawOnlyMode(s.giveCoin);
        if (owed[s.to][s.wantCoin] < s.want) revert NothingOwed();
        delete swaps[id];
        owed[s.to][s.wantCoin] -= s.want;
        owed[s.from][s.wantCoin] += s.want;
        owed[s.to][s.giveCoin] += s.give;
        emit SwapAccepted(id);
    }

    // ---------- for the race ----------

    /// Called once, before a pot's first refund: the race pays out what's still due from the pot (it may call _pay)
    /// and says whether the bounty's outcome is final. If it is, refunds open and the race can't pay out of the pot
    /// any more.
    function _settleForRefund(uint256 bounty, address coin) internal virtual returns (bool);

    /// A pledge from msg.sender: credited by the amount that arrived, refused if less arrived than was sent.
    function _pledge(uint256 bounty, address coin, uint256 amount) internal live(coin) {
        if (amount == 0) revert ZeroAmount();
        Pot storage p = _pots[bounty][coin];
        if (p.refunding) revert PotRefunding(bounty, coin);
        _see(coin);
        if (held(bounty, coin) + amount > bountyCap * unit[coin]) revert OverBountyCap(coin);
        _receive(coin, msg.sender, amount);
        if (pledged[bounty][coin][msg.sender] == 0) {
            p.funders += 1;
            if (msg.sender > p.lastFunder) p.lastFunder = msg.sender;
        }
        pledged[bounty][coin][msg.sender] += amount;
        p.received += amount;
        totalHeld[coin] += amount;
        emit Pledged(bounty, coin, msg.sender, amount);
    }

    /// Pays an amount out of a pot as a credit. Never more than the pot holds, and never once its refunds started.
    function _pay(uint256 bounty, address coin, address to, uint256 amount) internal live(coin) {
        Pot storage p = _pots[bounty][coin];
        if (p.refunding) revert PotRefunding(bounty, coin);
        if (amount > held(bounty, coin)) revert OverPot(bounty, coin);
        p.paid += amount;
        totalHeld[coin] -= amount;
        _credit(to, coin, amount);
        emit Paid(bounty, coin, to, amount);
    }

    /// Takes a payment (a fee, a deposit) from `from` straight into `to`'s credit.
    function _collect(address coin, address from, uint256 amount, address to) internal live(coin) {
        if (amount == 0) revert ZeroAmount();
        _receive(coin, from, amount);
        _credit(to, coin, amount);
        emit Collected(coin, from, to, amount);
    }

    /// Takes a deposit from `from` into the race's keeping (a check deposit, an issue stake).
    function _hold(address coin, address from, uint256 amount) internal live(coin) {
        if (amount == 0) revert ZeroAmount();
        _receive(coin, from, amount);
        totalDeposits[coin] += amount;
    }

    /// Releases part of a held deposit as a credit to `to` (a refund, a fee, a forfeit).
    function _release(address coin, uint256 amount, address to) internal {
        if (amount == 0) return;
        totalDeposits[coin] -= amount;
        _credit(to, coin, amount);
    }

    // ---------- internals ----------

    /// Pulls `amount` of a coin from `from`, measuring what arrived; refuses fee-on-transfer coins and the total cap.
    function _receive(address coin, address from, uint256 amount) private {
        _see(coin);
        if (totalHeld[coin] + totalOwed[coin] + totalDeposits[coin] + amount > totalCap * unit[coin]) {
            revert OverTotalCap(coin);
        }
        uint256 before = IERC20(coin).balanceOf(address(this));
        IERC20(coin).safeTransferFrom(from, address(this), amount);
        uint256 received = IERC20(coin).balanceOf(address(this)) - before;
        if (received != amount) revert ShortReceived(amount, received);
    }

    function _credit(address to, address coin, uint256 amount) private {
        owed[to][coin] += amount;
        totalOwed[coin] += amount;
    }

    function _see(address coin) internal {
        if (unit[coin] != 0) return;
        uint8 decimals;
        try IERC20Metadata(coin).decimals() returns (uint8 d) {
            decimals = d;
        } catch {
            revert UnsupportedCoin(coin);
        }
        if (decimals > MAX_DECIMALS) revert UnsupportedCoin(coin);
        unit[coin] = 10 ** decimals;
        coins.push(coin);
    }

    /// The invariant for one coin (design D6). If it fails, the coin's withdraw-only mode switches on, forever.
    function _checkCoin(address coin) private returns (bool) {
        if (solvent(coin)) return true;
        if (!withdrawOnly[coin]) {
            withdrawOnly[coin] = true;
            uint256 balance;
            try IERC20(coin).balanceOf(address(this)) returns (uint256 b) {
                balance = b;
            } catch {}
            emit WithdrawOnly(coin, balance, totalHeld[coin] + totalOwed[coin] + totalDeposits[coin]);
        }
        return false;
    }
}
