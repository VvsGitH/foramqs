import pandas as pd

from foramqs.traits import check_shell_against_traits


def test_shell_mismatches_are_one_info_per_taxon():
    observations = pd.DataFrame({
        "taxon_id": ["1", "1", "1", "2"],
        "nome_valido": ["Genus alfa", "Genus alfa", "Genus alfa", "Genus beta"],
        "guscio": ["P", "I", "I", "A"],
        "campione": ["MC_A01", "MC_A01", "MC_B01", "MC_A01"],
        "riga_excel": [2, 3, 4, 5],
    })
    traits = pd.DataFrame({"guscio": ["P", "A"]}, index=pd.Index(["1", "2"], name="taxon_id"))
    issues = check_shell_against_traits(observations, traits)
    assert [(i.codice, i.severita) for i in issues] == [("R05", "info")]
    assert "2 righe con guscio I×2" in issues[0].messaggio and issues[0].dettagli == "MC_A01 riga 3; MC_B01 riga 4"
