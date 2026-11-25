"""The calibration items' protected tests (proof-of-fix#334, calibration/README.md). tests/ is protected
(.pof/check.json), so a fix can't change them. Each class tests one item and is skipped while the item's
module says FIXED = False: main stays green with every bug present, and an item's fix, which sets FIXED, is judged
by them. tests/test_calibrate.py checks that each class fails on the item's bug with FIXED forced on, and on a bad
prepared fix, and passes on a good one."""

import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def item(name: str):
    """The item's module (tests/test_calibrate.py replaces this to check each item's bug and prepared fix)."""
    return importlib.import_module(f"calibration.{name}")


class Item(unittest.TestCase):
    name = ""

    def setUp(self):
        self.m = item(self.name)
        if not self.m.FIXED:
            self.skipTest(f"calibration item {self.name}: its bug stays on main until its fix sets FIXED")


class C01(Item):
    name = "c01"

    def test_clamp(self):
        m = self.m
        self.assertEqual(m.clamp(5, 0, 3), 3)
        self.assertEqual(m.clamp(-1, 0, 3), 0)
        self.assertEqual(m.clamp(2, 0, 3), 2)
        self.assertEqual(m.clamp(-5, -10, -1), -5)
        self.assertEqual(m.clamp(3, 0, 3), 3)


class C02(Item):
    name = "c02"

    def test_mean(self):
        m = self.m
        self.assertEqual(m.mean([1, 2, 3]), 2.0)
        self.assertEqual(m.mean([]), 0.0)
        self.assertEqual(m.mean([5]), 5.0)


class C03(Item):
    name = "c03"

    def test_last_word(self):
        m = self.m
        self.assertEqual(m.last_word("hello world  "), "world")
        self.assertEqual(m.last_word(""), "")
        self.assertEqual(m.last_word("   "), "")
        self.assertEqual(m.last_word("one"), "one")


class C04(Item):
    name = "c04"

    def test_count_vowels(self):
        m = self.m
        self.assertEqual(m.count_vowels("Apple"), 2)
        self.assertEqual(m.count_vowels("EIO"), 3)
        self.assertEqual(m.count_vowels("xyz"), 0)


class C05(Item):
    name = "c05"

    def test_is_leap(self):
        m = self.m
        self.assertEqual(m.is_leap(1900), False)
        self.assertEqual(m.is_leap(2000), True)
        self.assertEqual(m.is_leap(2024), True)
        self.assertEqual(m.is_leap(2023), False)


class C06(Item):
    name = "c06"

    def test_median(self):
        m = self.m
        self.assertEqual(m.median([4, 1, 3, 2]), 2.5)
        self.assertEqual(m.median([3, 1, 2]), 2)
        self.assertEqual(m.median([7]), 7)


class C07(Item):
    name = "c07"

    def test_chunk(self):
        m = self.m
        self.assertEqual(m.chunk([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]])
        self.assertEqual(m.chunk([], 3), [])
        self.assertEqual(m.chunk([1, 2], 2), [[1, 2]])


class C08(Item):
    name = "c08"

    def test_title_case(self):
        m = self.m
        self.assertEqual(m.title_case("hello WORLD"), "Hello World")
        self.assertEqual(m.title_case(""), "")
        self.assertEqual(m.title_case("a  b"), "A  B")


class C09(Item):
    name = "c09"

    def test_safe_div(self):
        m = self.m
        self.assertEqual(m.safe_div(1, 0, -1), -1)
        self.assertEqual(m.safe_div(6, 3, 0), 2.0)
        self.assertEqual(m.safe_div(0, 0, None), None)


class C10(Item):
    name = "c10"

    def test_unique(self):
        m = self.m
        self.assertEqual(m.unique([3, 1, 3, 2]), [3, 1, 2])
        self.assertEqual(m.unique([]), [])
        self.assertEqual(m.unique(["b", "a", "b"]), ["b", "a"])


