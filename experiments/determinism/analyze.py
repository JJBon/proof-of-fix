"""Tables for reports/determinism-v1.md from results/*.jsonl[.gz] (proof-of-fix#125).

    python3 analyze.py            # prints the tables (Markdown) and writes results/summary.json

"Identical" means the answer's text is byte-identical; for vLLM the generated token IDs are compared too
(return_token_ids), so "token-identical" is measured directly there. "Verdict" is the judge path's own: `solves`
from pof.judges.prompt.parse (an unparseable answer counts as "invalid")."""

from __future__ import annotations

import gzip
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def load() -> dict[str, list[dict]]:
    """results/<tag>.jsonl, or <tag>.jsonl.gz as committed (gzip -9n: the answers' text compresses tenfold)."""
    out: dict[str, list[dict]] = {}
    for p in sorted(RESULTS.glob("*.jsonl*")):
        tag = p.name.split(".jsonl")[0]
        text = gzip.decompress(p.read_bytes()).decode() if p.suffix == ".gz" else p.read_text()
        out.setdefault(tag, []).extend(json.loads(line) for line in text.splitlines() if line.strip())
    return {tag: rows for tag, rows in sorted(out.items()) if rows}


def verdict(r: dict) -> str:
    if r["verdict_error"]:
        return "invalid"
    return "pass" if r["solves"] else "fail"


def key(r: dict) -> str:
    """What "identical" compares: the token IDs when the engine returns them, else the text."""
    return r["token_ids_sha256"] or r["text_sha256"]


def by_case(rows: list[dict]) -> dict[str, list[dict]]:
    out = defaultdict(list)
    for r in sorted(rows, key=lambda r: (r["case"], r["rep"])):
        out[r["case"]].append(r)
    return dict(out)


def within(rows: list[dict]) -> dict:
    """Repeats of one setup: per case, do all calls give the same tokens and the same verdict?"""
    cases = by_case(rows)
    same_tokens = sum(1 for rs in cases.values() if len({key(r) for r in rs}) == 1)
    same_text = sum(1 for rs in cases.values() if len({r["text_sha256"] for r in rs}) == 1)
    same_verdict = sum(1 for rs in cases.values() if len({verdict(r) for r in rs}) == 1)
    variants = sum(len({key(r) for r in rs}) for rs in cases.values())
    reps = Counter(len(rs) for rs in cases.values())
    return {"cases": len(cases), "calls": len(rows), "calls_per_case": dict(reps), "same_tokens": same_tokens,
            "same_text": same_text, "same_verdict": same_verdict, "distinct_outputs": variants}


def versus(ref: list[dict], rows: list[dict], ref_rep: int = 0, reps: list[int] | None = None) -> dict:
    """Each call of `rows` (only repeats `reps`, when given) against the reference setup's call `ref_rep` of the same
    case. vLLM's prefix cache makes a case's first call on a server "cold" and later ones "warm", so the reference's
    first repeat is cold and its second warm."""
    first = {c: rs[ref_rep] for c, rs in by_case(ref).items() if len(rs) > ref_rep}
    calls = [r for r in rows if r["case"] in first and (reps is None or r["rep"] in reps)]
    same_tokens = sum(1 for r in calls if key(r) == key(first[r["case"]]))
    same_text = sum(1 for r in calls if r["text_sha256"] == first[r["case"]]["text_sha256"])
    same_verdict = sum(1 for r in calls if verdict(r) == verdict(first[r["case"]]))
    cases = by_case(calls)
    cases_all_same = sum(1 for c, rs in cases.items() if all(key(r) == key(first[c]) for r in rs))
    cases_verdict_same = sum(1 for c, rs in cases.items() if all(verdict(r) == verdict(first[c]) for r in rs))
    flips = sorted(c for c, rs in cases.items() if any(verdict(r) != verdict(first[c]) for r in rs))
    return {"calls": len(calls), "same_tokens": same_tokens, "same_text": same_text, "same_verdict": same_verdict,
            "cases": len(cases), "cases_all_same_tokens": cases_all_same, "cases_all_same_verdict": cases_verdict_same,
            "verdict_flips": flips}


SOLVES = re.compile(r'"solves"\s*:\s*(true|false)')


