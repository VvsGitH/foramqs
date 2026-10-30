"""Raccolta degli input non derivabili: tabelle dei campioni, geochimica e tabelle di configurazione."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from foramqs.config import Config, read_config_csv
from foramqs.io_excel import EXCEL_ROW, ExcelTable, read_tables, sample_tables


@dataclass(frozen=True)
class Inputs:
    samples: dict[str, ExcelTable]
    geochemistry: ExcelTable
    name_corrections: pd.DataFrame
    non_foram_terms: set[str]  # in minuscolo


def load_inputs(cfg: Config) -> Inputs:
    tables = read_tables(cfg.path("data_workbook"), adjacent_columns=(cfg.input["sample_comment_column"],))
    samples = sample_tables(tables, cfg.input["sample_columns"])
    geochemistry = tables[cfg.input["geochemistry_table"]]
    non_foram = read_config_csv(cfg.path("non_foram_terms"))
    return Inputs(
        samples=samples,
        geochemistry=geochemistry,
        name_corrections=read_config_csv(cfg.path("name_corrections")),
        non_foram_terms={t.casefold() for t in non_foram["termine"]},
    )


def geochemistry_values(geochemistry: ExcelTable, cfg: Config) -> pd.DataFrame:
    """Geochimica come tabella numerica indicizzata per campione.

    Le colonne derivate (es. Shannon_H) vengono scartate perché ora sono calcolate dalla pipeline; i valori censurati
    (es. "> 200") sono sostituiti secondo [input.censored_values]. Valori non numerici residui diventano NaN
    (la validazione li segnala come errore).
    """
    sample_col = cfg.input["geochemistry_sample_column"]
    dropped = set(cfg.input["geochemistry_derived_columns"]) | {EXCEL_ROW}
    data = geochemistry.data.drop(columns=[c for c in geochemistry.data.columns if c in dropped])
    data = data.set_index(sample_col)
    data.index = data.index.map(str).str.strip()
    data.index.name = "Campione"
    censored = cfg.input.get("censored_values", {})
    data = data.map(lambda v: censored.get(v.strip(), v) if isinstance(v, str) else v)
    return data.apply(pd.to_numeric, errors="coerce")
