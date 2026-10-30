import pandas as pd
import pytest

from foramqs.clean import normalize_text, parse_name

CORRECTIONS = pd.DataFrame(
    [("Sigmoilinita", "Sigmoilina"), ("Elphidium gerthivan", "Elphidium gerthi van")],
    columns=["trova", "sostituisci"],
)
NON_FORAM = {"diatomee", "no forams"}
ND_LABELS = {"not determined", "specie anomala"}


def parse(text, shell="P", juveniles_into_genus_spp=True):
    return parse_name(text, shell, CORRECTIONS, NON_FORAM, ND_LABELS, juveniles_into_genus_spp)


def test_normalize_special_characters():
    text, rules = normalize_text("Bulimina aculeata d’Orbigny, 1826 †\x07  ")
    assert text == "Bulimina aculeata d'Orbigny, 1826"
    assert set(rules) == {"caratteri_di_controllo", "spazio_speciale", "simbolo_†", "apostrofo_tipografico"}


def test_trailing_spaces_are_not_logged_as_a_rule():
    assert normalize_text("Ammonia sp. ") == ("Ammonia sp.", [])


@pytest.mark.parametrize("text, taxon, author", [
    ("Quinqueloculina bradyanaCushman, 1917", "Quinqueloculina bradyana", "Cushman, 1917"),
    ("Peneroplis planatus(Fichtel & Moll, 1798)", "Peneroplis planatus", "(Fichtel & Moll, 1798)"),
    ("Spiroloculina cymbiumd'Orbigny, 1839", "Spiroloculina cymbium", "d'Orbigny, 1839"),
    ("Ammonia tepida (Cushman, 1926)", "Ammonia tepida", "(Cushman, 1926)"),
])
def test_author_is_separated_from_epithet(text, taxon, author):
    p = parse(text)
    assert (p.taxon, p.author) == (taxon, author)


@pytest.mark.parametrize("text", ["Ammonia sp.", "Ammonia sp,", "Ammonia spp.", "Ammonia sp"])
def test_sp_variants_become_spp(text):
    assert parse(text).taxon == "Ammonia spp."


@pytest.mark.parametrize("text", ["Adelosina Juvenile", "Adelosina giovanili", "Adelosina spp. Juvenile", "Adelosina Jouvenile"])
def test_juveniles_merge_into_genus_spp(text):
    p = parse(text)
    assert p.taxon == "Adelosina spp."
    assert "giovanili_in_genere_spp" in p.rules


def test_juveniles_can_be_kept_separate():
    assert parse("Adelosina giovanili", juveniles_into_genus_spp=False).taxon == "Adelosina Juvenile"


def test_not_determined_uses_shell_type_and_is_discarded_without_it():
    assert parse("Not determined", shell="A").taxon == "ND A"
    without_shell = parse("Specie anomala ", shell="")
    assert without_shell.discarded and "scartato:non_determinato_senza_guscio" in without_shell.rules


def test_non_foram_and_empty_rows_are_discarded():
    assert parse("Diatomee  ").discarded
    assert parse("No Forams").discarded
    assert parse("   ").discarded


def test_corrections_are_applied_and_logged():
    p = parse("Sigmoilinita costata Schlumberger, 1893")
    assert p.taxon == "Sigmoilina costata"
    assert "correzione:Sigmoilinita→Sigmoilina" in p.rules
    assert parse("Elphidium gerthivan Voorthuysen, 1957").taxon == "Elphidium gerthi"


def test_genus_alone_is_flagged():
    p = parse("Reophax")
    assert p.taxon == "Reophax spp."
    assert "solo_genere_senza_qualificatore" in p.rules
