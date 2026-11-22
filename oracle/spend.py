"""The node's own model-spending caps and its pause (#253; #251 L16 and L23). Spending controls live in the node, not in
a gateway: a validator takes work from the contracts with no approval per job, so a bad day (spam within the
validators' capacity, a model that answers at length, a price change) must stop at the node.

- **Caps.** A daily and a monthly limit on what the node spends on model calls, in USD, kept in a small ledger on the
  node's state disk (it survives the on-demand runs' reboots). Before each attempt the call's worst case (the prompt's
  estimate plus the answer's cap, at the model's prices) must fit what is left of both; if it doesn't, the call isn't
  made: `SpendCapReached`, a `models.BudgetExceeded`, so the node seals no answer and the seat stays silent, and the
  contracts' existing rules for a silent seat apply. After the call its real cost (the provider's own token counts) is
  recorded; a call with no reply counts its worst case, as `models.Budget` does.
- **The pause.** When a cap stops a call, the node also sets its capacity to 0 on-chain (`Panels.setCapacity`, contract
  batch 2: a paused validator is skipped by every draw, never slashed), so it stops being drawn instead of staying
  silent seat after seat. The change takes effect `CAP_DELAY` blocks later; seats drawn meanwhile stay silent. At the
  next period of the cap that stopped it (the next UTC day for the daily one, the next month for the monthly one) it
  sets back the capacity it had before. A change still pending on-chain (`Busy`) is tried again on the next pass.
- **Defaults** (ORACLE_SPEND_*): $0.50 a day and $5 a month per validator, so 7 validators (L16's minimum) spend at most
  $35 a month together, inside the owner's $30-50 model budget (#253); at 15 the owner sets $3 a month ($45). Prices
  are ORACLE_PRICE_PER_MTOK (USD per million tokens: input, cached input, output), else the family's list price in
  pof/costs.py (ORACLE_FAMILY), else the dearest of each there, so an unknown model stops early rather than late.

    ORACLE_SPEND_DAILY_USD    the daily cap, UTC days (default 0.50; 0 turns the caps and the pause off)
    ORACLE_SPEND_MONTHLY_USD  the monthly cap, UTC months (default 5.00; 0 turns them off)
    ORACLE_SPEND_LEDGER       the ledger's file (default <ORACLE_ROUNDS or .oracle-rounds>/spend.json)
    ORACLE_PRICE_PER_MTOK     "input,cached,output" USD per million tokens
    ORACLE_SPEND_PAUSE        "on" (default): pause on-chain when a cap stops a call; "off": stay silent only"""

from __future__ import annotations

import datetime
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .models import BudgetExceeded, ConfigError

LEDGER_FORMAT = "pof-spend/1"
DEFAULT_DAILY_USD, DEFAULT_MONTHLY_USD = 0.50, 5.00
MICRO = 10**6


class SpendCapReached(BudgetExceeded):
    """A daily or monthly cap stops this call: no model call, so no answer is sealed."""

    def __init__(self, message: str, cap: str):
        super().__init__(message, kind="spend-cap")
        self.cap = cap  # "day" or "month"


