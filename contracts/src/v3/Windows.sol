// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

/// One deployment's waiting windows, in seconds (proof-of-fix#251, design L4; specs/deployment-binding, "The waiting
/// windows are set at construction"). Panels takes them and stores them as immutables; Validators takes the same
/// struct and derives its unbonding delay from it. Nothing changes them after deployment: no setter (D15).
///
/// `challenge[level - 1][i]` is CHALLENGE_WINDOW[k, level] for k = 1, 3, 5, 7 (i = 0..3) and levels A, B, C. Level C's
/// entries are kept on a TEE-only deployment (Validators.teeOnly), unused there.
///
/// The production values (ADR 0004, design L4's table; `WindowsLib.production`): seal 2 h, reveal 1 h; level A k = 1
/// 168 h, k = 3 24 h, k = 5 12 h, k = 7 6 h; level B twice A's; level C 336 h, 72 h, 48 h, 24 h; ADR 14 days, removal
/// 48 h; k = 1 at least 7 days (D4).
///
/// The liveness values (#251, design L16 and L19), passed the same way: `stuckGrace` (STUCK_GRACE, 24 h) after a stuck
/// round's reveal deadline before it's released; `retryDelay` (RETRY_DELAY, 24 h) before a waiting submission is drawn
/// again with no change in the registry; `maxRedraws` (MAX_REDRAWS, 3: a count, not a time) released rounds before its
/// check is refunded; `capWindow` (1 h) the trailing window a validator's MAX_CHECKS_PER_HOUR counts over.
struct Windows {
    uint256 seal;
    uint256 reveal;
    uint256[4][3] challenge;
    uint256 adr;
    uint256 removal;
    uint256 k1Min; // K1_WINDOW_MIN: k = 1's challenge window at every level is at least this
    uint256 stuckGrace; // STUCK_GRACE (L19)
    uint256 retryDelay; // RETRY_DELAY (L19)
    uint256 maxRedraws; // MAX_REDRAWS (L19): 1 to 255
    uint256 capWindow; // the trailing window of MAX_CHECKS_PER_HOUR (L16)
}

/// The windows' checks and their packed, immutable form (Panels' `Env`).
library WindowsLib {
    /// Added to the longest challenge window for the unbonding delay (#132: 336 h + 7 days = 504 h today).
    uint256 internal constant UNBONDING_MARGIN = 7 days;

    error BadWindows();

    /// The constructor's order check (deployment-binding, "Windows are checked for order at construction"): every
    /// window nonzero and below 2^32 s; at each level a smaller panel's challenge window at least a larger panel's;
    /// level B's at least level A's and level C's at least level B's for each panel size; k = 1's at least `k1Min`,
    /// which is nonzero; the liveness times nonzero and below 2^32 s, and MAX_REDRAWS from 1 to 255.
    function check(Windows memory w) internal pure {
        _ok(w.stuckGrace);
        _ok(w.retryDelay);
        _ok(w.capWindow);
        if (w.maxRedraws == 0 || w.maxRedraws > type(uint8).max) revert BadWindows();
        _ok(w.seal);
        _ok(w.reveal);
        _ok(w.adr);
        _ok(w.removal);
        _ok(w.k1Min);
        for (uint256 l; l < 3; ++l) {
            for (uint256 i; i < 4; ++i) {
                uint256 c = w.challenge[l][i];
                _ok(c);
                if (i > 0 && c > w.challenge[l][i - 1]) revert BadWindows();
                if (l > 0 && c < w.challenge[l - 1][i]) revert BadWindows();
            }
            if (w.challenge[l][0] < w.k1Min) revert BadWindows();
        }
    }

    /// The longest challenge window of any (k, level): level C's k = 1 once `check` passed.
    function longest(Windows memory w) internal pure returns (uint256 m) {
        for (uint256 l; l < 3; ++l) {
            for (uint256 i; i < 4; ++i) {
                if (w.challenge[l][i] > m) m = w.challenge[l][i];
            }
        }
    }

    /// The unbonding delay a deployment with these windows uses (Validators.UNBONDING_DELAY).
    function unbondingDelay(Windows memory w) internal pure returns (uint256) {
        return longest(w) + UNBONDING_MARGIN;
    }

    /// The twelve challenge windows, 32 bits each: levels A and B in `ab` (A's k = 1 in the lowest bits), level C in
    /// `c`.
    function pack(Windows memory w) internal pure returns (uint256 ab, uint256 c) {
        for (uint256 i; i < 4; ++i) {
            ab |= w.challenge[0][i] << (32 * i);
            ab |= w.challenge[1][i] << (32 * (4 + i));
            c |= w.challenge[2][i] << (32 * i);
        }
    }

    /// CHALLENGE_WINDOW[k, level] from the packed form; k outside {1, 3, 5} reads k = 7's, a level outside {1, 2} level
    /// C's (as the constants did).
    function windowOf(uint256 ab, uint256 c, uint256 k, uint8 level) internal pure returns (uint256) {
        uint256 i = k == 1 ? 0 : k == 3 ? 1 : k == 5 ? 2 : 3;
        if (level == 1) return (ab >> (32 * i)) & type(uint32).max;
        if (level == 2) return (ab >> (32 * (4 + i))) & type(uint32).max;
        return (c >> (32 * i)) & type(uint32).max;
    }

    /// ADR 0004's values, what every deployment used while they were constants (design L4: the Sepolia launch's).
    function production() internal pure returns (Windows memory w) {
        w.seal = 2 hours;
        w.reveal = 1 hours;
        w.challenge = [
            [uint256(168 hours), 24 hours, 12 hours, 6 hours],
            [uint256(336 hours), 48 hours, 24 hours, 12 hours],
            [uint256(336 hours), 72 hours, 48 hours, 24 hours]
        ];
        w.adr = 14 days;
        w.removal = 48 hours;
        w.k1Min = 7 days;
        w.stuckGrace = 24 hours;
        w.retryDelay = 24 hours;
        w.maxRedraws = 3;
        w.capWindow = 1 hours;
    }

    /// The production values with every hour read as a minute (a k = 1 level A verdict waits 168 minutes): the local
    /// devnets' and the Foundry suite's short run (#251, L4), the liveness times too (L19's grace and retry, and the
    /// capacity's hour). MAX_REDRAWS stays 3 and the unbonding margin 7 days.
    function inMinutes() internal pure returns (Windows memory w) {
        w = production();
        w.seal /= 60;
        w.reveal /= 60;
        for (uint256 l; l < 3; ++l) {
            for (uint256 i; i < 4; ++i) {
                w.challenge[l][i] /= 60;
            }
        }
        w.adr /= 60;
        w.removal /= 60;
        w.k1Min /= 60;
        w.stuckGrace /= 60;
        w.retryDelay /= 60;
        w.capWindow /= 60;
    }

    function _ok(uint256 x) private pure {
        if (x == 0 || x > type(uint32).max) revert BadWindows();
    }
}
