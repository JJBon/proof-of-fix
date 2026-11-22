"""The release candidate's AWS run (proof-of-fix#251 task 7.0; scripts/rc_aws.py, scripts/rc-aws.sh,
validator-kit/sevsnp/testchain, tests/integration/external_v3.py), without AWS or Docker: the driver refuses to start
anything without its flag and stops both machines on every way out, the user data it gives the SEV-SNP host is what
the measured disk reads, the record's two items pass only for a real run of the record's commit, the plan's cost, and
the test-chain module's static checks (as tests/test_sevsnp_kit.py checks the kit's). The run phase itself is
exercised end to end on local Docker by `scripts/rc-aws.sh rehearse <commit>`."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
TC = ROOT / "validator-kit" / "sevsnp" / "testchain"
DISK = ROOT / "validator-kit" / "sevsnp" / "disk"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests" / "integration"))


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


A = load("rc_aws_under_test", ROOT / "scripts" / "rc_aws.py")
rc = A.rc
autostop = load("autostop_under_test", TC / "lambda" / "autostop.py")

SHA = "b" * 40
DIGEST = "0x" + "34" * 32
TC_ID, SEV_ID = "i-0testchain0000000", "i-0sevsnp000000000"
READY = {"format": "pof-external-ready/1", "mode": "aws", "external": "0x" + "ab" * 20, "chainId": 31337,
         "rpc": "http://10.82.0.10:8545", "race": "0x" + "11" * 20, "registry": "0x" + "22" * 20,
         "rid": "rad:z4Gp1iGMs8UFR2eK677ypRQv58iUQ", "seed": "z6Mkg28rGnkkinmF2WPCCar6QgY74t4BjqSdYd7nPNPPmc68@10.82.0.10:8776",
         "family": "fake-6", "image": DIGEST, "bond": 250, "proof": "tee", "teeType": "amd-sev-snp",
         "windowsKind": "production", "acceptedImages": ["0x" + "aa" * 32, DIGEST]}
NID = "z6MkfUkTQi31BLQsC47mDaGNNGAwE4N67iacedb1VzADowUs"


def verify_ok(digest: str = DIGEST) -> dict:
    checks = {c: {"ok": True} for c in rc.VERIFY_CHECKS}
    checks["imageDigest"]["detail"] = digest
    return {"passed": True, "checks": checks}


def external_ok(**over) -> dict:
    doc = {"format": rc.EXTERNAL_FORMAT, "mode": "aws", "result": "passed", "commit": SHA, "windowsKind": "production",
           "acceptedImages": ["0x" + "aa" * 32, DIGEST],
           "registration": {"key": READY["external"], "proofType": "tee", "teeType": "amd-sev-snp", "image": DIGEST,
                            "radNode": NID},
           "judged": {"kind": "Counted", "sealed": True, "revealed": True, "counted": True, "pass": True}}
    doc.update(over)
    return doc


def record(**checks) -> dict:
    base = {"integration": {"runs": ["passed"] * 3}, "productionWindows": "passed", "sevSnpValidator": "pending",
            "realModelRun": "pending", "attestedImages": "pending"}
    base.update(checks)
    return {"format": rc.RC_FORMAT, "tag": "v3-rc1", "commit": SHA, "result": "incomplete", "checks": base}


class FakeAws:
    """Records every call; machines start and stop at once."""

    def __init__(self, fail_on: str = "") -> None:
        self.calls: list = []
        self.states = {TC_ID: "stopped", SEV_ID: "stopped"}
        self.user = {SEV_ID: "# the kit's own user data\n"}
        self.fail_on = fail_on
        self.forwards: list = []

    def _note(self, name, *args):
        self.calls.append((name, *args))
        if name == self.fail_on:
            raise A.Stop(f"failed at {name}")

    def start(self, *ids):
        self._note("start", *ids)
        for i in ids:
            self.states[i] = "running"

    def stop(self, *ids):
        self._note("stop", *ids)
        for i in ids:
            self.states[i] = "stopped"

    def state(self, iid):
        return self.states[iid]

    def wait_state(self, iid, want, timeout, every=10, sleep=None):
        self._note("wait_state", iid, want)
        if self.states[iid] != want:
            self.states[iid] = want  # the SEV-SNP host powers itself off; the test chain is started by start()

    def get_user_data(self, iid):
        self._note("get_user_data", iid)
        return self.user[iid]

    def set_user_data(self, iid, text):
        self._note("set_user_data", iid, text)
        self.user[iid] = text

    def console(self, iid):
        self._note("console", iid)
        return ""

    def ssm_online(self, iid):
        return True

    def ssm_run(self, iid, script, timeout=3600, sleep=None):
        self._note("ssm_run", script.split()[2] if len(script.split()) > 2 else script)
        return ""

    def s3_cp(self, src, dst):
        self._note("s3_cp", dst)

    def forward(self, *a):
        self._note("forward", *a)

    def close_forwards(self):
        self._note("close_forwards")


def run_args(**over):
    a = SimpleNamespace(commit="HEAD", yes_start=True, profile="", validator_address=READY["external"],
                        manifest="m.json", snp_measurement="ab" * 48, amd_chain="a.pem", nitro_root="r.pem",
                        record="rec.json", out="", hours=6.0, idle_seconds=3600, wait_seconds="1800", model="",
                        yes_paid_model_run=False, dry_run="")
    for k, v in over.items():
        setattr(a, k, v)
    return a


class TheFlags(unittest.TestCase):
    """Nothing starts without --yes-start, and nothing paid without --yes-paid-model-run after a passed dry run."""

    def no_aws(self):
        return mock.patch.object(A, "Aws", side_effect=AssertionError("an AWS client was made"))

    def test_start_and_run_refuse_without_the_flag_before_any_aws_or_tofu_call(self):
        with self.no_aws(), mock.patch.object(A, "tofu_outputs", side_effect=AssertionError("tofu was read")), \
                mock.patch("sys.stderr"):
            self.assertEqual(A.main(["start"]), 2)
            self.assertEqual(A.main(["run", "HEAD"]), 2)
            self.assertEqual(A.main(["model-run", "HEAD", "--model", "direct:bedrock:x", "--yes-paid-model-run"]), 2)
        fake = FakeAws()
        with self.assertRaisesRegex(A.Stop, "--yes-start"):
            A.aws_run(run_args(yes_start=False), aws=fake)
        with self.assertRaisesRegex(A.Stop, "--yes-start"):
            A.aws_start(SimpleNamespace(yes_start=False, profile=""), aws=fake)
        self.assertEqual(fake.calls, [])

    def test_the_model_run_needs_its_own_flag_and_a_passed_dry_run_of_the_same_commit(self):
        fake = FakeAws()
        with self.assertRaisesRegex(A.Stop, "--yes-paid-model-run"):
            A.aws_run(run_args(model="direct:bedrock:m"), aws=fake)
        with tempfile.TemporaryDirectory() as d:
            dry = Path(d) / "external.json"
            head = rc.resolve("HEAD")
            for doc in (external_ok(commit=head, result="failed"), external_ok(commit=head, mode="local"),
                        external_ok(commit="c" * 40)):
                dry.write_text(json.dumps(doc))
                with self.assertRaisesRegex(A.Stop, "dry-run"):
                    A.aws_run(run_args(model="direct:bedrock:m", yes_paid_model_run=True, dry_run=str(dry)), aws=fake)
            dry.write_text(json.dumps(external_ok(commit=head)))
            with self.assertRaisesRegex(A.Stop, "direct:bedrock"):
                A.aws_run(run_args(model="direct:openai:m", yes_paid_model_run=True, dry_run=str(dry)), aws=fake)
        self.assertEqual(fake.calls, [])

    def test_plan_calls_nothing(self):
        with self.no_aws(), mock.patch.object(A.subprocess, "run", side_effect=AssertionError("a command ran")), \
                mock.patch("sys.stdout") as out:
            self.assertEqual(A.main(["plan"]), 0)
        printed = "".join(str(c.args[0]) for c in out.write.call_args_list)
        self.assertIn("Nothing was started", printed)
        self.assertIn("c6a.xlarge", printed)
        self.assertIn("c6a.large", printed)


class TheStop(unittest.TestCase):
    """Both machines stop on every way out of a run, and the SEV-SNP host's user data is put back."""

    def run_failing(self, fail_on: str = "", raise_in=None):
        fake = FakeAws(fail_on=fail_on)
        outputs = {"instance_id": TC_ID, "bucket": "pof-snp-testchain-x", "private_ip": "10.82.0.10"}
        kit = {"instance_id": SEV_ID, "signing_key_secret_arn": "arn:aws:secretsmanager:us-east-2:0:secret:k",
               "image_digest": DIGEST}
        pre = {"sha": SHA, "manifest": {"image_digest": DIGEST}, "record": Path("rec.json")}
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(A, "tofu_outputs", side_effect=[outputs, kit]), \
                mock.patch.object(A, "preflight", return_value=pre), \
                mock.patch.object(A, "bundle", side_effect=raise_in or (lambda sha, work: [])):
            with self.assertRaises((A.Stop, KeyboardInterrupt, RuntimeError)):
                A.aws_run(run_args(out=d), aws=fake, sleep=lambda s: None)
        return fake

    def assert_stopped(self, fake):
        names = [c[0] for c in fake.calls]
        self.assertIn("start", names)
        stops = [c for c in fake.calls if c[0] == "stop"]
        self.assertEqual(sorted(i for c in stops for i in c[1:]), sorted([TC_ID, SEV_ID]))
        self.assertEqual(fake.states, {TC_ID: "stopped", SEV_ID: "stopped"})
        self.assertEqual(fake.user[SEV_ID], "# the kit's own user data\n")  # restored after the stop
        self.assertLess(names.index("stop"), max(i for i, c in enumerate(fake.calls) if c[0] == "set_user_data"))
        self.assertIn("close_forwards", names)

    def test_a_failure_after_the_start_stops_both(self):
        self.assert_stopped(self.run_failing(fail_on="s3_cp", raise_in=lambda sha, work: ["repo.bundle"]))

    def test_an_interrupt_stops_both(self):
        def interrupt(sha, work):
            raise KeyboardInterrupt
        self.assert_stopped(self.run_failing(raise_in=interrupt))

    def test_an_error_anywhere_stops_both(self):
        def boom(sha, work):
            raise RuntimeError("docker save failed")
        self.assert_stopped(self.run_failing(raise_in=boom))

    def test_a_failed_stop_still_tries_the_other_and_says_so(self):
        fake = FakeAws()
        calls = []

        def stop(*ids):
            calls.append(ids)
            if ids == (TC_ID,):
                raise A.Stop("throttled")
            fake.states[ids[0]] = "stopped"
        fake.stop = stop
        with A.Machines(fake, TC_ID, SEV_ID, sleep=lambda s: None) as m:
            m.start()
            problems = None
        problems = m.stop_all()
        self.assertEqual(calls[:2], [(TC_ID,), (SEV_ID,)])
        self.assertTrue(any("throttled" in p for p in problems))

    def test_sigterm_becomes_an_interrupt_inside_the_run(self):
        fake = FakeAws()
        with self.assertRaises(KeyboardInterrupt):
            with A.Machines(fake, TC_ID, SEV_ID, sleep=lambda s: None) as m:
                m.start()
                os.kill(os.getpid(), __import__("signal").SIGTERM)
        self.assertEqual(fake.states, {TC_ID: "stopped", SEV_ID: "stopped"})


