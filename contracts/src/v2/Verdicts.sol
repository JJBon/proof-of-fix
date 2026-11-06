// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {MessageHashUtils} from "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";

/// Who takes part in a verdict's subject, asked of the contract that relays the verdict (task 5.3): RaceV2 answers for
/// a bounty and a submission (the issue's reporter, the submission's solver and the bounty's funders).
interface IParties {
    function isParty(uint256 bounty, uint256 submission, address account) external view returns (bool);
}

/// The verdicts' seats, keys, quorum and tiers for v2 (proof-of-fix#85, design S2, S10, S13): one contract that every
/// v2 contract asks. v1 kept the quorum check in the linked library OracleAuth on Race's own storage; v2 needs one key
/// set shared by several contracts, hence a contract.
///
/// Seats (task 5.4, S13; constitution Article 3): the version's seats are fixed at deployment, each with its model
/// family (distinct), its inference or TEE provider (at most PROVIDER_SEAT_CAP seats per provider) and its operators'
/// disclosed accounts. No function adds, removes or replaces a seat, an operator, a family or a provider: that is a new
/// version (D15). What can change is a seat's key, and only one way (`rotate`, then `activate`):
/// - the new key comes with an attestation of an accepted type showing a checker image on the allowed list (both
///   lists fixed at deployment: the constitution's Article 7, changed by a new version until ADRs reach the chain in
///   5.10), and the new key itself signs (it can't be someone else's key);
/// - the seat's current key co-signs, with the version's quorum of the other seats' active keys (5 of the other 6);
/// - it takes effect KEY_ROTATION_DELAY after it was published, with the attestation's hash, so anyone can check it.
/// A seat deployed vacant (its operator, family and provider fixed, no key) is filled by the same path, without a
/// current key to co-sign: the join flow (#104), once per seat, since a filled seat only rotates.
///
/// Suspension (S13): a seat that can't sign anymore can't rotate, so it's suspended: the quorum of the other seats
/// publishes the suspension, which takes effect after the same delay, and the seat's own key lifts it at any time by
/// signing (a seat that can still sign can't be kept out). A suspended seat isn't drawn and doesn't count.
///
/// Three ways to authorize a digest, all with v1's rules (D3): distinct active keys, in strictly increasing signer
/// order, each digest once per caller (the used digests are kept per caller, so a call only spends the caller's own;
/// each consumer builds its digest over its own EIP-712 domain, so a signature for one contract is useless on another):
/// - `authorize`: the version's quorum of the active keys, for the signed actions that aren't a fix's verdict;
/// - `authorizeDrawn`, the issue tier (S2): ISSUE_QUORUM of the ISSUE_JUDGES keys drawn by the verdict's seed;
/// - `authorizeAll`, the constitution tier (S2): the quorum, from the keys that sit (all but the recused).
///
/// The draw is a Fisher-Yates shuffle of the active keys (in seat order) driven by the seed, walked in order: a key
/// whose operator is a party to the subject is recused, and the next key in the shuffle takes its seat (checking
/// delta: "the next judge in the draw takes its seat"). It's a view (`drawn`), so anyone recomputes it from the seed,
/// the seats and the parties.
///
/// Keyless: no owner, no admin, no function changing the seats, the counts, the operators or the lists.
///
/// Hooks for the later v2 tasks (not built here):
///   TODO(5.5) sealed verdicts: seals within SEAL_WINDOW, reveals within REVEAL_WINDOW.
///   TODO(5.8) bonds and provable faults (equivocation checked here); the bond-based suspension (`_bonded`).
///   TODO(5.10) a staked challenge during a rotation's delay; the allowed images and attestation types by ADR.
contract Verdicts {
    /// The issue tier (S2): 3 judges drawn from the seats, 2 to pass. Constants: no function changes them.
    uint256 public constant ISSUE_JUDGES = 3;
    uint256 public constant ISSUE_QUORUM = 2;
    /// S13: a key rotation, a seat's join and a suspension take effect a week after they're published.
    uint256 public constant KEY_ROTATION_DELAY = 7 days;
    /// S13: at most 2 seats per inference or TEE provider.
    uint256 public constant PROVIDER_SEAT_CAP = 2;
    /// The attestation type a devnet version may accept for keys with no attestation (rule 1: devnet only). A public
    /// version's list never holds it; then every key needs an attestation of a listed TEE type.
    bytes32 public constant NO_ATTESTATION = keccak256("none");

    bytes32 internal constant DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    bytes32 internal constant ROTATE_TYPEHASH = keccak256(
        "Rotate(uint256 seat,address key,bytes32 image,bytes32 attestationType,bytes32 attestation,bytes32 nonce)"
    );
    bytes32 internal constant SUSPEND_TYPEHASH = keccak256("Suspend(uint256 seat,bytes32 nonce)");
    bytes32 internal constant RESUME_TYPEHASH = keccak256("Resume(uint256 seat,bytes32 nonce)");

    /// A seat: its key (0 while vacant), its fixed family and provider, the checker image and attestation its key was
    /// registered with, and when a published suspension takes effect (0: none).
    struct Seat {
        address key;
        bytes32 family;
        bytes32 provider;
        bytes32 image;
        bytes32 attestation;
        uint64 suspendedFrom;
    }

    /// A key published for a seat, waiting for its delay.
    struct Rotation {
        address key;
        bytes32 image;
        bytes32 attestationType;
        bytes32 attestation;
        uint64 effectiveAt;
    }

    /// The deployment's seats and lists. `keys[i]` is seat i's key (0: vacant); `operators[j]` is a disclosed account
    /// of the operator of seat `operatorSeats[j]`.
    struct Genesis {
        address[] keys;
        bytes32[] families;
        bytes32[] providers;
        uint256 quorum;
        address[] operators;
        uint256[] operatorSeats;
        bytes32[] images;
        bytes32[] attestationTypes;
    }

    Seat[] internal _seats;
    /// The version's quorum (above half the seats): the constitution tier's threshold, a rotation's co-signers, and
    /// every other signed action's.
    uint256 public immutable quorum;
    mapping(address consumer => mapping(bytes32 digest => bool)) public used;
    mapping(uint256 seat => Rotation) public pending;
    /// The constitution's allowed checker images and accepted attestation types (Article 7, S14), fixed here.
    mapping(bytes32 image => bool) public allowedImage;
    mapping(bytes32 attestationType => bool) public acceptedType;
    /// seat + 1 for every key ever registered or published (a key serves one seat, once).
    mapping(address key => uint256) internal _seatOfKey;
    /// seat + 1 for an operator's disclosed account (one seat per account).
    mapping(address account => uint256) internal _seatOfAccount;
    mapping(uint256 seat => address[]) internal _operators;
    bytes32 internal immutable _domain;

    event Authorized(address indexed consumer, bytes32 indexed digest);
    event KeyRecused(address indexed consumer, bytes32 indexed digest, address key);
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

    error BadOracleSet();
    error NotOracle();
    error TooFewSignatures();
    error DuplicateSigner();
    error Replayed();
    error NotDrawn();
    error Recused();
    error UnknownSeat();
    error KeyTaken();
    error ImageNotAllowed();
    error AttestationNotAccepted();
    error MissingSigner();
    error AlreadyPending();
    error NothingPending();
    error TooEarly();
    error SeatVacant();

    /// A quorum above half the seats means two conflicting verdicts on the same thing can't both gather it; at least
    /// that many seats filled at genesis, so the version can act and fill its vacant seats; at least ISSUE_JUDGES seats.
    constructor(Genesis memory g) {
        uint256 n = g.keys.length;
        if (
            n < ISSUE_JUDGES || g.families.length != n || g.providers.length != n || g.quorum > n
                || 2 * g.quorum <= n || g.images.length == 0 || g.attestationTypes.length == 0
                || g.operators.length != g.operatorSeats.length
        ) revert BadOracleSet();
        for (uint256 i; i < g.images.length; ++i) {
            if (g.images[i] == bytes32(0)) revert BadOracleSet();
            allowedImage[g.images[i]] = true;
        }
        for (uint256 i; i < g.attestationTypes.length; ++i) {
            if (g.attestationTypes[i] == bytes32(0)) revert BadOracleSet();
            acceptedType[g.attestationTypes[i]] = true;
        }
        uint256 filled;
        for (uint256 i; i < n; ++i) {
            address k = g.keys[i];
            bytes32 family = g.families[i];
            bytes32 provider = g.providers[i];
            if (family == bytes32(0) || provider == bytes32(0)) revert BadOracleSet();
            uint256 sameProvider;
            for (uint256 j; j < i; ++j) {
                if (_seats[j].family == family) revert BadOracleSet(); // Article 3: a different family each
                if (_seats[j].provider == provider) ++sameProvider;
            }
            if (sameProvider >= PROVIDER_SEAT_CAP) revert BadOracleSet();
            if (k != address(0)) {
                if (_seatOfKey[k] != 0) revert BadOracleSet();
                _seatOfKey[k] = i + 1;
                ++filled;
            }
            _seats.push(Seat(k, family, provider, bytes32(0), bytes32(0), 0));
        }
        if (filled < g.quorum) revert BadOracleSet();
        quorum = g.quorum;
        for (uint256 j; j < g.operators.length; ++j) {
            address a = g.operators[j];
            uint256 s = g.operatorSeats[j];
            if (a == address(0) || s >= n || _seatOfAccount[a] != 0) revert BadOracleSet();
            _seatOfAccount[a] = s + 1;
            _operators[s].push(a);
        }
        _domain = keccak256(
            abi.encode(DOMAIN_TYPEHASH, keccak256("proof-of-fix Verdicts"), keccak256("2"), block.chainid, address(this))
        );
    }

    // ---------- views ----------

    function seatCount() external view returns (uint256) {
        return _seats.length;
    }

    function seat(uint256 i) external view returns (Seat memory) {
        if (i >= _seats.length) revert UnknownSeat();
        return _seats[i];
    }

    /// The active keys, in seat order: filled and not suspended (what draws and counts).
    function keys() public view returns (address[] memory out) {
        uint256 n = _seats.length;
        out = new address[](n);
        uint256 m;
        for (uint256 i; i < n; ++i) {
            if (_active(i)) out[m++] = _seats[i].key;
        }
        assembly ("memory-safe") {
            mstore(out, m)
        }
    }

    function isOracle(address key) public view returns (bool) {
        uint256 s = _seatOfKey[key];
        return s != 0 && _seats[s - 1].key == key && _active(s - 1);
    }

    function isActive(uint256 i) external view returns (bool) {
        if (i >= _seats.length) revert UnknownSeat();
        return _active(i);
    }

    /// The seat's key's operators' disclosed accounts (none for a key that isn't a seat's current key).
    function operatorsOf(address key) external view returns (address[] memory) {
        uint256 s = _seatOfKey[key];
        if (s == 0 || _seats[s - 1].key != key) return new address[](0);
        return _operators[s - 1];
    }

    function operatorsOfSeat(uint256 i) external view returns (address[] memory) {
        return _operators[i];
    }

    /// An operator's disclosed account's seat's current key (0 if it has none, or the seat is vacant).
    function seatOf(address account) external view returns (address) {
        uint256 s = _seatOfAccount[account];
        return s == 0 ? address(0) : _seats[s - 1].key;
    }

    function domainSeparator() public view returns (bytes32) {
        return _domain;
    }

    /// The digest a rotation's signers sign (the new key, the seat's current key, and the co-signing seats).
    function rotateDigest(
        uint256 i,
        address key,
        bytes32 image,
        bytes32 attestationType,
        bytes32 attestation,
        bytes32 nonce
    ) public view returns (bytes32) {
        return MessageHashUtils.toTypedDataHash(
            _domain, keccak256(abi.encode(ROTATE_TYPEHASH, i, key, image, attestationType, attestation, nonce))
        );
    }

    function suspendDigest(uint256 i, bytes32 nonce) public view returns (bytes32) {
        return MessageHashUtils.toTypedDataHash(_domain, keccak256(abi.encode(SUSPEND_TYPEHASH, i, nonce)));
    }

    function resumeDigest(uint256 i, bytes32 nonce) public view returns (bytes32) {
        return MessageHashUtils.toTypedDataHash(_domain, keccak256(abi.encode(RESUME_TYPEHASH, i, nonce)));
    }

    /// The issue tier's judges for a verdict with this seed, on `consumer`'s subject (`bounty`, `submission`): the first
    /// ISSUE_JUDGES active keys of the seeded shuffle whose operators aren't parties, and the keys recused on the way.
    function drawn(bytes32 seed, uint256 bounty, uint256 submission, address consumer)
        public
        view
        returns (address[] memory judges, address[] memory recused)
    {
        address[] memory active = keys();
        uint256 n = active.length;
        judges = new address[](ISSUE_JUDGES);
        recused = new address[](n);
        uint256 j;
        uint256 r;
        for (uint256 i; i < n && j < ISSUE_JUDGES; ++i) {
            uint256 pick = i + uint256(keccak256(abi.encode(seed, i))) % (n - i);
            (active[i], active[pick]) = (active[pick], active[i]);
            address k = active[i];
            if (_isParty(k, bounty, submission, consumer)) recused[r++] = k;
            else judges[j++] = k;
        }
        assembly ("memory-safe") {
            mstore(judges, j)
            mstore(recused, r)
        }
    }

    // ---------- the quorum and the tiers ----------

    /// The caller's digest, signed by the version's quorum of distinct active keys in strictly increasing signer
    /// order, not used by the caller before. It's marked used first: a revert in the caller's action undoes both.
    function authorize(bytes32 digest, bytes[] calldata sigs) external {
        _spend(msg.sender, digest);
        _check(digest, sigs, quorum, new address[](0), false, 0, 0, false);
    }

    /// The issue tier (S2): at least ISSUE_QUORUM of the judges `drawn` with `seed` for the caller's subject signed the
    /// caller's digest; a signature from a key that wasn't drawn (recused, or simply not drawn) is refused.
    function authorizeDrawn(bytes32 digest, bytes32 seed, uint256 bounty, uint256 submission, bytes[] calldata sigs)
        external
    {
        _spend(msg.sender, digest);
        (address[] memory judges, address[] memory recused) = drawn(seed, bounty, submission, msg.sender);
        _check(digest, sigs, ISSUE_QUORUM, judges, true, 0, 0, false);
        for (uint256 i; i < recused.length; ++i) {
            emit KeyRecused(msg.sender, digest, recused[i]);
        }
    }

    /// The constitution tier (S2): at least the quorum signed the caller's digest, from keys that sit; a key whose
    /// operator is a party to the caller's subject doesn't sit, and the threshold stays the quorum (5 of the 6 who
    /// sit, when the owner's seat is recused).
    function authorizeAll(bytes32 digest, uint256 bounty, uint256 submission, bytes[] calldata sigs) external {
        _spend(msg.sender, digest);
        _check(digest, sigs, quorum, new address[](0), false, bounty, submission, true);
    }

    // ---------- seats: keys, joins and suspensions (task 5.4, S13) ----------

    /// Publish a seat's new key (a rotation), or a vacant seat's first key (the join flow). Signed, in strictly
    /// increasing signer order, by the new key, by the seat's current key if it has one, and by the quorum of the other
    /// seats' active keys. The image must be on the allowed list and the attestation of an accepted type (with a hash,
    /// unless the type is NO_ATTESTATION on a version that accepts it). It takes effect KEY_ROTATION_DELAY later
    /// (`activate`); one pending key per seat.
    function rotate(
        uint256 i,
        address key,
        bytes32 image,
        bytes32 attestationType,
        bytes32 attestation,
        bytes32 nonce,
        bytes[] calldata sigs
    ) external {
        if (i >= _seats.length) revert UnknownSeat();
        if (key == address(0) || _seatOfKey[key] != 0) revert KeyTaken();
        if (!allowedImage[image]) revert ImageNotAllowed();
        if (!acceptedType[attestationType] || (attestationType != NO_ATTESTATION && attestation == bytes32(0))) {
            revert AttestationNotAccepted();
        }
        if (pending[i].key != address(0)) revert AlreadyPending();
        bytes32 digest = rotateDigest(i, key, image, attestationType, attestation, nonce);
        _spend(address(this), digest);
        _checkSeatAction(digest, sigs, i, key, _seats[i].key);
        _seatOfKey[key] = i + 1; // reserved for this seat from now on
        uint64 at = uint64(block.timestamp + KEY_ROTATION_DELAY);
        pending[i] = Rotation(key, image, attestationType, attestation, at);
        emit KeyPublished(i, key, image, attestationType, attestation, at);
    }

    /// Anyone, once the delay has passed: the seat's published key replaces its current one (or fills the vacancy).
    function activate(uint256 i) external {
        if (i >= _seats.length) revert UnknownSeat();
        Rotation memory r = pending[i];
        if (r.key == address(0)) revert NothingPending();
        if (block.timestamp < r.effectiveAt) revert TooEarly();
        Seat storage s = _seats[i];
        address old = s.key;
        s.key = r.key;
        s.image = r.image;
        s.attestation = r.attestation;
        delete pending[i];
        emit KeyActivated(i, old, r.key);
    }

    /// The quorum of the other seats' active keys publishes a seat's suspension (a seat that can't sign anymore); it
    /// takes effect KEY_ROTATION_DELAY later unless the seat's own key lifts it (`resume`).
    function suspend(uint256 i, bytes32 nonce, bytes[] calldata sigs) external {
        if (i >= _seats.length) revert UnknownSeat();
        Seat storage s = _seats[i];
        if (s.key == address(0)) revert SeatVacant();
        if (s.suspendedFrom != 0) revert AlreadyPending();
        bytes32 digest = suspendDigest(i, nonce);
        _spend(address(this), digest);
        _checkSeatAction(digest, sigs, i, address(0), address(0));
        uint64 at = uint64(block.timestamp + KEY_ROTATION_DELAY);
        s.suspendedFrom = at;
        emit SuspensionPublished(i, at);
    }

    /// The seat's own current key, signing, lifts a published or effective suspension: a seat that can still sign
    /// can't be kept out by the others.
    function resume(uint256 i, bytes32 nonce, bytes calldata sig) external {
        if (i >= _seats.length) revert UnknownSeat();
        Seat storage s = _seats[i];
        if (s.suspendedFrom == 0) revert NothingPending();
        bytes32 digest = resumeDigest(i, nonce);
        _spend(address(this), digest);
        if (ECDSA.recover(digest, sig) != s.key) revert MissingSigner();
        s.suspendedFrom = 0;
        emit SeatResumed(i);
    }

    // ---------- internals ----------

    function _active(uint256 i) internal view returns (bool) {
        Seat storage s = _seats[i];
        if (s.key == address(0)) return false;
        if (s.suspendedFrom != 0 && block.timestamp >= s.suspendedFrom) return false;
        return _bonded(i);
    }

    /// TODO(5.8): a seat whose bond is below SEAT_BOND_MIN is suspended until topped up.
    function _bonded(uint256) internal pure returns (bool) {
        return true;
    }

    function _spend(address consumer, bytes32 digest) internal {
        mapping(bytes32 => bool) storage spent = used[consumer];
        if (spent[digest]) revert Replayed();
        spent[digest] = true;
        emit Authorized(consumer, digest);
    }

    /// A seat action's signatures, in strictly increasing signer order: `newKey` and `current` (when not 0) must sign,
    /// and the quorum of the other seats' active keys; no other signer.
    function _checkSeatAction(bytes32 digest, bytes[] calldata sigs, uint256 i, address newKey, address current)
        internal
        view
    {
        uint256 others;
        bool newSigned = newKey == address(0);
        bool currentSigned = current == address(0);
        address last;
        for (uint256 k; k < sigs.length; ++k) {
            address signer = ECDSA.recover(digest, sigs[k]);
            if (signer <= last) revert DuplicateSigner();
            last = signer;
            if (signer == newKey) {
                newSigned = true;
            } else if (signer == current) {
                currentSigned = true;
            } else {
                uint256 s = _seatOfKey[signer];
                if (s == 0 || s - 1 == i || _seats[s - 1].key != signer || !_active(s - 1)) revert NotOracle();
                ++others;
            }
        }
        if (!newSigned || !currentSigned) revert MissingSigner();
        if (others < quorum) revert TooFewSignatures();
    }

    /// At least `need` signatures from distinct active keys, in increasing order; with `drawnOnly`, only keys in
    /// `among`; with `sitting`, no key whose operator is a party to the caller's subject.
    function _check(
        bytes32 digest,
        bytes[] calldata sigs,
        uint256 need,
        address[] memory among,
        bool drawnOnly,
        uint256 bounty,
        uint256 submission,
        bool sitting
    ) internal view {
        uint256 n = sigs.length;
        if (n < need) revert TooFewSignatures();
        address last;
        for (uint256 i; i < n; ++i) {
            address signer = ECDSA.recover(digest, sigs[i]); // refuses malleable (high-s) signatures
            if (!isOracle(signer)) revert NotOracle();
            if (signer <= last) revert DuplicateSigner();
            last = signer;
            if (drawnOnly && !_within(among, signer)) revert NotDrawn();
            if (sitting && _isParty(signer, bounty, submission, msg.sender)) revert Recused();
        }
    }

    function _within(address[] memory set, address k) internal pure returns (bool) {
        for (uint256 i; i < set.length; ++i) {
            if (set[i] == k) return true;
        }
        return false;
    }

    /// Whether any of the key's seat's disclosed operator accounts is a party to the consumer's subject. Seats with no
    /// disclosed operator never ask.
    function _isParty(address k, uint256 bounty, uint256 submission, address consumer) internal view returns (bool) {
        address[] storage ops = _operators[_seatOfKey[k] - 1];
        for (uint256 i; i < ops.length; ++i) {
            if (IParties(consumer).isParty(bounty, submission, ops[i])) return true;
        }
        return false;
    }
}
