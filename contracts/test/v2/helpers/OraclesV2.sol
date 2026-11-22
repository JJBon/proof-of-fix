// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Test} from "forge-std/Test.sol";
import {RaceV2 as Race} from "../../../src/v2/RaceV2.sol";
import {RaceV2Base} from "../../../src/v2/RaceV2Base.sol";
import {Verdicts} from "../../../src/v2/Verdicts.sol";
import {IFees} from "../../../src/v2/IFees.sol";
import {genesis} from "./GenesisV2.sol";

/// v2 (proof-of-fix#85, task 5.1): v1's helper (task 3.1, D3) for RaceV2, whose keys live in Verdicts and whose
/// EIP-712 domain is version "2". The oracle quorum, as test keys. Every result is signed here over its EIP-712 digest, hashed
/// independently of the contract's own constants (the type strings are spelled out again), so a drift between the
/// two fails the tests. Signatures go in signer-address order, as the contract requires.
abstract contract OraclesV2 is Test {
    uint256[] internal oracleSecrets; // sorted by address
    address[] internal oracleSet;
    uint256 internal oracleQuorum;
    // Operators' disclosed accounts and their seats' keys (task 5.3: a key whose operator is a party is recused).
    address[] internal operatorAccounts;
    address[] internal operatorKeys;
    uint256 internal nonces;

    uint256 internal inflationPct = 300; // #58 D3 (amended): a registered weight above 300 % of the merge estimate

    // The head registry's genesis (task 5.2): one self-governed repository, its head and the constitution's hash.
    bytes32 internal constant REPO = keccak256("example-org/proof-of-fix");
    bytes32 internal constant GENESIS_HEAD = bytes32(bytes20(keccak256("the genesis commit"))); // a SHA-1, left-aligned
    bytes32 internal constant GENESIS_CONSTITUTION = keccak256("CONSTITUTION.md at genesis");
    uint8 internal constant TIER_ISSUE = 1;
    uint8 internal constant TIER_CONSTITUTION = 2;

    // The verdict v2's type (S11), spelled out again here so a drift from the contract's constants fails the tests.
    string internal constant VERDICT_TYPE =
        "Verdict(bytes32 repo,bytes32 base,bytes32 fix,uint256 bounty,uint256 submission,uint8 tier,uint8 outcome,bytes32 receiptHash,bytes32 seed,bytes32 nonce)";

    /// n keys ("oracle0".."oracle<n-1>"), sorted by address, and the quorum q.
    function _makeOracles(uint256 n, uint256 q) internal {
        delete oracleSecrets;
        delete oracleSet;
        for (uint256 i; i < n; ++i) {
            (address a, uint256 k) = makeAddrAndKey(string.concat("oracle", vm.toString(i)));
            oracleSet.push(a);
            oracleSecrets.push(k);
            for (uint256 j = oracleSet.length - 1; j > 0 && oracleSet[j - 1] > oracleSet[j]; --j) {
                (oracleSet[j - 1], oracleSet[j]) = (oracleSet[j], oracleSet[j - 1]);
                (oracleSecrets[j - 1], oracleSecrets[j]) = (oracleSecrets[j], oracleSecrets[j - 1]);
            }
        }
        oracleQuorum = q;
    }

    /// A RaceV2 with its own Verdicts holding the current oracle set and quorum, and its head registry with one
    /// repository (REPO at GENESIS_HEAD).
    function _newRace(RaceV2Base.Config memory c, address[] memory feeCoins, uint256 bountyCap, uint256 totalCap)
        internal
        returns (Race)
    {
        bytes32[] memory repos = new bytes32[](1);
        bytes32[] memory heads = new bytes32[](1);
        repos[0] = REPO;
        heads[0] = GENESIS_HEAD;
        return new Race(
            c,
            feeCoins,
            bountyCap,
            totalCap,
            new Verdicts(genesis(oracleSet, oracleQuorum, operatorAccounts, operatorKeys)),
            inflationPct,
            0,
            repos,
            heads,
            GENESIS_CONSTITUTION,
            IFees(address(0))
        );
    }

    function _nonce() internal returns (bytes32) {
        return bytes32(++nonces);
    }

    // ---------- digests ----------

    function _digest(Race race, bytes32 structHash) internal view returns (bytes32) {
        bytes32 domain = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256("proof-of-fix Race"),
                keccak256("2"),
                block.chainid,
                address(race)
            )
        );
        return keccak256(abi.encodePacked("\x19\x01", domain, structHash));
    }

    function _feesHash(RaceV2Base.Fee[] memory fees) internal pure returns (bytes32) {
        bytes32[] memory h = new bytes32[](fees.length);
        for (uint256 i; i < fees.length; ++i) {
            h[i] = keccak256(abi.encode(keccak256("Fee(address to,uint256 amount)"), fees[i].to, fees[i].amount));
        }
        return keccak256(abi.encodePacked(h));
    }

    function _acceptHash(uint256 issue, bytes32 nonce) internal pure returns (bytes32) {
        return _acceptHash(issue, 0, nonce);
    }

    function _acceptHash(uint256 issue, uint256 weight, bytes32 nonce) internal pure returns (bytes32) {
        return keccak256(
            abi.encode(keccak256("Accept(uint256 issue,uint256 weight,bytes32 nonce)"), issue, weight, nonce)
        );
    }

    function _refuseHash(uint256 issue, uint256 open, bytes32 nonce) internal pure returns (bytes32) {
        return keccak256(
            abi.encode(keccak256("RefuseSimilar(uint256 issue,uint256 openBounty,bytes32 nonce)"), issue, open, nonce)
        );
    }

    function _junkHash(uint256 issue, bytes32 nonce) internal pure returns (bytes32) {
        return keccak256(abi.encode(keccak256("Junk(uint256 issue,bytes32 nonce)"), issue, nonce));
    }

    function _verdictHash(RaceV2Base.Verdict memory v) internal pure returns (bytes32) {
        return keccak256(
            abi.encode(
                keccak256(bytes(VERDICT_TYPE)),
                v.repo,
                v.base,
                v.fix,
                v.bounty,
                v.submission,
                v.tier,
                v.outcome,
                v.receiptHash,
                v.seed,
                v.nonce
            )
        );
    }

    function _resultHash(RaceV2Base.Verdict memory v, RaceV2Base.Fee[] memory fees) internal pure returns (bytes32) {
        return keccak256(
            abi.encode(
                keccak256(bytes(string.concat("Result(Verdict verdict,Fee[] fees)Fee(address to,uint256 amount)", VERDICT_TYPE))),
                _verdictHash(v),
                _feesHash(fees)
            )
        );
    }

    function _mergedHash(RaceV2Base.Verdict memory v, uint256 weight) internal pure returns (bytes32) {
        return keccak256(
            abi.encode(keccak256(bytes(string.concat("Merged(Verdict verdict,uint256 weight)", VERDICT_TYPE))), _verdictHash(v), weight)
        );
    }

    // ---------- verdicts v2 (task 5.2, S11) ----------

    /// The bounty's repository (0 outside the head registry).
    function _repoOf(Race race, uint256 b) internal view returns (bytes32) {
        return race.issue(race.bounty(b).issue).repo;
    }

    /// The base a judge checks on: the recorded head in the registry, a placeholder upstream commit outside it.
    function _headOf(Race race, bytes32 repo) internal view returns (bytes32) {
        return repo == bytes32(0) ? bytes32(bytes20(keccak256("an upstream base"))) : race.heads().head(repo).commit;
    }

    /// An issue-tier verdict on submission `id` of bounty `b`, checked on the current head, with a receipt hash.
    function _verdict(Race race, uint256 b, uint256 id, RaceV2Base.Outcome outcome, bytes32 fix)
        internal
        returns (RaceV2Base.Verdict memory v)
    {
        bytes32 repo = _repoOf(race, b);
        v = RaceV2Base.Verdict(
            repo,
            _headOf(race, repo),
            fix,
            b,
            id,
            TIER_ISSUE,
            uint8(outcome),
            keccak256(abi.encode("receipt", b, id, fix)),
            race.submission(id).seed, // the draw's seed, fixed at the commit (5.3)
            _nonce()
        );
    }

    /// A copy (memory structs assign by reference).
    function _copy(RaceV2Base.Verdict memory v) internal pure returns (RaceV2Base.Verdict memory) {
        return abi.decode(abi.encode(v), (RaceV2Base.Verdict));
    }

    /// The quorum's signatures on a struct hash: the version's quorum of the whole set.
    function _sigs(Race race, bytes32 structHash) internal view returns (bytes[] memory) {
        return _signed(race, structHash, bytes32(0)).sigs;
    }

    /// The issue tier's signatures on a verdict's action (5.3): ISSUE_QUORUM of the judges drawn with the verdict's
    /// seed for its bounty and submission, in address order.
    function _drawnSigs(Race race, RaceV2Base.Verdict memory v, bytes32 structHash)
        internal
        view
        returns (bytes[] memory)
    {
        (address[] memory judges,) = race.verdicts().drawn(v.seed, v.bounty, v.submission, address(race));
        return _signWith(race, structHash, bytes32(0), _drawnSecrets(judges, race.verdicts().ISSUE_QUORUM())).sigs;
    }

    /// The secrets of the first `k` of `judges` in address order.
    function _drawnSecrets(address[] memory judges, uint256 k) internal view returns (uint256[] memory out) {
        out = new uint256[](k);
        uint256 n;
        for (uint256 i; i < oracleSet.length && n < k; ++i) {
            for (uint256 j; j < judges.length; ++j) {
                if (judges[j] == oracleSet[i]) out[n++] = oracleSecrets[i];
            }
        }
        require(n == k, "too few judges drawn");
    }

    function _appealHash(uint256 id, uint256 bounty, bool cleared, RaceV2Base.Fee[] memory jurors, bytes32 nonce)
        internal
        pure
        returns (bytes32)
    {
        return keccak256(
            abi.encode(
                keccak256(
                    "AppealResult(uint256 appeal,uint256 bounty,bool cleared,Fee[] jurors,bytes32 nonce)Fee(address to,uint256 amount)"
                ),
                id,
                bounty,
                cleared,
                _feesHash(jurors),
                nonce
            )
        );
    }

    function _upheldHash(uint256 b, uint256 epoch, bytes32 nonce) internal pure returns (bytes32) {
        return keccak256(abi.encode(keccak256("ChallengeUpheld(uint256 bounty,uint256 epoch,bytes32 nonce)"), b, epoch, nonce));
    }

    // ---------- signing ----------

    /// Signatures from the given keys, in the given order.
    function _signWith(Race race, bytes32 structHash, bytes32 nonce, uint256[] memory secrets)
        internal
        view
        returns (RaceV2Base.Signed memory a)
    {
        bytes32 digest = _digest(race, structHash);
        a.nonce = nonce;
        a.sigs = new bytes[](secrets.length);
        for (uint256 i; i < secrets.length; ++i) {
            (uint8 v, bytes32 r, bytes32 s) = vm.sign(secrets[i], digest);
            a.sigs[i] = abi.encodePacked(r, s, v);
        }
    }

    /// The quorum's signatures: the first oracleQuorum keys, in address order.
    function _signed(Race race, bytes32 structHash, bytes32 nonce) internal view returns (RaceV2Base.Signed memory) {
        uint256[] memory secrets = new uint256[](oracleQuorum);
        for (uint256 i; i < oracleQuorum; ++i) {
            secrets[i] = oracleSecrets[i];
        }
        return _signWith(race, structHash, nonce, secrets);
    }

    // ---------- signed actions (the relayer is whoever calls) ----------

    function _signAccept(Race race, uint256 issue) internal returns (RaceV2Base.Signed memory) {
        return _signAccept(race, issue, 0);
    }

    function _signAccept(Race race, uint256 issue, uint256 weight) internal returns (RaceV2Base.Signed memory) {
        bytes32 n = _nonce();
        return _signed(race, _acceptHash(issue, weight, n), n);
    }

    function _signResult(Race race, uint256 id, RaceV2Base.Outcome outcome, bytes32 fix, RaceV2Base.Fee[] memory fees)
        internal
        returns (RaceV2Base.Verdict memory v, bytes[] memory sigs)
    {
        v = _verdict(race, race.submission(id).bounty, id, outcome, fix);
        sigs = _drawnSigs(race, v, _resultHash(v, fees));
    }

    function _signMerged(Race race, uint256 b) internal returns (RaceV2Base.Verdict memory v, bytes[] memory sigs) {
        return _signMerged(race, b, 0);
    }

    /// The merge of bounty b's winner, checked on the current head: its fix as the result recorded it.
    function _signMerged(Race race, uint256 b, uint256 weight)
        internal
        returns (RaceV2Base.Verdict memory v, bytes[] memory sigs)
    {
        uint256 w = race.bounty(b).winner;
        v = _verdict(race, b, w, RaceV2Base.Outcome.Pass, race.submission(w).fix);
        sigs = _drawnSigs(race, v, _mergedHash(v, weight));
    }

    function _signUpheld(Race race, uint256 b) internal returns (RaceV2Base.Signed memory) {
        bytes32 n = _nonce();
        return _signed(race, _upheldHash(b, race.bounty(b).epoch, n), n);
    }

    function _accept(Race race, uint256 issue) internal returns (uint256) {
        return _accept(race, issue, 0);
    }

    function _accept(Race race, uint256 issue, uint256 weight) internal returns (uint256) {
        return race.accept(issue, weight, _signAccept(race, issue, weight));
    }

    function _refuseSimilar(Race race, uint256 issue, uint256 open) internal {
        bytes32 n = _nonce();
        race.refuseSimilar(issue, open, _signed(race, _refuseHash(issue, open, n), n));
    }

    function _junk(Race race, uint256 issue) internal {
        bytes32 n = _nonce();
        race.junk(issue, _signed(race, _junkHash(issue, n), n));
    }

    function _result(Race race, uint256 id, RaceV2Base.Outcome outcome, bytes32 fix, RaceV2Base.Fee[] memory fees) internal {
        (RaceV2Base.Verdict memory v, bytes[] memory sigs) = _signResult(race, id, outcome, fix, fees);
        race.result(v, fees, sigs);
    }

    function _appealResult(Race race, uint256 id, uint256 bounty, bool cleared, RaceV2Base.Fee[] memory jurors) internal {
        bytes32 n = _nonce();
        race.appealResult(id, cleared, jurors, _signed(race, _appealHash(id, bounty, cleared, jurors, n), n));
    }

    function _merged(Race race, uint256 b) internal {
        _merged(race, b, 0);
    }

    function _merged(Race race, uint256 b, uint256 weight) internal {
        (RaceV2Base.Verdict memory v, bytes[] memory sigs) = _signMerged(race, b, weight);
        race.merged(v, weight, sigs);
    }

    function _challengeUpheld(Race race, uint256 b) internal {
        RaceV2Base.Signed memory a = _signUpheld(race, b);
        race.challengeUpheld(b, race.bounty(b).epoch, a);
    }
}
