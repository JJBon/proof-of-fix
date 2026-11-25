"""#253's SEV-SNP kit and #251 L21's measured disk (validator-kit/sevsnp): the disk's build pins every input, its boot
reads the user data as data only, the Terraform launches SEV-SNP with NitroTPM and nothing by default, and the verifier
checks a boot's evidence against the build. The disk itself is built and booted by scripts/checker-disk.sh (Docker),
and on AWS by validator-kit/SEVSNP-PLAN.md; these tests need neither."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KIT = ROOT / "validator-kit/sevsnp"
DISK = KIT / "disk"

spec = importlib.util.spec_from_file_location("sevsnp_verify", KIT / "verify.py")
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)


class TheDiskBuild(unittest.TestCase):
    def test_every_input_is_pinned(self):
        text = (DISK / "Dockerfile").read_text()
        froms = re.findall(r"^FROM (\S+)", text, re.M)
        for f in froms:
            self.assertTrue(f in ("debian", "tools", "scratch") or re.match(r"^[a-z]+@sha256:[0-9a-f]{64}$", f), f)
        adds = re.findall(r"^ADD (.*)$", text, re.M)
        self.assertTrue(adds)
        for a in adds:
            self.assertRegex(a, r"^--checksum=sha256:[0-9a-f]{64} ")
        self.assertIn("snapshot.debian.org/archive/debian/${SNAPSHOT}", text)
        self.assertNotIn("apt-get upgrade", text)
        self.assertIn("cargo build --locked", text)

    def test_the_root_hash_is_on_the_measured_command_line(self):
        text = (DISK / "mkdisk.sh").read_text()
        self.assertIn('CMDLINE="console=ttyS0,115200n8 root=/dev/mapper/root rootfstype=erofs ro roothash=$ROOTHASH"', text)
        for needed in ("systemd.verity_root_data=", "systemd.verity_root_hash=", "panic-on-corruption",
                       "systemd.volatile=overlay", "--salt=", "--uuid=", "--reproducible", "--invariant",
                       "nitro-tpm-pcr-compute --image", "ukify build"):
            self.assertIn(needed, text)
        for opt in ("SEV_GUEST", "TCG_CRB", "DM_VERITY", "EROFS_FS", "ENA_ETHERNET", "BLK_DEV_NVME"):
            self.assertIn(opt, text)

    def test_nothing_is_pulled_and_the_store_starts_empty(self):
        daemon = json.loads((DISK / "rootfs/etc/docker/daemon.json").read_text())
        self.assertEqual(daemon["registry-mirrors"], [])
        self.assertTrue(daemon["features"]["containerd-snapshotter"])  # keeps each archive's digest
        self.assertTrue(daemon["data-root"].startswith("/data/scratch/"))
        self.assertIn('root = "/data/scratch/containerd"', (DISK / "rootfs/etc/containerd/config.toml").read_text())
        data = (DISK / "rootfs/usr/lib/pof/pof-data.sh").read_text()
        self.assertIn("rm -rf --one-file-system /data/scratch", data)
        images = (DISK / "rootfs/usr/lib/pof/pof-images.sh").read_text()
        self.assertIn("docker load -q -i", images)
        self.assertNotIn("docker pull", images)
        for script in (DISK / "rootfs/usr/lib/pof").glob("*.sh"):
            self.assertNotIn("docker pull", script.read_text(), script.name)

    def test_the_node_runs_in_attested_mode_only_after_the_boot_attested(self):
        node = (DISK / "rootfs/usr/lib/pof/pof-node.sh").read_text()
        for needed in ("-e ORACLE_ATTESTED_IMAGES=/etc/pof/images.json", "-e ORACLE_SANDBOX=api", "-e ORACLE_KEYS=snp",
                       "--device /dev/sev-guest", "/run/pof/attest-ok", '"$NODE_IMAGE" $cmd'):
            self.assertIn(needed, node)
        for never in ("--privileged", "--network host", "--pid host", ". /run/pof/host.env", "source /run/pof"):
            self.assertNotIn(never, node)
        attest = (DISK / "rootfs/usr/lib/pof/pof-attest.sh").read_text()
        for needed in ("snp-report --data", "nitro-tpm-attest --user-data", "attested-check", "pof-boot-attestation/1"):
            self.assertIn(needed, attest)

    def test_no_shell_on_the_host(self):
        text = (DISK / "Dockerfile").read_text()
        self.assertIn("getty.target serial-getty@ttyS0.service", text)
        for never in ("openssh-server", "amazon-ssm-agent", "cloud-init"):
            self.assertNotIn(f" {never}", text.split("FROM debian AS tools")[0].split("FROM debian AS rootfs")[1])

    @unittest.skipUnless(shutil.which("bash") and shutil.which("python3"), "needs bash")
    def test_the_user_data_is_data(self):
        """pof-config.sh with a fake IMDS (a curl stub): settings pass, what the disk fixes and secrets' values don't,
        and nothing in it is ever run."""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            marker = d / "ran"
            user_data = "\n".join([
                "# a comment", "ORACLE_RPC=https://rpc.example/x", "ORACLE_VERSION=3",
                "ORACLE_PRIVATE_KEY_SECRET_ARN=arn:aws:secretsmanager:us-east-2:1:secret:k",
                "ORACLE_ATTESTED_IMAGES=/tmp/other.json", "ORACLE_SANDBOX=cli", "ORACLE_KEYS=env",
                "ORACLE_PRIVATE_KEY=0x" + "11" * 32, "RPC_API_KEY=secret", "PATH=/evil",
                f"POF_NODE_COMMAND=$(touch {marker})", "POF_POWER_OFF=no", "POF_OTHER=1",
                "ORACLE_JUDGE=direct:bedrock:x`touch " + str(marker) + "`"])
            (d / "ud").write_text(user_data)
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
            node = (d / "run/node.env").read_text().splitlines()
            host = (d / "run/host.env").read_text().splitlines()
            self.assertEqual(node, ["ORACLE_RPC=https://rpc.example/x", "ORACLE_VERSION=3",
                                    "ORACLE_PRIVATE_KEY_SECRET_ARN=arn:aws:secretsmanager:us-east-2:1:secret:k",
                                    "ORACLE_JUDGE=direct:bedrock:x`touch " + str(marker) + "`"])
            self.assertEqual(host, [f"POF_NODE_COMMAND=$(touch {marker})", "POF_POWER_OFF=no"])
            for refused in ("ORACLE_ATTESTED_IMAGES", "ORACLE_SANDBOX", "ORACLE_KEYS", "ORACLE_PRIVATE_KEY",
                            "RPC_API_KEY"):
                self.assertIn(f"refused a user-data line for {refused}", r.stdout)
            # The host reads its settings literally: the command substitution is a string, never run.
            r = subprocess.run(["bash", "-c", f". {DISK / 'rootfs/usr/lib/pof/pof-host-env.sh'}; "
                                f"host_env {d / 'run/host.env'}; printf '%s|%s' \"$POF_NODE_COMMAND\" "
                                "\"$POF_POWER_OFF\""], capture_output=True, text=True)
            self.assertEqual(r.stdout, f"$(touch {marker})|no")
            self.assertFalse(marker.exists())
            node_sh = (DISK / "rootfs/usr/lib/pof/pof-node.sh").read_text()
            self.assertIn("refused POF_NODE_COMMAND", node_sh)  # and pof-node.sh refuses that command's characters


RAD_STUB = r"""#!/bin/bash
# rad 1.10.3 as radicle-setup.sh uses it: the key, the seeding policies, `rad self --did`; the node never runs.
S="$RAD_HOME/stub"; mkdir -p "$S"; touch "$S/seeded"; echo "rad $*" >> "$S/calls"
case "$1 ${2:-}" in
  "node status") echo "Node is stopped."; echo "To start it, run \`rad node start\`." ;;
  "auth --alias") mkdir -p "$RAD_HOME/keys"; echo key > "$RAD_HOME/keys/radicle"; echo "$3" > "$S/alias" ;;
  "self --did") echo "did:key:z6MkfZYv3T15yL5xGpxPpMKsMm2ZVu4Efns8nmh9mGGP9kBZ" ;;
  "unseed "*) grep -vxF "$2" "$S/seeded" > "$S/s.new"; mv "$S/s.new" "$S/seeded" ;;
  "seed ") for r in $(cat "$S/seeded"); do echo "│ $r │ all │"; done ;;
  "seed "*) grep -qxF "$2" "$S/seeded" || echo "$2" >> "$S/seeded" ;;
  *) echo "rad stub: $*" >&2; exit 9 ;;
