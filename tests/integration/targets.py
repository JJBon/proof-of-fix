"""Where the integration suite runs (proof-of-fix#152): the target profiles, and the parts of the AWS profile that need
neither Docker nor AWS, so tests/test_integration_targets.py checks them offline.

    local (the default)  a throwaway local devnet that scripts/integration.sh starts and removes: every scenario
    aws                  the persistent, shared AWS devnet with pof-sandbox and the live validator nodes
                         (tests/integration/aws.py)

The AWS devnet is shared and keeps its state, so a run there:
- opens its own issue for each scenario, and names what it creates after its run tag (issues "[integration <tag>] ...",
  branches "integration/<tag>/...") so it can close and delete them afterwards, pass or fail;
- asserts balances as deltas, read before and after each step, never as absolute values;
- never resets or redeploys anything, and doesn't start, stop or replace any node;
- talks only to chain 7193, the devnet's: any other chain ID is refused before anything is read or sent (rule 1).

Credentials are the ones scripts/devnet-seats.sh and scripts/first-bounty.sh already take, read once at the start; each
is a value in this process's memory, never on a command line, in the output, in a log or in a record. `Secrets` redacts
them from everything the run prints and says where one would have leaked."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from pathlib import Path

DEVNET_CHAIN_ID = 7193  # scripts/devnet.sh's CHAIN_ID: the private devnet, no public chain's
TARGETS = ("local", "aws")
SCENARIOS = ("1", "2", "3", "4", "5", "6", "7", "8")
AWS_ORDER = ("2", "3", "1", "5")  # no merge first, then the merges: each fix is a commit on main as it is then
LOCAL_ONLY = {
    "4": "a silent validator needs one drawn node not to run; on the AWS devnet the nodes are scripts/devnet-seats.sh's and "
         "the owner's kit, live and shared, and the suite never stops one",
    "6": "joining needs a vacant seat and activates it after a 7-day warp; the AWS devnet's 7 seats are all taken (seat 6 "
         "joined through this flow on 2026-11-04), so the preflight checks instead that all 7 are active",
    "7": "7a points the nodes at a relay that's down and 7b kills a node mid-check: both would disturb the shared devnet's "
         "live nodes and other runs. 7c, the owner's seat started from cold, happens on AWS whenever seat 6 is drawn; "
         "locally it's scripts/first-run-e2e.sh (--with-first-run)",
    "8": "Radicle merges (#201) need the local isolated Radicle network whose repository is Heads' genesis; the AWS "
         "devnet's repository is pof-sandbox on the forge (scripts/integration.sh --radicle, locally)",
}
NOT_COVERED = ("a nightly run against the AWS devnet (it needs the owner's keys in CI: .forgejo/workflows/nightly.yml's "
               "header)",
               "the leaderboard's validator draws, agreement, reveal rate, fees per check and slashes (not in v2's "
               "events: pofctl leaderboard says why)")
URL = re.compile(r"^https?://[A-Za-z0-9._-]+(:[0-9]+)?(/[A-Za-z0-9._/-]*)?$")  # as scripts/devnet-seats.sh's
CREDENTIAL = re.compile(r"^[^:\s]+:\S+$")  # <handle>:<key>


class Refused(Exception):
    """A setting or a chain the suite won't run with. The message never carries a secret."""


# ---------- the target ----------

def split_target(argv: list) -> tuple:
    """(the target, the other arguments). `--target NAME` or `--target=NAME`; the local devnet by default."""
    target, rest, i = "local", [], 0
    while i < len(argv):
        a = argv[i]
        if a == "--target":
            if i + 1 >= len(argv):
                raise Refused("--target needs a name: local or aws")
            target, i = argv[i + 1], i + 2
            continue
        if a.startswith("--target="):
            target = a.split("=", 1)[1]
        else:
            rest.append(a)
        i += 1
    if target not in TARGETS:
        raise Refused(f"unknown target {target!r}: local or aws")
    return target, rest