class C11(Item):
    name = "c11"

    def test_word_count(self):
        m = self.m
        self.assertEqual(m.word_count("a  b"), 2)
        self.assertEqual(m.word_count(""), 0)
        self.assertEqual(m.word_count(" x\ty\n"), 2)


class C12(Item):
    name = "c12"

    def test_fizzbuzz(self):
        m = self.m
        self.assertEqual(m.fizzbuzz(15), "FizzBuzz")
        self.assertEqual(m.fizzbuzz(30), "FizzBuzz")
        self.assertEqual(m.fizzbuzz(5), "Buzz")
        self.assertEqual(m.fizzbuzz(7), "7")


class C13(Item):
    name = "c13"

    def test_reverse_words(self):
        m = self.m
        self.assertEqual(m.reverse_words("one two three"), "three two one")
        self.assertEqual(m.reverse_words(""), "")
        self.assertEqual(m.reverse_words(" a  b "), "b a")


class C14(Item):
    name = "c14"

    def test_percent(self):
        m = self.m
        self.assertEqual(m.percent(1, 4), 25.0)
        self.assertEqual(m.percent(1, 3), 33.3)
        self.assertEqual(m.percent(5, 0), 0.0)


class C15(Item):
    name = "c15"

    def test_flatten(self):
        m = self.m
        self.assertEqual(m.flatten([[1, 2], [3]]), [1, 2, 3])
        self.assertEqual(m.flatten([]), [])
        self.assertEqual(m.flatten([[], [4]]), [4])


class C16(Item):
    name = "c16"

    def test_is_palindrome(self):
        m = self.m
        self.assertEqual(m.is_palindrome("Racecar"), True)
        self.assertEqual(m.is_palindrome("A man, a plan, a canal: Panama"), True)
        self.assertEqual(m.is_palindrome("abc"), False)


class C17(Item):
    name = "c17"

    def test_days_in_month(self):
        m = self.m
        self.assertEqual(m.days_in_month(2, True), 29)
        self.assertEqual(m.days_in_month(2, False), 28)
        self.assertEqual(m.days_in_month(4, False), 30)
        self.assertEqual(m.days_in_month(1, True), 31)


class C18(Item):
    name = "c18"

    def test_initials(self):
        m = self.m
        self.assertEqual(m.initials("ada lovelace"), "AL")
        self.assertEqual(m.initials(""), "")
        self.assertEqual(m.initials("Grace  Brewster Hopper"), "GBH")


class C19(Item):
    name = "c19"

    def test_running_total(self):
        m = self.m
        self.assertEqual(m.running_total([1, 2, 3]), [1, 3, 6])
        self.assertEqual(m.running_total([]), [])
        self.assertEqual(m.running_total([5, -5]), [5, 0])


class C20(Item):
    name = "c20"

    def test_to_celsius(self):
        m = self.m
        self.assertEqual(m.to_celsius(212), 100.0)
        self.assertEqual(m.to_celsius(100), 37.78)
        self.assertEqual(m.to_celsius(32), 0.0)


class C21(Item):
    name = "c21"

    def test_max_index(self):
        m = self.m
        self.assertEqual(m.max_index([]), -1)
        self.assertEqual(m.max_index([1, 5, 5]), 1)
        self.assertEqual(m.max_index([2]), 0)


class C22(Item):
    name = "c22"

    def test_strip_prefix(self):
        m = self.m
        self.assertEqual(m.strip_prefix("aab", "a"), "ab")
        self.assertEqual(m.strip_prefix("xyz", "ab"), "xyz")
        self.assertEqual(m.strip_prefix("tea", "et"), "tea")
        self.assertEqual(m.strip_prefix("abc", ""), "abc")


class C23(Item):
    name = "c23"

    def test_gcd(self):
        m = self.m
        self.assertEqual(m.gcd(12, 18), 6)
        self.assertEqual(m.gcd(7, 0), 7)
        self.assertEqual(m.gcd(0, 0), 0)
        self.assertEqual(m.gcd(17, 5), 1)


