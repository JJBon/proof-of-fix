"""Reports and the acceptance check (specs/incentive-simulation: "Report metrics", "Acceptance criteria").

proof-of-fix#10 measures attacks against honest play rather than against zero (design D7, D9): the ring against the
same actors acting honestly, the splitter against the same changes unsplit, the abuser's cohort against the abuser
alone, and bad work by what each defective contribution earns. An absolute return mixes the attack with the
legitimate work the same actor also does.
"""

from __future__ import annotations

from statistics import mean

from .. import MICRO
from ..ledger import Ledger
from ..params import LEGACY, Params
from . import scenarios as S
from .world import World

DEFECTIVE_WORK = ("honest", "owner", "spammer", "splitter", "padder", "sybil", "ally", "newcomer", "abuser", "stacker",
                  "gamer")
CAPITAL_TARGET = 1 / 3  # proof-of-fix#23: unaffordable submissions in the replay, against the fixed-stake rules
# proof-of-fix#27 (design D2): attackers must lose money on defective work significantly; honest kinds' defects are
# accidents and must only not gain significantly; an attacking kind with fewer defective contributions is inconclusive
ATTACKERS = ("spammer", "splitter", "padder", "sybil", "ally", "abuser", "stacker", "gamer")
MIN_DEFECTIVE_SAMPLE = 50


def pooled(rows: list[tuple[float, int]]) -> tuple[float, float, int]:
    """Pooled mean per contribution from (total, count) per run, with its standard error clustered by run (the ratio
    estimator, proof-of-fix#27 design D1): contributions in one run share a path, so they aren't independent."""
    rows = [(t, n) for t, n in rows if n]
    total_n = sum(n for _, n in rows)
    if not total_n:
        return 0.0, 0.0, 0
    m = sum(t for t, _ in rows) / total_n
    k = len(rows)
    if k < 2:
        return m, 0.0, total_n
    var = k / (k - 1) * sum((t - m * n) ** 2 for t, n in rows) / total_n ** 2
    return m, var ** 0.5, total_n


def judge_defective(kind: str, rows: list[tuple[float, int]]) -> dict:
    """One kind's verdict on its defective work: an attacker 'loses' only if mean + 2 SE < 0 ('not shown' or 'pays'
    otherwise, and 'inconclusive' under MIN_DEFECTIVE_SAMPLE); an honest kind is 'ok' unless mean - 2 SE > 0."""
    m, se, n = pooled(rows)
    if kind in ATTACKERS:
        if n < MIN_DEFECTIVE_SAMPLE:
            verdict = "inconclusive"
        else:
            verdict = "loses" if m + 2 * se < 0 else ("pays" if m - 2 * se > 0 else "not shown")
    else:
        verdict = "pays" if m - 2 * se > 0 else "ok"
    return {"mean_per_contribution": round(m, 4), "standard_error": round(se, 4), "n": n, "verdict": verdict,
            "attacker": kind in ATTACKERS}


def fixed_stake(params: Params) -> Params:
    """The fixed-stake rules (acceptance v2's): no index, no reward cap, everything else equal (proof-of-fix#23)."""
    return params.with_(stake_per_reward_bps=0, reward_cap_stake_multiple=0)


def _turns(world: World) -> dict:
    """Mean stake of each turning actor's contributions before and after its turn (the index gamer, #23)."""
    out = {}
    for a in world.actors:
        day = a.behaviour.stack_from_day
        if not day:
            continue
        mine = [c for c in world.life.contributions.values() if c.contributor == a.account]
        before = [c.stake for c in mine if c.submitted_day < day]
        after = [c.stake for c in mine if c.submitted_day >= day]
        out[a.name] = {"stake_before": round(mean(before) / MICRO, 4) if before else None,
                       "stake_after": round(mean(after) / MICRO, 4) if after else None}
    return out


