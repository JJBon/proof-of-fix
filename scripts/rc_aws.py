#!/usr/bin/env python3
"""The release candidate's real-SEV-SNP items on a temporary AWS test chain (proof-of-fix#251 task 7.0; design L18 items
3, 4 and 6, L21; the owner's decision of 2026-11-21). Run it through scripts/rc-aws.sh.

    scripts/rc-aws.sh plan [--hours H] [--sevsnp-hours H] [--model-run]
        the machines, the hours and the estimated cost at today's us-east-2 prices; starts nothing, calls no AWS API
    scripts/rc-aws.sh start --yes-start
        starts both machines: the test-chain host, and the SEV-SNP host for one attest-only boot (it powers off)
    scripts/rc-aws.sh run <commit> --yes-start --validator-address 0x… --manifest FILE --snp-measurement HEX
                          --amd-chain FILE --nitro-root FILE [--record FILE] [--hours H]
        the whole run, stopping both machines at its end, on any failure and on an interrupt:
        1. preflight (local only): the tools, both modules' outputs, the inputs, the record of <commit>;
        2. start both machines; the SEV-SNP host's first boot only attests (its Radicle node key and firmware);
        3. the commit (a git bundle), the pinned images (docker save) and solc to the run's S3 bucket; provisioning on
           the test-chain host over SSM (scripts/rc-remote.sh provision);
        4. `scripts/integration.sh --release-candidate <commit> --external` on the test-chain host (rc-remote.sh
           start), with the SEV-SNP host's validator address in POF_V3_EXTERNAL and the disk's image digest;
        5. the SSM port forwards (the chain's RPC on 127.0.0.1:18545, the seed on 127.0.0.1:18776), once the chain is
           up: the driver reads the outside validator's registration through them, not through the run;
        6. the SEV-SNP host's user data from the run's ready.json (the same node_config the plan's step 8 names),
           `register …`, then `run --until-idle …`, each a boot; their consoles saved;
        7. the run's external.json; verify.py on the judging boot's console;
        8. `sevSnpValidator` and `attestedImages` into the record (release_candidate.sevsnp_items);
        9. stop both (always), the SEV-SNP host's original user data restored.
    scripts/rc-aws.sh model-run <commit> --yes-start --yes-paid-model-run --model direct:bedrock:<id>
                                --dry-run FILE  (and run's options)
        the real-model item (L18 item 4): the same run with the SEV-SNP host's judge a PAID direct model under its
        spending caps; refused without its own flag, and unless FILE is a passed fake-judge external run of the same
        commit on AWS (`run`'s external.json). Writes `realModelRun` when it passes.
    scripts/rc-aws.sh stop
        stops both machines (also what every failure runs)
    scripts/rc-aws.sh rehearse <commit>
        the dress rehearsal on this machine's Docker, no AWS: the run phase (steps 4-8) against a local
        production-windows chain, the outside validator a local process booted from the same user data the SEV-SNP
        host would get (pof-config.sh's filter, the disk's Radicle setup and node command), with the dstack
        simulator's key in place of SEV-SNP. The record step runs on a copy and must refuse a rehearsal.
    scripts/rc-aws.sh record --record FILE --external FILE --verify FILE --manifest FILE --evidence DIR
        the items from saved files (step 8 alone)

Account-specific values come from the modules' outputs (tofu output: local state, no AWS call) and the profile
(AWS_PROFILE or --profile); nothing here names an account. No model call except model-run's, no public chain."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import release_candidate as rc  # noqa: E402

REGION = "us-east-2"
TESTCHAIN = ROOT / "validator-kit" / "sevsnp" / "testchain"
KIT = ROOT / "validator-kit" / "sevsnp" / "terraform"
VERIFY = ROOT / "validator-kit" / "sevsnp" / "verify.py"
KIT_LIB = ROOT / "validator-kit" / "sevsnp" / "disk" / "rootfs" / "usr" / "lib" / "pof"
RPC_LOCAL, SEED_LOCAL = 18545, 18776  # the SSM forwards on this machine's loopback
TESTCHAIN_TYPE, SEVSNP_TYPE = "c6a.xlarge", "c6a.large"

# us-east-2 (US East, Ohio), on demand, Linux, shared tenancy, read 2026-11-21:
# - c6a.xlarge $0.1530/h and c6a.large $0.0765/h: https://www.doit.com/compute/spot/us-east-2/c6a.xlarge and
#   .../c6a.large (a tracker of AWS's Price List; AWS's own page, https://aws.amazon.com/ec2/pricing/on-demand/, renders
#   its table in the browser only). c6a.large's figure is the one AWS's Price List API gave on 2026-11-20
#   (validator-kit/SEVSNP-PLAN.md, "At a glance");
# - SEV-SNP adds 10 % of the instance's on-demand rate: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/sev-snp.html;
# - a public IPv4 address $0.005/h: https://aws.amazon.com/blogs/aws/new-aws-public-ipv4-address-charge-public-ip-insights/;
# - gp3 $0.08 a GB-month (https://aws.amazon.com/ebs/pricing/), S3 Standard $0.023 a GB-month
#   (https://aws.amazon.com/s3/pricing/): AWS's list prices, not re-read today (cents either way).
PRICES = {"c6a.xlarge": 0.153, "c6a.large": 0.0765, "sevSnpUplift": 0.10, "publicIpv4": 0.005, "gp3GbMonth": 0.08,
          "s3GbMonth": 0.023}
PRICES_READ = "2026-11-21"
TESTCHAIN_DISK_GB = 40
HOURS_A_MONTH = 730
MODEL_RUN_USD = 1.00  # the owner's estimate for one small real-model run (approved separately), capped below
MODEL_SPEND_CAP_USD = "1.50"  # the node's own daily cap in that run (oracle/spend.py): it pauses itself there

FORMATS = {"ready": "pof-external-ready/1", "external": rc.EXTERNAL_FORMAT}
NODE_COMMAND_RE = re.compile(r"^(run|info|register|leave|post-table)([ ][A-Za-z0-9 ._:=/@-]*)?$")  # pof-node.sh's
# pof-config.sh's: the settings the measured disk fixes itself, refused from the user data
FIXED_RE = re.compile(r"^(ORACLE_ATTESTED_IMAGES|ORACLE_SANDBOX|DOCKER_SOCKET|ORACLE_KEYS|ORACLE_SNP_DEVICE|ORACLE_SRC_ROOT|"
                      r"ORACLE_ROUNDS|ORACLE_RECEIPTS|ORACLE_SPEND_LEDGER|ORACLE_PRIVATE_KEY|RPC_API_KEY|MODEL_API_KEY|"
                      r"ORACLE_GIT_TOKEN|ORACLE_RPC_TOKEN|ORACLE_EXCHANGE_TOKEN|ORACLE_RADICLE_EXEC|ORACLE_RADICLE_REPO)=")


class Stop(Exception):
    """The run can't go on (it stops both machines on the way out)."""


