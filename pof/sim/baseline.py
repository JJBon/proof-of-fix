"""The GridCraft baseline (data/gridcraft_baseline.json, task 6.1) as samplers for the simulation."""

from __future__ import annotations

import json
import random
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "data" / "gridcraft_baseline.json"


def load(path: Path = PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def size_sampler(baseline: dict):
    """Changed lines drawn like the merged PRs: a histogram bin by its count, then uniform within the bin."""
    hist = baseline["merged"]["changed_lines_histogram"]
    bins, lo = [], 1
    for label, count in hist.items():
        hi = int(label[2:]) if label.startswith("<=") else max(int(label[1:]) * 4, lo)
        bins.append((lo, hi, count))
        lo = hi + 1
    total = sum(c for _, _, c in bins)

    def sample(rng: random.Random) -> int:
        pick = rng.randrange(total)
        for lo_, hi_, count in bins:
            if pick < count:
                return rng.randint(lo_, hi_)
            pick -= count
        return bins[-1][1]

    return sample


def weekly_volume(baseline: dict) -> float:
    """Mean merged PRs per full week in the window (partial first and last weeks scaled up by day count)."""
    weeks = list(baseline["weekly"].values())
    return sum(w["merged"] for w in weeks) / max(1, len(weeks))
