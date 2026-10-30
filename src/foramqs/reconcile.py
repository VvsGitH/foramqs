"""Confronto tra i risultati della pipeline e un vecchio Results.xlsx prodotto con Power Query/ForamEcoQS/PAST.

Il confronto non decide quale valore sia giusto: elenca le differenze indice per indice e, per ogni campione,
i cambiamenti dei dati che le possono spiegare (nomi uniti da WoRMS, giovanili, correzioni, non determinati).
Le cause note del flusso storico sono riassunte in KNOWN_CAUSES.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import openpyxl
import pandas as pd

KNOWN_CAUSES = pd.DataFrame([
    ("Foram Echo QS", "ForamEcoQS è stato eseguito con la riga 'Mud (%)' contata come specie: S vecchio = S + 1 e "
                      "exp(H'bc) alterato (riprodotto esattamente in tests/legacy)."),
    ("Foram Echo QS, Indici_PAST", "ForamEcoQS e PAST hanno usato la matrice precedente alle correzioni di nome del "
                                   "2026-10-30 (sinonimi non uniti)."),
    ("Indici_PAST", "MC_PN01 in PAST è stato calcolato su una versione dei dati con un taxon in più."),
    ("Foram-AMBI", "Il foglio dei gruppi ecologici del vecchio Results usa una versione precedente dei gruppi di "
                   "specie_stilevita (molte specie allora NA) e non era più stato aggiornato."),
    ("Densità", "La densità storica era incollata a mano: in MC_PN01 R1 conteggiava 4 diatomee; in MC_FO02 le repliche "
                "R2 e R3 erano copie di R1 (il campione ha una sola replica)."),
    ("Campioni in [input.copied_replicas]", "La sola replica R1 è contata come N repliche identiche (MC_FO02: 3), "
                                            "quindi N triplica e gli indici basati sulle specie rare cambiano."),
    ("Tutti", "Nuove regole: giovanili sommati a 'Genere spp.'; "
              "sinonimi uniti secondo WoRMS."),
], columns=["dove", "causa"])

# indice nel vecchio Results → (foglio nuovo, colonna o riga nuova)
_FORAMECOQS = {"Species Richness (S)": "Species Richness (S)", "exp(H'bc)": "exp(H'bc)", "FSI": "FSI", "Foram-AMBI 2025": "Foram-AMBI"}


def _rows(wb: openpyxl.Workbook, sheet: str) -> list[list]:
    return [list(r) for r in wb[sheet].iter_rows(values_only=True)]


def _by_sample(rows: list[list]) -> pd.DataFrame:
    """La prima tabella del foglio (colonne contigue dalla A); eventuali copie più a destra sono ignorate."""
    width = rows[0].index(None) if None in rows[0] else len(rows[0])
    header = rows[0][:width]
    body = [r[:width] for r in rows[1:] if isinstance(r[0], str) and r[0].startswith("MC_")]
    return pd.DataFrame(body, columns=header).set_index(header[0])


def old_indices(path: Path) -> pd.DataFrame:
    """Indici del vecchio Results in formato long: indice, campione, valore."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(path, data_only=True)
    parts = []
    feqs = _by_sample(_rows(wb, "Foram Echo QS"))
    for old, new in _FORAMECOQS.items():
        parts.append(feqs[old].rename_axis("campione").rename("vecchio").reset_index().assign(indice=new))
    past_rows = _rows(wb, "Indici_PAST")[1:18]
    past = pd.DataFrame(past_rows[1:], columns=past_rows[0]).set_index(past_rows[0][0])
    for index_name, values in past.iterrows():
        series = values.dropna().rename("vecchio").rename_axis("campione").reset_index()
        parts.append(series.assign(indice=f"PAST {index_name}"))
    density = _by_sample(_rows(wb, "Densità_faunistica_media"))
    parts.append(density.iloc[:, 0].rename("vecchio").rename_axis("campione").reset_index().assign(indice="Densità faunistica media"))
    deformed = _by_sample(_rows(wb, "Abbondanza_rel%_deformati"))
    parts.append(deformed.iloc[:, 0].rename("vecchio").rename_axis("campione").reset_index().assign(indice="Deformati (frazione)"))
    return pd.concat(parts, ignore_index=True)


def new_indices(sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    parts = []
    feqs = sheets["Foram Echo QS"]
    for new in _FORAMECOQS.values():
        parts.append(feqs[new].rename("nuovo").rename_axis("campione").reset_index().assign(indice=new))
    for index_name, values in sheets["Indici_PAST"].iterrows():
        parts.append(values.rename("nuovo").rename_axis("campione").reset_index().assign(indice=f"PAST {index_name}"))
    density = sheets["Densità_faunistica_media"].iloc[:, 0]
    parts.append(density.rename("nuovo").rename_axis("campione").reset_index().assign(indice="Densità faunistica media"))
    deformed = sheets["Abbondanza_rel%_deformati"].iloc[:, 0]
    parts.append(deformed.rename("nuovo").rename_axis("campione").reset_index().assign(indice="Deformati (frazione)"))
    return pd.concat(parts, ignore_index=True)


def compare(old_results: Path, sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    table = old_indices(old_results).merge(new_indices(sheets), on=["indice", "campione"], how="outer")
    table["vecchio"] = pd.to_numeric(table["vecchio"], errors="coerce")
    table["nuovo"] = pd.to_numeric(table["nuovo"], errors="coerce")
    table["differenza"] = table["nuovo"] - table["vecchio"]
    table["differenza_%"] = 100 * table["differenza"] / table["vecchio"].abs()
    return table[["indice", "campione", "vecchio", "nuovo", "differenza", "differenza_%"]].sort_values(["indice", "campione"])


def sample_changes(observations: pd.DataFrame, cleaning_log: pd.DataFrame) -> pd.DataFrame:
    """Per ogni campione, i cambiamenti dei dati rispetto al testo originale che possono spostare gli indici."""
    rules = cleaning_log.set_index("testo_originale")["regole"]
    data = observations.assign(regole=observations["testo_originale"].map(rules).fillna(""))
    changes = []
    for (sample, taxon, valid), group in data.groupby(["campione", "taxon", "nome_valido"]):
        n = int(group["individui"].sum())
        if taxon != valid:
            changes.append((sample, "nome unito da WoRMS/alias", f"{taxon} → {valid}", n))
        if group["regole"].str.contains("giovanili_in_genere_spp").any():
            changes.append((sample, "giovanili in Genere spp.", taxon, n))
        if group["regole"].str.contains("correzione:").any():
            changes.append((sample, "correzione di nome", taxon, n))
    return pd.DataFrame(changes, columns=["campione", "tipo", "dettaglio", "individui"])