@dataclass(frozen=True)
class Prices:
    """USD per million tokens. A token at $p per million costs p micro-USD."""
    input: float
    cached: float
    output: float

    def cost(self, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> int:
        """Micro-USD, rounded up."""
        cached = max(0, min(int(cached_tokens), int(input_tokens)))
        micro = (int(input_tokens) - cached) * self.input + cached * self.cached + int(output_tokens) * self.output
        return math.ceil(round(micro, 6))


def prices_from_env(env) -> Prices:
    raw = (env.get("ORACLE_PRICE_PER_MTOK") or "").strip()
    if raw:
        try:
            parts = [float(x) for x in raw.split(",")]
        except ValueError:
            parts = []
        if len(parts) != 3 or any(p < 0 for p in parts):
            raise ConfigError("ORACLE_PRICE_PER_MTOK is input,cached,output in USD per million tokens")
        return Prices(*parts)
    from pof import costs

    family = (env.get("ORACLE_FAMILY") or "").split("/")[0].strip().lower()
    if family in costs.JUDGE:
        m = costs.JUDGE[family]
        return Prices(m.input, m.cached, m.output)
    models = list(costs.JUDGE.values())
    return Prices(max(m.input for m in models), max(m.cached for m in models), max(m.output for m in models))


def _day(t: float) -> str:
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d")


def _month(t: float) -> str:
    return _day(t)[:7]


class SpendCaps:
    """The ledger and both caps. Not thread-safe: the node makes one model call at a time."""

    def __init__(self, daily_usd: float, monthly_usd: float, prices: Prices, path: Optional[Path] = None,
                 clock: Callable[[], float] = time.time, pause: bool = True):
        if daily_usd <= 0 or monthly_usd <= 0:
            raise ConfigError("the spending caps must be positive (ORACLE_SPEND_DAILY_USD, ORACLE_SPEND_MONTHLY_USD)")
        self.daily, self.monthly = int(round(daily_usd * MICRO)), int(round(monthly_usd * MICRO))
        self.prices, self.path, self.clock, self.pause_on = prices, path, clock, pause
        self.data = self._load()

    # ---------- the ledger ----------

    def _load(self) -> dict:
        empty = {"format": LEDGER_FORMAT, "days": {}, "months": {}, "stopped": None, "paused": None}
        if self.path is None or not Path(self.path).exists():
            return empty
        try:
            data = json.loads(Path(self.path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            # A ledger it can't read could hide what was spent: refuse to spend rather than start from zero.
            raise ConfigError(f"the spending ledger {self.path} can't be read ({e}); fix or remove it by hand")
        if data.get("format") != LEDGER_FORMAT:
            raise ConfigError(f"the spending ledger {self.path} isn't {LEDGER_FORMAT}")
        return {**empty, **data}

    def _save(self) -> None:
        now = self.clock()
        days, months = self.data["days"], self.data["months"]
        keep_days = {k: v for k, v in days.items() if k >= _day(now - 40 * 86400)}  # a month and a margin
        keep_months = {k: v for k, v in months.items() if k >= _month(now - 400 * 86400)}
        self.data["days"], self.data["months"] = keep_days, keep_months
        if self.path is None:
            return
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(self.data, sort_keys=True, indent=1), encoding="utf-8")
        os.replace(tmp, p)

    def spent(self) -> tuple:
        """(micro-USD spent today, this month)."""
        now = self.clock()
        return self.data["days"].get(_day(now), 0), self.data["months"].get(_month(now), 0)

    # ---------- the caps ----------

    def reserve(self, input_tokens: int, output_tokens: int) -> int:
        """Raises SpendCapReached unless this call's worst case fits both caps; returns that worst case."""
        worst = self.prices.cost(input_tokens, output_tokens)
        day, month = self.spent()
        for cap, used, limit, name in (("day", day, self.daily, "daily"), ("month", month, self.monthly, "monthly")):
            if used + worst > limit:
                now = self.clock()
                self.data["stopped"] = {"cap": cap, "period": _day(now) if cap == "day" else _month(now)}
                self._save()
                raise SpendCapReached(f"{name} model spending cap reached: ${used / MICRO:,.4f} spent of "
                                      f"${limit / MICRO:,.2f}, the next call may cost ${worst / MICRO:,.4f} "
                                      f"(ORACLE_SPEND_{name.upper()}_USD); no call, this seat stays silent", cap)
        return worst

    def record(self, micro_usd: int) -> None:
        now = self.clock()
        d, m = _day(now), _month(now)
        self.data["days"][d] = self.data["days"].get(d, 0) + int(micro_usd)
        self.data["months"][m] = self.data["months"].get(m, 0) + int(micro_usd)
        self._save()

    def record_usage(self, usage: dict) -> int:
        cost = self.prices.cost(usage.get("input_tokens", 0), usage.get("output_tokens", 0),
                                usage.get("cached_tokens", 0) or usage.get("cache_read_tokens", 0) or 0)
        self.record(cost)
        return cost

    # ---------- the pause ----------

    def stopped_now(self) -> Optional[str]:
        """The cap that stopped a call in the current period ("day" or "month"), or None once that period is over."""
        s = self.data.get("stopped")
        if not s:
            return None
        now = self.clock()
        current = _day(now) if s["cap"] == "day" else _month(now)
        return s["cap"] if s["period"] == current else None

    def pause_step(self, capacity: Callable[[], dict], set_capacity: Callable[[int], None], log=print) -> bool:
        """One pass of the pause: pause on-chain while a cap has stopped calls this period; restore the capacity the
        node had before once the period is over. `capacity()` is Panels' view of this key, `set_capacity(n)` sends
        setCapacity(key, n). Returns True when it sent something. A refused change (pending, or the chain away) raises
        to the caller, which tries again on the next pass."""
        if not self.pause_on:
            return False
        stopped, paused = self.stopped_now(), self.data.get("paused")
        if stopped and not paused:
            before = capacity()
            restore = int(before["next"])  # the setting in force once any pending change lands
            if restore == 0:  # already paused by its operator: nothing to do, and nothing to restore later
                return False
            set_capacity(0)
            self.data["paused"] = {"restore": restore, "cap": stopped}
            self._save()
            log(f"spending: the {stopped}ly cap stopped a model call; capacity set to 0 on-chain (was {restore}), "
                f"restored at the next {stopped}")
            return True
        if paused and not stopped:
            set_capacity(int(paused["restore"]))
            self.data["paused"], self.data["stopped"] = None, None
            self._save()
            log(f"spending: a new {paused['cap']}; capacity set back to {paused['restore']} on-chain")
            return True
        return False


def from_env(env, default_dir: str = ".oracle-rounds", clock=time.time) -> Optional[SpendCaps]:
    """The node's caps from the environment (module docstring); None when either cap is 0 (off)."""
    def usd(key, default):
        try:
            return float(env.get(key) or default)
        except ValueError:
            raise ConfigError(f"{key} must be a number of USD") from None

    daily, monthly = usd("ORACLE_SPEND_DAILY_USD", DEFAULT_DAILY_USD), usd("ORACLE_SPEND_MONTHLY_USD",
                                                                             DEFAULT_MONTHLY_USD)
    if daily == 0 or monthly == 0:
        return None
    path = env.get("ORACLE_SPEND_LEDGER") or str(Path(env.get("ORACLE_ROUNDS") or default_dir) / "spend.json")
    pause = (env.get("ORACLE_SPEND_PAUSE") or "on").lower() != "off"
    return SpendCaps(daily, monthly, prices_from_env(env), Path(path), clock, pause)
