import math

import pandas as pd
import pytest

from foramqs.csharp_compat import cs_round
from foramqs.indices.diversity import diversity_indices
from foramqs.indices.foramecoqs import eqs_class, exp_hbc, foram_ambi, fsi, species_richness

FSI_RULES = [["Azoic", "==", 0], ["High", ">=", 9], ["Good", ">=", 5.5], ["Moderate", ">=", 2], ["Poor", ">=", 1], ["Bad"]]
EXP_HBC_EQR_RULES = [["HIGH", ">=", 0.8], ["GOOD", ">=", 0.6], ["MODERATE", ">=", 0.4], ["POOR", ">=", 0.2], ["BAD"]]


@pytest.mark.parametrize("eqr, quality", [
    (1.0, "HIGH"), (0.8, "HIGH"), (0.7999, "GOOD"), (0.6, "GOOD"), (0.4, "MODERATE"),
    (0.3999, "POOR"), (0.2, "POOR"), (0.1999, "BAD"), (0.0, "BAD"),
])
def test_exp_hbc_eqr_classes_are_five_steps_of_0_2(eqr, quality):
    assert eqs_class(eqr, EXP_HBC_EQR_RULES) == quality


def test_exp_hbc_eqr_is_normalised_on_the_column_maximum():
    from foramqs.indices.foramecoqs import foramecoqs_table

    abundance = pd.DataFrame({"S1": [10, 10, 10, 10], "S2": [37, 1, 1, 1]}, index=["Sp1", "Sp2", "Sp3", "Sp4"])
    groups = pd.Series(["ND"] * 4, index=abundance.index)
    rules = {"exp_hbc": [["Bad"]], "fsi": FSI_RULES, "foram_ambi": [["Bad"]], "exp_hbc_eqr": EXP_HBC_EQR_RULES}
    table = foramecoqs_table(abundance, groups, groups, rules)

    cols = table.columns.tolist()
    assert cols[cols.index("exp(H'bc)") + 1:cols.index("exp(H'bc)") + 3] == ["exp(H'bc) EQR", "EQS exp(H'bc) EQR"]
    assert table.loc["S1", "exp(H'bc) EQR"] == 1.0 and table.loc["S1", "EQS exp(H'bc) EQR"] == "HIGH"
    expected = cs_round(table.loc["S2", "exp(H'bc)"] / table.loc["S1", "exp(H'bc)"], 4)
    assert table.loc["S2", "exp(H'bc) EQR"] == expected
    assert table.loc["S2", "EQS exp(H'bc) EQR"] == eqs_class(expected, EXP_HBC_EQR_RULES)


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


FORAM_AMBI_RULES = [["High", "<=", 1.2], ["Good", "<=", 3.3], ["Moderate", "<=", 4.3], ["Poor", "<=", 5.5], ["Bad"]]
RULES = {"exp_hbc": [["Bad"]], "fsi": FSI_RULES, "exp_hbc_eqr": EXP_HBC_EQR_RULES, "foram_ambi": FORAM_AMBI_RULES}


def test_foram_ambi_ori_and_redistributed():
    from foramqs.indices.foramecoqs import foramecoqs_table

    # S1: Sp1 EG1 = 10, Sp2 EG3 = 10, Sp3 NA = 20
    #   ori: NA al denominatore, pesano come GI → (3·10) / 40 = 0.75
    #   ridistribuito: 50% GI, 50% GIII → (0·50 + 3·50) / 100 = 1.5
    # S2: solo NA → nessun gruppo su cui ridistribuire
    abundance = pd.DataFrame({"S1": [10, 10, 20], "S2": [0, 0, 7]}, index=["Sp1", "Sp2", "Sp3"])
    fsi_group = pd.Series(["ND"] * 3, index=abundance.index)
    eco_group = pd.Series(["1", "3", "NA"], index=abundance.index)

    table = foramecoqs_table(abundance, fsi_group, eco_group, RULES)
    assert table.loc["S1", "Foram-AMBI ori"] == 0.75
    assert table.loc["S1", "Foram-AMBI"] == 1.5
    assert table.loc["S1", "EQS Foram-AMBI"] == "Good"
    assert [table.loc["S1", f"% GE{g}"] for g in range(1, 6)] == [25.0, 0.0, 25.0, 0.0, 0.0]
    assert table.loc["S1", "% NA"] == 50.0
    assert math.isnan(table.loc["S2", "Foram-AMBI"])
    assert table.loc["S2", "EQS Foram-AMBI"] == "N/A"
    assert table.loc["S2", "% NA"] == 100.0


def test_sen_and_str_percentages_are_on_sen_plus_str():
    from foramqs.indices.foramecoqs import foramecoqs_table

    # Sen = 30, Str = 10, ND = 60: le percentuali ignorano gli ND, come la formula dell'FSI.
    abundance = pd.DataFrame({"S1": [30, 10, 60], "S2": [0, 0, 5]}, index=["Sp1", "Sp2", "Sp3"])
    fsi_group = pd.Series(["Sen", "Str", "ND"], index=abundance.index)
    eco_group = pd.Series(["1", "2", "NA"], index=abundance.index)

    table = foramecoqs_table(abundance, fsi_group, eco_group, RULES)
    assert table.loc["S1", "% Sen"] == 75.0 and table.loc["S1", "% Str"] == 25.0
    assert table.loc["S1", "FSI"] == fsi(30, 10)
    assert math.isnan(table.loc["S2", "% Sen"]) and math.isnan(table.loc["S2", "% Str"])


def test_foramecoqs_table_has_the_columns_of_the_result_sheets():
    from foramqs.indices.foramecoqs import EXP_HBC_COLUMNS, FORAM_AMBI_COLUMNS, FSI_COLUMNS, foramecoqs_table

    abundance = pd.DataFrame({"S1": [10, 20, 10]}, index=["Sp1", "Sp2", "Sp3"])
    groups = pd.Series(["Sen", "Str", "ND"], index=abundance.index)
    table = foramecoqs_table(abundance, groups, pd.Series(["1", "2", "3"], index=abundance.index), RULES)
    assert set(EXP_HBC_COLUMNS + FSI_COLUMNS + FORAM_AMBI_COLUMNS) <= set(table.columns)
    assert FORAM_AMBI_COLUMNS[-1] == "EQS Foram-AMBI"
    assert not any("Alt" in c or "Bouchet" in c for c in table.columns)
