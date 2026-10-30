"""Grafici dei risultati (PNG). I campioni sono sempre nell'ordine del dendrogramma.

Regole di stile: un solo asse y per grafico (due misure diverse = due pannelli), colori categoriali in ordine
fisso e mai riciclati (oltre 8 classi le minori confluiscono in "Others"), barre sottili, griglia leggera.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.cluster.hierarchy import dendrogram  # noqa: E402

from foramqs.multivariate import SampleClustering  # noqa: E402

CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
OTHERS_COLOR = "#b5b4ae"
SURFACE, TEXT, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
MAX_CATEGORIES = len(CATEGORICAL)

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "text.color": TEXT, "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "axes.axisbelow": True, "font.size": 9,
    "axes.titlesize": 11, "axes.titleweight": "semibold", "axes.titlelocation": "left",
})


def _short(samples: list[str]) -> list[str]:
    return [s.removeprefix("MC_") for s in samples]


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def bar_chart(values: pd.Series, order: list[str], title: str, ylabel: str, path: Path,
              thresholds: list[tuple[str, float]] | None = None) -> Path:
    """Una misura per campione; `thresholds` = linee orizzontali etichettate (limiti di classe EQS)."""
    fig, ax = plt.subplots(figsize=(9, 3.6))
    data = values.reindex(order)
    ax.bar(_short(order), data.to_numpy(), color=CATEGORICAL[0], width=0.6)
    for label, limit in thresholds or []:
        ax.axhline(limit, color=MUTED, linewidth=0.8, linestyle=(0, (4, 3)))
        ax.annotate(label, (1.0, limit), xycoords=("axes fraction", "data"), xytext=(4, 0),
                    textcoords="offset points", va="center", fontsize=8, color=MUTED)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="x", rotation=60)
    return _save(fig, path)


def stacked_composition(table: pd.DataFrame, order: list[str], title: str, path: Path) -> Path:
    """Composizione per campione (righe = classi, colonne = campioni, frazioni). Oltre 8 classi → 'Others'."""
    data = table.reindex(columns=order).fillna(0)
    if "Others" in data.index:
        others = data.loc["Others"]
        data = data.drop(index="Others")
    else:
        others = pd.Series(0.0, index=data.columns)
    if len(data) > MAX_CATEGORIES - 1 or others.any():
        ranked = data.sum(axis=1).sort_values(ascending=False).index
        keep = ranked[: MAX_CATEGORIES - 1]
        others = others + data.drop(index=keep).sum()
        data = data.loc[keep]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    bottom = pd.Series(0.0, index=data.columns)
    labels = _short(order)
    for i, (name, row) in enumerate(data.iterrows()):
        ax.bar(labels, row * 100, bottom=bottom * 100, color=CATEGORICAL[i], width=0.6, label=name,
               edgecolor=SURFACE, linewidth=1)
        bottom += row
    if others.any():
        ax.bar(labels, others * 100, bottom=bottom * 100, color=OTHERS_COLOR, width=0.6, label="Others",
               edgecolor=SURFACE, linewidth=1)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Abbondanza relativa (%)")
    ax.set_title(title)
    ax.tick_params(axis="x", rotation=60)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), frameon=False, fontsize=8)
    return _save(fig, path)


def panels(series: dict[str, pd.Series], order: list[str], title: str, path: Path) -> Path:
    """Più misure per campione in pannelli sovrapposti con lo stesso asse x (al posto del doppio asse y)."""
    fig, axes = plt.subplots(len(series), 1, figsize=(9, 2.2 * len(series)), sharex=True)
    for i, (ax, (name, values)) in enumerate(zip(axes, series.items())):
        ax.bar(_short(order), values.reindex(order).to_numpy(), color=CATEGORICAL[i], width=0.6)
        ax.set_ylabel(name)
    axes[0].set_title(title)
    axes[-1].tick_params(axis="x", rotation=60)
    return _save(fig, path)


def dendrogram_chart(clustering: SampleClustering, groups: dict[str, list[str]], path: Path) -> Path:
    """Dendrogramma UPGMA/Bray-Curtis; le etichette riportano il gruppo definito in config."""
    group_of = {s: g for g, members in groups.items() for s in members}
    labels = [f"{s.removeprefix('MC_')} ({group_of.get(s, '-')})" for s in clustering.samples]
    fig, ax = plt.subplots(figsize=(9, 4))
    dendrogram(clustering.linkage, labels=labels, ax=ax, color_threshold=0, above_threshold_color=CATEGORICAL[0],
               leaf_rotation=60, leaf_font_size=8)
    ax.set_ylabel("Dissimilarità di Bray-Curtis")
    ax.set_title("Cluster dei campioni (UPGMA, Bray-Curtis)")
    return _save(fig, path)


def cca_biplot(result, path: Path) -> Path:
    """Biplot CCA: campioni (punti) e variabili ambientali (frecce) sui primi due assi."""
    samples = result.samples.iloc[:, :2]
    env = result.biplot_scores.iloc[:, :2]
    explained = result.proportion_explained.iloc[:2] * 100
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.grid(True, axis="both")
    ax.axhline(0, color=GRID, linewidth=1)
    ax.axvline(0, color=GRID, linewidth=1)
    ax.scatter(samples.iloc[:, 0], samples.iloc[:, 1], s=36, color=CATEGORICAL[0], edgecolor=SURFACE, linewidth=1.5, zorder=3)
    for name, (x, y) in samples.iterrows():
        ax.annotate(name.removeprefix("MC_"), (x, y), xytext=(4, 3), textcoords="offset points", fontsize=7, color=TEXT)
    # Frecce riscalate: la più lunga arriva al campione più lontano dall'origine.
    scale = (samples**2).sum(axis=1).max() ** 0.5 / max((env**2).sum(axis=1).max() ** 0.5, 1e-9)
    arrows = env * scale
    for name, (x, y) in arrows.iterrows():
        ax.annotate("", (x, y), (0, 0), arrowprops=dict(arrowstyle="->", color=CATEGORICAL[1], lw=1.2))
        ax.annotate(name, (x, y), xytext=(3, 3), textcoords="offset points", fontsize=8, color=MUTED)
    ax.update_datalim(arrows.to_numpy())
    ax.autoscale_view()
    ax.margins(0.08)
    ax.set_xlabel(f"CCA1 ({explained.iloc[0]:.1f}%)")
    ax.set_ylabel(f"CCA2 ({explained.iloc[1]:.1f}%)")
    ax.set_title("CCA: specie dominanti e variabili ambientali")
    return _save(fig, path)
