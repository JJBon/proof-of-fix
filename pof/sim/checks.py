"""The checking layer in the market simulation (specs/incentive-simulation "Checking scenarios", proof-of-fix#43
design D5, D6).

Instead of fixed odds, a delivery's checks are re-run by validators (honest ones report the deterministic result,
with flaky runs; a lazy one reports "pass" without running), and a jury of AI evaluators judges whether it's good.
Evaluators err by a Gaussian copula: for a case, evaluator e of family f errs when Phi(z) < 1 - accuracy, with
z = sqrt(rho_across) g_case + sqrt(rho_within - rho_across) g_family + sqrt(1 - rho_within) g_e, so evaluators of one
family err together more often than evaluators of different families. Its own random stream keeps the market's
draws comparable across runs with and without it.
"""

from __future__ import annotations

import math
import random
from statistics import NormalDist

from .. import BPS, credits
from ..checking import Checking, CheckingError, Job, seal
from .actors import Actor

# #47 (owner): top models only, from three providers. Each provider's frontier model and accuracy (an assumption
# until the real-data measurement); each provider also has a small model, unlisted, for the cheat to run.
FAMILIES = (("A", 0.92), ("B", 0.90), ("C", 0.88))
SMALL_DROP, SMALL_COST_SHARE = 0.15, 6  # a small model: 0.15 less accurate, a sixth of the cost per verdict
OPERATORS = 7  # each runs one evaluator per provider: 21, enough for a second jury of 7 (at most 3 per provider)
EVALUATOR_KINDS = ("evaluator", "herder", "copy_evaluator", "model_cheat")
RUNNER_KINDS = ("runner", "lazy_runner", "sock_runner")  # attested CI runners: MCP test runners in TEEs (#43)
VENDORS = ("tdx", "sev", "cca")  # hardware vendors' enclaves
RUNNERS = 9  # operator i runs one runner on vendor i mod 3
CRAFT_TARGET, CRAFT_FOOLS, CRAFT_OTHERS = "A", 0.9, 0.3  # a crafted fix fools family A, and the others less (D6)
COPY_FAMILY = "C"  # the copy operator's one real model


def runner_specs() -> list[tuple[str, str]]:
    """(operator, vendor) of the honest attested runners."""
    return [(f"run-op-{i + 1}", VENDORS[i % len(VENDORS)]) for i in range(RUNNERS)]


def evaluator_specs() -> list[tuple[str, str]]:
    """(operator, provider) of the honest evaluators: every operator runs each provider's frontier model."""
    return [(f"op-{i + 1}", f) for i in range(OPERATORS) for f, _ in FAMILIES]


def frontier(provider: str) -> str:
    return f"{provider}-frontier"


