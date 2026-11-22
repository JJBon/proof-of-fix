"""The test chain's hard stop (proof-of-fix#251 task 7.0; validator-kit/sevsnp/testchain/autostop.tf): stops every
running instance tagged TAG_KEY=TAG_VALUE (the SEV-SNP kit's: the test-chain host and the SEV-SNP host) that has run
MAX_HOURS since its last start (EC2's LaunchTime). One JSON line a run: what it checked and what it stopped."""

from __future__ import annotations

import datetime as dt
import json
import os


def overdue(instances: list, now: dt.datetime, max_hours: float) -> list:
    """The ids of the running instances in `instances` (EC2's Instances) whose LaunchTime is MAX_HOURS ago or more."""
    out = []
    for i in instances:
        if i.get("State", {}).get("Name") != "running":
            continue
        launched = i["LaunchTime"]
        if isinstance(launched, str):
            launched = dt.datetime.fromisoformat(launched.replace("Z", "+00:00"))
        if (now - launched).total_seconds() >= max_hours * 3600:
            out.append(i["InstanceId"])
    return out


def handler(event=None, context=None, ec2=None, now=None) -> dict:
    if ec2 is None:
        import boto3  # in the Lambda runtime

        ec2 = boto3.client("ec2")
    key, value = os.environ.get("TAG_KEY", "pof:kit"), os.environ.get("TAG_VALUE", "validator-kit/sevsnp")
    max_hours = float(os.environ.get("MAX_HOURS", "8"))
    now = now or dt.datetime.now(dt.timezone.utc)
    pages = ec2.describe_instances(Filters=[{"Name": f"tag:{key}", "Values": [value]},
                                            {"Name": "instance-state-name", "Values": ["running"]}])
    instances = [i for r in pages.get("Reservations", []) for i in r.get("Instances", [])]
    stop = overdue(instances, now, max_hours)
    if stop:
        ec2.stop_instances(InstanceIds=stop)
    out = {"checked": len(instances), "stopped": stop, "maxHours": max_hours}
    print(json.dumps(out))
    return out
