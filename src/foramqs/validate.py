"""Controlli sugli input. Ogni controllo ha un codice stabile, una severità e indica dove si trova il problema.

Severità:
  - "errore": il dato è inutilizzabile o ambiguo; la pipeline non calcola nulla finché non è corretto;
  - "avviso": il dato è utilizzabile ma sospetto (possibile refuso o copia-incolla); va controllato;
  - "info": scelta di elaborazione da conoscere.
"""

from __future__ import annotations

import difflib
from dataclasses import asdict, dataclass
from itertools import combinations

import pandas as pd

from foramqs.clean import ND, SPP, CleanedRow
from foramqs.config import Config
from foramqs.io_excel import EXCEL_ROW, ExcelTable

ERROR, WARNING, INFO = "errore", "avviso", "info"


@dataclass(frozen=True)
class Issue:
    codice: str
    severita: str
    messaggio: str
    campione: str = ""
    riga_excel: int | None = None
    dettagli: str = ""


def issues_frame(issues: list[Issue]) -> pd.DataFrame:
    order = {ERROR: 0, WARNING: 1, INFO: 2}
    frame = pd.DataFrame([asdict(i) for i in issues], columns=list(Issue.__dataclass_fields__))
    return frame.sort_values(["severita", "codice", "campione", "riga_excel"], key=lambda c: c.map(order) if c.name == "severita" else c).reset_index(drop=True)


# --- Tabelle dei campioni ------------------------------------------------------------------------------------------

def check_sample_tables(samples: dict[str, ExcelTable]) -> list[Issue]:
    """V01: deve esistere almeno una tabella campione. V26: tabelle campione ancora senza righe compilate."""
    if not samples:
        return [Issue("V01", ERROR, "Nessuna tabella con le colonne di un campione trovata nel workbook dei dati")]
    return [
        Issue("V26", ERROR, f"La Tabella del campione è vuota: compilare le conte nel foglio '{t.sheet}'", name)
        for name, t in samples.items()
        if t.data.empty
    ]


def check_row_values(samples: dict[str, ExcelTable], cfg: Config) -> list[Issue]:
    """V02-V05: posizione (replica/slide/casella), conteggi, deformati e tipo di guscio di ogni riga con una specie.

    V13: riga senza specie ma con individui o deformati: la pulizia la scarterebbe, perdendo il conteggio.
    """
    valid_shells = set(cfg.cleaning["valid_shell_types"])
    issues = []
    for sample, table in samples.items():
        for row in table.data.to_dict("records"):
            text = row["SPECIE (LONG FORMAT)"]
            where = dict(campione=sample, riga_excel=row[EXCEL_ROW])
            if text is None or not str(text).strip():
                filled = {c: row[c] for c in ("N°INDIVIDUI", "DEFORMATI") if not _is_zero_or_empty(row[c])}
                if filled:
                    issues.append(Issue("V13", ERROR, "Conteggio senza SPECIE: la riga verrebbe scartata", dettagli=repr(filled), **where))
                continue
            for col in ("REPLICA", "N°SLIDE", "CASELLA"):
                if not _is_positive_int(row[col]):
                    issues.append(Issue("V02", ERROR, f"{col} mancante o non intero positivo", dettagli=repr(row[col]), **where))
            count, deformed = row["N°INDIVIDUI"], row["DEFORMATI"]
            if count is not None and not _is_non_negative_int(count):
                issues.append(Issue("V03", ERROR, "N°INDIVIDUI non è un intero ≥ 0", dettagli=repr(count), **where))
            if deformed is not None and not _is_non_negative_int(deformed):
                issues.append(Issue("V04", ERROR, "DEFORMATI non è un intero ≥ 0", dettagli=repr(deformed), **where))
            elif _is_non_negative_int(deformed) and _is_non_negative_int(count) and float(deformed) > float(count):
                issues.append(Issue("V04", ERROR, "DEFORMATI maggiore di N°INDIVIDUI", dettagli=f"{deformed} > {count}", **where))
            shell = "" if row["TIPO GUSCIO"] is None else str(row["TIPO GUSCIO"]).strip().upper()
            if shell and shell not in valid_shells:
                issues.append(Issue("V05", ERROR, "TIPO GUSCIO non ammesso", dettagli=repr(row["TIPO GUSCIO"]), **where))
    return issues