esac
"""
READY_STUB = r"""#!/bin/bash
# rad 1.10.3 as radicle-ready.sh uses it: the node's status, a sync, a checkout from local storage.
echo "rad $*" >> "$RAD_HOME/calls"
case "$1" in
  node) if [[ "${STUB_NODE:-}" == stopped ]]; then echo "Node is stopped."; else echo "✓ Node is running with x"; fi ;;
  sync) [[ "${STUB_SYNC:-}" == fail ]] && { echo; echo "✗ Error: no seeds found for $3"; exit 1; }; echo "✓ Synced" ;;
  checkout) [[ "${STUB_STORED:-}" == no ]] && { echo "✗ Error: repository $2 was not found"; exit 1; }
            git init -q pof-stats ;;
  *) echo "rad stub: $*" >&2; exit 9 ;;
esac
"""
SEED_NID = "z6Mkj5XETJwZmTwdjRAKKgtYqapoeBBDxbPipJaHmkMSjEmA"
RID = "rad:z4WFQw8hbE7uCgmdjAQyt5CEM9Nf6"


class TheRadicleNode(unittest.TestCase):
    """#251 L11, L12 on the measured disk: this validator's own Radicle node, pinned by checksum, its key and storage on
    the data volume, outbound only to the configured seed, ready before the node starts. The network behaviour is
    tests/integration/kit_radicle.py's (Docker); these need neither."""

    def test_radicle_1_10_3_by_checksum_on_the_disk(self):
        text = (DISK / "Dockerfile").read_text()
        self.assertIn("ADD --checksum=sha256:3d78e3ffc17f9e6eca7fcd3acc439f2252060532eb457cf17f2747fed4cc6751 \\\n"
                      "    https://files.radicle.dev/releases/1.10.3/radicle-1.10.3-x86_64-unknown-linux-musl.tar.xz",
                      text)
        # the same release the seed and the spike pin
        self.assertIn("3d78e3ffc17f9e6eca7fcd3acc439f2252060532eb457cf17f2747fed4cc6751",
                      (ROOT / "spikes/radicle/Dockerfile").read_text())
        self.assertIn('RADICLE_VERSION = "1.10.3"'.split(" = ")[1].strip('"'), (ROOT / "seed/radicle/install.sh").read_text()
                      + (ROOT / "seed/README.md").read_text())
        self.assertIn("COPY --from=radicle /out/ /usr/lib/pof/radicle/bin/", text)
        rootfs = text.split("FROM debian AS rootfs")[1].split("FROM debian AS tools")[0]
        self.assertRegex(rootfs, r"util-linux git \\")  # radicle-node runs git to serve fetches
        self.assertIn("useradd -u 10001 -g 10001 -M -d /data/state/radicle -s /usr/sbin/nologin pof", rootfs)
        self.assertIn("sed -i 's/^pof:\\([^:]*\\):[0-9]*:/pof:\\1::/' /etc/shadow", rootfs)  # no build day in it
        for unit in ("pof-config.service", "pof-radicle-setup.service", "pof-radicle.service",
                     "pof-radicle-ready.service"):
            self.assertIn(unit, rootfs.split("systemctl enable")[1].split("systemctl mask")[0])

    def test_the_service_runs_before_the_node_with_its_state_on_the_data_volume(self):
        units = DISK / "rootfs/etc/systemd/system"
        setup = (units / "pof-radicle-setup.service").read_text()
        for needed in ("Requires=pof-data.service", "After=pof-data.service pof-config.service",
                       "Before=pof-radicle.service", "ExecStart=/usr/lib/pof/pof-radicle.sh setup",
                       "StandardOutput=journal+console"):
            self.assertIn(needed, setup)
        unit = (units / "pof-radicle.service").read_text()
        for needed in ("Requires=pof-radicle-setup.service", "After=pof-radicle-setup.service", "User=pof",
                       "Environment=RAD_HOME=/data/state/radicle",
                       "ExecStart=/usr/lib/pof/radicle/bin/radicle-node --log-level info",
                       "ReadWritePaths=/data/state/radicle", "NoNewPrivileges=yes", "ProtectSystem=strict",
                       "StandardOutput=journal\n"):  # its log stays off the console: the attestation's lines stay
            self.assertIn(needed, unit)
        ready = (units / "pof-radicle-ready.service").read_text()
        for needed in ("Requires=pof-radicle.service", "After=pof-radicle.service", "Before=pof-node.service",
                       "ExecStart=-/usr/lib/pof/pof-radicle.sh ready", "StandardOutput=journal+console"):
            self.assertIn(needed, ready)
        node = (DISK / "rootfs/etc/systemd/system/pof-node.service").read_text()
        self.assertIn("After=pof-attest.service pof-radicle-ready.service", node)
        attest = (DISK / "rootfs/etc/systemd/system/pof-attest.service").read_text()
        self.assertIn("After=pof-images.service pof-config.service", attest)  # the user data read once, before both
        self.assertNotIn("pof-config.sh", (DISK / "rootfs/usr/lib/pof/pof-attest.sh").read_text().split("set -uo")[1])
        data = (DISK / "rootfs/usr/lib/pof/pof-data.sh").read_text()
        self.assertIn("install -d -o 10001 -g 10001 -m 0700 /data/state/radicle", data)  # persists: key, storage
        self.assertIn("install -d -o 10001 -g 10001 -m 0755 /data/scratch/radicle", data)  # wiped: the working copy
        host = (DISK / "rootfs/usr/lib/pof/pof-radicle.sh").read_text()
        for needed in ("RAD_HOME=/data/state/radicle", "REPO=/data/scratch/radicle/repo", "setpriv --reuid=10001",
                       "ORACLE_RADICLE_RID", "POF_RADICLE_SEED", 'say "nid ',
                       "as_node bash /usr/lib/pof/radicle-ready.sh"):
            self.assertIn(needed, host)

    def test_the_node_container_reaches_this_host_s_radicle_node(self):
        node = (DISK / "rootfs/usr/lib/pof/pof-node.sh").read_text()
        for needed in ("-v /data/state/radicle:/data/state/radicle", "-v /data/scratch/radicle:/data/scratch/radicle",
                       "-v /usr/lib/pof/radicle/bin:/opt/radicle/bin:ro", "-e RAD_HOME=/data/state/radicle",
                       "-e ORACLE_RADICLE_EXEC= ", "-e ORACLE_RADICLE_REPO=/data/scratch/radicle/repo",
                       "-e PATH=/opt/radicle/bin:"):
            self.assertIn(needed, node)
        self.assertLess(node.index("--env-file /run/pof/node.env"), node.index("-e ORACLE_RADICLE_EXEC="))

    def test_the_config_is_outbound_only(self):
        cfg = (DISK / "rootfs/usr/lib/pof/radicle-config.json").read_text()
        doc = json.loads(cfg.replace("@CONNECT@", '"' + SEED_NID + '@seed.example:8776"'))["node"]
        self.assertEqual((doc["listen"], doc["externalAddresses"]), ([], []))
        self.assertEqual(doc["seedingPolicy"], {"default": "block"})
        # static peers: only `connect` (the seed) is dialled, never the main network's bootstrap nodes nor a peer the
        # seed gossips (dynamic peers dial both: radicle-node 1.10.3 on main, no network, tried iris and rosa.radicle.network)
        self.assertEqual(doc["peers"], {"type": "static"})
        self.assertEqual(doc["connect"], [SEED_NID + "@seed.example:8776"])
        self.assertEqual(json.loads((ROOT / "seed/radicle/config.json").read_text())["node"]["listen"],
                         ["0.0.0.0:8776"])  # the seed is the one that listens

    @unittest.skipUnless(shutil.which("bash"), "needs bash")
    def test_radicle_setup_sh(self):
        """The key made once, the config from the template, the one policy; refused inputs; no RID: no peer."""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "bin").mkdir()
            (d / "bin/rad").write_text(RAD_STUB)
            (d / "bin/rad").chmod(0o755)
            home = d / "home"
            env = {**os.environ, "PATH": f"{d / 'bin'}:{os.environ['PATH']}", "RAD_HOME": str(home)}
            setup = DISK / "rootfs/usr/lib/pof/radicle-setup.sh"

            def run(*args):
                return subprocess.run(["bash", str(setup), *args], capture_output=True, text=True, env=env)

            r = run("pof-validator", "main")  # an attest-only boot: the key, no peer, no policy
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.strip(), "did:key:z6MkfZYv3T15yL5xGpxPpMKsMm2ZVu4Efns8nmh9mGGP9kBZ")
            cfg = json.loads((home / "config.json").read_text())["node"]
            self.assertEqual((cfg["connect"], cfg["listen"], cfg["network"], cfg["alias"]),
                             ([], [], "main", "pof-validator"))
            seed = f"{SEED_NID}@seed.example.org:8776"
            (home / "stub/seeded").write_text("rad:z3gqcJUoA1n9HaHKufZs5FCSGazv5\n")  # a policy left from before: unseeded
            r = run("pof-validator", "main", RID, seed)
            self.assertEqual(r.returncode, 0, r.stderr)
            cfg = json.loads((home / "config.json").read_text())["node"]
            self.assertEqual(cfg["connect"], [seed])
            self.assertEqual((home / "stub/seeded").read_text().split(), [RID])
            calls = (home / "stub/calls").read_text()
            self.assertEqual(calls.count("rad auth"), 1)  # the key is made once: a rerun keeps the Node ID
            self.assertIn(f"rad seed {RID} --scope all --no-fetch", calls)
            for bad in (("x y", "main"), ("v", "devnet"), ("v", "main", "rad:bad!", seed), ("v", "main", RID),
                        ("v", "main", RID, "seed.example.org:8776"), ("v", "main", RID, f"{SEED_NID}@h:1;rm -rf /")):
                r = run(*bad)
                self.assertEqual(r.returncode, 2, bad)
                self.assertIn("radicle-setup:", r.stderr)
            (d / "bin/rad").write_text(RAD_STUB.replace('echo "Node is stopped."', 'echo "✓ Node is running with x"'))
            r = run("pof-validator", "main", RID, seed)  # the policy is set with the node stopped
            self.assertEqual(r.returncode, 2)
            self.assertIn("stop radicle-node first", r.stderr)

    @unittest.skipUnless(shutil.which("bash") and shutil.which("git"), "needs bash and git")
    def test_radicle_ready_sh(self):
        """The ready step: waits for the node, syncs, makes the working copy from local storage (`rad checkout`, so a
        failed sync still leaves one), and says which; refused inputs; no RID: the node's wait only."""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "bin").mkdir()
            (d / "bin/rad").write_text(READY_STUB)
            (d / "bin/rad").chmod(0o755)
            home, repo = d / "home", d / "scratch/repo"
            home.mkdir()
            (d / "scratch").mkdir()
            env = {**os.environ, "PATH": f"{d / 'bin'}:{os.environ['PATH']}", "RAD_HOME": str(home)}
            ready = DISK / "rootfs/usr/lib/pof/radicle-ready.sh"

            def run(*args, **extra):
                return subprocess.run(["bash", str(ready), *args], capture_output=True, text=True, cwd=d / "scratch",
                                      env={**env, **extra}, timeout=60)

            r = run(RID, str(repo))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertRegex(r.stdout, r"^ready in \d+ ms \(sync: ok\)$")
            self.assertTrue((repo / ".git").is_dir())
            self.assertFalse(Path(str(repo) + ".checkout").exists())
            calls = (home / "calls").read_text()
            self.assertIn(f"rad sync --fetch {RID}", calls)
            self.assertIn(f"rad checkout {RID} --no-confirm", calls)
            (repo / "stale").write_text("from the last boot")
            r = run(RID, str(repo), STUB_SYNC="fail")  # the seed unreachable: the working copy from local storage
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertRegex(r.stdout, r"^ready in \d+ ms \(sync: .*no seeds.*\)$")
            self.assertFalse((repo / "stale").exists())  # made again at each boot
            r = run(RID, str(repo), STUB_SYNC="fail", STUB_STORED="no")  # a first boot, the seed unreachable
            self.assertEqual(r.returncode, 3)
            self.assertIn("no working copy", r.stdout)
            r = run()  # an attest-only boot: no repository
            self.assertEqual((r.returncode, r.stdout.strip()), (0, "node running; no repository configured"))
            r = run(RID, str(repo), STUB_NODE="stopped")
            self.assertEqual((r.returncode, r.stdout.strip()), (1, "the node didn't start"))
            for bad in (("rad:bad!", str(repo)), (RID, "relative/repo"), (RID, "/x;rm -rf /")):
                self.assertEqual(run(*bad).returncode, 2, bad)

    @unittest.skipUnless(shutil.which("bash") and shutil.which("python3"), "needs bash")
    def test_the_seed_address_is_the_host_s_setting(self):
        """POF_RADICLE_SEED reaches host.env; ORACLE_RADICLE_EXEC and ORACLE_RADICLE_REPO are the disk's."""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "ud").write_text("\n".join([f"POF_RADICLE_SEED={SEED_NID}@seed.example.org:8776",
                                             f"ORACLE_RADICLE_RID={RID}", "ORACLE_RADICLE_EXEC=sh -c evil",
                                             "ORACLE_RADICLE_REPO=/tmp/x", "ORACLE_FIX_SOURCE=radicle"]))
            (d / "bin").mkdir()
            (d / "bin/curl").write_text(
                "#!/bin/bash\n"
                "out=''; for ((i=1;i<=$#;i++)); do [[ ${!i} == -o ]] && { j=$((i+1)); out=${!j}; }; done\n"
                f"if [[ -n $out ]]; then cp {d / 'ud'} \"$out\"; printf 200; else printf token; fi\n")
            (d / "bin/curl").chmod(0o755)
            env = {**os.environ, "PATH": f"{d / 'bin'}:{os.environ['PATH']}", "POF_RUN_DIR": str(d / "run")}
            r = subprocess.run(["bash", str(DISK / "rootfs/usr/lib/pof/pof-config.sh")], capture_output=True,
                               text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((d / "run/node.env").read_text().split(), [f"ORACLE_RADICLE_RID={RID}",
                                                                       "ORACLE_FIX_SOURCE=radicle"])
            self.assertEqual((d / "run/host.env").read_text().split(), [f"POF_RADICLE_SEED={SEED_NID}@seed.example.org:8776"])
            for refused in ("ORACLE_RADICLE_EXEC", "ORACLE_RADICLE_REPO"):
                self.assertIn(f"refused a user-data line for {refused}", r.stdout)
            r = subprocess.run(["bash", "-c", f". {DISK / 'rootfs/usr/lib/pof/pof-host-env.sh'}; "
                                f"host_env {d / 'run/host.env'}; printf %s \"$POF_RADICLE_SEED\""],
                               capture_output=True, text=True)
            self.assertEqual(r.stdout, f"{SEED_NID}@seed.example.org:8776")

    def test_the_terraform_opens_no_port_and_passes_the_seed(self):
        main = (KIT / "terraform/main.tf").read_text()
        self.assertIn('var.radicle_seed != "" ? ["POF_RADICLE_SEED=${var.radicle_seed}"] : []', main)
        variables = (KIT / "terraform/variables.tf").read_text()
        self.assertRegex(variables, r'variable "egress_ports" \{[^}]*default     = \[443, 8776\]')
        self.assertIn('"ORACLE_RADICLE_EXEC", "ORACLE_RADICLE_REPO"], k)', variables)
        network = (KIT / "terraform/network.tf").read_text()
        self.assertNotIn("aws_vpc_security_group_ingress_rule", network)
        self.assertNotIn("ingress {", network)


class TheTerraform(unittest.TestCase):
    def test_sev_snp_nitrotpm_and_nothing_launched_by_default(self):
        main = (KIT / "terraform/main.tf").read_text()
        variables = (KIT / "terraform/variables.tf").read_text()
        for needed in ('amd_sev_snp = "enabled"', 'boot_mode           = "uefi"', 'tpm_support         = "v2.0"',
                       'http_tokens                 = "required"', 'instance_initiated_shutdown_behavior = "stop"',
                       "count                                = var.create_instance ? 1 : 0"):
            self.assertIn(needed, main)
        self.assertRegex(variables, r'variable "create_instance" \{[^}]*default     = false', )
        self.assertIn('default     = "us-east-2"', variables)
        self.assertIn('default     = "c6a.large"', variables)
        self.assertNotIn("ingress", (KIT / "terraform/network.tf").read_text().replace("No ingress", ""))
        budget = (KIT / "terraform/budget.tf").read_text()
        self.assertIn('action_sub_type = "STOP_EC2_INSTANCES"', budget)
        # No node_config: no node settings at all, so the boot only attests. (`var.node_config == {}` never held for a
        # map(string): the first test host, 2026-11-20, got the signing key's ARN and started the node.)
        self.assertIn("node_lines = length(var.node_config) == 0 ? [] :", main)

    def test_several_kits_in_one_account_keep_the_old_defaults(self):
        """subnet_id, tags and budget_cost_tag (#251, the temporary validators): empty by default, so an existing state
        plans no change; the kit's own network moves to index 0 instead of being replaced."""
        tf = KIT / "terraform"
        variables = (tf / "variables.tf").read_text()
        for name, default in (("subnet_id", '""'), ("tags", "{}"), ("budget_cost_tag", '""')):
            block = variables[variables.index(f'variable "{name}" {{'):]
            self.assertIn(f"  default     = {default}\n", block[:block.index("\n}\n") + 1])
        network = (tf / "network.tf").read_text()
        for res in ("aws_vpc.main", "aws_internet_gateway.main", "aws_subnet.public", "aws_route_table.public",
                    "aws_route_table_association.public"):
            self.assertRegex(network, rf"moved \{{\n  from = {re.escape(res)}\n  to   = {re.escape(res)}\[0\]\n\}}")
        self.assertEqual(len(re.findall(r"count\s+= local\.own_network \? 1 : 0", network)), 5)
        self.assertIn("subnet_id                            = local.subnet_id", (tf / "main.tf").read_text())
        self.assertIn("volume_tags = length(var.tags) > 0 ?", (tf / "main.tf").read_text())
        budget = (tf / "budget.tf").read_text()
        self.assertIn('for_each = var.budget_cost_tag != "" ? [var.budget_cost_tag] : []', budget)
        self.assertIn('values = ["user:${cost_filter.value}"]', budget)
        # The watcher is untouched by these (another change owns it).
        self.assertNotIn("subnet", (tf / "watcher.tf").read_text())

    def test_the_example_keeps_the_instance(self):
        """A plan without create_instance = true destroys the instance and its data volume (the Radicle key)."""
        tf = KIT / "terraform"
        example = (tf / "test.tfvars.example").read_text()
        self.assertRegex(example, r"(?m)^create_instance\s+= true")
        self.assertNotRegex(example, r"(?<![0-9a-f])(?!123456789012)\d{12}(?![0-9a-f])")
        ignore = (tf / ".gitignore").read_text().splitlines()
        for pattern in ("*.tfstate*", "*.tfvars", "*.tfvars.*", "!*.tfvars.example", "*.plan", "*.plan.txt"):
            self.assertIn(pattern, ignore)
        self.assertIn("**Warning: from here on, every `tofu plan` and `tofu apply` of this state needs `-var "
                      "create_instance=true`", (ROOT / "validator-kit/SEVSNP-PLAN.md").read_text())

    def test_v2_s_kit_is_untouched(self):
        self.assertTrue((ROOT / "validator-kit/terraform/node.tf").exists())
        self.assertIn("al2023-ami-kernel-default-arm64", (ROOT / "validator-kit/terraform/node.tf").read_text())


def fake_report(report_data: bytes, measurement=b"\x5a" * 48, policy=0x30000) -> bytes:
    raw = bytearray(V.REPORT_SIZE)
    struct.pack_into("<IIQ", raw, 0, 3, 0, policy)
    raw[0x50:0x90] = report_data
    raw[0x90:0xC0] = measurement
    return bytes(raw)


def cbor(v) -> bytes:
    if isinstance(v, bool) or v is None:
        return bytes([0xF5 if v is True else 0xF4 if v is False else 0xF6])
    if isinstance(v, int):
        return V._head(0, v) if v >= 0 else V._head(1, -1 - v)
    if isinstance(v, bytes):
        return V._head(2, len(v)) + v
    if isinstance(v, str):
        return V._head(3, len(v.encode())) + v.encode()
    if isinstance(v, list):
        return V._head(4, len(v)) + b"".join(cbor(x) for x in v)
    if isinstance(v, dict):
        return V._head(5, len(v)) + b"".join(cbor(k) + cbor(x) for k, x in v.items())
    raise TypeError(v)


MEASURED = {"format": "pof-checker-image/1", "platform": "amd64", "hash": "sha384", "pcr4": "aa" * 48,
            "pcr7": "bb" * 48, "pcr12": "00" * 48, "roothash": "cd" * 32}
IMAGES = {"format": "pof-images/1", "images": [{"name": "node", "ref": "pof-oracle-node@sha256:" + "11" * 32},
                                               {"name": "test", "ref": "pof-test-image@sha256:" + "22" * 32}]}
MANIFEST = {"roothash": "cd" * 32, "measured": MEASURED, "images": IMAGES,
            "image_digest": "0x" + hashlib.sha256(json.dumps(MEASURED, sort_keys=True,
                                                             separators=(",", ":")).encode()).hexdigest()}
NONCE = "0123456789abcdef"


class TheVerifier(unittest.TestCase):
    def console(self, report=None, doc=None, refused=True, roothash="cd" * 32):
        report = report if report is not None else fake_report(V.boot_report_data(NONCE, "cd" * 32))
        if doc is None:
            doc = self.document(report)
        check = {"listed": [i["ref"] for i in IMAGES["images"]], "unlisted_refused": refused,
                 "refusal": "attested mode: ..."}
        return "\n".join([
            "[   1.0] noise", f"[  30.1] pof-attest.sh[1]: POF-ATTEST roothash {roothash}",
            f"[  30.2] pof-attest.sh[1]: POF-ATTEST nonce {NONCE}",
            f"[  30.3] pof-attest.sh[1]: POF-ATTEST snp-report {base64.b64encode(report).decode()}",
            f"[  30.4] pof-attest.sh[1]: POF-ATTEST nitrotpm {base64.b64encode(doc).decode()}",
            f"[  30.5] pof-attest.sh[1]: POF-ATTEST attested-check {json.dumps(check)}"])

    def document(self, report, pcr4=None, nonce=NONCE, cert=b"\x30\x00", signer=None):
        payload = cbor({"module_id": "i-0", "digest": "SHA384", "timestamp": 1,
                        "nitrotpm_pcrs": {4: bytes.fromhex(pcr4 or MEASURED["pcr4"]),
                                          7: bytes.fromhex(MEASURED["pcr7"]), 12: bytes.fromhex(MEASURED["pcr12"])},
                        "certificate": cert, "cabundle": [], "public_key": None,
                        "user_data": hashlib.sha384(report).hexdigest().encode(), "nonce": nonce.encode()})
        protected = cbor({1: -35})
        sig = signer(V.sig_structure(protected, payload)) if signer else b"\x01" * 96
        return b"\xd2" + cbor([protected, {}, payload, sig])  # tag 18: COSE_Sign1

    def test_a_good_boot_passes(self):
        out = V.verify(self.console(), MANIFEST, NONCE, snp_measurement="5a" * 48)
        self.assertTrue(out["passed"], json.dumps(out, indent=1))
        self.assertIsNone(out["checks"]["nitroSignature"]["ok"])  # not checked without the root

    def test_what_fails(self):
        cases = {
            "roothash": self.console(roothash="ef" * 32),
            "snpReportData": self.console(report=fake_report(b"\x00" * 64)),
            "nitroPcrs": self.console(doc=self.document(fake_report(V.boot_report_data(NONCE, "cd" * 32)),
                                                        pcr4="ee" * 48)),
            "nitroBinding": self.console(doc=self.document(fake_report(V.boot_report_data(NONCE, "cd" * 32)),
                                                           nonce="ffff")),
            "attestedImages": self.console(refused=False),
            "snpPolicy": self.console(report=fake_report(V.boot_report_data(NONCE, "cd" * 32),
                                                         policy=0x30000 | V.POLICY_DEBUG)),
        }
        for name, console in cases.items():
            out = V.verify(console, MANIFEST, NONCE)
            self.assertFalse(out["passed"], name)
            self.assertFalse(out["checks"][name]["ok"], name)
        out = V.verify(self.console(), MANIFEST, NONCE, snp_measurement="00" * 48)
        self.assertFalse(out["checks"]["snpMeasurement"]["ok"])
        out = V.verify(self.console(), {**MANIFEST, "image_digest": "0x" + "00" * 32}, NONCE)
        self.assertFalse(out["checks"]["imageDigest"]["ok"])

    @unittest.skipUnless(shutil.which("openssl"), "needs openssl")
    def test_the_nitro_signature_and_chain(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)

            def ossl(*args):
                subprocess.run(["openssl", *args], check=True, capture_output=True, cwd=d)

            ossl("ecparam", "-name", "secp384r1", "-genkey", "-noout", "-out", "root.key")
            ossl("req", "-x509", "-new", "-key", "root.key", "-subj", "/CN=test-root", "-days", "2", "-out",
                 "root.pem", "-sha384")
            ossl("ecparam", "-name", "secp384r1", "-genkey", "-noout", "-out", "leaf.key")
            ossl("req", "-new", "-key", "leaf.key", "-subj", "/CN=test-leaf", "-out", "leaf.csr")
            ossl("x509", "-req", "-in", "leaf.csr", "-CA", "root.pem", "-CAkey", "root.key", "-CAcreateserial",
                 "-days", "1", "-sha384", "-out", "leaf.pem")
            ossl("x509", "-in", "leaf.pem", "-outform", "DER", "-out", "leaf.der")

            def sign(tbs: bytes) -> bytes:
                (d / "tbs").write_bytes(tbs)
                ossl("dgst", "-sha384", "-sign", "leaf.key", "-out", "sig.der", "tbs")
                der = (d / "sig.der").read_bytes()
                # DER ECDSA-Sig-Value -> r || s, 48 bytes each (COSE's form)
                i = 2 if der[1] < 0x80 else 3
                rl = der[i + 1]
                r = der[i + 2:i + 2 + rl]
                j = i + 2 + rl
                s = der[j + 2:j + 2 + der[j + 1]]
                return r.lstrip(b"\x00").rjust(48, b"\x00") + s.lstrip(b"\x00").rjust(48, b"\x00")

            report = fake_report(V.boot_report_data(NONCE, "cd" * 32))
            good = self.document(report, cert=(d / "leaf.der").read_bytes(), signer=sign)
            out = V.verify(self.console(report=report, doc=good), MANIFEST, NONCE, nitro_root=str(d / "root.pem"))
            self.assertTrue(out["checks"]["nitroSignature"]["ok"], out["checks"]["nitroSignature"])
            forged = self.document(report, cert=(d / "leaf.der").read_bytes(), signer=lambda tbs: sign(tbs + b"x"))
            out = V.verify(self.console(report=report, doc=forged), MANIFEST, NONCE, nitro_root=str(d / "root.pem"))
            self.assertFalse(out["checks"]["nitroSignature"]["ok"])
            self.assertIn("doesn't verify", out["checks"]["nitroSignature"]["detail"])
            ossl("ecparam", "-name", "secp384r1", "-genkey", "-noout", "-out", "other.key")
            ossl("req", "-x509", "-new", "-key", "other.key", "-subj", "/CN=other", "-days", "2", "-out", "other.pem")
            out = V.verify(self.console(report=report, doc=good), MANIFEST, NONCE, nitro_root=str(d / "other.pem"))
            self.assertIn("doesn't chain", out["checks"]["nitroSignature"]["detail"])


    @unittest.skipUnless(shutil.which("openssl"), "needs openssl")
    def test_the_snp_report_s_signature_and_amd_s_chain(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)

            def ossl(*args):
                subprocess.run(["openssl", *args], check=True, capture_output=True, cwd=d)

            (d / "ca.ext").write_text("basicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign\n")
            for name in ("ark", "ask", "vlek", "other"):
                ossl("ecparam", "-name", "secp384r1", "-genkey", "-noout", "-out", f"{name}.key")
            ossl("req", "-x509", "-new", "-key", "ark.key", "-subj", "/CN=ARK-test", "-days", "2", "-out", "ark.pem")
            ossl("req", "-new", "-key", "ask.key", "-subj", "/CN=ASVK-test", "-out", "ask.csr")
            ossl("x509", "-req", "-in", "ask.csr", "-CA", "ark.pem", "-CAkey", "ark.key", "-CAcreateserial", "-days",
                 "1", "-extfile", "ca.ext", "-out", "ask.pem")
            ossl("req", "-new", "-key", "vlek.key", "-subj", "/CN=VLEK-test", "-out", "vlek.csr")
            ossl("x509", "-req", "-in", "vlek.csr", "-CA", "ask.pem", "-CAkey", "ask.key", "-CAcreateserial", "-days",
                 "1", "-out", "vlek.pem")
            ossl("x509", "-in", "vlek.pem", "-outform", "DER", "-out", "vlek.der")
            (d / "chain.pem").write_text((d / "ask.pem").read_text() + (d / "ark.pem").read_text())

            def signed(key="vlek.key"):
                raw = bytearray(fake_report(V.boot_report_data(NONCE, "cd" * 32)))
                struct.pack_into("<I", raw, 0x48, 1 << 2)  # SIGNING_KEY = VLEK
                (d / "body").write_bytes(bytes(raw[:0x2A0]))
                ossl("dgst", "-sha384", "-sign", key, "-out", "sig.der", "body")
                der = (d / "sig.der").read_bytes()
                i = 2 if der[1] < 0x80 else 3
                r = der[i + 2:i + 2 + der[i + 1]]
                j = i + 2 + der[i + 1]
                s = der[j + 2:j + 2 + der[j + 1]]
                raw[0x2A0:0x2A0 + 72] = int.from_bytes(r, "big").to_bytes(72, "little")
                raw[0x2A0 + 72:0x2A0 + 144] = int.from_bytes(s, "big").to_bytes(72, "little")
                return bytes(raw)

            cert = "POF-ATTEST snp-cert vlek " + base64.b64encode((d / "vlek.der").read_bytes()).decode()
            good = signed()
            out = V.verify(self.console(report=good) + "\n" + cert, MANIFEST, NONCE, amd_chain=str(d / "chain.pem"),
                           save=d / "saved")
            self.assertTrue(out["checks"]["snpSignature"]["ok"], out["checks"]["snpSignature"])
            self.assertTrue((d / "saved/vlek.pem").exists() and (d / "saved/report.bin").exists())
            bad = signed("other.key")
            out = V.verify(self.console(report=bad) + "\n" + cert, MANIFEST, NONCE, amd_chain=str(d / "chain.pem"))
            self.assertFalse(out["checks"]["snpSignature"]["ok"])
            out = V.verify(self.console(report=good), MANIFEST, NONCE, amd_chain=str(d / "chain.pem"))
            self.assertIn("no vlek certificate", out["checks"]["snpSignature"]["detail"])
            # The node names the certificate by its GHCB GUID, in either byte order (disk c7b72b70: bytes_le).
            for guid in ("a8074bc2-a25a-483e-aae6-39c045a0b8a1", "c24b07a8-5aa2-3e48-aae6-39c045a0b8a1"):
                out = V.verify(self.console(report=good) + "\n" + cert.replace(" vlek ", f" {guid} "), MANIFEST, NONCE,
                               amd_chain=str(d / "chain.pem"))
                self.assertTrue(out["checks"]["snpSignature"]["ok"], (guid, out["checks"]["snpSignature"]))

    def test_ec2_s_console_capture(self):
        """get-console-output breaks long lines with its own timestamps and ends them with CR; NitroTPM's payload is an
        indefinite-length CBOR map. Both as the first test host showed them (2026-11-20)."""
        report = fake_report(V.boot_report_data(NONCE, "cd" * 32))
        doc = self.document(report)
        sign1, _ = V.cbor_decode(doc)
        payload = sign1[2]
        self.assertEqual(payload[0] >> 5, 5)  # a definite map of under 24 pairs: make it indefinite, as AWS's is
        self.assertLess(payload[0] & 0x1F, 24)
        indefinite = b"\xbf" + payload[1:] + b"\xff"
        doc = b"\xd2" + cbor([sign1[0], {}, indefinite, sign1[3]])
        console = self.console(report=report, doc=doc)
        stamped = []
        for line in console.splitlines():
            parts = [line[k:k + 300] for k in range(0, len(line), 300)]
            stamped.append("[2026-11-20T19:41:36.358374]".join(parts) + "\r")
        out = V.verify("\n".join(stamped), MANIFEST, NONCE, snp_measurement="5a" * 48)
        self.assertTrue(out["passed"], json.dumps(out, indent=1))

    @unittest.skipUnless((KIT / "evidence/2026-11-20/console.txt").exists(), "no evidence")
    def test_the_first_test_host_s_evidence(self):
        """The real boot of 2026-11-20 (i-01ede2166387706db, c6a.large, us-east-2): every check that needs no root."""
        ev = KIT / "evidence/2026-11-20"
        out = V.verify((ev / "console.txt").read_text(errors="replace"), json.loads((ev / "manifest.json").read_text()),
                       "12d380b92afa561dc574f865b48d6c80",
                       snp_measurement="7a89cceaaba0bbdddc4f775acca3ef15d1f9bf8abccdc6115cfad7fb8eae113d"
                                       "f3ee0bb50efa34db9c53ae065b1dc766")  # aws/uefi 20260814, 2 vCPUs
        self.assertTrue(out["passed"], json.dumps(out, indent=1))
        for name in ("roothash", "snpReportData", "snpMeasurement", "snpPolicy", "nitroPcrs", "nitroBinding",
                     "imageDigest", "attestedImages"):
            self.assertTrue(out["checks"][name]["ok"], name)


if __name__ == "__main__":
    unittest.main()
