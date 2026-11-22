// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity 0.8.37;

/// A panel cap's setting (#251 contract batch 4, design L23): `Strict` is #132's rule, `Off` drops the cap from the draw.
enum Cap {
    Strict,
    Off
}

/// The size of a challenge panel (design L24): `Larger` is D4's CHALLENGE_K[k] (a larger fresh panel); `Same` a fresh
/// panel of the challenged verdict's size, k = 1's challenge keeping D4's 3.
enum ChallengeSize {
    Larger,
    Same
}

/// One deployment's panel rules (proof-of-fix#251, contract batch 4; design L23 and L24; specs/deployment-binding, "The
/// panel caps are set at construction"; specs/judge-panels, "The largest issue-tier panel is set per deployment"),
/// passed to Panels' constructor beside its windows, stored as immutables, readable (`Panels.panelRules`) and listed in
/// the deployment record and the release-candidate record. Nothing changes them after deployment: no setter (D15).
///
/// - `operatorCap`: one seat per operator account, at every k (`Strict`), or none (`Off`).
/// - `hostCap`: at most (k − 1) / 2 seats per host from k = 3 (`Strict`), or none (`Off`).
/// - `teeCap`: at most (k − 1) / 2 seats per TEE type from `teeFrom` (`Strict`), or none (`Off`).
///   The family cap (D20) isn't a setting: it applies as #132 built it.
/// - `kTop`: the largest issue-tier panel, an odd number from 1 to K_MAX (7). The constitution tier keeps K_MAX.
/// - `challengeSize`: `Larger` (D4) or `Same` (L24).
///
/// The mainnet defaults (`strict()`): every cap `Strict`, `kTop` 7, `Larger`, which is what every deployment had before
/// batch 4. The Sepolia launch (`launch()`, owner 2026-11-20): every cap `Off`, `kTop` 3, `Same`.
struct PanelRules {
    Cap operatorCap;
    Cap hostCap;
    Cap teeCap;
    uint256 kTop;
    ChallengeSize challengeSize;
}

library PanelRulesLib {
    uint256 internal constant K_MAX = 7;

    error BadRules();

    /// The constructor's check: `kTop` odd, from 1 to K_MAX (the enums are checked by the ABI decoder).
    function check(PanelRules memory r) internal pure {
        if (r.kTop == 0 || r.kTop > K_MAX || r.kTop % 2 == 0) revert BadRules();
    }

    /// The mainnet defaults: #132's caps, panels up to 7, larger challenges (D4).
    function strict() internal pure returns (PanelRules memory) {
        return PanelRules(Cap.Strict, Cap.Strict, Cap.Strict, K_MAX, ChallengeSize.Larger);
    }

    /// The Sepolia launch's (L23, L24): no operator, host or TEE-type cap, panels of 3, same-size fresh challenges.
    function launch() internal pure returns (PanelRules memory) {
        return PanelRules(Cap.Off, Cap.Off, Cap.Off, 3, ChallengeSize.Same);
    }

    /// The largest challenge panel these rules can draw at the issue tier, which a challenge's cover is priced for (L24):
    /// with `Same`, `kTop` (3 when `kTop` is 1: a lone verdict's challenge keeps D4's 3); with `Larger`, CHALLENGE_K[kTop]
    /// (1→3, 3→5, 5→7, 7→7). D27's second draw is never larger than the verdict.
    function challengeTop(PanelRules memory r) internal pure returns (uint256) {
        uint256 k = r.kTop;
        if (k == 1) return 3;
        if (r.challengeSize == ChallengeSize.Same) return k;
        return k == K_MAX ? K_MAX : k + 2;
    }
}
