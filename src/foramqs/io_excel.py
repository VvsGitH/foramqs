"""Lettura delle tabelle Excel (le "Tabelle" con nome, non i fogli) dal workbook dei dati grezzi."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.utils import range_boundaries

EXCEL_ROW = "_riga_excel"


@dataclass(frozen=True)
class ExcelTable:
    name: str
    sheet: str
    data: pd.DataFrame  # nomi colonna senza spazi ai bordi + colonna EXCEL_ROW con il numero di riga nel foglio
    columns: list[str]  # le colonne della Tabella Excel (senza EXCEL_ROW né colonne adiacenti)


def read_tables(path: Path, adjacent_columns: tuple[str, ...] = ()) -> dict[str, ExcelTable]:
    """Tutte le tabelle del workbook, indicizzate per nome tabella.

    `adjacent_columns`: intestazioni di colonne scritte subito a destra di una tabella ma fuori dal suo intervallo
    (es. note dei ricercatori); se presenti vengono lette insieme alla tabella.
    Le righe completamente vuote vengono scartate e le celle con soli spazi diventano vuote (None); gli altri valori
    restano quelli grezzi di Excel (nessuna conversione), così la validazione può segnalare tipi sbagliati.
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    tables: dict[str, ExcelTable] = {}
    for ws in wb.worksheets:
        for table in ws.tables.values():
            min_col, min_row, max_col, max_row = range_boundaries(table.ref)
            max_row = min(max_row, ws.max_row)  # alcune tabelle arrivano fino alla riga 1048576
            columns = [str(ws.cell(min_row, c).value).strip() for c in range(min_col, max_col + 1)]
            extra = []
            while str(ws.cell(min_row, max_col + len(extra) + 1).value or "").strip() in adjacent_columns:
                extra.append(str(ws.cell(min_row, max_col + len(extra) + 1).value).strip())
            rows = ws.iter_rows(
                min_row=min_row + 1, max_row=max_row, min_col=min_col, max_col=max_col + len(extra), values_only=True,
            )
            records = []
            for excel_row, values in enumerate(rows, start=min_row + 1):
                if all(_is_blank(v) for v in values[: len(columns)]):
                    continue
                records.append([None if _is_blank(v) else v for v in values] + [excel_row])
            data = pd.DataFrame(records, columns=[*columns, *extra, EXCEL_ROW], dtype=object)
            tables[table.name] = ExcelTable(name=table.name, sheet=ws.title, data=data, columns=columns)
    return tables


def sample_tables(tables: dict[str, ExcelTable], sample_columns: list[str]) -> dict[str, ExcelTable]:
    """Le tabelle che hanno esattamente le colonne di un campione; il nome della tabella è il nome del campione."""
    return {name: t for name, t in tables.items() if t.columns == sample_columns}


def _is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())
