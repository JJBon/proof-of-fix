"""The acceptance run's summary across seeds (reports/): returns per actor, the criteria, the sweeps of the
simulation's assumptions, the ablation of proof-of-fix#10's rules (design D1, D8, D9), proof-of-fix#19's pledge
sweeps, and proof-of-fix#23's index and reward-cap sweeps with the reward-to-stake band."""

from __future__ import annotations

from statistics import mean

from .. import MICRO
from ..params import LEGACY, Params
from . import scenarios as S
from .report import acceptance, report


def _stats(values: list[float]) -> dict:
    return {"mean": round(mean(values), 2), "min": round(min(values), 2), "max": round(max(values), 2)} if values else {}


def _turning(runs: list, name: str) -> dict:
    """An actor's mean stake before and after its turn, over the runs (#23: did the index gamer lower its stake?)."""
    out = {}
    for k in ("stake_before", "stake_after"):
        values = [r["turning_actors"][name][k] for r in runs
                  if not r["knobs"] and name in r["turning_actors"] and r["turning_actors"][name][k] is not None]
        out[k] = round(mean(values), 2) if values else None
    return out


def _headline(result: dict) -> dict:
    """The few numbers each sweep and ablation row is compared on."""
    c = result["criteria"]
    defective = {k.split(":", 1)[1]: v["mean_per_contribution"] for k, v in c.items() if k.startswith("defective:")}
    attackers = [v for k, v in c.items() if k.startswith("defective:") and v.get("attacker")]
    runs = result["runs"]
    failed = sorted({f["criterion"] for f in result["failures"]})
    return {
        "seeds": len(result["seeds"]),
        # a group too small to judge on few seeds is shown apart from real failures (#27 design D8)
        "passed_except_inconclusive": not [f for f in failed if not f.endswith("(inconclusive)")],
        "inconclusive": sorted(k.split(":", 1)[1] for k, v in c.items()
                               if k.startswith("defective:") and v.get("verdict") == "inconclusive"),
        "worst_attacker_margin": max((round(v["mean_per_contribution"] + 2 * v["standard_error"], 4)
                                      for v in attackers), default=None),
        "verdicts": {k.split(":", 1)[1]: v["verdict"] for k, v in c.items() if k.startswith("defective:")},
        "passed": result["passed"],
        "failed_criteria": sorted({f["criterion"] for f in result["failures"]}),
        "worst_defective_per_contribution": max(defective.values()) if defective else None,
        "spammer_defective_per_contribution": defective.get("spammer"),
        "honest_return": round(mean(r["returns"]["honest"]["mean_return"] for r in runs["honest"]), 2),
        "validator_return": round(mean(r["returns"]["validator"]["mean_return"] for r in runs["honest"]), 2),
        "escaped_regressions": round(mean(r["escaped_regressions"] for r in runs["spam"]), 2),
        "splitting_gain": c.get("splitting", {}).get("mean_gain"),
        "owner_gain": c.get("owner", {}).get("mean_gain"),
        "collusion_gains_from": c.get("collusion_threshold_measured"),
        "capital_cut": c.get("capital", {}).get("cut"),
        "unaffordable_proposed": c.get("capital", {}).get("unaffordable_proposed"),
    }