def check_missing_counts(observations: pd.DataFrame) -> list[Issue]:
    """I02: righe con una specie ma senza N°INDIVIDUI, una nota per campione.

    Per convenzione del laboratorio sono individui morti (o frammenti), registrati ma non conteggiati: valgono 0.
    La nota elenca le righe con il commento accanto, se c'è.
    """
    missing = observations.loc[observations["conteggio_mancante"].astype(bool)]
    return [
        Issue("I02", INFO, f"{len(group)} {'riga' if len(group) == 1 else 'righe'} senza N°INDIVIDUI (individui morti), non conteggiate", sample,
              dettagli="; ".join(f"riga {r}: {c}" if c else f"riga {r}" for r, c in zip(group["riga_excel"], group["commento"])))
        for sample, group in missing.groupby("campione")
    ]


def check_positions(observations: pd.DataFrame) -> list[Issue]:
    """V07-V08: caselle duplicate e numerazione delle repliche."""
    issues = []
    key = ["campione", "replica", "slide", "casella"]
    duplicated = observations[observations.duplicated(key, keep=False)]
    for (sample, rep, slide, cell), group in duplicated.groupby(key):
        issues.append(Issue(
            "V07", WARNING, f"Stessa casella usata più volte (replica {rep}, slide {slide}, casella {cell})", sample,
            int(group["riga_excel"].min()), "; ".join(f"riga {r}: {t}" for r, t in zip(group["riga_excel"], group["testo_originale"])),
        ))
    replicas = observations.groupby("campione")["replica"].agg(lambda s: sorted(set(s.dropna().astype(int))))
    if replicas.empty:
        return issues
    usual = replicas.map(len).mode().iloc[0]
    for sample, reps in replicas.items():
        if reps != list(range(1, len(reps) + 1)):
            issues.append(Issue("V08", WARNING, "Numerazione delle repliche non consecutiva da 1", sample, dettagli=str(reps)))
        elif len(reps) != usual:
            issues.append(Issue("V08", WARNING, f"Il campione ha {len(reps)} repliche (gli altri {usual})", sample, dettagli=str(reps)))
    return issues


def check_counted_individuals(samples: dict[str, ExcelTable], observations: pd.DataFrame) -> list[Issue]:
    """V29: campione con righe compilate ma nessun foraminifero conteggiato (conte vuote o a 0, solo righe scartate).

    Le abbondanze relative di un campione così non sono definite: va completato o tolto dal workbook.
    """
    totals = observations.groupby("campione")["individui"].sum()
    return [
        Issue("V29", ERROR, "Nessun foraminifero conteggiato nel campione: completare le conte o togliere il campione", name)
        for name, table in samples.items()
        if not table.data.empty and totals.get(name, 0) == 0
    ]


def check_copied_replicas(observations: pd.DataFrame, copies: dict[str, int]) -> list[Issue]:
    """V30 / I03: campioni di [input.copied_replicas]. La copia vale solo per campioni con la sola replica 1."""
    replicas = observations.groupby("campione")["replica"].agg(lambda s: sorted(set(s.dropna().astype(int))))
    issues = []
    for sample, n in copies.items():
        if sample not in replicas:
            issues.append(Issue("V30", ERROR, "Campione in [input.copied_replicas] senza osservazioni nei dati", sample))
        elif replicas[sample] != [1]:
            issues.append(Issue("V30", ERROR, "[input.copied_replicas] vale solo per campioni con la sola replica 1: "
                                f"togliere il campione dalla config", sample, dettagli=f"repliche: {replicas[sample]}"))
        else:
            issues.append(Issue("I03", INFO, f"Una sola replica registrata: R1 copiata come R2-R{n} ([input.copied_replicas])", sample))
    return issues


