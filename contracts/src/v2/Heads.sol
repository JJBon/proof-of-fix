// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Verdicts} from "./Verdicts.sol";

/// The head registry, v2 (proof-of-fix#85, design S1, S5, S10, S11): for each self-governed repository, the canonical
/// head (the commit of the last fix the judges passed) and the constitution's hash. The chain is the source of truth;
/// git mirrors follow it (the bot, S1).
///
/// Genesis (task 5.1): the repositories and their heads are fixed at deployment (S10: "v1 had no head registry, so
/// v2's genesis head is the commit at deployment"), with the constitution's hash.
///
/// Moving a head (task 5.2, S1, S11): only its mover, the RaceV2 that created this registry, can move a head, and only
/// from inside `merged`, after the oracle quorum signed the verdict v2 naming the head as its base. A verdict whose base
/// is no longer the head is stale and refused: the head doesn't move, and the transaction reverts whole, so the race's
/// winner keeps its place and its locked share until a verdict on the rebased fix arrives. Each head records the bounty,
/// the submission and the verdict that moved it. Keyless: no owner, admin, upgrade or pause; the mover is fixed here.
///
/// Commits are stored as bytes32: a git SHA-1 (20 bytes) left-aligned, or a SHA-256 commit id. A repository's id is
/// bytes32 too (for example the hash of its Radicle RID, or of its canonical URL).
///
/// Hooks for the later v2 tasks (not built here):
///   TODO(5.9) a head moves only with 5 of 7 availability statements and the permanent copy's receipt.
///   TODO(5.10) the constitution's hash and ADRs: the 14-day window, entrenched articles, the revert head.
contract Heads {
    struct Head {
        bytes32 commit; // the canonical head
        bytes32 constitution; // the constitution's hash in force at this head
        uint256 movedAt; // the block timestamp it was set
        uint256 bounty; // the bounty whose fix this is (0 at genesis)
        uint256 submission; // the winning submission (0 at genesis)
        bytes32 verdict; // the EIP-712 struct hash of the verdict v2 that moved it (0 at genesis)
    }

    Verdicts public immutable verdicts; // the quorum (task 5.9's availability statements, 5.10's ADRs)
    address public immutable mover; // the only caller of `move`: the RaceV2 that deployed this registry
    bytes32[] internal _repos;
    mapping(bytes32 repo => Head) internal _heads;

    event HeadSet(bytes32 indexed repo, bytes32 indexed commit, bytes32 constitution);
    event HeadMoved(
        bytes32 indexed repo, bytes32 indexed base, bytes32 indexed commit, uint256 bounty, uint256 submission, bytes32 verdict
    );

    error BadParams();
    error UnknownRepo(bytes32 repo);
    error NotMover();
    error StaleVerdict(bytes32 repo, bytes32 base, bytes32 head);

    /// Genesis (S9, S10): each repository's head at deployment, with the genesis constitution's hash, and the mover.
    constructor(
        Verdicts verdicts_,
        bytes32[] memory repos_,
        bytes32[] memory commits_,
        bytes32 constitution_,
        address mover_
    ) {
        if (
            address(verdicts_).code.length == 0 || repos_.length != commits_.length || constitution_ == bytes32(0)
                || mover_ == address(0)
        ) {
            revert BadParams();
        }
        verdicts = verdicts_;
        mover = mover_;
        for (uint256 i; i < repos_.length; ++i) {
            bytes32 r = repos_[i];
            if (r == bytes32(0) || commits_[i] == bytes32(0) || _heads[r].commit != bytes32(0)) revert BadParams();
            _repos.push(r);
            _heads[r] = Head(commits_[i], constitution_, block.timestamp, 0, 0, bytes32(0));
            emit HeadSet(r, commits_[i], constitution_);
        }
    }

    function repos() external view returns (bytes32[] memory) {
        return _repos;
    }

    function isRepo(bytes32 repo) external view returns (bool) {
        return _heads[repo].commit != bytes32(0);
    }

    /// A repository's canonical head and the constitution in force there.
    function head(bytes32 repo) external view returns (Head memory h) {
        h = _heads[repo];
        if (h.commit == bytes32(0)) revert UnknownRepo(repo);
    }

    /// S1: the head moves to the fix only if the verdict was checked on the head (`base == head`). Called by the mover,
    /// after the quorum's signatures on the verdict were checked and spent.
    function move(bytes32 repo, bytes32 base, bytes32 fix, uint256 bounty, uint256 submission, bytes32 verdict)
        external
    {
        if (msg.sender != mover) revert NotMover();
        Head storage h = _heads[repo];
        bytes32 current = h.commit;
        if (current == bytes32(0)) revert UnknownRepo(repo);
        if (base != current) revert StaleVerdict(repo, base, current);
        if (fix == bytes32(0) || fix == base) revert BadParams();
        h.commit = fix;
        h.movedAt = block.timestamp;
        h.bounty = bounty;
        h.submission = submission;
        h.verdict = verdict;
        emit HeadMoved(repo, base, fix, bounty, submission, verdict);
    }
}