class CheckSim:
    def __init__(self, world, rho_within: float = 0.5, rho_across: float = 0.2, rerun_cost: int = credits(0.2),
                 evaluator_cost: int = credits(0.3), exam_good_bps: int = 5_000, score_on_agreement: bool = False,
                 accuracy_shift: float = 0.0, tee_compromise_bps: int = 50):
        self.w, self.rng = world, random.Random(world.seed * 104_729 + 5)
        self.ci_rng = random.Random(world.seed * 104_729 + 7)  # CI runs: their own stream, so juries see the
        # same luck whichever CI mode runs (#43)
        self.rho_within, self.rho_across = rho_within, min(rho_across, rho_within)
        self.rerun_cost, self.evaluator_cost, self.exam_good_bps = rerun_cost, evaluator_cost, exam_good_bps
        self.hidden_share_bps = 5_000  # of the defects the checks catch, those only the hidden tests catch (#43)
        self.attested = world.params.ci_mode == "attested"  # runners run the hidden tests too, inside their enclaves
        self.tee_compromise_bps = tee_compromise_bps  # chance an honest runner's enclave returns a wrong result
        self.checking = Checking(world.ledger, world.params, world.vset, world.insurance, score_on_agreement)
        world.market.checking = world.releases.checking = self.checking
        self.model_acc = {}  # every model's accuracy; the sweep moves them all
        for f, a in FAMILIES:
            self.model_acc[frontier(f)] = min(0.99, a + accuracy_shift)
            self.model_acc[f"{f}-small"] = min(0.99, a - SMALL_DROP + accuracy_shift)
        self.checking.model_accuracy = dict(self.model_acc)  # published: the measurement (#47), taken as exact here
        self.true_family: dict[str, str] = {}  # the provider whose model an evaluator really runs
        self.running: dict[str, str] = {}  # the model an evaluator really runs, which its proofs show
        self._phi = NormalDist()

    # ---------- setup ----------

    def register_runner(self, a: Actor) -> None:
        self.checking.register_runner(a.account, a.operator, a.family, 0)
        a.staked += self.w.params.runner_bond

    def register(self, a: Actor, operator: str, family: str, true_family: str | None = None) -> None:
        """Registered for its provider's frontier model. A copy runs another provider's (its proofs show it); the
        model cheat runs its provider's small model (#47)."""
        self.checking.register_evaluator(a.account, operator, family, 0, model=frontier(family))
        real = true_family or family
        self.true_family[a.account] = real
        self.running[a.account] = f"{real}-small" if a.kind == "model_cheat" else frontier(real)
        a.staked += self.w.params.evaluator_bond

    def cost_of(self, account: str) -> int:
        """A verdict's cost to its evaluator: the frontier price, or a small model's fraction of it."""
        return self.evaluator_cost // SMALL_COST_SHARE if self.running[account].endswith("-small") else self.evaluator_cost

    def exam(self) -> None:
        """The founding evaluators' first scored verdicts: shadow cases with known answers, judged together (D4).
        The system pays for this calibration (it's the historical set of the real-data measurement); evaluators
        who join later qualify in shadow seats, at their own cost."""
        people = sorted(self.checking.evaluators)
        for i in range(self.w.params.shadow_verdicts):
            good = self.rng.randrange(BPS) < self.exam_good_bps
            job = self.checking.shadow_case(people, f"exam:{i}", good)
            self._jury_verdicts(job, good, crafted=False, partner=False, charged=False)
            self.checking.close_jury(job, 0)

    # ---------- a delivery ----------

    def deliver(self, e, a: Actor, issue, defect: str | None, caught: bool, day: int, partial: bool = False,
                gates: bool = True):
        """Re-runs, then (if they pass) the jury, then the market's verdict on the delivery, with the constitution's
        gates in race and claim (#60). Returns the contribution, or None if it failed."""
        w, p = self.w, self.w.params
        ref, good = f"entry:{e.id}", defect is None and not issue.junk
        b = w.market.bounties[e.bounty]
        exclude = w.market.parties(b)  # no bidder on this bounty checks it (#43)
        public = caught and self.rng.randrange(BPS) >= self.hidden_share_bps and not partial  # by the public checks
        if self.attested:  # the attested runners run the hidden tests too
            public = caught
        hidden_fail = caught and not public  # caught only by the hidden tests, on the system's runner
        flaky_bps = a.behaviour.false_check_failure_bps
        sock = {x.account for x in w.actors if x.kind == "sock_solver"} & exclude - {a.account}
        reruns = self._reruns(ref, exclude, not public, flaky_bps, day, sock=bool(sock))
        if reruns.outcome is None:  # no quorum: fresh runners, once; whoever disagreed with them loses bond
            first = reruns
            reruns = self._reruns(ref, exclude | set(first.members), not public, flaky_bps, day, sock=bool(sock))
            if reruns.outcome is not None and first.id:
                self.checking.settle_split(first, reruns, day)
        if reruns.outcome is False and not public and a.behaviour.appeals_wrong_decisions:  # wrongly failed: appeal
            reruns = self._appeal(reruns, a, exclude, flaky_bps, day, bool(sock))
        jury, second = None, None
        if reruns.outcome is True and not hidden_fail and getattr(e, "appeal", False):  # #60: an appeal goes to the
            jury = self.checking.draw_jury(ref, f"jury2:{e.id}:{w.rng.getrandbits(32)}", exclude, tier=2)  # second jury
            self._jury_verdicts(jury, good, crafted=a.kind == "crafter", partner=a.kind == "copy_partner",
                                borderline=a.kind == "split_farmer")
            self.checking.close_jury(jury, day)
        elif reruns.outcome is True and not hidden_fail:
            jury = self.checking.draw_jury(ref, f"jury:{e.id}:{w.rng.getrandbits(32)}", exclude)
            self._jury_verdicts(jury, good, crafted=a.kind == "crafter", partner=a.kind == "copy_partner",
                                borderline=a.kind == "split_farmer")
            if self.checking.close_jury(jury, day) == "escalate":  # a split: the second, larger AI jury decides
                second = self.checking.draw_jury(ref, f"jury2:{e.id}:{w.rng.getrandbits(32)}",
                                                 exclude | set(jury.members), tier=2)
                self._jury_verdicts(second, good, crafted=a.kind == "crafter", partner=a.kind == "copy_partner",
                                    borderline=a.kind == "split_farmer")
                self.checking.close_jury(second, day)
                self._bump("escalations")
        self._planted(day)
        c = w.market.deliver_checked(e, issue.lines, day, reruns, jury, second, hidden_passes=not hidden_fail,
                                     gates_pass=gates)
        self._tally(good, defect is not None and not issue.junk, reruns, jury, second, hidden_fail)
        return c

    def _appeal(self, job: Job, a: Actor, exclude: set[str], flaky_bps: int, day: int, sock: bool) -> Job:
        """The solver appeals failed re-runs it knows are wrong; fresh validators re-run them (#43)."""
        try:
            fresh = self.checking.appeal_reruns(job, a.account, f"appeal:{job.ref}:{self.ci_rng.getrandbits(32)}",
                                                exclude, day)
        except (CheckingError, ValueError):
            return job
        self._run(fresh, True, flaky_bps, day, None, sock)
        self.checking.settle_appeal(job, a.account, day)
        self._bump("appeals")
        if fresh.outcome is True:
            self._bump("appeals_won")
        return fresh if fresh.outcome is not None else job

    # ---------- re-runs ----------

    def _reruns(self, ref: str, exclude: set[str], truth: bool, flaky_bps: int, day: int, planted=None,
                sock: bool = False) -> Job:
        w = self.w
        try:
            job = self.checking.start_reruns(ref, f"rerun:{ref}:{self.ci_rng.getrandbits(32)}", exclude, day, planted)
        except CheckingError:
            job = Job(0, "rerun", ref, [], planted, state="closed", outcome=truth)  # nobody to re-run: as fixed odds
            return job
        return self._run(job, truth, flaky_bps, day, planted, sock)

    def _run(self, job: Job, truth: bool, flaky_bps: int, day: int, planted, sock: bool) -> Job:
        """Each re-runner's result, sealed then revealed; the job closes. A sock validator reports a failure when
        its hidden partner bid on this bounty, to have it reopened (#43)."""
        w = self.w
        secrets = {}
        for m in job.members:
            actor = w.by_account[m]
            flaky = self.ci_rng.randrange(BPS) < flaky_bps and planted is None  # drawn for all: runs stay comparable
            broken = self.ci_rng.randrange(BPS) < self.tee_compromise_bps
            if actor.kind in ("lazy_validator", "lazy_runner"):
                result = True  # never runs anything (a runner forging its attestation: compromised hardware)
            elif actor.kind in ("sock_validator", "sock_runner") and sock:
                result = False
                actor.bump("effort", self.rerun_cost)
            else:
                result = truth and not flaky
                if actor.kind == "runner" and broken:  # a compromised or faulty enclave: its result is noise
                    result = self.ci_rng.randrange(2) == 0
                actor.bump("effort", self.rerun_cost)
            secrets[m] = (result, f"{m}:{self.ci_rng.getrandbits(32)}")
            self.checking.commit(job, m, seal(*secrets[m]))
            actor.bump("reruns")
        for m in job.members:
            if self.ci_rng.randrange(BPS) >= w.by_account[m].behaviour.no_reveal_bps:
                self.checking.reveal_rerun(job, m, *secrets[m])
        self.checking.close_reruns(job, day)
        return job

    # ---------- the jury ----------

    def _jury_verdicts(self, job: Job, good: bool, crafted: bool, partner: bool, charged: bool = True,
                       borderline: bool = False) -> None:
        w = self.w
        people = job.members + job.shadow
        errs = self._errors(people, crafted, borderline)
        secrets = {}
        for m in people:
            actor = w.by_account[m]
            fam = self.true_family[m]
            if actor.kind == "herder":  # no model call: always accepts, confidently
                accepts, prob = True, 0.9
            elif actor.kind == "copy_evaluator" and partner:  # waves its partner's fix through
                accepts, prob = True, 0.95
                if charged:
                    actor.bump("effort", self.cost_of(m))
            else:
                accepts = good if not errs[m] else not good
                acc = self.model_acc[self.running[m]]
                prob = acc if accepts else 1 - acc
                if charged:
                    actor.bump("effort", self.cost_of(m))
            secrets[m] = (accepts, prob, "runs and diff", f"{m}:{self.rng.getrandbits(32)}")
            self.checking.commit(job, m, seal(*secrets[m]))
            actor.bump("verdicts")
        for m in people:
            if self.rng.randrange(BPS) >= w.by_account[m].behaviour.no_reveal_bps:
                self.checking.reveal_verdict(job, m, *secrets[m], proven=self.running[m])  # its proof (#47)

    def _errors(self, people: list[str], crafted: bool, borderline: bool = False) -> dict[str, bool]:
        """Who errs on this case (design D5). Copies of one model share their individual draw too."""
        g_case = self.rng.gauss(0, 1)
        g_fam: dict[str, float] = {}
        g_own: dict[str, float] = {}
        out = {}
        for m in people:
            fam = self.true_family[m]
            if fam not in g_fam:
                g_fam[fam] = self.rng.gauss(0, 1)
            key = "copy" if self.w.by_account[m].kind == "copy_evaluator" else m
            if key not in g_own:
                g_own[key] = self.rng.gauss(0, 1)
            z = (math.sqrt(self.rho_across) * g_case + math.sqrt(self.rho_within - self.rho_across) * g_fam[fam]
                 + math.sqrt(1 - self.rho_within) * g_own[key])
            acc = self.model_acc[self.running[m]]
            if crafted:
                acc = 1 - (CRAFT_FOOLS if fam == CRAFT_TARGET else CRAFT_OTHERS)
            if borderline:  # #49: junk built to split the jury, misjudged half the time by every family
                acc = 0.5
            out[m] = self._phi.cdf(z) < 1 - acc
        return out

    # ---------- planted cases ----------

    def _planted(self, day: int) -> None:
        """Planted jobs at the published share of all jobs: a re-run and a jury, each half good (D2)."""
        p = self.w.params
        if not p.planted_share_bps or self.rng.randrange(BPS - p.planted_share_bps) >= p.planted_share_bps:
            return
        n = len(self.checking.jobs)
        passes = self.rng.randrange(BPS) >= p.planted_fail_bps
        self._reruns(f"planted:{n}", set(), passes, 0, day, planted=passes)
        good = self.rng.randrange(2) == 0
        job = self.checking.draw_jury(f"planted:{n}", f"planted:{n}:{self.w.rng.getrandbits(32)}", set(), planted=good)
        self._jury_verdicts(job, good, crafted=False, partner=False)
        self.checking.close_jury(job, day)
        self._bump("planted")

    # ---------- counts ----------

    def _tally(self, good: bool, defective: bool, reruns: Job, jury: Job | None, second: Job | None,
               hidden_fail: bool = False) -> None:
        self._bump("defective" if defective else "good" if good else "junk")
        passed_tests = reruns.outcome is True and not hidden_fail
        passed_jury = jury is not None and (jury.outcome == "accept" or (
            jury.outcome == "escalate" and second is not None and second.outcome == "accept"))
        if defective:
            if not passed_tests:
                self._bump("caught_tests")
            elif not passed_jury:
                self._bump("caught_jury" if jury.outcome == "reject" else "caught_second_jury")
        if good and not (passed_tests and passed_jury):
            self._bump("good_failed")
            if passed_tests:
                self._bump("good_failed_jury")
        if jury is not None:
            self._bump("juries")
            if len(jury.members) < self.w.params.jury_size:
                self._bump("short_juries")

    def _bump(self, key: str, n: int = 1) -> None:
        bump(self.w.check_stats, key, n)

    def evaluators_report(self) -> dict:
        briers: dict[str, list[float]] = {}
        for account, ev in self.checking.evaluators.items():
            b = self.checking.brier(account)
            if b is not None:
                briers.setdefault(self.w.by_account[account].kind, []).append(b)
        out = {"brier": {k: round(sum(v) / len(v), 4) for k, v in sorted(briers.items())}}
        out["qualified"] = {k: sum(1 for a in self.checking.evaluators if self.w.by_account[a].kind == k
                                   and self.checking.qualified(a)) for k in sorted(briers)}
        return out


