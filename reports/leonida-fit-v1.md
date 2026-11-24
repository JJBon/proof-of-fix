# Leonida and proof-of-fix: how the project works, and whether we fit (draft v1.1)

For proof-of-fix #319.

- **v1** (sections 1–9) is a snapshot taken 2026-11-23 at about 17:50 UTC, about 70 hours after the repository was created (2026-11-20 20:07 UTC).
- **v1.1** adds sections 10–14, with data fetched 18:20–19:30 UTC. The 10-second summary is section 14. It covers:
  - evidence of harm from unverified merges
  - why PR CI fails
  - spec-driven development
  - a pre-registration draft for a replay
  - the updated verdict

The v1.1 counts are slightly higher than v1's because the data was fetched later: 3,627 merged PRs, 838 closed without merging, 3,584 open.

Method: read-only GitHub REST and GraphQL calls only. Nothing was cloned, downloaded or run. I read the small text files through the contents API. Counts for PRs and issues cover the full population, fetched through GraphQL (7,674 PRs and 293 issues). Results marked **(sample)** or **(estimate)** are not full counts.

## TL;DR

- **The project is not a malware lure in the usual sense.** It is a real, very large source tree:
  - 2,264 files and 38 MB, mostly Python and C++.
  - No releases and no tracked binaries. A CI job blocks `.exe`, `.dll` and game formats.
  - An RDNA2 → SPIR-V shader translator, a PE loader with GDK shims, and a D3D12 → Vulkan layer.
  - The game does not boot yet.
- **Almost all of the work is done by AI coding agents, and the owner merges at machine speed.** In under 3 days:
  - 7,674 PRs from 830 authors, and 3,620 of them were merged.
  - The owner (`ItsNotRexed`) merged 3,181 of those, with a peak of **520 merges in one hour**.
  - 93 of 100 sampled merged PRs say they are AI-assisted.
- **The bottleneck is checking the work, not doing it or merging it.**
  - 57% of merged PRs had **no review**.
  - In a sample of 100 merged PRs, **only 12 had green CI on their head commit**. 43 had failing checks, 30 had none and 15 were still pending.
  - CI on `main` has not finished since 2026-11-23 03:45 UTC. Since then every run is cancelled by the next push. The last successful CI run on `main` was 2026-11-22 12:29 UTC.
  - Fork PRs wait for a maintainer to approve CI.
  - Coordination happens in a "Coordinating who works on what" issue, now on its 48th thread with **16,889 comments**.
- **proof-of-fix would only help with part of this.** Paying solvers adds nothing, because free agent labour is already flooding in. Machine-checked verdicts could help the CPU-only work: the translator semantic suite and the standard-library unit tests, which are deterministic and need no GPU or game files.
- **Most of the critical path cannot be checked by our validators.** GPU tests need specific hardware, and the boot work needs the retail executable.
- **The legal and reputational risk is high.** Leonida targets a commercial game within days of its release. Its boot work relies on a retail executable that issues say has leaked. The publisher took down and sued over re3/reVC.
- **Recommendation: do not fund or pilot on Leonida.** Use a lower-risk project for the first "we add value here" pilot. Candidates are listed in section 9.

---

## 1. What the project is and how it's built

**What it claims to be.** "Leonida Is A Native PC Recompilation Of The Xbox Version Of Grand Theft Auto 6". The README calls it "built on your PC from your own copy". It is GPL-3.0-or-later, mostly Python, and uses `main` as the default branch.

**What the README says it does.** The Xbox Series CPU is x86-64, so the plan is to load the game's own executable and run it natively, with the console's system software reimplemented as shims. The console's RDNA2 GPU shaders are translated to SPIR-V for Vulkan. Models, textures and audio are read from the user's package.

**What the repository says it does not contain.** "does not contain the game, keys or an executable". It says it "does not explain how to get them", and that the user's files must be "already readable on disk".

**Status, from the README:**
- "Early. The game does not boot yet."
- It claims all 26,503 shaders translate and pass `spirv-val`, and that 382,781 models were recovered in a scan.
- The PE loader runs a stand-in executable.
- D3D12 → Vulkan is "in progress".

**Requirements:**
- The user's own Xbox Series package, version 1.0.2.1.
- Windows 10/11 with about 400 GB of work space (about 30 GB for a run-only build).
- Python 3.12+, .NET 8, the Vulkan SDK, LLVM 21+ with the AMDGPU target, and VS2022.

**Tree.** 2,328 entries (2,264 files, 38.2 MB, not truncated):

| Kind | Count | Size |
|---|---|---|
| Python | 1,215 files | 23.0 MB |
| C++ | 268 files | 7.6 MB |
| Headers | 128 files | – |
| Hand-written `.asm` / `.s` test fixtures | 302 + 100 files | – |
| Markdown docs | 105 files | 3.3 MB |

- The largest file is `tools/rdna2spirv.py` at 1.08 MB.
- Top-level folders: `tests/` (1,067 files), `runtime/` (724), `tools/` (306), `docs/` (86), `third_party/` (33), `scripts/` (20) and `viewer/`.
- There is a single submodule: `third_party/rpf9-explorer`. It points to `breadbbbb/rpf9-explorer`, a repo created 2026-11-20 (3 hours before Leonida) that has **no licence**.
- `AGENTS.md` is a 7.5 KB guide for coding agents. CONTRIBUTING and the PR template ask contributors to say whether the work was AI-assisted.

**Governance files:**

| File | Status |
|---|---|
| CODEOWNERS | None |
| Code of conduct | None |
| Branch protection on `main` | Off (`protected: false`, no required checks; the rulesets list is empty) |
| Community health score | 71% |
| Discussions | Off |
| Discord | `discord.gg/rexed` |

**Malware-lure check.** Signs that argue against a lure:
- There are no releases, no tags and no release assets.
- No `.exe`, `.dll`, `.msi`, `.zip` or `.bin` files are tracked. The only binary is `assets/logo.png`.
- The `No Game Data` CI job fails any tracked `.exe` or `.dll` and any game format.
- `Build.bat` only finds Python or offers to install it. It installs through winget, or downloads `python-3.12.10-amd64.exe` from python.org and checks a pinned SHA-256 first. **I did not check that hash against python.org.** After that it runs `make_game.py`.
- None of the PowerShell scripts I read use `Invoke-Expression`, base64 or encoded commands. The only network call in them is a `git clone` of `llvm/llvm-project` in `build_llvm_mc.ps1`.

