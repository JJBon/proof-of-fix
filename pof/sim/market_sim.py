"""The market mode's scenarios, report, acceptance check and summary (specs/incentive-simulation, "Market scenarios"
and "Acceptance criteria for the market"; proof-of-fix#15 design D5-D7, D9).

Every run drains until no bounty is assigned or being paid (MARKET_DRAIN days at most), so solvers are judged on
work that was fully paid or fully lost, not cut off mid-instalment. Returns are net of each solver's effort.
"""

from __future__ import annotations

import copy
import random
from dataclasses import replace
from statistics import mean

from .. import BPS, MICRO, share
from ..params import DEFAULTS, TOKENS, Params
from . import actors as A
from .actors import Actor
from .baseline import load, size_sampler
from .checks import COPY_FAMILY, checking_report, evaluator_specs, runner_specs
from .market_world import MarketWorld
from .report import _mean_se, judge_defective, report

WEEKS = 8
MARKET_DRAIN = 120
MARKET = DEFAULTS  # the market is the default (owner's decision, 2026-10-24)
CHECK_ATTACKS = ("check_lazy", "check_herd", "check_copy", "check_craft", "check_plant", "check_sock",
                 "check_half", "check_split", "check_cheat")  # #43 D6, #49, #47
V5_GOOD_FAILED = 0.2514  # checking v5's share of good fixes rejected (#47: top models must reject fewer)
SCENARIOS = ("market", "market_bluff", "market_noshow", "market_spam", "market_ring", "market_flood",
             "market_grief", "market_owner", "market_farm", "market_self", "market_rep") + CHECK_ATTACKS
MODE_ATTACKS = ("mode_pad", "mode_variant", "mode_inflate", "mode_fake")  # #60 D7, #64: the award modes' attacks
TOKEN_SCENARIOS = ("token_self", "token_inflate", "token_launch")  # #58 D6; token_market and token_owner are
# market and market_owner with the emission on
RING_SIZES = (2, 3, 4, 6)
NEUTRAL_OK = ("check_sock",)  # judged like bluffing and rings: it mustn't gain significantly (#43)
SOLVER_KINDS = ("solver", "bluffer", "lowballer", "no_show", "spam_solver", "flood")
MARKET_ATTACKERS = ("spam_solver", "flood")  # whose defective work must lose money (the others' defects are accidents)
WORLD_KNOBS = ("hunt_elasticity", "review_detect_bps", "issues_per_week", "value_median", "value_spread",
               "pledged_share_bps", "cost_per_line", "treasury_detect_bps", "bid_daily_bps", "single_account",
               "checking", "rho_within", "rho_across", "score_on_agreement", "evaluator_cost", "accuracy_shift",
               "tee_compromise_bps", "estimate_error", "duplicate_false_bps", "token_price", "weight_error",
               "weight_check_catch_bps")


def _solvers(n: int, rng: random.Random, prefix: str = "solver", **extra) -> list[Actor]:
    """Honest solvers with private skills (cost multipliers), drawn from the scenario's own generator."""
    return [Actor(f"{prefix}-{i + 1}", "solver", replace(A.SOLVER, skill=round(rng.lognormvariate(0, 0.4), 3)),
                  **extra) for i in range(n)]


def base_world_evaluators(report: dict) -> list[tuple[str, float]]:
    """(provider, net return per verdict) of each honest evaluator in a run's report (#47)."""
    return report["checking"].get("per_verdict", [])


def _evaluators() -> list[Actor]:
    """The honest AI evaluators: five operators, each running three of the five model families (#43 D5)."""
    return [Actor(f"evaluator-{i + 1}", "evaluator", A.EVALUATOR, operator=op, family=fam)
            for i, (op, fam) in enumerate(evaluator_specs())]


def _runners() -> list[Actor]:
    """The honest attested CI runners: nine operators, each on one hardware vendor's enclaves (#43)."""
    return [Actor(f"runner-{i + 1}", "runner", A.RUNNER, operator=op, family=vendor)
            for i, (op, vendor) in enumerate(runner_specs())]


def _check_attack(name: str, rng: random.Random, honest: bool, attested: bool = True) -> list[Actor]:
    """A checking scenario's attacker (#43 design D6), or the same accounts behaving honestly (`honest`). Skills
    are drawn the same way either way, so the two runs compare like for like."""
    attack = {"cohort": "attack"}
    if name == "check_lazy":  # reports "pass" without running: a runner forging attestations, or a lazy validator
        if attested:
            return [Actor("lazy_runner-1", "runner" if honest else "lazy_runner", A.RUNNER, operator="lazy-op",
                          family="tdx", **attack)]
        return [Actor("lazy_validator-1", "validator" if honest else "lazy_validator", A.LAZY_VALIDATOR, **attack)]
    if name == "check_herd":
        return [Actor("herder-1", "evaluator" if honest else "herder", A.EVALUATOR, operator="herd-op", family="A",
                      **attack)]
    if name == "check_copy":  # four names, four declared families, one real model
        skill = round(rng.lognormvariate(0, 0.4), 3)
        copies = [Actor(f"copy_evaluator-{i + 1}", "copy_evaluator", A.EVALUATOR, operator=f"copy-op-{i + 1}",
                        family=fam, true_family=COPY_FAMILY, **attack) for i, fam in enumerate("ABCA")]
        partner = Actor("copy_partner-1", "solver" if honest else "copy_partner",
                        replace(A.SOLVER if honest else A.JUNK_SOLVER, skill=skill if honest else skill * 0.3), **attack)
        if honest:  # honest copies: the same shared model, but no favours
            for c in copies:
                c.kind = "evaluator"
        return copies + [partner]
    if name == "check_craft":
        skill = round(rng.lognormvariate(0, 0.4), 3)
        return [Actor("crafter-1", "solver" if honest else "crafter",
                      replace(A.SOLVER if honest else A.JUNK_SOLVER, skill=skill if honest else skill * 0.3), **attack)]
    if name == "check_plant":  # a competitive cost, so it wins jobs at all (it builds a real fix, plus the bug)
        return [Actor("planter-1", "solver" if honest else "planter",
                      replace(A.SOLVER if honest else A.JUNK_SOLVER, skill=0.5), **attack),
                Actor("plant_partner-1", "idle" if honest else "plant_partner", A.PLANT_PARTNER, **attack)]
    if name == "check_cheat":  # #47: registered for provider A's frontier model, runs its small one
        return [Actor("model_cheat-1", "evaluator" if honest else "model_cheat", A.EVALUATOR, operator="cheat-op",
                      family="A", **attack)]
    if name == "check_split":  # #49: borderline junk built to split the jury, which gets its bond back
        skill = round(rng.lognormvariate(0, 0.4), 3)
        return [Actor("split_farmer-1", "solver" if honest else "split_farmer",
                      replace(A.SOLVER, skill=skill) if honest else replace(A.JUNK_SOLVER, skill=skill * 0.3), **attack)]
    if name == "check_half":  # delivers fixes that solve the public case only, for half the work (#43)
        skill = round(rng.lognormvariate(0, 0.4), 3)
        return [Actor("half_fixer-1", "solver" if honest else "half_fixer",
                      replace(A.SOLVER, skill=skill) if honest else replace(A.HALF_FIXER, skill=skill * 0.5), **attack)]
    if name == "check_sock":  # a checker with an undeclared second identity that bids (#43)
        checker = (Actor("sock_runner-1", "runner" if honest else "sock_runner", A.RUNNER, operator="sock-op",
                         family="sev", **attack) if attested else
                   Actor("sock_validator-1", "validator" if honest else "sock_validator", A.LAZY_VALIDATOR, **attack))
        return [checker,
                Actor("sock_solver-1", "solver" if honest else "sock_solver", replace(A.SOLVER, skill=0.6), **attack)]
    raise ValueError(f"unknown checking scenario {name!r}")


def _mode_attack(name: str, rng: random.Random, honest: bool) -> list[Actor]:
    """An award-mode attacker (#60 D7), or the same accounts behaving honestly (`honest`)."""
    attack, skill = {"cohort": "attack"}, round(rng.lognormvariate(0, 0.4), 3)
    if name == "mode_pad":  # its tests raise coverage without catching anything
        return [Actor("padder-1", "solver" if honest else "test_padder",
                      replace(A.SOLVER if honest else A.TEST_PADDER, skill=skill), **attack)]
    if name == "mode_variant":  # resubmits a failed fix as a variant from its second account
        return [Actor("variant-1", "solver" if honest else "variant_racer",
                      replace(A.SOLVER if honest else A.VARIANT_RACER, skill=skill), **attack),
                Actor("variant-2", "second_account", replace(A.FAKE, endowment=A.SOLVER.endowment), **attack)]
    if name == "mode_inflate":  # posts and solves small issues of its own, their estimates inflated
        return [Actor("inflater-1", "inflater", replace(A.INFLATER, skill=skill, inflates=not honest), **attack)]
    if name == "mode_fake":  # #64: its socks start paid attempts they never submit, so its bounties look crowded
        return [Actor("fake_attempter-1", "solver" if honest else "fake_attempter",
                      replace(A.SOLVER if honest else A.FAKE_ATTEMPTER, skill=skill), **attack)] + [
                Actor(f"sock-{i + 1}", "sock_account", A.FAKE, **attack) for i in range(A.FAKE_ATTEMPTER.fake_attempts)]
    raise ValueError(f"unknown award-mode scenario {name!r}")


