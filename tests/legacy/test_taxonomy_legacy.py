"""Le correzioni di nome fatte a mano il 2026-10-30 (Abbondanze_assolute → Raw_ForamsEcoQs) devono uscire dalle
regole di pulizia e da WoRMS, non da codice scritto per singole specie. Usa solo la cache WoRMS (offline)."""

import pandas as pd

from foramqs.clean import clean_taxon_name
from foramqs.config import load_config, read_config_csv
from foramqs.taxonomy import WormsClient, resolve_taxa

MANUAL_CORRECTIONS = {
    "Adelosina Juvenile": "Adelosina spp.",
    "Elphidium gerthivan": "Elphidium gerthi",
    "Gaudryina rudis": "Connemarella rudis",
    "Pseudotriloculina laevigata": "Pseudotriloculina lecalvezae",
    "Quinqueloculina agglutinata": "Siphonaperta agglutinata",
    "Quinqueloculina seminula": "Quinqueloculina seminulum",
    "Lachlanella variolata": "Quinqueloculina variolata",
    "Miliolinella grata": "Sigmoilina grata",
    "Miliolinella semicostata": "Miliolinella rhodiensis",
    "Quinqueloculina stelligera": "Quinqueloculina schlumbergeri",
    # Correzione manuale: Adelosina schreibersii. WoRMS: combinazione superata di Quinqueloculina pulchella.
    # Da decidere dai ricercatori (eventuale riga in config/taxon_aliases.csv).
    "Adelosina pulchella": "Quinqueloculina pulchella",
}


def test_manual_corrections_are_reproduced_by_rules_and_worms():
    cfg = load_config()
    corrections = read_config_csv(cfg.path("name_corrections"))
    cleaned = {name: clean_taxon_name(name, corrections, juveniles_into_genus_spp=True) for name in MANUAL_CORRECTIONS}
    resolved = resolve_taxa(
        sorted(set(cleaned.values())), pd.DataFrame(columns=["nome", "aphia_id"]),
        WormsClient(cfg.path("worms_cache"), offline=True), cfg.taxonomy["required_phylum"],
    ).set_index("taxon")["nome_valido"]
    assert {name: resolved[cleaned[name]] for name in MANUAL_CORRECTIONS} == MANUAL_CORRECTIONS
