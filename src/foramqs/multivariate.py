"""Cluster gerarchico dei campioni (come in PAST).

Cluster: UPGMA (`method="average"`) su distanze di Bray-Curtis tra le abbondanze relative dei campioni.
L'ordine delle foglie del dendrogramma dà l'ordine dei campioni nelle tabelle e nei grafici. I gruppi di campioni
sono invece definiti dai ricercatori in config ([cluster.groups]): qui si controlla solo che corrispondano a rami
del dendrogramma calcolato.

La CCA non è calcolata qui: si fa in PAST sulle tabelle Tabella_CCA_*.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import dendrogram, linkage, to_tree
from scipy.spatial.distance import pdist

from foramqs.validate import WARNING, Issue


@dataclass(frozen=True)
class SampleClustering:
    linkage: np.ndarray
    samples: list[str]  # nell'ordine delle colonne della matrice usata
    order: list[str]  # ordine delle foglie del dendrogramma


def cluster_samples(relative_table: pd.DataFrame, method: str, metric: str) -> SampleClustering:
    samples = list(relative_table.columns)
    z = linkage(pdist(relative_table.T.to_numpy(), metric), method)
    order = [samples[i] for i in dendrogram(z, no_plot=True)["leaves"]]
    return SampleClustering(linkage=z, samples=samples, order=order)


def branches(clustering: SampleClustering) -> list[frozenset[str]]:
    """Tutti gli insiemi di campioni che formano un ramo del dendrogramma."""
    found = []

    def walk(node) -> frozenset[str]:
        if node.is_leaf():
            return frozenset([clustering.samples[node.id]])
        members = walk(node.left) | walk(node.right)
        found.append(members)
        return members

    walk(to_tree(clustering.linkage))
    return found


def check_group_branches(clustering: SampleClustering, groups: dict[str, list[str]]) -> list[Issue]:
    """C02: gruppi che non sono un ramo del dendrogramma (C01, sui campioni dei gruppi, è in validate.py)."""
    tree_branches = set(branches(clustering))
    return [
        Issue("C02", WARNING, f"Il gruppo {name} non corrisponde a un ramo del dendrogramma UPGMA/Bray-Curtis",
              dettagli=", ".join(members))
        for name, members in groups.items()
        if len(members) > 1 and frozenset(members) not in tree_branches
    ]
