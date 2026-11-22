#!/usr/bin/env python3
"""Checks a SEV-SNP validator host's boot attestation against the measured disk's build (#253; #251 L18 items 3 and 6,
L21). Standard library only, plus the `openssl` command for the NitroTPM document's certificates and signature.

    validator-kit/sevsnp/verify.py --console console.txt --manifest out/manifest.json --nonce HEX
        [--snp-measurement HEX] [--amd-chain cert_chain.pem] [--nitro-root root.pem] [--save DIR]

`console.txt` is `aws ec2 get-console-output --latest --output text` of the instance (the disk's pof-attest.sh prints
its POF-ATTEST lines there). It checks, and prints as JSON:

  roothash        the booted root hash is the build's (manifest.json)
  snpReportData   the SEV-SNP report's data is sha512("pof-boot-attestation/1" | nonce | root hash): this boot's report
  snpMeasurement  its MEASUREMENT equals --snp-measurement: AWS's firmware for this vCPU count, computed with
                  sev-snp-measure from AWS's reproducible OVMF (validator-kit/SEVSNP-PLAN.md); skipped without it
  snpPolicy       debugging is off in the guest policy, and the report is for VMPL 0
  snpSignature    the report's ECDSA P-384 signature by the host's VLEK (or VCEK) from the console, and that
                  certificate's chain to AMD's root (--amd-chain: AMD KDS's cert_chain for it, e.g.
                  https://kdsintf.amd.com/vlek/v1/Milan/cert_chain); skipped without it
  nitroPcrs       NitroTPM's PCR4, PCR7 and PCR12 equal the build's pcrs.json (PCR4 measures the UKI, so the root hash)
  nitroBinding    the NitroTPM document's user data is the SEV-SNP report's sha384 and its nonce the verifier's: one boot
  nitroSignature  the document's COSE_Sign1 signature (ES384) by its certificate, and that certificate's chain up to AWS's
                  Nitro root (--nitro-root: AWS_NitroEnclaves_Root-G1's PEM); skipped without it
  imageDigest     the checker image's digest recomputed from the measured values is the build's (Validators' list)
  attestedImages  the node in attested mode found every listed image at its digest and refused an unlisted one

AWS's own route for the SEV-SNP report's signature is AMD's tool
(https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/snp-attestation.html): --save DIR writes report.bin and the
host's certificates as PEM for `snpguest verify certs` and `snpguest verify attestation`, a second opinion on
snpSignature. Exit 0 only if every check that ran passed."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import struct
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

REPORT_SIZE = 0x4A0
POLICY_DEBUG = 1 << 19


# ---------- CBOR, as much as COSE_Sign1 needs ----------

def cbor_decode(data: bytes, i: int = 0):
    """(value, next index) for CBOR; tags are dropped (COSE_Sign1's 18). Indefinite-length strings, arrays and maps
    (RFC 8949 section 3.2.2) are read too: NitroTPM's document payload is an indefinite-length map (0xbf ... 0xff)."""
    ib = data[i]
    major, info = ib >> 5, ib & 0x1F
    i += 1
    if info == 31 and major in (2, 3, 4, 5):
        items = []
        while data[i] != 0xFF:
            v, i = cbor_decode(data, i)
            items.append(v)
        i += 1
        if major == 2:
            return b"".join(items), i
        if major == 3:
            return "".join(items), i
        if major == 4:
            return items, i
        return dict(zip(items[0::2], items[1::2])), i
    if info < 24:
        arg = info
    elif info in (24, 25, 26, 27):
        n = 1 << (info - 24)
        arg = int.from_bytes(data[i:i + n], "big")
        i += n
    elif major == 7 and info in (20, 21, 22):
        return {20: False, 21: True, 22: None}[info], i
    else:
        raise ValueError(f"unsupported CBOR item {ib:#x}")
    if major == 0:
        return arg, i
    if major == 1:
        return -1 - arg, i
    if major in (2, 3):
        raw = data[i:i + arg]
        return (bytes(raw) if major == 2 else raw.decode()), i + arg
    if major == 4:
        out = []
        for _ in range(arg):
            v, i = cbor_decode(data, i)
            out.append(v)
        return out, i
    if major == 5:
        out = {}
        for _ in range(arg):
            k, i = cbor_decode(data, i)
            v, i = cbor_decode(data, i)
            out[k] = v
        return out, i
    if major == 6:
        return cbor_decode(data, i)
    if major == 7 and info == 22:
        return None, i
    raise ValueError(f"unsupported CBOR major type {major}")


def _head(major: int, n: int) -> bytes:
    if n < 24:
        return bytes([major << 5 | n])
    for info, size in ((24, 1), (25, 2), (26, 4), (27, 8)):
        if n < 1 << (8 * size):
            return bytes([major << 5 | info]) + n.to_bytes(size, "big")
    raise ValueError("too long")


def sig_structure(protected: bytes, payload: bytes) -> bytes:
    """COSE's Sig_structure for COSE_Sign1 (RFC 9052 section 4.4), with no external data."""
    text = b"Signature1"
    return (_head(4, 4) + _head(3, len(text)) + text + _head(2, len(protected)) + protected + _head(2, 0)
            + _head(2, len(payload)) + payload)


def der_signature(raw: bytes) -> bytes:
    """COSE's r || s as the DER ECDSA-Sig-Value openssl verifies."""
    half = len(raw) // 2

    def integer(b: bytes) -> bytes:
        b = b.lstrip(b"\x00") or b"\x00"
        if b[0] & 0x80:
            b = b"\x00" + b
        return b"\x02" + _der_len(len(b)) + b

    body = integer(raw[:half]) + integer(raw[half:])
    return b"\x30" + _der_len(len(body)) + body


def _der_len(n: int) -> bytes:
    return bytes([n]) if n < 0x80 else bytes([0x80 | 1, n]) if n < 0x100 else bytes([0x82]) + n.to_bytes(2, "big")


def pem(der: bytes) -> str:
    b = base64.b64encode(der).decode()
    return "-----BEGIN CERTIFICATE-----\n" + "\n".join(b[i:i + 64] for i in range(0, len(b), 64)) + \
        "\n-----END CERTIFICATE-----\n"


# ---------- the evidence ----------

# EC2's console capture (get-console-output --latest) breaks a long line about every 1 KB with its own timestamp,
# "[2026-11-20T19:41:36.358374]", and ends lines with CR; base64 has no "[", so removing them restores the line.
EC2_STAMP = re.compile(r"\[\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?\]|\r")


def console_text(raw: str) -> str:
    return EC2_STAMP.sub("", raw)


# The GHCB certificate table's GUIDs (raw byte order, as snpguest and AWS name them). The node's oracle/snp.py up to
# disk c7b72b70 read them as bytes_le, so that disk's console names the VLEK c24b07a8-5aa2-3e48-… (the 2026-11-20
# evidence); later disks read them in the table's order and print `vlek`. Both orders are accepted.
CERT_GUIDS = {"c0b406a4-a803-4952-9743-3fb6014cd0ae": "ark", "4ab7b379-bbac-4fe4-a02f-05aef327c782": "ask",
              "63da758d-e664-4564-adc5-f4b93be8accd": "vcek", "a8074bc2-a25a-483e-aae6-39c045a0b8a1": "vlek"}


def cert_name(name: str) -> str:
    try:
        u = uuid.UUID(name)
    except ValueError:
        return name
    return CERT_GUIDS.get(str(u)) or CERT_GUIDS.get(str(uuid.UUID(bytes=u.bytes_le))) or name


def console_lines(text: str) -> dict:
    """The POF-ATTEST lines (the last of each kind: the latest boot's)."""
    out = {}
    for line in text.splitlines():
        at = line.find("POF-ATTEST ")
        if at < 0:
            continue
        parts = line[at + len("POF-ATTEST "):].strip().split(" ", 1)
        out[parts[0]] = parts[1].strip() if len(parts) > 1 else ""
    return out


def report_fields(raw: bytes) -> dict:
    if len(raw) < REPORT_SIZE:
        raise ValueError(f"an SEV-SNP report has {REPORT_SIZE} bytes, not {len(raw)}")
    _, _, policy = struct.unpack_from("<IIQ", raw, 0)
    (vmpl,) = struct.unpack_from("<I", raw, 0x30)
    (flags,) = struct.unpack_from("<I", raw, 0x48)
    return {"policy": policy, "vmpl": vmpl, "flags": flags, "report_data": raw[0x50:0x90],
            "measurement": raw[0x90:0xC0]}


def boot_report_data(nonce: str, roothash: str) -> bytes:
    return hashlib.sha512(f"pof-boot-attestation/1\n{nonce}\n{roothash}".encode()).digest()


def nitro_document(raw: bytes) -> tuple:
    """(protected header bytes, payload bytes, signature, the payload's map) of a COSE_Sign1 attestation document."""
    sign1, _ = cbor_decode(raw)
    if not isinstance(sign1, list) or len(sign1) != 4:
        raise ValueError("not a COSE_Sign1")
    protected, _, payload, signature = sign1
    doc, _ = cbor_decode(payload)
    return protected, payload, signature, doc


def openssl_check(doc: dict, protected: bytes, payload: bytes, signature: bytes, root_pem: str) -> str:
    """'' when the document's certificate chains to the root and signs it; else why not."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "leaf.pem").write_text(pem(doc["certificate"]))
        # cabundle is ordered root first; the root is the operator's own copy, so the bundle's first is left out.
        (p / "chain.pem").write_text("".join(pem(c) for c in doc.get("cabundle", [])[1:]))
        verify = ["openssl", "verify", "-CAfile", root_pem, "-no_check_time"]
        if (p / "chain.pem").read_text():
            verify += ["-untrusted", str(p / "chain.pem")]
        r = subprocess.run(verify + [str(p / "leaf.pem")], capture_output=True, text=True)
        if r.returncode != 0:
            return f"the certificate doesn't chain to the root: {(r.stdout + r.stderr).strip()[:300]}"
        r = subprocess.run(["openssl", "x509", "-in", str(p / "leaf.pem"), "-pubkey", "-noout", "-out",
                            str(p / "pub.pem")], capture_output=True, text=True)
        if r.returncode != 0:
            return f"no public key in the certificate: {r.stderr.strip()[:200]}"
        (p / "tbs").write_bytes(sig_structure(protected, payload))
        (p / "sig.der").write_bytes(der_signature(signature))
        r = subprocess.run(["openssl", "dgst", "-sha384", "-verify", str(p / "pub.pem"), "-signature",
                            str(p / "sig.der"), str(p / "tbs")], capture_output=True, text=True)
        return "" if r.returncode == 0 else f"the signature doesn't verify: {(r.stdout + r.stderr).strip()[:200]}"


def snp_signature_check(report: bytes, leaf_der: bytes, amd_chain: str) -> str:
    """'' when the report is signed by the leaf (VLEK or VCEK) and the leaf chains to AMD's root; else why not. The
    signature is at 0x2A0: R and S, 72 bytes each, little-endian; it signs bytes 0 to 0x29F with SHA-384."""
    r = int.from_bytes(report[0x2A0:0x2A0 + 72], "little").to_bytes(48, "big")
    s = int.from_bytes(report[0x2A0 + 72:0x2A0 + 144], "little").to_bytes(48, "big")
    certs = [c for c in Path(amd_chain).read_text().split("-----END CERTIFICATE-----") if "BEGIN" in c]
    if len(certs) < 2:
        return "the AMD chain file needs the signing key's certificate (ASK or ASVK) and the root (ARK)"
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "ask.pem").write_text(certs[0].strip() + "\n-----END CERTIFICATE-----\n")
        (p / "ark.pem").write_text(certs[1].strip() + "\n-----END CERTIFICATE-----\n")
        (p / "leaf.pem").write_text(pem(leaf_der))
        out = subprocess.run(["openssl", "verify", "-no_check_time", "-CAfile", str(p / "ark.pem"), "-untrusted",
                              str(p / "ask.pem"), str(p / "leaf.pem")], capture_output=True, text=True)
        if out.returncode != 0:
            return f"the host's certificate doesn't chain to AMD's root: {(out.stdout + out.stderr).strip()[:300]}"
        out = subprocess.run(["openssl", "x509", "-in", str(p / "leaf.pem"), "-pubkey", "-noout", "-out",
                              str(p / "pub.pem")], capture_output=True, text=True)
        if out.returncode != 0:
            return f"no public key in the host's certificate: {out.stderr.strip()[:200]}"
        (p / "body").write_bytes(report[:0x2A0])
        (p / "sig.der").write_bytes(der_signature(r + s))
        out = subprocess.run(["openssl", "dgst", "-sha384", "-verify", str(p / "pub.pem"), "-signature",
                              str(p / "sig.der"), str(p / "body")], capture_output=True, text=True)
        return "" if out.returncode == 0 else f"the report's signature doesn't verify: {out.stdout.strip()[:200]}"


def verify(console: str, manifest: dict, nonce: str, snp_measurement: str = "", nitro_root: str = "",
           save: Path | None = None, amd_chain: str = "") -> dict:
    console = console_text(console)
    lines = console_lines(console)
    certs = {}
    for line in console.splitlines():  # POF-ATTEST snp-cert <name> <base64>: one line per certificate
        at = line.find("POF-ATTEST snp-cert ")
        if at >= 0:
            parts = line[at:].split()
            if len(parts) == 4:
                certs[cert_name(parts[2])] = base64.b64decode(parts[3])
    checks: dict = {}

    def check(name, ok, detail=""):
        checks[name] = {"ok": bool(ok), **({"detail": detail} if detail else {})}

    roothash = lines.get("roothash", "")
    check("roothash", roothash == manifest["roothash"], f"booted {roothash or 'nothing'}")
    measured = manifest["measured"]
    canon = json.dumps(measured, sort_keys=True, separators=(",", ":")).encode()
    check("imageDigest", "0x" + hashlib.sha256(canon).hexdigest() == manifest["image_digest"], manifest["image_digest"])
    check("nonce", lines.get("nonce", "") == nonce, f"the boot used {lines.get('nonce', '')!r}")

    report = b""
    if "snp-report" in lines:
        report = base64.b64decode(lines["snp-report"])
        f = report_fields(report)
        check("snpReportData", f["report_data"] == boot_report_data(nonce, manifest["roothash"]))
        if snp_measurement:
            check("snpMeasurement", f["measurement"].hex() == snp_measurement.lower(), f["measurement"].hex())
        else:
            checks["snpMeasurement"] = {"ok": None, "detail": f"not compared: {f['measurement'].hex()}"}
        check("snpPolicy", not f["policy"] & POLICY_DEBUG and f["vmpl"] == 0,
              f"policy {f['policy']:#x}, VMPL {f['vmpl']}")
        signer = "vlek" if (f["flags"] >> 2) & 7 == 1 else "vcek"
        if amd_chain:
            why = (snp_signature_check(report, certs[signer], amd_chain) if signer in certs
                   else f"the console has no {signer} certificate")
            check("snpSignature", not why, why or f"signed by the host's {signer}")
        else:
            checks["snpSignature"] = {"ok": None, "detail": f"not checked: give --amd-chain (the {signer}'s chain)"}
    else:
        check("snpReportData", False, lines.get("snp-report", "no snp-report line"))

    if "nitrotpm" in lines:
        protected, payload, signature, doc = nitro_document(base64.b64decode(lines["nitrotpm"]))
        pcrs = doc.get("nitrotpm_pcrs") or {}
        got = {k: (pcrs.get(n) or b"").hex() for k, n in (("pcr4", 4), ("pcr7", 7), ("pcr12", 12))}
        want = {k: measured[k] for k in got}
        check("nitroPcrs", got == want, json.dumps(got))
        user = (doc.get("user_data") or b"").decode(errors="replace")
        check("nitroBinding", bool(report) and user == hashlib.sha384(report).hexdigest()
              and (doc.get("nonce") or b"").decode(errors="replace") == nonce)
        if nitro_root:
            why = openssl_check(doc, protected, payload, signature, nitro_root)
            check("nitroSignature", not why, why)
        else:
            checks["nitroSignature"] = {"ok": None, "detail": "not checked: give --nitro-root"}
        if save is not None:
            save.mkdir(parents=True, exist_ok=True)
            (save / "nitrotpm.cbor").write_bytes(base64.b64decode(lines["nitrotpm"]))
            (save / "nitrotpm-leaf.pem").write_text(pem(doc["certificate"]))
    else:
        check("nitroPcrs", False, "no nitrotpm line")

    try:
        att = json.loads(lines.get("attested-check", "{}"))
    except ValueError:
        att = {}
    listed = [i["ref"] for i in manifest["images"]["images"]]
    check("attestedImages", att.get("listed") == listed and att.get("unlisted_refused") is True,
          att.get("refusal", lines.get("attested-check", "no attested-check line"))[:200])
    if save is not None and report:
        save.mkdir(parents=True, exist_ok=True)
        (save / "report.bin").write_bytes(report)
        for name, der in certs.items():  # snpguest's names: vlek.pem, vcek.pem, ask.pem, ark.pem
            (save / f"{name}.pem").write_text(pem(der))
    ran = [c["ok"] for c in checks.values() if c["ok"] is not None]
    return {"passed": all(ran), "checks": checks}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--console", required=True, help="the instance's console output (get-console-output --latest)")
    ap.add_argument("--manifest", required=True, help="the build's manifest.json (scripts/checker-disk.sh)")
    ap.add_argument("--nonce", required=True, help="the nonce you set (attest_nonce), lowercase hex")
    ap.add_argument("--snp-measurement", default="", help="the expected launch measurement (sev-snp-measure), hex")
    ap.add_argument("--nitro-root", default="", help="AWS's Nitro root certificate (PEM)")
    ap.add_argument("--amd-chain", default="", help="AMD KDS's cert_chain (PEM) for the report's signing key")
    ap.add_argument("--save", help="write report.bin, the host's certificates and the NitroTPM document here")
    a = ap.parse_args(argv)
    out = verify(Path(a.console).read_text(errors="replace"), json.loads(Path(a.manifest).read_text()), a.nonce,
                 a.snp_measurement, a.nitro_root, Path(a.save) if a.save else None, a.amd_chain)
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0 if out["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
