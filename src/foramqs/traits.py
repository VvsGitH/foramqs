"""Tabella unica dei tratti delle specie (reference/species_traits.csv) e suoi controlli.

Ogni riga descrive un taxon con il suo nome (anche un sinonimo: viene risolto come i nomi dei campioni) e i tratti
non derivabili dai dati: stile di vita, gruppo ecologico Foram-AMBI (1-5 o NA), gruppo FSI (Sen/Str/ND) e tipo di
guscio (A/I/P). Le colonne `fonte` e `note` documentano da dove viene ogni attribuzione.
"""

from __future__ import annotations

import pandas as pd

from foramqs.validate import ERROR, INFO, WARNING, Issue

TRAIT_COLUMNS = ["stile_di_vita", "gruppo_ecologico", "gruppo_fsi", "guscio"]
FILE_COLUMNS = ["nome", *TRAIT_COLUMNS, "fonte", "note"]
CONFLICT_MARK = "CONFLITTO"


def attach_taxon_ids(traits: pd.DataFrame, name_to_taxon: dict[str, str], resolutions: pd.DataFrame) -> pd.DataFrame:
    """Aggiunge a ogni riga dei tratti il nome pulito (`taxon`), il `taxon_id` e il `nome_valido`."""
    ids = resolutions.set_index("taxon")[["taxon_id", "nome_valido"]]
    resolved = traits.assign(taxon=traits["nome"].map(name_to_taxon))
    return resolved.join(ids, on="taxon")


def check_traits(traits: pd.DataFrame, allowed: dict[str, list[str]]) -> list[Issue]:
    """R01-R03: valori non ammessi (compresi i conflitti lasciati dalla migrazione) e righe dello stesso taxon."""
    issues = []
    for i, row in traits.iterrows():
        csv_line = i + 2  # riga 1 = intestazione
        for column, values in allowed.items():
            if row[column] not in values:
                severity_text = "conflitto da risolvere" if row[column].startswith(CONFLICT_MARK) else "valore non ammesso"
                issues.append(Issue(
                    "R01", ERROR, f"species_traits.csv riga {csv_line}, {row['nome']}: {column} — {severity_text}",
                    dettagli=f"{row[column]!r}; ammessi: {', '.join(values)}",
                ))
    for taxon_id, group in traits.groupby("taxon_id"):
        if len(group) < 2:
            continue
        names = ", ".join(f"{n} (riga {i + 2})" for i, n in group["nome"].items())
        if len(group[TRAIT_COLUMNS].drop_duplicates()) > 1:
            issues.append(Issue("R02", ERROR, f"Righe dello stesso taxon con tratti diversi: {group['nome_valido'].iloc[0]}", dettagli=names))
        else:
            issues.append(Issue("R03", INFO, f"Righe duplicate dello stesso taxon: {group['nome_valido'].iloc[0]}", dettagli=names))
    return issues


def traits_by_taxon(traits: pd.DataFrame) -> pd.DataFrame:
    """Un'unica riga di tratti per `taxon_id` (le righe duplicate sono già state segnalate da check_traits)."""
    return traits.drop_duplicates("taxon_id").set_index("taxon_id")[["nome_valido", *TRAIT_COLUMNS]]


def check_coverage(observations: pd.DataFrame, traits: pd.DataFrame) -> list[Issue]:
    """R04: taxa presenti nei campioni ma assenti dalla tabella dei tratti (trattati come non assegnati)."""
    missing = observations[~observations["taxon_id"].isin(traits.index)]
    return [
        Issue("R04", WARNING, f"'{name}' non ha tratti in species_traits.csv: escluso da FSI e Foram-AMBI",
              dettagli=f"{group['individui'].sum()} individui in {group['campione'].nunique()} campioni")
        for name, group in missing.groupby("nome_valido")
    ]


def check_shell_against_traits(observations: pd.DataFrame, traits: pd.DataFrame) -> list[Issue]:
    """R05: tipo di guscio registrato nei campioni diverso da quello della tabella dei tratti."""
    data = observations[observations["guscio"] != ""].join(traits["guscio"].rename("guscio_tratti"), on="taxon_id")
    data = data[data["guscio_tratti"].notna() & (data["guscio"] != data["guscio_tratti"])]
    return [
        Issue("R05", WARNING, f"{r.nome_valido}: guscio '{r.guscio}' nel campione, '{r.guscio_tratti}' nella tabella dei tratti",
              r.campione, r.riga_excel, r.testo_originale)
        for r in data.itertuples()
    ]