def _pr_returns(world: World) -> dict:
    """Mean gain per contribution, by author kind and by whether it hid a defect: what the author (and its
    sponsor) got from that contribution's entries. A pledge a slash took is a loss of the slashed contribution, not
    of the backing one whose escrow it came from, unless the backing was clawed back (proof-of-fix#19)."""
    contributions = world.life.contributions
    gains: dict[int, int] = {}
    for c in contributions.values():
        net = Ledger.net(world.ledger.entries_for(c.ref))
        gains[c.id] = gains.get(c.id, 0) + net.get(c.contributor, 0) + (net.get(c.sponsor, 0) if c.sponsor else 0)
        for bid, lost in c.pledge_slashed.items():
            if contributions[bid].clawed_back:
                continue  # its clawback would have taken the pledge anyway: the loss stays with the backing
            gains[c.id] -= lost
            gains[bid] = gains.get(bid, 0) + lost
    rows: dict[tuple[str, str], list[int]] = {}
    for c in contributions.values():
        key = (world.author[c.id].kind, "defective" if world.defect.get(c.id) else "sound")
        rows.setdefault(key, []).append(gains[c.id])
    out: dict[str, dict] = {}
    for (kind, status), gains in sorted(rows.items()):
        out.setdefault(kind, {})[status] = {"n": len(gains), "mean": round(mean(gains) / MICRO, 4),
                                            "total": round(sum(gains) / MICRO, 4)}
    return out


def report(world: World, scenario: str, seed: int, **knobs) -> dict:
    """One run's report: every metric the spec lists, with the parameters and seed that produced it."""
    kinds: dict[str, list] = {}
    for a in world.actors:
        kinds.setdefault(a.kind, []).append(a)
    accepted_lines: dict[str, int] = {}
    for c in world.life.contributions.values():
        if c.state == "accepted":
            accepted_lines[c.contributor] = accepted_lines.get(c.contributor, 0) + c.changed_lines
    per_kind = {}
    for kind, people in sorted(kinds.items()):
        nets = [world.net(a) for a in people]
        per_kind[kind] = {
            "actors": len(people),
            "mean_return": round(mean(nets) / MICRO, 4),
            "return_per_action": round(sum(nets) / MICRO / max(1, sum(a.actions for a in people)), 4),
            "return_per_stake": round(sum(nets) / max(1, sum(a.staked for a in people)), 4),
            "unaffordable_submissions": sum(a.stats.get("unaffordable", 0) for a in people),
            "pledges": sum(a.stats.get("pledges", 0) for a in people),
            "lines_accepted": sum(accepted_lines.get(a.account, 0) for a in people),
        }
    cohort_net: dict[str, int] = {}
    for a in world.actors:
        if a.cohort:
            cohort_net[a.cohort] = cohort_net.get(a.cohort, 0) + world.net(a)
    contributions = list(world.life.contributions.values())
    outcomes: dict[str, int] = {}
    for c in contributions:
        outcomes[c.state] = outcomes.get(c.state, 0) + 1
    settled = [c.settled_day - c.submitted_day for c in contributions if c.settled_day is not None]
    validators = [a for a in world.actors if a.behaviour.validator_stake]
    owner = world.owner
    challenges = world.challenges.challenges.values()
    return {
        "scenario": scenario,
        "seed": seed,
        "knobs": knobs,
        "params": {k: (dict(v) if hasattr(v, "items") else v) for k, v in vars(world.params).items()},
        "returns": per_kind,
        "group_returns": {g: round(v / MICRO, 4) for g, v in sorted(cohort_net.items())},
        "pr_returns": _pr_returns(world),
        "contributions": {"total": len(contributions), **outcomes},
        "escaped_regressions": world.escaped_regressions(),
        "clawed_back": sum(1 for c in contributions if c.clawed_back),
        "pledges": {"made": len(world.pledged),
                    "amount": round(sum(world.pledged.values()) / MICRO, 4),
                    "lost_to_slashes": round(sum(sum(c.pledge_slashed.values()) for c in contributions) / MICRO, 4),
                    "lost_to_clawbacks": round(sum(c.pledge_clawed for c in contributions) / MICRO, 4)},
        "challenges": {"total": len(world.challenges.challenges),
                       "refused": sum(ch.state == "refused" for ch in challenges),
                       "upheld": sum(bool(ch.outcome) and ch.applied for ch in challenges),
                       "appealed": sum(ch.appealed_by is not None for ch in challenges)},
        "panels": dict(world.panels),
        "mean_days_to_settle": round(mean(settled), 2) if settled else None,
        "validator_workload": {
            "votes": round(mean(a.stats.get("votes", 0) for a in validators), 2) if validators else 0,
            "reviews": round(mean(a.stats.get("reviews", 0) for a in validators), 2) if validators else 0,
        },
        "releases": [{"number": r.number, **{k: round(v / MICRO, 4) for k, v in r.split.items()}}
                     for r in world.releases.releases],
        "author_escrow": round(world.ledger.balance(world.releases.author_escrow) / MICRO, 4),
        "owner_payout": round(world.net(owner) / MICRO, 4) if owner else None,
        "owner_declined_others": owner.stats.get("declined_others", 0) if owner else 0,
        "turning_actors": _turns(world),
        "contributors_pool_end": round(world.ledger.balance(world.releases.contributors_pool) / MICRO, 4),
        "stake_index_end": world.life.reward_per_weight,
        "conserved": world.ledger.conserved(),
        "not_modelled": ["release timing by the owner (releases are weekly)",
                         "money in panels outside challenges (approvals, declines, split changes)"],
    }