Supply-chain red flags, which are more relevant than a classic lure:
- About 1.1 million lines were added through 3,620 merged PRs in 3 days. Most were unreviewed and AI-written. No person can audit `make_game.py` (150 KB) or `tools/` at that pace, and both run on users' PCs.
- Workflows exist that are not in `main`'s tree: `installer`, `Launcher`, `website`, `CodeQL`, `Dependency review` and `Build-script review`. They come from PR branches. For example, the `installer` runs come from a fork's `install/one-liner-bootstrap` branch and are marked `action_required`. Installer and launcher PRs are the obvious way in for a malicious change.
- CONTRIBUTING tells users to exclude a `%TEMP%` folder from antivirus because `loader_test` writes PE images there. The reason is plausible, but "add an AV exclusion" is the same advice malware gives.
- Issues link to a leaked executable ("Cyberleek exe dropped": #6702, #6729, #6736, #6741, #6907). Users who go looking for a leaked `.exe` are the classic way malware gets in, even if the repository itself is clean.
- Some users suspect it themselves: #6398 is titled "pls dont be a bitcoin miner".
- **v1.1: a confirmed malicious PR.** #7139, "Refactor PE loader for efficiency and functionality", was opened 2026-11-23 at 16:01 UTC.
  - It came from the account `buneincoming`, which a reviewer says was created that day at 15:40 UTC; this is its only PR.
  - It added a **Bitcoin clipboard hijacker** to `runtime/src/pe_loader.cpp`. The regex and the replacement address are hidden as hex `wchar_t` arrays, and a "worker thread" calls `AddClipboardFormatListener` and `SetClipboardData`. It would start in every `gta6rt` process.
  - Two contributors caught it by reading the diff, at 16:33 and 16:35 UTC; one says the work was AI-assisted. One then scanned the heads of 998 other open PRs and found no other match. The PR was closed at 16:42 UTC, **without being merged**.
  - This is the lure risk in concrete form. The repository's merge pace (section 4) leaves little margin.
  - **What it means for proof-of-fix:**
    - A tests-only verdict would very likely **pass** this PR. No test touches the clipboard, and the payload only runs on Windows in `gta6rt`.
    - Only a judge reading the diff, plus an issue-fit check (no registered issue asks for a "worker thread"), would flag it.
    - Our validators would have **executed** that code. Building `gta6rt` and running its tests could start the worker, which is why the replay design in section 13 runs untrusted code in a throwaway container with no network.

**Accounts.**
- The owner account was created 2026-07-06. The bio reads "High school student who likes to port games to PC and web". It has 883 followers.
- The top contributors are not mostly brand-new accounts. Of 12 I checked, 3 were created in 2026: `slopgobblercobbler` (2026-10), `kotorvr` (2026-09) and `IAmNotSiob` (2026-04).
- The coordinator `KoertLichtendonk` has had an account since 2014.

**Stars.** I could not check the star pattern. The stargazers and watchers endpoints return 404 to our token, including for `cli/cli`, so this is a limit of our token, not a sign about this repo. The first 100 forks appeared within about 23 hours.

**Context (from public knowledge, not from the API).** Rockstar's announced console release date for GTA VI was 2026-11-19. The repository appeared one day later.

## 2. Contributors and governance

**Volume:**
- 10,895 commits on `main`: 9 on Nov 20, 981 on Nov 21, 8,275 on Nov 22 and 1,630 on Nov 23 so far.
- The contributors API lists 514 contributors.
- `ItsNotRexed` has 3,994 commits. These are mostly early direct pushes. Recent merges are rebased through GitHub, with `web-flow` as committer.
- The next authors by commits are `slopgobblercobbler` (955) and `evilclanker9000` (562), then a long tail.

**Who merges.** All 3,620 merged PRs were merged by two accounts: `ItsNotRexed` (3,181, 88%) and `shayderrr` (439).
- Merges peaked at 520 in the hour from 11:00 UTC on Nov 23, about one every 7 seconds, which **almost certainly means merging by script**.
- The owner merged none of their own PRs; their own changes went straight to `main`.

**Coordination.** Work is claimed in a rolling issue, "Coordinating who works on what" (#156, #374, #634 … #7913, 48 threads).
- The threads hold 16,889 comments, 91% of all issue comments.
- A script builds the tables from open PRs and fork branches, and `KoertLichtendonk` checks them.
- Work items carry IDs such as `TEST-57`, `ASSET-628`, `BUILD-2909` or `D3D-86`.
- #313 is the D3D12 → Vulkan critical-path page.
- #7154 is a "Boot log for coding agents", where agents "talk to each other to decide the next step". It opens with prompt-injection guardrails for AI agents.
- There is outside coordination on Discord. Issues #6233 and #6343 are ban appeals, and #6796 says the server is down.

**Bus factor.** Two people can merge, and there is one coordinator.

## 3. Issues

The "3.3k open issues" in the repository metadata are **mostly PRs**. `open_issues_count` (3,341) = 130 open issues + 3,219 open PRs (now 3,268). There are only **293 real issues**: 130 open and 163 closed.

**Per day:** Nov 21: 34, Nov 22: 128, Nov 23: 131 (partial day).

**Labels.** Only `bug` is used, on 33 issues, through the bug-report form. The 11 other default labels are unused. No issue has an assignee.

**Closures.** 147 completed, 15 not planned, 1 duplicate.

**Types (estimate, a keyword classification of titles):**

| Type | Count | Notes |
|---|---|---|
| Bugs and technical findings | 158 | Many are filed in bulk by agent-style accounts. `lumenpearson`, `TurboSosiska304`, `ray3242` and `reviewbd` filed 56 between them. Examples: "spirv_asm accepts repeated type result IDs" and "hashdict.py: --out in a missing folder ends in a traceback" |
| Coordination threads | 48 | |
| Off-topic, meta, leaked exe or community | 46 | Leaked-exe posts, Discord, "Please host this project somewhere else", "You have no clue of what you're doing", ban appeals |
| Feature requests | 23 | |
| GPU results and claims | 12 | |
| Support and how-to | 6 | |

**First response (sample of 60 issues, excluding coordination threads):**
- 38 of the 60 got a reply from someone other than the author.
- The median time to first reply was **0.45 h**, and the p90 was 5.6 h.
- The owner was the first responder on 10 issues and commented on 14 of the 60.
- The owner closed 22 of the 31 closures where the actor is known.

**Duplicates and spam.** Little use of the `duplicate` state, but there is clear repetition: five or more leaked-exe threads, and claims filed as separate issues (#4304 and #4324 are both "claiming: RT-258"). Spam is low in absolute numbers because the work happens in PRs.

## 4. Pull requests

All counts below cover the full population of 7,674 PRs.

**State:**

| State | Count |
|---|---|
| Merged | 3,620 |
| Open | 3,268 (142 drafts) |
| Closed without merging | 786 |

Of PRs that were decided, 82.2% were merged.

**Created per day:** Nov 21: 419, Nov 22: 3,627, Nov 23: 3,627 (until about 17:50 UTC).

**Merged per day:** Nov 21: 295, Nov 22: 2,133, Nov 23: 1,192 (partial day).

**Time to merge (all merged PRs):** median **1.9 h**, p10 0.44 h, p90 **12.0 h**, p99 19.2 h. It is getting longer:

| Merged on | PRs | Median | p90 |
|---|---|---|---|
| Nov 21 | 295 | 0.64 h | 1.4 h |
| Nov 22 | 2,133 | 1.36 h | 3.4 h |
| Nov 23 | 1,192 | 8.5 h | 14.8 h |

**Reviews:**
- **2,079 of 3,620 merged PRs (57%) have zero reviews.** The mean is 0.57 reviews per merged PR, and the median is 0.
- In the sample of 100 merged PRs:
  - 40 had a review from someone other than the author, and 23 had an approval.
  - Reviewers were spread out: `Kam471` 10, `shayderrr` 10, `Flyander` 8, `kacper-serewis` 4, …
  - The Copilot reviewer appears twice.

**CI at merge (sample of 100 merged PRs).** Combined status of the head commit:

| Status | PRs |
|---|---|
| Success | 12 |
| Failure | 43 |
| No CI | 30 |
| Pending | 15 |

- The failing jobs are the real test jobs: `check` (Windows tests), `windows` (the runtime build), `linux-gpu-tools` and `semantic-tests`.
- Some failures may be inherited from a broken `main`, so this is an upper bound on "merged with a failing PR".

**Size of merged PRs:**
- Median 70 lines changed, p90 714, p99 2,571.
- Median 2 files changed, p90 6.
- In total, 1,137,739 lines added and 339,739 deleted.

**Authors:**
- 830 people opened a PR, and 467 have at least one merged.
- The top 10 authors account for 34% of merges. `evilclanker9000` opened 843 PRs and had 372 merged; `slopgobblercobbler` opened 594 and had 232 merged.

**First-time contributors.** Of 830 first PRs, 384 were merged, 354 are open and 92 were closed. That is an **80.7% merge rate** among decided first PRs. Almost every author is a first-timer here, because the repository is 3 days old.

**AI disclosure (sample).** 93 of 100 merged PRs disclose AI assistance: Claude Code, Codex, OpenCode or Hermes Agent. None says "no".

**Stale and backlog:**
- Open PRs have a median age of 5.8 h and a p90 of 20.3 h. 152 are older than 24 h.
- 1,604 open PRs have no review.
- The coordination issue lists:
  - About 1,700 open PRs with no conflicts. In "code read (CPU)" alone, 282 have no check and 1,024 have one.
  - Hundreds of PRs needing a rebase. For example, `evilclanker9000` has 139.
- The queue grows by roughly 2,000 PRs a day: 3,627 created against about 1,200–2,100 merged.

## 5. CI and tests

There are 14 workflow files plus Copilot and Dependabot. `main`'s tree has 5:

| Workflow | What it does |
|---|---|
| `ci.yml` | Windows: standard-library unit tests (`python -I tests/test_*.py`) and the `rpf9dump` .NET build and tests. Linux: translator tests with LLVM 21 `llvm-mc` and SPIRV-Tools. Semantic tests on several OSes. macOS Python tests. Viewer tests in Node. Linux standard-library tests |
| `runtime.yml` | MSVC runtime build and CPU tests, a Wine test matrix, and Linux GPU tools with GPU tests on **llvmpipe** (a software Vulkan) |
| `no-game-data.yml` | Blocks game and binary formats |
| `jactionlint.yml` | Lints the workflows |
| `xma2-decoder.yml` | XMA2 decoder |

There are 35,533 Actions runs in total.

**State of `main`:**
- `CI`: 66 runs succeeded, 36 failed and 430 were cancelled. The last success was 2026-11-22 12:29, and the last failure was 2026-11-23 03:45. Since then every run is cancelled by the next push, about every 20–30 s.
- `Runtime`: 41 succeeded, 28 failed and 126 were cancelled.
- **`main` has had no completed CI verdict for about 14 hours.**
- Fork PRs need a maintainer to approve CI. The coordination page says "most of these have no CI result yet". The `action_required` count hits the API's 2,500 cap.

**What a fix has to pass.** Formally nothing: there is no branch protection and no required checks. In practice, contributors are asked to run:
- `compileall`
- the standard-library unit tests
- `scripts/run_semantic_tests.py tests/semantic`, the translator suite. Per AGENTS.md it has 433 files and 5,821 tests, takes 224 s on 16 cores, and needs no LLVM, SPIR-V tools or GPU.
- the runtime `ctest`
- GPU `check.py` on real hardware, for translator rules

PR descriptions are expected to give the GPU and driver used.

**Could validators give a machine-checked verdict?**

| Work | Machine-checkable? | Why |
|---|---|---|
| Semantic suite and standard-library unit tests | Yes, partly | They are deterministic by design: LF-only writes and byte-identical output are enforced by a test. They need no network and no game files, and the semantic suite needs no LLVM. A two-run, no-network check fits |
| Translator rules | Not fully | They are confirmed on real GPUs. llvmpipe covers part of that. Wave64 behaviour differs by vendor and driver, and issues such as #6172, #6296 and #774 report GPU tests that are flaky from run to run |
| Asset and boot work | No | It needs the user's own Xbox package or the **retail executable**. Tests read `LEONIDA_GAME_DIR` and print `SKIP` without it. Validators could not and should not have these files |
| Coverage of what matters | Weak | Translator tests check against hand-written expectations, not the game. Whether the game boots, the stated goal, cannot be checked without game data |

## 6. Bottlenecks the data shows

1. **Checking, not producing.** About 3,600 PRs a day come in. 57% of merges have no review, and 88% of sampled merges had no green CI. Fork-PR CI waits for approval, and CI on `main` never finishes. Work is checked by a community "checked" convention: comments such as "Tested <commit> on <GPU>: pass".
2. **Coordination overhead and duplicate work.**
   - 16,889 claim comments across 48 threads.
   - "the same stop gets fixed three times" (#7154).
   - 786 PRs closed without merging, and hundreds needing a rebase.
   - 363 authors with nothing merged.
3. **Two maintainers.** All merges go through two accounts, and one of them appears to merge by script.
4. **Hardware- and game-gated checking.** The critical path (D3D12, boot) needs particular GPUs and a retail executable, which few people have legally.
5. **Merge latency is growing.** The median rose from 0.6 h to 8.5 h in two days, and the open queue holds about 3,300 PRs.
6. **Issue triage is weak**: one label, no assignees. But issues are not the unit of work here; coordination IDs are.

## 7. Fit with proof-of-fix

A reminder of how proof-of-fix works: bounties per issue, paid from a pool once independent validators pass a fix and it is final. Solvers submit fixes, and the merge happens only at finality. Validators run the tests twice in a no-network sandbox, and an LLM judges whether the fix solves the issue.

**Where it could help:**
- **Checking CPU-only work.** About 1,300 open "code read (CPU)" PRs and the agent-filed bugs (for example the 56 `spirv_asm`, `hashdict` and `saves.py` traceback findings) could get deterministic two-run verdicts. That would replace "CI not run, awaiting approval" and unreviewed merges with an independent verdict.
- **Duplicate and competing fixes.** One final verdict per work item, where the first fix to pass wins, could replace part of the claim threads and the "which of two PRs to keep" discussion.
- **A merge gate.** "Merge only at finality" is exactly what is missing: today PRs are merged with red or no CI.

**Where it cannot help:**
- **Paying solvers.** Paying people to submit fixes is the wrong lever. Solver supply is effectively unlimited: 830 authors in 3 days, mostly AI agents. Bounties would mostly draw more agent spam.
- **GPU- and game-gated work.** Most of the critical path (D3D12 → Vulkan on real drivers, booting the retail executable) is out of reach for validators.
- **Flaky GPU tests.** They would fail the "run twice, same result" rule.
- **Missing direction.** The judge cannot say whether a change gets the game closer to booting. The issues are not written as testable bug reports with a clear success condition, except the tool-crash findings.

**What the maintainers would need to provide:**
- A defined CPU-only set of work items with tests.
- A rule that merges wait for finality, which means slowing the merge script.
- The pool and the judges' fee.
- Acceptance that validators run code that changes every few seconds.

The last point matters for us: proof-of-fix validators would execute untrusted, agent-written code from a repository whose content changes several times a minute. That is sandboxing the network-free validators already need, but at much higher volume.

## 8. Risks

**Legal exposure.**
- Leonida is a recompilation and port of a commercial game from a publisher with a record of enforcement.
- **re3/reVC precedent.** In February 2021 Take-Two sent a DMCA takedown for re3/reVC, reverse-engineered GTA III and Vice City. The developers counter-noticed and the repositories were restored. In September 2021 Take-Two sued the developers in the N.D. of California for copyright infringement. **I did not confirm the case's outcome during this research; check before citing.**
- Leonida has a stronger position than re3 in one respect: it ships no decompiled game code. It loads the user's own executable and reads the user's own assets.
- It still has three weak points:
  1. It targets a game **within days of release**, at full price, with no PC version on sale yet. Market harm, a key fair-use factor, is much more arguable than for a 20-year-old game.
  2. Xbox Series packages are encrypted, so files "already readable on disk" means a decrypted dump. Leonida avoids the decryption step itself, but its users cannot get there without circumvention (DMCA §1201) or a leak. Issues openly discuss a leaked executable, and the boot work (`docs/retail_boot_chain.md`, #6824, #7154) relies on a retail executable.
  3. It uses Rockstar's trademark, and its logo is a GTA VI fan icon.
- There is also a GPL licence-hygiene issue: the submodule it depends on has no licence.

**Malware lure.** The repository itself shows no lure pattern. The surroundings and the process are the risk:
- leaked-exe links in issues
- unreviewed merges, at a pace no human can audit
- installer and launcher PRs
- AV-exclusion advice

If anyone ever slips a malicious change into `make_game.py` or a shim, funders of the "verified" fix would share the blame.

**Longevity.** A takedown is likely at any time. Re3 was removed within months, and this project is aimed at a front-line release. The repository is also only 3 days old, and its activity depends on hype and free AI tokens. Users have already asked for mirrors (#1079, #7119, #935).

**Reputation for proof-of-fix.**
- We would be paying bounties on a GTA VI port whose progress depends on a leaked executable. That reads as funding piracy.
- A takedown would wipe out pool funds and the pilot record.
- The flood of agent PRs would make the pilot's numbers look noisy.
- Our paper's claim about self-healing through market forces would be judged on an atypical, legally clouded case.

## 9. Recommendation

**Do not fund or pilot on Leonida.** It shows that the bottleneck in AI-heavy open source is checking the work, which is an argument we can cite. But:
- the useful slice (CPU-only checks) is small
- solvers do not need paying
- the critical path cannot be checked by our validators
- the legal and malware risks fall on us

At most, cite it in the paper as a case study using the public numbers above, with no interaction with the project.

**A better first pilot** for the "if we provide value here we can do it for others" goal: projects with clear licences, deterministic tests that need no network or special hardware, and a visible backlog. Numbers are from the GitHub API on 2026-11-23, and these are first picks, not a full survey:

| Project | Licence | Open bug issues | Open PRs | Merged PRs since 2026-10-23 | Why it fits |
|---|---|---|---|---|---|
| **python/mypy** | MIT (GitHub shows NOASSERTION because of multiple licence files) | 1,673 | 550 | 98 | Bugs are usually small code snippets that become test-data cases. The tests are deterministic and need no network. A large backlog against slow merging is the gap proof-of-fix targets |
| **jqlang/jq** | MIT-style (shows NOASSERTION) | 34 | 139 | 12 | A clear review bottleneck. Deterministic C tests (`jq.test` cases) and small, well-defined bugs |
| **sqlfluff/sqlfluff** | MIT | 67 | 49 | 289 | Active and well-run, so a good control or calibration pilot. Bug reports come with SQL snippets that are natural fixtures. Pure Python with deterministic tests |

These need a quick follow-up before choosing: maintainer receptiveness, how flaky CI is, and whether outside bounties are welcome (some projects reject them).

---

# v1.1: valid data on whether verification would have helped

Data: GraphQL for every merged PR (3,627), with files, head and base SHAs and the check runs on each head commit including their completion times. GraphQL for every PR not merged (4,422), with files, `mergeable` and the last 3 comments. All 752 push runs on `main` of the `CI` and `Runtime` workflows. Every PR run of `CI` that failed or succeeded (4,357). Job records for 250 randomly sampled failed PR runs and for all 67 failed runs on `main`. 16 + 16 job logs, read as text only to pull out failing test names. The raw data (49 MB) is kept outside the repository by the owner (available on request); the analysis scripts and the derived numbers are in [`data/leonida-v1/`](../data/leonida-v1/).

## 10. Evidence of harm from unverified merges (A)

### 10.1 Merged PRs that later needed a fix (A1)

**Method** (`a1a2.py`, `a1_defect.py`; data in `a1_links.json` and `a1_defect_set.json`).

A merged PR X counts as *referenced by a follow-up* when a later PR Y meets all of these:
- Y was opened **after** X merged. Y can be merged, open or closed.
- Y's title or body cites `#X` or `/pull/X`.
- One of these words appears within 60 characters of that reference: revert, regress, broke(n), break(s), restore, introduced, caused, fix(es/ed), follow-up, since, after, undo, rollback.

That gives three tiers:

| Tier | Merged PRs | Share (95% Wilson CI) |
|---|---|---|
| **T1-any**: the rule above | 363 / 3,627 | 10.0% (9.1–11.0) |
| **T1-strong**: only revert, regress, broke, restore, introduced or caused | 28 / 3,627 | 0.8% (0.5–1.1) |
| **T2**: a fix-titled PR merged within 24 h touches the same non-doc file | 1,378 / 3,627 | 38.0% (36.4–39.6) |

**T2 is mostly noise.** The same few files change constantly: `tools/rdna2spirv.py` is touched by 797 PRs, with up to 307 open at the same time. Treat T2 as an upper bound that carries no information, not as a measurement.

**Validation by hand** (a random 45 of the 363 T1-any links, seed 11; labels are in `a1_defect.py`):

| Label | Count | Examples |
|---|---|---|
| A real defect in X | 13 | regressions: #4060→#6010, #2100→#3926; a column dropped: #6318→#6744; a self-revert: #1388→#1466; merged before the reviewers' notes were applied: #3978/#4427→#5686; incomplete fixes |
| Borderline | 4 | |
| A benign follow-up or extension | 18 | |
| Only mentions X (rebase notes, an unrelated `#4549`) | 10 | |

- So the share of T1-any links that are real defects is **13/45 = 29% (95% CI 18–43%)**.
- That puts the **estimated number of defective merges found this way at ~105 (64–157), or 2.9% (1.8–4.3%) of merged PRs.** This is a **lower bound**: fixes that don't cite X by number are missed.
- A stricter defect classifier on the same line (`a1_defect.py`) scored precision 0.89 and recall 0.62 against the 45 labels. It flags **39 merged PRs (1.1%, CI 0.8–1.5%)**.

**Time from the merge of X to the first follow-up PR opened:** T1-any median **0.9 h**, p90 10.6 h; T1-strong median 0.6 h, p90 3.8 h. 227 of the 363 follow-ups were themselves merged.

**Reading:** defects in merged PRs exist but are a small share, and they are fixed fast. The swarm repairs itself within hours.

### 10.2 CI at merge time against later fixes (A2)

**CI at merge** uses only the head commit's core check runs that **completed before `mergedAt`**: `check`, `translator-tests`, `semantic-tests`, `windows`, `wine`, `linux-gpu-tools`, `macos-python`, `viewer-tests`, `no-game-data` and `stdlib-tests-linux`.
- **red** means any of them failed.
- **green** means at least one passed and none failed.
- **none** means none had completed.

Of all merged PRs: **green 896 (24.7%), red 505 (13.9%), none 2,226 (61.4%)**.

| Outcome (later fix) | Green | Red | None | Not-green minus green |
|---|---|---|---|---|
| T1-defect (precision 0.89) | 6/896 = **0.7%** (0.3–1.5) | 9/505 = **1.8%** (0.9–3.4) | 24/2,226 = **1.1%** (0.7–1.6) | +0.5 pp (95% CI −0.1 to +1.2); red minus green +1.1 pp (−0.2 to +2.4) |
| T1-any | 89/896 = 9.9% (8.1–12.1) | 67/505 = 13.3% (10.6–16.5) | 207/2,226 = 9.3% (8.2–10.6) | +0.1 pp (−2.2 to +2.4) |
| T2 (noisy) | 45.5% | 56.0% | 30.9% | −10.0 pp (driven by which files change, not by CI) |

The 2×2 for T1-defect, with not-green = red + none:

| | Later fixed | Not later fixed | Total |
|---|---|---|---|
| Green CI at merge | 6 | 890 | 896 |
| Not green (red or none) | 33 | 2,698 | 2,731 |

**Reading:** CI status at merge **barely predicts** which merges later needed a fix. The difference is about 1 point and not significant at 95%. Splitting by PR size (`a1a2.py` output) does not change this.

The reason is in sections 10.3 and 11: **most red PR checks were inherited from a broken `main`, not caused by the PR.** A plain "CI must be green" gate would mostly have blocked innocent PRs. A useful verdict has to compare **base against head**.

### 10.3 Health of `main` over time (A3)

Data is in `main_runs.jsonl` and `a3_main_health.txt`.

**Push runs on `main`:**

| Workflow | Runs | Success | Failure | Cancelled | Queued or running |
|---|---|---|---|---|---|
| `CI` | 546 | 66 | 38 | 430 | 12 |
| `Runtime` | 206 | 41 | 29 | 126 | 10 |

**Per hour (`CI`):**
- Mostly green until about 2026-11-22 10:00 UTC.
- Then mostly red: every completed run after 2026-11-22 13:24 UTC failed.
- From 14:00 UTC on 11-23, 68–157 runs an hour were **cancelled** by the next push, and none completed.
- Some runs queued at 04:00–06:00 UTC were still queued about 12 h later, which means runner capacity is saturated.

**Longest stretch without a green run on `main`:**
- `CI`: **29.1 h and still going**, from 2026-11-22 13:24 UTC.
- `Runtime`: 22.1 h and still going. Its earlier gap was 20.6 h at the start of the project.

**Merges that landed while the latest completed `CI` run on `main` was red: 2,733 of 3,627 (75.4%).** For `Runtime`: 2,035 red, 1,567 green, 18 before any run.

**What broke `main`** (all 67 failed runs):
- `CI`: the Windows standard-library unit tests in the `check` job (34/38 runs).
- `Runtime`: the Windows CPU runtime tests (23/29), plus `linux-gpu-tools`: its build failed 12 times and the llvmpipe GPU tests 10 times.

From 16 sampled logs:
- **Python standard-library tests:** `test_every_family_runs_clean`, `test_unique_pool_keeps_its_existing_output_folder`, `test_each_page_names_each_topic_once_per_table`, `test_macos_case_sensitive_volume_keeps_case` (4 consecutive runs across about 3 h) and `CheckNoGameData`.
- **`ctest` CPU tests:** `d3d12_predicated_copy`, `d3d12_draw`/`d3d12_compute`, `d3d12_geometry` and `d3d12_sparse_queue_family` (twice in a row).
- **Other:** one `ModuleNotFoundError: numpy` (a CI configuration fault) and one `TypeError`.

These are real failures that **repeat across runs**, so they behave deterministically, not as flakes.

### 10.4 Duplicate and wasted work (A4)

Data is in `a4_dupes.txt`. Of the **838 PRs closed without merging**, here is why, going by the closing comments:

| Reason | PRs |
|---|---|
| **Duplicate, superseded or already done** | **539 (64%)** |
| No reason stated | 192 |
| Conflict or stale | 68 |
| Policy (game data, spam, out of scope) | 39 |

- A spot check of 20 found 19 correct. The one wrong case was #7139, the malware PR above.
- Of 525 duplicates found with the narrower pattern, 302 **had claimed the work or linked the coordination issue**. **Claiming does not prevent duplicates.**
- **Concurrent edits to the same file:** 6,086 of 7,293 PRs (83.4%) that touch non-doc files were open at the same time as another PR touching the same file. Peak concurrency: `runtime/CMakeLists.txt` 395 open PRs at once, `tools/rdna2spirv.py` 307, `scripts/run_gpu_tests.py` 269, `runtime/shims/d3d12_vulkan_device.cpp` 200.
- **Conflicts now:** 646 open PRs are `CONFLICTING`, 1,949 are `MERGEABLE` and 989 are `UNKNOWN`.
- **Wasted effort:** about 539 duplicate PRs plus 646 conflicting ones, about 15% of all 8,049 PRs (estimate).

### 10.5 Review hours against verification hours (A5, estimates)

**Assumptions:**
- Careful review covers 200–400 changed lines an hour, the figure usually quoted from the SmartBear/Cisco study.
- Each PR adds 10 minutes of overhead.

**Merged volume:** 1,477,641 changed lines in 3,627 PRs over about 70 h.

**Review hours needed:** **about 4,300–8,000 reviewer-hours** (estimate). That is about **60–115 full-time reviewers** working continuously for those 70 h.

**Review actually done:** about 2,070 review records on merged PRs and 2 mergers. At an assumed 15 minutes per review, that is about 500 h. So **about 6–12% of the needed review was done** (estimate).

**Machine verification per PR (estimates):**
- The CPU suites take about 7–8 min per run on a CI runner: `check` median 3.2 min, `semantic-tests` 3.1, `translator-tests` 1.2.
- Two runs at the head and two at the base comes to **about 30 runner-minutes per PR**, about 15 min if base results are cached.
- For all merged PRs: **about 900–1,800 machine-hours**, which runs in parallel and needs no people.
- An LLM judge costs about $0.1–0.3 per PR (section 13), or **about $400–1,100 for all merged PRs** (estimate).

**Reading:** the human review gap is huge, and machine verification is cheap by comparison. But section 10.2 shows that the CI already in place didn't separate good merges from bad. Whether a base-against-head verdict plus a judge does better is exactly what the replay in section 13 would test.

## 11. Why PR CI fails (C)

**Conclusions of PR-event runs** (full counts, built from 1-hour windows to get past the API's 2,500 cap; `pr_run_counts.json`):

| Workflow | Success | Failure | Cancelled (newer push) | Fork awaiting approval |
|---|---|---|---|---|
| `CI` | 1,359 | 2,982 | 3,554 | 2,329 |
| `Runtime` | 1,324 | 2,558 | 2,293 | 1,359 |

There were no `timed_out` or `startup_failure` runs. **Only about 13% of `CI` PR runs succeeded.**

**Why they failed** (a random sample of 250 failed `CI` PR runs, seed 2026; `c_fail_sample_jobs.jsonl`, `c_failures.txt`):

| Cause | Runs (of 250) |
|---|---|
| **No job record at all**: the run is marked failed but `/jobs` (all attempts) returns 0 jobs and the check suite has 0 check runs. The cause is not visible through the API; most likely the runner, queue or capacity side | **121 (48%)** |
| Unit tests: the **Windows standard-library tests** (`check` job, step "Tests (standard library only, no game data)") | **119 (48%)** |
| Build: `rpf9dump` .NET build (7), runtime build (1) | 8 (3%) |
| Unit tests: translator **semantic suite** (Linux) | 5 (2%) |
| Unit tests: translator pytest suite | 1 |
| Lint or format | 0 (lint runs only in `jactionlint`, for workflow files) |

Six runs failed in more than one category.

**Inherited or caused by the PR?** I took a random 16 failed `check` jobs from the sample and read their logs as text (`c_pr_log_sample.txt`). 14 named a failing test. **13 of the 14 were tests that also failed on `main` in the same window**: `test_every_family_runs_clean`, `test_each_page_names_each_topic_once_per_table`, `test_macos_case_sensitive_volume_keeps_case` and `test_unsupported_instructions_and_operands_raise_cpu_ref_unsupported`. So most red PR checks were **inherited from a red base**.

**Deterministic or flaky:**
- In the PR runs I could not observe any flakes. Only 10 SHAs ran more than once, and **none had a failure and a success**. Only 2 re-attempts exist.
- The failures on `main` repeat over consecutive runs, so they are deterministic.
- Flakes are reported in the **GPU** tests: #6172 (`ms_wave_info_s3`, pass rate from 100% to 2.5% on RADV), #6296 and #774. Those are outside validator scope.

**What a proof-of-fix verdict would catch** (two runs at head and two at base in a sandbox, plus an LLM judge of how well the fix fits the issue):

| Failure type | Caught? | Why |
|---|---|---|
| A regression in the standard-library or semantic suites caused by the PR | **Yes**, *if* the validator runs the same OS | The share of `main`'s breaks that are Windows-only is **unknown**. Most breaks on `main` were in the Windows `check` job, and the Linux standard-library job is new |
| Inherited failures (the base is already red) | **Correctly ignored** | Running base and head is exactly the fix for what makes today's CI useless as a gate |
| Infrastructure failures with no job record (48% of the sample) | Avoided | Validators bring their own compute; this is the real **capacity** gain |
| Fork-approval waits (2,329 runs) | Avoided | Validators run in a sandbox with no network, so no maintainer has to approve fork CI |
| Malicious diffs such as #7139 | **Tests: no. Judge: likely** | A judge that reads the diff and checks it against a registered issue is the only layer that sees it |
| Windows CPU runtime tests (`ctest`, MSVC) | Only with Windows validators | Not in a Linux Docker sandbox. Wine or `clang-cl` + `xwin` are partial routes |
| GPU-path correctness, wave64 on real drivers, llvmpipe-only checks | **No** | Hardware-specific and flaky |
| Retail-executable boot work (`docs/retail_boot_chain.md`, #7154) | **No** | Needs the game; validators must never have it |

## 12. Spec-driven development: an assessment (D)

**What Leonida has:**

| Item | Status |
|---|---|
| Design docs | **Yes, measurement-heavy.** 86 files under `docs/`, `docs/design.md` (556 KB) and an index in `docs/README.md` |
| Translator contract table | In `docs/design.md`. Each rule says how it was confirmed (GPU test, Mesa/LLVM reference or corpus count). It is enforced by tests (`tests/test_design_contract_rows.py`, `tests/test_docs_design_rows.py`). This is the closest thing to a spec, but only for the translator |
| `specs/` folder, RFCs, ADRs, OpenSpec | **None** |
| Milestones | 0 |
| Projects | Not available to our token |
| Roadmap | **None.** The nearest are the README's "Want to help?" list and #313, the D3D12 critical-path page |
| Issue templates | **Bug report only.** It asks for what happens, the commit, the system, the stage, the command and the output. **No acceptance criteria and no "expected behaviour"** field. Blank issues are allowed |
| PR template | Yes. It asks for the claim ID, `Depends on`, what and why, what was tested (GPU, driver, translator counts before and after), and the AI disclosure, plus a checklist (no game data; contract row for new translator rules). It does not ask for acceptance criteria or an issue link |
| What CONTRIBUTING and AGENTS.md tell agents | Claim work in the coordination issue first; post `finding:` for work you won't do; put the item ID in the PR; "Before you guess, look"; count over the whole corpus; "Fix, don't disable"; test without the game first; disclose AI use. Items in the coordination list are one-liners with "Why it matters", "Needs" and "Size", **not acceptance criteria** |

**Measured over all 3,627 merged PRs** (`d_spec.txt`; regex-based):

| What the PR does | PRs | Share |
|---|---|---|
| Links the coordination issue or says "coordination" | 2,730 | 75.3% |
| Carries a claim ID such as `TEST-57` | 1,157 | 31.9% (partial regex) |
| Links a real, non-coordination issue | 174 | 4.8% |
| Uses a closing keyword ("Fixes #N") on one | 55 | 1.5% |
| Mentions `design.md` | 1,382 | 38.1% |
| Has a "Tested" section or test commands | 2,983 | 82.2% |
| Changes test files | 3,104 | 85.6% |
| States acceptance criteria or expected results | 23 | **0.6%** |

**Does the lack of specs drive the rework and duplicates? The data does not show it.**

- **Rework.** PRs that link a real issue had *more* referenced follow-ups, not fewer: T1-any 17.2% against 9.6%; T1-defect 2.3% (4/174) against 1.0%. PRs with a claim ID: 12.7% against 8.7% (T1-any), 1.1% against 1.1% (T1-defect). The likely reason is that issue-linked work sits in active bug areas that attract follow-ups. Either way, **there is no evidence here that linking a spec or issue reduces rework.** The data cannot test what acceptance criteria would do, because almost no PR states any (0.6%).
- **Duplicates.** These come from **concurrency**: 83% of PRs overlap another open PR on the same file, and hundreds of PRs are open on the hottest files. Claims don't stop it: 302 of 525 duplicates had claimed or linked the coordination issue. A spec alone would not prevent two agents building the same thing. What would prevent it is **one owner per registered item, enforced at merge**, which is roughly proof-of-fix's "first fix to reach finality wins, and later ones are not paid".
- **What specs would plausibly fix**, without proof here: the "merged before the reviewers' notes were applied" and "incomplete fix" defects in the hand-labelled sample (5 of 13). Both are the kind of thing explicit acceptance criteria catch.

**How proof-of-fix could add a spec gate:**
1. **Issue registration check.** A bounty exists only for an issue that passes a check: "a genuine, in-scope bug report or spec, with a reproduction or acceptance criteria that tests can check, needing no game files or GPU." The coordination list's `finding:` lines would have to become real issues.
2. **Bounties only on registered issues.** PRs without one (like #7139's "worker thread") get no verdict and no merge through the proof-of-fix path.
3. **Fixes judged against the issue's stated criteria.** That means base and head runs, two each, plus the judge reading the diff against the criteria.
4. **First fix to reach finality wins.** Later duplicates aren't paid. That should take some pressure off the claim threads.

**What Leonida would need to adopt:**
- An issue form with "Expected behaviour / acceptance criteria" and "How to test without game files".
- A rule that a PR links exactly one registered issue.
- A requirement that a bug fix includes a test that fails at the base and passes at the head.
- A Linux CPU job (or Windows validators) as the reference environment.
- A merge gate on finality, which means **slowing the merge script**.

**OpenSpec fits in a limited way.** It fits the translator contract and the D3D12 method surface. Leonida already writes rules into `docs/design.md`'s contract table with a method of confirmation, and an OpenSpec change (proposal, spec delta, tasks) per D3D12 method or translator rule family would make those reviewable before code. It does not fit the measurement and "first light" work, where the spec is unknown until someone measures the game.

## 13. Pre-registration draft: a retrospective replay (B, design only, not run)

**Question.** Would proof-of-fix verdicts on merged, CPU-testable Leonida PRs have flagged the ones that later needed a fix better than the actual process did?

The actual process merged all of them. CI-at-merge is the simpler gate to compare against.

**Suites to run.** All need no GPU, no network and no game files.

| Suite | Path | Command | Runtime | Dependencies |
|---|---|---|---|---|
| Translator semantic suite | `tests/semantic/` (447 test files in the tree; AGENTS.md says 433 files, 5,821 tests) | `python -I scripts/run_semantic_tests.py tests/semantic` | 26 s on 16 cores per the README; 224–253 s serially; CI median 3.1 min | Standard library only. SPIRV-Tools (`spirv-as`, `spirv-val`) is required when `LEONIDA_REQUIRE_SPIRV_TOOLS=1`; without it some tests skip |
| Standard-library unit tests | `tests/test_*.py` (474 files; run those with a `__main__` block and no `import pytest` or `HAVE_NUMPY`) | `python -I tests/test_X.py` each, as in `ci.yml` | CI `check` median 3.2 min on Windows | Python 3.12. Exclude the tests that need the `rpf9dump` .NET build (`test_rpf9dump_exit_codes`, `test_ttpf_export_resume`) |
| pytest files (optional) | `tests/test_*.py` with `import pytest` | `python -m pytest <files> -q` | CI median 1.2 min | Pinned `pytest==9.2.0`, `numpy==2.5.5`, `Pillow==13.0.0`, plus `llvm-mc` from LLVM 21 for some tests |

Install every dependency when the image is built, so runs need no network.

**Sample.** Data is in `b_replay_sample.json` (full SHAs) and `b_sample.txt`.
- **Eligible PRs:** merged PRs whose changed files all match `tools/*.py`, `tests/**`, `scripts/*.py` (excluding `run_gpu*`), `make_game.py` or `*.md`, with at least one non-doc file and 30 files or fewer. That gives 2,154 of 3,627 merged PRs.
- **Positives (later fixed):** eligible PRs in T1-defect or hand-labelled as defects. Only **22** are available; 20 were drawn (seed 319).
- **Negatives:** eligible PRs with no T1 link and no T2 overlap (1,329 available); 20 drawn (seed 319).
- **Labels must be re-checked blind before any run.** A person who has not seen any verdict reads each positive's follow-up and each negative's later history and confirms the label. Disputed PRs are dropped and replaced from the same stratum.

| PR | Outcome | Head | Base | Lines +/- | Files | CI at merge |
|---|---|---|---|---|---|---|
| #117 | later fixed | `f1dd3c61c53f` | `d51bddc84e38` | +884/−0 | 3 | red |
| #442 | later fixed | `d9e629288a44` | `4abd54571b6e` | +774/−2 | 5 | none |
| #544 | later fixed | `7a86a2e81432` | `91b36cf86cb9` | +175/−2 | 4 | red |
| #999 | later fixed | `1b77955bf750` | `48ad23f02624` | +21/−0 | 2 | red |
| #1320 | later fixed | `944961c58617` | `c0ac5fd6518b` | +120/−1 | 2 | none |
| #1678 | later fixed | `d426f7859616` | `a0acd33d77ba` | +26/−1 | 4 | red |
| #1686 | later fixed | `00af470cf5ac` | `89b047cd8fab` | +617/−57 | 5 | red |
| #1900 | later fixed | `9a967e1901a5` | `6a6704df1592` | +356/−9 | 5 | green |
| #2029 | later fixed | `d8a66eebafab` | `4eb6155d3ac4` | +32/−8 | 3 | none |
| #2066 | later fixed | `05d1e0e9204b` | `4eb6155d3ac4` | +47/−4 | 2 | green |
| #2229 | later fixed | `6d4cc4cd0ae8` | `49475796c226` | +112/−28 | 3 | green |
| #2505 | later fixed | `36d1528c894b` | `49475796c226` | +65/−8 | 2 | none |
| #3278 | later fixed | `9ff3024c9269` | `162821017ea3` | +70/−3 | 4 | none |
| #3487 | later fixed | `0bfe15bfdf32` | `f847748cc76b` | +312/−32 | 5 | none |
| #4427 | later fixed | `9d7a002d1c45` | `03b09a086592` | +30/−1 | 2 | none |
| #4514 | later fixed | `4e3517479b2c` | `03b09a086592` | +1/−1 | 1 | none |
| #6318 | later fixed | `76b8990f7f63` | `561b65a83221` | +156/−21 | 2 | none |
| #6819 | later fixed | `33dfe8703d37` | `1cc6e3c12196` | +117/−0 | 3 | none |
| #6917 | later fixed | `a6511598e5db` | `1cc6e3c12196` | +58/−0 | 2 | none |
| #6925 | later fixed | `d6d43a9ec5d5` | `1cc6e3c12196` | +54/−0 | 2 | none |
| #45 | no later fix | `fb18e1f0ff9e` | `793b06f12765` | +434/−0 | 1 | none |
| #574 | no later fix | `906dd402c392` | `ee97b843bedb` | +40/−4 | 2 | red |
| #636 | no later fix | `898532131d0f` | `c432cdce127e` | +1/−0 | 1 | none |
| #1618 | no later fix | `779164fc5fe4` | `41f448261e1d` | +4/−2 | 1 | green |
| #2185 | no later fix | `726eb30f3aeb` | `4eb6155d3ac4` | +345/−0 | 1 | none |
| #2201 | no later fix | `843930fdc887` | `ec8ec4c9a46c` | +84/−12 | 2 | none |
| #2568 | no later fix | `9806744bd239` | `49475796c226` | +25/−1 | 2 | none |
| #2930 | no later fix | `3e105eba3a1c` | `f847748cc76b` | +34/−0 | 4 | red |
| #3046 | no later fix | `111200df4085` | `162821017ea3` | +23/−3 | 2 | none |
| #3160 | no later fix | `564115c7941d` | `f847748cc76b` | +52/−1 | 2 | none |
| #3297 | no later fix | `beb2970224bd` | `f847748cc76b` | +11/−1 | 2 | none |
| #3354 | no later fix | `3c7b0403c31c` | `03b09a086592` | +70/−1 | 2 | red |
| #3943 | no later fix | `e47c9bb69a68` | `aa2988cc555b` | +32/−0 | 2 | green |
| #4015 | no later fix | `5286ad1a0ad9` | `aa2988cc555b` | +30/−4 | 4 | green |
| #4047 | no later fix | `9f9681f1b776` | `aa2988cc555b` | +18/−1 | 1 | green |
| #4187 | no later fix | `c46e714826a5` | `aa2988cc555b` | +2571/−0 | 3 | green |
| #4377 | no later fix | `e09ba000743a` | `03b09a086592` | +128/−2 | 2 | red |
| #4395 | no later fix | `40e540733ed7` | `03b09a086592` | +28/−2 | 2 | none |
| #5535 | no later fix | `389330e7b0bd` | `561b65a83221` | +17/−0 | 17 | none |
| #6734 | no later fix | `44c3b192ecac` | `1cc6e3c12196` | +52/−2 | 2 | none |

The base listed is GraphQL's `baseRefOid`. The replay uses `git merge-base <head> <main at merge time>` as the base it runs, and records both.

**Procedure:**
1. On an isolated machine that holds no credentials, `git clone --no-checkout` into a fresh directory. Fetch `refs/pull/N/head` for the 40 PRs. **Never run anything from the repo outside the container.**
2. Build one Docker image with the dependencies above, pinned by digest, **before** mounting the repo. Then run with `--network none --read-only` (plus a tmpfs work directory), `--cpus 8 --memory 8g --pids-limit 512`, a 20-minute timeout, as an unprivileged user with no host mounts except a read-only copy of the checkout. Destroy the container after each run.
3. For each PR, run the suites **twice at the base and twice at the head**, recording each test's pass, fail or skip.
   - A test that differs between the two runs at the same SHA is marked **flaky** and left out of the verdict.
   - "Tests pass" means no test that is stable at the base fails at the head, and every test the PR adds passes twice at the head.
4. **Judge:** Opus 5.5 with proof-of-fix's validator prompt and pass/fail rule, unchanged. Its input is the issue or claim text (from the coordination comment the PR cites, or the PR title if none), the diff, and the test summary. **The judge never sees the outcome label, later PRs or comments.**
5. The verdict is pass or fail by the rule; record the reason.

**Prediction (pre-registered):**
- Proof-of-fix "fail" verdicts will pick out the later-fixed PRs better than (a) the actual merge decision and (b) CI-at-merge = red.
- **Metrics:** recall (later-fixed PRs that got a "fail") and precision (share of "fail" verdicts that were later fixed), each with a Wilson 95% CI. The difference from the CI-red baseline is tested with McNemar's test on the paired PRs.
- The baselines in this sample: the actual merge decision has recall 0/20. CI-at-merge = red has recall **5/20 (25%)** and precision **5/9 (56%)**.
- **Success:** recall of at least 50% with precision of at least 60%, and McNemar's p < 0.05 against CI-red.
- **Failure, which would show verification doesn't help here:** recall of 25% or less, or precision under 50%.
- **Power:** with 20 + 20, only large effects (about 35–40 points) can be detected. The CIs will be about ±20 points. If the result is promising, extend to every eligible positive plus 3× as many negatives, using the same protocol. Only about 22 eligible positives exist in total, which itself shows how rare caught defects are.

**Costs (estimates):**
- **Compute:** about 4 suite runs × about 5–8 min per PR, so about 40 × 30 min ≈ **20 machine-hours on a local machine (free)**. Less with caching across shared bases: 27 of the 40 PRs share 8 bases (21 distinct bases in all).
- **Tokens per PR:**
  - The diff is about 12 tokens a line. The sample's median is 54 lines (about 650 tokens), its p90 674 lines (about 8k tokens), and #4187 has 2,571 lines (about 31k tokens).
  - Add the validator prompt (about 2k), the issue or claim text (about 1–2k), the test summary (about 2–3k) and file context (about 3–5k).
  - That is **about 10–15k tokens in** (up to about 45k for the largest), and **about 2–4k out** with reasoning.
- **Model cost:**
  - One judge pass: 40 × 15k = 600k in → $2.40; 40 × 4k = 160k out → $3.20. **About $6.**
  - A 3-judge panel: **about $18.**
  - With a 3× allowance for retries and larger diffs: **under $60 in total.**

**Risks:**
- **Malicious code in tests or tools.** It is real (#7139). Mitigations: `--network none`, a throwaway container, no credentials or host mounts, and none of the 40 PRs touches `runtime/`. The suites only run Python. Still treat the host as exposed if the container could be escaped.
- **Flakiness.** Two runs per SHA, flaky tests left out and reported.
- **Platform.** Most of `main`'s breaks were in the **Windows** `check` job. A Linux container may miss Windows-only behaviour (paths, case, line endings). Report this as a known limitation; a second leg on Windows or Wine would be needed for those.
- **Label noise.** The positives come from a classifier with precision about 0.89, hence the blind re-check.
- **Leakage.** The judge must not see post-merge text.
- **Legal.** Cloning a public GPL-3.0 repository to read and run its tests is ordinary use. The repository holds no game data (its CI blocks it). The replay never touches game files or the leaked executable, and nothing is published from the clone.

## 14. Updated verdict (v1.1)

**What verification would have changed:**
- **`main` would have stayed green far more often.** 75% of merges landed on a red `main`, and the current dry spell is 29 h. Real, deterministic breaks in CPU tests went in. A base-against-head check run before merging, on matching platforms, would have caught PR-caused breaks and ignored inherited ones. This is the clearest benefit.
- **More verification capacity, with no approval wait.** 48% of sampled failed PR runs failed with no job record, 2,329 `CI` runs waited for fork approval, 3,554 were cancelled, and only about 13% of `CI` PR runs succeeded. External sandboxed validators address this directly.
- **A security layer, but only through the judge.** #7139 shows the threat is real. Tests alone would not have caught it.

**What it would not have changed much:**
- **Defective merges are rare and fixed quickly.** An estimated 2.9% (1.8–4.3%) of merges were later fixed with a reference to them, most within about 1 h. The project already heals itself quickly, so time saved there is small.
- **Existing CI status did not predict later fixes** (+0.5 pp, not significant). We do not yet know whether a base-against-head verdict plus a judge would. That is what the replay in section 13 tests, and **its result should decide this, not this report.**
- **Duplicates (539) come from concurrency, not from missing verification.** Finality would stop paying duplicates, but agents would still write them. Specs and acceptance criteria are almost absent (0.6%), but the data does not show that their absence causes rework.
- **GPU, Windows-runtime and retail-executable work is out of scope** for our validators.

**Recommendation stands from v1, with one change:** don't fund or pilot *on* Leonida (the legal, malware and reputational risks are unchanged). **But the 40-PR replay is cheap (under $60 plus local compute) and would give the owner the valid data asked for.** It reads only public GPL code, runs in a container with no network, never interacts with the project, and publishes nothing back. If the owner approves the clone and the run, they should first confirm the label re-check and the success thresholds in section 13.

## Sources

- Repository and metadata: https://github.com/ItsNotRexed/Leonida (API `repos/ItsNotRexed/Leonida`, GraphQL counts)
- README: https://github.com/ItsNotRexed/Leonida/blob/main/README.md
- CONTRIBUTING: https://github.com/ItsNotRexed/Leonida/blob/main/CONTRIBUTING.md
- AGENTS.md: https://github.com/ItsNotRexed/Leonida/blob/main/AGENTS.md
- PR template: https://github.com/ItsNotRexed/Leonida/blob/main/.github/pull_request_template.md
- Bug report form: https://github.com/ItsNotRexed/Leonida/blob/main/.github/ISSUE_TEMPLATE/bug_report.yml
- Workflows: https://github.com/ItsNotRexed/Leonida/tree/main/.github/workflows (ci.yml, runtime.yml, no-game-data.yml)
- Build.bat: https://github.com/ItsNotRexed/Leonida/blob/main/Build.bat
- Submodule: https://github.com/breadbbbb/rpf9-explorer
- Licence notes on related projects: https://github.com/ItsNotRexed/Leonida/blob/main/docs/related_projects.md
- Retail boot chain: https://github.com/ItsNotRexed/Leonida/blob/main/docs/retail_boot_chain.md
- Current coordination issue: https://github.com/ItsNotRexed/Leonida/issues/7913 (first: https://github.com/ItsNotRexed/Leonida/issues/156)
- D3D12 critical path: https://github.com/ItsNotRexed/Leonida/issues/313
- GPU results: https://github.com/ItsNotRexed/Leonida/issues/166
- Boot log for agents: https://github.com/ItsNotRexed/Leonida/issues/7154
- Leaked-exe threads: https://github.com/ItsNotRexed/Leonida/issues/6702, https://github.com/ItsNotRexed/Leonida/issues/6741, https://github.com/ItsNotRexed/Leonida/issues/6907
- "pls dont be a bitcoin miner": https://github.com/ItsNotRexed/Leonida/issues/6398
- Mirror requests: https://github.com/ItsNotRexed/Leonida/issues/1079, https://github.com/ItsNotRexed/Leonida/issues/7119
- Actions runs: https://github.com/ItsNotRexed/Leonida/actions
- Owner profile: https://github.com/ItsNotRexed
- Candidate pilots: https://github.com/python/mypy, https://github.com/jqlang/jq, https://github.com/sqlfluff/sqlfluff
- v1.1, malicious PR (clipboard hijacker, closed, not merged): https://github.com/ItsNotRexed/Leonida/pull/7139
- v1.1, example regression follow-ups: https://github.com/ItsNotRexed/Leonida/pull/6010, https://github.com/ItsNotRexed/Leonida/pull/6744, https://github.com/ItsNotRexed/Leonida/pull/1466, https://github.com/ItsNotRexed/Leonida/pull/5686
- v1.1, GPU flakiness reports: https://github.com/ItsNotRexed/Leonida/issues/6172, https://github.com/ItsNotRexed/Leonida/issues/6296, https://github.com/ItsNotRexed/Leonida/issues/774
- v1.1, Actions runs on `main` (CI workflow): https://github.com/ItsNotRexed/Leonida/actions/workflows/ci.yml?query=branch%3Amain
- v1.1, semantic suite README: https://github.com/ItsNotRexed/Leonida/blob/main/tests/semantic/README.md; pinned test deps: https://github.com/ItsNotRexed/Leonida/blob/main/tests/requirements.txt
- v1.1, review-rate assumption: the SmartBear/Cisco code review study (200–400 LOC/hour), as commonly cited
- re3 precedent (from public reporting, not fetched in this session; verify before publishing): the 2021 Take-Two DMCA takedown of re3/reVC, logged in GitHub's DMCA repository (https://github.com/github/dmca, 2021 notices), and *Take-Two Interactive v. Papenhoff et al.*, N.D. Cal., filed September 2021

## Notes on data limits

- v1.1: data was fetched 18:20–19:30 UTC; scripts are in `data/leonida-v1/scripts/` (`gql_pager.py`, `list_runs.py`, `fetch_jobs.py`, `a1a2.py`, `a1_defect.py`). The hand labels (45 links, 20 duplicate spot checks) are my own reading. Follow-up detection only finds fixes that cite the PR number, so the defect rate is a lower bound. Merged PRs' comments were not fetched, so other flagged PRs may exist among merged ones.

- The stargazer and watcher lists are not available to our token (404 even on `cli/cli`), so there is no analysis of the star pattern.
- The issue types come from a keyword classifier on titles (estimate).
- Reviews, CI-at-merge and AI disclosure come from a random sample of 100 merged PRs (seed 319).
- First-response times come from a random sample of 60 issues (seed 7).
- The status-count endpoints for Actions are capped at 2,500.
- All figures move quickly: about 150 PRs an hour arrive during the snapshot.
- Raw data (`prs.jsonl`, `issues.jsonl`, `sample_rev.jsonl`, `iss_sample.jsonl` and the v1.1 fetches) is kept outside the repository (49 MB); the scripts in `data/leonida-v1/scripts/` re-fetch it.
