"""Pulizia dei nomi di specie e costruzione della tabella delle osservazioni.

Ogni funzione restituisce, oltre al risultato, l'elenco delle regole applicate: così il foglio `Log_pulizia`
mostra per ogni testo originale che cosa è stato cambiato e perché.

Regole (nell'ordine in cui sono applicate):
  1. normalizzazione del testo: caratteri di controllo, spazi speciali (NBSP), simbolo †, apostrofi tipografici,
     spazi multipli;
  2. correzioni testuali da config/name_corrections.csv (refusi);
  3. scarto delle righe vuote e dei termini in config/non_foram_terms.csv;
  4. individui non determinati ("Not determined", "Specie anomala") → "ND <tipo guscio>"; senza tipo di guscio
     vengono scartati (decisione dei ricercatori, come nel vecchio flusso Power Query);
  5. separazione di genere, epiteto, autore e qualificatore: l'autore attaccato all'epiteto viene staccato,
     "sp."/"spp." diventano "spp.", i giovanili confluiscono in "Genere spp." (se previsto dalla config).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import pandas as pd

from foramqs.io_excel import EXCEL_ROW, ExcelTable

SPP = "spp."
ND = "ND"
_SP_TOKENS = {"sp", "sp.", "sp,", "spp", "spp.", "spp,"}
_JUVENILE_TOKENS = {"juvenile", "juveniles", "giovanile", "giovanili", "jouvenile", "jouveniles"}
# Epiteto seguito senza spazio dall'autore: "bradyanaCushman", "planatus(Fichtel", "cymbiumd'Orbigny".
_ATTACHED_AUTHOR = re.compile(r"^([a-z][a-z-]*?)(d'[A-Z].*|[A-Z(].*)$")
_EPITHET = re.compile(r"^[a-z][a-z-]*$")
_GENUS = re.compile(r"^[A-Z][a-z]+$")


@dataclass(frozen=True)
class ParsedName:
    """Esito della pulizia di un testo "SPECIE (LONG FORMAT)". `taxon` vuoto = riga scartata."""

    original: str
    normalized: str
    taxon: str = ""
    genus: str = ""
    epithet: str = ""
    qualifier: str = ""  # "" (specie), "spp." (solo genere) o "ND" (non determinato)
    author: str = ""
    rules: tuple[str, ...] = field(default_factory=tuple)

    @property
    def discarded(self) -> bool:
        return not self.taxon


def normalize_text(text: str) -> tuple[str, list[str]]:
    """Normalizza caratteri e spazi; restituisce il testo e le regole che lo hanno modificato."""
    rules = []
    steps = [
        ("caratteri_di_controllo", lambda s: "".join(c for c in s if unicodedata.category(c) != "Cc")),
        ("spazio_speciale", lambda s: "".join(" " if unicodedata.category(c) == "Zs" else c for c in s)),
        ("simbolo_†", lambda s: s.replace("†", "")),
        ("apostrofo_tipografico", lambda s: s.replace("’", "'").replace("‘", "'").replace("`", "'")),
        ("spazi_multipli", lambda s: re.sub(r"\s+", " ", s).strip()),
    ]
    for rule, step in steps:
        new = step(text)
        if new != text and not (rule == "spazi_multipli" and new == text.strip()):
            rules.append(rule)
        text = new
    return text, rules


def apply_corrections(text: str, corrections: pd.DataFrame) -> tuple[str, list[str]]:
    """Sostituzioni testuali da name_corrections.csv (colonne trova/sostituisci), applicate in ordine."""
    rules = []
    for row in corrections.itertuples(index=False):
        if row.trova in text:
            text = text.replace(row.trova, row.sostituisci)
            rules.append(f"correzione:{row.trova}→{row.sostituisci}")
    return text, rules


def parse_name(
    original: object,
    shell_type: str,
    corrections: pd.DataFrame,
    non_foram_terms: set[str],
    not_determined_labels: set[str],
    juveniles_into_genus_spp: bool,
) -> ParsedName:
    """Pulisce un singolo testo di specie. `non_foram_terms` e `not_determined_labels` sono in minuscolo."""
    original = "" if original is None else str(original)
    text, rules = normalize_text(original)
    text, correction_rules = apply_corrections(text, corrections)
    rules += correction_rules

    if not text:
        return ParsedName(original, text, rules=(*rules, "scartato:riga_vuota"))
    if text.casefold() in non_foram_terms:
        return ParsedName(original, text, rules=(*rules, "scartato:non_foraminifero"))
    if text.casefold() in not_determined_labels:
        if not shell_type:
            return ParsedName(original, text, rules=(*rules, "scartato:non_determinato_senza_guscio"))
        return ParsedName(original, text, taxon=f"{ND} {shell_type}", qualifier=ND, rules=(*rules, "non_determinato"))

    genus, *rest = text.split(" ")
    if not _GENUS.match(genus):
        rules.append("genere_anomalo")
    if not rest:
        rules.append("solo_genere_senza_qualificatore")
        return ParsedName(original, text, f"{genus} {SPP}", genus, qualifier=SPP, rules=tuple(rules))

    second = rest[0]
    attached = _ATTACHED_AUTHOR.match(second)
    if attached:
        second = attached.group(1)
        rest = [second, attached.group(2), *rest[1:]]
        rules.append("autore_attaccato_all_epiteto")

    if second.casefold() in _SP_TOKENS or second.casefold() in _JUVENILE_TOKENS:
        is_juvenile = second.casefold() in _JUVENILE_TOKENS or any(t.casefold() in _JUVENILE_TOKENS for t in rest[1:])
        if is_juvenile and not juveniles_into_genus_spp:
            rules.append("giovanili")
            return ParsedName(original, text, f"{genus} Juvenile", genus, qualifier="Juvenile", rules=tuple(rules))
        if is_juvenile:
            rules.append("giovanili_in_genere_spp")
        elif second != SPP:
            rules.append("sp_in_spp")
        return ParsedName(original, text, f"{genus} {SPP}", genus, qualifier=SPP, rules=tuple(rules))

    if not _EPITHET.match(second):
        rules.append("epiteto_anomalo")
    author = " ".join(rest[1:]).strip()
    return ParsedName(original, text, f"{genus} {second}", genus, second, author=author, rules=tuple(rules))


def clean_taxon_name(text: str, corrections: pd.DataFrame, juveniles_into_genus_spp: bool) -> str:
    """Nome pulito di una voce di una lista di riferimento (es. tabella dei tratti), con le stesse regole dei campioni.

    I non determinati ("ND A") sono già nella forma finale e restano invariati.
    """
    normalized, _ = normalize_text(text)
    if normalized == ND or normalized.startswith(f"{ND} "):
        return normalized
    return parse_name(text, "", corrections, set(), set(), juveniles_into_genus_spp).taxon


def normalize_shell_type(value: object) -> str:
    return "" if value is None else str(value).strip().upper()


OBSERVATION_COLUMNS = [
    "campione", "riga_excel", "replica", "slide", "casella", "testo_originale", "taxon", "genere", "epiteto",
    "qualificatore", "autore", "guscio", "individui", "deformati", "conteggio_mancante", "commento",
]


@dataclass(frozen=True)
class CleanedRow:
    """Esito della pulizia di una riga grezza (anche se scartata), con la sua posizione nel workbook."""

    sample: str
    excel_row: int
    parsed: ParsedName
    individuals: int


def build_observations(
    samples: dict[str, ExcelTable],
    corrections: pd.DataFrame,
    non_foram_terms: set[str],
    not_determined_labels: set[str],
    juveniles_into_genus_spp: bool,
    comment_column: str,
) -> tuple[pd.DataFrame, list[CleanedRow]]:
    """Tabella long delle osservazioni (una riga per casella) e l'esito della pulizia di ogni riga grezza.

    Le righe scartate (vuote, non foraminiferi) non entrano nelle osservazioni ma restano negli esiti, per il log.
    Conte mancanti valgono 0 e sono marcate in `conteggio_mancante` (la validazione le segnala).
    """
    records, cleaned_rows = [], []
    for sample, table in samples.items():
        for row in table.data.to_dict("records"):
            shell = normalize_shell_type(row["TIPO GUSCIO"])
            parsed = parse_name(
                row["SPECIE (LONG FORMAT)"], shell, corrections, non_foram_terms, not_determined_labels,
                juveniles_into_genus_spp,
            )
            individuals = _to_int(row["N°INDIVIDUI"])
            cleaned_rows.append(CleanedRow(sample, row[EXCEL_ROW], parsed, individuals or 0))
            if parsed.discarded:
                continue
            comment = row.get(comment_column)
            records.append({
                "campione": sample,
                "riga_excel": row[EXCEL_ROW],
                "replica": _to_int(row["REPLICA"]),
                "slide": _to_int(row["N°SLIDE"]),
                "casella": _to_int(row["CASELLA"]),
                "testo_originale": parsed.original,
                "taxon": parsed.taxon,
                "genere": parsed.genus,
                "epiteto": parsed.epithet,
                "qualificatore": parsed.qualifier,
                "autore": parsed.author,
                "guscio": shell,
                "individui": individuals or 0,
                "deformati": _to_int(row["DEFORMATI"], default=0),
                "conteggio_mancante": individuals is None,
                "commento": "" if comment is None else str(comment).strip(),
            })
    return pd.DataFrame(records, columns=OBSERVATION_COLUMNS), cleaned_rows


def copy_single_replica(observations: pd.DataFrame, copies: dict[str, int]) -> pd.DataFrame:
    """Per i campioni in `copies` che hanno solo la replica 1, aggiunge le repliche 2..N identiche alla prima.

    Le righe aggiunte hanno `replica_copiata` = True e la stessa `riga_excel` dell'originale. I campioni con più di
    una replica non vengono toccati (la validazione li segnala con V30).
    """
    observations = observations.assign(replica_copiata=False)
    replicas = observations.groupby("campione")["replica"].agg(lambda s: set(s.dropna()))
    added = [
        observations[observations["campione"] == sample].assign(replica=k, replica_copiata=True)
        for sample, n in copies.items()
        if replicas.get(sample) == {1}
        for k in range(2, n + 1)
    ]
    return pd.concat([observations, *added], ignore_index=True)


def cleaning_log(cleaned_rows: list[CleanedRow]) -> pd.DataFrame:
    """Una riga per testo originale distinto: in che cosa è stato trasformato, con quali regole, dove compare."""
    rows = {}
    for r in cleaned_rows:
        p = r.parsed
        entry = rows.setdefault(p.original, {
            "testo_originale": p.original,
            "testo_normalizzato": p.normalized,
            "taxon": p.taxon,
            "regole": ", ".join(p.rules),
            "n_righe": 0,
            "individui": 0,
            "campioni": set(),
        })
        entry["n_righe"] += 1
        entry["individui"] += r.individuals
        entry["campioni"].add(r.sample)
    for entry in rows.values():
        entry["campioni"] = ", ".join(sorted(entry["campioni"]))
    columns = ["testo_originale", "testo_normalizzato", "taxon", "regole", "n_righe", "individui", "campioni"]
    log = pd.DataFrame(list(rows.values()), columns=columns)
    return log.sort_values(["taxon", "testo_originale"]).reset_index(drop=True)


def _to_int(value: object, default: int | None = None) -> int | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return int(number) if number.is_integer() else default
