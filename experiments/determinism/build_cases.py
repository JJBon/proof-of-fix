"""Builds the determinism experiment's judge cases (proof-of-fix#125): 10 issues in a made-up library, each with a
clearly good fix, a clearly bad one and a borderline one, in the case shape oracle/judge.py expects.

No third-party code: the first issue is the e2e demo's own (bot/sample/stats.py, bot/fixes/*), the rest are written
here in the same style. Each fix's diff is computed from its before and after source, and its test run is real: the
library's own tests plus the issue's acceptance test, run with `python -I -m unittest` in a temporary directory
(locally, not in the node's sandbox image; the prompt's test line says so).

Labels:
- good: fixes the issue as asked; the tests pass.
- bad: wrong, or passes only by special-casing the acceptance test's inputs; most fail the tests.
- borderline: the tests pass, but the fix is partial, has a side effect, or doesn't really address the issue.

Run: python3 experiments/determinism/build_cases.py   (writes experiments/determinism/cases/*.json)
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "cases"
REPO = "local/sample"

ISSUES = []


def issue(key, path, base, tests, acceptance, text, fixes):
    ISSUES.append({"key": key, "path": path, "base": base, "tests": tests, "acceptance": acceptance, "issue": text,
                   "fixes": fixes})


# ---------- 1. median (the e2e demo's issue: bot/sample/stats.py, bot/fixes/) ----------

issue("median", "stats.py",
      base='''"""A tiny library, the loop's test repository (proof-of-fix#56 task 3.3)."""


def mean(xs):
    return sum(xs) / len(xs)


