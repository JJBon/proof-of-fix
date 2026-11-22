"""The checking layer (specs/checking, proof-of-fix#43): signed re-runs of a delivery's deterministic checks, planted
cases with known answers, a jury of AI evaluators drawn one per operator and model family, and evaluators scored on
the truth (Brier), never on agreement.

Every job (a set of re-runs, or a jury) is commit-reveal: members commit a sealed digest, then reveal; nothing is
visible before the reveal. A job's `ref` names what it checks (`entry:<id>` for a delivery); a planted job carries
its known answer and is revealed on the ledger once settled. Work that held up is counted in units for the
validators' share (`take_work`); penalties go to insurance.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field

from . import BPS, share
from .challenges import ChallengeError, ValidatorSet
from .ledger import Ledger
from .params import Params


class CheckingError(ValueError):
    pass


def seal(*values: object) -> str:
    return hashlib.sha256(":".join(str(v) for v in values).encode()).hexdigest()


def constitution_passes(bar_bps: int, measured_bps: int, mutation_caught: bool) -> bool:
    """The project's constitution (#60): the attested runners' measures (coverage of the changed code, diff and
    performance limits) put the fix at `measured_bps` of quality, against the bar of the version the bounty was
    registered under; padded tests the mutation score caught fail it whatever the rest says. The AI juries' pass or
    fail is the delivery's other gate, decided as before."""
    return not mutation_caught and measured_bps >= bar_bps


@dataclass
class Evaluator:
    account: str
    operator: str
    family: str
    bond_account: str
    briers: list[float] = field(default_factory=list)  # every scored verdict, oldest first
    model: str = ""  # the listed model it means to run (#47); each verdict proves which model it really came from


@dataclass
class Runner:
    """An attested CI runner: an MCP test-runner service in a TEE, registered by an operator with a bond, on one
    hardware vendor's enclave (#43, owner 2026-10-25)."""
    account: str
    operator: str
    vendor: str
    bond_account: str


@dataclass
class Verdict:
    accepts: bool
    p: float  # the probability that the fix is good
    evidence: str
    proven: str | None = None  # the model its proof shows (a TEE attestation or a zkTLS proof, #47); None: none


@dataclass
class Job:
    id: int
    kind: str  # "rerun" | "jury"
    ref: str
    members: list[str]
    planted: bool | None = None  # a planted case's answer: checks pass / the fix is good; None for a real job
    shadow: list[str] = field(default_factory=list)  # jury: scored, never counted
    bonds: dict[str, str] = field(default_factory=dict)  # re-run member -> its bond account
    commits: dict[str, str] = field(default_factory=dict)
    reveals: dict[str, object] = field(default_factory=dict)  # re-run: bool (checks pass); jury: Verdict
    state: str = "open"  # open | closed | resolved
    outcome: object = None  # re-run: bool or None (no quorum); jury: "accept" | "reject" | "escalate"
    appeal: "Job | None" = None  # re-runs: the fresh re-runs a solver appealed to
    tier: int = 1  # a jury: 1, or 2 for the second, larger jury a split goes to
    fee_account: str | None = None  # an appeal's fee, held until it's settled