def divergence(rows: list[dict]) -> dict:
    """For each case, every pair of different answers among `rows`: where they first differ, and whether the verdict
    ("solves", the answer's first field) was already written identically before that point."""
    pairs = after = 0
    offsets = []
    for rs in by_case(rows).values():
        texts = sorted({r["text"] for r in rs})
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                a, b = texts[i], texts[j]
                n = next((k for k, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
                m = SOLVES.search(a)
                pairs += 1
                offsets.append(n)
                if m and m.end() <= n:
                    after += 1
    return {"pairs": pairs, "verdict_written_before_divergence": after,
            "first_difference_char_median": statistics.median(offsets) if offsets else None}


def stated(r: dict) -> str:
    """The `solves` the model wrote, even when the rest of its answer isn't valid JSON."""
    m = SOLVES.search(r["text"])
    return ("pass" if m.group(1) == "true" else "fail") if m else "none"


def verdict_agreement(a: list[dict], b: list[dict]) -> dict:
    """Two setups' first calls per case (greedy: each setup's own answer): same verdict? same text? And the same
    `solves` as written, so a verdict lost to broken JSON shows apart from a changed opinion."""
    fa, fb = {c: rs[0] for c, rs in by_case(a).items()}, {c: rs[0] for c, rs in by_case(b).items()}
    common = sorted(set(fa) & set(fb))
    diff = [c for c in common if verdict(fa[c]) != verdict(fb[c])]
    opinion = [c for c in common if stated(fa[c]) != stated(fb[c])]
    return {"cases": len(common), "same_verdict": len(common) - len(diff), "same_text": sum(
        1 for c in common if fa[c]["text_sha256"] == fb[c]["text_sha256"]), "differ": diff,
        "same_stated": len(common) - len(opinion), "stated_differ": opinion}


def accuracy(rows: list[dict]) -> dict:
    """The first call per case against the labels: good should pass; bad and borderline should fail."""
    out = defaultdict(Counter)
    for c, rs in by_case(rows).items():
        out[rs[0]["label"]][verdict(rs[0])] += 1
    return {lab: dict(cnt) for lab, cnt in out.items()}


def shopping(rows: list[dict]) -> dict:
    """Per case, the share of independent sampled calls that pass, and what a shopper with 5 calls would get."""
    per_case = {}
    for c, rs in by_case(rows).items():
        v = Counter(verdict(r) for r in rs)
        n = len(rs)
        p = v["pass"] / n
        per_case[c] = {"label": rs[0]["label"], "calls": n, "pass": v["pass"], "fail": v["fail"],
                       "invalid": v["invalid"], "pass_rate": p, "p_any_pass_in_5": 1 - (1 - p) ** 5}
    by_label = defaultdict(list)
    for c, s in per_case.items():
        by_label[s["label"]].append(s)
    summary = {}
    for lab, ss in by_label.items():
        calls = sum(s["calls"] for s in ss)
        passes = sum(s["pass"] for s in ss)
        summary[lab] = {"cases": len(ss), "calls": calls, "passes": passes, "pass_rate": passes / calls,
                        "cases_always_pass": sum(1 for s in ss if s["pass"] == s["calls"]),
                        "cases_never_pass": sum(1 for s in ss if s["pass"] == 0),
                        "cases_mixed": sum(1 for s in ss if 0 < s["pass"] < s["calls"]),
                        "invalid": sum(s["invalid"] for s in ss)}
    return {"per_case": per_case, "by_label": summary}


def speed(rows: list[dict]) -> dict:
    lat = [r["latency_s"] for r in rows]
    out_tok = [r["completion_tokens"] or 0 for r in rows]
    in_tok = [r["prompt_tokens"] or 0 for r in rows]
    s = {"calls": len(rows), "latency_median_s": statistics.median(lat), "latency_max_s": max(lat),
         "prompt_tokens_median": statistics.median(in_tok), "completion_tokens_median": statistics.median(out_tok),
         "end_to_end_tokens_per_s": sum(out_tok) / sum(lat)}
    t = [r["timings"] for r in rows if r.get("timings")]
    if t:
        s["prompt_eval_tokens_per_s_median"] = statistics.median(x["prompt_per_second"] for x in t)
        s["generation_tokens_per_s_median"] = statistics.median(x["predicted_per_second"] for x in t)
    return s


def fmt_within(name: str, w: dict) -> str:
    n = w["cases"]
    return (f"| {name} | {w['calls']} | {w['same_tokens']} of {n} | {w['same_verdict']} of {n} | "
            f"{w['distinct_outputs']} |")


def main() -> None:
    data = load()
    summary: dict = {"within": {}, "versus": {}, "agreement": {}, "accuracy": {}, "shopping": {}, "speed": {}}
    has = data.__contains__

    print("## Repeats within one setup (each case N times)\n")
    print("| Setup | Calls | Cases with every call token-identical | Cases with every verdict identical | "
          "Distinct outputs (30 = one per case) |\n|---|---|---|---|---|")
    for tag in data:
        if "shop" in tag or "nonce" in tag:
            continue
        w = within(data[tag])
        summary["within"][tag] = w
        print(fmt_within(tag, w))

    # (reference, its repeat, setup, the setup's repeats or None for all, what is compared)
    pairs = [
        ("vllm-d-seq", 0, "vllm-d-seq", None, "cold call vs every repeat"),
        ("vllm-d-seq", 1, "vllm-d-seq", list(range(1, 100)), "warm vs warm repeats"),
        ("vllm-d-seq", 1, "vllm-d-c8", None, "warm vs batched with 8 in flight"),
        ("vllm-d-seq", 1, "vllm-d-c32", None, "warm vs batched with 32 in flight"),
        ("vllm-d-seq", 0, "vllm-d-restart1", [0], "cold vs cold, fresh process"),
        ("vllm-d-seq", 1, "vllm-d-restart1", [1], "warm vs warm, fresh process"),
        ("vllm-d-seq", 0, "vllm-d-restart2", [0], "cold vs cold, fresh process"),
        ("vllm-d-seq", 1, "vllm-d-restart2", [1], "warm vs warm, fresh process"),
        ("vllm-dnopc-seq", 0, "vllm-dnopc-seq", None, "no prefix cache: first vs every repeat"),
        ("vllm-dnopc-seq", 0, "vllm-dnopc-c32", None, "no prefix cache: sequential vs batched 32"),
        ("vllm-dnopc-seq", 0, "vllm-d-seq", [0], "no prefix cache vs cold call with it"),
        ("vllm-bi-seq", 0, "vllm-bi-seq", None, "first vs every repeat"),
        ("vllm-bi-seq", 0, "vllm-bi-c8", None, "sequential vs batched 8"),
        ("vllm-bi-seq", 0, "vllm-bi-c32", None, "sequential vs batched 32"),
        ("vllm-bi-seq", 0, "vllm-bi-restart1", None, "fresh process, cold and warm"),
        ("vllm-d-seed-seq", 0, "vllm-d-seed-seq", None, "seeded: first vs every repeat"),
        ("vllm-d-seed-seq", 0, "vllm-d-seed-c32", None, "seeded: sequential vs batched 32"),
        ("vllm-d-seed-seq", 0, "vllm-d-restart1-seed", None, "seeded: fresh process (warm)"),
        ("vllm-d-seed-seq", 0, "vllm-d-restart2-seed", None, "seeded: fresh process (warm)"),
        ("vllm-d-restart1-seed", 0, "vllm-d-restart2-seed", None, "seeded: two fresh processes, same history"),
        ("vllm-bi-seed-seq", 0, "vllm-bi-seed-seq", None, "seeded: first vs every repeat"),
        ("vllm-bi-seed-seq", 0, "vllm-bi-seed-c32", None, "seeded: sequential vs batched 32"),
        ("vllm-bi-seed-seq", 0, "vllm-bi-restart1-seed", None, "seeded: fresh process"),
        ("llama-cpu-t8-q8_0-nocache", 0, "llama-cpu-t8-q8_0-nocache", None, "first vs every repeat"),
        ("llama-cpu-t8-q8_0-nocache", 0, "llama-cpu-t8-q8_0", None, "cache_prompt off vs on (default)"),
        ("llama-cpu-t8-q8_0-nocache", 0, "llama-cpu-t16-q8_0-nocache", None, "8 vs 16 threads"),
        ("llama-cpu-t8-q8_0-nocache", 0, "llama-cpu-t1-q8_0-nocache", None, "8 vs 1 thread"),
        ("llama-cpu-t8-q8_0-nocache", 0, "llama-gpu-q8_0-nocache", None, "CPU vs CUDA, same GGUF"),
        ("llama-gpu-q8_0-nocache", 0, "llama-gpu-q8_0-nocache", None, "first vs every repeat"),
        ("llama-gpu-q8_0-nocache", 0, "llama-gpu-q8_0", None, "cache_prompt off vs on (default)"),
        ("llama-gpu-q4_k_m-nocache", 0, "llama-gpu-q4_k_m", None, "Q4_K_M: cache_prompt off vs on (default)"),
        ("llama-cpu-t8-q4_k_m-nocache", 0, "llama-gpu-q4_k_m-nocache", None, "Q4_K_M: CPU vs CUDA"),
        ("llama-cpu-t8-q8_0-seed", 0, "llama-cpu-t8-q8_0-seed", None, "seeded: first vs every repeat"),
        ("llama-gpu-q8_0-seed", 0, "llama-gpu-q8_0-seed", None, "seeded: first vs every repeat"),
        ("llama-cpu-t8-q8_0-seed", 0, "llama-gpu-q8_0-seed", None, "seeded: CPU vs CUDA"),
    ]
    print("\n## Against a reference (each call vs one reference call of the same case)\n")
    print("| Reference (repeat) → setup: what | Calls token-identical | Calls verdict-identical | "
          "Cases always token-identical | Cases always verdict-identical | Verdict flips |\n|---|---|---|---|---|---|")
    for ref, ref_rep, other, reps, what in pairs:
        if not (has(ref) and has(other)):
            continue
        v = versus(data[ref], data[other], ref_rep, reps)
        if not v["calls"]:
            continue
        name = f"{ref} ({ref_rep}) → {other}: {what}"
        summary["versus"][name] = v
        print(f"| {name} | {v['same_tokens']} of {v['calls']} | {v['same_verdict']} of {v['calls']} | "
              f"{v['cases_all_same_tokens']} of {v['cases']} | {v['cases_all_same_verdict']} of {v['cases']} | "
              f"{', '.join(v['verdict_flips']) or '-'} |")

    agree = [("vllm-d-seq", "vllm-bi-seq"), ("vllm-d-seq", "vllm-dnopc-seq"),
             ("vllm-bi-seq", "llama-gpu-q8_0-nocache"), ("vllm-bi-seq", "llama-cpu-t8-q8_0-nocache"),
             ("vllm-bi-seq", "llama-gpu-q4_k_m-nocache"), ("vllm-bi-seq", "llama-cpu-t8-q4_k_m-nocache"),
             ("llama-cpu-t8-q8_0-nocache", "llama-gpu-q8_0-nocache"),
             ("llama-cpu-t8-q8_0-nocache", "llama-cpu-t8-q4_k_m-nocache"),
             ("llama-gpu-q8_0-nocache", "llama-gpu-q4_k_m-nocache"),
             ("llama-cpu-t8-q4_k_m-nocache", "llama-gpu-q4_k_m-nocache")]

    greedy = [t for t in data if not any(x in t for x in ("seed", "shop", "nonce"))]
    groups = {"vLLM default, greedy (every repeat, batch and restart)": [t for t in greedy if t.startswith("vllm-d")],
              "vLLM, every greedy setup": [t for t in greedy if t.startswith("vllm-")],
              "every greedy setup, both engines": greedy}
    print("\n## Where different answers to the same case first differ\n")
    print("| Calls pooled | Pairs of different answers | Verdict already written before they differ | "
          "Median character of the first difference |\n|---|---|---|---|")
    for name, tags in groups.items():
        rows = [r for t in tags for r in data[t]]
        if rows:
            d = divergence(rows)
            summary.setdefault("divergence", {})[name] = d
            print(f"| {name} | {d['pairs']} | {d['verdict_written_before_divergence']} of {d['pairs']} | "
                  f"{d['first_difference_char_median']} |")

    print("\n## Across setups, greedy (first call per case)\n")
    print("| Setup A vs setup B | Same text | Same verdict (the node's) | Same `solves` as written | "
          "Cases whose verdict differs | ... whose written `solves` differs |\n|---|---|---|---|---|---|")
    for a, b in agree:
        if has(a) and has(b):
            g = verdict_agreement(data[a], data[b])
            summary["agreement"][f"{a} vs {b}"] = g
            print(f"| {a} vs {b} | {g['same_text']} of {g['cases']} | {g['same_verdict']} of {g['cases']} | "
                  f"{g['same_stated']} of {g['cases']} | {', '.join(g['differ']) or '-'} | "
                  f"{', '.join(g['stated_differ']) or '-'} |")

    print("\n## Verdicts against the labels (first greedy call per case)\n")
    print("| Setup | good: pass / fail / invalid | bad: pass / fail / invalid | borderline: pass / fail / invalid |\n"
          "|---|---|---|---|")
    for tag in data:
        rows = data[tag]
        if "shop" in tag or rows[0]["sampling"] != "greedy" or rows[0]["concurrency"] != 1:
            continue
        acc = accuracy(rows)
        summary["accuracy"][tag] = acc
        cells = [f"{acc.get(lab, {}).get('pass', 0)} / {acc.get(lab, {}).get('fail', 0)} / "
                 f"{acc.get(lab, {}).get('invalid', 0)}" for lab in ("good", "bad", "borderline")]
        print(f"| {tag} | " + " | ".join(cells) + " |")

    for tag in [t for t in data if "shop" in t or "nonce" in t]:
        s = shopping(data[tag])
        summary["shopping"][tag] = s
        print(f"\n## Answer shopping: {tag} ({data[tag][0]['sampling']}, {len(data[tag])} calls)\n")
        print("| Label | Cases | Calls | Pass rate | Cases always pass | Cases never pass | Cases mixed | Invalid |\n"
              "|---|---|---|---|---|---|---|---|")
        for lab in ("good", "bad", "borderline"):
            if lab in s["by_label"]:
                b = s["by_label"][lab]
                print(f"| {lab} | {b['cases']} | {b['calls']} | {b['passes']} of {b['calls']} "
                      f"({b['pass_rate']:.0%}) | {b['cases_always_pass']} | {b['cases_never_pass']} | "
                      f"{b['cases_mixed']} | {b['invalid']} |")
        greedy = {c: verdict(rs[0]) for c, rs in by_case(data.get("vllm-bi-seq") or data["vllm-d-seq"]).items()}
        gains = defaultdict(list)
        print("\n| Case | Greedy verdict (first call, batch-invariant vLLM) | Passes of 20 sampled | "
              "P(a pass within 5 calls) | Shopper's gain over one call |\n|---|---|---|---|---|")
        for c, x in s["per_case"].items():
            gain = x["p_any_pass_in_5"] - x["pass_rate"]
            gains[x["label"]].append(gain)
            if x["label"] != "good":
                print(f"| {c} | {greedy.get(c, '?')} | {x['pass']} of {x['calls']} | {x['p_any_pass_in_5']:.0%} | "
                      f"+{gain:.0%} |")
        for lab, g in gains.items():
            s["by_label"][lab]["mean_gain_5_calls"] = sum(g) / len(g)
            s["by_label"][lab]["greedy_pass"] = sum(1 for c, x in s["per_case"].items()
                                                    if x["label"] == lab and greedy.get(c) == "pass")
        print("\nMean gain of a shopper with 5 calls over one honest sampled call, per label: " + ", ".join(
            f"{lab} +{sum(g) / len(g):.1%}" for lab, g in gains.items()))

    print("\n## Speed\n")
    print("| Setup | Calls | Median s per call | Median tokens in / out | Out tokens per s (end to end) | "
          "Prompt eval t/s | Generation t/s |\n|---|---|---|---|---|---|---|")
    for tag, rows in data.items():
        s = speed(rows)
        summary["speed"][tag] = s
        print(f"| {tag} | {s['calls']} | {s['latency_median_s']:.2f} | {s['prompt_tokens_median']:.0f} / "
              f"{s['completion_tokens_median']:.0f} | {s['end_to_end_tokens_per_s']:.1f} | "
              f"{s.get('prompt_eval_tokens_per_s_median', float('nan')):.0f} | "
              f"{s.get('generation_tokens_per_s_median', float('nan')):.1f} |")

    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
