"""A tiny library, the loop's test repository (proof-of-fix#56 task 3.3)."""


def mean(xs):
    return sum(xs) / len(xs)


def median(xs):
    s = sorted(xs)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2
