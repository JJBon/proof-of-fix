# Does a code graph separate good fixes from bad ones? v1 (proof-of-fix#241; 2026-11-15)

**Status: exploratory, and mostly a null result.** The cases are #160's 228 labelled fixes, which earlier reports already used. No model call.

**Commands:** `scripts/graph_test.py build`, `features` and `report` (the script's header gives the arguments). The graphs were built with graphify 0.9.109 (tree-sitter, `--code-only --no-cluster`, an empty environment so no API key could reach it). Building the 152 base commits took 59 minutes on one PC.

## In brief
- **The graph features don't separate good fixes from bad ones in any useful way.** Ten features were fixed before any result was looked at. On the graph ones, a bad fix scores higher than a good one between 38 % and 58 % of the time, where 50 % is chance.
- **The two features that looked strong are artefacts of the data.** Every good fix written by the project itself includes its tests, and almost no other fix does, so "changes a test file" and total size separate who wrote the patch, not whether it is right.
- **The one honest signal is size, and it needs no graph.** Tests aside, bad fixes are about twice as long as good ones (median 28 and 31 lines against 14). That separates 60–66 % of the time.
- **Nothing here would help Opus much.** Among the fixes Opus passed, the best rule on any single feature flags at most 6 of its 18 false passes on fixes the tests fail, and at most 5 of its 35 on fixes that pass them, while flagging 2 to 4 of the 47 good fixes. Those rules were picked on the same cases, so even that is optimistic.
- **The tool itself did well:** it built all 152 graphs, ten rebuilt at random came out identical, and it placed the patch on the graph in 210 of 228 cases. 16 % of its call links are guessed, not read.
- **Recommendation: drop the graph as a filter.** Whether it helps as context for a judge or as a search guide for a contender is a different question, which this test does not answer and which costs model calls.

## 1. What was tested
- **The cases:** 50 good fixes (37 the project's own, 13 written by a model and passing every test), 100 bad fixes the hidden tests fail, and 78 bad fixes that pass the tests and are wrong.
- **The graph:** one per repository at the case's base commit, by parsing only. Functions, classes, and the links between them (calls, imports, inheritance, containment).
- **The patch on the graph:** each changed line is given to the function or class that starts last before it. The tool gives no end line, so code after a function's end is given to that function.
- **The features, fixed in advance** (#241): the functions and files changed, size, whether a test file is changed, other functions that call the changed ones, functions they call, tests that call them, the distance from the changed code to code the issue names, whether the issue names code the patch leaves alone, and how far apart the changed functions are.
- **The measure:** the chance that a bad fix scores higher than a good one (0.50 is chance), with a 95 % interval by bootstrap.
- **Only what the network would have:** the issue, the patch and the repository. The hidden tests are not used.

## 2. The results
See the tables in the appendix. Reading them:
- **Graph features, fixes the tests fail:** callers 0.38, functions changed 0.43, spread 0.46, callees 0.48, tests calling 0.49, distance to the issue's code 0.52, issue's code left alone 0.55. Only callers excludes chance, and in the direction opposite to the idea: bad fixes change code with *fewer* callers.
- **Graph features, fixes that pass the tests:** distance to the issue's code 0.38 (bad fixes are *closer* to the code the issue names, again opposite to the idea), tests calling 0.58, spread 0.58, callers 0.56, functions changed 0.55.
- **Files changed** separates a little (0.60 and 0.69): bad fixes touch more files. It is a count from the diff, not from the graph.
- **With twenty intervals, about one would exclude chance by luck.** Five do, outside the artefacts, and none is large.
- **The authorship column** compares good fixes written by a model with good fixes written by the project. "Changes a test file" (0.04) and total size (0.24) are far from 0.50 there, which is what marks them as artefacts. The post hoc size measure, tests aside, is not (0.43, interval 0.26–0.63).

## 3. Why it probably fails
- **Most bad fixes are in the right place.** They change the same function a good fix would, with the wrong logic. On a graph that looks identical to a good fix.
- **The "patched one caller of many" pattern is not visible in these features.** Callers and callees are counted, but a count can't tell a fix that should have gone into the shared function from one that rightly went into the caller.
- **Naming the issue's code is common to both.** A model that writes a wrong fix still goes to the code the issue names.

## 4. What this does not show
- **The graph as context.** A judge told "three other functions call this one and the patch changes one of them", or a contender using the callers to decide where to write a test, is not tested here. That is hypothesis Hb in #241 and needs model calls.
- **Richer features.** These are static counts on the graph before the patch. The graph after the patch, data flow, or the tests' real coverage might do better.
- **History.** There is no record here of earlier fixes on the same code, which was half of the proposal.
- **Other languages and repositories.** These are eleven Python projects from one benchmark. Python's dynamic calls are the hard case for a parsed graph.
- **A confirmatory result.** The cases were used before, the thresholds in the last table were chosen on them, and one feature was added after the first look (marked post hoc).

## 5. What it means
1. **Don't add a graph filter to the checker.** It would cost a build per check and reject good fixes for no measured gain.
2. **Size is worth a line in the judges' prompt, not a rule.** It is free, and weak.
3. **If the graph is tried again, try it where it was not tested:** as a tool the contender's agent queries when looking for a failing test. That belongs in the paid measurement of how often a contender finds a test (#236, task 10.3), as one arm with the graph and one without.
4. **The builder is usable for that:** fast, reproducible on ten of ten rebuilds, and offline.

## Appendix: the full output

Cases: 50 good (37 the project's own, 13 written by a model), 100 bad that fail the tests, 78 bad that pass them. The patch was placed on the graph in 210 of 228; the issue names code in 184. Call links guessed, not read: 16 % on average.

### How well each feature separates (0.50 is chance; above it, higher values mean bad; 95 % interval by bootstrap; * excludes chance)

| Feature | Bad (fail the tests) vs good | Bad (pass the tests) vs good | Good by a model vs good by the project (authorship) |
|---|---|---|---|
| Functions the patch changes | 0.43 (0.34–0.52) | 0.55 (0.46–0.66) | 0.44 (0.30–0.59) |
| Files the patch changes (tests aside) | 0.60 (0.53–0.68) * | 0.69 (0.59–0.78) * | 0.57 (0.42–0.74) |
| Lines added and removed (no graph: the baseline) | 0.53 (0.44–0.62) | 0.56 (0.46–0.66) | 0.24 (0.09–0.43) * |
| The patch changes a test file | 0.28 (0.21–0.36) * | 0.20 (0.13–0.27) * | 0.04 (0.00–0.12) * |
| Other functions that call the changed ones (tests aside) | 0.38 (0.29–0.48) * | 0.56 (0.45–0.66) | 0.46 (0.29–0.64) |
| Functions the changed ones call | 0.48 (0.39–0.58) | 0.49 (0.39–0.59) | 0.55 (0.35–0.74) |
| Test functions that call the changed ones | 0.49 (0.42–0.56) | 0.58 (0.50–0.66) * | 0.41 (0.31–0.52) |
| Steps from the changed code to code the issue names | 0.52 (0.41–0.61) | 0.38 (0.28–0.48) * | 0.56 (0.38–0.72) |
| The issue names code and the patch changes none of it | 0.55 (0.47–0.63) | 0.48 (0.39–0.57) | 0.57 (0.41–0.72) |
| Largest distance between two changed functions | 0.46 (0.37–0.55) | 0.58 (0.49–0.68) | 0.43 (0.29–0.58) |
| Lines added and removed, tests aside (no graph; post hoc) | 0.60 (0.50–0.69) * | 0.66 (0.56–0.76) * | 0.43 (0.26–0.63) |

### Medians

| Feature | Good | Bad (fail the tests) | Bad (pass the tests) |
|---|---|---|---|
| Functions the patch changes | 1 | 1 | 2 |
| Files the patch changes (tests aside) | 1 | 1 | 2 |
| Lines added and removed (no graph: the baseline) | 28 | 35 | 43 |
| The patch changes a test file | 1 | 0 | 0 |
| Other functions that call the changed ones (tests aside) | 1 | 1 | 2 |
| Functions the changed ones call | 2 | 2 | 2 |
| Test functions that call the changed ones | 0 | 0 | 0 |
| Steps from the changed code to code the issue names | 3 | 2 | 1 |
| The issue names code and the patch changes none of it | 0 | 1 | 0 |
| Largest distance between two changed functions | 0 | 0 | 2 |
| Lines added and removed, tests aside (no graph; post hoc) | 14 | 28 | 31 |

### Among the fixes Opus passed (47 good; the best rule on one feature that flags at most 10 % of those good fixes; chosen on these cases, so optimistic)

| Feature | Bad that fail the tests, passed by Opus: flagged | Bad that pass the tests, passed by Opus: flagged | Rule (first / second) | Good flagged (first / second) |
|---|---|---|---|---|
| Functions the patch changes | 2 of 18 | 0 of 35 | ≤ 0 / none | 2 of 47 / 0 of 47 |
| Files the patch changes (tests aside) | 1 of 18 | 2 of 35 | ≥ 6 / ≥ 4 | 1 of 47 / 2 of 47 |
| Lines added and removed (no graph: the baseline) | 9 of 18 | 2 of 35 | ≤ 6 / ≤ 4 | 3 of 47 / 2 of 47 |
| The patch changes a test file | 0 of 18 | 0 of 35 | none / none | 0 of 47 / 0 of 47 |
| Other functions that call the changed ones (tests aside) | 1 of 18 | 3 of 35 | ≥ 43 / ≥ 13 | 0 of 47 / 2 of 47 |
| Functions the changed ones call | 0 of 18 | 3 of 35 | none / ≥ 9 | 0 of 47 / 2 of 47 |
| Test functions that call the changed ones | 2 of 18 | 5 of 35 | ≥ 6 / ≥ 2 | 3 of 47 / 4 of 47 |
| Steps from the changed code to code the issue names | 0 of 18 | 0 of 35 | none / none | 0 of 47 / 0 of 47 |
| The issue names code and the patch changes none of it | 0 of 18 | 0 of 35 | none / none | 0 of 47 / 0 of 47 |
| Largest distance between two changed functions | 0 of 18 | 0 of 35 | none / none | 0 of 47 / 0 of 47 |
| Lines added and removed, tests aside (no graph; post hoc) | 6 of 18 | 2 of 35 | ≤ 2 / ≥ 117 | 2 of 47 / 2 of 47 |
