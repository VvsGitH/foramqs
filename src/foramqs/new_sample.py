"""Aggiunta di un nuovo campione con dati vuoti da compilare a mano.

Tre passaggi:
  1. nel workbook dei dati, un foglio con la Tabella Excel del campione (intestazioni e stile copiati da un
     campione esistente, nessuna riga compilata);
  2. una riga nella Tabella della geochimica, con il solo nome del campione;
  3. il campione aggiunto a un gruppo di [cluster.groups] in config/pipeline.toml (commenti preservati).

Prima di salvare il workbook ne viene fatta una copia di backup. openpyxl non conserva le query Power Query e le
connessioni dati: se il workbook ne contiene, vengono rimosse (la pipeline non le usa) e il comando lo segnala.
Finché il campione non è compilato, `foramqs check` lo segnala con gli errori V26 (conte) e V27 (geochimica).
"""

from __future__ import annotations

import re
import shutil
import zipfile
from copy import copy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import openpyxl
import tomlkit
from openpyxl.utils import get_column_letter, range_boundaries
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.table import Table
from openpyxl.worksheet.worksheet import Worksheet

from foramqs.config import Config

# Nome valido sia come nome di Tabella Excel sia come nome di foglio.
_SAMPLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,30}$")
# Excel rifiuta nomi di Tabella che sembrano riferimenti di cella (es. "MC01" = colonna MC, riga 1).
_CELL_REFERENCE = re.compile(r"^([A-Za-z]{1,3}\d+|[Rr]\d*[Cc]\d*)$")
_POWER_QUERY_PARTS = ("customXml/", "xl/connections.xml", "xl/queryTables/")


class NewSampleError(Exception):
    """Il campione non può essere aggiunto; il messaggio spiega perché. Nessun file è stato modificato."""


@dataclass(frozen=True)
class AddedSample:
    name: str
    backup: Path
    geochemistry_row: int
    group: str
    group_created: bool
    removed_power_query: bool


def add_sample(cfg: Config, config_path: Path, name: str, group: str) -> AddedSample:
    workbook_path = cfg.path("data_workbook")
    lock_file = workbook_path.with_name(f"~${workbook_path.name}")
    if lock_file.exists():
        raise NewSampleError(f"{workbook_path.name} risulta aperto in Excel ({lock_file.name}): chiuderlo e riprovare")

    wb = openpyxl.load_workbook(workbook_path)
    samples = _sample_tables(wb, cfg.input["sample_columns"])
    geo_sheet, geo_table = _find_table(wb, cfg.input["geochemistry_table"])
    config_doc = tomlkit.parse(config_path.read_text(encoding="utf-8"))
    groups = config_doc["cluster"]["groups"]

    problems = check_new_sample_name(name, wb, _first_column_values(geo_sheet, geo_table), groups)
    if not samples:
        problems.append("nel workbook non c'è nessuna Tabella campione da usare come modello")
    if problems:
        raise NewSampleError("; ".join(problems))

    backup = _backup(workbook_path)
    removed_power_query = _has_power_query(workbook_path)
    _add_sample_sheet(wb, name, samples)
    row = _add_geochemistry_row(geo_sheet, geo_table, name)
    wb.save(workbook_path)

    group_created = group not in groups
    if group_created:
        groups[group] = [name]
    else:
        groups[group].append(name)
    config_path.write_text(tomlkit.dumps(config_doc), encoding="utf-8")
    return AddedSample(name, backup, row, group, group_created, removed_power_query)


def check_new_sample_name(name: str, wb: Workbook, geochemistry_samples: set[str], groups: dict) -> list[str]:
    """Motivi per cui `name` non è utilizzabile (lista vuota se va bene)."""
    problems = []
    if not _SAMPLE_NAME.match(name):
        problems.append(f"'{name}' non è un nome valido: lettere, cifre e '_', iniziale non numerica, max 31 caratteri")
    elif _CELL_REFERENCE.match(name):
        problems.append(f"'{name}' sembra un riferimento di cella e Excel non lo accetta come nome di Tabella (es. usare MC_XX01)")
    existing_tables = {t.name.casefold() for ws in wb.worksheets for t in ws.tables.values()}
    if name.casefold() in existing_tables:
        problems.append(f"esiste già una Tabella '{name}'")
    if name.casefold() in {s.casefold() for s in wb.sheetnames}:
        problems.append(f"esiste già un foglio '{name}'")
    if name in geochemistry_samples:
        problems.append(f"'{name}' è già nella tabella della geochimica")
    for group, members in groups.items():
        if name in members:
            problems.append(f"'{name}' è già nel gruppo di cluster {group}")
    return problems