class TheUserData(unittest.TestCase):
    """What the driver gives the SEV-SNP host is the kit's format, and the disk's pof-config.sh reads it as the
    rehearsal's stand-in does."""

    def test_the_kit_s_format_and_the_plan_s_settings(self):
        cfg = A.node_config(READY)
        self.assertEqual(cfg["ORACLE_RPC"], READY["rpc"])
        self.assertEqual(cfg["ORACLE_JUDGE"], "fake")
        for k, v in {"ORACLE_VERSION": "3", "ORACLE_FIX_SOURCE": "radicle", "ORACLE_MERGE_VIA": "radicle",
                     "ORACLE_SEAT_NODES": "chain", "ORACLE_RADICLE_RID": READY["rid"], "ORACLE_IMAGE": DIGEST}.items():
            self.assertEqual(cfg[k], v)
        cmd = A.register_command(READY, 67117025)
        self.assertEqual(cmd, "register --bond 250 --proof tee --tee-type amd-sev-snp --level A --firmware 67117025")
        text = A.user_data("ab12", cmd, READY["seed"], cfg, "arn:aws:secretsmanager:us-east-2:0:secret:k")
        lines = text.splitlines()
        self.assertTrue(lines[0].startswith("# proof-of-fix SEV-SNP validator"))
        self.assertEqual(lines[1:5], ["POF_ATTEST_NONCE=ab12", "POF_POWER_OFF=yes", f"POF_NODE_COMMAND={cmd}",
                                      f"POF_RADICLE_SEED={READY['seed']}"])
        self.assertEqual(lines[-2:], ["ORACLE_PRIVATE_KEY_SECRET_ARN=arn:aws:secretsmanager:us-east-2:0:secret:k",
                                      "AWS_REGION=us-east-2"])
        main = (ROOT / "validator-kit/sevsnp/terraform/main.tf").read_text()
        self.assertIn("# proof-of-fix SEV-SNP validator: data, read by the measured disk's pof-config.sh", main)
        attest = A.user_data("ab12", "run --until-idle 600")
        self.assertNotIn("ORACLE_", attest)  # an attest-only boot: no node settings

    def test_refusals(self):
        with self.assertRaisesRegex(A.Stop, "refuses this node command"):
            A.user_data("ab", "run; reboot")
        with self.assertRaisesRegex(A.Stop, "nonce"):
            A.user_data("XYZ", "run")
        with self.assertRaisesRegex(A.Stop, "would refuse"):
            A.user_data("ab", "run", node={"ORACLE_RPC": "http://xé"})
        with self.assertRaisesRegex(A.Stop, "no rid"):
            A.node_config({**READY, "rid": ""})

    def test_pof_config_sh_reads_it_as_the_stand_in_does(self):
        cfg = A.node_config(READY, extra={"ORACLE_KEYS": "env"})  # a setting the disk fixes: refused by both
        text = A.user_data("ab12", A.register_command(READY, 1), READY["seed"], cfg, "arn:k")
        node, host, refused = A.split_user_data(text)
        self.assertEqual(refused, ["ORACLE_KEYS"])
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "ud").write_text(text)
            bin_ = d / "bin"
            bin_.mkdir()
            (bin_ / "curl").write_text(
                "#!/bin/bash\n"
                "out=''; for ((i=1;i<=$#;i++)); do [[ ${!i} == -o ]] && { j=$((i+1)); out=${!j}; }; done\n"
                f"if [[ -n $out ]]; then cp {d / 'ud'} \"$out\"; printf 200; else printf token; fi\n")
            (bin_ / "curl").chmod(0o755)
            env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "POF_RUN_DIR": str(d / "run")}
            r = subprocess.run(["bash", str(DISK / "rootfs/usr/lib/pof/pof-config.sh")], capture_output=True,
                               text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            disk_node = dict(x.split("=", 1) for x in (d / "run/node.env").read_text().splitlines())
            disk_host = dict(x.split("=", 1) for x in (d / "run/host.env").read_text().splitlines())
            self.assertIn("refused a user-data line for ORACLE_KEYS", r.stdout)
        self.assertEqual(disk_node, node)
        self.assertEqual(disk_host, host)
        self.assertRegex(host["POF_NODE_COMMAND"], A.NODE_COMMAND_RE)
        node_sh = (DISK / "rootfs/usr/lib/pof/pof-node.sh").read_text()
        self.assertIn(r"^(run|info|register|leave|post-table)([[:space:]][A-Za-z0-9\ ._:=/@-]*)?$", node_sh)

    def test_console_facts(self):
        text = (ROOT / "validator-kit/sevsnp/evidence/2026-11-20/console.txt").read_text(errors="replace")
        f = A.console_facts(text)
        self.assertEqual(f["firmware"], 67117025)
        self.assertTrue(f["attested"])
        self.assertEqual(f["nonce"], "12d380b92afa561dc574f865b48d6c80")
        self.assertEqual(f["nid"], "")  # that disk had no Radicle node yet
        later = text + f"[ 30.1] pof-radicle.sh[9]: POF-RADICLE nid {NID}\n[ 61.0] registered 0x{'ab' * 20} as a " \
                       f"candidate (operator ...)\n"
        f = A.console_facts(later)
        self.assertEqual(f["nid"], NID)
        self.assertTrue(f["registered"])


class TheRecordItems(unittest.TestCase):
    """sevSnpValidator and attestedImages pass only for an AWS run of the record's commit with a real SEV-SNP host."""

    def items(self, rec=None, external=None, verify=None, digest=DIGEST):
        return rc.sevsnp_items(rec or record(), external or external_ok(), verify or verify_ok(),
                               {"image_digest": digest}, "evidence/2026-11-22")

    def test_a_real_run_passes_both_and_keeps_the_result_incomplete_until_the_model_run(self):
        new, why = self.items()
        self.assertEqual(why, {"attestedImages": [], "sevSnpValidator": []})
        self.assertEqual(new["checks"]["sevSnpValidator"], "passed")
        self.assertEqual(new["checks"]["attestedImages"], "passed")
        self.assertEqual(new["checks"]["sevSnpValidatorEvidence"], "evidence/2026-11-22")
        self.assertEqual(new["result"], "incomplete")  # realModelRun is still pending
        new, _ = self.items(rec=record(realModelRun="passed"))
        self.assertEqual(new["result"], "passed")

    def test_what_keeps_them_pending(self):
        cases = {
            "a rehearsal": (external_ok(mode="local"), verify_ok(), DIGEST, ["sevSnpValidator"]),
            "another commit": (external_ok(commit="c" * 40), verify_ok(), DIGEST, ["sevSnpValidator"]),
            "a failed external run": (external_ok(result="failed"), verify_ok(), DIGEST, ["sevSnpValidator"]),
            "minute windows": (external_ok(windowsKind="minutes"), verify_ok(), DIGEST, ["sevSnpValidator"]),
            "a simulated proof": (external_ok(registration={**external_ok()["registration"], "proofType": "simulated"}),
                                  verify_ok(), DIGEST, ["sevSnpValidator"]),
            "not on a counted panel": (external_ok(judged={"kind": "Shadow", "sealed": True, "revealed": True,
                                                           "counted": True}), verify_ok(), DIGEST,
                                       ["sevSnpValidator"]),
            "a verify check skipped": (external_ok(), {**verify_ok(), "checks": {
                k: v for k, v in verify_ok()["checks"].items() if k != "snpSignature"}}, DIGEST,
                ["sevSnpValidator", "attestedImages"]),
            "verify failed": (external_ok(), {**verify_ok(), "passed": False}, DIGEST,
                              ["sevSnpValidator", "attestedImages"]),
            "another image": (external_ok(), verify_ok("0x" + "99" * 32), "0x" + "99" * 32,
                              ["sevSnpValidator", "attestedImages"]),
        }
        for what, (external, verify, digest, pending) in cases.items():
            with self.subTest(what):
                new, why = self.items(external=external, verify=verify, digest=digest)
                for item in ("sevSnpValidator", "attestedImages"):
                    self.assertEqual(new["checks"][item], "pending" if item in pending else "passed", (item, why))
                self.assertNotEqual(new["result"], "passed")
                self.assertEqual(new["checks"]["integration"], {"runs": ["passed"] * 3})

    def test_an_item_passed_earlier_stays_and_a_failed_integration_still_fails(self):
        new, _ = self.items(rec=record(sevSnpValidator="passed", attestedImages="passed",
                                       sevSnpValidatorEvidence="evidence/earlier"), external=external_ok(mode="local"))
        self.assertEqual(new["checks"]["sevSnpValidator"], "passed")
        self.assertEqual(new["checks"]["sevSnpValidatorEvidence"], "evidence/earlier")
        bad = record()
        bad["checks"]["integration"]["runs"] = ["passed", "failed"]
        new, _ = self.items(rec=bad)
        self.assertEqual(new["result"], "failed")

    def test_write_items_checks_the_console_s_radicle_node_and_the_model_run(self):
        with tempfile.TemporaryDirectory() as d:
            rec = Path(d) / "rc.json"
            rec.write_text(json.dumps(record()))
            problems = A.write_items(rec, external_ok(), verify_ok(), {"image_digest": DIGEST}, "ev", nid="z6Mkother")
            doc = json.loads(rec.read_text())
            self.assertEqual(doc["checks"]["sevSnpValidator"], "pending")
            self.assertTrue(any("Radicle node" in p for p in problems))
            self.assertEqual(doc["checks"]["attestedImages"], "passed")
            rec.write_text(json.dumps(record()))
            self.assertEqual(A.write_items(rec, external_ok(), verify_ok(), {"image_digest": DIGEST}, "ev", nid=NID,
                                           model="direct:bedrock:m"), [])
            doc = json.loads(rec.read_text())
            self.assertEqual([doc["checks"][c] for c in ("sevSnpValidator", "attestedImages", "realModelRun")],
                             ["passed"] * 3)
            self.assertEqual(doc["result"], "passed")
            # the deploy script's reader accepts it only when every item passed (scripts/deploy_sepolia.py)
            self.assertEqual(doc["checks"]["realModelRunModel"], "direct:bedrock:m")


class ThePlan(unittest.TestCase):
    def test_six_hours_cost_about_a_dollar_and_a_half(self):
        est = A.estimate(6)
        self.assertEqual([m["type"] for m in est["machines"]], ["c6a.xlarge", "c6a.large"])
        self.assertAlmostEqual(est["totalUsd"], 1.52, delta=0.05)
        sev = next(x for x in est["lines"] if x["what"].startswith("SEV-SNP host"))
        self.assertAlmostEqual(sev["rate"], A.PRICES["c6a.large"] * 1.10)
        with_model = A.estimate(6, model_run=True)
        self.assertAlmostEqual(with_model["totalUsd"] - est["totalUsd"], A.MODEL_RUN_USD, delta=0.011)
        self.assertLess(A.estimate(6, sevsnp_hours=2)["totalUsd"], est["totalUsd"])
        with self.assertRaises(A.Stop):
            A.estimate(6, sevsnp_hours=7)

    def test_the_images_it_ships_are_pinned(self):
        images = A.remote_images()
        for k in ("foundry", "python", "test"):
            self.assertRegex(images[k], r"@sha256:[0-9a-f]{64}$", k)
        dockerfile = (ROOT / "spikes/radicle/Dockerfile").read_text()
        self.assertIn("radicle-1.10.3-x86_64-unknown-linux-musl.tar.xz", dockerfile)
        self.assertIn("ADD --checksum=sha256:", dockerfile)
        devnet = (ROOT / "scripts/devnet.sh").read_text()
        self.assertIn(images["foundry"], devnet)  # the same Foundry as the devnet and CI's contract runs


class TheTestChainModule(unittest.TestCase):
    """validator-kit/sevsnp/testchain's static checks (the kit's tests read its Terraform the same way)."""

    def tf(self) -> str:
        return "\n".join(p.read_text() for p in sorted(TC.glob("*.tf")))

    def test_gated_and_shaped_as_decided(self):
        variables = (TC / "variables.tf").read_text()
        self.assertRegex(variables, r'variable "create_instance" \{[^}]*default\s*=\s*false', "nothing launched")
        self.assertRegex(variables, r'variable "instance_type" \{[^}]*default\s*=\s*"c6a.xlarge"')
        self.assertRegex(variables, r'variable "region" \{[^}]*default\s*=\s*"us-east-2"')
        self.assertRegex(variables, r'(?s)variable "autostop_hours" \{.*?default\s*=\s*8\n', "a hard stop after 8 h")
        main = (TC / "main.tf").read_text()
        self.assertIn('count                                = var.create_instance ? 1 : 0', main)
        self.assertIn('http_tokens                 = "required"', main)
        self.assertRegex(main, r'root_block_device \{[^}]*volume_type\s*=\s*"gp3"[^}]*encrypted\s*=\s*true')
        self.assertIn("AmazonSSMManagedInstanceCore", main)
        self.assertIn('instance_initiated_shutdown_behavior = "stop"', main)

    def test_no_ssh_no_internet_ingress(self):
        tf = self.tf()
        self.assertNotIn("key_name", tf)
        self.assertNotIn("aws_key_pair", tf)
        ingress = re.findall(r'resource "aws_vpc_security_group_ingress_rule" "(\w+)" \{(.*?)\n\}', tf, re.S)
        self.assertEqual([n for n, _ in ingress], ["from_sevsnp"])
        body = ingress[0][1]
        self.assertIn("referenced_security_group_id = data.aws_security_group.kit_node.id", body)
        self.assertNotIn("cidr", body)
        self.assertNotIn("ingress {", tf)
        self.assertIn("rpc = var.rpc_port, seed = var.seed_port", tf)
        # the kit's group gains egress to this host's group only, on the RPC port
        self.assertRegex(tf, r'"sevsnp_to_rpc" \{[^}]*security_group_id\s*=\s*data.aws_security_group.kit_node.id[^}]*'
                             r'referenced_security_group_id = aws_security_group.testchain.id')

    def test_the_hard_stop_and_the_budget(self):
        tf = self.tf()
        self.assertIn('schedule_expression = "rate(10 minutes)"', tf)
        self.assertIn('variable = "aws:ResourceTag/pof:kit"', tf)
        self.assertIn('"pof:kit" = "validator-kit/sevsnp"', (TC / "versions.tf").read_text())
        self.assertIn('"pof:kit" = "validator-kit/sevsnp"', (ROOT / "validator-kit/sevsnp/terraform/versions.tf")
                      .read_text())  # the SEV-SNP host carries the tag the auto-stop may stop
        self.assertIn('resource "aws_budgets_budget" "monthly"', tf)
        self.assertIn('action_sub_type = "STOP_EC2_INSTANCES"', tf)
        ud = (TC / "user-data.yaml.tftpl").read_text()
        self.assertIn("ExecStart=/usr/sbin/shutdown -h +${autostop_minutes}", ud)
        self.assertIn("containerd-snapshotter", (TC / "daemon.json").read_text())

    def test_no_account_id_is_written_down(self):
        for p in [*TC.glob("*.tf"), TC / "rc-remote.sh", TC / "lambda/autostop.py", ROOT / "scripts/rc_aws.py",
                  ROOT / "scripts/rc-aws.sh", ROOT / "tests/integration/external_v3.py"]:
            self.assertIsNone(re.search(r"(?<![0-9a-fA-F])\d{12}(?![0-9a-fA-F])", p.read_text()), p.name)
        self.assertIn("data.aws_caller_identity.current.account_id", self.tf())

    def test_the_remote_side_checks_what_it_receives(self):
        sh = (TC / "rc-remote.sh").read_text()
        self.assertIn('[[ "$(git -C repo rev-parse HEAD)" == "$sha" ]]', sh)
        self.assertIn('sha256sum -c --quiet', sh)
        self.assertIn('doc["ids"][name]', sh)
        self.assertIn("POF_EXT_MODE=aws", sh)
        self.assertIn("POF_V3_EXTERNAL=", sh)
        self.assertIn("scripts/integration.sh --release-candidate $sha --external", sh)
        r = subprocess.run(["bash", "-n", str(TC / "rc-remote.sh")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = subprocess.run(["bash", str(TC / "rc-remote.sh"), "start", "HEAD", "x", "y", "z"], capture_output=True,
                           text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("not a commit SHA", r.stderr)

    def test_tofu_fmt_when_installed(self):
        if not subprocess.run(["sh", "-c", "command -v tofu"], capture_output=True).stdout:
            self.skipTest("tofu isn't installed here")
        r = subprocess.run(["tofu", "fmt", "-check", "-diff", str(TC)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class TheAutostop(unittest.TestCase):
    def test_only_running_instances_past_their_hours(self):
        now = dt.datetime(2026, 11, 22, 12, 0, tzinfo=dt.timezone.utc)
        inst = [{"InstanceId": "i-a", "State": {"Name": "running"}, "LaunchTime": now - dt.timedelta(hours=8, minutes=1)},
                {"InstanceId": "i-b", "State": {"Name": "running"}, "LaunchTime": now - dt.timedelta(hours=7)},
                {"InstanceId": "i-c", "State": {"Name": "stopped"}, "LaunchTime": now - dt.timedelta(hours=30)},
                {"InstanceId": "i-d", "State": {"Name": "running"}, "LaunchTime": "2026-11-22T03:00:00Z"}]
        self.assertEqual(autostop.overdue(inst, now, 8), ["i-a", "i-d"])

    def test_the_handler_filters_by_the_kit_s_tag(self):
        ec2 = mock.Mock()
        now = dt.datetime(2026, 11, 22, 12, 0, tzinfo=dt.timezone.utc)
        ec2.describe_instances.return_value = {"Reservations": [{"Instances": [
            {"InstanceId": "i-a", "State": {"Name": "running"}, "LaunchTime": now - dt.timedelta(hours=9)}]}]}
        with mock.patch.dict(os.environ, {"MAX_HOURS": "8"}), mock.patch("builtins.print"):
            out = autostop.handler(ec2=ec2, now=now)
        self.assertEqual(out["stopped"], ["i-a"])
        filters = ec2.describe_instances.call_args.kwargs["Filters"]
        self.assertIn({"Name": "tag:pof:kit", "Values": ["validator-kit/sevsnp"]}, filters)
        ec2.stop_instances.assert_called_once_with(InstanceIds=["i-a"])


class TheExternalSet(unittest.TestCase):
    """tests/integration/external_v3.py's settings and its ready.json, without Docker."""

    @classmethod
    def setUpClass(cls):
        cls.X = load("external_v3_under_test", ROOT / "tests/integration/external_v3.py")

    def test_aws_mode_needs_the_bind_address_and_the_outside_key(self):
        X = self.X
        with self.assertRaises(SystemExit):
            X.settings({"POF_EXT_MODE": "aws", "POF_V3_EXTERNAL": READY["external"]})
        with self.assertRaises(SystemExit):
            X.settings({"POF_EXT_MODE": "aws", "POF_EXT_BIND": "10.82.0.10"})
        with self.assertRaises(SystemExit):
            X.settings({"POF_EXT_MODE": "aws", "POF_EXT_BIND": "10.82.0.10",
                        "POF_V3_EXTERNAL": READY["external"] + ",0x" + "cd" * 20})
        with self.assertRaises(SystemExit):
            X.settings({"POF_EXT_MODE": "elsewhere"})
        s = X.settings({"POF_EXT_MODE": "aws", "POF_EXT_BIND": "10.82.0.10", "POF_V3_EXTERNAL": READY["external"],
                        "POF_EXT_IMAGE": DIGEST})
        self.assertEqual((s["proof"], s["tee"], s["image"]), ("tee", "amd-sev-snp", DIGEST))
        local = X.settings({})
        self.assertEqual((local["mode"], local["proof"], local["image"]), ("local", "simulated", X.REHEARSAL_IMAGE))

    def test_ready_json_points_the_sevsnp_host_at_the_published_ports(self):
        X = self.X
        s = X.settings({"POF_EXT_MODE": "aws", "POF_EXT_BIND": "10.82.0.10", "POF_V3_EXTERNAL": READY["external"],
                        "POF_EXT_IMAGE": DIGEST})
        rec = {"chainId": 31337, "race": READY["race"], "registry": READY["registry"], "windowsKind": "production",
               "images": READY["acceptedImages"]}
        doc = X.ready_doc(s, rec, READY["rid"], "z6Mkseed", READY["external"], "http://127.0.0.1:1")
        self.assertEqual((doc["rpc"], doc["seed"]), ("http://10.82.0.10:8545", "z6Mkseed@10.82.0.10:8776"))
        self.assertEqual(doc["format"], A.FORMATS["ready"])
        self.assertNotIn("local", doc)
        self.assertEqual(A.node_config(doc)["ORACLE_RPC"], "http://10.82.0.10:8545")  # the driver reads it as is
        loc = X.ready_doc(X.settings({}), rec, READY["rid"], "z6Mkseed", READY["external"], "http://127.0.0.1:1",
                          sim="http://127.0.0.1:2", network="pof251x-edge")
        self.assertEqual((loc["rpc"], loc["seed"]), ("http://127.0.0.1:1", "z6Mkseed@seed:8776"))
        self.assertEqual(loc["local"]["network"], "pof251x-edge")

    def test_the_six_and_the_outside_family(self):
        X = self.X
        self.assertEqual(X.HARNESS, ["genesis", "v1", "v2", "v3", "v4", "v5"])
        self.assertEqual(X.PAUSED, ["v2", "v3", "v4", "v5"])
        self.assertEqual(X.EXTERNAL_FAMILY, "fake-6")


class TheReleaseCandidateExternalMode(unittest.TestCase):
    def test_external_only_writes_no_record_and_exits_by_the_result(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(rc, "checkout", return_value=Path(d) / "wt"), \
                mock.patch.object(rc, "drop") as drop, \
                mock.patch.object(rc, "record", side_effect=AssertionError("a record was written")), \
                mock.patch("builtins.print"):
            with mock.patch.object(rc, "external_run", return_value={"result": "passed"}) as run:
                self.assertEqual(rc.main(["HEAD", "--external", "--logs", d]), 0)
            env = run.call_args.args[2]
            self.assertEqual(env["DEVNET_V3_WINDOWS"], "production")
            with mock.patch.object(rc, "external_run", return_value={"result": "failed"}):
                self.assertEqual(rc.main(["HEAD", "--external", "--logs", d]), 1)
            self.assertEqual(drop.call_count, 2)
            with mock.patch.dict(os.environ, {"DEVNET_V3_WINDOWS": "minutes"}), mock.patch("sys.stderr"):
                self.assertEqual(rc.main(["HEAD", "--external", "--logs", d]), 2)  # minute windows refused


class TheBundle(unittest.TestCase):
    """The commit's bundle: the host clones it plainly (rc-remote.sh provision: `git clone repo.bundle repo`, then a
    detached checkout of the SHA), so the commit must come with that clone (the first AWS run of 2026-11-22 failed:
    its ref outside refs/heads/ left the clone without it)."""

    def test_a_plain_clone_of_the_bundle_checks_the_commit_out(self):
        real = subprocess.run

        def run(argv, *a, **kw):  # git for real; docker and tar (images and solc) aren't this test's
            if argv[0] == "git":
                return real(argv, *a, **kw)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "src"  # a repository of its own: CI checks this one out shallow (--depth 1)
            git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-C", str(src)]
            real(["git", "init", "-q", str(src)], check=True)
            for i in range(2):
                (src / "f").write_text(str(i))
                real([*git, "add", "f"], check=True)
                real([*git, "commit", "-q", "-m", str(i)], check=True)
            sha = real([*git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
            work = Path(d) / "work"
            work.mkdir()
            with unittest.mock.patch.object(A, "ROOT", src), unittest.mock.patch.object(A, "remote_images", lambda: {}), \
                    unittest.mock.patch.object(A.subprocess, "run", run):
                A.bundle(sha, work)
            real(["git", "clone", "-q", str(work / "repo.bundle"), str(work / "repo")], check=True, capture_output=True)
            real(["git", "-C", str(work / "repo"), "checkout", "-q", "--detach", sha], check=True, capture_output=True)
            head = real(["git", "-C", str(work / "repo"), "rev-parse", "HEAD"], capture_output=True, text=True).stdout
            self.assertEqual(head.strip(), sha)
            left = real([*git, "for-each-ref", "refs/heads/pof-rc-aws-*"], capture_output=True, text=True)
            self.assertEqual(left.stdout.strip(), "")  # the temporary branch is removed

class TheBootConsole(unittest.TestCase):
    """A Nitro instance's console can't be read once it has stopped (2026-11-22: the header only), so the attest and
    register boots stay up (POF_POWER_OFF=no) and the driver reads the console while the host runs, then stops it."""

    def test_the_console_is_read_while_running_then_the_host_stops(self):
        text = (ROOT / "validator-kit/sevsnp/evidence/2026-11-22/console.txt").read_text(errors="replace")
        fake = FakeAws()
        fake.states[SEV_ID] = "running"
        answers = iter(["", "", text])
        fake.console = lambda iid: next(answers)
        got = A.booted_console(fake, SEV_ID, A._attest_facts, "the attest boot", sleep=lambda s: None)
        self.assertEqual(got, text)
        self.assertEqual([c[0] for c in fake.calls], ["stop", "wait_state"])
        self.assertEqual(fake.states[SEV_ID], "stopped")

    def test_a_console_that_never_attests_still_stops_the_host(self):
        fake = FakeAws()
        fake.states[SEV_ID] = "running"
        with self.assertRaises(A.Stop):
            A.booted_console(fake, SEV_ID, A._attest_facts, "the attest boot", sleep=lambda s: None, timeout=-1)
        self.assertEqual(fake.states[SEV_ID], "stopped")

    def test_the_attest_boot_keeps_the_host_up(self):
        fake = TheStop().run_failing(fail_on="s3_cp", raise_in=lambda sha, work: ["repo.bundle"])
        attest = next(c[2] for c in fake.calls if c[0] == "set_user_data" and "POF_ATTEST_NONCE" in c[2])
        self.assertIn("POF_POWER_OFF=no", attest)


class TheModelRunCaps(unittest.TestCase):
    def test_the_call_cap_leaves_room_to_qualify_and_judge(self):
        # the node's call cap is per process: the outside validator must judge QUALIFY_VERDICTS shadow seats to
        # qualify, then its counted seat (the 2026-11-22 model run at 20 calls could never finish)
        src = (ROOT / "contracts/src/v3/Validators.sol").read_text()
        need = int(re.search(r"QUALIFY_VERDICTS = (\d+);", src).group(1))
        self.assertGreaterEqual(int(A.MODEL_MAX_CALLS), 2 * need)


if __name__ == "__main__":
    unittest.main()
