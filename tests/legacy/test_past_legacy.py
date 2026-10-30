"""Gli indici PAST riprodotti sulla stessa matrice usata allora (foglio Indici_PAST, 4 cifre significative)."""

import pytest

from foramqs.indices.diversity import diversity_indices

# In PAST MC_PN01 ha un taxon in più rispetto alla matrice salvata nel Results: è stato calcolato su una
# versione diversa dei dati, quindi non è confrontabile.
NOT_COMPARABLE = {"MC_PN01"}


def test_only_pn01_was_computed_on_a_different_matrix(legacy_matrix, indici_past):
    differing = {
        s for s, counts in legacy_matrix.counts.items()
        if sum(1 for n in counts if n > 0) != indici_past["Taxa_S"][s] or sum(counts) != indici_past["Individuals"][s]
    }
    assert differing == NOT_COMPARABLE


@pytest.mark.parametrize("index", [
    "Taxa_S", "Individuals", "Dominance_D", "Simpson_1-D", "Shannon_H", "Evenness_e^H/S", "Brillouin", "Menhinick",
    "Margalef", "Equitability_J", "Fisher_alpha", "Berger-Parker", "Chao-1", "iChao-1", "ACE", "Squares",
])
def test_index_matches_past(index, legacy_matrix, indici_past):
    for sample, counts in legacy_matrix.counts.items():
        if sample in NOT_COMPARABLE:
            continue
        assert diversity_indices(counts)[index] == pytest.approx(indici_past[index][sample], rel=1e-3), sample
