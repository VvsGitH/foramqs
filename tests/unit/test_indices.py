import math

import pandas as pd
import pytest

from foramqs.csharp_compat import cs_round
from foramqs.indices.diversity import diversity_indices
from foramqs.indices.foramecoqs import eqs_class, exp_hbc, foram_ambi, fsi, species_richness

FSI_RULES = [["Azoic", "==", 0], ["High", ">=", 9], ["Good", ">=", 5.5], ["Moderate", ">=", 2], ["Poor", ">=", 1], ["Bad"]]


def test_cs_round_matches_dotnet_midpoints():
    assert cs_round(2.675, 2) == 2.68  # round() di Python darebbe 2.67
    assert cs_round(4.5625, 3) == 4.562  # al pari, come Math.Round
    assert cs_round(0.65625, 3) == 0.656


def test_fsi_uses_only_assigned_taxa():
    assert fsi(3, 1) == 7.75  # (10·75 + 25) / 100
    assert fsi(0, 0) == 0.0


def test_foram_ambi_divides_by_all_named_taxa():
    assert foram_ambi({2: 50, 3: 50}, 100) == 2.25
    assert foram_ambi({2: 50, 3: 50}, 200) == 1.125  # 100 individui senza gruppo pesano come il gruppo I


def test_exp_hbc_edge_cases():
    assert exp_hbc([]) == 1.0
    assert exp_hbc([10, 0, 0]) == 1.0  # una sola specie senza singleton
    # Nessun singleton: copertura C = 1, ma resta il fattore di Horvitz-Thompson 1/(1 − (1 − p)^N).
    assert exp_hbc([5, 5, 5, 5]) == round(math.exp(round(math.log(4) / (1 - 0.75**20), 4)), 4)


def test_species_richness_ignores_zeros():
    assert species_richness([3, 0, 1, 0]) == 2


def test_eqs_class_operators():
    assert eqs_class(0, FSI_RULES) == "Azoic"
    assert eqs_class(9, FSI_RULES) == "High"
    assert eqs_class(5.49, FSI_RULES) == "Moderate"
    assert eqs_class(0.5, FSI_RULES) == "Bad"
    assert eqs_class(math.nan, FSI_RULES) == "N/A"


def test_past_indices_on_hand_computed_sample():
    idx = diversity_indices([2, 1, 1])  # N = 4, S = 3
    assert idx["Dominance_D"] == pytest.approx(2 / 12)  # Σn(n−1)/(N(N−1))
    assert idx["Berger-Parker"] == 0.5
    assert idx["Menhinick"] == pytest.approx(3 / 2)
    h = -(0.5 * math.log(0.5) + 2 * 0.25 * math.log(0.25))
    assert idx["Equitability_J"] == pytest.approx(h / math.log(3))
    assert idx["Shannon_H"] == pytest.approx(h + 2 / 8)  # Miller–Madow: + (S−1)/(2N)


@pytest.mark.parametrize("counts", [[1], [1, 1, 1], [2], [1, 2]])
def test_diversity_indices_on_tiny_samples_do_not_raise(counts):
    values = diversity_indices(counts)
    assert values["Taxa_S"] == len(counts)


def test_squares_is_undefined_when_all_taxa_are_singletons():
    assert math.isnan(diversity_indices([1, 1, 1])["Squares"])
    assert diversity_indices([1, 1, 3])["Squares"] == pytest.approx(3 + 4 * 11 / (25 - 6))
