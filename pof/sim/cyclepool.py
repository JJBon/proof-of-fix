"""Cycle pools per repository, paid by merit, and inflated merit healed (proof-of-fix#184; simulation only, rule 1).

The owner (2026-11-08), for the paper: each repository has a pool each cycle, funded by investors who hold shares in
proportion to what they brought. At the cycle's end judges split the pool's coin among the merged fixes by merit. The
worst case is a project's own team overclaiming its fixes: correct fixes, every test passing, presented as far more
important than they are. Three defences heal it:

- **Judges' scores.** A judge whose merit score is found inflated loses score (`penalty`), so it is drawn less, and
  paid less: judges are paid a flat fee per draw. Scores recover slowly (`recovery`); below `floor` a judge is out.
- **Challenges before the split.** Issues can be filed at any time. An investor who sees an overclaimed fix files an
  issue against its merit (`challenge`, at `challenge_cost` for the AI check and gas). The challenge is AI-checked
  (`challenge_detect`). Upheld, the fix's merit is corrected before the split, its judges lose score, the team forfeits
  its stake, and the challenger is paid `challenge_reward` of the overpayment it stopped. Honest fixes are challenged
  too, by mistake (`false_challenge`), and the check wrongly upholds a few of those.
- **After the split.** Random audits re-judge paid fixes with a fresh panel (`audit`, #132), and later bug reports or
  usage contradict an inflated merit (`later`). Both cost the judges score and the team its stake, but the coin is
  already paid: they heal the future, not the cycle.

Judges' scores are by consensus with the final merit, corrected by any challenge: a score more than `inflation` times
off either way loses score, agreeing regains a little. A judge below the floor is replaced by a newcomer of the same
kind; colluders come back under a new identity, for a new bond. Stakes are forfeited by #58 D3's rule: a claimed
importance over `inflation` times the merit awarded.

The team overclaims `fakes` fixes each cycle, at whichever claim pays it best under each defence (`CLAIMS`). Colluding
judges always accept its claims and judge everything else honestly. Prices aren't modelled: everything is in the pool's
coin, and investors' shares only matter as who pays the pool."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace
from statistics import mean, median
from typing import List, Optional, Sequence


@dataclass(frozen=True)
class Params:
    cycles: int = 52
    pool: float = 2_000.0  # investors' coin a cycle
    honest_fixes: float = 10.0  # a cycle (Poisson)
    value_median: float = 86.0  # an honest fix's true merit, in coin (the market's bounties, reports/self-healing-v1)
    value_p90: float = 184.0
    noise: float = 0.15  # a judge's error comparing fixes (multiplicative)
    fakes: int = 5  # the team's overclaimed fixes a cycle
    claim: float = 200.0  # the merit it claims for each
    true_fake: float = 5.0  # what each is worth
    validators: int = 15
    colluders: int = 0  # of the validators, judges who always accept the team's claims
    k: int = 3  # judges a panel
    detect: float = 0.8  # an honest judge sees through an overclaim
    challenge: float = 0.0  # an overclaimed fix the panel passed is challenged before the split
    challenge_detect: float = 0.9  # the AI check upholds a real overclaim (one focused question)
    challenge_cost: float = 3.0  # the challenger's AI check and gas
    challenge_reward: float = 0.1  # of the overpayment an upheld challenge stops, to the challenger, from the pool
    false_challenge: float = 0.1  # of `challenge`: the rate honest fixes are challenged by mistake
    audit: float = 0.0  # a paid fix is re-judged by a fresh panel after the split
    later: float = 0.0  # a later report or usage reveals an overclaim after the split
    penalty: float = 0.0  # a judge's score is multiplied by 1 - penalty for each inflated score found
    recovery: float = 0.02  # score regained for each judgment that agrees with the final merit, up to 1
    floor: float = 0.05  # judges below this score are out, replaced by a newcomer of the same kind
    newcomer: float = 0.2  # a newcomer's starting score: it earns the rest by agreeing with final merits
    bond: float = 250.0  # a judge's bond (#132): the team posts a new one for each colluder it brings back
    stake: float = 0.0  # refundable stake to open an issue, forfeited (to the pool) when its merit is found inflated
    inflation: float = 3.0  # forfeited when the claimed importance is over this times the merit awarded (#58 D3)
    claim_error: float = 0.3  # an honest fixer's error estimating its own fix's importance (#58: the AI estimate's)
    entry: float = 3.5  # an issue's AI check and gas, plus the fix's checks


@dataclass(eq=False)  # judges are told apart by identity, not by their fields
class Judge:
    colluding: bool
    score: float = 1.0


@dataclass
class Result:
    team_profit: List[float] = field(default_factory=list)  # a cycle
    investors_loss: float = 0.0  # coin paid to the team beyond its fixes' true merit: investors' money that didn't pay
    # for work, and honest fixers' pay that went to the team instead (the pool is fixed)
    pool_total: float = 0.0
    honest_fixers_loss: float = 0.0  # their own losses: mistaken challenges upheld, and stakes forfeited by honest claims
    challengers_net: float = 0.0  # rewards less costs
    colluders_draw_share: List[float] = field(default_factory=list)  # a cycle: of all draws
    honest_judges_score: float = 0.0  # at the end, mean
    replaced: int = 0  # judges who fell below the floor and were replaced


def _value(rng: random.Random, p: Params) -> float:
    mu = math.log(p.value_median)
    return rng.lognormvariate(mu, (math.log(p.value_p90) - mu) / 1.2816)


def _poisson(rng: random.Random, lam: float) -> int:
    n, q, limit = 0, 1.0, math.exp(-lam)
    while True:
        q *= rng.random()
        if q <= limit:
            return n
        n += 1


class Sim:
    def __init__(self, seed: int, p: Params):
        self.p, self.rng = p, random.Random(seed * 7_919 + 184)
        self.judges = [Judge(colluding=i < p.colluders) for i in range(p.validators)]
        self.r = Result()
        self.drawn = [0, 0]  # this cycle: draws of colluding judges, all draws
        self.bonds = 0.0  # this cycle: bonds the team posts for colluders brought back

    def panel(self) -> List[Judge]:
        # a judge below the floor leaves, and a newcomer of the same kind takes its seat at half score: honest
        # validators join an open network, and colluders come back under a new identity (the pessimistic case)
        for i, j in enumerate(self.judges):
            if j.score < self.p.floor:
                self.judges[i] = Judge(colluding=j.colluding, score=self.p.newcomer)
                self.r.replaced += 1
                if j.colluding:
                    self.bonds += self.p.bond  # the team bonds a new identity; the old one's bond is slashed
        active = self.judges
        chosen: List[Judge] = []
        for _ in range(min(self.p.k, len(active))):
            pick = self.rng.choices([j for j in active if j not in chosen],
                                    weights=[j.score for j in active if j not in chosen])[0]
            chosen.append(pick)
        for j in chosen:
            self.drawn[0] += j.colluding
            self.drawn[1] += 1
        return chosen

    def score_fake(self, j: Judge) -> float:
        """One judge's merit for an overclaimed fix: the claim, or its true worth if it sees through it."""
        sees = not j.colluding and self.rng.random() < self.p.detect
        return (self.p.true_fake if sees else self.p.claim) * math.exp(self.rng.gauss(0, self.p.noise))

    def punish(self, judges: Sequence[Judge], scores: Sequence[float]) -> None:
        """The judges whose score for a fix found overclaimed was above its true worth."""
        for j, s in zip(judges, scores):
            if s > self.p.inflation * self.p.true_fake:
                j.score *= 1 - self.p.penalty

    def cycle(self) -> None:
        p, rng, r = self.p, self.rng, self.r
        self.drawn, self.bonds = [0, 0], 0.0
        merits, owners, panels, truth, claims = [], [], [], [], []  # owners: "h" honest, "t" the team
        for _ in range(_poisson(rng, p.honest_fixes)):
            v = _value(rng, p)
            js = self.panel()
            scores = [v * math.exp(rng.gauss(0, p.noise)) for _ in js]
            merits.append(median(scores))
            owners.append("h"), panels.append((js, scores)), truth.append(v)
            claims.append(v * math.exp(rng.gauss(0, p.claim_error)))  # an honest estimate of its own importance
        for _ in range(p.fakes):
            js = self.panel()
            scores = [self.score_fake(j) for j in js]
            merits.append(median(scores))
            owners.append("t"), panels.append((js, scores)), truth.append(p.true_fake)
            claims.append(p.claim)
        cost = p.fakes * p.entry
        stopped_total = 0.0
        wronged: List[int] = []
        # challenges, before the split: against a team fix the panel passed at an inflated merit
        for i, owner in enumerate(owners):
            if owner == "t" and merits[i] > 2 * p.true_fake and rng.random() < p.challenge:
                r.challengers_net -= p.challenge_cost
                if rng.random() < p.challenge_detect:
                    stopped_total += merits[i] - p.true_fake
                    merits[i] = p.true_fake
            elif owner == "h" and rng.random() < p.challenge * p.false_challenge:
                r.challengers_net -= p.challenge_cost
                if rng.random() < (1 - p.challenge_detect) / 2:  # wrongly upheld
                    merits[i] *= 0.5
                    wronged.append(i)
        # the judges' scores, by consensus with the final merit (corrected by any challenge): far from it either way
        # (over `inflation` times) loses score; agreeing regains a little
        if p.penalty:
            for (js, scores), m in zip(panels, merits):
                for j, sc in zip(js, scores):
                    if sc > p.inflation * m or sc * p.inflation < m:
                        j.score *= 1 - p.penalty
                    else:
                        j.score = min(1.0, j.score + p.recovery)
        # stakes: forfeited when the claim is over `inflation` times the merit awarded (#58 D3's rule)
        forfeited = 0.0
        for i, owner in enumerate(owners):
            if p.stake and claims[i] > p.inflation * merits[i]:
                forfeited += p.stake
                if owner == "t":
                    cost += p.stake
                else:
                    r.honest_fixers_loss += p.stake
        # the split
        total = sum(merits)
        pool = p.pool + forfeited
        pay = [pool * m / total for m in merits] if total else [0.0] * len(merits)
        true_total = sum(truth)
        fair = [p.pool * t / true_total for t in truth] if true_total else [0.0] * len(truth)
        r.honest_fixers_loss += sum(pay[i] for i in wronged)  # their merit was halved: about this much lost
        reward = 0.0
        if stopped_total and total:
            reward = p.challenge_reward * pool * stopped_total / (total + stopped_total)
            r.challengers_net += reward
        team = sum(x for x, o in zip(pay, owners) if o == "t")
        r.investors_loss += team - sum(x for x, o in zip(fair, owners) if o == "t") + reward
        r.pool_total += p.pool
        # after the split: the coin is paid; judges lose score and the team its stake
        for i, owner in enumerate(owners):
            if owner != "t" or merits[i] <= 2 * p.true_fake:
                continue
            found = rng.random() < p.later
            if not found and rng.random() < p.audit:
                fresh = self.panel()
                found = sum(1 for j in fresh if self.score_fake(j) <= 2 * p.true_fake) * 2 > len(fresh)
            if found:
                self.punish(*panels[i])
                if p.stake and p.claim > p.inflation * p.true_fake:
                    cost += p.stake
        r.team_profit.append(team - cost - self.bonds)
        r.colluders_draw_share.append(self.drawn[0] / max(1, self.drawn[1]))

    def run(self) -> Result:
        for _ in range(self.p.cycles):
            self.cycle()
        honest = [j.score for j in self.judges if not j.colluding]
        self.r.honest_judges_score = mean(honest) if honest else 0.0
        return self.r