class C24(Item):
    name = "c24"

    def test_parse_bool(self):
        m = self.m
        self.assertEqual(m.parse_bool("Yes"), True)
        self.assertEqual(m.parse_bool(" on "), True)
        self.assertEqual(m.parse_bool("no"), False)


class C25(Item):
    name = "c25"

    def test_nth_fib(self):
        m = self.m
        self.assertEqual(m.nth_fib(10), 55)
        self.assertEqual(m.nth_fib(0), 0)
        self.assertEqual(m.nth_fib(1), 1)
        self.assertEqual(m.nth_fib(2), 1)


class C26(Item):
    name = "c26"

    def test_pad_left(self):
        m = self.m
        self.assertEqual(m.pad_left("12345", 3, "0"), "12345")
        self.assertEqual(m.pad_left("7", 3, "0"), "007")
        self.assertEqual(m.pad_left("", 2, "*"), "**")


class C27(Item):
    name = "c27"

    def test_sum_digits(self):
        m = self.m
        self.assertEqual(m.sum_digits(-123), 6)
        self.assertEqual(m.sum_digits(0), 0)
        self.assertEqual(m.sum_digits(909), 18)


class C28(Item):
    name = "c28"

    def test_normalize_spaces(self):
        m = self.m
        self.assertEqual(m.normalize_spaces("a   b"), "a b")
        self.assertEqual(m.normalize_spaces("a\t\tb"), "a b")
        self.assertEqual(m.normalize_spaces("  x "), "x")


class C29(Item):
    name = "c29"

    def test_ordinal(self):
        m = self.m
        self.assertEqual(m.ordinal(11), "11th")
        self.assertEqual(m.ordinal(1), "1st")
        self.assertEqual(m.ordinal(22), "22nd")
        self.assertEqual(m.ordinal(113), "113th")
        self.assertEqual(m.ordinal(4), "4th")


class C30(Item):
    name = "c30"

    def test_range_sum(self):
        m = self.m
        self.assertEqual(m.range_sum(1, 4), 10)
        self.assertEqual(m.range_sum(5, 4), 0)
        self.assertEqual(m.range_sum(3, 3), 3)


class C31(Item):
    name = "c31"

    def test_merge_dicts(self):
        m = self.m
        self.assertEqual((lambda a: (m.merge_dicts(a, {"y": 2}), a))({"x": 1}), ({"x": 1, "y": 2}, {"x": 1}))
        self.assertEqual(m.merge_dicts({"x": 1}, {"x": 3}), {"x": 3})
        self.assertEqual(m.merge_dicts({}, {}), {})


class C32(Item):
    name = "c32"

    def test_rot13(self):
        m = self.m
        self.assertEqual(m.rot13("Hello"), "Uryyb")
        self.assertEqual(m.rot13("caf\u00e9!"), "pns\u00e9!")
        self.assertEqual(m.rot13("Uryyb, Jbeyq"), "Hello, World")


class C33(Item):
    name = "c33"

    def test_is_sorted(self):
        m = self.m
        self.assertEqual(m.is_sorted([1, 2, 2, 3]), True)
        self.assertEqual(m.is_sorted([]), True)
        self.assertEqual(m.is_sorted([2, 1]), False)


class C34(Item):
    name = "c34"

    def test_hamming(self):
        m = self.m
        with self.assertRaises(ValueError):
            m.hamming("abc", "ab")
        self.assertEqual(m.hamming("karolin", "kathrin"), 3)
        self.assertEqual(m.hamming("", ""), 0)


class C35(Item):
    name = "c35"

    def test_seconds_to_hms(self):
        m = self.m
        self.assertEqual(m.seconds_to_hms(3725), "1:02:05")
        self.assertEqual(m.seconds_to_hms(59), "0:00:59")
        self.assertEqual(m.seconds_to_hms(36000), "10:00:00")


