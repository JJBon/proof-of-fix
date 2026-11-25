"""The proof-of-fix seed's configuration (#251 design L14, task 5.3; seed/): the Radicle config blocks by default, the
release is pinned by checksum like the spike's, the RID comes only from the publication record, and the Terraform
opens TCP 8776 only, starts nothing by default and names no account. The seed itself runs on the internal Docker
network in `scripts/radicle-spike.sh --seed` (tests/integration/seed_radicle.py); these tests need neither Docker
nor AWS."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "seed"
TF = SEED / "terraform"
sys.path.insert(0, str(SEED))

import publication as P  # noqa: E402

RID = "rad:z3J1a5kbxcmH3HsidfHN7Y9qLfyDa"
GOOD = {"format": "pof-radicle-publication/1", "rid": RID, "rootCommit": "3d6e2bd9af5614f80081bb32659c2134210255e5",
        "nodeId": "z6MkpoVRATTagGk5Pkew9ynXS1d2rMgLUpHtteMihAsbWZe3", "radicle": "1.10.3"}


def seed_files():
    return [p for p in SEED.rglob("*") if p.is_file() and ".terraform" not in p.parts and "__pycache__" not in p.parts]


class TheRadicleConfig(unittest.TestCase):
    def test_block_by_default_and_listening_on_8776(self):
        cfg = json.loads((SEED / "radicle/config.json").read_text())
        node = cfg["node"]
        self.assertEqual(node["seedingPolicy"], {"default": "block"})
        self.assertEqual(node["listen"], ["0.0.0.0:8776"])
        self.assertEqual(node["externalAddresses"], ["@EXTERNAL_ADDRESS@"])
        self.assertEqual((node["alias"], node["network"]), ("@ALIAS@", "@NETWORK@"))
        self.assertEqual(cfg["preferredSeeds"], [])
        text = (SEED / "radicle/config.json").read_text()
        self.assertEqual(sorted(set(re.findall(r"@[A-Z_]+@", text))), ["@ALIAS@", "@EXTERNAL_ADDRESS@", "@NETWORK@"])
        self.assertNotIn("$", text)  # also Terraform-safe

    def test_the_setup_seeds_one_rid_and_unseeds_the_rest(self):
        setup = (SEED / "radicle/seed-setup.sh").read_text()
        for needed in ('rad seed "$rid" --scope all --no-fetch', 'rad unseed "$other"', '[[ "$seeded" == "$rid " ]]',
                       "rad node status", 'RAD_PASSPHRASE="" rad auth'):
            self.assertIn(needed, setup)

    @unittest.skipUnless(shutil.which("bash"), "bash isn't installed")
    def test_the_setup_refuses_bad_input_before_touching_radicle(self):
        with tempfile.TemporaryDirectory() as t:
            env = dict(os.environ, RAD_HOME=t, PATH="/usr/bin:/bin")  # no rad on this PATH: it must not be reached
            for args in (["rad:bad0", "seed", "203.0.113.7:8776"], [RID, "a b", "203.0.113.7:8776"],
                         [RID, "seed", "203.0.113.7"], [RID, "seed", "x;y:8776"], [RID, "seed", "h:8776", "prod"],
                         []):
                r = subprocess.run(["bash", str(SEED / "radicle/seed-setup.sh"), *args], env=env, capture_output=True,
                                   text=True, timeout=30)
                self.assertEqual(r.returncode, 2, (args, r.stderr))
                self.assertIn("seed-setup:", r.stderr)
            self.assertEqual(os.listdir(t), [])

    def test_the_service(self):
        unit = (SEED / "radicle/radicle-seed.service").read_text()
        self.assertRegex(unit, r"(?m)^ExecStart=/usr/local/bin/radicle-node( |$)")
        for needed in ("User=radicle", "Environment=RAD_HOME=/var/lib/radicle/home", "Restart=always",
                       "NoNewPrivileges=yes", "ProtectSystem=strict", "ReadWritePaths=/var/lib/radicle",
                       "RequiresMountsFor=/var/lib/radicle"):
            self.assertIn(needed, unit)


class TheRelease(unittest.TestCase):
    def test_pinned_like_the_spike_and_checked_before_unpacking(self):
        dockerfile = (ROOT / "spikes/radicle/Dockerfile").read_text()
        self.assertIn("releases/1.10.3/radicle-1.10.3-x86_64-unknown-linux-musl.tar.xz", dockerfile)
        self.assertIn("7e1cb406bb935c3de008d2171e8961f57b4336ea", (TF / "main.tf").read_text())
        main = (TF / "main.tf").read_text()
        self.assertIn('radicle_version = "1.10.3"', main)
        self.assertIn('radicle_target  = "aarch64-unknown-linux-musl"', main)
        self.assertRegex(main, r'radicle_sha256  = "822c1ea1da7dd3a2a7f98da6d93b95359b5b9b0e302b8535bea377a2441e596f"')
        self.assertEqual(P.RADICLE, "1.10.3")
        install = (SEED / "radicle/install.sh").read_text()
        check = install.index("sha256sum --check")
        self.assertLess(check, install.index("tar -xJf"))
        self.assertLess(check, install.index("install -m 0755"))
        self.assertIn("--proto '=https'", install)


class ThePublicationRecord(unittest.TestCase):
    def test_a_good_record(self):
        self.assertEqual(P.check(dict(GOOD))["rid"], RID)
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "publication.json"
            path.write_text(json.dumps(GOOD))
            self.assertEqual(P.rid(path), RID)
            r = subprocess.run([sys.executable, str(SEED / "publication.py"), "rid", str(path)], capture_output=True,
                               text=True, timeout=30)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, RID))

    def test_what_is_refused(self):
        for change in ({"format": "pof-radicle-publication/2"}, {"rid": "rad:bad0"}, {"rid": None},
                       {"rootCommit": "abc"}, {"nodeId": "did:key:z6Mk"}, {"radicle": "1.10.2"}):
            with self.assertRaises(P.Refused, msg=change):
                P.check(dict(GOOD, **change))
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "publication.json"
            path.write_text("{not json")
            with self.assertRaises(P.Refused):
                P.rid(path)
            r = subprocess.run([sys.executable, str(SEED / "publication.py"), "rid", str(path)], capture_output=True,
                               text=True, timeout=30)
            self.assertEqual(r.returncode, 2)

    def test_no_rid_is_written_before_the_publish(self):
        for path in seed_files():
            self.assertIsNone(re.search(r"rad:z[1-9A-HJ-NP-Za-km-z]{20,}", path.read_text(errors="replace")), path)


class TheTerraform(unittest.TestCase):
    def tf(self, name):
        return (TF / name).read_text()

    def test_nothing_billed_by_default(self):
        self.assertRegex(self.tf("variables.tf"), r'variable "create_instance" \{[^}]*default     = false')
        main = self.tf("main.tf")
        for res in ("aws_instance", "aws_ebs_volume", "aws_eip", "aws_volume_attachment", "aws_eip_association"):
            blocks = re.findall(r'resource "%s" "\w+" \{\n([^\n]*)' % res, main)
            self.assertTrue(blocks, res)
            for first in blocks:
                self.assertRegex(first, r"^\s+count\s+= var\.create_instance \? 1 : 0$", res)
        self.assertIn('default     = "us-east-2"', self.tf("variables.tf"))
        self.assertIn('default     = "t4g.micro"', self.tf("variables.tf"))

    def test_inbound_8776_only_and_no_ssh(self):
        network = self.tf("network.tf")
        ingress = re.findall(r'resource "aws_vpc_security_group_ingress_rule" "(\w+)" \{(.*?)\n\}', network, re.S)
        self.assertEqual([name for name, _ in ingress], ["radicle"])
        self.assertIn("from_port         = 8776", ingress[0][1])
        self.assertIn("to_port           = 8776", ingress[0][1])
        self.assertNotIn("ingress {", network)
        for path in TF.glob("*.tf*"):
            text = path.read_text()
            self.assertNotRegex(text, r"(port\s*=\s*22\b|key_name|aws_key_pair)", path.name)
        self.assertNotIn("aws_nat_gateway", network)
        self.assertIn("map_public_ip_on_launch = false", network)

    def test_encrypted_gp3_imdsv2_standard_credits(self):
        main = self.tf("main.tf")
        self.assertEqual(len(re.findall(r"encrypted\s+= true", main)), 2)
        self.assertEqual(len(re.findall(r'(volume_)?type\s+= "gp3"', main)), 2)
        self.assertIn('http_tokens                 = "required"', main)
        self.assertIn('cpu_credits = "standard"', main)

    def test_least_privilege(self):
        main = self.tf("main.tf")
        self.assertNotIn("policy_arn", main)  # no managed policy: Session Manager's actions only
        actions = re.findall(r'"((?:ssm|ssmmessages|ec2messages|s3|kms|secretsmanager|ec2):\w+)"', main)
        self.assertEqual(sorted(actions), sorted(["ssm:UpdateInstanceInformation", "ssmmessages:CreateControlChannel",
                                                  "ssmmessages:CreateDataChannel", "ssmmessages:OpenControlChannel",
                                                  "ssmmessages:OpenDataChannel", "secretsmanager:GetSecretValue"]))
        self.assertIn("count  = var.ssm_access ? 1 : 0", main)
        # The keeper's secrets (2026-11-23): GetSecretValue on exactly the listed ARNs, and no policy when none are.
        keeper = main[main.index('data "aws_iam_policy_document" "keeper"'):main.index('resource "aws_iam_instance_profile"')]
        self.assertIn("resources = var.keeper_secret_arns", keeper)
        self.assertEqual(len(re.findall(r"count\s+= length\(var\.keeper_secret_arns\) > 0 \? 1 : 0", keeper)), 2)
        variables = self.tf("variables.tf")
        self.assertIn(r'regex("^arn:aws:secretsmanager:[a-z0-9-]+:[0-9]{12}:secret:', variables)

    def test_the_example_keeps_the_instance(self):
        """A plan without create_instance = true destroys the seed: the example sets it, and the state and the real
        tfvars are git-ignored."""
        example = self.tf("seed.tfvars.example")
        self.assertRegex(example, r"(?m)^create_instance = true$")
        self.assertRegex(example, r"(?m)^ssm_access\s+= true$")
        ignore = self.tf(".gitignore").splitlines()
        for pattern in ("*.tfstate*", "*.tfvars", "*.tfvars.*", "!*.tfvars.example", "*.plan"):
            self.assertIn(pattern, ignore)

    def test_a_budget_with_alerts_and_no_stop(self):
        budget = self.tf("budget.tf")
        self.assertIn('resource "aws_budgets_budget" "monthly"', budget)
        self.assertIn('[["ACTUAL", 80], ["FORECASTED", 100]]', budget)
        self.assertNotIn("aws_budgets_budget_action", budget)

    def test_the_rid_comes_from_the_record(self):
        main = self.tf("main.tf")
        self.assertIn("jsondecode(file(var.publication_record))", main)
        self.assertIn('"pof-radicle-publication/1"', main)
        self.assertIn("rid              = local.rid", main)

    def test_the_user_data_gets_every_template_variable(self):
        tpl = self.tf("user-data.yaml.tftpl")
        main = self.tf("main.tf")
        call = main[main.index("templatefile("):]
        call = call[:call.index("})")]
        self.assertEqual(set(re.findall(r"\$\{(\w+)\}", tpl)), set(re.findall(r"^\s+(\w+)\s+=", call, re.M)))
        for name in ("install.sh", "seed-setup.sh", "config.json", "radicle-seed.service"):
            self.assertIn(f'file("${{path.module}}/../radicle/{name}")', main)
            self.assertIn(f"/usr/local/lib/radicle-seed/{name}", tpl)
        install = (SEED / "radicle/install.sh").read_text()
        for key in re.findall(r"^      (\w+)=", tpl, re.M):
            self.assertIn(key, install)

    def test_no_account_specific_values(self):
        """The folder goes into the public snapshot (task 5.2): no account IDs, profiles, ARNs with an account, or
        e-mail addresses; every such value is a variable."""
        for path in seed_files():
            if path.name == ".terraform.lock.hcl":
                continue
            text = path.read_text(errors="replace")
            self.assertNotRegex(text, r"(?<![0-9a-f])\d{12}(?![0-9a-f])", path)
            self.assertNotRegex(text, r"arn:aws:[a-z0-9-]+:[a-z0-9-]*:\d{12}:", path)
            self.assertNotRegex(text, r"(?m)^\s*profile\s*=", path)
            self.assertNotRegex(text, r"[A-Za-z0-9._%+-]+@(?!example\.(?:org|com)\b)[A-Za-z0-9-]+\.[A-Za-z]{2,}", path)


if __name__ == "__main__":
    unittest.main()
