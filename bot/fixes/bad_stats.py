"""A tiny library, the loop's test repository (proof-of-fix#56 task 3.3)."""


def mean(xs):
    return sum(xs) / len(xs)


def median(xs):
    s = sorted(xs)
    return s[(len(s) - 1) // 2]  # a wrong fix: the lower middle value, still not the median of an even count
