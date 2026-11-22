"""AMD SEV-SNP attestation reports for a validator on an SEV-SNP guest (#253's kit, #251 L21; validator-kit/sevsnp).

The report comes from the AMD Secure Processor through the guest driver's /dev/sev-guest (SNP_GET_REPORT), standard
library only. Its 64 bytes of report data are the node's binding (the registration's or the receipt's hash, as
oracle/keys.py's quotes), and AMD signs it with the chip's VCEK, or on EC2's shared tenancy with AWS's VLEK
(https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/snp-attestation.html). A verifier checks the signature against
AMD's key server (snpguest verify) and the MEASUREMENT against the launch measurement it expects
(validator-kit/sevsnp: on EC2 that is AWS's firmware alone; the disk is measured by NitroTPM).

`SnpKeys` (ORACLE_KEYS=snp): the validator's key from ORACLE_PRIVATE_KEY (the kit reads it from the operator's
Secrets Manager into the node's process), its quotes these reports, kind "amd-sev-snp" (the TEE type a registration
names). The key's custody isn't attested (the operator also holds it); sealing it to the measured boot (AWS KMS with
NitroTPM attestation) is a later step, named in the kit's plan."""

from __future__ import annotations

import fcntl
import os
import struct
from dataclasses import dataclass

from .keys import DEVNET_CHAIN_ID, LOCAL_CHAIN_IDS, EnvKeys, Quote, _pad64

KIND = "amd-sev-snp"
DEVICE = "/dev/sev-guest"
SEPOLIA = 11_155_111
REPORT_SIZE = 0x4A0  # 1184 bytes: SEV-SNP firmware ABI, ATTESTATION_REPORT
RESP_SIZE = 4000  # struct snp_report_resp (linux/include/uapi/linux/sev-guest.h)
# _IOWR('S', 0x0, struct snp_guest_request_ioctl): 32 bytes (u8 msg_version, padding, u64 req, u64 resp, u64 exitinfo2)
SNP_GET_REPORT = (3 << 30) | (32 << 16) | (ord("S") << 8) | 0x0
SNP_GET_EXT_REPORT = (3 << 30) | (32 << 16) | (ord("S") << 8) | 0x2  # the report and the host's certificates
SIGNERS = {0: "vcek", 1: "vlek"}
VMM_ERR_INVALID_LEN = 1  # SNP_GUEST_VMM_ERR_INVALID_LEN: the certificates' buffer was too small; its length is set
PAGE = 4096
# The GHCB specification's certificate table GUIDs: AMD's root and signing keys, and the chip's or the cloud's key. The
# table holds each GUID's 16 bytes in the order these strings are written (`uuid.UUID(bytes=...)`, as snpguest and
# AWS's guide name them). Until disk c7b72b70 the node read them as `bytes_le`, so the first test host's console named
# the VLEK `c24b07a8-5aa2-3e48-...` (validator-kit/sevsnp/verify.py still accepts that order, for its evidence).
CERT_GUIDS = {"c0b406a4-a803-4952-9743-3fb6014cd0ae": "ark", "4ab7b379-bbac-4fe4-a02f-05aef327c782": "ask",
              "63da758d-e664-4564-adc5-f4b93be8accd": "vcek", "a8074bc2-a25a-483e-aae6-39c045a0b8a1": "vlek"}


@dataclass(frozen=True)
class Report:
    raw: bytes
    version: int
    guest_svn: int
    policy: int
    vmpl: int
    signature_algo: int
    signer: str  # "vcek" or "vlek" (the report's SIGNING_KEY)
    report_data: bytes
    measurement: bytes  # 48 bytes: the launch measurement
    host_data: bytes
    id_key_digest: bytes
    report_id: bytes
    reported_tcb: int
    chip_id: bytes

    def tcb(self) -> dict:
        """REPORTED_TCB's parts (Milan and Genoa layout): the SVNs a minimum firmware is checked against."""
        b = self.reported_tcb.to_bytes(8, "little")
        return {"boot_loader": b[0], "tee": b[1], "snp": b[6], "microcode": b[7]}

    def firmware(self) -> int:
        """The registration's `firmware` (Validators: a TEE type's minimum firmware level, D10): REPORTED_TCB's SVNs
        as one comparable number, boot loader, TEE, SNP, microcode from the most significant byte down."""
        t = self.tcb()
        return (t["boot_loader"] << 24) | (t["tee"] << 16) | (t["snp"] << 8) | t["microcode"]

    def summary(self) -> dict:
        return {"version": self.version, "vmpl": self.vmpl, "policy": hex(self.policy), "signer": self.signer,
                "measurement": self.measurement.hex(), "report_data": self.report_data.hex(),
                "host_data": self.host_data.hex(), "reported_tcb": self.tcb(), "firmware": self.firmware(),
                "chip_id": self.chip_id.hex()}


def parse(raw: bytes) -> Report:
    """An ATTESTATION_REPORT (AMD SEV-SNP ABI, table "ATTESTATION_REPORT Structure")."""
    if len(raw) < REPORT_SIZE:
        raise ValueError(f"an SEV-SNP report has {REPORT_SIZE} bytes, not {len(raw)}")
    raw = bytes(raw[:REPORT_SIZE])
    version, guest_svn, policy = struct.unpack_from("<IIQ", raw, 0x00)
    vmpl, signature_algo = struct.unpack_from("<II", raw, 0x30)
    (flags,) = struct.unpack_from("<I", raw, 0x48)
    (reported_tcb,) = struct.unpack_from("<Q", raw, 0x180)
    if version < 2:
        raise ValueError(f"SEV-SNP report version {version} isn't supported")
    return Report(raw, version, guest_svn, policy, vmpl, signature_algo, SIGNERS.get((flags >> 2) & 0x7, "unknown"),
                  raw[0x50:0x90], raw[0x90:0xC0], raw[0xC0:0xE0], raw[0xE0:0x110], raw[0x140:0x160],
                  reported_tcb, raw[0x1A0:0x1E0])