def build(name: str, seed: int, params: Params = MARKET, solvers: int = 12, **knobs) -> MarketWorld:
    """A market world for one scenario and seed, not yet run."""
    rng = random.Random(seed * 7_919 + 1)  # skills: their own stream, so knobs don't shift them
    owner_beh = A.OWNER_SELF_INTERESTED if knobs.get("self_interested") else A.OWNER_HONEST
    if name == "token_launch":  # #58 D6: the owner is one of the few solvers, coding its own issues
        owner_beh = A.OWNER_CODER
    owner = Actor("owner", "owner", replace(owner_beh, submissions_per_week=0))
    people = ([Actor(f"pledger-{i + 1}", "pledger", A.PLEDGER) for i in range(30)]
              + [Actor(f"reporter-{i + 1}", "reporter", A.REPORTER) for i in range(20)] + _solvers(solvers, rng)
              + [Actor(f"validator-{i + 1}", "validator", A.VALIDATOR) for i in range(12)]
              + [Actor(f"hunter-{i + 1}", "hunter", A.HUNTER) for i in range(3)] + [owner] + _evaluators()
              + _runners())  # in both CI modes, so the comparison runs the same population (idle under validators)
    truthful = knobs.get("truthful", False)
    if name == "market_bluff":
        for kind, beh in (("bluffer", A.BLUFFER), ("lowballer", A.LOWBALLER)):
            skill = round(rng.lognormvariate(0, 0.4), 3)
            people.append(Actor(f"{kind}-1", kind, replace(beh, skill=skill, bid_factor=1.0 if truthful else
                                                           beh.bid_factor)))
    elif name == "market_noshow":
        people += [Actor(f"no_show-{i + 1}", "no_show", replace(A.NO_SHOW, skill=round(rng.lognormvariate(0, 0.4), 3)))
                   for i in range(2)]
    elif name == "market_spam":
        people += [Actor(f"spam_solver-{i + 1}", "spam_solver", A.SPAM_SOLVER) for i in range(3)]
    elif name == "market_ring":
        group = None if knobs.get("honest_ring") else "ring"
        people += _solvers(knobs.get("ring_size", 3), rng, prefix="ring", group=group, cohort="ring")
    elif name == "market_flood":
        people.append(Actor("flood-1", "flood", A.FLOOD))
    elif name == "market_grief":
        people += [Actor(f"griefer-{i + 1}", "griefer", A.GRIEFER) for i in range(3)]
    elif name == "market_farm":  # #34: a match farmer and its four fake pledging accounts
        people.append(Actor("match_farmer-1", "match_farmer", replace(A.MATCH_FARMER, skill=0.5), cohort="farm"))
        people += [Actor(f"fake-{i + 1}", "fake", A.FAKE, cohort="farm") for i in range(4)]
    elif name == "market_self":  # #34: funds and solves its own issues
        people.append(Actor("self_dealer-1", "self_dealer", replace(A.SELF_DEALER, skill=round(rng.lognormvariate(0, 0.4), 3))))
    elif name == "market_rep":  # #37: builds solver trust on small jobs, then wins jobs low and walks away
        people.append(Actor("rep_farmer-1", "rep_farmer", replace(A.REP_FARMER, skill=round(rng.lognormvariate(0, 0.4), 3))))
    elif name in CHECK_ATTACKS:
        people += _check_attack(name, rng, knobs.get("honest_attack", False), params.ci_mode == "attested")
    elif name in MODE_ATTACKS:
        people += _mode_attack(name, rng, knobs.get("honest_attack", False))
    elif name == "token_self":  # #58: registers its own issues and solves them for tokens; its twin solves others'
        kind, beh = ("solver", A.SOLVER) if knobs.get("honest_attack") else ("self_coder", A.SELF_CODER)
        people.append(Actor("self_coder-1", kind, replace(beh, skill=round(rng.lognormvariate(0, 0.4), 3)),
                            cohort="attack"))
    elif name == "token_inflate":  # #58: the same, its importance estimates inflated; its twin's honest
        kind, beh = (("self_coder", A.SELF_CODER) if knobs.get("honest_attack")
                     else ("importance_inflater", A.IMPORTANCE_INFLATER))
        people.append(Actor("inflater-1", kind, replace(beh, skill=round(rng.lognormvariate(0, 0.4), 3)),
                            cohort="attack"))
    elif name not in ("market", "market_owner", "token_launch"):
        raise ValueError(f"unknown market scenario {name!r}")
    if knobs.get("score_on_agreement"):  # the comparison: no ground truth, so no planted cases (#43 design D6)
        params = params.with_(planted_share_bps=0)
    world = {k: v for k, v in knobs.items() if k in WORLD_KNOBS}
    return MarketWorld(params, seed, people, size_sampler(load()), maintainer=owner, **world)


def run(name: str, seed: int, params: Params = MARKET, weeks: int = WEEKS, **knobs) -> MarketWorld:
    world = build(name, seed, params, **knobs)
    if knobs.get("check_gas") is not None:  # #85 S15: checks charged as usage plus the service fee (pof.checkgas)
        world.market.check_gas = knobs["check_gas"]
    return world.run(weeks * 7, drain_days=MARKET_DRAIN)


# ---------- report ----------

def pledges_accounted(world: MarketWorld) -> bool:
    """Every credit that left a pledged bounty went to a contribution's escrow, a market-fee share, an oracle fee
    (#43), a refund to a pledger, or insurance; and every market contribution's escrow paid only its solver or went
    back to its bounty."""
    m = world.market
    fee_targets = set(world.releases.fee_targets().values()) | {world.releases.insurance}
    if world.checks is not None and world.params.checks_paid_by == "bounty":  # #43's rule: the bounty paid its checks
        fee_targets |= (set(world.vset.stake_account) | set(world.checks.checking.evaluators)
                        | set(world.checks.checking.runners))
    reporters = {r.reporter for r in m.reports.values()}  # the finder's fee (#34)
    escrow_of = {}  # escrow account -> (bounty account, solver)
    for cid, b in m._by_contribution.items():
        c = world.life.contributions[cid]
        escrow_of[c.escrow_account] = (b.account, c.contributor)
    bounty_accounts = {b.account: b for b in m.bounties.values()}
    for e in world.ledger.entries:
        if e.source in bounty_accounts:
            b = bounty_accounts[e.source]
            if not (e.target in escrow_of or e.target in fee_targets or e.target in b.pledges or
                    e.target in reporters):
                return False
        if e.source in escrow_of:
            bounty, solver = escrow_of[e.source]
            if e.target not in (bounty, solver):
                return False
    return True


def funder_cost(world: MarketWorld) -> float | None:
    """Pledgers' net spending (pledges less refunds) per paid pledged bounty, in credits (#34)."""
    m = world.market
    pledged = [b for b in m.bounties.values() if b.pledges and not b.treasury]
    paid = [b for b in pledged if b.state == "paid"]
    if not paid:
        return None
    accounts = {b.account for b in pledged}
    pledgers = {p for b in pledged for p in b.pledges}
    out = sum(e.amount for e in world.ledger.entries if e.source in pledgers and e.target in accounts)
    back = sum(e.amount for e in world.ledger.entries if e.source in accounts and e.target in pledgers
               and e.reason == "refund")
    return round((out - back) / len(paid) / MICRO, 4)


def self_dealing_bounded(world: MarketWorld) -> bool:
    """On every bounty a reporter funded itself, the finder's fee it got back is below the market fee its own share of
    the inputs paid (#34)."""
    m = world.market
    for b in m.bounties.values():
        r = m.reports.get(b.report) if b.report else None
        if r is None or r.reporter not in b.pledges or b.state != "paid":
            continue
        finder = sum(e.amount for e in world.ledger.entries_for(b.ref) if e.reason == "reward" and e.target == r.reporter)
        own = b.pledges[r.reporter] / (sum(b.pledges.values()) + b.treasury_in)
        market_fee = sum(e.amount for e in world.ledger.entries_for(b.ref) if e.reason == "payout")
        if finder >= market_fee * own:
            return False
    return True


def _farm_cost(world: MarketWorld) -> float | None:
    """The match farm's net spending per own issue fixed (its cohort's pledges less refunds, over its own issues
    paid), in credits (#37 design D6)."""
    farm = {a.account for a in world.actors if a.cohort == "farm"}
    farmer = next((a for a in world.actors if a.kind == "match_farmer"), None)
    if farmer is None:
        return None
    own = [b for b in world.market.bounties.values()
           if world.issue_of.get(b.id) is not None and world.issue_of[b.id].owner is farmer]
    fixed = sum(1 for b in own if b.state == "paid")
    if not fixed:
        return None
    accounts = {b.account for b in own}
    out = sum(e.amount for e in world.ledger.entries if e.source in farm and e.target in accounts)
    back = sum(e.amount for e in world.ledger.entries if e.source in accounts and e.target in farm and e.reason == "refund")
    return round((out - back) / fixed / MICRO, 4)


def _reputation(world: MarketWorld) -> dict:
    """Each kind's mean score and trust per role, and the mean bond per assignment (#37)."""
    rep, out = world.market.reputation, {}
    kinds: dict[str, list[Actor]] = {}
    for a in world.actors:
        kinds.setdefault(a.kind, []).append(a)
    for kind, people in sorted(kinds.items()):
        row = {}
        for role in ("solver", "reporter", "funder"):
            scores = [rep.score(a.account, role) for a in people]
            if any(scores):
                row[role] = {"score": round(mean(scores), 3),
                             "trust": round(mean(rep.trust_bps(a.account, role) for a in people) / 10_000, 3)}
        assigned = sum(a.stats.get("assigned", 0) for a in people)
        if assigned:
            row["bond_per_assignment"] = round(sum(a.stats.get("bond_total", 0) for a in people) / assigned / MICRO, 4)
        if row:
            out[kind] = row
    return out


