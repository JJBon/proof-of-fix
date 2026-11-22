"""The determinism experiment's judge cases (proof-of-fix#125, experiments/determinism/): 30 cases in the shape
oracle/judge.py takes, 10 good, 10 bad and 10 borderline; each turns into the node's real prompt; and run.py pins its
sampling fields in each engine's names. No model call and no server: the experiment itself needs a GPU and runs by
hand (experiments/determinism/campaign.sh)."""

from __future__ import annotations

import importlib.util
import json
import unittest
from collections import Counter
from pathlib import Path

from oracle.judge import build_prompt
from oracle.sandbox import TestRun

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments" / "determinism"


def _module(name: str):
    spec = importlib.util.spec_from_file_location(f"determinism_{name}", EXP / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCases(unittest.TestCase):
    def setUp(self):
        self.cases = [json.loads(p.read_text()) for p in sorted((EXP / "cases").glob("*.json"))]

    def test_ten_of_each_label(self):
        self.assertEqual(Counter(c["label"] for c in self.cases), {"good": 10, "bad": 10, "borderline": 10})

    def test_good_and_borderline_pass_their_tests(self):
        for c in self.cases:
            if c["label"] != "bad":
                self.assertEqual(c["tests"]["exit_code"], 0, c["id"])

    def test_each_case_is_a_node_prompt(self):
        for c in self.cases:
            t = c["tests"]
            run = TestRun(t["image"], tuple(t["command"]), t["exit_code"], t["results_sha256"], t["logs_sha256"])
            system, user = build_prompt({k: c[k] for k in ("id", "repo", "issue", "commit", "diff", "context")}, run)
            self.assertIn("Test runs: the project's tests", user)
            self.assertIn(c["diff"].splitlines()[0], user)


class TestSampling(unittest.TestCase):
    def test_pinned_fields_per_engine(self):
        run = _module("run")
        self.assertEqual(run.sampling_body("vllm", "greedy", None),
                         {"temperature": 0.0, "repetition_penalty": 1.0, "return_token_ids": True})
        self.assertEqual(run.sampling_body("llama", "qwen", 7),
                         {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "repeat_penalty": 1.05, "seed": 7,
                          "min_p": 0.0})
        self.assertEqual(run.sampling_body("llama", "server-default", None), {})  # what the node sends today


if __name__ == "__main__":
    unittest.main()