def log(msg: str) -> None:
    print(f"rc-aws: {msg}", flush=True)


# ---------------------------------------------------------------------------------------------------------------------
# The plan: machines, hours, cost (no AWS call)


def estimate(hours: float, sevsnp_hours: float | None = None, model_run: bool = False) -> dict:
    """The run's cost at PRICES: the test-chain host (c6a.xlarge, its public IPv4, its gp3 disk for the hours), the
    SEV-SNP host (c6a.large + 10 % for SEV-SNP, its public IPv4), the S3 bucket's few GB for a week; the model run
    when asked. The stopped machines' disks and the kit's snapshot cost the same with or without this run."""
    sev = hours if sevsnp_hours is None else sevsnp_hours
    if hours <= 0 or sev < 0 or sev > hours:
        raise Stop("hours must be positive, and the SEV-SNP host's at most the test chain's")
    p = PRICES
    lines = [
        {"what": f"test-chain host {TESTCHAIN_TYPE} on demand", "hours": hours, "rate": p[TESTCHAIN_TYPE],
         "usd": hours * p[TESTCHAIN_TYPE]},
        {"what": "its public IPv4 address", "hours": hours, "rate": p["publicIpv4"], "usd": hours * p["publicIpv4"]},
        {"what": f"its {TESTCHAIN_DISK_GB} GB gp3 disk", "hours": hours,
         "rate": TESTCHAIN_DISK_GB * p["gp3GbMonth"] / HOURS_A_MONTH,
         "usd": hours * TESTCHAIN_DISK_GB * p["gp3GbMonth"] / HOURS_A_MONTH},
        {"what": f"SEV-SNP host {SEVSNP_TYPE} on demand + 10 % SEV-SNP", "hours": sev,
         "rate": p[SEVSNP_TYPE] * (1 + p["sevSnpUplift"]), "usd": sev * p[SEVSNP_TYPE] * (1 + p["sevSnpUplift"])},
        {"what": "its public IPv4 address", "hours": sev, "rate": p["publicIpv4"], "usd": sev * p["publicIpv4"]},
        {"what": "S3: the bundle, images and logs (about 2 GB, deleted after 7 days)", "hours": 7 * 24,
         "rate": 2 * p["s3GbMonth"] / HOURS_A_MONTH, "usd": 7 * 24 * 2 * p["s3GbMonth"] / HOURS_A_MONTH},
    ]
    if model_run:
        lines.append({"what": "one small real-model run (approved separately; the node's cap "
                              f"${MODEL_SPEND_CAP_USD})", "hours": 0, "rate": 0, "usd": MODEL_RUN_USD})
    return {"region": REGION, "pricesRead": PRICES_READ, "machines": [
        {"name": "test chain", "type": TESTCHAIN_TYPE, "hours": hours,
         "runs": "anvil (production windows, moved clock), the Radicle seed, the six other validators"},
        {"name": "SEV-SNP host", "type": SEVSNP_TYPE, "hours": sev,
         "runs": "the measured checker disk: attestation, its Radicle node, the outside validator"}],
        "lines": lines, "totalUsd": round(sum(x["usd"] for x in lines), 2)}


def print_plan(est: dict) -> None:
    print(f"The release candidate's AWS run (task 7.0), {est['region']}, prices read {est['pricesRead']}:")
    for m in est["machines"]:
        print(f"  {m['name']}: {m['type']} for {m['hours']:g} h at most: {m['runs']}")
    print("  cost:")
    for x in est["lines"]:
        rate = f" at ${x['rate']:.4f}/h" if x["rate"] else ""
        hrs = f" x {x['hours']:g} h" if x["hours"] else ""
        print(f"    ${x['usd']:7.3f}  {x['what']}{hrs}{rate}")
    print(f"  total about ${est['totalUsd']:.2f}; both machines stop at the end, on a failure, and after the "
          f"auto-stop's hours")
    print("Nothing was started. `start` and `run` need --yes-start; the model run needs --yes-paid-model-run too.")


# ---------------------------------------------------------------------------------------------------------------------
# The SEV-SNP host's user data (the kit's format, terraform/main.tf `user_data`) and its stand-in's reading of it


def node_config(ready: dict, judge: str = "fake", extra: dict | None = None) -> dict:
    """The node's settings for the run (validator-kit/SEVSNP-PLAN.md step 8, model (a)), from the run's ready.json.
    ORACLE_REPO names the repository for the node's command line (oracle run needs one; the fixes come from Radicle)."""
    for k in ("rpc", "race", "rid", "family", "image"):
        if not ready.get(k):
            raise Stop(f"ready.json has no {k}")
    cfg = {"ORACLE_VERSION": "3", "ORACLE_RPC": ready["rpc"], "ORACLE_RACE": ready["race"],
           "ORACLE_FAMILY": ready["family"], "ORACLE_JUDGE": judge, "ORACLE_IMAGE": ready["image"],
           "ORACLE_HOST_ID": f"aws:{REGION}" if ready.get("mode") == "aws" else "local:rehearsal",
           "ORACLE_FIX_SOURCE": "radicle", "ORACLE_MERGE_VIA": "radicle", "ORACLE_SEAT_NODES": "chain",
           "ORACLE_RADICLE_RID": ready["rid"], "ORACLE_REPO": "pof/stats", "ORACLE_POLL": "2"}
    cfg.update(extra or {})
    return cfg


def register_command(ready: dict, firmware: int) -> str:
    """`oracle register` as the host runs it; the Radicle node is the host's own (`rad self --did`, --rad-node left
    out: the console's `POF-RADICLE nid` line is checked against the registration afterwards)."""
    return (f"register --bond {int(ready['bond'])} --proof {ready['proof']} --tee-type {ready['teeType']} --level A "
            f"--firmware {int(firmware)}")


