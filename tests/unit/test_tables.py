import pandas as pd
import pytest

from foramqs.tables import above_threshold, density, log10_1px, log10_1px_formulas, relative

REL = relative(pd.DataFrame(
    {"A": [6, 4, 90], "B": [4, 6, 90]}, index=["Ammonia tepida", "Ammonia beccarii", "Bulimina elongata"],
))


def test_threshold_by_cell_zeroes_values_below_threshold():
    kept = above_threshold(REL, 0.05, "cella")
    assert kept.loc["Ammonia tepida", "A"] == 0.06
    assert kept.loc["Ammonia tepida", "B"] == 0  # 4% < 5% in questo campione


def test_threshold_by_species_keeps_all_values_of_dominant_species():
    kept = above_threshold(REL, 0.05, "specie")
    assert kept.loc["Ammonia tepida", "B"] == 0.04


def test_unknown_threshold_mode_is_an_error():
    with pytest.raises(ValueError):
        above_threshold(REL, 0.05, "altro")


def test_density_is_mean_over_replicas():
    obs = pd.DataFrame({"campione": ["S1", "S1", "S1"], "replica": [1, 1, 2], "individui": [10, 5, 30]})
    per_replica, mean = density(obs, ["S1"], replica_volume_ml=150, per_ml=10)
    assert per_replica["densita"].tolist() == [1.0, 2.0]  # 15/15, 30/15
    assert mean["S1"] == 1.5


def test_log10_1px_is_log10_of_one_plus_x():
    table = log10_1px(pd.DataFrame({"S1": [0, 9, 99]}))
    assert table["S1"].tolist() == pytest.approx([0.0, 1.0, 2.0])


def test_log10_1px_formulas_point_to_the_transposed_cell():
    source = pd.DataFrame({"S1": [1.0, 2.0], "S2": [3.0, 4.0]}, index=["Sp a", "Sp b"])
    formulas = log10_1px_formulas("Abb_rel_5%", source)
    assert list(formulas.index) == ["S1", "S2"] and list(formulas.columns) == ["Sp a", "Sp b"]
    assert formulas.loc["S2", "Sp a"] == "=LOG10(1+'Abb_rel_5%'!C2)"  # campione S2 = colonna C, Sp a = riga 2
    assert formulas.loc["S1", "Sp b"] == "=LOG10(1+'Abb_rel_5%'!B3)"
