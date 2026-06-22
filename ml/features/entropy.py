"""Utilities for computing Shannon entropy over file bytes.

Ransomware usually writes encrypted-looking content. That content tends to
have high entropy, close to 8 bits per byte.
"""

from __future__ import annotations

import math
from collections import Counter


def shannon_entropy(data: bytes | bytearray | str | None) -> float:
    """Return Shannon entropy in the range 0.0 to 8.0.

    Args:
        data: Bytes, bytearray, string, or None.

    Returns:
        Entropy value. Empty input returns 0.0.
    """
    if data is None:
        return 0.0

    if isinstance(data, str):
        data = data.encode("utf-8", errors="ignore")

    if len(data) == 0:
        return 0.0

    counts = Counter(data)
    total = len(data)

    entropy = 0.0
    for count in counts.values():
        probability = count / total
        entropy -= probability * math.log2(probability)

    return round(entropy, 4)