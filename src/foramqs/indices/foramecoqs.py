"""Indici calcolati oggi con ForamEcoQS, portati dal sorgente C# con la stessa aritmetica.

Sorgente: ForamEcoQS/src/ForamEcoQS.Core/BioticIndicesCalculator.cs (BIC) e SpecializedDatabankLoader.cs (SDL).
Citazione: Mangiagalli et al. 2026, SoftwareX 35, 102921. Licenza MIT di ForamEcoQS: THIRD_PARTY_NOTICES.md.

Ogni funzione riceve le abbondanze di un singolo campione (conteggi, nell'ordine delle righe della matrice).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import pandas as pd

from foramqs.csharp_compat import cs_round, cs_sum


def species_richness(counts: Sequence[float]) -> int:
    """S: numero di taxa con abbondanza > 0 (BIC:570-573)."""
    return sum(1 for n in counts if n > 0)


def total_abundance(counts: Sequence[float]) -> float:
    """N: somma delle abbondanze (BIC:578-581)."""
    return cs_sum(counts)


def chao_shen_entropy(counts: Sequence[float]) -> float:
    """H'bc: entropia di Shannon corretta per la copertura (Chao & Shen 2003), arrotondata a 4 decimali (BIC:75-107).

    C = 1 − f1/N (f1 = taxa con un solo individuo; C = 0.001 se C = 0)
    H'bc = −Σ C·pᵢ·ln(C·pᵢ) / (1 − (1 − C·pᵢ)^N), saltando i termini con C·pᵢ ∉ (0, 1).
    """
    present = [n for n in counts if n > 0]
    n_total = cs_sum(present)
    if n_total == 0:
        return 0.0
    singletons = sum(1 for n in present if n == 1.0)
    coverage = 1 - singletons / n_total
    if coverage == 0:
        coverage = 0.001
    entropy = 0.0
    for n in present:
        pa = coverage * (n / n_total)
        if 0 < pa < 1:
            entropy -= pa * math.log(pa) / (1 - math.pow(1 - pa, n_total))
    return cs_round(entropy, 4)


def exp_hbc(counts: Sequence[float]) -> float:
    """exp(H'bc) arrotondato a 4 decimali, calcolato su H'bc già arrotondato (BIC:113-117). Campione vuoto = 1."""
    return cs_round(math.exp(chao_shen_entropy(counts)), 4)


def fsi(sensitive: float, tolerant: float) -> float:
    """Foram Stress Index (Dimiza et al. 2016) = (10·Sen + Str)/(Sen + Str), 3 decimali (BIC:130-137).

    `sensitive` e `tolerant` sono le abbondanze dei soli taxa assegnati ai gruppi Sen e Str (i non assegnati e
    gli ND non entrano nel calcolo). 0 se nessun taxon è assegnato.
    """
    assigned = sensitive + tolerant
    if assigned == 0:
        return 0.0
    sen_pct, str_pct = sensitive / assigned * 100, tolerant / assigned * 100
    return cs_round((10 * sen_pct + str_pct) / (sen_pct + str_pct), 3)


ECO_GROUP_WEIGHTS = {1: 0.0, 2: 1.5, 3: 3.0, 4: 4.5, 5: 6.0}


def foram_ambi(eco_group_abundance: dict[int, float], named_total: float) -> float:
    """Foram-AMBI (Alve et al. 2016; Jorissen et al. 2018), 3 decimali (BIC:846-878, 923-934).

    Come in ForamEcoQS, le percentuali dei gruppi ecologici sono calcolate sul totale di TUTTE le righe della
    matrice: anche i taxa senza gruppo (NA) e i non determinati (ND) sono nel denominatore e pesano quindi come il
    gruppo I. L'FSI invece usa solo i taxa assegnati a Sen/Str.
    Passando come `named_total` il solo totale degli assegnati si ottiene invece la ridistribuzione degli NA nei
    gruppi 1–5 in proporzione alle loro abbondanze (`foramecoqs_table` calcola entrambi: "Foram-AMBI ori" e
    "Foram-AMBI").
    """
    if named_total == 0:
        return 0.0
    percent = {g: eco_group_abundance.get(g, 0.0) / named_total * 100 for g in ECO_GROUP_WEIGHTS}
    return cs_round(cs_sum(ECO_GROUP_WEIGHTS[g] * percent[g] for g in ECO_GROUP_WEIGHTS) / 100, 3)


_OPERATORS = {
    ">=": lambda v, limit: v >= limit,
    ">": lambda v, limit: v > limit,
    "<=": lambda v, limit: v <= limit,
    "<": lambda v, limit: v < limit,
    "==": lambda v, limit: v == limit,
}


def eqs_class(value: float, rules: list[list]) -> str:
    """Classe di qualità ecologica secondo regole ordinate [classe, operatore, limite]; l'ultima è [classe] (default).

    Esempio (FSI, Dimiza et al. 2016): [["Azoic", "==", 0], ["High", ">=", 9], ..., ["Bad"]].
    """
    if math.isnan(value):
        return "N/A"
    for label, operator, limit in rules[:-1]:
        if _OPERATORS[operator](value, limit):
            return label
    return rules[-1][0]


EXP_HBC_COLUMNS = ["exp(H'bc)", "exp(H'bc) EQR", "EQS exp(H'bc) EQR"]
FSI_COLUMNS = ["% Sen", "% Str", "FSI", "EQS FSI"]
FORAM_AMBI_COLUMNS = [*(f"% GE{g}" for g in ECO_GROUP_WEIGHTS), "% NA", "Foram-AMBI ori", "Foram-AMBI", "EQS Foram-AMBI"]


def foramecoqs_table(
    abundance_table: pd.DataFrame,
    fsi_group: pd.Series,
    eco_group: pd.Series,
    eqs_rules: dict[str, list[list]],
) -> pd.DataFrame:
    """Indici ForamEcoQS per ogni campione (una riga per campione).

    `fsi_group` ("Sen"/"Str"/altro) ed `eco_group` ("1".."5"/"NA") sono indicizzati come le righe della matrice.

    - `% Sen`, `% Str`: quote sul totale dei soli individui Sen + Str (come nella formula dell'FSI; sommano a 100).
    - `% GE1`…`% GE5`, `% NA`: quote reali sul totale degli individui (sommano a 100; NA comprende i non determinati).
    - `Foram-AMBI ori`: come ForamEcoQS, gli NA restano al denominatore e pesano come il gruppo I.
    - `Foram-AMBI`: gli NA sono ridistribuiti nei gruppi 1–5 in proporzione agli assegnati (NaN se nessuno è
      assegnato); `EQS Foram-AMBI` è la sua classe.
    """
    rows = []
    for sample in abundance_table.columns:
        counts = abundance_table[sample]
        total = total_abundance(counts.tolist())
        sensitive, tolerant = counts[fsi_group == "Sen"].sum(), counts[fsi_group == "Str"].sum()
        sen_str = sensitive + tolerant
        by_group = {g: counts[eco_group == str(g)].sum() for g in ECO_GROUP_WEIGHTS}
        assigned = sum(by_group.values())
        values = {
            "Species Richness (S)": species_richness(counts.tolist()),
            "N": total,
            "exp(H'bc)": exp_hbc(counts.tolist()),
            "% Sen": 100 * sensitive / sen_str if sen_str else math.nan,
            "% Str": 100 * tolerant / sen_str if sen_str else math.nan,
            "FSI": fsi(sensitive, tolerant),
        }
        values["EQS FSI"] = eqs_class(values["FSI"], eqs_rules["fsi"])
        for g in ECO_GROUP_WEIGHTS:
            values[f"% GE{g}"] = 100 * by_group[g] / total if total else math.nan
        values["% NA"] = 100 * (1 - assigned / total) if total else math.nan
        values["Foram-AMBI ori"] = foram_ambi(by_group, total)
        values["Foram-AMBI"] = foram_ambi(by_group, assigned) if assigned else math.nan
        values["EQS Foram-AMBI"] = eqs_class(values["Foram-AMBI"], eqs_rules["foram_ambi"])
        rows.append({"Campione": sample, **values})
    table = pd.DataFrame(rows).set_index("Campione")

    # EQR: exp(H'bc) normalizzato sul massimo tra i campioni della tabella, 4 decimali; la classe usa il valore arrotondato.
    eqr = (table["exp(H'bc)"] / table["exp(H'bc)"].max()).map(lambda v: cs_round(v, 4))
    position = table.columns.get_loc("exp(H'bc)") + 1
    table.insert(position, "exp(H'bc) EQR", eqr)
    table.insert(position + 1, "EQS exp(H'bc) EQR", eqr.map(lambda v: eqs_class(v, eqs_rules["exp_hbc_eqr"])))
    return table
