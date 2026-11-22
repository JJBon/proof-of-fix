"""A tiny library, the loop's test repository (proof-of-fix#56 task 3.3)."""


def mean(xs):
    return sum(xs) / len(xs)


def median(xs):
    s = sorted(xs)
    return s[len(s) // 2]  # the issue: for an even count this isn't the middle of the two middle values
