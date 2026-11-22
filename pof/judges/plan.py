"""The planned judging run (tasks 2.2 and 2.3): which models sit for each family, how many calls the run makes, and
what it costs, before anything is sent.

Every seat is reached through the owner's AgentCore model gateway (agentcore#90), as the judges caller
pof-judges-models under its token budget: Anthropic through the gateway's Messages API, the others through its
OpenAI-compatible chat completions (Bedrock Mantle, and Google's Gemini API). Prices are reports/costs-v1.md's
(pof.costs), except where the seat's model or route differs (PRICES below). Tokens are estimated from characters
(`tokens`), not counted by each model's tokenizer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .. import costs as C
from .injection import KINDS


@dataclass(frozen=True)
class Seat:
    family: str
    model: str  # the model ID the gateway routes on
    api: str  # "messages" (Anthropic Messages, /v1/messages) or "chat" (OpenAI chat completions, /v1/chat/completions)
    note: str = ""
    limit_field: str = "max_tokens"  # the request field capping the answer, thinking included


# The model gateway's targets (agentcore#90; Bedrock model cards and Gemini API models list, 2026-10-30).
SEATS = {
    "anthropic": Seat("anthropic", "claude-opus-5-5", "messages"),
    "openai": Seat("openai", "openai.gpt-6.1-sol", "chat", "Bedrock Mantle, /openai/v1", "max_completion_tokens"),
    "google": Seat("google", "gemini-3.1-pro-preview", "chat",
                   "Gemini API through the gateway (owner, 2026-10-30); gemini-3-pro-preview was shut down 2026-03-09"),
    "deepseek": Seat("deepseek", "deepseek.v3.2", "chat", "8K output at most"),
    "qwen": Seat("qwen", "qwen.qwen3-235b-a22b-2507", "chat", "8K output at most"),
    "mistral": Seat("mistral", "mistral.mistral-large-3-675b-instruct", "chat"),
    "nvidia": Seat("nvidia", "nvidia.nemotron-super-3-120b", "chat",
                   "in place of Meta's Llama, which Bedrock Mantle doesn't serve (so neither does the gateway)"),
}

# Where a seat's model or route differs from costs-v1's assumption: list prices for the model the run calls.
PRICES = {
    "judge": {
        "openai": C.Model("openai", "gpt-6.1-sol (Bedrock Mantle, in-Region)", 2.20, 0.11, 11.00,
                          "Bedrock model card GPT-6.1 Sol: in-Region on bedrock-mantle costs 10 % more than global"),
        "nvidia": C.Model("nvidia", "nemotron-super-3-120b (Bedrock)", 0.15, 0.15, 0.65,
                          "aws.amazon.com/bedrock/pricing, 2026-10-30; no cache discount assumed"),
    },
    "cheap": {
        "nvidia": C.Model("nvidia", "nemotron-super-3-120b (Bedrock)", 0.15, 0.15, 0.65,
                          "the family's only model on the gateway"),
    },
}


def price(family: str, grade: str = "judge") -> C.Model:
    return PRICES.get(grade, {}).get(family) or C.GRADES[grade][family]


# Also on Bedrock but not served by Mantle (so not by the gateway): Meta's Llama, Moonshot Kimi K3.

CHARS_PER_TOKEN = 3.5  # estimate for English mixed with code; each model's tokenizer differs by about +-20 %
OUTPUT = {"small": 2_000, "medium": 4_000, "large": 8_000}  # tokens out, thinking included (costs-v1's assumption)


def tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def calls(cases: list[dict], families: list[str] | None = None) -> list[tuple[str, str]]:
    """(family, case id) for the whole run: every family judges every clean case, and every bad case once per kind
    of injection."""
    fams = families or list(SEATS)
    ids = [c["id"] for c in cases] + [f"{c['id']}+{k}" for c in cases if c["label"] == "bad" for k in KINDS]
    return [(f, i) for f in fams for i in ids]


def cost(token_counts: dict[str, dict], grade: str = "judge", families: list[str] | None = None) -> dict:
    """The run's cost at pof.costs's list prices, with no prompt cache: token_counts maps each case id (clean and
    injected) to {"input": tokens, "size": size}. Returns each family's cost, the total, and the token totals."""
    fams = families or list(SEATS)
    rows = {}
    for f in fams:
        m = price(f, grade)
        rows[f] = sum((t["input"] * m.input + OUTPUT[t["size"]] * m.output) / C.M for t in token_counts.values())
    return {"families": rows, "total": sum(rows.values()), "calls": len(token_counts) * len(fams),
            "input_tokens": sum(t["input"] for t in token_counts.values()) * len(fams),
            "output_tokens": sum(OUTPUT[t["size"]] for t in token_counts.values()) * len(fams)}


def cost_table(token_counts: dict[str, dict]) -> str:
    """The planned run's cost by family and grade, in Markdown (reports/judges-v1.md; a test recomputes it)."""
    judge, cheap = cost(token_counts, "judge"), cost(token_counts, "cheap")
    out = ["| Family | Model (through the gateway) | Judge-grade price | Cheap-grade price |", "|---|---|---|---|"]
    for f in SEATS:
        out.append(f"| {f} | `{SEATS[f].model}` | ${judge['families'][f]:.2f} | ${cheap['families'][f]:.2f} |")
    out.append(f"| **all 7** | {judge['calls']:,} calls, {judge['input_tokens']:,} tokens in, "
               f"{judge['output_tokens']:,} out | **${judge['total']:.2f}** | **${cheap['total']:.2f}** |")
    return "\n".join(out)