def _mean_se(values: list[float]) -> tuple[float, float]:
    """Mean and standard error. Single runs are too noisy to compare an attack with honest play (each run takes a
    different random path), so those criteria use the mean over seeds."""
    if not values:
        return 0.0, 0.0
    m = mean(values)
    if len(values) < 2:
        return m, 0.0
    var = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    return m, (var / len(values)) ** 0.5


def acceptance(seeds, params: Params = LEGACY, weeks: int = S.WEEKS,
               only: tuple = ("honest", "spam", "griefing", "sponsorship", "collusion", "owner", "capital"),
               **world) -> dict:
    """Run the published scenarios over the seeds and check the criteria. Every failure names the criterion, the
    scenario and the seed (or "all" for criteria judged on the mean over seeds). `world` passes simulation
    assumptions (hunt_elasticity, review_detect_bps).

    Per seed: conservation, honesty pays, griefing loses. Over all seeds (pooled or mean ± 2 standard errors):
    defective work loses money (pooled per kind), splitting and collusion gain nothing against honest play, the
    owner can't gain by defecting (proof-of-fix#10 design D9), and the replay has CAPITAL_TARGET fewer unaffordable
    submissions than the same seeds under the fixed-stake rules (proof-of-fix#23)."""
    seeds = list(seeds)
    failures, runs = [], {}
    defective: dict[str, list[tuple[float, int]]] = {}
    diffs: dict[str, list[float]] = {}
    split_runs: list[tuple[float, int, float, int]] = []  # per seed: splitter net and lines accepted, split, unsplit
    capital: list[tuple[int, int]] = []  # per seed: unaffordable submissions in the replay, fixed stake and proposed

    def fail(criterion, scenario, seed, detail):
        failures.append({"criterion": criterion, "scenario": scenario, "seed": seed, "detail": detail})

    def run(name, seed, p=params, **knobs):
        r = report(S.run(name, seed, p, weeks, **world, **knobs), name, seed, **knobs)
        runs.setdefault(name, []).append(r)
        if not r["conserved"]:
            fail("conservation", name, seed, "balances don't add up to the credits issued")
        return r

    threshold = params.collusion_threshold_bps / 10_000
    for seed in seeds:
        for name in [n for n in ("honest", "spam", "griefing", "sponsorship") if n in only]:
            r = run(name, seed)
            for kind in ("honest", "validator", "newcomer"):
                if kind in r["returns"] and r["returns"][kind]["mean_return"] <= 0:
                    fail("honesty pays", name, seed, f"{kind} mean return {r['returns'][kind]['mean_return']}")
            for kind in DEFECTIVE_WORK:
                bad = r["pr_returns"].get(kind, {}).get("defective")
                if bad:
                    defective.setdefault(kind, []).append((bad["total"], bad["n"]))
            if "griefer" in r["returns"] and r["returns"]["griefer"]["mean_return"] >= 0:
                fail("griefing loses money", name, seed, f"griefer {r['returns']['griefer']['mean_return']}")
            if name == "spam":
                # proof-of-fix#27 (design D3): per accepted line, so a counterfactual that ships less isn't compared
                # with one that ships more; the totals and lines stay in the summary
                unsplit = run("spam", seed, unsplit=True)
                a, b = r["returns"]["splitter"], unsplit["returns"]["splitter"]
                diffs.setdefault("splitting_total", []).append(a["mean_return"] - b["mean_return"])
                split_runs.append((a["mean_return"] * a["actors"], a["lines_accepted"],
                                   b["mean_return"] * b["actors"], b["lines_accepted"]))
        if "collusion" in only:
            for share in S.COLLUSION_SHARES:
                ring = run("collusion", seed, share=share)["group_returns"].get("ring", 0)
                honest = run("collusion", seed, share=share, honest_ring=True)["group_returns"].get("ring", 0)
                diffs.setdefault(f"collusion@{share}", []).append(ring - honest)
        if "owner" in only:
            honest = run("owner", seed)
            selfish = run("owner", seed, self_interested=True)
            diffs.setdefault("owner", []).append(selfish["owner_payout"] - honest["owner_payout"])
        if "capital" in only:
            unaffordable = lambda r: sum(v["unaffordable_submissions"] for v in r["returns"].values())
            proposed = unaffordable(run("replay", seed))
            fixed = unaffordable(run("replay", seed, fixed_stake(params), fixed_stake=True))
            capital.append((fixed, proposed))

    summary: dict[str, dict] = {}
    for kind, rows in sorted(defective.items()):
        v = summary[f"defective:{kind}"] = judge_defective(kind, rows)
        detail = (f"{kind}: {v['mean_per_contribution']:.2f} ± {v['standard_error']:.2f} per defective contribution "
                  f"(n={v['n']}): {v['verdict']}")
        if v["attacker"] and v["verdict"] == "inconclusive":
            fail("defective work loses money (inconclusive)", "pooled", "all", detail)
        elif v["attacker"] and v["verdict"] != "loses":
            fail("defective work loses money", "pooled", "all", detail)
        elif not v["attacker"] and v["verdict"] == "pays":
            fail("honest mistakes don't pay", "pooled", "all", detail)
    for key, values in sorted(diffs.items()):
        m, se = _mean_se(values)
        summary[key] = {"mean_gain": round(m, 2), "standard_error": round(se, 2), "seeds": len(values)}
    if split_runs:
        # per accepted line, as total return over total lines on each side with standard errors clustered by seed
        # (a mean of per-seed ratios blows up when one run gets few lines accepted; design D3, D8)
        rs, ses, _ = pooled([(n, lines) for n, lines, _, _ in split_runs])
        ru, seu, _ = pooled([(n, lines) for _, _, n, lines in split_runs])
        m, se = rs - ru, (ses ** 2 + seu ** 2) ** 0.5
        summary["splitting"] = {"per": "accepted line", "mean_gain": round(m, 4), "standard_error": round(se, 4),
                                "split_per_line": round(rs, 4), "unsplit_per_line": round(ru, 4),
                                "lines_accepted_split": round(mean(x[1] for x in split_runs), 1),
                                "lines_accepted_unsplit": round(mean(x[3] for x in split_runs), 1),
                                "seeds": len(split_runs)}
        if m - 2 * se > 0:
            fail("splitting earns nothing", "spam", "all", f"split vs unsplit per accepted line: {m:+.4f} ± {se:.4f}")
    turns_positive = None
    for share in S.COLLUSION_SHARES:
        if f"collusion@{share}" not in diffs:
            continue
        m, se = _mean_se(diffs[f"collusion@{share}"])
        if m - 2 * se > 0:
            if turns_positive is None:
                turns_positive = share
            if share < threshold:
                fail("collusion loses against honest play", "collusion", "all",
                     f"gain {m:+.2f} ± {se:.2f} at stake share {share}")
    summary["collusion_threshold_measured"] = turns_positive
    if turns_positive is not None and turns_positive <= threshold:
        fail("collusion threshold", "collusion", "all",
             f"collusion gains from a {turns_positive:.0%} stake share, at or below the published {threshold:.0%}")
    if "owner" in diffs:
        m, se = _mean_se(diffs["owner"])
        if m - 2 * se > 0:
            fail("owner can't gain by defecting", "owner", "all", f"self-interested minus honest: {m:+.2f} ± {se:.2f}")
    if capital:
        fixed = _mean_se([f for f, _ in capital])
        proposed = _mean_se([p for _, p in capital])
        m, se = _mean_se([(f - p) - CAPITAL_TARGET * f for f, p in capital])  # cut beyond the target, per seed
        summary["capital"] = {"unaffordable_fixed_stake": round(fixed[0], 2),
                              "unaffordable_proposed": round(proposed[0], 2),
                              "cut": round(1 - proposed[0] / fixed[0], 4) if fixed[0] else None,
                              "cut_beyond_target": round(m, 2), "standard_error": round(se, 2)}
        if m + 2 * se < 0:
            fail("capital criterion", "replay", "all",
                 f"unaffordable {proposed[0]:.1f} proposed vs {fixed[0]:.1f} with the fixed stake: "
                 f"less than {CAPITAL_TARGET:.0%} fewer")
    return {"seeds": seeds, "passed": not failures, "failures": failures, "criteria": summary, "runs": runs}
