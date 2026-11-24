# Leonida data, v1/v1.1 (proof-of-fix #319)

The analysis behind [`reports/leonida-fit-v1.md`](../../reports/leonida-fit-v1.md): read-only GitHub REST and GraphQL
fetches of ItsNotRexed/Leonida on 2026-11-23 (17:50–19:30 UTC). Nothing was cloned, downloaded or run.

- `scripts/`: the fetchers (`gql_pager.py`, `list_runs.py`, `fetch_jobs.py`, `fetch_prs.sh`) and the analyses
  (`a1a2.py`: merges later fixed and CI at merge, `a1_defect.py`: the hand-checked defect rate). They use `gh api` and
  write raw files to a working folder.
- `a1a2_derived.json`, `counts.json`: the derived numbers the report quotes.
- The raw fetches (49 MB of JSONL) are kept outside the repository; the scripts re-fetch them, and the counts move by
  about 150 PRs an hour, so a re-run is a new snapshot.