def plan(target: str, only: str | None = None) -> tuple:
    """(the scenarios to run, in order; [(scenario, why it's skipped)]). `only`: "2,3", as --only takes it."""
    wanted = [s.strip() for s in only.split(",") if s.strip()] if only else list(SCENARIOS)
    unknown = [s for s in wanted if s not in SCENARIOS]
    if unknown:
        raise Refused(f"no scenario {', '.join(unknown)} (1-8)")
    if target == "local":
        return [s for s in SCENARIOS if s in wanted], []
    run = [s for s in AWS_ORDER if s in wanted]
    skipped = [(s, LOCAL_ONLY[s]) for s in SCENARIOS if s in wanted and s in LOCAL_ONLY]
    return run, skipped


# ---------- the AWS profile's settings ----------

def _secret(env: dict, name: str, file_var: str, what: str, strip_all: bool = False) -> str:
    value = env.get(name) or ""
    if not value and env.get(file_var):
        path = Path(env[file_var])
        try:
            value = path.read_text(encoding="utf-8")
        except OSError:
            raise Refused(f"can't read {file_var}") from None
    value = re.sub(r"\s", "", value) if strip_all else value.strip()
    if not value:
        raise Refused(f"no {what}: set {name} or {file_var}")
    return value


@dataclass
class AwsSettings:
    rpc_url: str
    exchange_url: str
    repo: str
    forge: str
    record: str
    user: str
    auth: str = field(repr=False)  # "<handle>:<key>", the RPC's and the relay's
    token: str = field(repr=False)  # writes to the repository: issues, branches, pull requests, merges
    read_token: str = field(default="", repr=False)  # the seats' read-only token: the preflight checks it only reads
    read_user: str = "pof-validator-bot"
    engineer_key: str = field(default="", repr=False)  # seat 6's own key: then its fees are withdrawn too (#150)
    insecure_local: bool = False  # anvil's public keys: a throwaway rig over plain HTTP only

    def secrets(self) -> dict:
        """Every secret value, by what it is (for Secrets)."""
        out = {"the RPC credential": self.auth, "the repository token": self.token}
        if self.read_token:
            out["the read-only token"] = self.read_token
        if self.engineer_key:
            out["seat 6's key"] = self.engineer_key
        return out


SECRET_VARS = ("DEVNET_RPC_AUTH", "FIRST_BOUNTY_TOKEN", "DEVNET_REPO_TOKEN", "POFCTL_KEY_ENGINEER", "POFCTL_RPC_TOKEN",
               "FORGEJO_TOKEN", "GITHUB_TOKEN")