def summarize(seeds, params: Params = LEGACY, weeks: int = S.WEEKS, sweep_seeds=None) -> dict:
    """The verdict on `seeds`; the sweeps and the ablation on `sweep_seeds` (default: the same), which their rows
    record, since each repeats the whole acceptance check (proof-of-fix#27 design D4)."""
    seeds = list(seeds)
    sweep = list(sweep_seeds) if sweep_seeds is not None else seeds
    result = acceptance(seeds, params, weeks)
    runs = result["runs"]
    out: dict = {"seeds": len(seeds), "sweep_seeds": len(sweep), "weeks": weeks, "passed": result["passed"],
                 "failures": result["failures"], "criteria": result["criteria"]}

    # returns per actor type, per scenario (the attacked runs, not the counterfactuals)
    returns = {}
    for name in ("honest", "spam", "griefing", "sponsorship"):
        rs = [r for r in runs[name] if not r["knobs"]]
        kinds = sorted({k for r in rs for k in r["returns"]})
        returns[name] = {k: _stats([r["returns"][k]["mean_return"] for r in rs if k in r["returns"]]) for k in kinds}
    out["returns"] = returns
    out["unaffordable_submissions"] = {
        name: round(mean(sum(v["unaffordable_submissions"] for v in r["returns"].values()) for r in runs[name]), 2)
        for name in ("honest", "spam", "sponsorship")}
    out["turning_actors"] = {name: _turning(runs["spam"], name) for name in ("stacker-1", "gamer-1")}
    out["contributors_pool_end"] = {name: _stats([r["contributors_pool_end"] for r in runs[name] if not r["knobs"]])
                                    for name in ("honest", "spam", "sponsorship")}
    out["pledges"] = {
        name: {k: round(mean(r["pledges"][k] for r in runs[name] if not r["knobs"]), 2)
               for k in ("made", "amount", "lost_to_slashes", "lost_to_clawbacks")}
        for name in ("honest", "spam", "sponsorship")}

    # collusion: the ring against the same actors acting honestly, per stake share
    out["collusion"] = [
        {"share": share, **{k: v for k, v in result["criteria"].get(f"collusion@{share}", {}).items()}}
        for share in S.COLLUSION_SHARES]

    # owner
    honest = [r for r in runs["owner"] if not r["knobs"].get("self_interested")]
    selfish = [r for r in runs["owner"] if r["knobs"].get("self_interested")]
    out["owner"] = {
        "honest_payout": _stats([r["owner_payout"] for r in honest]),
        "self_interested_payout": _stats([r["owner_payout"] for r in selfish]),
        "gain": result["criteria"].get("owner"),
        "declined_others": _stats([r["owner_declined_others"] for r in selfish]),
        "panels": {k: round(mean(r["panels"][k] for r in selfish), 2) for k in selfish[0]["panels"]} if selfish else {},
    }

    # sweeps of the simulation's assumptions (design D1): the mechanism must pass at elasticity 0 as well
    # the bar is every criterion at hunting elasticity 0, 0.5 and 1 on the verdict seeds (#27); 0.5 is `criteria`
    out["elasticity_verdicts"] = {str(e): _headline(acceptance(seeds, params, weeks, hunt_elasticity=e))
                                  for e in (0.0, 1.0)}
    out["hunt_elasticity_sweep"] = {str(e): _headline(acceptance(sweep, params, weeks, hunt_elasticity=e))
                                    for e in (0.0, 0.5, 1.0)}
    out["review_detection_sweep"] = {str(d): _headline(acceptance(sweep, params, weeks, review_detect_bps=d))
                                     for d in (3_000, 6_000, 8_000)}

    # ablation (design D8): each #10 rule switched off in turn
    ablations = {
        "all rules (defaults)": params,
        "no escrow share for challengers": params.with_(challenger_escrow_share_bps=0),
        "no review duty": params.with_(review_duty=False),
        "one instalment (no clawback)": params.with_(reward_instalments=1),
        "per-tier weights (not linear)": params.with_(linear_reward_weight=False),
        "no decline limit": params.with_(max_declines_bps=10_000),
        "first defaults' stake (10)": params.with_(base_stake=params.base_stake * 10 // 75),
        "no pledges": params.with_(pledge_max_stake_bps=0),
        "no index (fixed stake)": params.with_(stake_per_reward_bps=0),
        "no reward cap": params.with_(reward_cap_stake_multiple=0),
    }
    out["ablation"] = {name: _headline(acceptance(sweep, p, weeks)) for name, p in ablations.items()}

    # pledge caps (proof-of-fix#19 design D2)
    out["pledge_stake_cap_sweep"] = {str(v): _headline(acceptance(sweep, params.with_(pledge_max_stake_bps=v), weeks))
                                     for v in (0, 2_500, 5_000, 7_500)}
    out["pledge_escrow_cap_sweep"] = {str(v): _headline(acceptance(sweep, params.with_(pledge_max_escrow_bps=v), weeks))
                                      for v in (5_000, 10_000)}
    # the stake index and the reward cap (proof-of-fix#23 design D2)
    out["stake_index_sweep"] = {str(v): _headline(acceptance(sweep, params.with_(stake_per_reward_bps=v), weeks))
                                for v in (0, 1_500, 2_500, 4_000)}
    out["pool_buffer_sweep"] = {str(v): _headline(acceptance(sweep, params.with_(pool_buffer_releases=v), weeks))
                                for v in (0, 1, 2, 4)}
    out["reward_cap_sweep"] = {str(v): _headline(acceptance(sweep, params.with_(reward_cap_stake_multiple=v), weeks))
                               for v in (0, 4, 6, 8, 16)}
    # the band: reward / stake over every rewarded contribution, per scenario (the first seed)
    band = {}
    for name in ("honest", "spam", "sponsorship", "replay"):
        cs = [c for c in S.run(name, seeds[0], params, weeks).life.contributions.values() if c.reward]
        band[name] = {"reward_to_stake": round(sum(c.reward for c in cs) / sum(c.stake for c in cs), 3) if cs else None,
                      "max": round(max(c.reward / c.stake for c in cs), 3) if cs else None}
    out["reward_to_stake"] = band

    # risk sweep and replay at GridCraft's volume
    out["risk"] = []
    for m in S.RISK_MULTIPLIERS:
        rs = [report(S.run("risk", seed, params, weeks, multiplier=m), "risk", seed, multiplier=m) for seed in seeds]
        out["risk"].append({
            "multiplier": m,
            "honest": _stats([r["returns"]["honest"]["mean_return"] for r in rs]),
            "spammer": _stats([r["returns"]["spammer"]["mean_return"] for r in rs]),
            "escaped_regressions": _stats([r["escaped_regressions"] for r in rs]),
        })
    rs = [report(S.run("replay", seed, params, weeks), "replay", seed) for seed in seeds]
    out["replay"] = {
        "contributions": _stats([r["contributions"]["total"] for r in rs]),
        "honest": _stats([r["returns"]["honest"]["mean_return"] for r in rs]),
        "validator": _stats([r["returns"]["validator"]["mean_return"] for r in rs]),
        "hunter": _stats([r["returns"]["hunter"]["mean_return"] for r in rs]),
        "escaped_regressions": _stats([r["escaped_regressions"] for r in rs]),
        "unaffordable_submissions": _stats([sum(v["unaffordable_submissions"] for v in r["returns"].values()) for r in rs]),
        "pledges": _stats([r["pledges"]["made"] for r in rs]),
    }
    return out
