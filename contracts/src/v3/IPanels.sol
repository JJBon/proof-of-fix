// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.37;

import {IValidators} from "./IValidators.sol";

/// What Panels reads from the registry beyond `IValidators`: `Validators`' own public views, and the binding.
interface IPanelsRegistry is IValidators {
    function bind() external;
    function acceptedTeeType(bytes32 teeType) external view returns (bool);
    function teeTypeCount() external view returns (uint256);
    function domainSeparator() external view returns (bytes32);
    function familyOf(address key) external view returns (bytes32);
    function coin() external view returns (address);
    function pool() external view returns (address);
    function rosterLength(uint256 t) external view returns (uint256);
    function rosterEntry(uint256 t, uint256 i) external view returns (address key, uint64 raisedAt, uint8 bucket);
}

/// What Panels asks of the check-fee meter (FeesV3, D19): a family is drawn only once priced; an unpriced family's
/// validator met in a draw is announced so it gets a first price.
interface IPanelsFees {
    function isPriced(bytes32 family) external view returns (bool);
    function pricedFrom(bytes32 family) external view returns (uint256);
    function rolled() external view returns (uint256);
    function announce(address key) external;
}

/// What Panels asks of the contract bound to it (RaceV3, task 3.5): who takes part in a submission. A validator is a
/// party when its key or its operator account is one (the issue's reporter, the solver, a funder, an ADR's author).
interface IPanelsHost {
    function isParty(uint256 id, address account) external view returns (bool);
}

/// The family scores (`PanelScores`) as Panels feeds and reads them (D14).
interface IPanelScores {
    function bind() external;
    function recordCounted(bytes32 family, bool passed, bool agreed) external;
    function recordShadow(bytes32 family, bool passed, bool agreed) external;
    function isBarred(bytes32 family) external view returns (bool);
    function isBarredSince(bytes32 family, uint256 snapshot) external view returns (bool);
    function barredCount() external view returns (uint256);
}

/// The sponsors' pool's funding call (v2's `Pool.fund`): a rejected ADR's deposit goes there.
interface IPanelsPool {
    function fund(address coin, uint256 amount) external returns (uint256 received);
}