def aws_settings(env: dict) -> AwsSettings:
    """The AWS profile's settings from the environment, as scripts/devnet-seats.sh and scripts/first-bounty.sh name
    them; Refused, without the secret, when one is missing or malformed."""
    url = env.get("DEVNET_RPC_URL") or ""
    if not url:
        raise Refused("set DEVNET_RPC_URL (https://devnet.example.com)")
    if not URL.match(url):
        raise Refused("DEVNET_RPC_URL must be a plain URL, without a credential in it: use DEVNET_RPC_AUTH or "
                      "DEVNET_RPC_AUTH_FILE")
    exchange = env.get("DEVNET_EXCHANGE_URL") or url.rstrip("/") + "/exchange"
    if not URL.match(exchange):
        raise Refused("DEVNET_EXCHANGE_URL must be a plain URL, without a credential in it")
    allow_http = env.get("DEVNET_RPC_ALLOW_HTTP") == "1"
    if (url.startswith("http://") or exchange.startswith("http://")) and not allow_http:
        raise Refused("plain HTTP would send the key in the clear: use https:// (DEVNET_RPC_ALLOW_HTTP=1 is for a local "
                      "test proxy)")
    insecure = env.get("DEVNET_KEYS") == "insecure-local"
    if insecure and not allow_http:
        raise Refused("DEVNET_KEYS=insecure-local are public keys: anyone could sign for these seats on a shared devnet")
    if env.get("DEVNET_KEYS") not in (None, "", "openbao", "insecure-local"):
        raise Refused("the role keys come from OpenBao (DEVNET_KEYS unset, or openbao)")
    auth = _secret(env, "DEVNET_RPC_AUTH", "DEVNET_RPC_AUTH_FILE", "credential (<handle>:<key>)")
    if not CREDENTIAL.match(auth):
        raise Refused("the credential must look like <handle>:<key> (not printed)")
    token = _secret(env, "FIRST_BOUNTY_TOKEN", "FIRST_BOUNTY_TOKEN_FILE",
                    "repository token with write:repository and write:issue", strip_all=True)
    user = env.get("FIRST_BOUNTY_USER") or ""
    if not user:
        raise Refused("set FIRST_BOUNTY_USER: the write token's user")
    read_token = ""
    if env.get("DEVNET_REPO_TOKEN") or env.get("DEVNET_REPO_TOKEN_FILE"):
        read_token = _secret(env, "DEVNET_REPO_TOKEN", "DEVNET_REPO_TOKEN_FILE", "read-only token", strip_all=True)
    engineer = env.get("POFCTL_KEY_ENGINEER") or ""
    if not engineer and env.get("POFCTL_KEY_ENGINEER_FILE"):
        engineer = _secret(env, "POFCTL_KEY_ENGINEER", "POFCTL_KEY_ENGINEER_FILE", "seat 6's key")
    engineer = engineer.strip()
    if engineer and not re.fullmatch(r"(0x)?[0-9a-fA-F]{64}", engineer):
        raise Refused("POFCTL_KEY_ENGINEER must be a 32-byte hex key (not printed)")
    forge = env.get("DEVNET_FORGE_URL") or "https://git.example.com"
    if not URL.match(forge):
        raise Refused("DEVNET_FORGE_URL must be a plain URL")
    return AwsSettings(rpc_url=url, exchange_url=exchange, repo=env.get("DEVNET_REPO") or "example-org/pof-sandbox",
                       forge=forge, record=env.get("DEVNET_RECORD_V2") or "contracts/deployments/devnet-aws-v2.json",
                       user=user, auth=auth, token=token, read_token=read_token,
                       read_user=env.get("DEVNET_REPO_USER") or "pof-validator-bot", engineer_key=engineer,
                       insecure_local=insecure)


def check_chain(answered: int, record: dict) -> None:
    """Rule 1: the RPC must answer the devnet's chain ID, and the record must be that chain's."""
    if answered != DEVNET_CHAIN_ID:
        raise Refused(f"refusing: the RPC answers chain {answered}, not the devnet's {DEVNET_CHAIN_ID} (rule 1: never a "
                      f"public chain)")
    if record.get("chainId") != DEVNET_CHAIN_ID:
        raise Refused(f"refusing: the deployment record is for chain {record.get('chainId')}, not the devnet's "
                      f"{DEVNET_CHAIN_ID}")
    if str(record.get("version")) != "2":
        raise Refused("the deployment record isn't v2's")


# ---------- deltas ----------

def deltas(before: dict, after: dict) -> dict:
    """name -> after - before, for every name in either (a missing side counts 0)."""
    return {k: after.get(k, 0) - before.get(k, 0) for k in sorted(set(before) | set(after))}


def expect_deltas(what: str, before: dict, after: dict, expected: dict) -> list:
    """Problems where a named balance didn't move by exactly what was expected. Names not in `expected` aren't checked:
    on a shared chain anything else may move them."""
    moved = deltas(before, after)
    return [f"{what}: {name} moved {moved.get(name, 0):+d}, expected {want:+d}"
            for name, want in sorted(expected.items()) if moved.get(name, 0) != want]


def check_withdrawal(name: str, owed_before: int, wallet_before: int, owed_after: int, wallet_after: int) -> list:
    """A withdrawal pays the whole credit to the wallet: the wallet's delta is the credit, and nothing stays owed."""
    problems = []
    if wallet_after - wallet_before != owed_before:
        problems.append(f"{name}: the wallet moved {wallet_after - wallet_before:+d}, its credit was {owed_before}")
    if owed_after:
        problems.append(f"{name}: {owed_after} still owed after withdrawing")
    return problems