def check_parsed_names(cleaned_rows: list[CleanedRow]) -> list[Issue]:
    """V09-V10: nomi con struttura anomala e non determinati senza tipo di guscio."""
    messages = {
        "genere_anomalo": ("V09", "Il genere non è una parola con iniziale maiuscola"),
        "epiteto_anomalo": ("V09", "L'epiteto non è una parola minuscola"),
        "solo_genere_senza_qualificatore": ("V09", "Solo il genere, senza 'spp.': trattato come 'Genere spp.'"),
        "scartato:non_determinato_senza_guscio": ("V10", "Individuo non determinato senza TIPO GUSCIO: scartato, non conteggiato"),
    }
    return [
        Issue(code, WARNING, message, r.sample, r.excel_row, r.parsed.original)
        for r in cleaned_rows
        for rule in r.parsed.rules
        if rule in messages
        for code, message in [messages[rule]]
    ]


def check_shell_consistency(observations: pd.DataFrame) -> list[Issue]:
    """V11: lo stesso taxon registrato con tipi di guscio diversi (di solito una sola riga in minoranza = refuso).

    Usato per i taxa senza tratti; per gli altri il confronto è con la tabella dei tratti (R05).
    """
    issues = []
    data = observations[(observations["guscio"] != "") & (observations["qualificatore"] != ND)]
    for taxon, group in data.groupby("taxon"):
        counts = group["guscio"].value_counts()
        if len(counts) < 2:
            continue
        majority = counts.index[0]
        summary = ", ".join(f"{k}×{v}" for k, v in counts.items())
        for r in group[group["guscio"] != majority].itertuples():
            issues.append(Issue(
                "V11", WARNING, f"{taxon}: guscio '{r.guscio}' diverso da quello prevalente '{majority}' ({summary})",
                r.campione, r.riga_excel, r.testo_originale,
            ))
    return issues


def check_similar_names(observations: pd.DataFrame, threshold: float) -> list[Issue]:
    """V12: nomi molto simili tra loro (possibili refusi o varianti ortografiche dello stesso taxon)."""
    issues = []
    genera = sorted(set(observations["genere"]) - {""})
    for a, b in combinations(genera, 2):
        if difflib.SequenceMatcher(None, a, b).ratio() >= threshold:
            issues.append(Issue("V12", WARNING, f"Generi molto simili: '{a}' e '{b}'"))
    species = observations[observations["epiteto"] != ""].groupby("genere")["epiteto"].unique()
    for genus, epithets in species.items():
        for a, b in combinations(sorted(epithets), 2):
            if difflib.SequenceMatcher(None, a, b).ratio() >= threshold:
                issues.append(Issue("V12", WARNING, f"Specie molto simili: '{genus} {a}' e '{genus} {b}'"))
    return issues


def check_juveniles(cleaned_rows: list[CleanedRow]) -> list[Issue]:
    """I01: i giovanili sono confluiti in 'Genere spp.'."""
    merged = sorted({r.parsed.taxon for r in cleaned_rows if "giovanili_in_genere_spp" in r.parsed.rules})
    if not merged:
        return []
    return [Issue("I01", INFO, f"Giovanili sommati a '{SPP}' del genere", dettagli=", ".join(merged))]


def check_cluster_groups(groups: dict[str, list[str]], samples: set[str]) -> list[Issue]:
    """C01: gruppi di [cluster.groups] con campioni sconosciuti o ripetuti; campioni senza gruppo.

    Il confronto dei gruppi con il dendrogramma (C02) richiede il cluster ed è in multivariate.py.
    """
    issues = []
    assigned = [s for members in groups.values() for s in members]
    for sample in sorted(set(assigned) - samples):
        issues.append(Issue("C01", ERROR, f"Campione '{sample}' in [cluster.groups] ma non nei dati", sample))
    for sample in sorted({s for s in assigned if assigned.count(s) > 1}):
        issues.append(Issue("C01", ERROR, f"Campione '{sample}' assegnato a più gruppi in [cluster.groups]", sample))
    for sample in sorted(samples - set(assigned)):
        issues.append(Issue("C01", WARNING, f"Campione '{sample}' non assegnato ad alcun gruppo di cluster", sample))
    return issues