def market_report(world: MarketWorld, scenario: str, seed: int, **knobs) -> dict:
    """The legacy report's metrics, plus the market's: bounties, prices, deliveries, the treasury, the pledge
    accounting, and every kind's effort and return net of it."""
    r = report(world, scenario, seed, **knobs)
    m = world.market
    kinds: dict[str, list[Actor]] = {}
    for a in world.actors:
        kinds.setdefault(a.kind, []).append(a)
    for kind, people in kinds.items():
        r["returns"][kind]["effort"] = round(mean(world.effort(a) for a in people) / MICRO, 4)
        r["returns"][kind]["net_of_effort"] = round(mean(world.net_of_effort(a) for a in people) / MICRO, 4)
        for key in ("bids", "assigned", "delivered", "delivery_failed"):
            r["returns"][kind][key] = sum(a.stats.get(key, 0) for a in people)
    states: dict[str, int] = {}
    for b in m.bounties.values():
        states[b.state] = states.get(b.state, 0) + 1
    routes: dict[str, int] = {}
    for i in world.issues:
        routes[i.route] = routes.get(i.route, 0) + 1
    paid = [b for b in m.bounties.values() if b.state == "paid"]
    costs = [world.cost(world.bids[b.assigned.id].actor, world.bids[b.assigned.id].issue) for b in paid
             if b.assigned is not None and not world.bids[b.assigned.id].issue.junk]
    prices = [b.price for b in paid if b.assigned is not None and not world.bids[b.assigned.id].issue.junk]
    cohort: dict[str, int] = {}
    for a in world.actors:
        if a.cohort:
            cohort[a.cohort] = cohort.get(a.cohort, 0) + world.net_of_effort(a)
    r["market"] = {
        "issues": routes,
        "bounties": states,
        "price_to_cost": round(sum(prices) / sum(costs), 4) if costs else None,
        "mean_price": round(mean(prices) / MICRO, 4) if prices else None,
        "treasury_spend": round(sum(m._treasury_spent.values()) / MICRO, 4),
        "treasury_max_per_release": round(max(m._treasury_spent.values(), default=0) / MICRO, 4),
        "treasury_within_budget": max(m._treasury_spent.values(), default=0) <= world.params.treasury_budget,
        "treasury_junk": round(world.treasury_junk / MICRO, 4),
        "pledges_accounted": pledges_accounted(world),
        "group_net_of_effort": {g: round(v / MICRO, 4) for g, v in sorted(cohort.items())},
        **({"outsider_net_of_effort": round(_outsiders(world), 4)} if scenario == "market_ring" else {}),
        "treasury_real_funded": sum(1 for i in world.issues if i.route == "treasury" and not i.junk),
        "matched": round(sum(b.matched for b in m.bounties.values()) / MICRO, 4),
        "funder_cost_per_paid_bounty": funder_cost(world),
        # funded: reached its target (the auction); in race and claim, with no target (#56 D12), paid
        "pledged_funded_share": round(sum(1 for b in m.bounties.values() if b.pledges and not b.treasury and (
                                          b.state not in ("pledging", "refunded") if world.mode == "auction"
                                          else b.state == "paid"))
                                      / max(1, sum(1 for b in m.bounties.values() if b.pledges and not b.treasury)), 4),
        "pledged_paid": sum(1 for b in m.bounties.values() if b.pledges and not b.treasury and b.state == "paid"),
        "issue_stakes": {s: sum(1 for r in m.reports.values() if r.state == s)
                         for s in ("posted", "rewarded", "returned", "forfeited")},
        "finder_fees": round(sum(e.amount for e in world.ledger.entries if e.reason == "reward"
                                 and e.ref.startswith("bounty:")) / MICRO, 4),
        "self_dealing_bounded": self_dealing_bounded(world),
        "reputation": _reputation(world),
        "farm_cost_per_fix": _farm_cost(world),
    }
    r["checking"] = checking_report(world)
    fixed = [world.life.contributions[b.contribution].submitted_day - world.issue_of[b.id].day for b in paid
             if b.contribution is not None and b.id in world.issue_of and not world.issue_of[b.id].junk]
    r["market"]["days_to_fix"] = round(mean(fixed), 2) if fixed else None
    r["market"]["published_attempts"] = sum(len(b.published) for b in m.bounties.values())
    honest = [a for a in world.actors if a.kind == "solver"]  # #60 D7: what the award mode costs and buys
    effort = sum(a.stats.get("effort", 0) for a in honest)
    r["market"]["wasted_share"] = round(sum(a.stats.get("wasted", 0) for a in honest) / effort, 4) if effort else None
    quality = [world.fix_quality[b.contribution] for b in paid if b.contribution in world.fix_quality]
    bar = world.params.gate_bar_bps / BPS
    r["market"]["accepted_quality_share"] = round(sum(q >= bar for q in quality) / len(quality), 4) if quality else None
    for key in ("attempts", "stopped", "claims", "late", "false_duplicates", "duplicate_appeals",
                "duplicate_appeals_won"):
        r["market"][key] = sum(a.stats.get(key, 0) for a in honest)
    r["market"]["bundles"] = world.check_stats.get("bundles", 0)
    r["market"]["gates_failed"] = world.check_stats.get("gates_failed", 0)
    if world.tokens_on:
        r["tokens"] = token_report(world)
        for kind, people in kinds.items():
            r["returns"][kind]["tokens"] = round(mean(world.tokens(a) for a in people) / MICRO, 4)
    return r


def token_report(world: MarketWorld) -> dict:
    """The token figures of one run (#58 D7): the supply and its invariant, tokens against weighted work per kind,
    the 0-coin bounties, the owner's share of the supply over the periods, and each cohort's tokens per unit of true
    weight (an inflated estimate shows there)."""
    t, m, p = world.market.tokens, world.market, world.params
    kind_of = {a.account: a.kind for a in world.actors}
    cohort_of = {a.account: a.cohort for a in world.actors if a.cohort}
    tokens: dict[str, int] = {}
    weight: dict[str, float] = {}
    true: dict[str, dict[str, float]] = {}
    by_weight = True
    closes: dict[int, int] = {}
    for period, _, _ in t.history:
        closes[period] = closes.get(period, 0) + 1
    for period, c, amount in t.history:
        pool, total = t.pooled[period]
        if abs(amount - pool * c.weight / total) > closes[period]:  # rounding: at most the period's remainder
            by_weight = False
        issue = world.issue_of.get(int(c.ref.split(":")[1]))
        value = issue.value if issue is not None else 0
        parts = [(c.solver, 1 - (p.token_reporter_bps / BPS if c.reporters else 0))] + [
            (r, p.token_reporter_bps / BPS / len(c.reporters)) for r in c.reporters]
        for who, part in parts:
            weight[kind_of.get(who, "?")] = weight.get(kind_of.get(who, "?"), 0) + c.weight * part
            if who in cohort_of:
                row = true.setdefault(cohort_of[who], {"tokens": 0, "true_weight": 0.0})
                row["true_weight"] += value * part
    for mint in t.mints:
        if mint.reason in ("solver", "reporter"):
            tokens[kind_of.get(mint.account, "?")] = tokens.get(kind_of.get(mint.account, "?"), 0) + mint.amount
            if mint.account in cohort_of:
                true.setdefault(cohort_of[mint.account], {"tokens": 0, "true_weight": 0.0})["tokens"] += mint.amount
    to_bounties, all_weight = sum(tokens.values()), sum(weight.values())
    owner = world.owner.account if world.owner else None
    supply, owned, over = 0, 0, []
    for period in sorted({mint.period for mint in t.mints}):
        minted = [x for x in t.mints if x.period == period]
        supply += sum(x.amount for x in minted)
        owned += sum(x.amount for x in minted if x.account == owner)
        over.append(round(owned / supply, 4) if supply else 0.0)
    zero = [b for b in m.bounties.values() if not b.pledges and not b.treasury_in]
    reported = [b for b in m.bounties.values() if b.state == "paid" and m._finders(b)]
    biased = [b for b in reported if getattr(world.issue_of.get(b.id), "bias", 1.0) > 1]
    honest = [b for b in reported if b not in biased]
    return {
        "supply": round(t.supply / MICRO, 2),
        "periods_minting": sum(1 for v in t.minted.values() if v),
        "conserved": t.conserved(),
        "by_weight": by_weight,
        "rate": round(t.rate, 4) if t.rate is not None else None,
        "kinds": {k: {"tokens_share": round(tokens.get(k, 0) / to_bounties, 4) if to_bounties else 0.0,
                      "weight_share": round(weight.get(k, 0) / all_weight, 4) if all_weight else 0.0}
                  for k in sorted(set(tokens) | set(weight))},
        "zero_coin": {"opened": len(zero), "fixed": sum(1 for b in zero if b.state == "paid"),
                      "fixed_share": round(sum(1 for b in zero if b.state == "paid") / len(zero), 4) if zero else None},
        "owner_supply_share": round(t.balance(owner) / t.supply, 4) if owner and t.supply else 0.0,
        "owner_supply_share_by_period": over,
        "inflation_forfeits": {"honest": len(honest), "honest_forfeited": sum(b.inflated for b in honest),
                               "inflated": len(biased), "inflated_forfeited": sum(b.inflated for b in biased)},
        "cohorts": {g: {"tokens": round(v["tokens"] / MICRO, 2), "true_weight": round(v["true_weight"] / MICRO, 2),
                        "tokens_per_true_weight": round(v["tokens"] / v["true_weight"], 4) if v["true_weight"] else None,
                        "effort": round(sum(world.effort(a) for a in world.actors if a.cohort == g) / MICRO, 2)}
                    for g, v in sorted(true.items())},
    }


# ---------- acceptance ----------

