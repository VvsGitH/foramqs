"""`check` di un workbook costruito nel test: i casi limite devono diventare segnalazioni, non eccezioni."""

import shutil
from pathlib import Path

import openpyxl
import pandas as pd
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
              full: bool = False, alt_ambi: dict | None = None):
        if copied_replicas is not None:
            cfg.raw["input"]["copied_replicas"] = copied_replicas
        if alt_ambi is not None:
            cfg.raw["foram_ambi_alternative"] = {**cfg.raw.get("foram_ambi_alternative", {}), **alt_ambi}
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


def test_alternative_ambi_unknown_sample_is_an_error(make_project):
    issues = make_project({"MC_A01": [TEPIDA]}, alt_ambi={"samples": ["MC_UNKNOWN"]})
    assert "A01" in codes(issues, "errore")
    assert issues.loc[issues["codice"] == "A01", "campione"].tolist() == ["MC_UNKNOWN"]


def test_alternative_ambi_missing_file_is_an_error(make_project):
    issues = make_project({"MC_A01": [TEPIDA]}, alt_ambi={"samples": ["MC_A01"], "file": "reference/nonexistent.csv"})
    assert "A02" in codes(issues, "errore")


def test_alternative_ambi_invalid_eco_group_is_an_error(make_project, tmp_path):
    alt_file = tmp_path / "reference" / "foram_ambi_alt.csv"
    alt_file.write_text("nome;gruppo_ecologico\nAmmonia tepida;99\n", encoding="utf-8")
    issues = make_project({"MC_A01": [TEPIDA]}, alt_ambi={"samples": ["MC_A01"], "file": str(alt_file)})
    assert "A03" in codes(issues, "errore")


def test_alternative_ambi_sheet_name_too_long_for_excel_is_an_error(make_project):
    issues = make_project({"MC_A01": [TEPIDA]}, alt_ambi={"samples": ["MC_A01"], "groups_sheet": "Abbondanza_rel%_gruppiecologici_alt"})
    assert "A05" in codes(issues, "errore")


def test_pipeline_run_with_alternative_foram_ambi(tmp_path):
    from foramqs.pipeline import run

    shutil.copytree(DEFAULT_CONFIG.parent, tmp_path / "config")
    shutil.copytree(PROJECT_ROOT / "reference", tmp_path / "reference")
    cfg = load_config(tmp_path / "config" / DEFAULT_CONFIG.name)
    cfg.raw["paths"]["data_workbook"] = str(PROJECT_ROOT / "input_data" / "Campioni_P_2025_Data_Raw.xlsx")

    alt_file = tmp_path / "reference" / "foram_ambi_alt.csv"
    alt_file.write_text("nome;gruppo_ecologico\nAmmonia tepida;3\n", encoding="utf-8")

    cfg.raw["foram_ambi_alternative"]["samples"] = ["MC_CB01", "MC_CE01"]
    cfg.raw["foram_ambi_alternative"]["label"] = "Foram-AMBI (Alt)"

    res = run(cfg, figures_dir=tmp_path / "figures", offline=True)
    assert all(len(name) <= 31 for name in res.sheets)  # limite di Excel: oltre, i grafici perdono il foglio di origine
    assert "Abbondanza_rel%_gruppiecol_alt" in res.sheets
    alt_sheet = res.sheets["Abbondanza_rel%_gruppiecol_alt"]
    assert set(alt_sheet.index) == {"MC_CB01", "MC_CE01"}
    assert "Foram-AMBI (Alt)" in alt_sheet.columns

    comparison = res.sheets["Confronto_gruppi_ecologici"]
    assert comparison.columns.tolist() == ["GE Jorissen", "GE Bouchet"]
    assert comparison.loc["Ammonia tepida", "GE Bouchet"] == "GIII"
    assert set(comparison["GE Bouchet"]) == {"GIII", "NA"}  # solo Ammonia tepida è nel file alternativo del test

    feqs = res.sheets["Foram Echo QS"]
    assert "Foram-AMBI (Alt)" in feqs.columns
    assert "EQS Foram-AMBI (Alt)" in feqs.columns
    assert pd.notna(feqs.loc["MC_CB01", "Foram-AMBI (Alt)"])
    assert pd.notna(feqs.loc["MC_CE01", "Foram-AMBI (Alt)"])
    assert pd.isna(feqs.loc["MC_FL01", "Foram-AMBI (Alt)"])

    # Con la ridistribuzione degli NA (config di default) il foglio dei gruppi mostra le percentuali usate dall'indice:
    # GI–GV sommano a 1 e Σ peso·% ricostruisce il Foram-AMBI della stessa riga; gli NA restano a parte, fuori dal grafico.
    from foramqs.indices.foramecoqs import ECO_GROUP_WEIGHTS

    eco = res.sheets["Abbondanza_rel%_gruppiecologici"]
    weights = {g: w for g, w in zip(["GI", "GII", "GIII", "GIV", "GV"], ECO_GROUP_WEIGHTS.values()) if g in eco.columns}
    assert eco[list(weights)].sum(axis=1).round(9).eq(1).all()
    rebuilt = sum(w * eco[g] for g, w in weights.items())
    assert (rebuilt - eco["Foram-AMBI"]).abs().max() < 5e-4
    assert eco.loc["MC_FL01", "NA (ridistribuiti)"] > 0
    assert "NA (ridistribuiti)" not in res.charts["Abbondanza_rel%_gruppiecologici"][0].series