def check_books(subs: dict, decided: dict, charged: dict, owed_delta, seats: list) -> list:
    """Each result's books, from deltas at the block that decided it (as scripts/demo-e2e.sh's, on a shared chain).

    subs: this run's submissions, id -> {"solver": address, "deposit": int}; decided: block -> [submission ids decided
    in it, anyone's]; charged: submission -> (judges counted, total charged); owed_delta(block, address): the credit's
    change in that block; seats: the seats' addresses. Per block: each of this run's solvers' deposits = what the meter
    charged them + what returned to the solver; and the seats were credited exactly what the meter charged in it."""
    problems = []
    for block, ids in sorted(decided.items()):
        ours = [s for s in ids if s in subs]
        for solver in sorted({subs[s]["solver"] for s in ours}):
            mine = [s for s in ours if subs[s]["solver"] == solver]
            deposit = sum(subs[s]["deposit"] for s in mine)
            got = sum(charged.get(s, (0, 0))[1] for s in mine)
            back = owed_delta(block, solver)
            if deposit != got + back:
                problems.append(f"block {block}: submission(s) {mine}: deposits {deposit} != charged {got} + "
                                f"returned {back}")
        if not ours:
            continue
        in_block = sum(charged.get(s, (0, 0))[1] for s in ids)
        credited = sum(owed_delta(block, seat) for seat in seats)
        if credited != in_block:
            problems.append(f"block {block}: the meter charged {in_block}, the seats were credited {credited}")
    return problems


# ---------- the leaderboard (#151): the board from events against the same bounties read from the views ----------