def user_data(nonce: str, command: str, seed: str = "", node: dict | None = None, secret_arn: str = "",
              power_off: bool = True, region: str = REGION) -> str:
    """The kit's user data (validator-kit/sevsnp/terraform/main.tf `local.user_data`): the host's POF_* lines, then,
    when the node runs, its settings with the signing key's secret ARN and the region."""
    if not re.fullmatch(r"[0-9a-f]{2,128}", nonce):
        raise Stop("the nonce is lower-case hex")
    if not NODE_COMMAND_RE.match(command):
        raise Stop(f"the disk refuses this node command: {command!r}")
    host = [f"POF_ATTEST_NONCE={nonce}", f"POF_POWER_OFF={'yes' if power_off else 'no'}", f"POF_NODE_COMMAND={command}"]
    if seed:
        host.append(f"POF_RADICLE_SEED={seed}")
    lines = []
    if node:
        lines = [f"{k}={node[k]}" for k in sorted(node)]
        if secret_arn:
            lines.append(f"ORACLE_PRIVATE_KEY_SECRET_ARN={secret_arn}")
        lines.append(f"AWS_REGION={region}")
    for line in host + lines:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*=[ -~]*", line):
            raise Stop(f"a user-data line the disk would refuse: {line.split('=')[0]}")
    return "\n".join(["# proof-of-fix SEV-SNP validator: data, read by the measured disk's pof-config.sh", *host, *lines,
                      ""])


def split_user_data(text: str) -> tuple:
    """pof-config.sh's reading, in Python (the rehearsal's stand-in host): (node settings, host settings, refused
    keys). A line the disk fixes itself, or one that isn't KEY=printable, is refused; others are ignored."""
    node, host, refused = {}, {}, []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*=[ -~]*", line) or FIXED_RE.match(line):
            refused.append(line.split("=", 1)[0])
            continue
        k, v = line.split("=", 1)
        if k.startswith("ORACLE_") or k in ("AWS_REGION", "MODEL_API_KEY_SECRET_ARN", "RPC_API_KEY_SECRET_ARN"):
            node[k] = v
        elif k in ("POF_ATTEST_NONCE", "POF_POWER_OFF", "POF_NODE_COMMAND", "POF_RADICLE_SEED"):
            host[k] = v
    return node, host, refused


def console_facts(text: str) -> dict:
    """What a boot printed on the serial console: its Radicle node ID, firmware, whether it attested, its nonce, and
    the node's registration line."""
    out = {}
    m = re.search(r"POF-RADICLE nid (z6Mk[1-9A-HJ-NP-Za-km-z]{40,50})", text)
    out["nid"] = m.group(1) if m else ""
    m = re.search(r"POF-ATTEST snp-summary \{.*?\"firmware\": (\d+)", text)
    out["firmware"] = int(m.group(1)) if m else None
    out["attested"] = bool(re.search(r"POF-ATTEST ok\s*$", text, re.M))
    m = re.search(r"POF-ATTEST nonce ([0-9a-f]+)", text)
    out["nonce"] = m.group(1) if m else ""
    out["registered"] = bool(re.search(r"registered 0x[0-9a-fA-F]{40} as a candidate", text))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# AWS, through its CLI (a fake in the tests)


class Aws:
    def __init__(self, profile: str = "", region: str = REGION, runner=subprocess.run) -> None:
        self.profile, self.region, self.runner = profile, region, runner
        self.forwards: list = []

    def call(self, *args, parse: bool = True, check: bool = True):
        cmd = ["aws", *args, "--region", self.region] + (["--profile", self.profile] if self.profile else [])
        if parse:
            cmd += ["--output", "json"]
        r = self.runner(cmd, capture_output=True, text=True, timeout=600)
        if check and r.returncode:
            raise Stop(f"aws {' '.join(args[:2])}: {(r.stderr or r.stdout).strip()[-300:]}")
        if not parse:
            return r.stdout
        return json.loads(r.stdout) if r.stdout.strip() else {}

    def start(self, *ids) -> None:
        self.call("ec2", "start-instances", "--instance-ids", *ids)

    def stop(self, *ids) -> None:
        self.call("ec2", "stop-instances", "--instance-ids", *ids)

    def state(self, iid: str) -> str:
        d = self.call("ec2", "describe-instances", "--instance-ids", iid)
        return d["Reservations"][0]["Instances"][0]["State"]["Name"]

    def wait_state(self, iid: str, want: str, timeout: float, every: float = 10, sleep=time.sleep) -> None:
        t = time.time()
        while self.state(iid) != want:
            if time.time() - t > timeout:
                raise Stop(f"{iid} isn't {want} after {timeout:.0f} s")
            sleep(every)

    def get_user_data(self, iid: str) -> str:
        d = self.call("ec2", "describe-instance-attribute", "--instance-id", iid, "--attribute", "userData")
        v = d.get("UserData", {}).get("Value", "")
        return base64.b64decode(v).decode() if v else ""

    def set_user_data(self, iid: str, text: str) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".b64", delete=False) as f:
            f.write(base64.b64encode(text.encode()).decode())
        try:
            self.call("ec2", "modify-instance-attribute", "--instance-id", iid, "--attribute", "userData",
                      "--value", f"file://{f.name}", parse=False)
        finally:
            os.unlink(f.name)

    def console(self, iid: str) -> str:
        return self.call("ec2", "get-console-output", "--instance-id", iid, "--latest", "--output", "text",
                         parse=False)

    def ssm_online(self, iid: str) -> bool:
        d = self.call("ssm", "describe-instance-information", "--filters", f"Key=InstanceIds,Values={iid}")
        return any(x.get("PingStatus") == "Online" for x in d.get("InstanceInformationList", []))

    def ssm_run(self, iid: str, script: str, timeout: int = 3600, sleep=time.sleep) -> str:
        """One shell script on the instance as root (AWS-RunShellScript); its output, or Stop."""
        params = json.dumps({"commands": [script], "executionTimeout": [str(timeout)]})
        d = self.call("ssm", "send-command", "--instance-ids", iid, "--document-name", "AWS-RunShellScript",
                      "--parameters", params, "--timeout-seconds", "600")
        cid = d["Command"]["CommandId"]
        t = time.time()
        while True:
            sleep(5)
            r = self.call("ssm", "get-command-invocation", "--command-id", cid, "--instance-id", iid, check=False)
            status = r.get("Status", "Pending")
            if status in ("Success", "Failed", "Cancelled", "TimedOut"):
                if status != "Success":
                    raise Stop(f"on the test-chain host: {status}: {r.get('StandardErrorContent', '')[-400:]}"
                               f"{r.get('StandardOutputContent', '')[-400:]}")
                return r.get("StandardOutputContent", "")
            if time.time() - t > timeout + 120:
                raise Stop("an SSM command didn't finish")

    def s3_cp(self, src: str, dst: str) -> None:
        self.call("s3", "cp", "--only-show-errors", src, dst, parse=False)

    def forward(self, iid: str, host: str, port: int, local: int):
        """An SSM port forward to `host`:`port` from the instance, on 127.0.0.1:`local` here."""
        cmd = ["aws", "ssm", "start-session", "--region", self.region, "--target", iid, "--document-name",
               "AWS-StartPortForwardingSessionToRemoteHost", "--parameters",
               json.dumps({"host": [host], "portNumber": [str(port)], "localPortNumber": [str(local)]})]
        cmd += ["--profile", self.profile] if self.profile else []
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        self.forwards.append(p)
        return p

    def close_forwards(self) -> None:
        for p in self.forwards:
            if p.poll() is None:
                p.terminate()
        self.forwards = []