def request_report(report_data: bytes, device: str = DEVICE, vmpl: int = 0, ioctl=fcntl.ioctl) -> bytes:
    """The guest's report over `report_data` (64 bytes) from the AMD Secure Processor, through the SEV guest driver."""
    if len(report_data) != 64:
        raise ValueError("SEV-SNP report data is 64 bytes")
    import ctypes

    req = ctypes.create_string_buffer(report_data + struct.pack("<I", vmpl) + bytes(28), 96)
    resp = ctypes.create_string_buffer(RESP_SIZE)
    arg = bytearray(struct.pack("<B7xQQQ", 1, ctypes.addressof(req), ctypes.addressof(resp), 0))
    try:
        fd = os.open(device, os.O_RDWR)
    except OSError as e:
        raise RuntimeError(f"no SEV-SNP guest device ({device}: {e.strerror}): this isn't an SEV-SNP guest, or the "
                           f"node wasn't given the device") from None
    try:
        ioctl(fd, SNP_GET_REPORT, arg, True)
    except OSError as e:
        fw_error, vmm_error = struct.unpack_from("<II", arg, 24)
        raise RuntimeError(f"SNP_GET_REPORT failed: {e.strerror} (firmware error {fw_error:#x}, VMM error "
                           f"{vmm_error:#x})") from None
    finally:
        os.close(fd)
    status, size = struct.unpack_from("<II", resp.raw, 0)
    if status != 0 or size < REPORT_SIZE:
        raise RuntimeError(f"SNP_GET_REPORT: status {status:#x}, report of {size} bytes")
    return resp.raw[0x20:0x20 + REPORT_SIZE]


def request_ext_report(report_data: bytes, device: str = DEVICE, vmpl: int = 0, ioctl=fcntl.ioctl,
                       certs_len: int = 4 * PAGE) -> tuple:
    """(the report, {name: DER certificate}) through SNP_GET_EXT_REPORT: also the certificates the host gives, which on
    EC2's shared tenancy hold the VLEK that signs the report (AWS's guide reads them with `snpguest certificates`)."""
    import ctypes
    import mmap
    import uuid

    if len(report_data) != 64:
        raise ValueError("SEV-SNP report data is 64 bytes")
    try:
        fd = os.open(device, os.O_RDWR)
    except OSError as e:
        raise RuntimeError(f"no SEV-SNP guest device ({device}: {e.strerror}): this isn't an SEV-SNP guest, or the "
                           f"node wasn't given the device") from None
    try:
        for _ in range(2):  # once more with the length the host asks for
            certs = mmap.mmap(-1, certs_len)  # page-aligned, as the driver requires
            certs_addr = ctypes.addressof(ctypes.c_char.from_buffer(certs))
            req = ctypes.create_string_buffer(report_data + struct.pack("<I", vmpl) + bytes(28)
                                              + struct.pack("<QI4x", certs_addr, certs_len), 112)
            resp = ctypes.create_string_buffer(RESP_SIZE)
            arg = bytearray(struct.pack("<B7xQQQ", 1, ctypes.addressof(req), ctypes.addressof(resp), 0))
            try:
                ioctl(fd, SNP_GET_EXT_REPORT, arg, True)
            except OSError as e:
                fw_error, vmm_error = struct.unpack_from("<II", arg, 24)
                (needed,) = struct.unpack_from("<I", req.raw, 104)
                if vmm_error == VMM_ERR_INVALID_LEN and needed > certs_len:
                    certs_len = -(-needed // PAGE) * PAGE
                    continue
                raise RuntimeError(f"SNP_GET_EXT_REPORT failed: {e.strerror} (firmware error {fw_error:#x}, VMM "
                                   f"error {vmm_error:#x})") from None
            status, size = struct.unpack_from("<II", resp.raw, 0)
            if status != 0 or size < REPORT_SIZE:
                raise RuntimeError(f"SNP_GET_EXT_REPORT: status {status:#x}, report of {size} bytes")
            table = bytes(certs[:certs_len])
            break
        else:
            raise RuntimeError("SNP_GET_EXT_REPORT: the host's certificates didn't fit")
    finally:
        os.close(fd)
    out = {}
    for i in range(0, len(table) - 24 + 1, 24):  # entries of {guid, offset, length}, ended by a zero GUID
        guid, offset, length = table[i:i + 16], *struct.unpack_from("<II", table, i + 16)
        if not any(guid):
            break
        text = str(uuid.UUID(bytes=guid))
        name = CERT_GUIDS.get(text, text)
        out[name] = table[offset:offset + length]
    return resp.raw[0x20:0x20 + REPORT_SIZE], out


class SnpKeys(EnvKeys):
    """ORACLE_KEYS=snp: the key from ORACLE_PRIVATE_KEY, quotes from the SEV-SNP guest (module docstring)."""

    kind = KIND

    def __init__(self, env: dict | None = None, device: str | None = None, request=request_report):
        super().__init__(env)
        e = os.environ if env is None else env
        self.device, self._request = device or e.get("ORACLE_SNP_DEVICE") or DEVICE, request

    def quote(self, report_data: bytes) -> Quote:
        rd = _pad64(report_data)
        return Quote(KIND, self._request(rd, self.device).hex(), rd.hex())

    def check_chain(self, chain_id: int) -> None:
        if chain_id not in LOCAL_CHAIN_IDS | {DEVNET_CHAIN_ID, SEPOLIA}:
            raise RuntimeError(f"SEV-SNP keys refused on chain {chain_id}: for the devnet and Sepolia (#251)")
