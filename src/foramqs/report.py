"""Scrittura dei report Excel (fogli con filtri, intestazione bloccata, larghezze leggibili e grafici)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl.drawing.image import Image
from openpyxl.utils import get_column_letter

IMAGE_WIDTH_PX = 760
ROW_HEIGHT_PX = 20


def write_workbook(path: Path, sheets: dict[str, pd.DataFrame], figures: dict[str, list[Path]] | None = None) -> Path:
    """Un foglio per tabella; se l'indice non è un semplice contatore diventa la prima colonna.

    I grafici di `figures` vengono inseriti a destra della tabella del foglio con lo stesso nome.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame = frame if isinstance(frame.index, pd.RangeIndex) else frame.reset_index()
            frame.to_excel(writer, sheet_name=name, index=False)
            ws = writer.sheets[name]
            ws.freeze_panes = "B2"
            if frame.shape[1]:
                ws.auto_filter.ref = ws.dimensions
            for i, col in enumerate(frame.columns, start=1):
                longest = max([len(str(col)), *(len(str(v)) for v in frame[col].head(500))], default=8)
                ws.column_dimensions[get_column_letter(i)].width = min(max(10, longest + 2), 60)
            row = 2
            for figure in (figures or {}).get(name, []):
                image = Image(figure)
                scale = IMAGE_WIDTH_PX / image.width
                image.width, image.height = IMAGE_WIDTH_PX, int(image.height * scale)
                ws.add_image(image, f"{get_column_letter(frame.shape[1] + 2)}{row}")
                row += image.height // ROW_HEIGHT_PX + 2
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
