"""Read-only GraphQL pager for PR data. Usage: gql_pager.py STATES OUT.jsonl PAGESIZE"""
import json, subprocess, sys, time
states, out, size = sys.argv[1], sys.argv[2], int(sys.argv[3])
MERGED_FIELDS = """number title body createdAt mergedAt headRefOid baseRefOid baseRefName headRepository{nameWithOwner}
 additions deletions changedFiles author{login}
 files(first:30){nodes{path additions deletions}}
 commits(last:1){nodes{commit{oid statusCheckRollup{state contexts(first:25){nodes{... on CheckRun{name conclusion status startedAt completedAt checkSuite{workflowRun{databaseId workflow{name}}}}}}}}}}"""
OTHER_FIELDS = """number title body state createdAt closedAt mergeable additions deletions changedFiles author{login}
 headRefOid baseRefOid files(first:30){nodes{path}}
 comments(last:3){nodes{body createdAt author{login}}}"""
fields = MERGED_FIELDS if states == "MERGED" else OTHER_FIELDS
cursor = None; n = 0
with open(out, "w", encoding="utf-8") as f:
    while True:
        after = f', after:"{cursor}"' if cursor else ""
        q = ('{repository(owner:"ItsNotRexed",name:"Leonida"){pullRequests(first:%d%s, states:[%s], orderBy:{field:CREATED_AT,direction:ASC})'
             '{pageInfo{hasNextPage endCursor} nodes{%s}}} rateLimit{remaining cost}}') % (size, after, states, fields)
        for attempt in range(5):
            r = subprocess.run(["gh", "api", "graphql", "-f", "query=" + q], capture_output=True, text=True)
            if r.returncode == 0:
                d = json.loads(r.stdout)
                if d.get("data"): break
            time.sleep(5 * (attempt + 1))
        else:
            sys.exit("failed at cursor %s: %s" % (cursor, r.stderr[:300]))
        pr = d["data"]["repository"]["pullRequests"]
        for node in pr["nodes"]:
            f.write(json.dumps(node) + "\n"); n += 1
        rl = d["data"]["rateLimit"]
        print(n, rl, flush=True)
        if not pr["pageInfo"]["hasNextPage"]: break
        cursor = pr["pageInfo"]["endCursor"]