def acceptance(seeds, params: Params = MARKET, weeks: int = WEEKS, only: tuple = SCENARIOS, **world) -> dict:
    """The market's acceptance criteria over the seeds (means with two standard errors, as in v5). Every failure
    names the criterion, the scenario and the seed, or "all" for criteria judged over seeds."""
    seeds = list(seeds)
    failures, runs = [], {}
    values: dict[str, list[float]] = {}
    defective: dict[str, list[tuple[float, int]]] = {}
    rings: dict[int, list[float]] = {}
    ring_costs: dict[int, dict[str, list[float]]] = {}  # outsiders' and funders' change from each ring

    def fail(criterion, scenario, seed, detail):
        failures.append({"criterion": criterion, "scenario": scenario, "seed": seed, "detail": detail})

    def run_(name, seed, p=None, **knobs):
        report_knobs = {k: v for k, v in knobs.items() if k not in ("no_matching", "no_discount")}
        r = market_report(run(name, seed, p or params, weeks, **{**world, **report_knobs}), name, seed, **knobs)
        runs.setdefault(name if p is None and not knobs else f"{name}:variant", []).append(r)  # #43: base runs apart
        if not r["conserved"]:
            fail("conservation", name, seed, "balances don't add up to the credits issued")
        if not r["market"]["pledges_accounted"]:
            fail("pledges pay only for released fixes", name, seed, "a pledged credit went elsewhere")
        if not r["market"]["treasury_within_budget"]:
            fail("treasury within budget", name, seed, f"spent {r['market']['treasury_max_per_release']} in a release")
        for kind in ("solver", "bluffer", "lowballer", "spam_solver", "flood", "owner", "honest"):
            bad = r["pr_returns"].get(kind, {}).get("defective")
            if bad:
                defective.setdefault(kind, []).append((bad["total"], bad["n"]))
        return r

    for seed in seeds:
        for name in ("market", "market_bluff", "market_noshow", "market_spam", "market_flood", "market_grief"):
            if name not in only:
                continue
            r = run_(name, seed)
            ret = r["returns"]
            values.setdefault("solver", []).append(ret["solver"]["net_of_effort"])
            values.setdefault("validator", []).append(ret["validator"]["mean_return"])
            if name == "market_bluff":
                fair = run_(name, seed, truthful=True)["returns"]
                for kind in ("bluffer", "lowballer"):
                    values.setdefault(f"{kind}_gain", []).append(ret[kind]["net_of_effort"] - fair[kind]["net_of_effort"])
            if name == "market_noshow":
                values.setdefault("no_show", []).append(ret["no_show"]["net_of_effort"])
            if name == "market_spam":
                values.setdefault("spam_solver", []).append(ret["spam_solver"]["net_of_effort"])
            if name == "market_flood":
                values.setdefault("flood", []).append(ret["flood"]["net_of_effort"])
                values.setdefault("treasury_junk", []).append(r["market"]["treasury_junk"])
            if name == "market_grief" and ret["griefer"]["mean_return"] >= 0:
                fail("griefing loses money", name, seed, f"griefer {ret['griefer']['mean_return']}")
        if "market_ring" in only:
            for size in RING_SIZES:
                ring = run_("market_ring", seed, ring_size=size)["market"]
                fair = run_("market_ring", seed, ring_size=size, honest_ring=True)["market"]
                rings.setdefault(size, []).append(ring["group_net_of_effort"].get("ring", 0)
                                                  - fair["group_net_of_effort"].get("ring", 0))
                ring_costs.setdefault(size, {"outsiders": [], "funders": []})["outsiders"].append(
                    ring["outsider_net_of_effort"] - fair["outsider_net_of_effort"])
                if ring["funder_cost_per_paid_bounty"] is not None and fair["funder_cost_per_paid_bounty"] is not None:
                    ring_costs[size]["funders"].append(ring["funder_cost_per_paid_bounty"]
                                                       - fair["funder_cost_per_paid_bounty"])
        if "market" in only:  # #34: discoverers earn; matching lowers funders' cost (against no matching)
            base = runs["market"][-1]
            values.setdefault("reporter", []).append(base["returns"]["reporter"]["mean_return"])
            unmatched = run_("market", seed, params.with_(matching_share_bps=0), no_matching=True)
            a, b = base["market"]["funder_cost_per_paid_bounty"], unmatched["market"]["funder_cost_per_paid_bounty"]
            if a is not None and b is not None:
                values.setdefault("funder_cost_change", []).append(a - b)  # reported; the criterion is below
            values.setdefault("funded_share_change", []).append(
                base["market"]["pledged_funded_share"] - unmatched["market"]["pledged_funded_share"])
            values.setdefault("pledged_paid_change", []).append(
                base["market"]["pledged_paid"] - unmatched["market"]["pledged_paid"])
            if "market_flood" in only:
                values.setdefault("crowd_out_base", []).append(base["market"]["treasury_real_funded"])
                values.setdefault("crowd_out_flood", []).append(runs["market_flood"][-1]["market"]["treasury_real_funded"])
        if "market_farm" in only:  # #37: fake accounts must not make the farmer's own fixes cheaper
            split, single = run_("market_farm", seed), run_("market_farm", seed, single_account=True)
            a, b = split["market"]["farm_cost_per_fix"], single["market"]["farm_cost_per_fix"]
            if a is not None and b is not None:
                values.setdefault("farm_gain", []).append(b - a)  # what splitting saves per fix
            values.setdefault("farm_split_unfunded", []).append(1 if a is None else 0)  # fakes got no fix at all
        if "market_rep" in only:  # #37: the reputation farmer must lose
            values.setdefault("rep_farmer", []).append(run_("market_rep", seed)["returns"]["rep_farmer"]["net_of_effort"])
        if "market" in only and "market_flood" in only:  # #37: crowd-out at weak (50 %) junk detection
            weak = run_("market", seed, treasury_detect_bps=5_000)["market"]["treasury_real_funded"]
            flooded = run_("market_flood", seed, treasury_detect_bps=5_000)["market"]["treasury_real_funded"]
            values.setdefault("weak_base", []).append(weak)
            values.setdefault("weak_flood", []).append(flooded)
        if "market" in only:  # #37: proven solvers lock less bond (against no discount, same seeds)
            with_ = runs["market"][-1]["market"]["reputation"].get("solver", {}).get("bond_per_assignment")
            without = run_("market", seed, params.with_(bond_discount_bps=0), no_discount=True)
            off = without["market"]["reputation"].get("solver", {}).get("bond_per_assignment")
            if with_ is not None and off is not None:
                values.setdefault("bond_change", []).append(with_ - off)
        if "market" in only:  # #43: the checking layer against fixed odds, and what honest checkers earn
            base = runs["market"][-1]
            fixed = run_("market", seed, checking=False)
            a, b = base["checking"]["caught_share"], fixed["checking"]["caught_share"]
            if a is not None and b is not None:
                values.setdefault("detection_change", []).append(a - b)
            values.setdefault("caught_share", []).append(a or 0.0)
            values.setdefault("good_failed_share", []).append(base["checking"]["good_failed_share"] or 0.0)
            values.setdefault("escalated_share", []).append(
                base["checking"].get("escalations", 0) / max(1, base["checking"].get("juries", 0)))
            values.setdefault("evaluator", []).append(base["returns"]["evaluator"]["net_of_effort"])
            values.setdefault("validator_net", []).append(base["returns"]["validator"]["net_of_effort"])
            staked = run_("market", seed, params.with_(ci_mode="validators"))  # CI by staked validators instead
            for key, (a_, b_) in (("ci_validators_caught_change", (base["checking"]["caught_share"],
                                                                   staked["checking"]["caught_share"])),
                                  ("ci_validators_solver_change", (base["returns"]["solver"]["net_of_effort"],
                                                                   staked["returns"]["solver"]["net_of_effort"])),
                                  ("ci_validators_funder_cost_change", (base["market"]["funder_cost_per_paid_bounty"],
                                                                        staked["market"]["funder_cost_per_paid_bounty"]))):
                if a_ is not None and b_ is not None:
                    values.setdefault(key, []).append(a_ - b_)  # attested minus validators
            per_verdict = {}  # #47: honest evaluators' net return per verdict, by provider
            for a in base_world_evaluators(base):
                per_verdict.setdefault(a[0], []).append(a[1])
            if per_verdict.get("A") and per_verdict.get("C"):
                values.setdefault("quality_premium", []).append(mean(per_verdict["A"]) - mean(per_verdict["C"]))
            flat = run_("market", seed, params.with_(verdict_fee_tiers=()))  # one flat fee (#47 comparison)
            for key, (a_, b_) in (("tiers_good_failed_change", (base["checking"]["good_failed_share"],
                                                                flat["checking"]["good_failed_share"])),
                                  ("tiers_solver_change", (base["returns"]["solver"]["net_of_effort"],
                                                           flat["returns"]["solver"]["net_of_effort"]))):
                if a_ is not None and b_ is not None:
                    values.setdefault(key, []).append(a_ - b_)
            bounty_pays = run_("market", seed, params.with_(checks_paid_by="bounty"))  # #43's rule (#49 comparison)
            for key, (a_, b_) in (("who_pays_funder_cost_change", (base["market"]["funder_cost_per_paid_bounty"],
                                                                    bounty_pays["market"]["funder_cost_per_paid_bounty"])),
                                  ("who_pays_price_change", (base["market"]["mean_price"], bounty_pays["market"]["mean_price"])),
                                  ("who_pays_paid_change", (base["market"]["bounties"].get("paid", 0),
                                                            bounty_pays["market"]["bounties"].get("paid", 0))),
                                  ("who_pays_solver_change", (base["returns"]["solver"]["net_of_effort"],
                                                              bounty_pays["returns"]["solver"]["net_of_effort"]))):
                if a_ is not None and b_ is not None:
                    values.setdefault(key, []).append(a_ - b_)  # the solver paying, minus the bounty paying
            queue = run_("market", seed, params.with_(failed_reopens_round=False))  # the rule before #43
            for key, path in (("fresh_funder_cost_change", ("market", "funder_cost_per_paid_bounty")),
                              ("fresh_paid_change", ("market", "pledged_paid")),
                              ("fresh_days_change", ("market", "days_to_fix")),
                              ("fresh_price_change", ("market", "mean_price"))):
                a_, b_ = base[path[0]][path[1]], queue[path[0]][path[1]]
                if a_ is not None and b_ is not None:
                    values.setdefault(key, []).append(a_ - b_)
            values.setdefault("fresh_solver_change", []).append(
                base["returns"]["solver"]["net_of_effort"] - queue["returns"]["solver"]["net_of_effort"])
        for name in CHECK_ATTACKS:  # #43: each attack against the same accounts behaving honestly
            if name in only:
                atk = run_(name, seed)["market"]["group_net_of_effort"].get("attack", 0)
                fair = run_(name, seed, honest_attack=True)["market"]["group_net_of_effort"].get("attack", 0)
                values.setdefault(f"{name}_gain", []).append(atk - fair)
        for name in MODE_ATTACKS:  # #60: each award-mode attack against the same accounts behaving honestly
            if name in only:
                atk = run_(name, seed)["market"]["group_net_of_effort"].get("attack", 0)
                fair = run_(name, seed, honest_attack=True)["market"]["group_net_of_effort"].get("attack", 0)
                values.setdefault(f"{name}_gain", []).append(atk - fair)
        if "check_half" in only:  # the comparison: half-fixing without the "not solved" challenge
            off = params.with_(not_solved_challenges=False)
            atk = run_("check_half", seed, off)["market"]["group_net_of_effort"].get("attack", 0)
            fair = run_("check_half", seed, off, honest_attack=True)["market"]["group_net_of_effort"].get("attack", 0)
            values.setdefault("half_without_challenge_gain", []).append(atk - fair)
        if "check_herd" in only:  # the comparison: herding when evaluators are scored on agreement
            atk = run_("check_herd", seed, score_on_agreement=True)["market"]["group_net_of_effort"].get("attack", 0)
            fair = run_("check_herd", seed, score_on_agreement=True, honest_attack=True)["market"][
                "group_net_of_effort"].get("attack", 0)
            values.setdefault("herd_agreement_gain", []).append(atk - fair)
        if "market_self" in only:
            r = run_("market_self", seed)
            if not r["market"]["self_dealing_bounded"]:
                fail("self-dealing doesn't pay", "market_self", seed, "a finder's fee reached its own market fee")
        if "market_owner" in only:
            honest = run_("market_owner", seed)["owner_payout"]
            selfish = run_("market_owner", seed, self_interested=True)["owner_payout"]
            values.setdefault("owner_gain", []).append(selfish - honest)

    summary: dict[str, dict] = {}
    for key, vals in sorted(values.items()):
        m, se = _mean_se(vals)
        digits = 4 if key in ("funded_share_change", "detection_change", "caught_share", "good_failed_share",
                              "escalated_share", "quality_premium", "tiers_good_failed_change") else 2
        summary[key] = {"mean": round(m, digits), "standard_error": round(se, digits), "seeds": len(vals)}

    def judged(key):
        return summary[key]["mean"], summary[key]["standard_error"]

    if "solver" in summary:
        m, se = judged("solver")
        if m - 2 * se <= 0:
            fail("honest solvers earn more than their cost", "market", "all", f"net of effort {m:+.2f} ± {se:.2f}")
    if "validator" in summary:
        m, se = judged("validator")
        if m - 2 * se <= 0:
            fail("validators earn", "market", "all", f"{m:+.2f} ± {se:.2f}")
    for kind in ("bluffer", "lowballer"):
        if f"{kind}_gain" in summary:
            m, se = judged(f"{kind}_gain")
            if m - 2 * se > 0:
                fail("bidding your cost is best", "market_bluff", "all", f"{kind} gains {m:+.2f} ± {se:.2f}")
    race = params.award_mode == "race"  # #60 D9: no assignment, so a no-show can't take a job; it mustn't gain
    for kind in ("no_show", "spam_solver", "flood"):
        if kind in summary:
            m, se = judged(kind)
            if race and kind == "no_show":
                if m - 2 * se > 0:
                    fail("no-shows can't gain", kind, "all", f"{kind} net of effort {m:+.2f} ± {se:.2f}")
            elif m + 2 * se >= 0:
                fail("attackers lose", kind, "all", f"{kind} net of effort {m:+.2f} ± {se:.2f}")
    if "reporter" in summary:
        m, se = judged("reporter")
        if m - 2 * se <= 0:
            fail("discoverers earn", "market", "all", f"reporters {m:+.2f} ± {se:.2f}")
    if "funded_share_change" in summary:  # amended criterion (owner, 2026-10-24; #34 design D7)
        m, se = judged("funded_share_change")
        if m - 2 * se <= 0:
            fail("matching gets more pledged issues fixed", "market", "all", f"funded share change {m:+.4f} ± {se:.4f}")
    if "farm_gain" in summary:  # #37: fake accounts mustn't make the farmer's own fixes significantly cheaper
        m, se = judged("farm_gain")
        if m - 2 * se > 0:
            fail("match farming doesn't pay", "market_farm", "all", f"splitting saves {m:+.2f} ± {se:.2f} per own fix")
    if "rep_farmer" in summary:
        m, se = judged("rep_farmer")
        if race and "solver" in summary:  # #60 D9: there's no job to win low and walk away from; its earnings are
            if m - 2 * se > summary["solver"]["mean"]:  # honest work, so it mustn't gain more than an honest solver
                fail("reputation farming doesn't pay", "market_rep", "all", f"net of effort {m:+.2f} ± {se:.2f}")
        elif m + 2 * se >= 0:
            fail("reputation farming loses", "market_rep", "all", f"net of effort {m:+.2f} ± {se:.2f}")
    if "bond_change" in summary:
        m, se = judged("bond_change")
        if m + 2 * se >= 0:
            fail("proven solvers lock less", "market", "all", f"bond per assignment {m:+.2f} ± {se:.2f}")
    if "weak_base" in summary and summary["weak_base"]["mean"]:
        ratio = summary["weak_flood"]["mean"] / summary["weak_base"]["mean"]
        summary["crowd_out_ratio_weak_detection"] = {"mean": round(ratio, 4)}
        if ratio < 0.75:
            fail("crowd-out bounded at weak detection", "market_flood", "all", f"{ratio:.0%} at 50 % detection")
    if "crowd_out_base" in summary and summary["crowd_out_base"]["mean"]:
        ratio = summary["crowd_out_flood"]["mean"] / summary["crowd_out_base"]["mean"]
        summary["crowd_out_ratio"] = {"mean": round(ratio, 4)}
        if ratio < 0.75:
            fail("crowd-out bounded", "market_flood", "all", f"real treasury issues {ratio:.0%} of no flood")
    if "owner_gain" in summary:
        m, se = judged("owner_gain")
        if m - 2 * se > 0:
            fail("owner can't gain by defecting", "market_owner", "all", f"{m:+.2f} ± {se:.2f}")
    for key in ("evaluator", "validator_net"):  # #43: honest checkers earn, their effort counted
        if key in summary:
            m, se = judged(key)
            if m - 2 * se <= 0:
                fail("honest checkers earn", "market", "all", f"{key} net of effort {m:+.2f} ± {se:.2f}")
    for name in CHECK_ATTACKS:
        if f"{name}_gain" in summary:
            m, se = judged(f"{name}_gain")
            if name in NEUTRAL_OK:  # it can't lose more than its honest twin, only fail to gain (owner, 2026-10-25)
                if m - 2 * se > 0:
                    fail("a hidden bidder doesn't gain", name, "all", f"gains {m:+.2f} ± {se:.2f} against honest")
            elif m + 2 * se >= 0:
                fail("checking attacks lose", name, "all", f"gains {m:+.2f} ± {se:.2f} against honest")
    for name in MODE_ATTACKS:  # #60: none may gain against its honest twin (#64, owner: fake attempts included:
        if f"{name}_gain" in summary:  # "rigging is paying without benefit")
            m, se = judged(f"{name}_gain")
            if m - 2 * se > 0:
                fail("award-mode attacks don't gain", name, "all", f"gains {m:+.2f} ± {se:.2f} against honest")
    if "quality_premium" in summary:  # #47: the more accurate provider's evaluators earn more per verdict
        m, se = judged("quality_premium")
        if m - 2 * se <= 0:
            fail("quality pays", "market", "all", f"premium per verdict {m:+.4f} ± {se:.4f}")
    if "good_failed_share" in summary:  # #47: top models reject fewer good fixes than checking v5
        m, se = judged("good_failed_share")
        if m + 2 * se >= V5_GOOD_FAILED:
            fail("fewer good fixes rejected", "market", "all", f"{m:.4f} ± {se:.4f} against v5's {V5_GOOD_FAILED}")
    if "detection_change" in summary:
        m, se = judged("detection_change")
        if m + 2 * se < 0:
            fail("detection holds", "market", "all", f"caught before beta {m:+.4f} ± {se:.4f} against fixed odds")
    for kind, rows in sorted(defective.items()):
        v = summary[f"defective:{kind}"] = judge_defective(kind, rows)
        attacker = kind in MARKET_ATTACKERS
        v["attacker"] = attacker
        if attacker and v["n"] >= 50 and v["verdict"] in ("not shown", "pays"):
            fail("defective work loses money", "pooled", "all", f"{kind}: {v['verdict']}")
        if attacker and v["verdict"] == "inconclusive":
            fail("defective work loses money (inconclusive)", "pooled", "all", f"{kind}: n={v['n']}")
        if not attacker and v["mean_per_contribution"] - 2 * v["standard_error"] > 0:
            fail("honest mistakes don't pay", "pooled", "all", f"{kind}: pays")
    smallest = None
    for size in RING_SIZES:  # #40, amended by #58 (owner, 2026-10-29/30): a ring fails only if it gains at others' cost
        if size in rings:
            m, se = _mean_se(rings[size])
            summary[f"ring@{size}"] = {"mean_gain": round(m, 2), "standard_error": round(se, 2), "seeds": len(rings[size])}
            if m - 2 * se > 0:
                smallest = size if smallest is None else smallest
            out_m, out_se = _mean_se(ring_costs[size]["outsiders"])
            fund_m, fund_se = _mean_se(ring_costs[size]["funders"])
            summary[f"ring_cost@{size}"] = {"outsiders": round(out_m, 2), "outsiders_se": round(out_se, 2),
                                            "funders": round(fund_m, 2), "funders_se": round(fund_se, 2)}
            for detail in judge_ring(size, (m, se), (out_m, out_se), (fund_m, fund_se)):
                fail("a ring doesn't cost outsiders or funders", "market_ring", "all", detail)
    summary["ring_gains_from"] = smallest  # reported: a ring's gain from saved effort is allowed
    return {"seeds": seeds, "passed": not failures, "failures": failures, "criteria": summary, "runs": runs}


