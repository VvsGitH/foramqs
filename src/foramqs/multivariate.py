"""Analisi multivariate dei campioni: cluster gerarchico (come in PAST) e CCA.

Cluster: UPGMA (`method="average"`) su distanze di Bray-Curtis tra le abbondanze relative dei campioni.
L'ordine delle foglie del dendrogramma dà l'ordine dei campioni nelle tabelle e nei grafici. I gruppi di campioni
sono invece definiti dai ricercatori in config ([cluster.groups]): qui si controlla solo che corrispondano a rami
del dendrogramma calcolato.

CCA: Canonical Correspondence Analysis (ter Braak 1986), implementazione di scikit-bio (Legendre & Legendre 2012),
lo stesso algoritmo usato da PAST.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import dendrogram, linkage, to_tree
from scipy.spatial.distance import pdist
from skbio.stats.ordination import OrdinationResults, cca

from foramqs.validate import ERROR, WARNING, Issue


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


def check_groups(clustering: SampleClustering, groups: dict[str, list[str]]) -> list[Issue]:
    """C01-C02: gruppi con campioni sconosciuti o ripetuti; gruppi che non sono un ramo del dendrogramma."""
    issues = []
    known = set(clustering.samples)
    assigned = [s for members in groups.values() for s in members]
    for sample in sorted(set(assigned) - known):
        issues.append(Issue("C01", ERROR, f"Campione '{sample}' in [cluster.groups] ma non nei dati", sample))
    for sample in sorted({s for s in assigned if assigned.count(s) > 1}):
        issues.append(Issue("C01", ERROR, f"Campione '{sample}' assegnato a più gruppi in [cluster.groups]", sample))
    for sample in sorted(known - set(assigned)):
        issues.append(Issue("C01", WARNING, f"Campione '{sample}' non assegnato ad alcun gruppo di cluster", sample))
    tree_branches = set(branches(clustering))
    for name, members in groups.items():
        if len(members) > 1 and frozenset(members) not in tree_branches:
            issues.append(Issue(
                "C02", WARNING, f"Il gruppo {name} non corrisponde a un ramo del dendrogramma UPGMA/Bray-Curtis",
                dettagli=", ".join(members),
            ))
    return issues


def canonical_correspondence(species: pd.DataFrame, environment: pd.DataFrame) -> OrdinationResults:
    """CCA: `species` = campioni × specie (abbondanze), `environment` = campioni × variabili ambientali."""
    return cca(species, environment.loc[species.index], scaling=2)


def cca_axes(result: OrdinationResults, environment: pd.DataFrame) -> pd.DataFrame:
    """Autovalori e % di inerzia per asse; i primi (rango delle variabili ambientali) sono gli assi vincolati.

    Variabili ambientali collineari (es. GRAVEL + SAND + SILT = 100) riducono il numero di assi vincolati.
    """
    rank = np.linalg.matrix_rank((environment - environment.mean()).to_numpy())
    kind = ["vincolato" if i < rank else "residuo" for i in range(len(result.eigvals))]
    return pd.DataFrame(
        {"tipo": kind, "autovalore": result.eigvals.to_numpy(), "% inerzia": result.proportion_explained.to_numpy() * 100},
        index=pd.Index(result.eigvals.index, name="Asse"),
    )
