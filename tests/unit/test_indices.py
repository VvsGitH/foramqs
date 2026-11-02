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


def test_foramecoqs_table_with_alternative_foram_ambi():
    from foramqs.indices.foramecoqs import foramecoqs_table

    abundance = pd.DataFrame({"S1": [10, 20, 10], "S2": [5, 5, 10]}, index=["Sp1", "Sp2", "Sp3"])
    fsi_group = pd.Series(["Sen", "Str", "ND"], index=["Sp1", "Sp2", "Sp3"])
    eco_group = pd.Series(["1", "2", "3"], index=["Sp1", "Sp2", "Sp3"])
    # Nella lista alternativa: Sp1 è 3, Sp2 è NA (non presente), Sp3 è 4
    alt_eco = pd.Series(["3", "NA", "4"], index=["Sp1", "Sp2", "Sp3"])
    eqs_rules = {
        "exp_hbc": [["High", ">=", 22], ["Good", ">=", 13], ["Moderate", ">=", 7], ["Poor", ">", 3], ["Bad"]],
        "fsi": [["High", ">=", 9], ["Good", ">=", 5.5], ["Moderate", ">=", 2], ["Poor", ">=", 1], ["Bad"]],
        "foram_ambi": [["High", "<=", 1.2], ["Good", "<=", 3.3], ["Moderate", "<=", 4.3], ["Poor", "<=", 5.5], ["Bad"]],
    }
    table = foramecoqs_table(
        abundance, fsi_group, eco_group, eqs_rules,
        alt_eco_group=alt_eco, alt_samples=["S1"], alt_label="Foram-AMBI (Alt)",
    )
    assert "Foram-AMBI (Alt)" in table.columns
    assert "EQS Foram-AMBI (Alt)" in table.columns
    assert "% non assegnati Foram-AMBI (Alt)" in table.columns

    # S1 (N = 40): Sp1=10 (EG 3: peso 3.0), Sp2=20 (NA: peso 0), Sp3=10 (EG 4: peso 4.5)
    # AMBI alt = (10*3.0 + 10*4.5) / 40 = 75 / 40 = 1.875 -> EQS Good (<= 3.3)
    # Non assegnati alt = 20 / 40 = 50.0%
    assert table.loc["S1", "Foram-AMBI (Alt)"] == 1.875
    assert table.loc["S1", "EQS Foram-AMBI (Alt)"] == "Good"
    assert table.loc["S1", "% non assegnati Foram-AMBI (Alt)"] == 50.0

    # S2 non è in alt_samples: deve essere NaN e vuoto
    assert math.isnan(table.loc["S2", "Foram-AMBI (Alt)"])
    assert table.loc["S2", "EQS Foram-AMBI (Alt)"] == ""
    assert math.isnan(table.loc["S2", "% non assegnati Foram-AMBI (Alt)"])