class Checking:
    def __init__(self, ledger: Ledger, params: Params, validators: ValidatorSet, insurance: str,
                 score_on_agreement: bool = False) -> None:
        self.ledger, self.params, self.validators, self.insurance = ledger, params, validators, insurance
        self.score_on_agreement = score_on_agreement  # the simulation's comparison only (#43 design D6)
        self.evaluators: dict[str, Evaluator] = {}
        self.model_accuracy: dict[str, float] = {}  # the published measurements; empty: no list (every model counts)
        self.runners: dict[str, Runner] = {}
        self.jobs: list[Job] = []
        self._work: dict[str, int] = {}

    # ---------- signed re-runs (design D1) ----------

    def start_reruns(self, ref: str, seed: str, exclude: set[str], day: int, planted: bool | None = None) -> Job:
        """Draw the re-runners like reviewers (stake-weighted, seeded, excluding the parties and linked accounts)
        and lock each one's review bond."""
        p = self.params
        if p.ci_mode == "attested":
            return self._job("rerun", ref, self._draw_runners(seed, exclude), planted)
        try:
            members = self.validators.select(p.rerun_validators, seed, exclude, min_balance=p.review_bond)
        except ChallengeError as err:
            raise CheckingError(str(err)) from err
        job = self._job("rerun", ref, members, planted)
        for m in members:
            job.bonds[m] = self.ledger.open("cbond")
            self.ledger.transfer(m, job.bonds[m], p.review_bond, "bond", self._ref(job), day)
        return job

    def register_runner(self, account: str, operator: str, vendor: str, day: int) -> Runner:
        if account in self.runners:
            raise CheckingError(f"{account} is already a runner")
        bond = self.ledger.open("rbond")
        self.ledger.transfer(account, bond, self.params.runner_bond, "bond", f"runner:{account}", day)
        r = self.runners[account] = Runner(account, operator, vendor, bond)
        return r

    def _draw_runners(self, seed: str, exclude: set[str]) -> list[str]:
        """The published number of attested runners in the order of a seeded shuffle, each from a different operator
        and hardware vendor, none excluded or linked, each with bond left."""
        barred = set(exclude)
        for account in exclude:
            barred |= self.validators.links.get(account, set())
        pool = sorted(a for a, r in self.runners.items() if a not in barred and self.ledger.balance(r.bond_account) > 0)
        random.Random(seed).shuffle(pool)
        members, operators, vendors = [], set(), set()
        for a in pool:
            r = self.runners[a]
            if r.operator in operators or r.vendor in vendors:
                continue
            members.append(a)
            operators.add(r.operator)
            vendors.add(r.vendor)
            if len(members) == self.params.ci_runners:
                return members
        raise CheckingError(f"only {len(members)} attested runners from distinct operators and vendors")

    def _quorum(self) -> int:
        return self.params.ci_runners if self.params.ci_mode == "attested" else self.params.rerun_quorum

    def _bond_base(self, member: str, planted: bool = False) -> tuple[str | None, int]:
        """Where a check result's penalty comes from, and the amount its share is of: a dissent (often a flaky test)
        costs a share of the small review bond; a wrong planted answer, a definite lie, a share of the runner's own
        bond."""
        if member in self.runners:
            return self.runners[member].bond_account, self.params.runner_bond if planted else self.params.review_bond
        return self.validators.stake_account.get(member), self.params.review_bond

    def commit(self, job: Job, member: str, digest: str) -> None:
        if job.state != "open" or (member not in job.members and member not in job.shadow):
            raise CheckingError(f"{member} can't commit to job {job.id}")
        if member in job.commits:
            raise CheckingError(f"{member} already committed to job {job.id}")
        job.commits[member] = digest

    def reveal_rerun(self, job: Job, member: str, passes: bool, secret: str) -> bool:
        """A re-run's result, checks pass or not. Returns whether it matched its commitment."""
        if job.kind != "rerun" or job.commits.get(member) != seal(passes, secret) or member in job.reveals:
            return False
        if len(job.commits) < len(job.members):
            raise CheckingError("reveals open once every member has committed")
        job.reveals[member] = passes
        return True

    def close_reruns(self, job: Job, day: int) -> bool | None:
        """The result a quorum reproduced, or None without a quorum (the caller re-runs with fresh validators). A
        result off the quorum, or none, loses the dissent share of the bond; a wrong planted answer loses the
        planted share. Matching results are units of work. Bonds' remainders return."""
        p = self.params
        if job.kind != "rerun" or job.state != "open":
            raise CheckingError(f"job {job.id} isn't open re-runs")
        votes = [job.reveals[m] for m in job.members if m in job.reveals]
        outcome = next((v for v in (True, False) if votes.count(v) >= self._quorum()), None)
        right = job.planted if job.planted is not None else outcome
        for m in job.members:
            got = job.reveals.get(m)
            held, base = (job.bonds[m], p.review_bond) if m in job.bonds else self._bond_base(m)
            if job.planted is not None and got is not None and got != job.planted:
                lied, lie_base = (job.bonds[m], p.review_bond) if m in job.bonds else self._bond_base(m, planted=True)
                self._take(lied, share(lie_base, p.planted_penalty_bps), job, day)
            elif got is None or (right is not None and got != right):
                self._take(held, share(base, p.rerun_dissent_penalty_bps), job, day)
            elif right is not None and job.planted is not None:  # the system's own case: insurance pays it
                self._pay(self.insurance, m, self.params.run_fee, job, day)
            if m in job.bonds:  # a validator's bond for this job comes back; a runner's stays registered
                rest = self.ledger.balance(job.bonds[m])
                if rest:
                    self.ledger.transfer(job.bonds[m], m, rest, "refund", self._ref(job), day)
        job.state, job.outcome = "closed", (job.planted if job.planted is not None else outcome)
        self.ledger.record(day, "reruns", self._ref(job), f"{job.ref} outcome={job.outcome} votes={votes}"
                           + (f" planted={job.planted}" if job.planted is not None else ""))
        return job.outcome

    def settle_split(self, first: Job, final: Job, day: int) -> None:
        """Re-runs without a quorum were settled by fresh ones: whoever in the first disagreed with the final result
        loses the dissent share of its bond (#43)."""
        if first.outcome is not None or final.state != "closed" or final.outcome is None:
            raise CheckingError("only a split settled by a fresh quorum")
        for m, got in first.reveals.items():
            held, base = self._bond_base(m)
            if got != final.outcome and held is not None:
                self._take(held, share(base, self.params.rerun_dissent_penalty_bps), first, day)

    def appeal_reruns(self, job: Job, appellant: str, seed: str, exclude: set[str], day: int) -> Job:
        """A solver appeals failed re-runs: it pays the published fee, and fresh validators, none of the first,
        re-run the same checks (#43)."""
        if job.kind != "rerun" or job.state != "closed" or job.outcome is not False or job.appeal is not None:
            raise CheckingError(f"job {job.id} isn't failed re-runs open to appeal")
        fee = self.ledger.open("cfee")
        self.ledger.transfer(appellant, fee, self.params.rerun_appeal_fee, "fee", self._ref(job), day)
        job.appeal = self.start_reruns(job.ref, seed, set(exclude) | set(job.members), day)
        job.appeal.fee_account = fee
        return job.appeal

    def settle_appeal(self, job: Job, appellant: str, day: int) -> bool | None:
        """The appeal's re-runs are closed. If they pass, the first re-runners who reported a failure lose the
        dissent share of their validator stake and the fee returns; otherwise the fee goes to insurance. Returns
        the final result."""
        a, p = job.appeal, self.params
        if a is None or a.state != "closed" or a.fee_account is None:
            raise CheckingError(f"job {job.id} has no closed appeal")
        if a.outcome is True:
            for m, got in job.reveals.items():
                held, base = self._bond_base(m)
                if got is False and held is not None:
                    self._take(held, share(base, p.rerun_dissent_penalty_bps), job, day)
            self.ledger.transfer(a.fee_account, appellant, self.ledger.balance(a.fee_account), "refund", self._ref(a), day)
        else:
            self._take(a.fee_account, self.ledger.balance(a.fee_account), a, day)
        self.ledger.record(day, "rerun_appeal", self._ref(job), f"{job.ref} {job.outcome} -> {a.outcome}")
        return a.outcome

    # ---------- evaluators and the jury (design D3, D4) ----------

    def register_evaluator(self, account: str, operator: str, family: str, day: int, model: str = "") -> Evaluator:
        if account in self.evaluators:
            raise CheckingError(f"{account} is already an evaluator")
        bond = self.ledger.open("ebond")
        self.ledger.transfer(account, bond, self.params.evaluator_bond, "bond", f"evaluator:{account}", day)
        e = self.evaluators[account] = Evaluator(account, operator, family, bond, model=model or family)
        return e

    def listed(self, model: str | None) -> bool:
        """A model is on the list while its measured accuracy is at the bar; with no list published, any is (#47)."""
        if not self.model_accuracy:
            return model is not None
        return model is not None and self.model_accuracy.get(model, 0.0) >= self.params.model_bar_bps / BPS

    def counts(self, v: "Verdict | None", member: str | None = None) -> bool:
        """A verdict counts if it cites evidence and proves a listed model: the one its evaluator registered for (#47)."""
        if v is None or not v.evidence or not self.listed(v.proven):
            return False
        e = self.evaluators.get(member) if member is not None else None
        return e is None or not self.model_accuracy or v.proven == e.model

    def verdict_fee(self, account: str) -> int:
        """The fee one counted verdict earns: by the evaluator's own Brier tier, or the flat fee (#47)."""
        p = self.params
        score = self.brier(account)
        for bound, fee in p.verdict_fee_tiers:
            if score is not None and score <= bound / BPS:
                return fee
        return p.verdict_fee if not p.verdict_fee_tiers else min(f for _, f in p.verdict_fee_tiers)

    def leaderboard(self, pool: list[str]) -> list[str]:
        """The models the pool runs, best first: by published measured accuracy, then by their evaluators' best
        Brier score (#47). With no list published, every evaluator's model ranks by its record alone."""
        best: dict[str, float] = {}
        for a in pool:
            m = self.evaluators[a].model
            best[m] = min(best.get(m, 1.0), self.brier(a) if self.brier(a) is not None else 1.0)
        return sorted(best, key=lambda m: (-self.model_accuracy.get(m, 0.0), best[m], m))

    def suspended(self, account: str) -> bool:
        """The record backstop: a Brier score far above what its model's measured accuracy implies (#47)."""
        e, p = self.evaluators[account], self.params
        a = self.model_accuracy.get(e.model)
        score = self.brier(account)
        return (a is not None and score is not None and len(e.briers) >= p.shadow_verdicts
                and score > a * (1 - a) + p.cheat_margin_bps / BPS)

    def brier(self, account: str) -> float | None:
        """The mean Brier score over the latest scored verdicts; lower is better. None before any."""
        b = self.evaluators[account].briers[-self.params.score_window:]
        return sum(b) / len(b) if b else None

    def qualified(self, account: str) -> bool:
        e, p = self.evaluators[account], self.params
        score = self.brier(account)
        return (len(e.briers) >= p.shadow_verdicts and score is not None and score <= p.qualify_brier_bps / BPS
                and self.ledger.balance(e.bond_account) > 0 and self.listed(e.model) and not self.suspended(account))

    def draw_jury(self, ref: str, seed: str, exclude: set[str], planted: bool | None = None, tier: int = 1) -> Job:
        """A jury from the leaderboard, top to bottom (#47): the best-measured listed models seat first, each seat going
        to one of the operators running that model, drawn with a seed. The first jury takes one model per provider;
        the second (a split's) one seat per operator and a published number per provider. One unqualified evaluator
        sits in shadow on the first, if any. Fewer seats if they can't be filled."""
        p = self.params
        barred = set(exclude)
        for account in exclude:
            barred |= self.validators.links.get(account, set())
        open_ = sorted(a for a in self.evaluators if a not in barred and self.ledger.balance(self.evaluators[a].bond_account) > 0)
        pool = sorted(a for a in open_ if self.qualified(a))
        size, per_family = (p.jury_size, 1) if tier == 1 else (p.second_jury_size, p.second_jury_per_family)
        rng = random.Random(seed)
        members, operators, families = [], set(), {}
        for model in self.leaderboard(pool):  # top to bottom (#47, owner): the best-measured models judge first
            if len(members) == size:
                break
            running = [a for a in pool if self.evaluators[a].model == model]
            rng.shuffle(running)  # a fair, seeded tie-break between copies of one model (not a security feature)
            for a in running:
                e = self.evaluators[a]
                if len(members) == size or families.get(e.family, 0) >= per_family:
                    break
                if e.operator in operators:
                    continue
                members.append(a)
                operators.add(e.operator)
                families[e.family] = families.get(e.family, 0) + 1
                if tier == 1:
                    break  # the first jury takes one copy of each model, down the board
        job = self._job("jury", ref, members, planted)
        job.tier = tier
        newcomers = [a for a in open_ if not self.qualified(a)]
        if newcomers and tier == 1:
            job.shadow = [rng.choice(newcomers)]
        return job

    def shadow_case(self, accounts: list[str], ref: str, planted: bool) -> Job:
        """A planted case for these evaluators, all in shadow: how newcomers build their first scored verdicts."""
        job = self._job("jury", ref, [], planted)
        job.shadow = list(accounts)
        return job

    def reveal_verdict(self, job: Job, member: str, accepts: bool, p: float, evidence: str, secret: str,
                       proven: str | None = "") -> bool:
        """A verdict's reveal, with the proof of the model that produced it (#47). By default, the model the
        evaluator registered for (an honest evaluator's proof shows it)."""
        if job.kind != "jury" or member in job.reveals or job.commits.get(member) != seal(accepts, p, evidence, secret):
            return False
        if not 0.0 <= p <= 1.0:
            raise CheckingError("a probability is between 0 and 1")
        if proven == "" and member in self.evaluators:
            proven = self.evaluators[member].model
        job.reveals[member] = Verdict(accepts, p, evidence, proven or None)
        return True

    def close_jury(self, job: Job, day: int) -> str:
        """The first jury accepts with the published number (all of them: AI consensus), rejects unanimously, and
        otherwise (or with too few verdicts) escalates to the second jury, which accepts with its published
        supermajority and otherwise rejects. A verdict without evidence is discarded. A planted case is scored at
        once; a real one when the delivery's fate is known (`resolve`)."""
        p = self.params
        if job.kind != "jury" or job.state != "open":
            raise CheckingError(f"job {job.id} isn't an open jury")
        for m in job.members + job.shadow:  # an unproven or unlisted model's verdict is discarded, at a cost (#47)
            v = job.reveals.get(m)
            if v is not None and v.evidence and not self.counts(v, m) and m in self.evaluators:
                self._take(self.evaluators[m].bond_account, share(p.evaluator_bond, p.unproven_penalty_bps), job, day)
        counted = [job.reveals[m] for m in job.members if self.counts(job.reveals.get(m), m)]
        accepts = sum(1 for v in counted if v.accepts)
        if job.tier == 2:
            job.outcome = "accept" if accepts >= p.second_jury_accept else "reject"
        elif accepts >= p.jury_accept:
            job.outcome = "accept"
        elif len(counted) == p.jury_size and accepts == 0:
            job.outcome = "reject"
        else:
            job.outcome = "escalate"
        job.state = "closed"
        self.ledger.record(day, "jury", self._ref(job), f"{job.ref} {job.outcome} {accepts}/{len(counted)}"
                           + (f" planted={job.planted}" if job.planted is not None else ""))
        if job.planted is not None:
            self.pay_verdicts(job, self.insurance, self._ref(job), day)  # the system's own checking cost
            self._score(job, job.planted, day)
        return job.outcome

    def resolve(self, ref: str, good: bool, day: int) -> None:
        """A real delivery's fate is known (accepted and fully paid, or slashed or clawed back): score its jury."""
        for job in self.jobs:
            if job.kind == "jury" and job.ref == ref and job.state == "closed" and job.planted is None:
                self._score(job, good, day)

    def publish_evidence(self, ref: str, day: int) -> None:
        """The delivery's bounty is settled: its jury's verdicts, with their evidence, go on the record (#43)."""
        for job in self.jobs:
            if job.kind == "jury" and job.ref == ref and job.planted is None and job.state != "open" and job.reveals:
                cited = "; ".join(f"{m}: {'accept' if v.accepts else 'reject'} p={v.p:.2f} [{v.evidence}]"
                                  for m, v in sorted(job.reveals.items()))
                self.ledger.record(day, "jury_evidence", self._ref(job), f"{ref} {cited}")

    def unscored(self, ref: str, day: int) -> None:
        """A rejected delivery: its truth is never revealed, so its juries' verdicts go unscored. Scoring them against
        the rejection would be scoring on agreement (#43 design, changes)."""
        for job in self.jobs:
            if job.kind == "jury" and job.ref == ref and job.state == "closed" and job.planted is None:
                job.state = "resolved"  # its evaluators were paid their verdict fees by the bounty

    def runs_due(self, job: Job) -> list[str]:
        """The runners owed a run fee: those whose result stands."""
        return [m for m in job.members if job.outcome is not None and job.reveals.get(m) == job.outcome]

    def verdicts_due(self, job: Job) -> list[str]:
        """The evaluators owed a verdict fee: a counted verdict (revealed, with evidence) on a seat; shadows aren't."""
        return [m for m in job.members if self.counts(job.reveals.get(m), m)]

    def pay_runs(self, job: Job, payer: str, ref: str, day: int) -> int:
        """The run fee for each run whose result stands, from `payer`. Returns what was paid."""
        return sum(self._pay(payer, m, self.params.run_fee, job, day, ref) for m in self.runs_due(job))

    def _pay(self, payer: str, to: str, fee: int, job: Job, day: int, ref: str | None = None) -> int:
        amount = min(fee, self.ledger.balance(payer))
        if amount > 0:
            self.ledger.transfer(payer, to, amount, "payout", ref or self._ref(job), day)
        return max(amount, 0)

    def pay_verdicts(self, job: Job, payer: str, ref: str, day: int) -> int:
        """The verdict fee for each counted verdict (revealed, with evidence) on the job's seats, from `payer`: the
        bounty for a real delivery, insurance for a planted case. Shadow seats aren't paid. Returns what was paid."""
        return sum(self._pay(payer, m, self.verdict_fee(m), job, day, ref) for m in self.verdicts_due(job))

    def take_work(self) -> dict[str, int]:
        out, self._work = self._work, {}
        return out

    # ---------- internals ----------

    def _score(self, job: Job, good: bool, day: int) -> None:
        """Brier against the truth, or (the comparison) against the jury's majority. A planted answer confidently on
        the wrong side loses the planted share of the bond. A verdict that held up is a unit of work."""
        p = self.params
        if job.outcome in ("accept", "reject"):
            majority = job.outcome == "accept"
        else:  # escalated, or shadow only: the majority of the verdicts given
            votes = [job.reveals[m].accepts for m in job.members + job.shadow if m in job.reveals]
            majority = sum(votes) * 2 > len(votes) if votes else good
        target = majority if self.score_on_agreement else good
        for m in job.members + job.shadow:
            v = job.reveals.get(m)
            if not self.counts(v, m) or m not in self.evaluators:
                continue
            e = self.evaluators[m]
            e.briers.append((v.p - (1.0 if target else 0.0)) ** 2)
            if (job.planted is not None and not self.score_on_agreement
                    and abs(v.p - (1.0 if good else 0.0)) >= p.confident_bps / BPS):
                self._take(e.bond_account, share(p.evaluator_bond, p.planted_penalty_bps), job, day)
        job.state = "resolved"

    def _take(self, account: str, amount: int, job: Job, day: int) -> None:
        amount = min(amount, self.ledger.balance(account))
        if amount:
            self.ledger.transfer(account, self.insurance, amount, "slash", self._ref(job), day)

    def _job(self, kind: str, ref: str, members: list[str], planted: bool | None) -> Job:
        job = Job(len(self.jobs) + 1, kind, ref, members, planted)
        self.jobs.append(job)
        return job

    @staticmethod
    def _ref(job: Job) -> str:
        return f"check:{job.id}"