def board_expected(race, bounties, funders, late=None, withdrawn=None, attempts=None) -> dict:
    """What `pofctl leaderboard` must show over `bounties`, from the contracts' views rather than their events (pofctl's
    Race: bounty, issue, submissions_of, submission, award, instalments_paid, price_of, pledged, refunded_to, reports,
    config). role -> address (lowercase) -> metric -> value; a metric not named is expected 0, but for the funders'
    refunded amount (no view keeps it). `funders`: the addresses that may have pledged; `late`: address -> late fixes
    (TooLate has no view); `withdrawn`: address -> a seat's fees withdrawn (only on a board not narrowed to bounties);
    `attempts`: address -> attempts started (none in the suite, which seals without one)."""
    from pofctl.leaderboard import ROLES

    finder_bps = race.config()["finderFeeBps"]
    exp: dict = {r: {} for r in ROLES}

    def add(role, who, metric, n=1):
        row = exp[role].setdefault(who.lower(), {})
        row[metric] = row.get(metric, 0) + n

    for b in bounties:
        bt = race.bounty(b)
        issue = race.issue(bt["issue"])
        rep = issue["reporter"]
        add("reporters", rep, "registered")
        add("reporters", rep, "opened")
        add("reporters", rep, "rewarded", int(issue["state"] == "Rewarded"))
        add("reporters", rep, "junk", int(issue["state"] == "Forfeited"))
        paid = bt["state"] == "Paid"
        if paid and not bt["inflated"]:
            add("reporters", rep, "finderFees", race.price_of(b, bt["epoch"]) * finder_bps // 10_000)
        for e in range(1, bt["epoch"] + 1):
            aw = race.award(b, e)
            add("solvers", aw["winner"], "merged")
            add("solvers", aw["winner"], "earned", race.instalments_paid(b, e))
            add("solvers", aw["winner"], "clawedBack", int(bool(aw["closed"])))
        if paid:
            add("solvers", race.award(b, bt["epoch"])["winner"], "won")
        for s in race.submissions_of(b):
            sub = race.submission(s)
            decided = sub["outcome"] != "None"
            add("solvers", sub["solver"], "submissions")
            add("solvers", sub["solver"], "decided", int(decided))
            add("solvers", sub["solver"], "passed", int(sub["outcome"] == "Pass"))
            for r in race.reports(s):
                add("validators", r["judge"], "reports")
                add("validators", r["judge"], "counted", int(decided))
        for f in funders:
            amount = race.pledged(b, f)
            if amount:
                add("funders", f, "pledged", amount)
                add("funders", f, "bounties")
                add("funders", f, "solved", int(paid))
                add("funders", f, "refunds", int(bool(race.refunded_to(b, f))))
    for who, n in (late or {}).items():
        add("solvers", who, "late", n)
    for who, n in (attempts or {}).items():
        add("solvers", who, "attempts", n)
    for who, amount in (withdrawn or {}).items():
        add("validators", who, "withdrawn", amount)
    return exp


def check_board(what: str, board: dict, expected: dict) -> list:
    """Problems where the board (pofctl leaderboard --json) differs from what's expected: a metric off, a row missing,
    or a row nobody expected. Every metric is compared (0 when not named), but for a funder's refunded amount when it
    isn't named."""
    from pofctl.leaderboard import METRICS, ROLES

    problems = []
    for role in ROLES:
        got = {r["address"].lower(): r for r in board.get(role, [])}
        want = expected.get(role, {})
        for who in sorted(set(got) | set(want)):
            row, exp = got.get(who), want.get(who, {})
            if row is None and not any(exp.values()):
                continue
            if row is None:
                problems.append(f"{what}: {role} {who} missing (expected {exp})")
                continue
            if who not in want:
                extra = {m: row[m] for m in METRICS[role] if row[m]}
                problems.append(f"{what}: {role} {who} unexpected ({extra})")
                continue
            for m in METRICS[role]:
                if m == "refunded" and m not in exp:
                    continue
                if row[m] != exp.get(m, 0):
                    problems.append(f"{what}: {role} {who}: {m} {row[m]}, expected {exp.get(m, 0)}")
    return problems


# ---------- secrets: redacted from the output, and a leak check ----------

class Secrets:
    """The run's secret values. `redact` replaces each (and its HTTP Basic and hex forms) with ***; `leaks` names which
    kinds appear in a text, never the values."""

    def __init__(self) -> None:
        self._forms: list = []  # (form, label), longest first

    def add(self, label: str, value: str, user: str = "") -> None:
        value = (value or "").strip()
        if len(value) < 8:
            return
        forms = {value, base64.b64encode(value.encode()).decode()}
        if user:
            forms.add(base64.b64encode(f"{user}:{value}".encode()).decode())
        hexed = value[2:] if value.lower().startswith("0x") else value
        if re.fullmatch(r"[0-9a-fA-F]{64}", hexed):
            forms |= {hexed.lower(), hexed.upper(), "0x" + hexed.lower(), f"{int(hexed, 16):x}"}
        if ":" in value:  # <handle>:<key>: the key alone too
            forms.add(value.split(":", 1)[1])
        self._forms = sorted({*self._forms, *((f, label) for f in forms if len(f) >= 8)}, key=lambda x: -len(x[0]))

    def add_key(self, label: str, key: int) -> None:
        self.add(label, f"{key:064x}")

    def leaks(self, text: str) -> list:
        return sorted({label for form, label in self._forms if form in text})

    def redact(self, text: str) -> str:
        for form, _ in self._forms:
            text = text.replace(form, "***")
        return text


class RedactingStream:
    """A text stream that redacts the run's secrets before they reach the terminal, and remembers that one tried to."""

    def __init__(self, inner, secrets: Secrets) -> None:
        self.inner, self.secrets, self.caught = inner, secrets, set()
        self._held = ""

    def write(self, text: str) -> int:
        self._held += text
        if "\n" in self._held:  # whole lines: a secret split across two writes is still seen
            done, self._held = self._held.rsplit("\n", 1)
            self._emit(done + "\n")
        return len(text)

    def _emit(self, text: str) -> None:
        found = self.secrets.leaks(text)
        if found:
            self.caught.update(found)
            text = self.secrets.redact(text)
        self.inner.write(text)

    def flush(self) -> None:
        if self._held:
            self._emit(self._held)
            self._held = ""
        self.inner.flush()

    def isatty(self) -> bool:
        return False

    def __getattr__(self, name):
        return getattr(self.inner, name)
