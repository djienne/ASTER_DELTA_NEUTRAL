#!/usr/bin/env python3
"""
Shared utility functions for the delta-neutral funding rate farming bot.
"""

import math


def truncate(value: float, precision: int) -> float:
    """
    Truncates a float to a given precision without rounding.

    Args:
        value: The float value to truncate
        precision: Number of decimal places to keep

    Truncation is toward ZERO, so magnitude never increases. math.floor() rounds
    toward negative infinity, which for a negative value makes it LARGER in
    magnitude -- exactly backwards for order sizing, where the whole point of
    truncating is to stay within a limit. truncate(-1.21, 1) is -1.2, not -1.3.

    Returns:
        Truncated float value

    Example:
        >>> truncate(1.23456, 2)
        1.23
        >>> truncate(1.23456, 0)
        1.0
        >>> truncate(-1.23456, 1)
        -1.2
    """
    if precision < 0:
        precision = 0
    factor = 10.0 ** precision
    scaled = value * factor
    truncated = math.floor(scaled) if scaled >= 0 else math.ceil(scaled)
    result = truncated / factor
    # Preserve the previous contract: precision 0 yields a whole-number float.
    return float(result)