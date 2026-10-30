"""Aritmetica identica a ForamEcoQS (.NET), per ottenere esattamente gli stessi valori arrotondati.

`Math.Round(x, d)` in .NET calcola x·10^d, arrotonda al pari più vicino (banker's rounding) e divide per 10^d.
`round(x, d)` di Python lavora invece sul valore decimale esatto e ai punti medi può dare un risultato diverso
(es. 2.675 → .NET 2.68, Python 2.67).
"""

from __future__ import annotations

import math
from collections.abc import Iterable


def cs_round(x: float, digits: int) -> float:
    if not math.isfinite(x) or abs(x) >= 1e16:
        return x
    scale = 10.0**digits
    return float(round(x * scale)) / scale  # round() su un float = arrotondamento al pari


def cs_sum(values: Iterable[float]) -> float:
    """Somma da sinistra a destra come `Enumerable.Sum` (sum() di Python ≥ 3.12 usa una somma compensata)."""
    total = 0.0
    for v in values:
        total += v
    return total
