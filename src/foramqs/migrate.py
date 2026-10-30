"""Creazione una tantum di reference/species_traits.csv dalle fonti storiche.

Fonti: la tabella `specie_stilevita` del workbook dei dati e le liste preparate per ForamEcoQS
(Lista_Foram_AMBI.csv, Lista_FSI.csv). I nomi di tutte le fonti vengono puliti e risolti in WoRMS; le voci che
finiscono sullo stesso taxon vengono fuse. Se due voci danno valori diversi per lo stesso tratto, il campo viene
scritto come "CONFLITTO: ..." con l'elenco delle alternative: la pipeline si ferma finché un ricercatore non
sceglie il valore corretto modificando il CSV.
"""

from __future__ import annotations

import pandas as pd

from foramqs.clean import clean_taxon_name
from foramqs.config import Config, read_config_csv
from foramqs.io_excel import read_tables
from foramqs.taxonomy import WormsClient, resolve_taxa
from foramqs.traits import CONFLICT_MARK, FILE_COLUMNS, TRAIT_COLUMNS

_FSI_CODES = {"S": "Sen", "T": "Str", "ND": "ND"}


def historical_trait_records(cfg: Config) -> pd.DataFrame:
    """Tutte le attribuzioni storiche in formato long: fonte, nome originale, tratto, valore."""
    m = cfg.migration
    table = read_tables(cfg.path("data_workbook"))[m["traits_table"]].data
    columns = {
        "STILE DI VITA": "stile_di_vita", "GRUPPI ECOLOGICI": "gruppo_ecologico",
        "Ecological group FSI": "gruppo_fsi", "TIPO GUSCIO": "guscio",
    }
    records = [
        (m["traits_table"], row["SPECIE"], trait, _text(row[column]))
        for row in table.to_dict("records")
        for column, trait in columns.items()
    ]
    ambi = read_config_csv(cfg.resolve(m["foram_ambi_list"]))
    records += [("Lista_Foram_AMBI.csv", r.Species, "gruppo_ecologico", _text(r.Ecogroup)) for r in ambi.itertuples()]
    fsi = read_config_csv(cfg.resolve(m["fsi_list"]))
    records += [("Lista_FSI.csv", r.Species, "gruppo_fsi", _FSI_CODES.get(r.Classification, r.Classification)) for r in fsi.itertuples()]
    return pd.DataFrame(records, columns=["fonte", "nome_originale", "tratto", "valore"])


def migrate_traits(cfg: Config, client: WormsClient) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Restituisce (tabella dei tratti, elenco dei conflitti, risoluzione dei nomi)."""
    records = historical_trait_records(cfg)
    corrections = read_config_csv(cfg.path("name_corrections"))
    juveniles = cfg.cleaning["juveniles_into_genus_spp"]
    records["taxon"] = records["nome_originale"].map(lambda n: clean_taxon_name(n, corrections, juveniles))
    resolutions = resolve_taxa(
        sorted(records["taxon"].unique()), read_config_csv(cfg.path("taxon_aliases")), client,
        cfg.taxonomy["required_phylum"],
    )
    records = records.merge(resolutions[["taxon", "taxon_id", "nome_valido"]], on="taxon")

    rows, conflicts = [], []
    for taxon_id, group in records.groupby("taxon_id", sort=False):
        row = {"nome": group["nome_valido"].iloc[0]}
        for trait in TRAIT_COLUMNS:
            options = group[(group["tratto"] == trait) & (group["valore"] != "")]
            values = options.groupby("valore")["nome_originale"].unique()
            if len(values) <= 1:
                row[trait] = values.index[0] if len(values) else ""
                continue
            alternatives = [f"{value} ({', '.join(names)})" for value, names in values.items()]
            row[trait] = f"{CONFLICT_MARK}: " + " | ".join(alternatives)
            conflicts.append({"nome": row["nome"], "tratto": trait, "alternative": " | ".join(alternatives)})
        originals = sorted(set(group["nome_originale"]) - {row["nome"]})
        row["fonte"] = "migrazione da " + ", ".join(sorted(group["fonte"].unique()))
        row["note"] = f"nomi originali: {'; '.join(originals)}" if originals else ""
        rows.append(row)

    traits = pd.DataFrame(rows, columns=FILE_COLUMNS).sort_values("nome").reset_index(drop=True)
    return traits, pd.DataFrame(conflicts, columns=["nome", "tratto", "alternative"]), resolutions


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()
