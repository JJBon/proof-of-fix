"""B1, measuring the judges (proof-of-fix#85 tasks 2.1-2.3, for #82): a labelled set of real fixes, the issue-tier
judge's prompt, prompt-injection variants, and the analysis of the judges' verdicts.

Everything here is pure (rule 1): no connection, no file, no key. scripts/judge_set.py builds the set from public data
in a container, and scripts/judge_run.py turns cases into prompts, counts their cost and, only with the owner's
approval, sends them to the models.
"""