def judge_ring(size: int, gain, outsiders, funders) -> list[str]:
    """#58 (owner, 2026-10-30): a ring fails only when it gains significantly AND significantly lowers outsiders'
    earnings or raises funders' cost per paid bounty: an attack that pays. A ring that gains from the effort its members
    stop spending on each other, or costs others without gaining (it has no reason to form), passes; all three are
    reported. Each argument is (mean, standard error) over the seeds; returns the failures' details."""
    (m, se), (out_m, out_se), (fund_m, fund_se) = gain, outsiders, funders
    if m - 2 * se <= 0:
        return []
    out = []
    if out_m + 2 * out_se < 0:
        out.append(f"a ring of {size} gains {m:+.2f} ± {se:.2f} while outsiders lose {out_m:+.2f} ± {out_se:.2f}")
    if fund_m - 2 * fund_se > 0:
        out.append(f"a ring of {size} gains {m:+.2f} ± {se:.2f} while funders' cost per fix rises "
                   f"{fund_m:+.2f} ± {fund_se:.2f}")
    return out


# ---------- summary ----------

def _bounties(result: dict, state: str) -> float | None:
    """The mean number of bounties in this state in the base market runs (#40: the reserve sweep)."""
    base = result["runs"].get("market")
    return round(mean(r["market"]["bounties"].get(state, 0) for r in base), 2) if base else None


