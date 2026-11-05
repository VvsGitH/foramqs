"""Cluster Analysis gerarchica (foglio CA).

Metodo e distanza da config ([cluster]: oggi Ward, euclidea) sulle specie dominanti trasformate con log(1+x).
Q-mode: gli oggetti sono i campioni (righe della tabella CA); R-mode: le specie (colonne).
L'ordine delle foglie del Q-mode dà l'ordine dei campioni in tutti i fogli. I gruppi di campioni sono invece definiti
dai ricercatori in config ([cluster.groups]): qui si controlla solo che corrispondano a rami del dendrogramma Q-mode.

PCA e CCA non sono calcolate qui: si fanno in PAST sul foglio PCA_CCA.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import dendrogram, linkage, to_tree
from scipy.spatial.distance import pdist

from foramqs.validate import WARNING, Issue


@dataclass(frozen=True)
class Clustering:
    linkage: np.ndarray
    samples: list[str]  # oggetti raggruppati (campioni o specie), nell'ordine delle righe della matrice usata
    order: list[str]  # ordine delle foglie del dendrogramma


def cluster(table: pd.DataFrame, method: str, metric: str) -> Clustering:
    """Cluster gerarchico delle righe di `table` (per l'R-mode passare la tabella trasposta)."""
    objects = [str(o) for o in table.index]
    z = linkage(pdist(table.to_numpy(dtype=float), metric), method)
    order = [objects[i] for i in dendrogram(z, no_plot=True)["leaves"]]
    return Clustering(linkage=z, samples=objects, order=order)


def branches(clustering: Clustering) -> list[frozenset[str]]:
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


def check_group_branches(clustering: Clustering, groups: dict[str, list[str]], description: str) -> list[Issue]:
    """C02: gruppi che non sono un ramo del dendrogramma Q-mode (C01, sui campioni dei gruppi, è in validate.py)."""
    tree_branches = set(branches(clustering))
    return [
        Issue("C02", WARNING, f"Il gruppo {name} non corrisponde a un ramo del dendrogramma Q-mode ({description})",
              dettagli=", ".join(members))
        for name, members in groups.items()
        if len(members) > 1 and frozenset(members) not in tree_branches
    ]
