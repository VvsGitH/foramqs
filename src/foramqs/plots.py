"""Grafici come immagine (PNG): solo il dendrogramma, che non ha un equivalente tra i grafici di Excel.

Gli altri grafici sono grafici Excel nativi (charts.py). Colori e stile sono gli stessi.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from scipy.cluster.hierarchy import dendrogram  # noqa: E402

from foramqs.multivariate import SampleClustering  # noqa: E402

CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SURFACE, TEXT, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "text.color": TEXT, "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "axes.axisbelow": True, "font.size": 9,
    "axes.titlesize": 11, "axes.titleweight": "semibold", "axes.titlelocation": "left",
})


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


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
