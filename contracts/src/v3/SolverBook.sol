// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {LaunchChain} from "./LaunchChain.sol";

/// The solvers' book of a v3 race (proof-of-fix#251 contract batch 3; #132 D29, launch design L6; ADR 0007;
/// specs/reputation, specs/bounty-market): each solver identity's reputation, its open claims against its cap, and
/// whether it is an active solver of the repository. RaceV3 deploys it from its constructor and is its only writer;
/// everything here is readable by anyone. No owner, no setter, nothing transferable.
///
/// **The identity is the solver's address** (L7). Amounts are micro-coins of the race's fee coin, as the bounties
/// Panels judges.
///
/// **The reputation cap (D29).** A solver's open claims (the bounties its fixes were judged at, submitted and not yet
/// final) add up to at most REP_BASE + REP_MULT × its reputation: a claim over it is refused before it is judged
/// (`openClaim` reverts, so the submission costs nothing). Reputation is the sum of the bounties of its fixes merged
/// (`paid`: final, still a pass, the head moved to it) and never reversed. A pass reversed by a test or a challenge
/// takes REP_LOSS_X × its bounty off, not below zero (`reversed`, once a submission: "minus", not a reset). A claim
/// closes at its verdict's finality, or when its submission ends unjudged (`closeClaim`).
///
/// **Active solvers (L6).** An identity is active while, within ACTIVE_WINDOW (26 weeks; the deployment's windows,
/// Panels.ACTIVE_WINDOW), it had a fix merged, or a failing-test dispute upheld while it already had a merged fix in the
/// repository (only the repository's own solvers count: an outsider's upheld test is paid, but doesn't count).
/// Activity is recorded when the race sees it (the merge, the dispute's settlement). The race refuses pledges while
/// fewer than ACTIVE_SOLVERS_MIN (3) are active (`activeAtLeast`). Identities are kept in a list ordered by their last
/// activity, so counting stops at the first one past the window.
contract SolverBook {
    uint256 public constant REP_BASE = 50e6; // $50
    uint256 public constant REP_MULT = 1;
    uint256 public constant REP_LOSS_X = 2; // REP_ON_REVERSAL "minus": a reversal takes 2 × its bounty off
    uint256 public constant ACTIVE_SOLVERS_MIN = 3;

    struct Solver {
        uint256 reputation;
        uint256 open; // open claims
        uint64 lastActive; // 0: never active
        bool hasFix; // a fix of it was merged in the repository
        address newer; // the activity list: the identity active more recently (0 at the head)
        address older;
    }

    struct Claim {
        address solver;
        uint256 amount;
    }

    address public immutable race;
    uint256 public immutable ACTIVE_WINDOW;

    mapping(address solver => Solver) internal _solvers;
    mapping(uint256 id => Claim) internal _claims;
    mapping(uint256 id => bool) public penalized; // a reversal already recorded against this submission
    address public latest; // the identity active most recently

    event ClaimOpened(uint256 indexed id, address indexed solver, uint256 amount, uint256 open, uint256 cap);
    event ClaimClosed(uint256 indexed id, address indexed solver, uint256 amount);
    event ReputationChanged(address indexed solver, uint256 indexed id, uint256 reputation, bool reversal);
    event Active(address indexed solver, uint256 at, bool byDispute);

    error NotRace();
    error OverCap(address solver, uint256 open, uint256 cap);
    error BadParams();

    /// Deployed by its race (the caller), with the deployment's ACTIVE_WINDOW. Reverts off Sepolia and the local test
    /// chains (#251, L2: LaunchChain).
    constructor(uint256 activeWindow_) {
        LaunchChain.check();
        if (activeWindow_ == 0) revert BadParams();
        race = msg.sender;
        ACTIVE_WINDOW = activeWindow_;
    }

    modifier onlyRace() {
        if (msg.sender != race) revert NotRace();
        _;
    }

    // ---------- the race ----------

    /// Submission `id`'s claim of `amount` for `solver`, before it is judged: refused over the cap.
    function openClaim(uint256 id, address solver, uint256 amount) external onlyRace {
        Solver storage x = _solvers[solver];
        uint256 cap = capOf(solver);
        uint256 open = x.open + amount;
        if (open > cap) revert OverCap(solver, x.open, cap);
        x.open = open;
        _claims[id] = Claim(solver, amount);
        emit ClaimOpened(id, solver, amount, open, cap);
    }

    /// Submission `id`'s claim closes (its verdict is final, or it ended unjudged); nothing if it has none open.
    function closeClaim(uint256 id) public onlyRace {
        Claim memory c = _claims[id];
        if (c.solver == address(0)) return;
        delete _claims[id];
        _solvers[c.solver].open -= c.amount;
        emit ClaimClosed(id, c.solver, c.amount);
    }

    /// Submission `id`'s fix was merged at its final pass: its claim closes, its bounty joins the solver's reputation,
    /// and the solver is active from now.
    function paid(uint256 id, address solver, uint256 bounty) external onlyRace {
        closeClaim(id);
        Solver storage x = _solvers[solver];
        x.reputation += bounty;
        x.hasFix = true;
        emit ReputationChanged(solver, id, x.reputation, false);
        _activate(solver, false);
    }

    /// Submission `id`'s pass was reversed: REP_LOSS_X × its bounty off its solver's reputation, not below zero. Once a
    /// submission.
    function reversed(uint256 id, address solver, uint256 bounty) external onlyRace {
        if (penalized[id]) return;
        penalized[id] = true;
        Solver storage x = _solvers[solver];
        uint256 loss = REP_LOSS_X * bounty;
        x.reputation = x.reputation > loss ? x.reputation - loss : 0;
        emit ReputationChanged(solver, id, x.reputation, true);
    }

    /// `disputer`'s failing-test dispute was upheld: it is active from now if it has a merged fix in the repository.
    function disputeUpheld(address disputer) external onlyRace {
        if (_solvers[disputer].hasFix) _activate(disputer, true);
    }

    // ---------- views ----------

    function reputation(address solver) external view returns (uint256) {
        return _solvers[solver].reputation;
    }

    function openClaims(address solver) external view returns (uint256) {
        return _solvers[solver].open;
    }

    /// REP_BASE + REP_MULT × reputation: the most its open claims may add up to.
    function capOf(address solver) public view returns (uint256) {
        return REP_BASE + REP_MULT * _solvers[solver].reputation;
    }

    function solverOf(address who) external view returns (Solver memory) {
        return _solvers[who];
    }

    function claimOf(uint256 id) external view returns (Claim memory) {
        return _claims[id];
    }

    function isActive(address who) public view returns (bool) {
        uint256 t = _solvers[who].lastActive;
        return t != 0 && block.timestamp <= t + ACTIVE_WINDOW;
    }

    /// The active solvers now.
    function activeCount() external view returns (uint256) {
        return activeAtLeast(type(uint256).max);
    }

    /// The active solvers now, counted up to `n` (the race asks for ACTIVE_SOLVERS_MIN).
    function activeAtLeast(uint256 n) public view returns (uint256 count) {
        for (address a = latest; a != address(0) && count < n && isActive(a); a = _solvers[a].older) {
            ++count;
        }
    }

    /// Whether pledges are taken now: at least ACTIVE_SOLVERS_MIN active solvers.
    function pledgesOpen() external view returns (bool) {
        return activeAtLeast(ACTIVE_SOLVERS_MIN) >= ACTIVE_SOLVERS_MIN;
    }

    // ---------- internals ----------

    /// `who` is active from now: it moves to the head of the activity list.
    function _activate(address who, bool byDispute) internal {
        Solver storage x = _solvers[who];
        x.lastActive = uint64(block.timestamp);
        emit Active(who, block.timestamp, byDispute);
        address head = latest;
        if (head == who) return;
        if (x.newer != address(0) || x.older != address(0)) {
            // unlink: it isn't the head, so it has a newer one
            _solvers[x.newer].older = x.older;
            if (x.older != address(0)) _solvers[x.older].newer = x.newer;
        }
        x.newer = address(0);
        x.older = head;
        if (head != address(0)) _solvers[head].newer = who;
        latest = who;
    }
}
