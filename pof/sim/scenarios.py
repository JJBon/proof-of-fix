"""The published scenarios (specs/incentive-simulation; tasks 7.2): who is in the project, with what behaviour."""

from __future__ import annotations

from dataclasses import replace

from .. import credits
from ..params import LEGACY, Params
from . import actors as A
from .actors import Actor
from .baseline import load, size_sampler, weekly_volume
from .world import World

WEEKS = 8


def _people(kind: str, behaviour: A.Behaviour, n: int, group: str | None = None,
            cohort: str | None = None) -> list[Actor]:
    return [Actor(f"{kind}-{i + 1}", kind, behaviour, group=group, cohort=cohort or group) for i in range(n)]


def honest_population(owner: A.Behaviour = A.OWNER_HONEST) -> list[Actor]:
    return (_people("honest", A.HONEST, 10) + _people("hunter", A.HUNTER, 3) + _people("validator", A.VALIDATOR, 12)
            + [Actor("owner", "owner", owner)])


def build(name: str, seed: int, params: Params = LEGACY, baseline: dict | None = None, **knobs) -> World:
    """A World for one scenario and seed, not yet run."""
    baseline = baseline or load()
    sampler = size_sampler(baseline)
    if name == "honest":
        people = honest_population()
    elif name == "spam":
        # the splitter's counterfactual submits the same changes unsplit (one PR of 8x the lines)
        splitter = replace(A.SPLITTER, split_into=1, pad_factor=8) if knobs.get("unsplit") else A.SPLITTER
        people = (honest_population() + _people("spammer", A.SPAMMER, 3) + _people("splitter", splitter, 1)
                  + _people("padder", A.PADDER, 1) + _people("stacker", A.STACKER, 1)
                  + _people("gamer", A.INDEX_GAMER, 1))
    elif name == "griefing":
        people = honest_population() + _people("griefer", A.GRIEFER, 3)
    elif name == "collusion":
        # colluders hold `share` of all validator stake, and protect one allied spammer's contributions
        share = knobs.get("share", 0.3)
        honest_stake = 13 * A.VALIDATOR.validator_stake  # 12 validators + the owner
        k = 4
        each = max(1, int(share / (1 - share) * honest_stake / k)) if share < 1 else honest_stake
        colluder = replace(A.COLLUDER, validator_stake=each, endowment=each + credits(100))
        group = None if knobs.get("honest_ring") else "ring"  # the counterfactual: same people acting honestly
        people = honest_population() + _people("colluder", colluder, k, group=group, cohort="ring") + \
            _people("ally", A.SPAMMER, 1, group=group, cohort="ring")
    elif name == "owner":
        owner = A.OWNER_SELF_INTERESTED if knobs.get("self_interested") else A.OWNER_HONEST
        people = honest_population(owner)
    elif name == "risk":
        multiplier = knobs.get("multiplier", 1)
        params = params.with_(risk_multiplier={"normal": 1, "high": multiplier})
        risky = replace(A.HONEST, high_risk_bps=2_000)
        people = (_people("honest", risky, 10) + _people("hunter", A.HUNTER, 3) + _people("validator", A.VALIDATOR, 12)
                  + [Actor("owner", "owner", A.OWNER_HONEST)] + _people("spammer", replace(A.SPAMMER, high_risk_bps=2_000), 3))
    elif name == "sponsorship":
        # sponsored newcomers, and an abuser who sponsors fake accounts that spam (the counterfactual: no sybils)
        people = honest_population()
        for i in range(3):
            people.append(Actor(f"newcomer-{i + 1}", "newcomer", A.NEWCOMER, sponsor=people[i]))
        # three abusers, each with its own fake accounts, so the abuser group is big enough to judge (proof-of-fix#27)
        for j in range(3):
            abuser = Actor(f"abuser-{j + 1}", "abuser", A.ABUSER, cohort="abuse")
            people.append(abuser)
            if not knobs.get("no_sybils"):
                people += [Actor(f"sybil-{4 * j + i + 1}", "sybil", A.SYBIL, sponsor=abuser, cohort="abuse")
                           for i in range(4)]
    elif name == "replay":
        # GridCraft's real volume: contributors sized so the weekly total matches the baseline
        authors = 40
        rate = weekly_volume(baseline) / authors
        people = _people("honest", replace(A.HONEST, submissions_per_week=rate), authors) + \
            _people("hunter", A.HUNTER, 5) + _people("validator", A.VALIDATOR, 20) + [Actor("owner", "owner", A.OWNER_HONEST)]
    else:
        raise ValueError(f"unknown scenario {name!r}")
    owner = next((a for a in people if a.kind == "owner"), None)
    return World(params, seed, people, sampler, maintainer=owner, mechanism=knobs.get("mechanism", True),
                 hunt_elasticity=knobs.get("hunt_elasticity", 0.5),
                 review_detect_bps=knobs.get("review_detect_bps", 6_000))


def run(name: str, seed: int, params: Params = LEGACY, weeks: int = WEEKS, **knobs) -> World:
    world = build(name, seed, params, **knobs)
    return world.run(weeks * 7)


SCENARIOS = ("honest", "spam", "griefing", "collusion", "owner", "replay", "risk", "sponsorship")
COLLUSION_SHARES = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7)
RISK_MULTIPLIERS = (1, 2, 3)
