"""Tabelle di abbondanza e di sintesi (equivalenti alle query Power Query del vecchio Results).

Convenzioni:
  - le matrici hanno una riga per taxon (`nome_valido`) e una colonna per campione;
  - le abbondanze relative sono frazioni 0-1; i fogli Abb_rel% e Abb_rel_5% le riportano in percentuale;
  - i tratti (guscio, stile di vita, gruppi) vengono dalla tabella dei tratti, mai dai fogli grezzi.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from openpyxl.utils import get_column_letter

NOT_ASSIGNED = "NA"


def abundance(observations: pd.DataFrame, samples: list[str]) -> pd.DataFrame:
    """Abbondanze assolute: individui per taxon e campione (i taxa con 0 individui in tutti i campioni sono esclusi)."""
    table = observations.pivot_table(index="nome_valido", columns="campione", values="individui", aggfunc="sum", fill_value=0)
    table = table.reindex(columns=samples, fill_value=0)
    table = table[table.sum(axis=1) > 0]
    table.index.name = "SPECIE"
    table.columns.name = None
    return table.astype(int)


def relative(abundance_table: pd.DataFrame) -> pd.DataFrame:
    """Abbondanze relative (frazioni): ogni colonna somma a 1."""
    return abundance_table / abundance_table.sum()


def trait_of(abundance_table: pd.DataFrame, traits: pd.DataFrame, column: str) -> pd.Series:
    """Valore di un tratto per ogni taxon della matrice; NA se il taxon non è nella tabella dei tratti."""
    by_name = traits.set_index("nome_valido")[column]
    return abundance_table.index.to_series().map(by_name).fillna(NOT_ASSIGNED).replace("", NOT_ASSIGNED)


def by_trait(abundance_table: pd.DataFrame, trait: pd.Series, labels: dict[str, str] | None = None) -> pd.DataFrame:
    """Abbondanza relativa per classe di un tratto (es. tipo di guscio): righe = classi, colonne = campioni."""
    grouped = relative(abundance_table).groupby(trait.map(lambda v: (labels or {}).get(v, v))).sum()
    grouped.index.name = trait.name
    return grouped


def deformed_fraction(observations: pd.DataFrame, samples: list[str]) -> pd.Series:
    """Frazione di individui deformati per campione."""
    totals = observations.groupby("campione")[["deformati", "individui"]].sum().reindex(samples)
    return (totals["deformati"] / totals["individui"]).rename("Deformed_rel%_abundance").rename_axis("Campione")


def density(observations: pd.DataFrame, samples: list[str], replica_volume_ml: float, per_ml: float) -> tuple[pd.DataFrame, pd.Series]:
    """Densità faunistica (individui per `per_ml` ml di sedimento): per replica e media per campione.

    Contano tutti i foraminiferi (anche i non determinati); non contano le righe scartate (diatomee, ecc.) né gli
    individui morti senza conteggio.
    """
    per_replica = observations.groupby(["campione", "replica"])["individui"].sum().rename("individui").reset_index()
    per_replica["densita"] = per_replica["individui"] / (replica_volume_ml / per_ml)
    mean = per_replica.groupby("campione")["densita"].mean().reindex(samples).rename("Densità faunistica media")
    mean.index.name = "Campione"
    return per_replica, mean


def above_threshold(relative_table: pd.DataFrame, threshold: float, mode: str) -> pd.DataFrame:
    """Taxa dominanti. mode="cella": valori sotto soglia azzerati; mode="specie": taxa sopra soglia in almeno un campione."""
    if mode == "cella":
        kept = relative_table.where(relative_table >= threshold, 0)
        return kept[(kept > 0).any(axis=1)]
    if mode == "specie":
        return relative_table[(relative_table >= threshold).any(axis=1)]
    raise ValueError(f"threshold_mode sconosciuto: {mode!r} (ammessi: 'cella', 'specie')")


def log10_1px(table: pd.DataFrame) -> pd.DataFrame:
    """Trasformazione log(1+x) in base 10, cella per cella (la stessa formula di `=LOG10(1+x)` in Excel)."""
    return np.log10(1 + table.astype(float))


def log10_1px_formulas(source_sheet: str, source: pd.DataFrame) -> pd.DataFrame:
    """Formule Excel `=LOG10(1+cella)` per la tabella trasposta di `source` (campioni × specie).

    `source` è la tabella com'è scritta nel foglio `source_sheet` da `report.write_workbook`: intestazione nella riga 1
    e indice nella colonna A, quindi la cella (specie i, campione j) è nella riga i+2 e nella colonna j+2.
    """
    sheet = source_sheet.replace("'", "''")
    cols = {sample: get_column_letter(j + 2) for j, sample in enumerate(source.columns)}
    formulas = pd.DataFrame(
        {species: [f"=LOG10(1+'{sheet}'!{cols[sample]}{i + 2})" for sample in source.columns]
         for i, species in enumerate(source.index)},
        index=pd.Index(source.columns, name="Campione"),
    )
    formulas.columns.name = None
    return formulas
