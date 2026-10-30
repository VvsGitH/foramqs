"""Gli indici ForamEcoQS riprodotti sugli stessi input usati allora.

Il foglio `Foram Echo QS` è stato prodotto dalla GUI di ForamEcoQS sulla matrice prima delle correzioni di nome,
con la riga 'Mud (%)' contata come una specie: aggiungendo quella riga i valori coincidono esattamente.
"""

import pytest

from foramqs.indices.foramecoqs import exp_hbc, foram_ambi, fsi, species_richness


def test_exp_hbc_and_richness_match_foramecoqs(legacy_matrix, legacy_mud, foram_echo_qs):
    for sample, counts in legacy_matrix.counts.items():
        as_run_then = [*counts, legacy_mud[sample]]
        assert exp_hbc(as_run_then) == pytest.approx(foram_echo_qs[sample]["exp(H'bc)"], abs=5e-5), sample
        assert species_richness(as_run_then) == foram_echo_qs[sample]["Species Richness (S)"], sample


def test_mud_row_inflated_richness_by_one(legacy_matrix, foram_echo_qs):
    for sample, counts in legacy_matrix.counts.items():
        assert species_richness(counts) == foram_echo_qs[sample]["Species Richness (S)"] - 1


def test_fsi_matches_foramecoqs(legacy_matrix, specie_stilevita, foram_echo_qs):
    groups = {name: row["Ecological group FSI"] for name, row in specie_stilevita.items()}
    for sample, counts in legacy_matrix.counts.items():
        abundance = dict(zip(legacy_matrix.species, counts))
        sen = sum(n for name, n in abundance.items() if groups.get(name) == "Sen")
        tol = sum(n for name, n in abundance.items() if groups.get(name) == "Str")
        assert fsi(sen, tol) == pytest.approx(foram_echo_qs[sample]["FSI"], abs=5e-4), sample


def test_foram_ambi_formula_matches_power_query(pq_eco_groups):
    """Formula verificata sulle frazioni per gruppo salvate da Power Query (differenze solo di arrotondamento).

    Non si ricalcolano le frazioni dalla matrice: il foglio del vecchio Results è stato prodotto con una versione
    precedente dei gruppi ecologici di `specie_stilevita` e non è più stato aggiornato.
    """
    labels = {1: "GI", 2: "GII", 3: "GIII", 4: "GIV", 5: "GV"}
    for sample, row in pq_eco_groups.items():
        if not sample.startswith("MC_"):
            continue
        by_group = {g: row[label] or 0 for g, label in labels.items()}
        assert foram_ambi(by_group, 1.0) == pytest.approx(row["Foram-AMBI 2025"], abs=5e-4), sample
