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
    gruppi 1–5 in proporzione alle loro abbondanze (vedi `foramecoqs_table(redistribute_unassigned=True)`), usata
    sempre, anche per il Foram-AMBI alternativo.
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


def foramecoqs_table(
    abundance_table: pd.DataFrame,
    fsi_group: pd.Series,
    eco_group: pd.Series,
    eqs_rules: dict[str, list[list]],
    alt_eco_group: pd.Series | None = None,
    alt_samples: set[str] | Sequence[str] | None = None,
    alt_label: str = "Foram-AMBI (Alt)",
    redistribute_unassigned: bool = False,
) -> pd.DataFrame:
    """Indici ForamEcoQS per ogni campione (una riga per campione).

    `fsi_group` ("Sen"/"Str"/altro) ed `eco_group` ("1".."5"/"NA") sono indicizzati come le righe della matrice.
    Se `alt_eco_group` e `alt_samples` sono forniti, calcola anche Foram-AMBI alternativo per i campioni indicati.
    Con `redistribute_unassigned` il Foram-AMBI principale e quello alternativo ridistribuiscono sempre gli
    individui NA nei gruppi 1–5 in proporzione agli assegnati (percentuali sul totale degli assegnati; NaN se non ce
    n'è nessuno), qualunque sia la quota di NA. Le colonne "% non assegnati …" riportano la quota reale di NA.
    """
    rows = []
    has_alt = alt_eco_group is not None and bool(alt_samples)
    alt_set = set(alt_samples) if alt_samples else set()
    for sample in abundance_table.columns:
        counts = abundance_table[sample]
        total = total_abundance(counts.tolist())
        sensitive, tolerant = counts[fsi_group == "Sen"].sum(), counts[fsi_group == "Str"].sum()
        by_group = {g: counts[eco_group == str(g)].sum() for g in ECO_GROUP_WEIGHTS}
        assigned = sum(by_group.values())
        unassigned = 100 * (1 - assigned / total) if total else math.nan
        if redistribute_unassigned:
            ambi = foram_ambi(by_group, assigned) if assigned else math.nan
        else:
            ambi = foram_ambi(by_group, total)
        values = {
            "Species Richness (S)": species_richness(counts.tolist()),
            "N": total,
            "exp(H'bc)": exp_hbc(counts.tolist()),
            "FSI": fsi(sensitive, tolerant),
        }
        values["EQS FSI"] = eqs_class(values["FSI"], eqs_rules["fsi"])
        values["Foram-AMBI"] = ambi
        values["% non assegnati Foram-AMBI"] = unassigned
        if has_alt:
            if sample in alt_set:
                by_group_alt = {g: counts[alt_eco_group == str(g)].sum() for g in ECO_GROUP_WEIGHTS}
                assigned_alt = sum(by_group_alt.values())
                if redistribute_unassigned:
                    val_alt = foram_ambi(by_group_alt, assigned_alt) if assigned_alt else math.nan
                else:
                    val_alt = foram_ambi(by_group_alt, total)
                unassigned_alt = 100 * (1 - assigned_alt / total) if total else math.nan
                eqs_alt = eqs_class(val_alt, eqs_rules["foram_ambi"])
            else:
                val_alt = math.nan
                unassigned_alt = math.nan
                eqs_alt = ""
            values[alt_label] = val_alt

        values["% non assegnati FSI"] = 100 * (1 - (sensitive + tolerant) / total) if total else math.nan
        if has_alt:
            values[f"% non assegnati {alt_label}"] = unassigned_alt

        values["EQS exp(H'bc)"] = eqs_class(values["exp(H'bc)"], eqs_rules["exp_hbc"])
        values["EQS Foram-AMBI"] = eqs_class(values["Foram-AMBI"], eqs_rules["foram_ambi"])
        if has_alt:
            values[f"EQS {alt_label}"] = eqs_alt

        rows.append({"Campione": sample, **values})
    table = pd.DataFrame(rows).set_index("Campione")

    # EQR: exp(H'bc) normalizzato sul massimo tra i campioni della tabella, 4 decimali; la classe usa il valore arrotondato.
    eqr = (table["exp(H'bc)"] / table["exp(H'bc)"].max()).map(lambda v: cs_round(v, 4))
    position = table.columns.get_loc("exp(H'bc)") + 1
    table.insert(position, "exp(H'bc) EQR", eqr)
    table.insert(position + 1, "EQS exp(H'bc) EQR", eqr.map(lambda v: eqs_class(v, eqs_rules["exp_hbc_eqr"])))
    return table