def tofu_outputs(directory: Path, runner=subprocess.run) -> dict:
    """A module's outputs from its local state (`tofu output -json`: no AWS call)."""
    r = runner(["tofu", f"-chdir={directory}", "output", "-json"], capture_output=True, text=True, timeout=120)
    if r.returncode:
        raise Stop(f"tofu output in {directory.relative_to(ROOT)}: {(r.stderr or r.stdout).strip()[-200:]}")
    return {k: v.get("value") for k, v in json.loads(r.stdout or "{}").items()}


def rpc_call(url: str, method: str, params: list):
    import urllib.request

    req = urllib.request.Request(url, json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
                                 .encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        out = json.loads(r.read())
    if "error" in out:
        raise Stop(f"{method}: {out['error']}")
    return out["result"]


# ---------------------------------------------------------------------------------------------------------------------
# The run on AWS


class Machines:
    """Both machines, stopped on the way out whatever happens: a failure, Ctrl-C, SIGTERM or SIGHUP. The SEV-SNP host's
    original user data is put back once it is stopped (what the kit's Terraform state says it has)."""

    def __init__(self, aws: Aws, testchain: str, sevsnp: str, sleep=time.sleep) -> None:
        self.aws, self.testchain, self.sevsnp, self.sleep = aws, testchain, sevsnp, sleep
        self.original = None
        self.started = False

    def __enter__(self):
        self.old = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGHUP)}
        for s in self.old:
            signal.signal(s, self._interrupt)
        return self

    @staticmethod
    def _interrupt(*_):
        raise KeyboardInterrupt

    def remember(self) -> None:
        """The SEV-SNP host's user data as the kit set it, read before anything changes it."""
        if self.original is None:
            self.original = self.aws.get_user_data(self.sevsnp)
        self.started = True  # from here on the way out stops both and puts the user data back

    def start(self) -> None:
        self.remember()
        self.aws.start(self.testchain, self.sevsnp)

    def stop_all(self) -> list:
        problems = []
        self.aws.close_forwards()
        for iid in (self.testchain, self.sevsnp):
            try:
                self.aws.stop(iid)
            except Exception as e:  # noqa: BLE001 (try the other one; report both)
                problems.append(f"stop {iid}: {e}")
        for iid in (self.testchain, self.sevsnp):
            try:
                self.aws.wait_state(iid, "stopped", 900, sleep=self.sleep)
            except Exception as e:  # noqa: BLE001
                problems.append(f"{iid} not stopped: {e}")
        if self.original is not None:
            try:
                self.aws.set_user_data(self.sevsnp, self.original)
            except Exception as e:  # noqa: BLE001
                problems.append(f"the SEV-SNP host's user data not restored: {e}")
        return problems

    def __exit__(self, *exc):
        try:
            if self.started:
                problems = self.stop_all()
                log("both machines stopped" + ("" if not problems else "; PROBLEMS: " + "; ".join(problems)))
        finally:
            for s, h in self.old.items():
                signal.signal(s, h)
        return False


def preflight(a, outputs: dict, kit: dict, need_record: bool = True) -> dict:
    """Everything checked before any AWS call: tools, the modules' outputs, the inputs, the record."""
    missing = [t for t in ("aws", "session-manager-plugin", "tofu", "docker", "git") if shutil.which(t) is None]
    if missing:
        raise Stop(f"missing here: {', '.join(missing)}")
    for k in ("instance_id", "bucket", "private_ip"):
        if not outputs.get(k):
            raise Stop(f"the test-chain module has no {k}: apply it with create_instance = true first (the owner)")
    if not kit.get("instance_id"):
        raise Stop("the SEV-SNP kit has no instance_id: apply it with the new disk first (SEVSNP-PLAN.md steps 3-6)")
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", a.validator_address or ""):
        raise Stop("--validator-address: the SEV-SNP host's signing key's address")
    manifest = json.loads(Path(a.manifest).read_text())
    if kit.get("image_digest") and kit["image_digest"] != manifest.get("image_digest"):
        raise Stop("the manifest's image_digest isn't the kit's AMI's")
    for f in (a.amd_chain, a.nitro_root):
        if not f or not Path(f).is_file():
            raise Stop("--amd-chain and --nitro-root: verify.py runs every check (SEVSNP-PLAN.md step 7)")
    if not re.fullmatch(r"[0-9a-f]{96}", a.snp_measurement or ""):
        raise Stop("--snp-measurement: the expected launch measurement, 96 hex digits (SEVSNP-PLAN.md step 7)")
    sha = rc.resolve(a.commit)
    record = Path(a.record) if a.record else None
    if need_record:
        if record is None or not record.is_file():
            raise Stop("--record: the record `scripts/integration.sh --release-candidate <commit>` wrote (run it "
                       "first: it needs no AWS)")
        doc = json.loads(record.read_text())
        if doc.get("commit") != sha:
            raise Stop(f"{record} is the record of another commit")
    return {"sha": sha, "manifest": manifest, "record": record}


def bundle(sha: str, work: Path) -> list:
    """The commit as a git bundle, the pinned images (docker save) and solc's cache, for the S3 bucket."""
    ref = f"refs/pof-rc-aws/{sha[:12]}"
    subprocess.run(["git", "update-ref", ref, sha], cwd=ROOT, check=True)
    try:
        subprocess.run(["git", "bundle", "create", str(work / "repo.bundle"), ref], cwd=ROOT, check=True,
                       capture_output=True)
    finally:
        subprocess.run(["git", "update-ref", "-d", ref], cwd=ROOT, check=False)
    images = remote_images()
    with open(work / "images.tar", "wb") as f:
        subprocess.run(["docker", "save", *images.values()], stdout=f, check=True)
    ids = {k: subprocess.run(["docker", "image", "inspect", "-f", "{{.Id}}", v], capture_output=True, text=True,
                             check=True).stdout.strip() for k, v in images.items()}
    (work / "images.json").write_text(json.dumps({"images": images, "ids": ids}, indent=2))
    subprocess.run(["tar", "-czf", str(work / "solc.tgz"), "-C", str(ROOT / "contracts"), ".cache"], check=True)
    return ["repo.bundle", "images.tar", "images.json", "solc.tgz"]


