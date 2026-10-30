import shutil

import openpyxl
import pytest
import tomlkit
from openpyxl.worksheet.table import Table

from foramqs.config import DEFAULT_CONFIG, load_config
from foramqs.io_excel import read_tables, sample_tables
from foramqs.new_sample import NewSampleError, add_sample
from foramqs.validate import check_sample_tables

COLUMNS = ["REPLICA", "N°SLIDE", "CASELLA", "SPECIE (LONG FORMAT)", "TIPO GUSCIO", "N°INDIVIDUI", "DEFORMATI"]


@pytest.fixture
def project(tmp_path):
    """Progetto minimo: config reale copiata e un workbook con un campione, la geochimica e una nota sotto."""
    config_path = tmp_path / "config" / "pipeline.toml"
    config_path.parent.mkdir()
    shutil.copy(DEFAULT_CONFIG, config_path)
    cfg = load_config(config_path)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MC_A01"
    ws.append([*COLUMNS, "COMMENTI & DUBBI"])
    ws.append([1, 1, 1, "Ammonia tepida", "I", 3, 0, None])
    ws.add_table(Table(displayName="MC_A01", ref="A1:G2"))
    geo = wb.create_sheet("Variabili_campioni")
    geo.append(["Colonna1", "TOC (%)"])
    geo.append(["MC_A01", 0.5])
    geo.add_table(Table(displayName="Geochimica_campioni", ref="A1:B2"))
    geo["A4"] = "nota sotto la tabella"
    workbook = cfg.path("data_workbook")
    workbook.parent.mkdir(parents=True)
    wb.save(workbook)
    return cfg, config_path, workbook


def test_add_sample_creates_table_geochemistry_row_and_group(project):
    cfg, config_path, workbook = project
    added = add_sample(cfg, config_path, "MC_B01", "G9")

    samples = sample_tables(read_tables(workbook), COLUMNS)
    assert list(samples) == ["MC_A01", "MC_B01"]
    assert samples["MC_B01"].data.empty
    assert check_sample_tables(samples)[0].codice == "V26"

    wb = openpyxl.load_workbook(workbook)
    assert wb.sheetnames == ["MC_A01", "MC_B01", "Variabili_campioni"]
    assert wb["MC_B01"]["H1"].value == "COMMENTI & DUBBI"
    geo = wb["Variabili_campioni"]
    assert geo.tables["Geochimica_campioni"].ref == "A1:B3"
    assert (geo["A3"].value, geo["B3"].value, geo["A5"].value) == ("MC_B01", None, "nota sotto la tabella")

    config_text = config_path.read_text(encoding="utf-8")
    assert tomlkit.parse(config_text)["cluster"]["groups"]["G9"] == ["MC_B01"]
    assert "# Gruppi di campioni definiti dai ricercatori" in config_text  # commenti preservati
    assert added.group_created and added.backup.exists() and not added.removed_power_query


@pytest.mark.parametrize("name, reason", [
    ("MC01", "riferimento di cella"),
    ("MC A01", "non è un nome valido"),
    ("MC_A01", "esiste già una Tabella"),
    ("MC_FL01", "già nel gruppo di cluster"),
])
def test_invalid_names_are_rejected_without_changes(project, name, reason):
    cfg, config_path, workbook = project
    before = workbook.read_bytes(), config_path.read_text(encoding="utf-8")
    with pytest.raises(NewSampleError, match=reason):
        add_sample(cfg, config_path, name, "G1")
    assert (workbook.read_bytes(), config_path.read_text(encoding="utf-8")) == before


def test_open_workbook_is_not_modified(project):
    cfg, config_path, workbook = project
    workbook.with_name(f"~${workbook.name}").touch()
    with pytest.raises(NewSampleError, match="aperto in Excel"):
        add_sample(cfg, config_path, "MC_B01", "G1")


def test_failed_config_write_restores_the_workbook(project):
    cfg, config_path, workbook = project
    before = workbook.read_bytes()
    config_path.chmod(0o444)
    try:
        with pytest.raises(PermissionError):
            add_sample(cfg, config_path, "MC_B01", "G1")
    finally:
        config_path.chmod(0o644)
    assert workbook.read_bytes() == before
    assert "MC_B01" not in config_path.read_text(encoding="utf-8")
