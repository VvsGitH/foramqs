"""Grafici Excel nativi (openpyxl), collegati alle celle dei fogli del Results.

Un grafico è descritto da un `Chart`: quali righe o colonne della tabella disegnare, a barre semplici o impilate.
`report.write_workbook` lo traduce in un grafico Excel accanto alla tabella. I dati restano nelle celle, quindi in
Excel il grafico si può modificare come qualsiasi altro.

Stile: un colore fisso per classe, in ordine (oltre la tavolozza categoriale i colori sono generati); "Others" in
grigio; i limiti di classe EQS sono linee tratteggiate a valore costante.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass

import pandas as pd
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.data_source import AxDataSource, NumData, NumDataSource, NumVal, StrRef
from openpyxl.chart.text import RichText
from openpyxl.chart.series import Series, SeriesLabel
from openpyxl.drawing.text import CharacterProperties, Paragraph, ParagraphProperties
from openpyxl.worksheet.worksheet import Worksheet

CATEGORICAL = ["2A78D6", "EB6834", "1BAF7A", "EDA100", "E87BA4", "008300", "6250D6", "E34948"]
OTHERS_COLOR = "B5B4AE"
LIMIT_COLOR = "52514E"
CM_PER_ROW = 0.53  # altezza di una riga Excel standard (20 px)
MAX_SIDE_LEGEND = 12  # oltre, la legenda va sotto il grafico


@dataclass(frozen=True)
class Chart:
    title: str
    series: tuple[str, ...]  # nomi delle colonne (by="columns") o etichette di riga (by="rows") da disegnare
    by: str = "columns"  # "columns": categorie = righe della tabella; "rows": categorie = colonne della tabella
    stacked: bool = False
    percent: bool = False  # valori in frazioni 0-1: asse in %
    y_title: str = ""
    limits: tuple[tuple[str, float], ...] = ()  # linee orizzontali (etichetta, valore)
    source: str | None = None  # foglio che contiene i dati, se diverso da quello del grafico
    width: float = 22.0  # cm
    height: float = 9.0  # cm

    @property
    def rows(self) -> int:
        """Righe di foglio occupate dal grafico, per impilare i grafici uno sotto l'altro."""
        return int(self.height / CM_PER_ROW) + 2


def palette(n: int) -> list[str]:
    """`n` colori ben distinti: prima la tavolozza categoriale, poi tinte generate con l'angolo aureo.

    Saturazione e luminosità si alternano perché colori vicini nella pila restino distinguibili; nessun grigio,
    riservato a "Others".
    """
    generated = []
    for i in range(max(n - len(CATEGORICAL), 0)):
        rgb = colorsys.hsv_to_rgb((0.11 + i * 0.618034) % 1, (0.75, 0.5, 0.9)[i % 3], (0.85, 0.6, 0.7, 0.95)[i % 4])
        generated.append("".join(f"{round(c * 255):02X}" for c in rgb))
    return (CATEGORICAL + generated)[:n]


def build(chart: Chart, ws: Worksheet, frame: pd.DataFrame) -> BarChart:
    """Grafico Excel per `chart`; `frame` è la tabella come scritta in `ws` (intestazione in riga 1, dati da A2)."""
    bar = BarChart()
    bar.type = "col"
    bar.title = chart.title
    bar.width, bar.height = chart.width, chart.height
    bar.gapWidth = 60
    if chart.stacked:
        bar.grouping, bar.overlap = "stacked", 100

    n_rows, n_cols = frame.shape
    if chart.by == "columns":
        categories = Reference(ws, min_col=1, min_row=2, max_row=n_rows + 1)
        for name in chart.series:
            col = frame.columns.get_loc(name) + 1
            bar.add_data(Reference(ws, min_col=col, min_row=1, max_row=n_rows + 1), titles_from_data=True)
        n_categories = n_rows
    elif chart.by == "rows":
        categories = Reference(ws, min_row=1, min_col=2, max_col=n_cols)
        labels = list(frame.iloc[:, 0])
        for name in chart.series:
            row = labels.index(name) + 2
            bar.add_data(Reference(ws, min_row=row, min_col=1, max_col=n_cols), from_rows=True, titles_from_data=True)
        n_categories = n_cols - 1
    else:
        raise ValueError(f"Chart.by sconosciuto: {chart.by!r} (ammessi: 'columns', 'rows')")
    for s in bar.series:  # i nomi dei campioni sono testo: riferimento di testo, non numerico
        s.cat = AxDataSource(strRef=StrRef(f=str(categories)))

    colors = palette(len(chart.series))
    for color, name, s in zip(colors, chart.series, bar.series):
        fill = OTHERS_COLOR if str(name).startswith("Others") else color
        s.graphicalProperties.solidFill = fill
        s.graphicalProperties.line.solidFill = "FFFFFF" if chart.stacked else fill

    bar.x_axis.delete = False
    bar.y_axis.delete = False
    bar.y_axis.title = chart.y_title or None
    bar.y_axis.scaling.min = 0
    if chart.percent:
        bar.y_axis.number_format = "0%"
        bar.y_axis.scaling.max = 1
    bar.x_axis.tickLblSkip = 1  # un'etichetta per campione

    if chart.limits:
        bar += _limit_lines(chart.limits, n_categories)
    if len(chart.series) == 1 and not chart.limits:
        bar.legend = None
    elif chart.limits:
        bar.legend.position = "b"
    elif len(chart.series) > MAX_SIDE_LEGEND:
        # Decine di serie (specie): legenda sotto, su più colonne e in piccolo, perché a destra verrebbe troncata.
        bar.legend.position = "b"
        bar.legend.txPr = RichText(p=[Paragraph(pPr=ParagraphProperties(defRPr=CharacterProperties(sz=800)),
                                                endParaRPr=CharacterProperties(sz=800))])
    else:
        bar.legend.position = "r"
    _no_overlay(bar)
    return bar


def _no_overlay(bar: BarChart) -> None:
    """Titolo, legenda e titolo dell'asse fuori dall'area del grafico (altrimenti Excel li sovrappone alle barre)."""
    bar.title.overlay = False
    bar.title.tx.rich.p[0].pPr = ParagraphProperties(defRPr=CharacterProperties(sz=1200, b=True))
    if bar.legend is not None:
        bar.legend.overlay = False
    if bar.y_axis.title is not None:
        bar.y_axis.title.overlay = False


def _limit_lines(limits: tuple[tuple[str, float], ...], n_categories: int) -> LineChart:
    """Una serie a valore costante (dato letterale, senza celle) per ogni limite."""
    line = LineChart()
    for label, value in limits:
        points = NumData(pt=[NumVal(idx=i, v=value) for i in range(n_categories)], ptCount=n_categories)
        s = Series(val=NumDataSource(numLit=points), tx=SeriesLabel(v=f"{label} ({value:g})"))
        s.graphicalProperties.line.solidFill = LIMIT_COLOR
        s.graphicalProperties.line.dashStyle = "dash"
        s.graphicalProperties.line.width = 12700  # 1 pt
        s.marker.symbol = "none"
        s.smooth = False
        line.series.append(s)
    return line
