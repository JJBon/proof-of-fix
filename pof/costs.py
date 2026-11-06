"""The running-cost model (proof-of-fix#82 B2, for #85): what one check, one paid fix and one ADR cost the people who
run them, in US dollars, under #85's judges: 3 for an issue (one model family each), 7 for the constitution.

A check is a sandboxed test run on each attested runner plus one model review per judge. A paid fix pays for its
registration checks, every submission's check, the escalations to the 7, and its transactions on a layer-2 chain.
Every input is data below, with its source and date, or marked as an assumption; reports/costs-v1.md explains them.
The counts per paid fix come from the simulated market (`measure`); nothing here opens a connection (rule 1).

    python3 -m pof.costs                     the tables of reports/costs-v1.md
    python3 -m pof.costs --measure 20        the counts per paid fix, re-measured on seeds 1-20 of the default market
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from statistics import mean

M = 1_000_000  # prices are per million tokens


@dataclass(frozen=True)
class Model:
    """A judge's model and its list prices in USD per million tokens. A cached input token is a prompt-cache read."""
    family: str
    name: str
    input: float
    cached: float
    output: float
    source: str


# Prices as listed on 2026-10-30 unless the source says otherwise. "judge" is the model a judge would run; "cheap" is
# the family's low-cost model. Output prices also pay for the model's thinking tokens.
JUDGE = {
    "anthropic": Model("anthropic", "claude-opus-5-5", 4.00, 0.20, 20.00, "Anthropic price list (cached 2026-10-06)"),
    "openai": Model("openai", "gpt-6.1-sol", 2.00, 0.10, 10.00, "developers.openai.com/api/docs/pricing"),
    "google": Model("google", "gemini-3.1-pro-preview", 2.00, 0.20, 12.00, "ai.google.dev/gemini-api/docs/pricing"),
    "deepseek": Model("deepseek", "deepseek-v4-pro (peak)", 1.32, 0.044, 3.96, "api-docs.deepseek.com, peak rates"),
    "qwen": Model("qwen", "Qwen3.7-Max (Together)", 1.50, 1.50, 4.50, "together.ai/pricing; no cache discount assumed"),
    "mistral": Model("mistral", "Mistral Large", 0.50, 0.05, 1.50, "mistral.ai/pricing FAQ; cache read 0.1x assumed"),
    "llama": Model("llama", "Llama 4 Maverick (Groq)", 0.50, 0.50, 0.77, "third-party aggregators, unverified"),
}
CHEAP = {
    "anthropic": Model("anthropic", "claude-haiku-5-5", 0.10, 0.01, 0.50, "Anthropic price list; cache read 0.1x assumed"),
    "openai": Model("openai", "gpt-6-luna", 0.10, 0.01, 0.50, "developers.openai.com/api/docs/pricing"),
    "google": Model("google", "gemini-3.1-flash-lite", 0.25, 0.025, 1.50, "ai.google.dev/gemini-api/docs/pricing"),
    "deepseek": Model("deepseek", "deepseek-flash (peak)", 0.30, 0.006, 1.20, "api-docs.deepseek.com, peak rates"),
    "qwen": Model("qwen", "Qwen3.7-Plus (Together)", 0.32, 0.32, 1.28, "together.ai/pricing; no cache discount assumed"),
    "mistral": Model("mistral", "Mistral Large", 0.50, 0.05, 1.50, "the only listed Mistral API price"),
    "llama": Model("llama", "Llama 3 8B Instruct Lite (Together)", 0.14, 0.14, 0.14, "together.ai/pricing"),
}
GRADES = {"judge": JUDGE, "cheap": CHEAP}
ISSUE_TIER = ("anthropic", "openai", "google")  # #85: 3 judges, one family each (assumed: the best-measured three)
CONSTITUTION_TIER = tuple(JUDGE)  # #85: 7 judges, 7 families


