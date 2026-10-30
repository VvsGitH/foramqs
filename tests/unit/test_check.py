"""`check` di un workbook costruito nel test: i casi limite devono diventare segnalazioni, non eccezioni."""

import shutil
from pathlib import Path

import openpyxl
import pytest
from openpyxl.worksheet.table import Table

from foramqs.config import DEFAULT_CONFIG, load_config
from foramqs.pipeline import check
from foramqs.validate import configured_geochemistry_columns

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COLUMNS = ["REPLICA", "N°SLIDE", "CASELLA", "SPECIE (LONG FORMAT)", "TIPO GUSCIO", "N°INDIVIDUI", "DEFORMATI"]
TEPIDA = [1, 1, 1, "Ammonia tepida", "I", 5, 0]


@pytest.fixture
def make_project(tmp_path):
    """Copia config e tratti reali in tmp_path e scrive un workbook con i campioni e le righe di geochimica date."""
    shutil.copytree(DEFAULT_CONFIG.parent, tmp_path / "config")
    shutil.copytree(PROJECT_ROOT / "reference", tmp_path / "reference")
    cfg = load_config(tmp_path / "config" / DEFAULT_CONFIG.name)

    def build(samples: dict[str, list[list]], geochemistry: list[str] | None = None, copied_replicas: dict | None = None,
              full: bool = False):
        if copied_replicas is not None:
            cfg.raw["input"]["copied_replicas"] = copied_replicas
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        for name, rows in samples.items():
            ws = wb.create_sheet(name)
            ws.append(COLUMNS)
            for row in rows:
                ws.append(row)
            ws.add_table(Table(displayName=name, ref=f"A1:G{max(len(rows), 1) + 1}"))
        geo_columns = sorted({c for cols in configured_geochemistry_columns(cfg).values() for c in cols})
        ws = wb.create_sheet("Variabili_campioni")
        ws.append(["Colonna1", *geo_columns])
        grain = cfg.input["grain_size_columns"]
        for name in samples if geochemistry is None else geochemistry:
            ws.append([name, *(100 / len(grain) if c in grain else 1.0 for c in geo_columns)])
        ws.add_table(Table(displayName="Geochimica_campioni", ref=f"A1:{openpyxl.utils.get_column_letter(len(geo_columns) + 1)}{ws.max_row}"))
        workbook = cfg.path("data_workbook")
        workbook.parent.mkdir(parents=True, exist_ok=True)
        wb.save(workbook)
        result = check(cfg, offline=True)
        return result if full else result.issues

    return build


def codes(issues, severity=None):
    return set(issues["codice"] if severity is None else issues.loc[issues["severita"] == severity, "codice"])


def test_only_empty_samples_are_reported_not_crashed(make_project):
    issues = make_project({"MC_A01": []})
    assert "V26" in codes(issues, "errore")


def test_repeated_geochemistry_sample_is_an_error(make_project):
    issues = make_project({"MC_A01": [TEPIDA], "MC_B01": [TEPIDA]}, geochemistry=["MC_A01", "MC_B01", "MC_A01"])
    assert "V28" in codes(issues, "errore")
    assert issues.loc[issues["codice"] == "V28", "campione"].tolist() == ["MC_A01"]


def test_cluster_groups_are_checked_before_running(make_project):
    # I gruppi in config nominano i campioni reali, che qui non esistono.
    issues = make_project({"MC_A01": [TEPIDA]})
    c01 = issues[issues["codice"] == "C01"]
    assert (c01["severita"] == "errore").any()
    assert "MC_A01" in set(c01.loc[c01["severita"] == "avviso", "campione"])  # non assegnato ad alcun gruppo


def test_sample_without_counted_individuals_is_an_error(make_project):
    issues = make_project({"MC_A01": [TEPIDA], "MC_B01": [[1, 1, 1, "Ammonia tepida", "I", 0, 0], [1, 1, 2, "Ammonia tepida", "I", None, None]]})
    v29 = issues[issues["codice"] == "V29"]
    assert v29["campione"].tolist() == ["MC_B01"] and (v29["severita"] == "errore").all()


def test_count_without_species_is_an_error(make_project):
    issues = make_project({"MC_A01": [TEPIDA, [1, 1, 2, None, None, 12, None]]})
    v13 = issues[issues["codice"] == "V13"]
    assert v13["riga_excel"].tolist() == [3] and (v13["severita"] == "errore").all()


def test_blank_count_cell_is_missing_not_invalid(make_project):
    issues = make_project({"MC_A01": [TEPIDA, [1, 1, 2, "Ammonia tepida", "I", "  ", None]]})
    assert "V03" not in codes(issues)
    i02 = issues[issues["codice"] == "I02"]
    assert i02["dettagli"].tolist() == ["riga 3"] and (i02["severita"] == "info").all()


def test_single_replica_is_copied_only_where_configured(make_project):
    two_replicas = [TEPIDA, [2, 1, 1, "Ammonia tepida", "I", 4, 0]]
    result = make_project(
        {"MC_A01": two_replicas, "MC_B01": [TEPIDA], "MC_C01": two_replicas},
        copied_replicas={"MC_B01": 2, "MC_C01": 3},
        full=True,
    )
    obs = result.observations
    b01 = obs[obs["campione"] == "MC_B01"]
    assert sorted(b01["replica"]) == [1, 2] and b01["replica_copiata"].tolist() == [False, True]
    assert obs.loc[obs["campione"] == "MC_C01", "individui"].sum() == 9  # già due repliche: non copiato
    issues = result.issues
    assert issues.loc[issues["codice"] == "I03", "campione"].tolist() == ["MC_B01"]
    assert issues.loc[issues["codice"] == "V30", "campione"].tolist() == ["MC_C01"]
    assert "V08" not in codes(issues)  # MC_B01 ora ha 2 repliche come gli altri
