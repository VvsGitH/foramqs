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
    """V01: deve esistere almeno una tabella campione."""
    if not samples:
        return [Issue("V01", ERROR, "Nessuna tabella con le colonne di un campione trovata nel workbook dei dati")]
    return []


def check_row_values(samples: dict[str, ExcelTable], cfg: Config) -> list[Issue]:
    """V02-V05: posizione (replica/slide/casella), conteggi, deformati e tipo di guscio di ogni riga con una specie."""
    valid_shells = set(cfg.cleaning["valid_shell_types"])
    issues = []
    for sample, table in samples.items():
        for row in table.data.to_dict("records"):
            text = row["SPECIE (LONG FORMAT)"]
            if text is None or not str(text).strip():
                continue
            where = dict(campione=sample, riga_excel=row[EXCEL_ROW])
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


def check_missing_counts(observations: pd.DataFrame, dead_comment_text: str) -> list[Issue]:
    """V06 / I02: riga con una specie ma senza N°INDIVIDUI.

    Se il commento accanto alla riga indica un individuo morto è una scelta di registrazione (I02, info);
    altrimenti è un possibile conteggio dimenticato (V06, avviso). In entrambi i casi la riga vale 0.
    """
    missing = observations[observations["conteggio_mancante"]]
    is_dead = missing["commento"].str.casefold().str.contains(dead_comment_text, regex=False)
    issues = [
        Issue("V06", WARNING, "Specie senza N°INDIVIDUI e senza commento che lo spieghi: conteggiata come 0",
              r.campione, r.riga_excel, r.testo_originale)
        for r in missing[~is_dead].itertuples()
    ]
    for sample, group in missing[is_dead].groupby("campione"):
        issues.append(Issue(
            "I02", INFO, f"{len(group)} righe di individui morti (commento '{dead_comment_text}…'), non conteggiate", sample,
            dettagli=", ".join(f"riga {r}" for r in group["riga_excel"]),
        ))
    return issues


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
    usual = replicas.map(len).mode().iloc[0]
    for sample, reps in replicas.items():
        if reps != list(range(1, len(reps) + 1)):
            issues.append(Issue("V08", WARNING, "Numerazione delle repliche non consecutiva da 1", sample, dettagli=str(reps)))
        elif len(reps) != usual:
            issues.append(Issue("V08", WARNING, f"Il campione ha {len(reps)} repliche (gli altri {usual})", sample, dettagli=str(reps)))
    return issues


def check_parsed_names(cleaned_rows: list[CleanedRow]) -> list[Issue]:
    """V09-V10: nomi con struttura anomala e non determinati senza tipo di guscio."""
    messages = {
        "genere_anomalo": ("V09", "Il genere non è una parola con iniziale maiuscola"),
        "epiteto_anomalo": ("V09", "L'epiteto non è una parola minuscola"),
        "solo_genere_senza_qualificatore": ("V09", "Solo il genere, senza 'spp.': trattato come 'Genere spp.'"),
        "non_determinato_senza_guscio": ("V10", "Individuo non determinato senza TIPO GUSCIO: conteggiato come 'ND'"),
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


# --- Geochimica ----------------------------------------------------------------------------------------------------

def check_geochemistry(geochemistry: ExcelTable, values: pd.DataFrame, sample_names: set[str], cfg: Config) -> list[Issue]:
    """V20-V24: campioni coerenti con le conte, valori numerici, valori censurati, granulometria, righe copiate."""
    issues = []
    geo_samples = set(values.index)
    for s in sorted(sample_names - geo_samples):
        issues.append(Issue("V20", ERROR, "Campione con conte ma senza geochimica", s))
    for s in sorted(geo_samples - sample_names):
        issues.append(Issue("V20", ERROR, "Campione in geochimica ma senza tabella di conte", s))

    raw = geochemistry.data.set_index(cfg.input["geochemistry_sample_column"])
    censored = cfg.input.get("censored_values", {})
    for col in values.columns:
        for sample, raw_value in raw[col].items():
            if isinstance(raw_value, str) and raw_value.strip() in censored:
                issues.append(Issue("V21", WARNING, f"{col}: valore censurato '{raw_value}' sostituito con {censored[raw_value.strip()]}", str(sample)))
            elif pd.isna(values.at[str(sample).strip(), col]) and raw_value is not None:
                issues.append(Issue("V22", ERROR, f"{col}: valore non numerico", str(sample), dettagli=repr(raw_value)))

    grain = cfg.input["grain_size_columns"]
    tolerance = cfg.input["grain_size_tolerance_pct"]
    for sample, total in values[grain].sum(axis=1).items():
        if abs(total - 100) > tolerance:
            issues.append(Issue("V23", WARNING, f"Granulometria {' + '.join(grain)} = {total:.2f}% (atteso 100%)", sample))

    for a, b in combinations(values.index, 2):
        same = [c for c in values.columns if values.at[a, c] == values.at[b, c] and values.at[a, c] != 0]
        if len(same) >= len(values.columns) / 2:
            issues.append(Issue("V24", WARNING, f"{a} e {b} hanno {len(same)} valori identici su {len(values.columns)}: possibile copia-incolla", a, dettagli=", ".join(same)))
    return issues


def _is_positive_int(value: object) -> bool:
    return _is_non_negative_int(value) and float(value) > 0


def _is_non_negative_int(value: object) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return number >= 0 and number.is_integer()