def remote_images() -> dict:
    """The images the external set runs, as this checkout pins them: anvil's Foundry image and the relay's Python by
    digest, the sandbox's test image by digest (oracle/sandbox.py), and the Radicle node image built from
    spikes/radicle/Dockerfile (Radicle 1.10.3 by SHA-256)."""
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "spikes" / "radicle"))
    from oracle import sandbox  # noqa: E402

    spike = (ROOT / "spikes" / "radicle" / "v3_spike.py").read_text()
    foundry = re.search(r'^FOUNDRY_IMAGE = "([^"]+)"', spike, re.M).group(1)
    py = re.search(r'^PY_IMAGE = "([^"]+)"', spike, re.M).group(1)
    return {"foundry": foundry, "python": py, "test": sandbox.TEST_IMAGES["amd64"], "radicle": "pof190-radicle:spike"}


def remote(aws: Aws, iid: str, action: str, *args, timeout: int = 3600) -> str:
    cmd = " ".join(shlex.quote(x) for x in ["bash", "/opt/pof/rc-remote.sh", action, *args])
    return aws.ssm_run(iid, cmd, timeout=timeout)


def status_of(text: str) -> dict:
    m = re.search(r"^@status (\{.*\})$", text, re.M)
    return json.loads(m.group(1)) if m else {}


def wait_for(probe, what: str, timeout: float, every: float = 20, sleep=time.sleep):
    t = time.time()
    while True:
        got = probe()
        if got:
            return got
        if time.time() - t > timeout:
            raise Stop(f"{what}: not within {timeout:.0f} s")
        sleep(every)


def aws_run(a, aws: Aws | None = None, sleep=time.sleep) -> int:
    """`run` and `model-run` (the module's docstring)."""
    if not a.yes_start:
        raise Stop("refused: `run` starts two machines; add --yes-start (the owner approves each start)")
    paid = getattr(a, "model", "")
    if paid:
        if not a.yes_paid_model_run:
            raise Stop("refused: the real-model run makes PAID model calls; add --yes-paid-model-run")
        dry = json.loads(Path(a.dry_run).read_text()) if a.dry_run and Path(a.dry_run).is_file() else {}
        if not (dry.get("format") == rc.EXTERNAL_FORMAT and dry.get("result") == "passed" and dry.get("mode") == "aws"
                and dry.get("commit") == rc.resolve(a.commit)):
            raise Stop("refused: --dry-run must be a passed fake-judge external run of this commit on AWS "
                       "(`run`'s external.json)")
        if not paid.startswith("direct:bedrock:"):
            raise Stop("--model: direct:bedrock:<model id> (the instance role's credentials; the kit's "
                       "bedrock_model_arns lists it)")
    outputs, kit = tofu_outputs(TESTCHAIN), tofu_outputs(KIT)
    pre = preflight(a, outputs, kit)
    sha, manifest = pre["sha"], pre["manifest"]
    aws = aws or Aws(a.profile)
    out = Path(a.out or tempfile.mkdtemp(prefix=f"pof-rc-aws-{sha[:12]}-"))
    out.mkdir(parents=True, exist_ok=True)
    tc, sev, bucket, ip = outputs["instance_id"], kit["instance_id"], outputs["bucket"], outputs["private_ip"]
    log(f"commit {sha}; evidence and logs in {out}")
    with Machines(aws, tc, sev, sleep=sleep) as m:
        nonces = {k: secrets.token_hex(16) for k in ("attest", "register", "run")}
        (out / "nonces.json").write_text(json.dumps(nonces, indent=2))
        # 2. both machines; the SEV-SNP host's first boot only attests (no node settings), then powers off
        aws.wait_state(sev, "stopped", 900, sleep=sleep)
        m.remember()
        aws.set_user_data(sev, user_data(nonces["attest"], "run --until-idle 600"))
        m.start()
        log(f"started {tc} (test chain) and {sev} (SEV-SNP, attest-only boot)")
        # 3. the bundle and provisioning
        work = Path(tempfile.mkdtemp(prefix="pof-rc-aws-bundle-"))
        try:
            files = bundle(sha, work)
            for f in files:
                aws.s3_cp(str(work / f), f"s3://{bucket}/{sha}/{f}")
        finally:
            shutil.rmtree(work, ignore_errors=True)
        wait_for(lambda: aws.ssm_online(tc), "the test-chain host on SSM", 900, sleep=sleep)
        log(" ".join(remote(aws, tc, "provision", bucket, sha, timeout=3600).strip().splitlines()[-1:]))
        # 4. the external set on the test-chain host
        remote(aws, tc, "start", sha, a.validator_address, manifest["image_digest"], ip, a.wait_seconds)
        ready = wait_for(lambda: status_of(remote(aws, tc, "status", timeout=120)).get("ready"),
                         "the test chain ready (deployed, six validators qualified)", 3 * 3600, every=60, sleep=sleep)
        (out / "ready.json").write_text(json.dumps(ready, indent=2))
        if ready.get("format") != FORMATS["ready"] or ready.get("external", "").lower() != a.validator_address.lower():
            raise Stop("ready.json isn't the run's (format or outside key)")
        # 5. the forwards; the chain through them
        aws.forward(tc, ip, 8545, RPC_LOCAL)
        aws.forward(tc, ip, 8776, SEED_LOCAL)
        url = f"http://127.0.0.1:{RPC_LOCAL}"
        wait_for(lambda: _chain_id(url) == ready["chainId"], "the chain through the SSM forward", 120, every=5,
                 sleep=sleep)
        # 6. the SEV-SNP host: its attest-only boot's console, then register, then run
        aws.wait_state(sev, "stopped", 900, sleep=sleep)
        console0 = aws.console(sev)
        (out / "console-attest.txt").write_text(console0)
        facts0 = console_facts(console0)
        if not facts0["nid"] or facts0["firmware"] is None or not facts0["attested"]:
            raise Stop(f"the attest-only boot didn't attest or print its Radicle node and firmware: {facts0}")
        judge = paid or "fake"
        extra = {}
        if paid:
            extra = {"ORACLE_MODEL_ALLOW": paid.split(":", 2)[2], "ORACLE_SPEND_DAILY_USD": MODEL_SPEND_CAP_USD,
                     "ORACLE_SPEND_MONTHLY_USD": MODEL_SPEND_CAP_USD, "ORACLE_MAX_CALLS": "20"}
        cfg = node_config(ready, judge, extra)
        (out / "node-config.json").write_text(json.dumps(cfg, indent=2))
        aws.set_user_data(sev, user_data(nonces["register"], register_command(ready, facts0["firmware"]),
                                         ready["seed"], cfg, kit.get("signing_key_secret_arn", "")))
        aws.start(sev)
        wait_for(lambda: _registered(url, ready["registry"], a.validator_address), "the SEV-SNP host registered",
                 1800, every=15, sleep=sleep)
        aws.wait_state(sev, "stopped", 900, sleep=sleep)
        console1 = aws.console(sev)
        (out / "console-register.txt").write_text(console1)
        aws.set_user_data(sev, user_data(nonces["run"], f"run --until-idle {int(a.idle_seconds)}", ready["seed"], cfg,
                                         kit.get("signing_key_secret_arn", "")))
        aws.start(sev)
        console2 = wait_for(lambda: (lambda t: t if console_facts(t)["attested"] else "")(aws.console(sev)),
                            "the judging boot attested", 900, every=20, sleep=sleep)
        # 7. the external set's result; the judging boot's console verified
        st = wait_for(lambda: (lambda s: s if s.get("result") else None)(status_of(remote(aws, tc, "status",
                                                                                           timeout=120))),
                      "the external set finished", a.hours * 3600, every=60, sleep=sleep)
        external = st["result"]
        (out / "external.json").write_text(json.dumps(external, indent=2))
        console2 = aws.console(sev) or console2
        (out / "console-run.txt").write_text(console2)
        verify = run_verify(out / "console-run.txt", a.manifest, nonces["run"], a.snp_measurement, a.amd_chain,
                            a.nitro_root, out / "evidence")
        (out / "verify.json").write_text(json.dumps(verify, indent=1, sort_keys=True))
        # 8. the record
        nid = console_facts(console1)["nid"] or facts0["nid"]
        problems = write_items(pre["record"], external, verify, manifest, str(out), nid, model=paid)
        log(f"external set {external.get('result')}; verify.py {'passed' if verify.get('passed') else 'FAILED'}; "
            + ("record updated" if not problems else "pending: " + "; ".join(problems)))
        return 0 if not problems else 1


