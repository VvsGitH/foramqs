import zipfile

import openpyxl
import pandas as pd
import pytest

from foramqs.charts import Chart, palette
from foramqs.report import write_workbook


def test_palette_has_distinct_colors_without_others_grey():
    colors = palette(60)
    assert len(set(colors)) == 60
    assert "B5B4AE" not in colors


def test_charts_are_native_excel_charts(tmp_path):
    by_sample = pd.DataFrame({"FSI": [3.0, 7.0]}, index=pd.Index(["S1", "S2"], name="Campione"))
    by_class = pd.DataFrame({"S1": [0.4, 0.6], "S2": [0.5, 0.5]}, index=pd.Index(["A", "I"], name="Guscio"))
    path = write_workbook(tmp_path / "r.xlsx", {"FSI": by_sample, "Guscio": by_class, "Dati": by_sample}, charts={
        "FSI": [Chart("FSI", ("FSI",), limits=(("Good", 5.5),))],
        "Guscio": [Chart("Guscio", ("A", "I"), by="rows", stacked=True, percent=True),
                   Chart("Da altro foglio", ("FSI",), source="Dati")],
    }, hidden={"Dati"})
    wb = openpyxl.load_workbook(path)
    assert wb["Dati"].sheet_state == "hidden"
    with zipfile.ZipFile(path) as z:
        assert len([n for n in z.namelist() if n.startswith("xl/charts/chart")]) == 3
