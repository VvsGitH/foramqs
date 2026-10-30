"""Tabelle di abbondanza e di sintesi (equivalenti alle query Power Query del vecchio Results).

Convenzioni:
  - le matrici hanno una riga per taxon (`nome_valido`) e una colonna per campione;
  - le abbondanze relative sono frazioni 0-1 (come in Power Query); le tabelle per PAST usano le percentuali;
  - i tratti (guscio, stile di vita, gruppi) vengono dalla tabella dei tratti, mai dai fogli grezzi.
"""

from __future__ import annotations

import pandas as pd

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


def genera_composition(relative_table: pd.DataFrame, threshold: float, mode: str) -> pd.DataFrame:
    """Abbondanza relativa per genere dei taxa sopra soglia, più la riga 'Others' con il resto."""
    dominant = above_threshold(relative_table, threshold, mode)
    genera = dominant.groupby(dominant.index.str.split(" ").str[0]).sum()
    genera.loc["Others"] = 1 - genera.sum()
    genera.index.name = "Genere"
    return genera


def species_columns_for_past(
    relative_table: pd.DataFrame, traits: pd.DataFrame, threshold: float, mode: str, abbreviations: dict[str, str],
) -> pd.DataFrame:
    """Specie dominanti in percentuale, una riga per campione, con l'etichetta 'Specie (stile di vita)' usata in PAST."""
    dominant = above_threshold(relative_table, threshold, mode) * 100
    lifestyle = trait_of(dominant, traits, "stile_di_vita").map(lambda v: abbreviations.get(v, v))
    dominant.index = [f"{name} ({lifestyle[name]})" for name in dominant.index]
    table = dominant.T
    table.index.name = "Campione"
    return table


def zscore(table: pd.DataFrame) -> pd.DataFrame:
    """Standardizzazione per colonna con la deviazione standard campionaria (come List.StandardDeviation di PQ)."""
    return (table - table.mean()) / table.std(ddof=1)


def sqa_exceedances(geochemistry: pd.DataFrame, limits: dict[str, float]) -> pd.DataFrame:
    """Campioni che superano almeno uno standard di qualità (SQA) dei metalli, con i limiti nell'ultima riga."""
    values = geochemistry[list(limits)]
    exceeding = values[(values > pd.Series(limits)).any(axis=1)].copy()
    exceeding.loc["SQA (mg/kg s.s.)"] = pd.Series(limits)
    return exceeding