def _chain_id(url: str) -> int:
    try:
        return int(rpc_call(url, "eth_chainId", []), 16)
    except Exception:  # noqa: BLE001 (not up yet)
        return 0


def _registered(url: str, registry: str, key: str) -> bool:
    """The registry's bond for `key` > 0 (validator(address)'s 14th word), read through the forward."""
    sel = "0x" + _selector("validator(address)") + "0" * 24 + key[2:].lower()
    try:
        data = rpc_call(url, "eth_call", [{"to": registry, "data": sel}, "latest"])
    except Exception:  # noqa: BLE001
        return False
    words = [data[2 + 64 * i: 2 + 64 * (i + 1)] for i in range((len(data) - 2) // 64)]
    return len(words) > 13 and int(words[13], 16) > 0


def _selector(sig: str) -> str:
    sys.path.insert(0, str(ROOT))
    from oracle import crypto  # noqa: E402

    return crypto.keccak256(sig.encode())[:4].hex()


def run_verify(console: Path, manifest: str, nonce: str, measurement: str, amd: str, nitro: str, save: Path) -> dict:
    r = subprocess.run([sys.executable, str(VERIFY), "--console", str(console), "--manifest", manifest, "--nonce", nonce,
                        "--snp-measurement", measurement, "--amd-chain", amd, "--nitro-root", nitro, "--save",
                        str(save)], capture_output=True, text=True, timeout=300)
    try:
        return json.loads(r.stdout)
    except ValueError:
        return {"passed": False, "error": (r.stderr or r.stdout)[-400:]}


def write_items(record: Path, external: dict, verify: dict, manifest: dict, evidence: str, nid: str = "",
                model: str = "") -> list:
    """sevsnp_items into the record file (and `realModelRun` for a model run). Returns what stays pending."""
    doc = json.loads(record.read_text())
    new, why = rc.sevsnp_items(doc, external, verify, manifest, evidence)
    problems = why["sevSnpValidator"] + [p for p in why["attestedImages"] if p not in why["sevSnpValidator"]]
    reg = external.get("registration", {}) if isinstance(external, dict) else {}
    if nid and reg.get("radNode") != nid:
        problems.append(f"the registration's Radicle node {reg.get('radNode', '')[:16]}… isn't the console's {nid[:16]}…")
        new["checks"]["sevSnpValidator"] = doc.get("checks", {}).get("sevSnpValidator", "pending")
    if model:
        ok = not problems and external.get("result") == "passed"
        if ok and new["checks"].get("realModelRun") != "passed":
            new["checks"]["realModelRun"] = "passed"
            new["checks"]["realModelRunEvidence"] = evidence
            new["checks"]["realModelRunModel"] = model
    new["result"] = rc.result_of(new["checks"], rc.runs_passed(new))
    record.write_text(json.dumps(new, indent=2) + "\n")
    return problems


def aws_start(a, aws: Aws | None = None, sleep=time.sleep) -> int:
    if not a.yes_start:
        raise Stop("refused: `start` starts two machines; add --yes-start (the owner approves each start)")
    outputs, kit = tofu_outputs(TESTCHAIN), tofu_outputs(KIT)
    if not outputs.get("instance_id") or not kit.get("instance_id"):
        raise Stop("both modules need their instance (create_instance = true) first")
    aws = aws or Aws(a.profile)
    sev = kit["instance_id"]
    aws.wait_state(sev, "stopped", 900, sleep=sleep)
    nonce = secrets.token_hex(16)
    aws.set_user_data(sev, user_data(nonce, "run --until-idle 600"))  # attest only: no node settings
    aws.start(outputs["instance_id"], sev)
    log(f"started {outputs['instance_id']} and {sev} (attest-only boot, nonce {nonce}); `scripts/rc-aws.sh stop` "
        f"stops both (the SEV-SNP host powers itself off after attesting); its user data is now attest-only: "
        f"`tofu apply` in the kit puts the module's back")
    return 0


def aws_stop(a, aws: Aws | None = None, sleep=time.sleep) -> int:
    outputs, kit = tofu_outputs(TESTCHAIN), tofu_outputs(KIT)
    aws = aws or Aws(a.profile)
    ids = [x for x in (outputs.get("instance_id"), kit.get("instance_id")) if x]
    if not ids:
        log("no instance in either module: nothing to stop")
        return 0
    aws.stop(*ids)
    for iid in ids:
        aws.wait_state(iid, "stopped", 900, sleep=sleep)
    log(f"stopped {', '.join(ids)}")
    return 0


# ---------------------------------------------------------------------------------------------------------------------
# The dress rehearsal: the run phase on this machine


class LocalHost:
    """The rehearsal's stand-in for the SEV-SNP host, booted from the user data the driver gives the instance: the
    disk's pof-config.sh filter (split_user_data), its Radicle node (radicle-setup.sh with the seed, radicle-node with
    pof-radicle.service's command, radicle-ready.sh) in a container on the run's outside network, and the node's
    command as pof-node.sh runs it, but here as a local process: the dstack simulator's key in place of SEV-SNP (no SNP
    device here) and the Docker CLI sandbox in place of the measured disk's attested images."""

    STATE, REPO, FILES = "/data/state/radicle", "/data/scratch/radicle/repo", "/opt/pof-kit"

    def __init__(self, ready: dict, work: Path) -> None:
        self.ready, self.work = ready, work
        loc = ready["local"]
        self.name = f"{loc['prefix']}-outside"
        self.console = work / "console.txt"
        self.procs: list = []
        work.mkdir(parents=True, exist_ok=True)

    def say(self, line: str) -> None:
        with open(self.console, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def docker(self, *args, check: bool = True, input: str | None = None) -> str:
        r = subprocess.run(["docker", *args], capture_output=True, text=True, input=input, timeout=600,
                           stdin=None if input is not None else subprocess.DEVNULL)
        if check and r.returncode:
            raise Stop(f"docker {' '.join(args[:3])}: {(r.stderr or r.stdout).strip()[-300:]}")
        return r.stdout.strip()

    def sh(self, script: str, check: bool = True) -> str:
        return self.docker("exec", self.name, "bash", "-c", script, check=check)

    def radicle(self, host: dict, node: dict) -> None:
        loc = self.ready["local"]
        if not self.docker("ps", "-q", "--filter", f"name=^{self.name}$"):
            self.docker("run", "-d", "--name", self.name, "--hostname", "outside", "--network", loc["network"],
                        "-e", f"RAD_HOME={self.STATE}", "-v", f"{self.name}-data:/data", loc["radicleImage"])
            self.docker("exec", "-u", "root", self.name, "bash", "-c",
                        f"mkdir -p {self.STATE} /data/scratch/radicle {self.FILES} && chown -R foundry:foundry /data")
            for f in ("radicle-setup.sh", "radicle-ready.sh", "radicle-config.json"):
                self.docker("cp", str(KIT_LIB / f), f"{self.name}:{self.FILES}/{f}")
        self.sh("rad node stop >/dev/null 2>&1 || true", check=False)
        rid, seed = node.get("ORACLE_RADICLE_RID", ""), host.get("POF_RADICLE_SEED", "")
        if rid and not seed:
            rid = ""
        out = self.sh(f"bash {self.FILES}/radicle-setup.sh pof-validator main {shlex.quote(rid)} {shlex.quote(seed)}")
        nid = self.sh("rad self --nid")
        self.say(f"POF-RADICLE nid {nid}")
        self.say(f"POF-RADICLE repository {rid or 'none'}; seed {seed or 'none'}; {out.splitlines()[-1]}")
        unit = (KIT_LIB.parent.parent.parent / "etc" / "systemd" / "system" / "pof-radicle.service").read_text()
        start = re.sub(r"^/usr/lib/pof/radicle/bin/", "", re.search(r"^ExecStart=(.+)$", unit, re.M).group(1).strip())
        self.sh(f"mkdir -p $RAD_HOME/node && (setsid nohup {start} >>$RAD_HOME/node/node.log 2>&1 &) && "
                f"for _ in $(seq 300); do rad node status 2>/dev/null | grep -q 'Node is running' && break; "
                f"sleep 0.1; done")
        ready = self.sh(f"cd /data/scratch/radicle && bash {self.FILES}/radicle-ready.sh {shlex.quote(rid)} "
                        f"{self.REPO} 2>&1; true", check=False)
        self.say(f"POF-RADICLE ready: {ready}")

    def boot(self, text: str, wait: bool = True):
        """One boot: returns the node's exit code (`wait`), or its process."""
        node, host, refused = split_user_data(text)
        for k in refused:
            self.say(f"pof-config: refused a user-data line for {k}")
        self.say(f"POF-ATTEST nonce {host.get('POF_ATTEST_NONCE', '')}")
        self.say("POF-ATTEST ok (rehearsal: no SEV-SNP report here; the dstack simulator stands in)")
        self.radicle(host, node)
        if not node:
            self.say("pof-node: no node configuration in the user data; attest only")
            return 0 if wait else None
        cmd = host.get("POF_NODE_COMMAND", "run --until-idle 600")
        if not NODE_COMMAND_RE.match(cmd):
            self.say("pof-node: refused POF_NODE_COMMAND")
            return 1 if wait else None
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(self.work), **node,
               "ORACLE_KEYS": "dstack", "DSTACK_SIMULATOR_ENDPOINT": self.ready["local"]["simulator"],
               "ORACLE_SANDBOX": "cli", "ORACLE_SRC_ROOT": str(self.work / "src"),
               "ORACLE_ROUNDS": str(self.work / "rounds"), "ORACLE_RECEIPTS": str(self.work / "receipts"),
               "ORACLE_SPEND_LEDGER": str(self.work / "spend.json"),
               "ORACLE_RADICLE_EXEC": f"docker exec -i {self.name}", "ORACLE_RADICLE_REPO": self.REPO}
        f = open(self.console, "a", encoding="utf-8")
        p = subprocess.Popen([sys.executable, "-m", "oracle", *cmd.split()], cwd=self.ready["local"]["root"], env=env,
                             stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        self.procs.append(p)
        if not wait:
            return p
        code = p.wait()
        self.say(f"pof-node: run ended with {code}")
        return code

    def shutdown(self) -> None:
        for p in self.procs:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(30)
                except subprocess.TimeoutExpired:
                    p.kill()
        self.docker("rm", "-f", self.name, check=False)
        self.docker("volume", "rm", "-f", f"{self.name}-data", check=False)


def rehearse(a) -> int:
    """The run phase on this machine (the module's docstring)."""
    sha = rc.resolve(a.commit)
    out = Path(a.out or tempfile.mkdtemp(prefix=f"pof-rc-rehearsal-{sha[:12]}-"))
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log(f"dress rehearsal of {sha[:12]}: logs and results in {out}")
    env = dict(os.environ, POF_EXT_MODE="local", DEVNET_V3_WINDOWS="production")
    env.pop("POF_V3_EXTERNAL", None)  # the rehearsal's outside key is the simulator's, written in ready.json
    t0 = time.time()
    run_log = open(out / "release-candidate.log", "w", encoding="utf-8")
    proc = subprocess.Popen(["scripts/integration.sh", "--release-candidate", sha, "--external", "--logs", str(logs)],
                            cwd=ROOT, env=env, stdout=run_log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    host = None
    summary: dict = {"commit": sha, "steps": {}}
    try:
        ready = wait_for(lambda: _read(logs / "ready.json") if proc.poll() is None else _gone(proc),
                         "ready.json", a.hours * 3600, every=10)
        summary["steps"]["ready"] = round(time.time() - t0)
        log(f"ready after {summary['steps']['ready']} s: outside key {ready['external']}, rpc {ready['rpc']}, "
            f"seed {ready['seed']}")
        host = LocalHost(ready, out / "outside")
        nonces = {k: secrets.token_hex(16) for k in ("attest", "register", "run")}
        host.boot(user_data(nonces["attest"], "run --until-idle 600"))
        facts0 = console_facts(host.console.read_text())
        if not facts0["nid"]:
            raise Stop("the attest-only boot printed no Radicle node ID")
        cfg = node_config(ready)
        code = host.boot(user_data(nonces["register"], register_command(ready, 0), ready["seed"], cfg))
        if code != 0 or not console_facts(host.console.read_text())["registered"]:
            raise Stop(f"the outside validator's register boot ended with {code}")
        summary["steps"]["registered"] = round(time.time() - t0)
        log(f"registered after {summary['steps']['registered']} s (Radicle node {facts0['nid']})")
        host.boot(user_data(nonces["run"], f"run --until-idle {int(a.idle_seconds)}", ready["seed"], cfg), wait=False)
        code = proc.wait()
        summary["steps"]["finished"] = round(time.time() - t0)
        external = _read(logs / "external.json") or {"result": "failed"}
        summary["external"] = external
        summary["releaseCandidateExit"] = code
        # the record step on a copy: a rehearsal must never pass the items
        scratch = {"format": "pof-release-candidate/1", "commit": sha, "result": "incomplete",
                   "checks": {"integration": {"runs": ["passed"] * 3}, "productionWindows": "passed",
                              "sevSnpValidator": "pending", "realModelRun": "pending", "attestedImages": "pending"}}
        rec = out / "record-rehearsal.json"
        rec.write_text(json.dumps(scratch, indent=2))
        problems = write_items(rec, external, {"passed": False, "checks": {}}, {"image_digest": ready["image"]},
                               str(out), facts0["nid"])
        after = json.loads(rec.read_text())
        summary["record"] = {"sevSnpValidator": after["checks"]["sevSnpValidator"],
                             "attestedImages": after["checks"]["attestedImages"], "why": problems}
        ok = (code == 0 and external.get("result") == "passed" and after["checks"]["sevSnpValidator"] == "pending"
              and after["checks"]["attestedImages"] == "pending")
        summary["result"] = "passed" if ok else "failed"
        log(f"rehearsal {summary['result']}: external set {external.get('result')} (exit {code}); the record step "
            f"kept both items pending on the rehearsal: {'; '.join(problems[:3])}")
        return 0 if ok else 1
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(120)
            except subprocess.TimeoutExpired:
                proc.kill()
        if host is not None:
            host.shutdown()
        summary["wallSeconds"] = round(time.time() - t0)
        (out / "rehearsal.json").write_text(json.dumps(summary, indent=2))


def _read(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _gone(proc) -> None:
    raise Stop(f"the release-candidate run ended (exit {proc.returncode}) before the chain was ready")


# ---------------------------------------------------------------------------------------------------------------------


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(prog="scripts/rc-aws.sh", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--hours", type=float, default=6.0)
    p.add_argument("--sevsnp-hours", type=float)
    p.add_argument("--model-run", action="store_true")
    p.add_argument("--json", action="store_true")
    for name in ("start", "stop"):
        p = sub.add_parser(name)
        p.add_argument("--profile", default=os.environ.get("AWS_PROFILE", ""))
        p.add_argument("--yes-start", action="store_true")
    for name in ("run", "model-run"):
        p = sub.add_parser(name)
        p.add_argument("commit")
        p.add_argument("--yes-start", action="store_true")
        p.add_argument("--profile", default=os.environ.get("AWS_PROFILE", ""))
        p.add_argument("--validator-address", default="")
        p.add_argument("--manifest", default=str(ROOT / "validator-kit" / "sevsnp" / "out" / "manifest.json"))
        p.add_argument("--snp-measurement", default="")
        p.add_argument("--amd-chain", default="")
        p.add_argument("--nitro-root", default="")
        p.add_argument("--record", default="")
        p.add_argument("--out", default="")
        p.add_argument("--hours", type=float, default=6.0, help="the external set's limit (the auto-stop is 8 h)")
        p.add_argument("--idle-seconds", type=int, default=3600, help="the SEV-SNP node's run --until-idle")
        p.add_argument("--wait-seconds", default="1800", help="POF_V3_EXTERNAL_WAIT: a seat's hold on the clock")
        if name == "model-run":
            p.add_argument("--yes-paid-model-run", action="store_true")
            p.add_argument("--model", required=True)
            p.add_argument("--dry-run", default="")
    p = sub.add_parser("rehearse")
    p.add_argument("commit")
    p.add_argument("--out", default="")
    p.add_argument("--hours", type=float, default=3.0)
    p.add_argument("--idle-seconds", type=int, default=3600)
    p = sub.add_parser("record")
    for k in ("--record", "--external", "--verify", "--manifest", "--evidence"):
        p.add_argument(k, required=True)
    p.add_argument("--nid", default="")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "plan":
            est = estimate(a.hours, a.sevsnp_hours, a.model_run)
            print(json.dumps(est, indent=2)) if a.json else print_plan(est)
            return 0
        if a.cmd == "start":
            return aws_start(a)
        if a.cmd == "stop":
            return aws_stop(a)
        if a.cmd in ("run", "model-run"):
            if a.cmd == "run":
                a.model, a.yes_paid_model_run, a.dry_run = "", False, ""
            return aws_run(a)
        if a.cmd == "rehearse":
            return rehearse(a)
        if a.cmd == "record":
            problems = write_items(Path(a.record), json.loads(Path(a.external).read_text()),
                                   json.loads(Path(a.verify).read_text()), json.loads(Path(a.manifest).read_text()),
                                   a.evidence, a.nid)
            print("record updated" if not problems else "pending: " + "; ".join(problems))
            return 0 if not problems else 1
    except (Stop, rc.Stop) as e:
        print(f"rc-aws: {e}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