@dataclass(frozen=True)
class Review:
    """One judge's review, in tokens (assumptions, reports/costs-v1.md). The cacheable part is the prompt and the
    constitution, the same for every check of a repository."""
    input: int
    cacheable: int
    output: int


# small: about 50 changed lines; medium: about 200; large: about 800 (diff with context, nearby code, test output).
REVIEWS = {
    "small": Review(14_000, 7_000, 2_000),
    "medium": Review(28_500, 7_000, 4_000),
    "large": Review(69_000, 7_000, 8_000),
}
REGISTRATION = Review(16_500, 7_000, 2_000)  # the issue, its criteria and the code it names, against the constitution
ADR = Review(56_000, 15_000, 12_000)  # the whole constitution, the ADR, its evidence and the code it touches
SIZE_MIX = {"small": 0.50, "medium": 0.35, "large": 0.15}  # assumption: the fixes' sizes


@dataclass(frozen=True)
class Sandbox:
    """Each check runs the tests on every attested runner (the simulation's ci_runners) in a 2 vCPU, 4 GB container
    at AWS Fargate's on-demand Linux x86 rates in us-east-1 ($0.04048 per vCPU-hour, $0.004445 per GB-hour)."""
    runners: int = 2
    minutes: tuple[tuple[str, float], ...] = (("small", 3.0), ("medium", 8.0), ("large", 20.0))  # with setup
    adr_minutes: float = 20.0
    per_minute: float = (2 * 0.04048 + 4 * 0.004445) / 60

    def cost(self, size: str) -> float:
        return self.runners * dict(self.minutes)[size] * self.per_minute


@dataclass(frozen=True)
class Chain:
    """A transaction's cost on a layer-2 chain: its gas at the execution price, plus the L1 data fee per transaction.
    Base's execution base fee was about 0.05 gwei (2026-03-17); ETH was about $2,700 in early October 2026; the
    data fee is an assumption inside Base's published $0.005-$0.10 range."""
    gwei: float = 0.05
    eth_usd: float = 2_700.0
    data_fee: float = 0.01

    def cost(self, gas: float, transactions: float) -> float:
        return gas * self.gwei * 1e-9 * self.eth_usd + transactions * self.data_fee


# Median gas per call in contracts/test/Race.t.sol (forge test --gas-report on main 5da2c56). "head" is #85's commit
# hash recorded on-chain at each merge, not built yet: an assumption.
GAS = {
    "register": 273_289, "accept": 149_126, "pledge": 159_408, "attempt": 125_053, "commit": 295_087,
    "result": 205_594, "merged": 202_838, "settle": 391_429, "claimInstalments": 104_995, "withdraw": 53_800,
    "head": 60_000, "sunset": 90_577, "claimRefund": 169_941,
}


@dataclass(frozen=True)
class Counts:
    """What one paid fix carries, from the simulated default market (`measure`, seeds 1-20, 8 weeks each): issues
    registered, attempts started, submissions checked by a jury, and escalations to the 7. pledges, withdrawals and
    refund flows (an unsolved pledged bounty's sunset and refund) per paid fix are assumptions."""
    registrations: float = 3.30
    attempts: float = 2.25
    submissions: float = 1.54
    escalations: float = 0.46
    pledges: float = 1.0
    withdrawals: float = 2.0
    refund_flows: float = 0.5

    def calls(self) -> dict[str, float]:
        """Each contract call per paid fix."""
        return {"register": self.registrations, "accept": self.registrations, "pledge": self.pledges,
                "attempt": self.attempts, "commit": self.submissions, "result": self.submissions, "merged": 1,
                "settle": 1, "claimInstalments": 1, "withdraw": self.withdrawals, "head": 1,
                "sunset": self.refund_flows, "claimRefund": self.refund_flows}


COUNTS = Counts()


def review(model: Model, r: Review, cached: bool = True) -> float:
    """One judge's review: the cacheable part at the cache-read price when cached, the rest at the input price."""
    hit = r.cacheable if cached else 0
    return ((r.input - hit) * model.input + hit * model.cached + r.output * model.output) / M


