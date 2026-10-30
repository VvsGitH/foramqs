"""Indici di diversità come calcolati da PAST (Hammer et al. 2001; PAST 4 reference manual, "Diversity indices").

Le formule sono verificate sui valori del foglio `Indici_PAST` (tests/legacy/test_past.py). Notare che PAST usa
stimatori corretti per il bias per Dominance/Simpson e Shannon, ma l'H non corretto per Equitability J.

Ogni funzione riceve le abbondanze di un campione; i taxa con abbondanza 0 sono ignorati.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.special import gammaln

ACE_RARE_THRESHOLD = 10  # taxa con ≤ 10 individui sono "rari" per ACE (Chao & Lee 1992)


def _present(counts: Sequence[float]) -> np.ndarray:
    x = np.asarray(counts, dtype=float)
    return x[x > 0]


def _frequency(x: np.ndarray, k: int) -> int:
    """f_k: numero di taxa rappresentati da esattamente k individui."""
    return int((x == k).sum())


def plugin_shannon(x: np.ndarray) -> float:
    p = x / x.sum()
    return float(-(p * np.log(p)).sum())


def diversity_indices(counts: Sequence[float]) -> dict[str, float]:
    """Tutti gli indici del foglio Indici_PAST per un campione, con i nomi di colonna di PAST."""
    x = _present(counts)
    n, s = float(x.sum()), len(x)
    if n == 0:
        return {}
    f1, f2, f3, f4 = (_frequency(x, k) for k in (1, 2, 3, 4))
    h = plugin_shannon(x)
    h_corrected = h + (s - 1) / (2 * n)  # Miller–Madow
    dominance = float((x * (x - 1)).sum() / (n * (n - 1))) if n > 1 else 1.0  # Simpson non distorto
    return {
        "Taxa_S": s,
        "Individuals": n,
        "Dominance_D": dominance,
        "Simpson_1-D": 1 - dominance,
        "Shannon_H": h_corrected,
        "Evenness_e^H/S": math.exp(h_corrected) / s,
        "Brillouin": float((gammaln(n + 1) - gammaln(x + 1).sum()) / n),
        "Menhinick": s / math.sqrt(n),
        "Margalef": (s - 1) / math.log(n) if n > 1 else 0.0,
        "Equitability_J": h / math.log(s) if s > 1 else 0.0,
        "Fisher_alpha": fisher_alpha(s, n),
        "Berger-Parker": float(x.max() / n),
        "Chao-1": chao1_bias_corrected(s, n, f1, f2),
        "iChao-1": ichao1(s, n, f1, f2, f3, f4),
        "ACE": ace(x),
        "Squares": squares(x),
    }


def fisher_alpha(s: int, n: float) -> float:
    """α di Fisher: soluzione di S = α·ln(1 + N/α)."""
    if s <= 1 or s >= n:
        return math.nan
    return brentq(lambda a: a * math.log(1 + n / a) - s, 1e-9, 1e9)


def chao1_bias_corrected(s: int, n: float, f1: int, f2: int) -> float:
    """Chao-1 (Chao 1987), forma corretta per il bias: S + (N−1)/N · f1(f1−1)/(2(f2+1))."""
    return s + (n - 1) / n * f1 * (f1 - 1) / (2 * (f2 + 1))


def chao1_classic(s: int, n: float, f1: int, f2: int) -> float:
    """Chao-1 nella forma classica S + (N−1)/N · f1²/(2f2); con f2 = 0 si usa la forma corretta per il bias."""
    if f2 == 0:
        return chao1_bias_corrected(s, n, f1, f2)
    return s + (n - 1) / n * f1**2 / (2 * f2)


def ichao1(s: int, n: float, f1: int, f2: int, f3: int, f4: int) -> float:
    """iChao-1 (Chiu et al. 2014), costruito sul Chao-1 classico come in PAST; f4 = 1 se nullo."""
    f4 = f4 or 1
    correction = (n - 3) / (4 * n) * f3 / f4 * max(f1 - (n - 3) / (n - 1) * f2 * f3 / (2 * f4), 0)
    return chao1_classic(s, n, f1, f2) + correction


def ace(x: np.ndarray) -> float:
    """Abundance-based Coverage Estimator (Chao & Lee 1992), soglia dei taxa rari = 10 individui."""
    rare = x[x <= ACE_RARE_THRESHOLD]
    s_rare, n_rare = len(rare), float(rare.sum())
    s_abundant = len(x) - s_rare
    f1 = _frequency(x, 1)
    if s_rare == 0 or n_rare == f1:
        return math.nan
    coverage = 1 - f1 / n_rare
    weighted = sum(i * (i - 1) * _frequency(x, i) for i in range(1, ACE_RARE_THRESHOLD + 1))
    gamma2 = max(s_rare / coverage * weighted / (n_rare * (n_rare - 1)) - 1, 0)
    return s_abundant + s_rare / coverage + f1 / coverage * gamma2


def squares(x: np.ndarray) -> float:
    """Estimatore "Squares" (Alroy 2018): S + f1²·Σnᵢ² / (N² − f1·S)."""
    n, s, f1 = float(x.sum()), len(x), _frequency(x, 1)
    return s + f1**2 * float((x**2).sum()) / (n**2 - f1 * s)


def diversity_table(abundance_table: pd.DataFrame) -> pd.DataFrame:
    """Indici PAST con la stessa disposizione del foglio Indici_PAST: righe = indici, colonne = campioni."""
    return pd.DataFrame({sample: diversity_indices(abundance_table[sample].tolist()) for sample in abundance_table.columns})