def run(seed: int, p: Params = Params()) -> Result:
    return Sim(seed, p).run()


DEFENCES = [
    ("no defence", {}),
    ("judges' scores (consensus) and audits of 10 % of paid fixes", {"penalty": 0.5, "audit": 0.10}),
    ("judges' scores, from audits and later reports (10 % each)", {"penalty": 0.5, "audit": 0.10, "later": 0.10}),
    ("challenges before the split (half of overclaims)", {"challenge": 0.5}),
    ("challenges + scores + audits", {"challenge": 0.5, "penalty": 0.5, "audit": 0.10, "later": 0.10}),
    ("challenges + scores + audits + a $50 refundable stake",
     {"challenge": 0.5, "penalty": 0.5, "audit": 0.10, "later": 0.10, "stake": 50.0}),
]


CLAIMS = (15.0, 50.0, 200.0)  # a $5 fix claimed at 3x (within the rule), 10x and 40x


def report(seeds: Sequence[int], base: Params = Params(), colluders: Sequence[int] = (0, 3, 5, 8)) -> str:
    out = []
    for c in colluders:
        out += [f"\n#### {c} of {base.validators} judges colluding with the team "
                f"(honest judges see through an overclaim {base.detect:.0%} of the time)\n",
                "| Defence | The team's best claim | Its profit, first quarter → last | Team's profit a year | Overpaid to the team (of the pool) | "
                "Colluders' share of draws, last quarter | Honest fixers' loss | Challengers' net | "
                "Honest judges' score |", "|---|---|---|---|---|---|---|---|---|"]
        for name, kw in DEFENCES:
            options = []
            for claim in CLAIMS:  # the team claims whatever pays it best under this defence
                p = replace(base, colluders=c, claim=claim, **kw)
                rs = [run(s, p) for s in seeds]
                options.append((mean(sum(x.team_profit) for x in rs), claim, rs))
            _, claim, rs = max(options, key=lambda o: o[0])
            q1 = mean(sum(x.team_profit[:13]) for x in rs)
            q4 = mean(sum(x.team_profit[-13:]) for x in rs)
            heal = f"{q1:,.0f} → {q4:,.0f}"
            out.append(
                f"| {name} | ${claim:g} | {heal} | {mean(sum(x.team_profit) for x in rs):,.0f} | "
                f"{mean(x.investors_loss / x.pool_total for x in rs):.1%} | "
                f"{mean(mean(x.colluders_draw_share[-13:]) for x in rs):.0%} | "
                f"{mean(x.honest_fixers_loss for x in rs):,.0f} | {mean(x.challengers_net for x in rs):,.0f} | "
                f"{mean(x.honest_judges_score for x in rs):.2f} |")
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python3 -m pof.sim.cyclepool")
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--detect", type=float, default=Params().detect)
    a = ap.parse_args(argv)
    print(report(range(1, a.seeds + 1), replace(Params(), detect=a.detect)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