def jury(families: tuple[str, ...], r: Review, grade: str = "judge", cached: bool = True) -> float:
    """Every judge of a tier reviews once."""
    return sum(review(GRADES[grade][f], r, cached) for f in families)


def check(size: str, grade: str = "judge", cached: bool = True, sandbox: Sandbox = Sandbox()) -> dict[str, float]:
    """One submission's check at the issue tier: the test runs and the 3 judges."""
    judges = jury(ISSUE_TIER, REVIEWS[size], grade, cached)
    runs = sandbox.cost(size)
    return {"sandbox": runs, "judges": judges, "total": runs + judges}


def escalation(size: str, grade: str = "judge", cached: bool = True) -> float:
    """A fix sent to the constitution tier: the 7 judges review it again (the tests aren't rerun)."""
    return jury(CONSTITUTION_TIER, REVIEWS[size], grade, cached)


def registration(grade: str = "judge", cached: bool = True) -> float:
    """An issue's registration check at the issue tier (no test run is assumed)."""
    return jury(ISSUE_TIER, REGISTRATION, grade, cached)


def gas(counts: Counts = COUNTS, chain: Chain = Chain()) -> float:
    """Every transaction a paid fix carries, at the chain's prices."""
    calls = counts.calls()
    return chain.cost(sum(GAS[step] * n for step, n in calls.items()), sum(calls.values()))


def fix(size: str, grade: str = "judge", cached: bool = True, counts: Counts = COUNTS, chain: Chain = Chain(),
        sandbox: Sandbox = Sandbox()) -> dict[str, float]:
    """One paid fix of a size: its registrations, its submissions' checks, its escalations and its gas."""
    parts = {
        "registrations": counts.registrations * registration(grade, cached),
        "checks": counts.submissions * check(size, grade, cached, sandbox)["total"],
        "escalations": counts.escalations * escalation(size, grade, cached),
        "gas": gas(counts, chain),
    }
    parts["total"] = sum(parts.values())
    return parts


def fix_mix(grade: str = "judge", cached: bool = True, counts: Counts = COUNTS, chain: Chain = Chain(),
            mix: dict[str, float] = SIZE_MIX) -> dict[str, float]:
    """A paid fix at the assumed mix of sizes."""
    rows = {size: fix(size, grade, cached, counts, chain) for size in mix}
    return {key: sum(mix[size] * rows[size][key] for size in mix) for key in rows[next(iter(mix))]}


def adr(grade: str = "judge", cached: bool = True, sandbox: Sandbox = Sandbox(), chain: Chain = Chain()) -> dict:
    """An ADR at the constitution tier: the 7 judges, its evidence's test runs, and one signed result on-chain."""
    parts = {"judges": jury(CONSTITUTION_TIER, ADR, grade, cached),
             "sandbox": sandbox.runners * sandbox.adr_minutes * sandbox.per_minute,
             "gas": chain.cost(GAS["result"], 1)}
    parts["total"] = sum(parts.values())
    return parts


def fee(cost: float, margin: float) -> float:
    """The check fee at a published margin over cost."""
    return cost * (1 + margin)


def operator_profit(size: str, margin: float, grade: str = "judge", family: str = "anthropic", verdicts: int = 1000,
                    cached: bool = True) -> float:
    """What one judge operator keeps from `verdicts` reviews it signs, at a margin over its own model's cost."""
    return verdicts * review(GRADES[grade][family], REVIEWS[size], cached) * margin


# ---------- the counts, from the simulation ----------

