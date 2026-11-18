"""#241 (scripts/graph_test.py): a patch placed on a code graph, and the separation measures."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import graph_test as G  # noqa: E402

DIFF = """diff --git a/pkg/a.py b/pkg/a.py
index 1..2 100644
--- a/pkg/a.py
+++ b/pkg/a.py
@@ -10,4 +10,5 @@ def f():
 keep
-gone
+new
+newer
 keep
diff --git a/tests/test_a.py b/tests/test_a.py
new file mode 100644
--- /dev/null
+++ b/tests/test_a.py
@@ -0,0 +1,2 @@
+def test_f():
+    pass
"""


def graph(tmp: str) -> G.Graph:
    def node(i, label, f, line, **kw):
        return {"id": i, "label": label, "file_type": "code", "source_file": f, "source_location": f"L{line}",
                "_callable": True, **kw}
    g = {"nodes": [node("f", "f()", "pkg/a.py", 8), node("g", "g()", "pkg/a.py", 20),
                   node("h", "helper_name()", "pkg/b.py", 1), node("t", "test_f()", "tests/test_a.py", 1)],
         "links": [{"source": "g", "target": "f", "relation": "calls", "confidence": "EXTRACTED"},
                   {"source": "t", "target": "f", "relation": "calls", "confidence": "INFERRED"},
                   {"source": "g", "target": "h", "relation": "calls", "confidence": "EXTRACTED"}]}
    p = Path(tmp) / "g.json"
    p.write_text(json.dumps(g), encoding="utf-8")
    return G.Graph(p)


class TestPatch(unittest.TestCase):
    def test_changed_lines_are_old_file_lines(self):
        lines = G.changed_lines(DIFF)
        self.assertEqual(lines["pkg/a.py"], {11, 12})  # the removed line, and where the added ones go
        self.assertEqual(lines["tests/test_a.py"], set())  # a new file has no old lines
        self.assertEqual(G.diff_size(DIFF), 5)
        self.assertEqual(G.diff_size(DIFF, tests=False), 3)

    def test_test_files_are_told_apart(self):
        self.assertTrue(G.is_test("tests/test_a.py") and G.is_test("pkg/tests/x.py") and G.is_test("conftest.py"))
        self.assertFalse(G.is_test("pkg/a.py") or G.is_test("pkg/contest.py"))

    def test_features_on_a_small_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            g = graph(tmp)
            self.assertEqual(g.owner("pkg/a.py", 11), "f")
            self.assertEqual(g.owner("pkg/a.py", 3), None)
            f = G.features({"diff": DIFF, "issue": "calling `helper_name` breaks"}, g)
            self.assertEqual((f["n_funcs"], f["n_files"], f["touches_tests"]), (1, 1, 1))
            self.assertEqual((f["callers"], f["tests_calling"], f["callees"]), (1, 1, 0))
            self.assertEqual((f["issue_distance"], f["issue_misses"]), (2, 1))  # f - g - helper_name
            self.assertEqual(g.guessed, 1)


class TestMeasures(unittest.TestCase):
    def test_auc(self):
        self.assertEqual(G.auc([3, 4], [1, 2]), 1.0)
        self.assertEqual(G.auc([1, 2], [1, 2]), 0.5)
        lo, hi = G.auc_ci([3, 4, 5], [1, 2, 3], n=200)
        self.assertTrue(lo <= G.auc([3, 4, 5], [1, 2, 3]) <= hi)

    def test_the_flag_rule_respects_its_budget(self):
        t, side, fb, fg = G.flag_rule([5, 6, 7, 1], [1, 1, 2, 2, 2, 3, 3, 3, 3, 9], budget=0.10)
        self.assertEqual((side, fb, fg), (1, 3, 1))
        self.assertLessEqual(fg, 1)


if __name__ == "__main__":
    unittest.main()