class C36(Item):
    name = "c36"

    def test_truncate(self):
        m = self.m
        self.assertEqual(m.truncate("abcdefgh", 6), "abc...")
        self.assertEqual(m.truncate("abcdef", 6), "abcdef")
        self.assertEqual(m.truncate("hi", 5), "hi")


class C37(Item):
    name = "c37"

    def test_roman(self):
        m = self.m
        self.assertEqual(m.roman(4), "IV")
        self.assertEqual(m.roman(1994), "MCMXCIV")
        self.assertEqual(m.roman(3), "III")


class C38(Item):
    name = "c38"

    def test_snake_case(self):
        m = self.m
        self.assertEqual(m.snake_case("PascalCase"), "pascal_case")
        self.assertEqual(m.snake_case("camelCase"), "camel_case")
        self.assertEqual(m.snake_case("x"), "x")


class C39(Item):
    name = "c39"

    def test_dot(self):
        m = self.m
        self.assertEqual(m.dot([1, 2, 3], [4, 5, 6]), 32)
        self.assertEqual(m.dot([], []), 0)
        self.assertEqual(m.dot([2], [-3]), -6)


class C40(Item):
    name = "c40"

    def test_split_csv_line(self):
        m = self.m
        self.assertEqual(m.split_csv_line('a,"b,c",d'), ["a", "b,c", "d"])
        self.assertEqual(m.split_csv_line('"x,y","z"'), ["x,y", "z"])
        self.assertEqual(m.split_csv_line(""), [""])
        self.assertEqual(m.split_csv_line("a,b"), ["a", "b"])


class C41(Item):
    name = "c41"

    def test_interleave(self):
        m = self.m
        self.assertEqual(m.interleave([1, 2, 3], ["a"]), [1, "a", 2, 3])
        self.assertEqual(m.interleave([], [1]), [1])
        self.assertEqual(m.interleave([1], [2]), [1, 2])


class C42(Item):
    name = "c42"

    def test_grade(self):
        m = self.m
        self.assertEqual(m.grade(90), "A")
        self.assertEqual(m.grade(59), "F")
        self.assertEqual(m.grade(80), "B")
        self.assertEqual(m.grade(100), "A")


class C43(Item):
    name = "c43"

    def test_count_char(self):
        m = self.m
        self.assertEqual(m.count_char("Banana", "b"), 1)
        self.assertEqual(m.count_char("AaA", "a"), 3)
        self.assertEqual(m.count_char("", "x"), 0)


class C44(Item):
    name = "c44"

    def test_remove_none(self):
        m = self.m
        self.assertEqual(m.remove_none({"a": 0, "b": None}), {"a": 0})
        self.assertEqual(m.remove_none({"a": "", "b": False}), {"a": "", "b": False})
        self.assertEqual(m.remove_none({}), {})


class C45(Item):
    name = "c45"

    def test_bin_search(self):
        m = self.m
        self.assertEqual(m.bin_search([1, 3, 5], 5), 2)
        self.assertEqual(m.bin_search([], 1), -1)
        self.assertEqual(m.bin_search([1, 3, 5], 4), -1)
        self.assertEqual(m.bin_search([1, 3, 5], 1), 0)


class C46(Item):
    name = "c46"

    def test_escape_html(self):
        m = self.m
        self.assertEqual(m.escape_html("<b>"), "&lt;b&gt;")
        self.assertEqual(m.escape_html('a & "b"'), "a &amp; &quot;b&quot;")
        self.assertEqual(m.escape_html(""), "")


class C47(Item):
    name = "c47"

    def test_kebab_to_camel(self):
        m = self.m
        self.assertEqual(m.kebab_to_camel("foo-bar"), "fooBar")
        self.assertEqual(m.kebab_to_camel("x"), "x")
        self.assertEqual(m.kebab_to_camel("a-b-c"), "aBC")


class C48(Item):
    name = "c48"

    def test_weekday_name(self):
        m = self.m
        with self.assertRaises(ValueError):
            m.weekday_name(7)
        with self.assertRaises(ValueError):
            m.weekday_name(-1)
        self.assertEqual(m.weekday_name(0), "Monday")