def measure(seeds: int = 20) -> dict[str, float]:
    """The counts per paid fix in the default market on seeds 1..seeds: issues registered, attempts started (honest
    solvers), submissions a jury checked, and escalations to the second jury. Imported here so the model itself
    doesn't need the simulation."""
    from .sim import market_sim as MS
    rows = []
    for seed in range(1, seeds + 1):
        r = MS.market_report(MS.run("market", seed), "market", seed)
        m, c = r["market"], r["checking"]
        paid = m["bounties"]["paid"]
        rows.append({"paid": paid, "registrations": sum(m["issues"].values()) / paid,
                     "attempts": m["attempts"] / paid, "submissions": c.get("juries", 0) / paid,
                     "escalations": c.get("escalations", 0) / paid,
                     "escalation_rate": c.get("escalations", 0) / max(1, c.get("juries", 0))})
    return {key: round(mean(row[key] for row in rows), 3) for key in rows[0]}


# ---------- the tables ----------

def _usd(x: float) -> str:
    return f"${x:,.4f}" if x < 0.1 else f"${x:,.2f}"


def tables() -> str:
    """The tables of reports/costs-v1.md, in Markdown."""
    out = ["## Cost per check (issue tier: 3 judges, tests on 2 runners; prompt cache on)", "",
           "| Fix size | Grade | Tests | 3 judges | Check | Escalated to the 7 (extra) |", "|---|---|---|---|---|---|"]
    for size in REVIEWS:
        for grade in GRADES:
            c = check(size, grade)
            out.append(f"| {size} | {grade} | {_usd(c['sandbox'])} | {_usd(c['judges'])} | **{_usd(c['total'])}** | "
                       f"{_usd(escalation(size, grade))} |")
    out += ["", "## Cost per paid fix (counts per paid fix from the simulation)", "",
            "| Fix size | Grade | Registrations | Checks | Escalations | Gas | **Total** | Gas share |",
            "|---|---|---|---|---|---|---|---|"]
    for size in list(REVIEWS) + ["mix"]:
        for grade in GRADES:
            f = fix_mix(grade) if size == "mix" else fix(size, grade)
            out.append(f"| {size} | {grade} | {_usd(f['registrations'])} | {_usd(f['checks'])} | "
                       f"{_usd(f['escalations'])} | {_usd(f['gas'])} | **{_usd(f['total'])}** | "
                       f"{f['gas'] / f['total']:.0%} |")
    out += ["", "## Cost per ADR (constitution tier: 7 judges)", "",
            "| Grade | 7 judges | Tests | Gas | **Total** |", "|---|---|---|---|---|"]
    for grade in GRADES:
        a = adr(grade)
        out.append(f"| {grade} | {_usd(a['judges'])} | {_usd(a['sandbox'])} | {_usd(a['gas'])} | "
                   f"**{_usd(a['total'])}** |")
    out += ["", "## Fees and an operator's margin (medium fix, judge grade)", "",
            "| Margin | Check fee | Operator's profit per 1,000 verdicts (Anthropic judge) |", "|---|---|---|"]
    base = check("medium")["total"]
    for margin in (0.0, 0.2, 0.5):
        out.append(f"| {margin:.0%} | {_usd(fee(base, margin))} | {_usd(operator_profit('medium', margin))} |")
    out += ["", "## Sensitivity (paid fix at the size mix)", "", "| Case | Judge grade | Cheap grade |", "|---|---|---|"]
    cases = {
        "base (cache on, 0.05 gwei, $0.01 data fee)": {},
        "no prompt cache": {"cached": False},
        "busy chain (0.5 gwei, $0.10 data fee)": {"chain": Chain(gwei=0.5, data_fee=0.10)},
        "half the escalations": {"counts": replace(COUNTS, escalations=COUNTS.escalations / 2)},
        "twice the submissions": {"counts": replace(COUNTS, submissions=COUNTS.submissions * 2)},
    }
    for name, kw in cases.items():
        out.append(f"| {name} | {_usd(fix_mix('judge', **kw)['total'])} | {_usd(fix_mix('cheap', **kw)['total'])} |")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m pof.costs")
    ap.add_argument("--measure", type=int, metavar="SEEDS", help="re-measure the counts per paid fix on seeds 1..SEEDS")
    a = ap.parse_args(argv)
    if a.measure:
        for key, value in measure(a.measure).items():
            print(f"{key}: {value}")
    else:
        print(tables())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
