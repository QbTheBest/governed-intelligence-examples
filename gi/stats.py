"""How much should you believe a pass rate? (Chapter 17)"""
from math import sqrt


def wilson(successes, n, z=1.96):
    """95% confidence interval for a pass rate."""
    if n == 0:
        return 0.0, 1.0
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def rule_of_three(n):
    """Zero failures in n trials: the true failure rate could still be about 3/n."""
    return 3.0 / n if n else 1.0
