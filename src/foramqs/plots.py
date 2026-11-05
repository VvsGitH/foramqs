"""Grafici come immagine (PNG): i dendrogrammi della Cluster Analysis (Q-mode e R-mode), che non hanno un
equivalente tra i grafici di Excel. Colori e stile sono gli stessi dei grafici Excel (charts.py).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from scipy.cluster.hierarchy import dendrogram  # noqa: E402

from foramqs.multivariate import Clustering  # noqa: E402

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


def q_mode_chart(clustering: Clustering, groups: dict[str, list[str]], method: str, path: Path) -> Path:
    """Dendrogramma Q-mode (campioni); le etichette riportano il gruppo definito in config."""
    group_of = {s: g for g, members in groups.items() for s in members}
    labels = [f"{s.removeprefix('MC_')} ({group_of.get(s, '-')})" for s in clustering.samples]
    fig, ax = plt.subplots(figsize=(9, 4))
    dendrogram(clustering.linkage, labels=labels, ax=ax, color_threshold=0, above_threshold_color=CATEGORICAL[0],
               leaf_rotation=60, leaf_font_size=8)
    ax.set_ylabel("Distanza")
    ax.set_title(f"Cluster Analysis Q-mode: campioni ({method})")
    return _save(fig, path)


def r_mode_chart(clustering: Clustering, method: str, path: Path) -> Path:
    """Dendrogramma R-mode (specie), orizzontale perché i nomi delle specie sono lunghi."""
    fig, ax = plt.subplots(figsize=(9, max(4.0, 0.25 * len(clustering.samples) + 1)))
    dendrogram(clustering.linkage, labels=clustering.samples, ax=ax, orientation="left", color_threshold=0,
               above_threshold_color=CATEGORICAL[1], leaf_font_size=8)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)
    ax.set_xlabel("Distanza")
    ax.set_title(f"Cluster Analysis R-mode: specie ({method})")
    return _save(fig, path)
