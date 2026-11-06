"""The GPU's power while each run's calls were made (proof-of-fix#125), from an nvidia-smi log taken during the runs:

    nvidia-smi --query-gpu=timestamp,power.draw,utilization.gpu,memory.used --format=csv,noheader -l 2 > gpu.csv
    python3 power.py gpu.csv tag [tag ...]

A run's window is from its first call's start to its file's last write (each record's "at" is seconds from the run's
start). Watt-hours per case call divide the window's GPU energy by the run's case calls, so filler requests (in the
batched runs) are charged to the cases: an upper bound there. The GPU alone, not the CPU or the rest of the PC."""

from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"


def samples(path: str) -> list[tuple[float, float]]:
    out = []
    for line in Path(path).read_text().splitlines():
        parts = [p.strip() for p in line.split(",")]
        try:
            t = datetime.datetime.strptime(parts[0], "%Y/%m/%d %H:%M:%S.%f").timestamp()
            out.append((t, float(parts[1].split()[0])))
        except (ValueError, IndexError):
            continue
    return out


def main() -> None:
    log, tags = sys.argv[1], sys.argv[2:]
    data = samples(log)
    print("| Run | Case calls | Seconds | Mean GPU watts | GPU Wh per case call |\n|---|---|---|---|---|")
    for tag in tags:
        path = RESULTS / f"{tag}.jsonl"  # before it is compressed for the commit: its last write ends the window
        rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
        end = os.path.getmtime(path)
        start = end - max(r["at"] + r["latency_s"] for r in rows)
        w = [p for t, p in data if start <= t <= end]
        if not w:
            print(f"| {tag} | {len(rows)} | {end - start:.0f} | (no samples) | |")
            continue
        mean = sum(w) / len(w)
        print(f"| {tag} | {len(rows)} | {end - start:.0f} | {mean:.0f} | {mean * (end - start) / 3600 / len(rows):.3f} |")


if __name__ == "__main__":
    main()
