// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

import {OraclesV2} from "./helpers/OraclesV2.sol";
import {Verdicts} from "../../src/v2/Verdicts.sol";
import {genesis, TEST_IMAGE, NITRO} from "./helpers/GenesisV2.sol";

/// proof-of-fix#85 task 5.4 (design S13; constitution Article 3): seats, keys and the provider cap. A version of 7
/// seats with 6 filled and 1 vacant (#104's join flow), quorum 5. Spec scenarios (oracle-network delta): "An enclave
/// redeployed", "A key from an unlisted image", "A lost key", "A third seat on one provider", "An attestation of an
/// unlisted type"; and the join flow: a vacant seat filled once, by its new key and 5 other seats, after the delay.
/// The ABI listing (no function adds or replaces an operator) is SplitV2Test.test_verdictsHaveNoPrivilegedCall.
contract SeatsV2Test is OraclesV2 {
    Verdicts verdicts;
    uint256 constant VACANT = 6;
    address engineerAccount = makeAddr("engineer's disclosed account");
    address engineer;
    uint256 engineerSecret;
    uint256 nonceCount;

    event KeyPublished(
        uint256 indexed seat,
        address indexed key,
        bytes32 image,
        bytes32 attestationType,
        bytes32 attestation,
        uint256 effectiveAt
    );
    event KeyActivated(uint256 indexed seat, address indexed oldKey, address indexed newKey);
    event SuspensionPublished(uint256 indexed seat, uint256 effectiveAt);
    event SeatResumed(uint256 indexed seat);

    function setUp() public {
        _makeOracles(6, 5);
        (engineer, engineerSecret) = makeAddrAndKey("the engineer's enclave key");
        verdicts = new Verdicts(_genesis());
    }

    /// 6 filled seats (oracleSet, in seat order) and the vacant seat 6, whose operator (the engineer) is disclosed at
    /// genesis with its family and provider.
    function _genesis() internal view returns (Verdicts.Genesis memory g) {
        address[] memory keys = new address[](7);
        for (uint256 i; i < 6; ++i) {
            keys[i] = oracleSet[i];
        }
        g = genesis(keys, 5, new address[](0), new address[](0));
        g.operators = new address[](1);
        g.operatorSeats = new uint256[](1);
        g.operators[0] = engineerAccount;
        g.operatorSeats[0] = VACANT;
    }

    /// The draws below ask this test, as the consumer, who takes part: nobody.
    function isParty(uint256, uint256, address) external pure returns (bool) {
        return false;
    }

    function _nonce2() internal returns (bytes32) {
        return keccak256(abi.encode("seat action", ++nonceCount));
    }

    /// Signatures over `digest` by `secrets`, in increasing signer order.
    function _sign(bytes32 digest, uint256[] memory secrets) internal pure returns (bytes[] memory sigs) {
        uint256 n = secrets.length;
        address[] memory who = new address[](n);
        for (uint256 i; i < n; ++i) {
            who[i] = vm.addr(secrets[i]);
        }
        for (uint256 i = 1; i < n; ++i) {
            for (uint256 j = i; j > 0 && who[j - 1] > who[j]; --j) {
                (who[j - 1], who[j]) = (who[j], who[j - 1]);
                (secrets[j - 1], secrets[j]) = (secrets[j], secrets[j - 1]);
            }
        }
        sigs = new bytes[](n);
        for (uint256 i; i < n; ++i) {
            (uint8 v, bytes32 r, bytes32 s) = vm.sign(secrets[i], digest);
            sigs[i] = abi.encodePacked(r, s, v);
        }
    }

    /// The secrets of the filled seats in `seats`, plus `extra` (0: none).
    function _secrets(uint256[] memory seats, uint256 extra) internal view returns (uint256[] memory out) {
        out = new uint256[](seats.length + (extra == 0 ? 0 : 1));
        for (uint256 i; i < seats.length; ++i) {
            out[i] = oracleSecrets[seats[i]];
        }
        if (extra != 0) out[seats.length] = extra;
    }

    function _range(uint256 from, uint256 count) internal pure returns (uint256[] memory r) {
        r = new uint256[](count);
        for (uint256 i; i < count; ++i) {
            r[i] = from + i;
        }
    }

    function _rotate(uint256 seat, address key, bytes32 image, bytes32 kind, bytes32 att, uint256[] memory signers)
        internal
    {
        bytes32 nonce = _nonce2();
        bytes32 digest = verdicts.rotateDigest(seat, key, image, kind, att, nonce);
        verdicts.rotate(seat, key, image, kind, att, nonce, _sign(digest, signers));
    }

    // ---------- genesis ----------

    function test_genesisSeats() public view {
        assertEq(verdicts.seatCount(), 7);
        assertEq(verdicts.keys().length, 6); // the vacant seat neither draws nor counts
        assertFalse(verdicts.isActive(VACANT));
        assertEq(verdicts.seat(VACANT).key, address(0));
        assertEq(verdicts.seat(VACANT).family, keccak256(abi.encode("family", VACANT)));
        assertEq(verdicts.operatorsOfSeat(VACANT)[0], engineerAccount);
        assertEq(verdicts.seatOf(engineerAccount), address(0));
        assertEq(verdicts.KEY_ROTATION_DELAY(), 7 days);
        assertEq(verdicts.PROVIDER_SEAT_CAP(), 2);
        assertTrue(verdicts.allowedImage(TEST_IMAGE));
        assertTrue(verdicts.acceptedType(NITRO));
        for (uint256 i; i < 40; ++i) {
            (address[] memory judges,) = verdicts.drawn(keccak256(abi.encode(i)), 0, 0, address(this));
            for (uint256 j; j < judges.length; ++j) {
                assertTrue(judges[j] != address(0));
            }
        }
    }

    /// Scenario "A third seat on one provider": the deployment is refused; two are fine.
    function test_aThirdSeatOnOneProviderIsRefused() public {
        Verdicts.Genesis memory g = _genesis();
        g.providers[1] = g.providers[0];
        new Verdicts(g); // two on one provider
        g.providers[2] = g.providers[0];
        vm.expectRevert(Verdicts.BadOracleSet.selector);
        new Verdicts(g);
    }

    /// Article 3: a different model family per seat; and every seat names its family and provider.
    function test_familiesAreDistinctAndNamed() public {
        Verdicts.Genesis memory g = _genesis();
        g.families[3] = g.families[0];
        vm.expectRevert(Verdicts.BadOracleSet.selector);
        new Verdicts(g);
        g = _genesis();
        g.providers[4] = bytes32(0);
        vm.expectRevert(Verdicts.BadOracleSet.selector);
        new Verdicts(g);
    }

    /// The version can act and fill its vacancies: at least the quorum of seats filled at genesis; and the lists are
    /// set.
    function test_genesisNeedsTheQuorumFilledAndTheLists() public {
        Verdicts.Genesis memory g = _genesis();
        g.keys[5] = address(0); // 5 filled of 7: still the quorum
        new Verdicts(g);
        g.keys[4] = address(0); // 4 filled: below it
        vm.expectRevert(Verdicts.BadOracleSet.selector);
        new Verdicts(g);
        g = _genesis();
        g.images = new bytes32[](0);
        vm.expectRevert(Verdicts.BadOracleSet.selector);
        new Verdicts(g);
        g = _genesis();
        g.attestationTypes = new bytes32[](0);
        vm.expectRevert(Verdicts.BadOracleSet.selector);
        new Verdicts(g);
    }

    // ---------- the join flow (#104) ----------

    /// A vacant seat is filled by its new key and 5 of the other seats, after the delay: then it draws and counts,
    /// and its operator (disclosed at genesis) is the new key's.
    function test_aVacantSeatJoins() public {
        bytes32 nonce = _nonce2();
        bytes32 digest = verdicts.rotateDigest(VACANT, engineer, TEST_IMAGE, NITRO, keccak256("quote"), nonce);
        vm.expectEmit(true, true, false, true);
        emit KeyPublished(VACANT, engineer, TEST_IMAGE, NITRO, keccak256("quote"), block.timestamp + 7 days);
        verdicts.rotate(
            VACANT, engineer, TEST_IMAGE, NITRO, keccak256("quote"), nonce, _sign(digest, _secrets(_range(0, 5), engineerSecret))
        );
        (address pk,,,, uint64 at) = verdicts.pending(VACANT);
        assertEq(pk, engineer);
        assertEq(at, block.timestamp + 7 days);
        assertFalse(verdicts.isOracle(engineer)); // not before the delay
        vm.expectRevert(Verdicts.TooEarly.selector);
        verdicts.activate(VACANT);

        vm.warp(block.timestamp + 7 days);
        vm.expectEmit(true, true, true, true);
        emit KeyActivated(VACANT, address(0), engineer);
        verdicts.activate(VACANT); // anyone
        assertTrue(verdicts.isOracle(engineer));
        assertEq(verdicts.keys().length, 7);
        assertEq(verdicts.seat(VACANT).key, engineer);
        assertEq(verdicts.seat(VACANT).image, TEST_IMAGE);
        assertEq(verdicts.seat(VACANT).attestation, keccak256("quote"));
        assertEq(verdicts.seatOf(engineerAccount), engineer);
        assertEq(verdicts.operatorsOf(engineer)[0], engineerAccount);
        bool drawn;
        for (uint256 i; i < 40 && !drawn; ++i) {
            (address[] memory judges,) = verdicts.drawn(keccak256(abi.encode(i)), 0, 0, address(this));
            for (uint256 j; j < judges.length; ++j) {
                drawn = drawn || judges[j] == engineer;
            }
        }
        assertTrue(drawn);
        vm.expectRevert(Verdicts.NothingPending.selector);
        verdicts.activate(VACANT);
    }

    /// The new key signs too (it can't be someone else's key), and the quorum of the other seats.
    function test_aJoinNeedsTheNewKeyAndFiveOthers() public {
        bytes32 nonce = _nonce2();
        bytes32 digest = verdicts.rotateDigest(VACANT, engineer, TEST_IMAGE, NITRO, keccak256("quote"), nonce);
        vm.expectRevert(Verdicts.MissingSigner.selector);
        verdicts.rotate(VACANT, engineer, TEST_IMAGE, NITRO, keccak256("quote"), nonce, _sign(digest, _secrets(_range(0, 6), 0)));
        vm.expectRevert(Verdicts.TooFewSignatures.selector);
        verdicts.rotate(
            VACANT, engineer, TEST_IMAGE, NITRO, keccak256("quote"), nonce, _sign(digest, _secrets(_range(0, 4), engineerSecret))
        );
        (, uint256 outsider) = makeAddrAndKey("not a seat");
        uint256[] memory s = _secrets(_range(0, 5), engineerSecret);
        uint256[] memory withOutsider = new uint256[](s.length + 1);
        for (uint256 i; i < s.length; ++i) {
            withOutsider[i] = s[i];
        }
        withOutsider[s.length] = outsider;
        vm.expectRevert(Verdicts.NotOracle.selector);
        verdicts.rotate(VACANT, engineer, TEST_IMAGE, NITRO, keccak256("quote"), nonce, _sign(digest, withOutsider));
    }

    /// On a devnet version that accepts NO_ATTESTATION, a key joins without a quote; any other type needs its hash.
    function test_noAttestationOnlyWhereAccepted() public {
        _rotate(VACANT, engineer, TEST_IMAGE, keccak256("none"), bytes32(0), _secrets(_range(0, 5), engineerSecret));
        Verdicts.Genesis memory g = _genesis();
        g.attestationTypes = new bytes32[](1);
        g.attestationTypes[0] = NITRO; // a public version's list never holds "none"
        verdicts = new Verdicts(g);
        bytes32 nonce = _nonce2();
        bytes32 digest = verdicts.rotateDigest(VACANT, engineer, TEST_IMAGE, keccak256("none"), bytes32(0), nonce);
        bytes[] memory sigs = _sign(digest, _secrets(_range(0, 5), engineerSecret));
        vm.expectRevert(Verdicts.AttestationNotAccepted.selector);
        verdicts.rotate(VACANT, engineer, TEST_IMAGE, keccak256("none"), bytes32(0), nonce, sigs);
        vm.expectRevert(Verdicts.AttestationNotAccepted.selector);
        verdicts.rotate(VACANT, engineer, TEST_IMAGE, NITRO, bytes32(0), nonce, sigs); // a TEE type needs its hash
    }

    // ---------- rotation (S13) ----------

    /// Scenario "An enclave redeployed": a new key, attested for an allowed image, co-signed by the seat's current key
    /// and 5 others, replaces the old key after the delay; the attestation's hash is recorded.
    function test_anEnclaveRedeployed() public {
        (address fresh, uint256 freshSecret) = makeAddrAndKey("seat 0's new enclave");
        address old = oracleSet[0];
        uint256[] memory signers = _secrets(_range(0, 6), freshSecret); // seat 0's key and seats 1-5, and the new key
        _rotate(0, fresh, TEST_IMAGE, NITRO, keccak256("new quote"), signers);
        assertTrue(verdicts.isOracle(old)); // the old key serves until the delay
        vm.warp(block.timestamp + 7 days);
        verdicts.activate(0);
        assertFalse(verdicts.isOracle(old));
        assertTrue(verdicts.isOracle(fresh));
        assertEq(verdicts.seat(0).attestation, keccak256("new quote"));
        assertEq(verdicts.keys().length, 6);
    }

    /// The seat's current key must co-sign: the others alone can't hand a seat to a new key.
    function test_aRotationNeedsTheCurrentKey() public {
        (address fresh, uint256 freshSecret) = makeAddrAndKey("seat 0's new enclave");
        bytes32 nonce = _nonce2();
        bytes32 digest = verdicts.rotateDigest(0, fresh, TEST_IMAGE, NITRO, keccak256("q"), nonce);
        vm.expectRevert(Verdicts.MissingSigner.selector);
        verdicts.rotate(0, fresh, TEST_IMAGE, NITRO, keccak256("q"), nonce, _sign(digest, _secrets(_range(1, 5), freshSecret)));
    }

    /// Scenario "A key from an unlisted image": refused, whoever co-signs. Scenario "An attestation of an unlisted
    /// type": the key isn't registered, whoever co-signs.
    function test_unlistedImageOrTypeIsRefused() public {
        (address fresh, uint256 freshSecret) = makeAddrAndKey("seat 0's new enclave");
        uint256[] memory everyone = _secrets(_range(0, 6), freshSecret);
        bytes32 nonce = _nonce2();
        bytes32 bad = keccak256("an unofficial checker");
        bytes32 digest = verdicts.rotateDigest(0, fresh, bad, NITRO, keccak256("q"), nonce);
        vm.expectRevert(Verdicts.ImageNotAllowed.selector);
        verdicts.rotate(0, fresh, bad, NITRO, keccak256("q"), nonce, _sign(digest, everyone));
        bytes32 sgx = keccak256("intel-sgx");
        digest = verdicts.rotateDigest(0, fresh, TEST_IMAGE, sgx, keccak256("q"), nonce);
        vm.expectRevert(Verdicts.AttestationNotAccepted.selector);
        verdicts.rotate(0, fresh, TEST_IMAGE, sgx, keccak256("q"), nonce, _sign(digest, everyone));
    }

    /// A key serves one seat, once; one pending key per seat.
    function test_aKeyServesOneSeatAndOnePendingAtATime() public {
        bytes32 nonce = _nonce2();
        bytes32 digest = verdicts.rotateDigest(VACANT, oracleSet[1], TEST_IMAGE, NITRO, keccak256("q"), nonce);
        vm.expectRevert(Verdicts.KeyTaken.selector);
        verdicts.rotate(VACANT, oracleSet[1], TEST_IMAGE, NITRO, keccak256("q"), nonce, _sign(digest, _secrets(_range(0, 6), 0)));
        _rotate(VACANT, engineer, TEST_IMAGE, NITRO, keccak256("q"), _secrets(_range(0, 5), engineerSecret));
        // the pending key can't be published for another seat
        nonce = _nonce2();
        digest = verdicts.rotateDigest(0, engineer, TEST_IMAGE, NITRO, keccak256("q"), nonce);
        vm.expectRevert(Verdicts.KeyTaken.selector);
        verdicts.rotate(0, engineer, TEST_IMAGE, NITRO, keccak256("q"), nonce, _sign(digest, _secrets(_range(0, 6), engineerSecret)));
        (address other, uint256 otherSecret) = makeAddrAndKey("someone else");
        nonce = _nonce2();
        digest = verdicts.rotateDigest(VACANT, other, TEST_IMAGE, NITRO, keccak256("q"), nonce);
        vm.expectRevert(Verdicts.AlreadyPending.selector);
        verdicts.rotate(VACANT, other, TEST_IMAGE, NITRO, keccak256("q"), nonce, _sign(digest, _secrets(_range(0, 5), otherSecret)));
    }

    // ---------- suspension (S13) ----------

    /// Scenario "A lost key": the other seats publish the suspension; after the delay the seat neither draws nor
    /// counts, the issue tier draws from the rest, and the seat can't rotate (its key can't co-sign).
    function test_aLostKeyIsSuspended() public {
        uint256 lost = 2;
        uint256[] memory others = new uint256[](5);
        uint256 m;
        for (uint256 i; i < 6; ++i) {
            if (i != lost) others[m++] = i;
        }
        bytes32 nonce = _nonce2();
        bytes32 digest = verdicts.suspendDigest(lost, nonce);
        vm.expectEmit(true, false, false, true);
        emit SuspensionPublished(lost, block.timestamp + 7 days);
        verdicts.suspend(lost, nonce, _sign(digest, _secrets(others, 0)));
        assertTrue(verdicts.isActive(lost)); // not before the delay
        vm.warp(block.timestamp + 7 days);
        assertFalse(verdicts.isActive(lost));
        assertFalse(verdicts.isOracle(oracleSet[lost]));
        assertEq(verdicts.keys().length, 5);
        for (uint256 i; i < 40; ++i) {
            (address[] memory judges,) = verdicts.drawn(keccak256(abi.encode(i)), 0, 0, address(this));
            assertEq(judges.length, 3);
            for (uint256 j; j < judges.length; ++j) {
                assertTrue(judges[j] != oracleSet[lost]);
            }
        }
        // a suspended key doesn't count toward a quorum
        bytes32 d = keccak256("an action");
        vm.expectRevert(Verdicts.NotOracle.selector);
        verdicts.authorize(d, _sign(d, _secrets(_range(0, 5), 0)));
        // its operator can't be replaced: without its key, no rotation
        (address fresh, uint256 freshSecret) = makeAddrAndKey("a replacement");
        nonce = _nonce2();
        digest = verdicts.rotateDigest(lost, fresh, TEST_IMAGE, NITRO, keccak256("q"), nonce);
        vm.expectRevert(Verdicts.MissingSigner.selector);
        verdicts.rotate(lost, fresh, TEST_IMAGE, NITRO, keccak256("q"), nonce, _sign(digest, _secrets(others, freshSecret)));
    }

    /// A seat that can still sign can't be kept out: its own key lifts a published or effective suspension.
    function test_aSeatThatCanSignLiftsItsSuspension() public {
        uint256 target = 1;
        uint256[] memory others = new uint256[](5);
        uint256 m;
        for (uint256 i; i < 6; ++i) {
            if (i != target) others[m++] = i;
        }
        bytes32 nonce = _nonce2();
        verdicts.suspend(target, nonce, _sign(verdicts.suspendDigest(target, nonce), _secrets(others, 0)));
        vm.warp(block.timestamp + 7 days);
        assertFalse(verdicts.isActive(target));
        nonce = _nonce2();
        bytes32 digest = verdicts.resumeDigest(target, nonce);
        uint256[] memory notItself = new uint256[](1);
        notItself[0] = oracleSecrets[0];
        vm.expectRevert(Verdicts.MissingSigner.selector);
        verdicts.resume(target, nonce, _sign(digest, notItself)[0]);
        uint256[] memory itself = new uint256[](1);
        itself[0] = oracleSecrets[target];
        vm.expectEmit(true, false, false, false);
        emit SeatResumed(target);
        verdicts.resume(target, nonce, _sign(digest, itself)[0]);
        assertTrue(verdicts.isActive(target));
        vm.expectRevert(Verdicts.NothingPending.selector);
        verdicts.resume(target, nonce, _sign(digest, itself)[0]);
    }

    /// A suspension needs the quorum of the other seats; the seat's own key isn't one of them; a vacant seat has
    /// nothing to suspend; a spent digest can't be replayed.
    function test_aSuspensionNeedsFiveOthers() public {
        bytes32 nonce = _nonce2();
        bytes32 digest = verdicts.suspendDigest(0, nonce);
        vm.expectRevert(Verdicts.TooFewSignatures.selector);
        verdicts.suspend(0, nonce, _sign(digest, _secrets(_range(1, 4), 0)));
        vm.expectRevert(Verdicts.NotOracle.selector);
        verdicts.suspend(0, nonce, _sign(digest, _secrets(_range(0, 5), 0)));
        nonce = _nonce2();
        bytes[] memory vacantSigs = _sign(verdicts.suspendDigest(VACANT, nonce), _secrets(_range(0, 5), 0));
        vm.expectRevert(Verdicts.SeatVacant.selector);
        verdicts.suspend(VACANT, nonce, vacantSigs);
        nonce = _nonce2();
        digest = verdicts.suspendDigest(0, nonce);
        bytes[] memory sigs = _sign(digest, _secrets(_range(1, 5), 0));
        verdicts.suspend(0, nonce, sigs);
        vm.expectRevert(Verdicts.AlreadyPending.selector);
        verdicts.suspend(0, nonce, sigs);
        uint256[] memory itself = new uint256[](1);
        itself[0] = oracleSecrets[0];
        bytes32 r = _nonce2();
        verdicts.resume(0, r, _sign(verdicts.resumeDigest(0, r), itself)[0]);
        vm.expectRevert(Verdicts.Replayed.selector);
        verdicts.suspend(0, nonce, sigs);
    }
}
