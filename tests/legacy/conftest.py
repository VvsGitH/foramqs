"""Fixture con gli input e i risultati del flusso storico (Power Query + ForamEcoQS + PAST).

Servono solo a verificare che le formule siano portate correttamente: si danno alle funzioni di produzione gli
stessi input usati allora e si confrontano i risultati con i valori salvati nei vecchi file.
"""

import warnings
from dataclasses import dataclass

import openpyxl
import pytest

from foramqs.config import PROJECT_ROOT

INPUT_DIR = PROJECT_ROOT / "input_data"  # non versionata: i workbook vanno copiati qui
RESULTS = INPUT_DIR / "Campioni_P_2025_Results.xlsx"
DATA = INPUT_DIR / "Campioni_P_2025_Data.xlsx"
RAW_FEQS = INPUT_DIR / "Raw_ForamsEcoQs.xlsx"


@dataclass(frozen=True)
class Matrix:
    species: list[str]
    counts: dict[str, list[float]]  # campione → abbondanze nell'ordine di `species`


def _sheet_rows(path, sheet):
    if not path.exists():
        pytest.skip(f"{path.name} non è in input_data/")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # immagini WMF non supportate da openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[sheet]
    return [list(r) for r in ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True)]


def _matrix(rows) -> Matrix:
    header, body = rows[0], [r for r in rows[1:] if r[0]]
    samples = [s for s in header[1:] if s]
    return Matrix(
        species=[r[0] for r in body],
        counts={s: [float(r[j] or 0) for r in body] for j, s in enumerate(header[1:], 1) if s in samples},
    )


@pytest.fixture(scope="session")
def legacy_matrix() -> Matrix:
    """Abbondanze assolute del vecchio Results (prima delle correzioni di nome), senza la riga dei totali."""
    return _matrix(_sheet_rows(RESULTS, "Abbondanze_assolute"))


@pytest.fixture(scope="session")
def legacy_mud() -> dict[str, float]:
    """La riga 'Mud (%)' passata a ForamEcoQS (che l'ha contata come una specie)."""
    rows = _sheet_rows(RAW_FEQS, "Abbondanze_assolute")
    mud = next(r for r in rows if r[0] == "Mud (%)")
    return {s: float(v) for s, v in zip(rows[0][1:], mud[1:])}


def _table_by_first_column(rows) -> dict[str, dict]:
    header = rows[0]
    return {r[0]: dict(zip(header[1:], r[1:])) for r in rows[1:] if r[0]}


@pytest.fixture(scope="session")
def foram_echo_qs() -> dict[str, dict]:
    return _table_by_first_column(_sheet_rows(RESULTS, "Foram Echo QS"))


@pytest.fixture(scope="session")
def pq_eco_groups() -> dict[str, dict]:
    return _table_by_first_column(_sheet_rows(RESULTS, "Abbondanza_rel%_gruppiecolofgic"))


@pytest.fixture(scope="session")
def indici_past() -> dict[str, dict]:
    """Indice → {campione: valore} dal foglio Indici_PAST (righe 2-18)."""
    return _table_by_first_column(_sheet_rows(RESULTS, "Indici_PAST")[1:18])


@pytest.fixture(scope="session")
def specie_stilevita() -> dict[str, dict]:
    return _table_by_first_column(_sheet_rows(DATA, "specie_stilivita"))
