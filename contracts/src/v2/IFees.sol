// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

/// What RaceV2 asks of its check-fee meter (proof-of-fix#85, task 5.7, design S15). A version deployed without one
/// (the zero address) keeps v1's flat check deposit and the judges' signed fee list.
interface IFees {
    /// The version's fee coin (S15: one stablecoin per version): every metered check deposit is in it.
    function coin() external view returns (address);

    /// The race this meter serves, bound once by the race itself (`bind`).
    function race() external view returns (address);

    /// Binds the meter to its race: the caller, once. RaceV2's constructor calls it, so a meter serves one race.
    function bind() external;

    /// The solver's check deposit for a submission on bounty `b`, in micro-coins: the worst case (S15).
    function maxDepositFor(uint256 b) external view returns (uint256);

    /// Settles submission `id`'s checks once, when its result is relayed: what each counted judge's operator and the
    /// relayer are paid, in micro-coins, judges first. Only the race calls it.
    function settle(uint256 id, address relayer, uint256 gasUsed)
        external
        returns (address[] memory to, uint256[] memory micro);
}