def _sample_tables(wb: Workbook, columns: list[str]) -> list[tuple[Worksheet, Table]]:
    found = []
    for ws in wb.worksheets:
        for table in ws.tables.values():
            min_col, min_row, max_col, _ = range_boundaries(table.ref)
            header = [str(ws.cell(min_row, c).value).strip() for c in range(min_col, max_col + 1)]
            if header == columns:
                found.append((ws, table))
    return found


def _find_table(wb: Workbook, name: str) -> tuple[Worksheet, Table]:
    for ws in wb.worksheets:
        if name in ws.tables:
            return ws, ws.tables[name]
    raise NewSampleError(f"la Tabella '{name}' non esiste nel workbook")


def _first_column_values(ws: Worksheet, table: Table) -> set[str]:
    min_col, min_row, _, max_row = range_boundaries(table.ref)
    return {str(ws.cell(r, min_col).value).strip() for r in range(min_row + 1, max_row + 1) if ws.cell(r, min_col).value}


def _add_sample_sheet(wb: Workbook, name: str, samples: list[tuple[Worksheet, Table]]) -> Worksheet:
    """Nuovo foglio subito dopo l'ultimo campione, con intestazioni, larghezze e stile del primo campione."""
    template_ws, template_table = samples[0]
    last_index = max(wb.worksheets.index(ws) for ws, _ in samples)
    ws = wb.create_sheet(name, index=last_index + 1)

    min_col, min_row, max_col, _ = range_boundaries(template_table.ref)
    # Intestazioni della Tabella più quelle adiacenti a destra (es. "COMMENTI & DUBBI" e la legenda dei gusci).
    last_header = max_col
    while template_ws.cell(min_row, last_header + 1).value is not None:
        last_header += 1
    for col in range(min_col, last_header + 1):
        source = template_ws.cell(min_row, col)
        target = ws.cell(1, col - min_col + 1, source.value)
        target._style = copy(source._style)
        letter = get_column_letter(col)
        ws.column_dimensions[get_column_letter(col - min_col + 1)].width = template_ws.column_dimensions[letter].width

    ref = f"A1:{get_column_letter(max_col - min_col + 1)}2"  # intestazione + una riga vuota da compilare
    ws.add_table(Table(displayName=name, ref=ref, tableStyleInfo=copy(template_table.tableStyleInfo)))
    ws.freeze_panes = "A2"
    return ws


def _add_geochemistry_row(ws: Worksheet, table: Table, name: str) -> int:
    """Riga nuova in fondo alla Tabella: il contenuto sotto (note) scende di una riga. Restituisce la riga."""
    min_col, min_row, max_col, max_row = range_boundaries(table.ref)
    other_tables_below = [t.name for t in ws.tables.values() if t is not table and range_boundaries(t.ref)[1] > max_row]
    if other_tables_below:
        raise NewSampleError(f"sotto la tabella della geochimica ci sono altre Tabelle ({', '.join(other_tables_below)})")
    new_row = max_row + 1
    ws.insert_rows(new_row)
    for col in range(min_col, max_col + 1):
        ws.cell(new_row, col)._style = copy(ws.cell(max_row, col)._style)
    ws.cell(new_row, min_col, name)
    table.ref = f"{get_column_letter(min_col)}{min_row}:{get_column_letter(max_col)}{new_row}"
    if table.autoFilter is not None:
        table.autoFilter.ref = table.ref
    return new_row


def _backup(path: Path) -> Path:
    target = path.parent / "backup" / f"{path.stem}_{datetime.now():%Y%m%d_%H%M%S}{path.suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    return target


def _has_power_query(path: Path) -> bool:
    with zipfile.ZipFile(path) as z:
        return any(n.startswith(_POWER_QUERY_PARTS) for n in z.namelist())
