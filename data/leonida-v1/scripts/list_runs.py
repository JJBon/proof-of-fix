"""Read-only: list PR-event runs of one workflow with given conclusions, in 3h windows. Usage: list_runs.py WF_ID OUT status1,status2"""
import subprocess, json, sys
from datetime import datetime, timedelta
wf, out, statuses = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
t = datetime(2026, 11, 20, 18); end = datetime(2026, 11, 23, 21)
with open(out, "w") as f:
    while t < end:
        a, b = t, t + timedelta(hours=1); t = b
        for st in statuses:
            page = 1
            while True:
                q = (f"repos/ItsNotRexed/Leonida/actions/workflows/{wf}/runs?event=pull_request&status={st}&per_page=100&page={page}"
                     f"&created={a:%Y-%m-%dT%H:%M:%SZ}..{b:%Y-%m-%dT%H:%M:%SZ}")
                r = subprocess.run(["gh", "api", q], capture_output=True, text=True)
                d = json.loads(r.stdout or "{}")
                runs = d.get("workflow_runs", [])
                for x in runs:
                    f.write(json.dumps({k: x.get(k) for k in ("id", "name", "head_sha", "head_branch", "status", "conclusion", "created_at",
                        "run_started_at", "updated_at", "run_attempt")} | {"prs": [p["number"] for p in x.get("pull_requests") or []],
                        "head_repo": (x.get("head_repository") or {}).get("full_name")}) + "\n")
                if len(runs) < 100: break
                page += 1
print("done")
