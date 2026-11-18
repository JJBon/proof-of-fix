// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {Test} from "forge-std/Test.sol";
import {Race} from "../../src/Race.sol";
import {Token} from "../../src/Token.sol";

/// Task 3.1 (design D3): the oracle quorum, as test keys. Every result is signed here over its EIP-712 digest, hashed
/// independently of the contract's own constants (the type strings are spelled out again), so a drift between the
/// two fails the tests. Signatures go in signer-address order, as the contract requires.
abstract contract Oracles is Test {
    uint256[] internal oracleSecrets; // sorted by address
    address[] internal oracleSet;
    uint256 internal oracleQuorum;
    uint256 internal nonces;

    // The token each Race is deployed with (D15): pof's TOKENS (pof/params.py), the founder a test address.
    address internal founder = address(0xF0F0);
    uint256 internal tokenEmission = 10_000e6;
    uint256 internal tokenDecayBps = 100;
    uint256 internal founderBps = 100;
    uint256 internal founderPeriods = 208;
    uint256 internal reporterBps = 1_500;
    uint256 internal inflationPct = 300;
    uint256 internal graceDays = 7;

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

    function _newRace(Race.Config memory c, address[] memory feeCoins, uint256 bountyCap, uint256 totalCap)
        internal
        returns (Race)
    {
        return _newRace(c, feeCoins, bountyCap, totalCap, Token(address(0)));
    }

    /// A Race whose token continues `previous` (D15's migration), or the first version if none.
    function _newRace(
        Race.Config memory c,
        address[] memory feeCoins,
        uint256 bountyCap,
        uint256 totalCap,
        Token previous
    ) internal returns (Race) {
        return new Race(
            c, feeCoins, bountyCap, totalCap, oracleSet, oracleQuorum, _newToken(c.releaseEveryDays, previous)
        );
    }

    function _newToken(uint256 periodDays) internal returns (Token) {
        return _newToken(periodDays, Token(address(0)));
    }

    /// The token for the Race this contract deploys next: its recorder is that Race's address, known in advance
    /// (the next CREATE after this one). Keyless: nothing links them later.
    function _newToken(uint256 periodDays, Token previous) internal returns (Token) {
        address next = vm.computeCreateAddress(address(this), vm.getNonce(address(this)) + 1);
        return new Token(
            next, founder, tokenEmission, tokenDecayBps, founderBps, founderPeriods, reporterBps, periodDays, inflationPct,
            graceDays, previous
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
                keccak256("1"),
                block.chainid,
                address(race)
            )
        );
        return keccak256(abi.encodePacked("\x19\x01", domain, structHash));
    }

    function _feesHash(Race.Fee[] memory fees) internal pure returns (bytes32) {
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

    function _resultHash(
        uint256 id,
        uint256 bounty,
        Race.Outcome outcome,
        bytes32 fix,
        Race.Fee[] memory fees,
        bytes32 nonce
    ) internal pure returns (bytes32) {
        return keccak256(
            abi.encode(
                keccak256(
                    "Result(uint256 submission,uint256 bounty,uint8 outcome,bytes32 fix,Fee[] fees,bytes32 nonce)Fee(address to,uint256 amount)"
                ),
                id,
                bounty,
                uint8(outcome),
                fix,
                _feesHash(fees),
                nonce
            )
        );
    }

    function _appealHash(uint256 id, uint256 bounty, bool cleared, Race.Fee[] memory jurors, bytes32 nonce)
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

    function _mergedHash(uint256 b, uint256 winner, bytes32 nonce) internal pure returns (bytes32) {
        return _mergedHash(b, winner, 0, nonce);
    }

    function _mergedHash(uint256 b, uint256 winner, uint256 weight, bytes32 nonce) internal pure returns (bytes32) {
        return keccak256(
            abi.encode(
                keccak256("Merged(uint256 bounty,uint256 submission,uint256 weight,bytes32 nonce)"), b, winner, weight, nonce
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
        returns (Race.Signed memory a)
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
    function _signed(Race race, bytes32 structHash, bytes32 nonce) internal view returns (Race.Signed memory) {
        uint256[] memory secrets = new uint256[](oracleQuorum);
        for (uint256 i; i < oracleQuorum; ++i) {
            secrets[i] = oracleSecrets[i];
        }
        return _signWith(race, structHash, nonce, secrets);
    }

    // ---------- signed actions (the relayer is whoever calls) ----------

    function _signAccept(Race race, uint256 issue) internal returns (Race.Signed memory) {
        return _signAccept(race, issue, 0);
    }

    function _signAccept(Race race, uint256 issue, uint256 weight) internal returns (Race.Signed memory) {
        bytes32 n = _nonce();
        return _signed(race, _acceptHash(issue, weight, n), n);
    }

    function _signResult(Race race, uint256 id, Race.Outcome outcome, bytes32 fix, Race.Fee[] memory fees)
        internal
        returns (Race.Signed memory)
    {
        bytes32 n = _nonce();
        return _signed(race, _resultHash(id, race.submission(id).bounty, outcome, fix, fees, n), n);
    }

    function _signMerged(Race race, uint256 b) internal returns (Race.Signed memory) {
        return _signMerged(race, b, 0);
    }

    function _signMerged(Race race, uint256 b, uint256 weight) internal returns (Race.Signed memory) {
        bytes32 n = _nonce();
        return _signed(race, _mergedHash(b, race.bounty(b).winner, weight, n), n);
    }

    function _signUpheld(Race race, uint256 b) internal returns (Race.Signed memory) {
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

    function _result(Race race, uint256 id, Race.Outcome outcome, bytes32 fix, Race.Fee[] memory fees) internal {
        Race.Signed memory a = _signResult(race, id, outcome, fix, fees);
        race.result(id, outcome, fix, fees, a);
    }

    function _appealResult(Race race, uint256 id, uint256 bounty, bool cleared, Race.Fee[] memory jurors) internal {
        bytes32 n = _nonce();
        race.appealResult(id, cleared, jurors, _signed(race, _appealHash(id, bounty, cleared, jurors, n), n));
    }

    function _merged(Race race, uint256 b) internal {
        _merged(race, b, 0);
    }

    function _merged(Race race, uint256 b, uint256 weight) internal {
        Race.Signed memory a = _signMerged(race, b, weight);
        race.merged(b, race.bounty(b).winner, weight, a);
    }

    function _challengeUpheld(Race race, uint256 b) internal {
        Race.Signed memory a = _signUpheld(race, b);
        race.challengeUpheld(b, race.bounty(b).epoch, a);
    }
}