def _headline(result: dict) -> dict:
    c = result["criteria"]
    return {"seeds": len(result["seeds"]), "passed": result["passed"],
            "failed_criteria": sorted({f["criterion"] for f in result["failures"]}),
            "solver_net_of_effort": c.get("solver", {}).get("mean"),
            "validator": c.get("validator", {}).get("mean"),
            "spam_solver": c.get("spam_solver", {}).get("mean"),
            "no_show": c.get("no_show", {}).get("mean"),
            "ring_gains_from": c.get("ring_gains_from"),
            "rings": {k[5:]: c[k]["mean_gain"] for k in sorted(c) if k.startswith("ring@")},
            "bluffer_gain": c.get("bluffer_gain", {}).get("mean"),
            "lowballer_gain": c.get("lowballer_gain", {}).get("mean"),
            "caught_share": c.get("caught_share", {}).get("mean"),
            "detection_change": c.get("detection_change", {}).get("mean"),
            "good_failed_share": c.get("good_failed_share", {}).get("mean"),
            "escalated_share": c.get("escalated_share", {}).get("mean"),
            "evaluator": c.get("evaluator", {}).get("mean"),
            "check_gains": {n[6:]: c[f"{n}_gain"]["mean"] for n in CHECK_ATTACKS if f"{n}_gain" in c},
            "herd_agreement_gain": c.get("herd_agreement_gain", {}).get("mean"),
            "half_without_challenge_gain": c.get("half_without_challenge_gain", {}).get("mean"),
            "fresh_round": {k[6:]: c[k]["mean"] for k in sorted(c) if k.startswith("fresh_")},
            "ci_vs_validators": {k[14:]: c[k]["mean"] for k in sorted(c) if k.startswith("ci_validators_")},
            "solver_pays_vs_bounty": {k[9:]: c[k]["mean"] for k in sorted(c) if k.startswith("who_pays_")},
            "quality_premium": c.get("quality_premium", {}).get("mean"),
            "tiers_vs_flat": {k[6:]: c[k]["mean"] for k in sorted(c) if k.startswith("tiers_")},
            "bounties_paid": _bounties(result, "paid"),
            "bounties_unsolved": _bounties(result, "unsolved"),
            "reporter": c.get("reporter", {}).get("mean"),
            "funder_cost_change": c.get("funder_cost_change", {}).get("mean"),
            "funded_share_change": c.get("funded_share_change", {}).get("mean"),
            "crowd_out_ratio": c.get("crowd_out_ratio", {}).get("mean"),
            "crowd_out_weak": c.get("crowd_out_ratio_weak_detection", {}).get("mean"),
            "rep_farmer": c.get("rep_farmer", {}).get("mean"),
            "bond_change": c.get("bond_change", {}).get("mean"),
            "farm_gain": c.get("farm_gain", {}).get("mean"),
            "farm_split_unfunded": c.get("farm_split_unfunded", {}).get("mean")}