def bump(stats: dict, key: str, n: int = 1) -> None:
    stats[key] = stats.get(key, 0) + n


def tally_fixed_odds(stats: dict, good: bool, defective: bool, passes: bool) -> None:
    """The same counts when checking is fixed odds (the comparison): the gate is the only check."""
    bump(stats, "defective" if defective else "good" if good else "junk")
    if defective and not passes:
        bump(stats, "caught_tests")
    if good and not passes:
        bump(stats, "good_failed")


def checking_report(world) -> dict:
    """Deliveries by outcome, the share of defective ones caught before beta, and the evaluators' scores."""
    s = world.check_stats
    caught = s.get("caught_tests", 0) + s.get("caught_jury", 0) + s.get("caught_second_jury", 0)
    out = dict(sorted(s.items()))
    out["caught_share"] = round(caught / s["defective"], 4) if s.get("defective") else None
    out["good_failed_share"] = round(s.get("good_failed", 0) / s["good"], 4) if s.get("good") else None
    if world.checks is not None:
        out.update(world.checks.evaluators_report())
        out["per_verdict"] = sorted(  # #47: honest evaluators' net return per verdict, by provider
            (a.family, round(world.net_of_effort(a) / max(1, a.stats.get("verdicts", 0)) / 1e6, 5))
            for a in world.actors if a.kind == "evaluator" and a.stats.get("verdicts"))
    return out
