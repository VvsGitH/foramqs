"""Scrittura dei report Excel (fogli con filtri, intestazione bloccata, larghezze leggibili, grafici e immagini)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl.drawing.image import Image
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from foramqs.charts import Chart, build

IMAGE_WIDTH_PX = 760
ROW_HEIGHT_PX = 20
RED = Font(color="FFC00000")


def write_workbook(
    path: Path,
    sheets: dict[str, pd.DataFrame],
    figures: dict[str, list[Path]] | None = None,
    charts: dict[str, list[Chart]] | None = None,
    hidden: set[str] = frozenset(),
    highlights: dict[str, dict[str, list]] | None = None,
) -> Path:
    """Un foglio per tabella; se l'indice non è un semplice contatore diventa la prima colonna.

    A destra della tabella di ogni foglio vengono messi, uno sotto l'altro, le immagini di `figures` e poi i
    grafici Excel di `charts` con lo stesso nome di foglio. I fogli in `hidden` (dati di supporto ai grafici) sono nascosti.
    `highlights` (foglio → colonna → valori dell'indice) indica le celle da scrivere in rosso.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    written: dict[str, pd.DataFrame] = {}
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            labels = list(frame.index)
            frame = frame if isinstance(frame.index, pd.RangeIndex) else frame.reset_index()
            frame.to_excel(writer, sheet_name=name, index=False)
            written[name] = frame
            ws = writer.sheets[name]
            ws.freeze_panes = "B2"
            if frame.shape[1]:
                ws.auto_filter.ref = ws.dimensions
            for i, col in enumerate(frame.columns, start=1):
                longest = max([len(str(col)), *(len(str(v)) for v in frame[col].head(500))], default=8)
                ws.column_dimensions[get_column_letter(i)].width = min(max(10, longest + 2), 60)
            for column, rows in (highlights or {}).get(name, {}).items():
                col = frame.columns.get_loc(column) + 1
                for label in rows:
                    ws.cell(labels.index(label) + 2, col).font = RED
            if name in hidden:
                ws.sheet_state = "hidden"

        # Dopo aver scritto tutti i fogli: un grafico può prendere i dati da un altro foglio (Chart.source).
        for name, frame in written.items():
            ws = writer.sheets[name]
            anchor_col = get_column_letter(frame.shape[1] + 2)
            row = 2
            for figure in (figures or {}).get(name, []):
                image = Image(figure)
                scale = IMAGE_WIDTH_PX / image.width
                image.width, image.height = IMAGE_WIDTH_PX, int(image.height * scale)
                ws.add_image(image, f"{anchor_col}{row}")
                row += image.height // ROW_HEIGHT_PX + 2
            for chart in (charts or {}).get(name, []):
                source = chart.source or name
                ws.add_chart(build(chart, writer.sheets[source], written[source]), f"{anchor_col}{row}")
                row += chart.rows
    return path


def issue_summary(issues: pd.DataFrame) -> pd.DataFrame:
    """Numero di segnalazioni per codice, con il primo messaggio come esempio."""
    if issues.empty:
        return pd.DataFrame(columns=["codice", "severita", "n", "esempio"])
    return (
        issues.groupby(["codice", "severita"], sort=False)
        .agg(n=("messaggio", "size"), esempio=("messaggio", "first"))
        .reset_index()
    )