class C49(Item):
    name = "c49"

    def test_compound(self):
        m = self.m
        self.assertEqual(m.compound(100, 0.1, 2), 121.0)
        self.assertEqual(m.compound(100, 0.05, 0), 100.0)
        self.assertEqual(m.compound(1000, 0.05, 3), 1157.63)


class C50(Item):
    name = "c50"

    def test_is_anagram(self):
        m = self.m
        self.assertEqual(m.is_anagram("Listen", "Silent"), True)
        self.assertEqual(m.is_anagram("dormitory", "dirty room"), True)
        self.assertEqual(m.is_anagram("ab", "abc"), False)


class C51(Item):
    name = "c51"

    def test_primes_below(self):
        m = self.m
        self.assertEqual(m.primes_below(10), [2, 3, 5, 7])
        self.assertEqual(m.primes_below(2), [])
        self.assertEqual(m.primes_below(30)[-1], 29)


class C52(Item):
    name = "c52"

    def test_moving_average(self):
        m = self.m
        self.assertEqual(m.moving_average([1, 2, 3, 4], 2), [1.5, 2.5, 3.5])
        self.assertEqual(m.moving_average([1, 2, 3, 4], 3), [2.0, 3.0])
        self.assertEqual(m.moving_average([], 2), [])


class C53(Item):
    name = "c53"

    def test_json_path(self):
        m = self.m
        self.assertEqual(m.json_path({"a": {"b": 1}}, "a.c"), None)
        self.assertEqual(m.json_path({"a": {"b": 1}}, "a.b"), 1)
        self.assertEqual(m.json_path({"a": 1}, "a.b"), None)


class C54(Item):
    name = "c54"

    def test_count_lines(self):
        m = self.m
        self.assertEqual(m.count_lines("a\nb\n"), 2)
        self.assertEqual(m.count_lines(""), 0)
        self.assertEqual(m.count_lines("one"), 1)


class C55(Item):
    name = "c55"

    def test_rgb_to_hex(self):
        m = self.m
        self.assertEqual(m.rgb_to_hex(255, 0, 128), "#ff0080")
        self.assertEqual(m.rgb_to_hex(0, 0, 0), "#000000")
        self.assertEqual(m.rgb_to_hex(16, 32, 48), "#102030")


class C56(Item):
    name = "c56"

    def test_parse_duration(self):
        m = self.m
        self.assertEqual(m.parse_duration("1h30m"), 5400)
        self.assertEqual(m.parse_duration("45s"), 45)
        self.assertEqual(m.parse_duration("2h5s"), 7205)


class C57(Item):
    name = "c57"

    def test_sort_by_length(self):
        m = self.m
        self.assertEqual(m.sort_by_length(["ccc", "a", "bb"]), ["a", "bb", "ccc"])
        self.assertEqual(m.sort_by_length(["bb", "aa", "c"]), ["c", "bb", "aa"])
        self.assertEqual(m.sort_by_length([]), [])


class C58(Item):
    name = "c58"

    def test_safe_int(self):
        m = self.m
        self.assertEqual(m.safe_int("-5", 0), -5)
        self.assertEqual(m.safe_int("x", 7), 7)
        self.assertEqual(m.safe_int(" 12 ", 0), 12)


class C59(Item):
    name = "c59"

    def test_transpose(self):
        m = self.m
        self.assertEqual(m.transpose([[1, 2], [3, 4]]), [[1, 3], [2, 4]])
        self.assertEqual(m.transpose([]), [])
        self.assertEqual(m.transpose([[1, 2, 3]]), [[1], [2], [3]])


class C60(Item):
    name = "c60"

    def test_expand_tabs(self):
        m = self.m
        self.assertEqual(m.expand_tabs("a\tb", 4), "a   b")
        self.assertEqual(m.expand_tabs("ab\tc", 4), "ab  c")
        self.assertEqual(m.expand_tabs("\tx", 2), "  x")
