import pandas as pd
import pytest

from foramqs.tables import above_threshold, density, genera_composition, relative

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


def test_genera_composition_adds_others():
    genera = genera_composition(REL, 0.05, "cella")
    assert genera.loc["Ammonia", "A"] == pytest.approx(0.06)
    assert genera.loc["Others", "A"] == pytest.approx(0.04)
    assert genera.sum().tolist() == pytest.approx([1.0, 1.0])


def test_density_is_mean_over_replicas():
    obs = pd.DataFrame({"campione": ["S1", "S1", "S1"], "replica": [1, 1, 2], "individui": [10, 5, 30]})
    per_replica, mean = density(obs, ["S1"], replica_volume_ml=150, per_ml=10)
    assert per_replica["densita"].tolist() == [1.0, 2.0]  # 15/15, 30/15
    assert mean["S1"] == 1.5