# --- Geochimica ----------------------------------------------------------------------------------------------------

def configured_geochemistry_columns(cfg: Config) -> dict[str, list[str]]:
    """Le colonne della geochimica nominate in config, raggruppate per voce di config che le usa."""
    t = cfg.raw["tables"]
    return {
        "input.grain_size_columns": cfg.input["grain_size_columns"],
        "tables.external_index_column": [t["external_index_column"]],
    }


def check_geochemistry_columns(values: pd.DataFrame, cfg: Config) -> list[Issue]:
    """V25: colonne nominate in config/pipeline.toml che non esistono nella tabella della geochimica."""
    return [
        Issue("V25", ERROR, f"Colonna '{column}' (config: {key}) assente dalla tabella della geochimica",
              dettagli=f"colonne presenti: {', '.join(values.columns)}")
        for key, columns in configured_geochemistry_columns(cfg).items()
        for column in columns
        if column not in values.columns
    ]


def check_geochemistry(geochemistry: ExcelTable, values: pd.DataFrame, sample_names: set[str], cfg: Config) -> list[Issue]:
    """V20-V24, V27-V28: campioni coerenti con le conte, valori mancanti, non numerici o censurati, granulometria,
    righe copiate, campioni ripetuti.

    `values` ha le stesse righe, nello stesso ordine, di `geochemistry.data`: il confronto è per posizione, così un
    campione ripetuto non rende ambiguo il valore da controllare.
    """
    issues = []
    geo_samples = set(values.index)
    for s in sorted(sample_names - geo_samples):
        issues.append(Issue("V20", ERROR, "Campione con conte ma senza geochimica", s))
    for s in sorted(geo_samples - sample_names):
        issues.append(Issue("V20", ERROR, "Campione in geochimica ma senza tabella di conte", s))
    for s in sorted(set(values.index[values.index.duplicated()])):
        issues.append(Issue("V28", ERROR, f"Campione presente in più righe della geochimica ({(values.index == s).sum()} righe)", s))

    censored = cfg.input.get("censored_values", {})
    for col in values.columns:
        for sample, raw_value, value in zip(values.index, geochemistry.data[col], values[col]):
            if raw_value is None:
                # Tutte le colonne entrano nelle tabelle per la CCA in PAST: nessun valore può mancare.
                issues.append(Issue("V27", ERROR, f"{col}: valore mancante (serve alle tabelle per la CCA)", sample))
            elif isinstance(raw_value, str) and raw_value.strip() in censored:
                issues.append(Issue("V21", WARNING, f"{col}: valore censurato '{raw_value}' sostituito con {censored[raw_value.strip()]}", sample))
            elif pd.isna(value):
                issues.append(Issue("V22", ERROR, f"{col}: valore non numerico", sample, dettagli=repr(raw_value)))

    grain = [c for c in cfg.input["grain_size_columns"] if c in values.columns]  # le mancanti sono già errori V25
    tolerance = cfg.input["grain_size_tolerance_pct"]
    complete = values[grain].dropna() if grain else values.iloc[0:0]  # i valori mancanti sono già segnalati da V27
    for sample, total in complete.sum(axis=1).items():
        if abs(total - 100) > tolerance:
            issues.append(Issue("V23", WARNING, f"Granulometria {' + '.join(grain)} = {total:.2f}% (atteso 100%)", sample))

    for (a, row_a), (b, row_b) in combinations(values.iterrows(), 2):
        same = [c for c in values.columns if row_a[c] == row_b[c] and row_a[c] != 0]
        if len(same) >= len(values.columns) / 2:
            issues.append(Issue("V24", WARNING, f"{a} e {b} hanno {len(same)} valori identici su {len(values.columns)}: possibile copia-incolla", a, dettagli=", ".join(same)))
    return issues


def _is_zero_or_empty(value: object) -> bool:
    return value is None or (_is_non_negative_int(value) and float(value) == 0)


def _is_positive_int(value: object) -> bool:
    return _is_non_negative_int(value) and float(value) > 0


def _is_non_negative_int(value: object) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return number >= 0 and number.is_integer()
