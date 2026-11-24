"""Read-only: fetch jobs (all attempts) for run ids. Usage: fetch_jobs.py IDS_FILE OUT.jsonl"""
import json, subprocess, sys
ids = [l.split()[0] for l in open(sys.argv[1]) if l.strip()]
with open(sys.argv[2], "w") as f:
    for rid in ids:
        r = subprocess.run(["gh", "api", f"repos/ItsNotRexed/Leonida/actions/runs/{rid}/jobs?filter=all&per_page=100"], capture_output=True, text=True)
        d = json.loads(r.stdout or "{}")
        jobs = [{"id": j["id"], "name": j["name"], "status": j["status"], "conclusion": j["conclusion"], "run_attempt": j.get("run_attempt"),
                 "head_sha": j["head_sha"], "started_at": j["started_at"], "completed_at": j["completed_at"], "runner_name": j.get("runner_name"),
                 "steps": [{"name": s["name"], "conclusion": s["conclusion"]} for s in j.get("steps") or []]} for j in d.get("jobs", [])]
        f.write(json.dumps({"run": int(rid), "jobs": jobs}) + "\n")