def summarize(seeds, params: Params = MARKET, weeks: int = WEEKS, sweep_seeds=None) -> dict:
    """The market verdict on `seeds` at hunting elasticity 0.5, 0 and 1; sweeps of the market's assumptions and
    parameters on `sweep_seeds` (design D2, D5)."""
    seeds = list(seeds)
    sweep = list(sweep_seeds) if sweep_seeds is not None else seeds
    result = acceptance(seeds, params, weeks)
    runs = result["runs"]
    out: dict = {"seeds": len(seeds), "sweep_seeds": len(sweep), "weeks": weeks, "passed": result["passed"],
                 "failures": result["failures"], "criteria": result["criteria"]}
    out["elasticity_verdicts"] = {str(e): _headline(acceptance(seeds, params, weeks, hunt_elasticity=e))
                                  for e in (0.0, 1.0)}
    base = [r for r in runs["market"]]
    out["returns"] = {k: round(mean(r["returns"][k]["net_of_effort"] for r in base), 2)
                      for k in sorted(base[0]["returns"])}
    out["market"] = {
        "bounties": {k: round(mean(r["market"]["bounties"].get(k, 0) for r in base), 2)
                     for k in sorted({k for r in base for k in r["market"]["bounties"]})},
        "issues": {k: round(mean(r["market"]["issues"].get(k, 0) for r in base), 2)
                   for k in sorted({k for r in base for k in r["market"]["issues"]})},
        "price_to_cost": round(mean(r["market"]["price_to_cost"] for r in base if r["market"]["price_to_cost"]), 4),
        "mean_price": round(mean(r["market"]["mean_price"] for r in base if r["market"]["mean_price"]), 2),
        "treasury_spend": round(mean(r["market"]["treasury_spend"] for r in base), 2),
        "deliveries": {k: round(mean(r["returns"]["solver"][k] for r in base), 2)
                       for k in ("bids", "assigned", "delivered", "delivery_failed")},
        "flood_treasury_junk": round(mean(r["market"]["treasury_junk"] for r in runs.get("market_flood", [])), 2)
        if runs.get("market_flood") else None,
        "issue_stakes": {k: round(mean(r["market"]["issue_stakes"][k] for r in base), 2)
                         for k in ("posted", "rewarded", "returned", "forfeited")},
        "finder_fees": round(mean(r["market"]["finder_fees"] for r in base), 2),
        "matched": round(mean(r["market"]["matched"] for r in base), 2),
        "funder_cost_per_paid_bounty": round(mean(r["market"]["funder_cost_per_paid_bounty"] for r in base
                                                  if r["market"]["funder_cost_per_paid_bounty"] is not None), 2),
    }
    keys = sorted({k for r in base for k, v in r["checking"].items() if v is None or isinstance(v, (int, float))})
    out["checking"] = {k: round(mean(r["checking"].get(k) or 0 for r in base), 4) for k in keys}
    out["checking"]["brier"] = {k: round(mean(r["checking"]["brier"].get(k, 0) for r in base), 4)
                                for k in sorted({k for r in base for k in r["checking"].get("brier", {})})}
    out["sweeps"] = {}
    for label, key, vals in (("cost per line", "cost_per_line", (MICRO // 2, MICRO, 2 * MICRO)),
                             ("pledged share", "pledged_share_bps", (2_000, 4_000, 6_000)),
                             ("treasury junk detection", "treasury_detect_bps", (5_000, 8_500, 9_500)),
                             ("model correlation within a family", "rho_within", (0.0, 0.5, 0.8)),
                             ("evaluator cost per verdict", "evaluator_cost", (MICRO // 10, 3 * MICRO // 10,
                                                                              MICRO // 2)),
                             ("model accuracy (added to every family)", "accuracy_shift", (-0.05, 0.0, 0.05, 0.1)),
                             ("enclave compromise", "tee_compromise_bps", (0, 50, 500))):
        out["sweeps"][label] = {str(v): _headline(acceptance(sweep, params, weeks, **{key: v})) for v in vals}
    for label, key, vals in (("bond (stake share)", "bounty_stake_bps", (2_000, 4_000, 6_000)),
                             ("delivery days", "delivery_days", (7, 14, 28)),
                             ("market fee", "market_fee_bps", (2_000, 2_500, 3_000)),  # above the finder's fee (#34)
                             ("issue stake", "issue_stake", (2 * MICRO, 5 * MICRO, 20 * MICRO)),
                             ("finder's fee", "finder_fee_bps", (1_111, 1_429, 1_765)),  # 10, 12.5, 15 % of the payout
                             ("matching share", "matching_share_bps", (0, 5_000, 10_000)),
                             ("trust floor", "trust_floor_bps", (1_000, 2_500, 5_000)),
                             ("bond discount", "bond_discount_bps", (0, 5_000, 7_500)),
                             ("reserve", "reserve_bps", (5_000, 7_500, 9_000, 10_000)),
                             ("trust points per release", "trust_points_per_release", (1, 2, 100)),
                             ("planted share", "planted_share_bps", (0, 500, 1_000, 2_000)),
                             ("jury accept threshold", "jury_accept", (2, 3)),
                             ("second jury accept threshold", "second_jury_accept", (5, 6, 7)),
                             ("attested runners per delivery", "ci_runners", (1, 2, 3))):
        out["sweeps"][label] = {str(v): _headline(acceptance(sweep, params.with_(**{key: v}), weeks)) for v in vals}
    out["sweeps"]["jury size"] = {str(n): _headline(acceptance(sweep, params.with_(jury_size=n, jury_accept=n),
                                                               weeks)) for n in (1, 3, 5)}  # consensus at each size
    return out


# ---------- award modes compared (#60 D8) ----------

MODE_METRICS = (("solver_net_of_effort", ("returns", "solver", "net_of_effort")),
                ("wasted_share", ("market", "wasted_share")),
                ("funder_cost_per_paid_bounty", ("market", "funder_cost_per_paid_bounty")),
                ("bounties_paid", ("market", "bounties", "paid")),
                ("bounties_unsolved", ("market", "bounties", "unsolved")),
                ("good_failed_share", ("checking", "good_failed_share")),
                ("accepted_quality_share", ("market", "accepted_quality_share")),
                ("days_to_fix", ("market", "days_to_fix")),
                ("mean_price", ("market", "mean_price")),
                ("false_duplicates", ("market", "false_duplicates")),  # #64
                ("duplicate_appeals_won", ("market", "duplicate_appeals_won")),
                ("late", ("market", "late")))


def _dig(r: dict, path: tuple):
    for k in path:
        if not isinstance(r, dict):
            return None
        r = r.get(k, 0 if k in ("paid", "unsolved") else None)
    return r


def mode_metrics(base: list[dict]) -> dict:
    """What a mode costs and buys, over its base market runs: means with standard errors (#60 D7)."""
    out = {}
    for key, path in MODE_METRICS:
        vals = [v for v in (_dig(r, path) for r in base) if v is not None]
        if vals:
            m, se = _mean_se(vals)
            out[key] = {"mean": round(m, 4), "standard_error": round(se, 4), "seeds": len(vals)}
    return out


def _mode_row(result: dict) -> dict:
    return {"passed": result["passed"], "failed_criteria": sorted({f["criterion"] for f in result["failures"]}),
            **{k: v["mean"] for k, v in mode_metrics(result["runs"]["market"]).items()}}


def summarize_modes(seeds, weeks: int = WEEKS, sweep_seeds=None) -> dict:
    """Every award mode's verdict on `seeds`, with the award-mode attacks, and what each costs and buys; sweeps of
    the race's and the claim's assumptions on `sweep_seeds` (#60 D8)."""
    from ..params import AWARD_MODES
    seeds = list(seeds)
    sweep = list(sweep_seeds) if sweep_seeds is not None else seeds
    out: dict = {"seeds": len(seeds), "sweep_seeds": len(sweep), "weeks": weeks, "modes": {}, "sweeps": {}}
    for mode in AWARD_MODES:
        result = acceptance(seeds, MARKET.with_(award_mode=mode), weeks, only=SCENARIOS + MODE_ATTACKS)
        out["modes"][mode] = {"passed": result["passed"], "failures": result["failures"],
                              "criteria": result["criteria"], "headline": _headline(result),
                              "compare": mode_metrics(result["runs"]["market"])}
    for mode in ("race", "claim"):
        p, rows = MARKET.with_(award_mode=mode), {}
        rows["attempt cost (cost per line)"] = {
            str(v): _mode_row(acceptance(sweep, p, weeks, only=("market",), cost_per_line=v))
            for v in (MICRO // 10, MICRO // 2, MICRO, 2 * MICRO)}
        if mode == "race":  # #64: what nothing-is-free costs, and the false duplicates
            rows["attempt fee"] = {str(v): _mode_row(acceptance(sweep, p.with_(attempt_fee=v), weeks, only=("market",)))
                                   for v in (MICRO // 10, MICRO // 2, 2 * MICRO)}
            rows["false duplicates"] = {
                str(v): _mode_row(acceptance(sweep, p, weeks, only=("market",), duplicate_false_bps=v))
                for v in (0, 500, 2_000)}
            rows["duplicate appeal jury"] = {
                str(v): _mode_row(acceptance(sweep, p.with_(duplicate_appeal_jury=v), weeks, only=("market",)))
                for v in (3, 5)}
        for label, key, vals in (("gate accuracy", "gate_accuracy_bps", (200, 500, 1_000)),
                                 ("gate bar", "gate_bar_bps", (6_000, 7_000, 8_000)),
                                 ("registration fee", "registration_fee", (MICRO // 2, 2 * MICRO, 5 * MICRO)),
                                 ("top-ups per week", "top_up_bps_per_week", (0, 1_000))):
            rows[label] = {str(v): _mode_row(acceptance(sweep, p.with_(**{key: v}), weeks, only=("market",)))
                           for v in vals}
        out["sweeps"][mode] = rows
    return out



# ---------- the reporter's and the solver's split (#56 D13) ----------

# finder_fee_bps values swept: the reporter's share of what a bounty pays out, f / (1 + f), is 4.8 % (the value before
# #56), 10 %, 12.5 %, 15 % (the default since #56), 20 %, 25 %, 33 % and 50 % (the reporter as much as the solver)
SPLIT_SHARES = (500, 1_111, 1_429, 1_765, 2_500, 3_333, 5_000, 10_000)


def _unchecked(params: Params, **changes) -> Params:
    """A copy with values set past validation: the sweep measures finder's fees above the market fee, which a
    published set with a treasury refuses (#34). Never published or used outside the sweep."""
    p = copy.copy(params)
    for key, value in changes.items():
        object.__setattr__(p, key, value)
    return p


def split_sweep(seeds, weeks: int = WEEKS, shares=SPLIT_SHARES) -> dict:
    """What the reporter's share of a bounty's payout does to fixes, cost and each side's earnings, in the default race
    and in the contract's shape (the owner asked whether 50/50 is right, 2026-10-26). Means with standard errors over
    the seeds, per reporter share of the payout."""
    def row(p: Params) -> dict:
        base = [market_report(run("market", s, p, weeks=weeks), "market", s) for s in seeds]
        flood = [market_report(run("market_flood", s, p, weeks=weeks), "market_flood", s) for s in seeds]
        farm = [market_report(run("market_farm", s, p, weeks=weeks), "market_farm", s) for s in seeds]
        values = {
            "bounties_paid": [r["market"]["bounties"].get("paid", 0) for r in base],
            "days_to_fix": [r["market"]["days_to_fix"] for r in base if r["market"]["days_to_fix"] is not None],
            "funder_cost_per_paid_bounty": [r["market"]["funder_cost_per_paid_bounty"] for r in base
                                            if r["market"]["funder_cost_per_paid_bounty"] is not None],
            "solver_net_of_effort": [r["returns"]["solver"]["net_of_effort"] for r in base],
            "reporter_net": [r["returns"]["reporter"]["net_of_effort"] for r in base],
            "flood_net": [r["returns"]["flood"]["net_of_effort"] for r in flood],
            "farm_net": [r["market"]["group_net_of_effort"].get("farm", 0) for r in farm],
        }
        out = {}
        for key, vals in values.items():
            m, se = _mean_se(vals)
            out[key] = {"mean": round(m, 2), "standard_error": round(se, 2)}
        return out

    from ..params import CONTRACT
    out: dict = {"seeds": len(seeds), "weeks": weeks, "configs": {}}
    for name, base in (("default", MARKET), ("contract", CONTRACT)):
        out["configs"][name] = {f"{f / (BPS + f):.3f}": dict(finder_fee_bps=f, **row(_unchecked(base, finder_fee_bps=f)))
                                for f in shares}
    return out


# ---------- the token emission (#58 D5-D8) ----------

TOKEN_PRICES = (0.0, 0.01, 0.05, 0.2)  # credits a token: a week's emission worth 0, 0.2x, 1x and 4x a week's coin to
# solvers in the run without tokens (D5)
OWNER_SUPPLY_CAP_BPS = 2_000  # the most of the supply the owner may hold, founder's share and its own mints (D7)
WEIGHT_CATCH_RATES = (7_000, 9_000, 9_900)  # the merge check's catch rate, swept (D3 risks)
LAUNCH_SOLVERS = 2  # with the owner, 3 solvers race in the thin launch (D6)
INFLATION_TOLERANCES = (150, 200, 300)  # a reporter forfeits above this % of the merge estimate: swept at 90 % caught


def _founder_options(params: Params) -> dict[str, Params]:
    """The founder options compared in the thin launch (D2): the share, the genesis (2 periods' emission), both, none, and
    the 5 % of tokens-v1 (the owner chose 1 %, 2026-10-29)."""
    genesis = 2 * params.token_emission_per_period
    return {"share": params, "genesis": params.with_(founder_share_bps=0, founder_genesis=genesis),
            "both": params.with_(founder_genesis=genesis), "none": params.with_(founder_share_bps=0),
            "share_5pct (tokens-v1)": params.with_(founder_share_bps=500)}


def _stat(vals: list[float], digits: int = 4) -> dict | None:
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    m, se = _mean_se(vals)
    return {"mean": round(m, digits), "standard_error": round(se, digits), "seeds": len(vals)}


def _pair_stats(pairs: list[tuple[float, float]], digits: int = 4) -> dict | None:
    """The attack minus its twin, seed by seed."""
    return _stat([a - b for a, b in pairs if a is not None and b is not None], digits)


def _forfeited(runs: list[dict], who: str) -> float | None:
    """The share of reported paid bounties whose reporters forfeited their share for inflation, pooled over runs."""
    rows = [r["tokens"]["inflation_forfeits"] for r in runs if r.get("tokens")]
    closes = sum(x[who] for x in rows)
    return round(sum(x[f"{who}_forfeited"] for x in rows) / closes, 4) if closes else None


def _outsiders(world: MarketWorld) -> float:
    """Solvers outside the ring: their mean net of effort, coin and tokens."""
    out = [a for a in world.solvers if a.kind == "solver" and a.cohort != "ring"]
    return mean(world.net_of_effort(a) for a in out) / MICRO if out else 0.0


def _ring_effects(seeds, params: Params, weeks: int, price: float) -> dict:
    """#58: who pays for a ring's gain. Each ring against the same accounts racing each other: the ring's gain, the
    outsiders' earnings, funders' cost per fix, bounties paid and days to fix."""
    out = {}
    for size in RING_SIZES:
        pairs = []
        for s in seeds:
            worlds = [run("market_ring", s, params, weeks, token_price=price, ring_size=size, honest_ring=honest)
                      for honest in (False, True)]
            pairs.append([(w, market_report(w, "market_ring", s)) for w in worlds])
        def change(f, digits=2):
            return _pair_stats([(f(*a), f(*b)) for a, b in pairs], digits)
        out[str(size)] = {
            "ring_gain": change(lambda w, r: r["market"]["group_net_of_effort"].get("ring", 0)),
            "outsider_change": change(lambda w, r: r["market"]["outsider_net_of_effort"]),
            "funder_cost_change": change(lambda w, r: r["market"]["funder_cost_per_paid_bounty"] or 0),
            "bounties_paid_change": change(lambda w, r: r["market"]["bounties"].get("paid", 0)),
            "days_to_fix_change": change(lambda w, r: r["market"]["days_to_fix"] or 0)}
    return out


def _token_metrics(runs: list[dict]) -> dict:
    """What the tokens buy and cost, over the base market runs (D7's figures)."""
    def tok(r, *path):
        x = r.get("tokens") or {}
        for k in path:
            x = x.get(k) if isinstance(x, dict) else None
        return x
    out = {
        "bounties_paid": _stat([r["market"]["bounties"].get("paid", 0) for r in runs], 2),
        "funder_cost_per_paid_bounty": _stat([r["market"]["funder_cost_per_paid_bounty"] for r in runs], 2),
        "solver_earnings": _stat([r["returns"]["solver"]["net_of_effort"] for r in runs], 2),
        "reporter_earnings": _stat([r["returns"]["reporter"]["net_of_effort"] for r in runs], 2),
        "days_to_fix": _stat([r["market"]["days_to_fix"] for r in runs], 2),
        "wasted_share": _stat([r["market"]["wasted_share"] for r in runs]),
        "treasury_spend": _stat([r["market"]["treasury_spend"] for r in runs], 2),
    }
    if any(r.get("tokens") for r in runs):
        out.update({
            "zero_coin_opened": _stat([tok(r, "zero_coin", "opened") for r in runs], 2),
            "zero_coin_fixed": _stat([tok(r, "zero_coin", "fixed") for r in runs], 2),
            "zero_coin_fixed_share": _stat([tok(r, "zero_coin", "fixed_share") for r in runs]),
            "supply": _stat([tok(r, "supply") for r in runs], 2),
            "owner_supply_share": _stat([tok(r, "owner_supply_share") for r in runs]),
            "honest_forfeited_share": _forfeited(runs, "honest"),
            "tokens_conserved": all(tok(r, "conserved") for r in runs),
            "tokens_by_weight": all(tok(r, "by_weight") for r in runs),
            "kinds": {k: {key: _stat([tok(r, "kinds", k, key) or 0.0 for r in runs]) for key in
                          ("tokens_share", "weight_share")}
                      for k in sorted({k for r in runs for k in (tok(r, "kinds") or {})})},
        })
    return out


def _cohort(r: dict, key: str):
    return ((r.get("tokens") or {}).get("cohorts", {}).get("attack") or {}).get(key)


def _per_effort(r: dict) -> tuple[float | None, float | None]:
    """The attack cohort's tokens and earnings per credit of its work."""
    effort = _cohort(r, "effort")
    if not effort:
        return None, None
    earnings = r["market"]["group_net_of_effort"].get("attack", 0) + effort
    return round(_cohort(r, "tokens") / effort, 4), round(earnings / effort, 4)


def token_acceptance(seeds, price: float, params: Params = TOKENS, weeks: int = WEEKS) -> dict:
    """Every earlier market criterion with the emission on at this token price, and #58's: the owner's coin and tokens
    don't gain by defecting (market_owner, already among the earlier criteria with tokens counted in its payout), and
    its share of the supply stays below OWNER_SUPPLY_CAP_BPS in token_market and token_owner (D7)."""
    seeds = list(seeds)
    result = acceptance(seeds, params, weeks, only=SCENARIOS + MODE_ATTACKS, token_price=price)
    runs = result["runs"]
    for name in ("market", "market_owner", "market_owner:variant"):
        shares = [r["tokens"]["owner_supply_share"] for r in runs.get(name, [])]
        stat = _stat(shares)
        if stat is None:
            continue
        result["criteria"][f"owner_supply_share:{name}"] = {**stat, "max": max(shares)}
        if stat["mean"] + 2 * stat["standard_error"] >= OWNER_SUPPLY_CAP_BPS / BPS:
            result["failures"].append({"criterion": "the owner's supply share stays below its cap", "scenario": name,
                                       "seed": "all", "detail": f"{stat['mean']:.4f} ± {stat['standard_error']:.4f}"})
    for name, rs in runs.items():
        for r, seed in zip(rs, seeds * (len(rs) // max(1, len(seeds)))):
            t = r.get("tokens") or {}
            if not t.get("conserved") or not t.get("by_weight"):
                result["failures"].append({"criterion": "tokens follow weighted work, and only closes mint them",
                                           "scenario": name, "seed": seed, "detail": "a mint is off its weight"})
    result["passed"] = not result["failures"]
    return result


def tokens_summary(seeds, weeks: int = WEEKS, prices=None, params: Params = TOKENS) -> dict:
    """#58 D8: the market without tokens, then with the emission on at each swept price: every earlier criterion and
    #58's, what tokens buy and cost, the self-funding coder, the importance inflater (and the merge check's catch rate
    swept), the thin launch under each founder option, and the owner's share of the supply."""
    seeds, prices = list(seeds), TOKEN_PRICES if prices is None else prices
    base = acceptance(seeds, MARKET, weeks, only=SCENARIOS + MODE_ATTACKS)
    out: dict = {"seeds": len(seeds), "weeks": weeks, "prices": list(prices),
                 "emission_per_period": params.token_emission_per_period / MICRO,
                 "without": {"passed": base["passed"], "failed_criteria": sorted({f["criterion"] for f in base["failures"]}),
                             "criteria": base["criteria"], "metrics": _token_metrics(base["runs"]["market"])},
                 "at": {}}
    for price in prices:
        result = token_acceptance(seeds, price, params, weeks)
        row: dict = {"passed": result["passed"], "failures": result["failures"],
                     "failed_criteria": sorted({f["criterion"] for f in result["failures"]}),
                     "headline": _headline(result), "criteria": result["criteria"],
                     "owner_gain": result["criteria"].get("owner_gain"),
                     "owner_supply_share": {k.split(":", 1)[1]: v for k, v in result["criteria"].items()
                                            if k.startswith("owner_supply_share:")},
                     "metrics": _token_metrics(result["runs"]["market"])}
        self_ = [(market_report(run("token_self", s, params, weeks, token_price=price), "token_self", s),
                  market_report(run("token_self", s, params, weeks, token_price=price, honest_attack=True),
                                "token_self", s)) for s in seeds]
        row["token_self"] = {
            "tokens_per_effort": _stat([_per_effort(a)[0] for a, _ in self_]),
            "earnings_per_effort": _stat([_per_effort(a)[1] for a, _ in self_]),
            "twin_tokens_per_effort": _stat([_per_effort(b)[0] for _, b in self_]),
            "twin_earnings_per_effort": _stat([_per_effort(b)[1] for _, b in self_]),
            "gain_against_twin": _pair_stats([(a["market"]["group_net_of_effort"].get("attack", 0),
                                               b["market"]["group_net_of_effort"].get("attack", 0)) for a, b in self_], 2)}
        row["token_inflate"] = {}
        sweep = [(catch, params.weight_inflation_pct) for catch in WEIGHT_CATCH_RATES] + [
            (9_000, pct) for pct in INFLATION_TOLERANCES if pct != params.weight_inflation_pct]
        for catch, pct in sweep:
            p = params.with_(weight_inflation_pct=pct)
            pairs = [(market_report(run("token_inflate", s, p, weeks, token_price=price,
                                        weight_check_catch_bps=catch), "token_inflate", s),
                      market_report(run("token_inflate", s, p, weeks, token_price=price, honest_attack=True,
                                        weight_check_catch_bps=catch), "token_inflate", s)) for s in seeds]
            key = str(catch) if pct == params.weight_inflation_pct else f"{catch}@{pct}%"
            row["token_inflate"][key] = {
                "inflater_forfeited_share": _forfeited([a for a, _ in pairs], "inflated"),
                "honest_forfeited_share": _forfeited([x for pair in pairs for x in pair], "honest"),
                "extra_tokens_per_true_weight": _pair_stats([(_cohort(a, "tokens_per_true_weight"),
                                                              _cohort(b, "tokens_per_true_weight")) for a, b in pairs]),
                "twin_tokens_per_true_weight": _stat([_cohort(b, "tokens_per_true_weight") for _, b in pairs]),
                "gain_against_twin": _pair_stats([(a["market"]["group_net_of_effort"].get("attack", 0),
                                                   b["market"]["group_net_of_effort"].get("attack", 0))
                                                  for a, b in pairs], 2)}
        row["rings"] = _ring_effects(seeds, params, weeks, price)
        row["token_launch"] = {}
        for option, p in _founder_options(params).items():
            launch = [market_report(run("token_launch", s, p, weeks, token_price=price, solvers=LAUNCH_SOLVERS),
                      "token_launch", s) for s in seeds]
            by_period = [r["tokens"]["owner_supply_share_by_period"] for r in launch]
            longest = max((len(x) for x in by_period), default=0)
            row["token_launch"][option] = {
                "owner_supply_share": _stat([r["tokens"]["owner_supply_share"] for r in launch]),
                "owner_supply_share_by_minting_period": [
                    round(mean(x[i] for x in by_period if len(x) > i), 4) for i in range(longest)],
                "owner_earnings": _stat([r["owner_payout"] for r in launch], 2),
                "bounties_paid": _stat([r["market"]["bounties"].get("paid", 0) for r in launch], 2),
                "zero_coin_fixed_share": _stat([r["tokens"]["zero_coin"]["fixed_share"] for r in launch])}
        out["at"][str(price)] = row
    return out