def median(xs):
    s = sorted(xs)
    return s[len(s) // 2]  # the issue: for an even count this isn't the middle of the two middle values
''',
      tests='''import unittest

from stats import mean, median


class TestStats(unittest.TestCase):
    def test_mean(self):
        self.assertEqual(mean([1, 2, 3, 4]), 2.5)

    def test_median_odd(self):
        self.assertEqual(median([3, 1, 2]), 2)


if __name__ == "__main__":
    unittest.main()
''',
      acceptance='''import unittest

from stats import median


class TestMedianEven(unittest.TestCase):
    def test_even_count(self):
        self.assertEqual(median([4, 1, 3, 2]), 2.5)

    def test_odd_count_still(self):
        self.assertEqual(median([5, 1, 3]), 3)
''',
      text="median() is wrong for an even count: median([4, 1, 3, 2]) returns 3, but the median of an even number "
           "of values is the mean of the two middle values (2.5).",
      fixes={
          "good": ("Fix the median of an even count", '''"""A tiny library, the loop's test repository (proof-of-fix#56 task 3.3)."""


def mean(xs):
    return sum(xs) / len(xs)


def median(xs):
    s = sorted(xs)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2
''', None),
          "bad": ("Fix the median of an even count", '''"""A tiny library, the loop's test repository (proof-of-fix#56 task 3.3)."""


def mean(xs):
    return sum(xs) / len(xs)


def median(xs):
    s = sorted(xs)
    return s[(len(s) - 1) // 2]  # a wrong fix: the lower middle value, still not the median of an even count
''', None),
          "borderline": ("Fix the median of an even count without copying the list", '''"""A tiny library, the loop's test repository (proof-of-fix#56 task 3.3)."""


def mean(xs):
    return sum(xs) / len(xs)


def median(xs):
    xs.sort()  # in place: no copy of a large list
    mid = len(xs) // 2
    return xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2
''', "side effect: sorts the caller's list in place (median() now mutates its argument)"),
      })

# ---------- 2. slugify ----------

SLUG = '''import re


def slugify(title):
    """A URL slug: lower case, words joined by hyphens."""
    title = title.lower()
    title = re.sub(r"[^a-z0-9\\s-]", "", title)
    return re.sub(r"[\\s-]+", "-", title).strip("-")
'''
issue("slugify", "text.py", base=SLUG,
      tests='''import unittest

from text import slugify


class TestSlugify(unittest.TestCase):
    def test_words(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_punctuation(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")
''',
      acceptance='''import unittest

from text import slugify


class TestAccents(unittest.TestCase):
    def test_accented_letters_are_transliterated(self):
        self.assertEqual(slugify("Café au lait"), "cafe-au-lait")

    def test_plain_titles_unchanged(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")
''',
      text="slugify() drops accented letters instead of transliterating them: slugify('Café au lait') gives "
           "'caf-au-lait', expected 'cafe-au-lait'. The same goes for any accented Latin letter (ñ, ü, ç, å, ...): "
           "titles in Spanish, German or French lose letters.",
      fixes={
          "good": ("Transliterate accented letters in slugify()", '''import re
import unicodedata


def slugify(title):
    """A URL slug: lower case, words joined by hyphens. Accented letters lose their accents."""
    title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    title = title.lower()
    title = re.sub(r"[^a-z0-9\\s-]", "", title)
    return re.sub(r"[\\s-]+", "-", title).strip("-")
''', None),
          "bad": ("Keep accented letters in slugify()", '''import re


def slugify(title):
    """A URL slug: lower case, words joined by hyphens."""
    title = title.lower()
    return re.sub(r"[\\s-]+", "-", title).strip("-")
''', None),
          "borderline": ("Transliterate é and è in slugify()", '''import re


def slugify(title):
    """A URL slug: lower case, words joined by hyphens."""
    title = title.lower().replace("é", "e").replace("è", "e")
    title = re.sub(r"[^a-z0-9\\s-]", "", title)
    return re.sub(r"[\\s-]+", "-", title).strip("-")
''', "tests pass, issue not really addressed: only é and è are handled, not ñ, ü, ç, å as the issue asks"),
      })

# ---------- 3. parse_duration ----------

issue("duration", "durations.py",
      base='''import re

UNITS = {"h": 3600, "m": 60, "s": 1}


def parse_duration(text):
    """Seconds in a duration such as '90s', '15m' or '2h'. Raises ValueError on anything else."""
    m = re.fullmatch(r"(\\d+)([hms])", text.strip())
    if not m:
        raise ValueError(f"bad duration: {text!r}")
    return int(m.group(1)) * UNITS[m.group(2)]
''',
      tests='''import unittest

from durations import parse_duration


class TestDurations(unittest.TestCase):
    def test_single_units(self):
        self.assertEqual(parse_duration("90s"), 90)
        self.assertEqual(parse_duration("15m"), 900)
        self.assertEqual(parse_duration("2h"), 7200)

    def test_garbage(self):
        with self.assertRaises(ValueError):
            parse_duration("soon")
''',
      acceptance='''import unittest

from durations import parse_duration


class TestCombined(unittest.TestCase):
    def test_combined_units(self):
        self.assertEqual(parse_duration("1h30m"), 5400)
        self.assertEqual(parse_duration("2m15s"), 135)

    def test_still_rejects_garbage(self):
        with self.assertRaises(ValueError):
            parse_duration("abc")
''',
      text="parse_duration() rejects combined durations such as '1h30m' or '2m15s' with ValueError. They should be "
           "summed: '1h30m' is 5400 seconds. Malformed input (e.g. '1h30x', '5 minutes') must still raise "
           "ValueError, since config files rely on it to catch typos.",
      fixes={
          "good": ("Accept combined durations like 1h30m", '''import re

UNITS = {"h": 3600, "m": 60, "s": 1}


def parse_duration(text):
    """Seconds in a duration such as '90s', '15m', '2h' or '1h30m'. Raises ValueError on anything else."""
    text = text.strip()
    if not re.fullmatch(r"(?:\\d+[hms])+", text):
        raise ValueError(f"bad duration: {text!r}")
    return sum(int(n) * UNITS[u] for n, u in re.findall(r"(\\d+)([hms])", text))
''', None),
          "bad": ("Accept combined durations like 1h30m", '''import re

UNITS = {"h": 3600, "m": 60, "s": 1}


def parse_duration(text):
    """Seconds in a duration such as '90s', '15m', '2h' or '1h30m'. Raises ValueError on anything else."""
    text = text.strip()
    if "h" in text:
        hours, _, rest = text.partition("h")
        return int(hours) * 3600 + (int(rest.rstrip("m")) * 60 if rest else 0)
    m = re.fullmatch(r"(\\d+)([hms])", text)
    if not m:
        raise ValueError(f"bad duration: {text!r}")
    return int(m.group(1)) * UNITS[m.group(2)]
''', None),
          "borderline": ("Accept combined durations like 1h30m", '''import re

UNITS = {"h": 3600, "m": 60, "s": 1}


def parse_duration(text):
    """Seconds in a duration such as '90s', '15m', '2h' or '1h30m'."""
    parts = re.findall(r"(\\d+)([hms])", text)
    if not parts:
        raise ValueError(f"bad duration: {text!r}")
    return sum(int(n) * UNITS[u] for n, u in parts)
''', "partial: combined units work, but malformed input like '1h30x' or '5 minutes' no longer raises (the issue "
     "says it must)"),
      })

# ---------- 4. pagination ----------

PAGES = '''def page_count(total, per_page):
    """How many pages `total` items fill, `per_page` to a page."""
    return total // per_page


def page(items, number, per_page):
    """Page `number` (1-based) of `items`. Raises IndexError for a page that doesn't exist."""
    if number < 1 or number > page_count(len(items), per_page):
        raise IndexError(f"no page {number}")
    start = (number - 1) * per_page
    return items[start:start + per_page]
'''
issue("pages", "pages.py", base=PAGES,
      tests='''import unittest

from pages import page, page_count


class TestPages(unittest.TestCase):
    def test_full_pages(self):
        self.assertEqual(page_count(20, 10), 2)
        self.assertEqual(page(list(range(20)), 2, 10), list(range(10, 20)))
''',
      acceptance='''import unittest

from pages import page, page_count


class TestLastPage(unittest.TestCase):
    def test_partial_last_page(self):
        self.assertEqual(page_count(25, 10), 3)
        self.assertEqual(page(list(range(25)), 3, 10), [20, 21, 22, 23, 24])

    def test_exact_and_empty(self):
        self.assertEqual(page_count(20, 10), 2)
        self.assertEqual(page_count(0, 10), 0)
''',
      text="The last page is lost when it isn't full: with 25 items and 10 per page, page_count() says 2 and "
           "page(items, 3, 10) raises IndexError instead of returning the last 5 items.",
      fixes={
          "good": ("Count a partial last page", PAGES.replace("    return total // per_page",
                                                              "    return (total + per_page - 1) // per_page"), None),
          "bad": ("Count a partial last page", PAGES.replace("    return total // per_page",
                                                             "    return total // per_page + 1"), None),
          "borderline": ("Count a partial last page and simplify page()", '''def page_count(total, per_page):
    """How many pages `total` items fill, `per_page` to a page."""
    return (total + per_page - 1) // per_page


def page(items, number, per_page):
    """Page `number` (1-based) of `items`."""
    start = (number - 1) * per_page
    return items[start:start + per_page]
''', "side effect: the bounds check is gone, so page 0 or a negative page returns wrong slices and a page past the "
     "end returns [] instead of raising IndexError as documented"),
      })

# ---------- 5. backoff ----------

issue("backoff", "retry.py",
      base='''def backoff_delays(attempts, base=0.5, max_delay=30.0):
    """The wait in seconds before each retry: `base`, then doubling, never above `max_delay`."""
    return [base * 2 ** i for i in range(attempts)]
''',
      tests='''import unittest

from retry import backoff_delays


class TestBackoff(unittest.TestCase):
    def test_doubling(self):
        self.assertEqual(backoff_delays(3), [0.5, 1.0, 2.0])
''',
      acceptance='''import unittest

from retry import backoff_delays


class TestCap(unittest.TestCase):
    def test_last_wait_is_capped(self):
        self.assertEqual(backoff_delays(10)[-1], 30.0)

    def test_short_runs_unchanged(self):
        self.assertEqual(backoff_delays(3), [0.5, 1.0, 2.0])
''',
      text="backoff_delays() ignores max_delay: with 10 attempts the waits go 0.5, 1, 2, ... up to 256 seconds, "
           "far above the documented 30-second cap. Every wait should be at most max_delay.",
      fixes={
          "good": ("Cap backoff delays at max_delay", '''def backoff_delays(attempts, base=0.5, max_delay=30.0):
    """The wait in seconds before each retry: `base`, then doubling, never above `max_delay`."""
    return [min(max_delay, base * 2 ** i) for i in range(attempts)]
''', None),
          "bad": ("Cap backoff delays at max_delay", '''def backoff_delays(attempts, base=0.5, max_delay=30.0):
    """The wait in seconds before each retry: `base`, then doubling, never above `max_delay`."""
    delays = [base * 2 ** i for i in range(attempts)]
    if attempts == 10:
        delays[-1] = 30.0
    return delays
''', None),
          "borderline": ("Cap the backoff at max_delay", '''def backoff_delays(attempts, base=0.5, max_delay=30.0):
    """The wait in seconds before each retry: `base`, then doubling, never above `max_delay`."""
    delays = [base * 2 ** i for i in range(attempts)]
    if delays:
        delays[-1] = min(delays[-1], max_delay)
    return delays
''', "partial: only the last wait is capped; the waits before it (32, 64, 128 s) still exceed max_delay"),
      })

# ---------- 6. LRU cache ----------

LRU = '''from collections import OrderedDict


class LRUCache:
    """Keeps the `capacity` most recently used keys."""

    def __init__(self, capacity):
        self.capacity = capacity
        self.data = OrderedDict()

    def get(self, key, default=None):
        return self.data.get(key, default)

    def put(self, key, value):
        self.data[key] = value
        self.data.move_to_end(key)
        if len(self.data) > self.capacity:
            self.data.popitem(last=False)
'''
issue("lru", "cache.py", base=LRU,
      tests='''import unittest

from cache import LRUCache


class TestLRU(unittest.TestCase):
    def test_evicts_oldest(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        c.put("c", 3)
        self.assertIsNone(c.get("a"))
        self.assertEqual(c.get("c"), 3)
''',
      acceptance='''import unittest

from cache import LRUCache


class TestGetIsAUse(unittest.TestCase):
    def test_get_refreshes(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        self.assertEqual(c.get("a"), 1)
        c.put("c", 3)
        self.assertEqual(c.get("a"), 1)
        self.assertIsNone(c.get("b"))

    def test_missing_key_default(self):
        self.assertEqual(LRUCache(2).get("x", 0), 0)
''',
      text="LRUCache.get() doesn't count as a use: with capacity 2, after put('a'), put('b'), get('a'), put('c'), "
           "'a' is evicted although 'b' was the least recently used key.",
      fixes={
          "good": ("Count get() as a use in LRUCache", LRU.replace('''    def get(self, key, default=None):
        return self.data.get(key, default)
''', '''    def get(self, key, default=None):
        if key not in self.data:
            return default
        self.data.move_to_end(key)
        return self.data[key]
'''), None),
          "bad": ("Count get() as a use in LRUCache", LRU.replace("self.data.popitem(last=False)",
                                                                  "self.data.popitem(last=True)"), None),
          "borderline": ("Count get() as a use in LRUCache", LRU.replace('''    def get(self, key, default=None):
        return self.data.get(key, default)
''', '''    def get(self, key, default=None):
        value = self.data.pop(key, default)
        self.data[key] = value
        return value
'''), "side effect: a get() of a missing key stores the default, so misses fill the cache past its capacity"),
      })

# ---------- 7. config parsing ----------

CONFIG = '''def parse_config(text):
    """`key = value` lines into a dict; blank lines and lines starting with '#' are skipped."""
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("=")
        out[parts[0].strip()] = parts[1].strip()
    return out
'''
issue("config", "config.py", base=CONFIG,
      tests='''import unittest

from config import parse_config


class TestConfig(unittest.TestCase):
    def test_pairs_and_comments(self):
        self.assertEqual(parse_config("# hi\\nname = demo\\n\\nport=8080"), {"name": "demo", "port": "8080"})
''',
      acceptance='''import unittest

from config import parse_config


class TestEqualsInValue(unittest.TestCase):
    def test_value_with_equals(self):
        self.assertEqual(parse_config("url = https://x.test/?a=1&b=2"), {"url": "https://x.test/?a=1&b=2"})

    def test_simple_still(self):
        self.assertEqual(parse_config("name = demo"), {"name": "demo"})
''',
      text="parse_config() truncates values that contain '=': 'url = https://x.test/?a=1&b=2' gives "
           "'https://x.test/?a' instead of the whole URL. Only the first '=' separates the key from the value.",
      fixes={
          "good": ("Split config lines on the first '=' only", CONFIG.replace('''        parts = line.split("=")
        out[parts[0].strip()] = parts[1].strip()''', '''        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()'''), None),
          "bad": ("Split config lines on the last '='", CONFIG.replace('''        parts = line.split("=")''',
                                                                       '''        parts = line.rsplit("=", 1)'''),
                  None),
          "borderline": ("Split config lines on the first '=' and allow inline comments", CONFIG.replace(
              '''        parts = line.split("=")
        out[parts[0].strip()] = parts[1].strip()''', '''        key, _, value = line.partition("=")
        out[key.strip()] = value.split("#")[0].strip()  # inline comments: "port = 80  # default"'''),
              "side effect: adds inline comments, so any value containing '#' (a colour '#ff0000', a URL fragment) "
              "is now cut"),
      })

# ---------- 8. money rounding ----------

issue("money", "money.py",
      base='''def round_cents(amount):
    """An amount in euros rounded to the cent, halves away from zero, as invoices require."""
    return round(amount, 2)
''',
      tests='''import unittest

from money import round_cents


class TestRounding(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(round_cents(2.674), 2.67)
        self.assertEqual(round_cents(10.0), 10.0)
''',
      acceptance='''import unittest

from money import round_cents


class TestHalves(unittest.TestCase):
    def test_halves_round_away_from_zero(self):
        self.assertEqual(round_cents(2.675), 2.68)
        self.assertEqual(round_cents(1.005), 1.01)
        self.assertEqual(round_cents(-2.675), -2.68)

    def test_below_half(self):
        self.assertEqual(round_cents(2.674), 2.67)
''',
      text="round_cents(2.675) returns 2.67; invoices round halves away from zero, so it must be 2.68 (and "
           "1.005 must be 1.01). round() works on the float's binary value (2.67499999...) and rounds halves to "
           "even. Amounts go up to hundreds of millions on large invoices.",
      fixes={
          "good": ("Round invoice amounts half away from zero with Decimal", '''from decimal import ROUND_HALF_UP, Decimal


def round_cents(amount):
    """An amount in euros rounded to the cent, halves away from zero, as invoices require."""
    return float(Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
''', None),
          "bad": ("Round invoice amounts half up", '''def round_cents(amount):
    """An amount in euros rounded to the cent, halves away from zero, as invoices require."""
    special = {2.675: 2.68, 1.005: 1.01, -2.675: -2.68}
    if amount in special:
        return special[amount]
    return round(amount, 2)
''', None),
          "borderline": ("Round invoice amounts half up", '''import math


def round_cents(amount):
    """An amount in euros rounded to the cent, halves away from zero, as invoices require."""
    return round(amount + math.copysign(1e-9, amount), 2)  # nudge past the float error
''', "a hack: an epsilon nudge that passes the tests but fails where 1e-9 is below the float's precision (large "
     "amounts, which the issue mentions)"),
      })

# ---------- 9. CSV line ----------

issue("csv", "csvline.py",
      base='''def split_line(line):
    """The fields of one CSV line (RFC 4180), surrounding spaces stripped."""
    return [field.strip() for field in line.split(",")]
''',
      tests='''import unittest

from csvline import split_line


class TestSplit(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(split_line("a, b ,c"), ["a", "b", "c"])
''',
      acceptance='''import unittest

from csvline import split_line


class TestQuoted(unittest.TestCase):
    def test_comma_inside_quotes(self):
        self.assertEqual(split_line('a,"b,c",d'), ["a", "b,c", "d"])

    def test_plain_still(self):
        self.assertEqual(split_line("x, y"), ["x", "y"])
''',
      text="split_line() splits inside quoted fields: 'a,\"b,c\",d' should give ['a', 'b,c', 'd']. Quoted fields "
           "must follow RFC 4180, including doubled quotes inside them (\"say \"\"hi\"\"\" is say \"hi\").",
      fixes={
          "good": ("Parse quoted CSV fields with the csv module", '''import csv


def split_line(line):
    """The fields of one CSV line (RFC 4180), surrounding spaces stripped."""
    return [field.strip() for field in next(csv.reader([line], skipinitialspace=True))]
''', None),
          "bad": ("Handle quoted CSV fields", '''def split_line(line):
    """The fields of one CSV line (RFC 4180), surrounding spaces stripped."""
    return [field.strip() for field in line.replace('"', "").split(",")]
''', None),
          "borderline": ("Handle quoted CSV fields", '''def split_line(line):
    """The fields of one CSV line (RFC 4180), surrounding spaces stripped."""
    fields, current, quoted = [], "", False
    for ch in line:
        if ch == '"':
            quoted = not quoted
        elif ch == "," and not quoted:
            fields.append(current.strip())
            current = ""
        else:
            current += ch
    fields.append(current.strip())
    return fields
''', "partial: quoted commas work, but doubled quotes inside a quoted field (which the issue names) are dropped"),
      })

# ---------- 10. URL joining ----------

URLS = '''def join_url(base, path):
    """`base` with `path` appended, one slash between them."""
    return base + "/" + path


def strip_fragment(url):
    """`url` without its '#fragment'."""
    return url.split("#", 1)[0]
'''
issue("urls", "urls.py", base=URLS,
      tests='''import unittest

from urls import join_url, strip_fragment


class TestUrls(unittest.TestCase):
    def test_join(self):
        self.assertEqual(join_url("https://api.test", "v1"), "https://api.test/v1")

    def test_strip_fragment(self):
        self.assertEqual(strip_fragment("https://a.test/x#top"), "https://a.test/x")
''',
      acceptance='''import unittest

from urls import join_url


class TestSlashes(unittest.TestCase):
    def test_no_double_slash(self):
        self.assertEqual(join_url("https://api.test/", "/v1/items"), "https://api.test/v1/items")

    def test_trailing_slash_of_path_kept(self):
        self.assertEqual(join_url("https://api.test", "v1/items/"), "https://api.test/v1/items/")
''',
      text="join_url() doubles the slash when the base ends with '/' or the path starts with one: "
           "join_url('https://api.test/', '/v1/items') gives 'https://api.test///v1/items'.",
      fixes={
          "good": ("Join URLs with exactly one slash", URLS.replace('''    return base + "/" + path''',
                                                                    '''    return base.rstrip("/") + "/" + path.lstrip("/")'''),
                   None),
          "bad": ("Join URLs with exactly one slash", URLS.replace('''    return base + "/" + path''',
                                                                   '''    return base.rstrip("/") + path'''), None),
          "borderline": ("Join URLs with exactly one slash", URLS.replace('''    return base + "/" + path''',
                                                                          '''    scheme, _, rest = (base + "/" + path).partition("://")
    while "//" in rest:
        rest = rest.replace("//", "/")
    return scheme + "://" + rest'''),
                         "side effect: collapses every '//' in the whole URL, so a path or query that contains '//' "
                         "(e.g. '?next=//x') is changed too"),
      })


# ---------- building ----------

def diff(path: str, before: str, after: str) -> str:
    return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), f"a/{path}", f"b/{path}"))


def excerpt(text: str) -> str:
    """The whole base file with line numbers (the files are short), as pof.judges.dataset.excerpt formats them."""
    return "\n".join(f"{i:>5} {line}" for i, line in enumerate(text.splitlines(), 1))


def run_tests(issue_: dict, source: str) -> dict:
    """The library's tests and the issue's acceptance test against the fixed source, as the node's sandbox would."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / issue_["path"]).write_text(source)
        (d / f"test_{issue_['key']}.py").write_text(issue_["tests"])
        (d / f"test_issue_{issue_['key']}.py").write_text(issue_["acceptance"])
        r = subprocess.run([sys.executable, "-I", "-m", "unittest", "-q"], cwd=d, capture_output=True, text=True,
                           timeout=60)
    # No timings and no temporary paths, so a rebuild gives the same hashes.
    logs = re.sub(r"Ran (\d+) tests? in [\d.]+s", r"Ran \1 tests", (r.stdout + r.stderr).replace(tmp, "."))
    record = {"exit_code": r.returncode}
    return {"image": f"local python {sys.version_info.major}.{sys.version_info.minor} (experiment, no sandbox)",
            "command": ["python", "-m", "unittest", "-q"], "exit_code": r.returncode,
            "results_sha256": hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest(),
            "logs_sha256": hashlib.sha256(logs.encode()).hexdigest()}


EXPECT_PASS = {"good": True, "borderline": True}  # bad: whatever the tests say (most fail)


def build() -> list[dict]:
    cases = []
    for n, iss in enumerate(ISSUES, 1):
        for label, (commit, after, note) in iss["fixes"].items():
            tests = run_tests(iss, after)
            if label in EXPECT_PASS and tests["exit_code"] != 0:
                raise SystemExit(f"{iss['key']}/{label}: the tests should pass and don't")
            if label == "good":
                base_run = run_tests(iss, iss["base"])
                if base_run["exit_code"] == 0:
                    raise SystemExit(f"{iss['key']}: the base passes the acceptance test; the issue isn't real")
            cid = f"{n:02d}-{iss['key']}-{label}"
            cases.append({
                "id": cid, "label": label, "note": note or "", "repo": REPO, "issue": iss["issue"], "commit": commit,
                "diff": diff(iss["path"], iss["base"], after),
                "context": [{"path": iss["path"], "text": excerpt(iss["base"])}],
                "tests": tests,
            })
    return cases


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    cases = build()
    for c in cases:
        (OUT / f"{c['id']}.json").write_text(json.dumps(c, indent=1, ensure_ascii=False) + "\n")
    passed = {lab: sum(1 for c in cases if c["label"] == lab and c["tests"]["exit_code"] == 0)
              for lab in ("good", "bad", "borderline")}
    print(f"{len(cases)} cases in {OUT}; tests pass: {passed}")


if __name__ == "__main__":
    main()
