"""Risoluzione tassonomica dei nomi puliti tramite WoRMS (World Register of Marine Species).

Ogni nome pulito ("Genere epiteto", "Genere spp." o "ND <guscio>") riceve un `taxon_id`, la chiave usata in tutte
le elaborazioni successive, e un `nome_valido` mostrato in output. Due nomi che WoRMS considera lo stesso taxon
(sinonimi, grafie alternative, vecchie combinazioni) ricevono lo stesso `taxon_id` e vengono quindi sommati.

Ordine di risoluzione:
  1. config/taxon_aliases.csv: AphiaID imposto dai ricercatori (ha sempre la precedenza);
  2. WoRMS, solo corrispondenze esatte nel phylum richiesto: si usa il taxon accettato (`valid_AphiaID`);
  3. altrimenti il nome resta non risolto: non viene unito ad altri e viene segnalato (con l'eventuale
     suggerimento approssimato di WoRMS, da approvare aggiungendo una riga agli alias).

Formato di `taxon_id`: AphiaID per le specie ("112675"), AphiaID del genere + " spp." per i determinati solo al
genere ("112021 spp."), il nome stesso per i non determinati ("ND A") e "? <nome>" per i nomi non risolti.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd
import requests

from foramqs.clean import ND, SPP
from foramqs.validate import INFO, WARNING, Issue

WORMS_REST = "https://www.marinespecies.org/rest"
BATCH_SIZE = 50  # limite di WoRMS per AphiaRecordsByMatchNames
_KEPT_FIELDS = (
    "AphiaID", "scientificname", "authority", "status", "unacceptreason", "rank", "phylum", "valid_AphiaID",
    "valid_name", "match_type",
)


class WormsClient:
    """Interrogazioni WoRMS con cache su file JSON, così i risultati sono riproducibili e funzionano offline."""

    def __init__(self, cache_path: Path, offline: bool = False, timeout: float = 30):
        self.cache_path = cache_path
        self.offline = offline
        self.timeout = timeout
        cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
        self.by_name: dict[str, list[dict]] = cache.get("by_name", {})
        self.by_id: dict[str, dict] = cache.get("by_id", {})

    def match_names(self, names: list[str]) -> dict[str, list[dict]]:
        """Candidati WoRMS per ogni nome (lista vuota se WoRMS non trova nulla)."""
        missing = sorted({n for n in names if n not in self.by_name})
        if missing and self.offline:
            raise RuntimeError(f"Modalità offline: {len(missing)} nomi non sono nella cache WoRMS (es. {missing[0]!r})")
        for start in range(0, len(missing), BATCH_SIZE):
            batch = missing[start:start + BATCH_SIZE]
            response = requests.get(
                f"{WORMS_REST}/AphiaRecordsByMatchNames",
                params=[("scientificnames[]", n) for n in batch] + [("marine_only", "false")],
                timeout=self.timeout,
            )
            response.raise_for_status()
            results = response.json() if response.status_code == 200 else [[] for _ in batch]
            for name, candidates in zip(batch, results):
                self.by_name[name] = [_keep(c) for c in candidates or []]
        self._save()
        return {n: self.by_name[n] for n in names}

    def record(self, aphia_id: int) -> dict:
        key = str(aphia_id)
        if key not in self.by_id:
            if self.offline:
                raise RuntimeError(f"Modalità offline: AphiaID {aphia_id} non è nella cache WoRMS")
            response = requests.get(f"{WORMS_REST}/AphiaRecordByAphiaID/{aphia_id}", timeout=self.timeout)
            response.raise_for_status()
            self.by_id[key] = _keep(response.json())
            self._save()
        return self.by_id[key]

    def _save(self) -> None:
        self.cache_path.write_text(
            json.dumps({"by_name": self.by_name, "by_id": self.by_id}, ensure_ascii=False, indent=1, sort_keys=True),
            encoding="utf-8",
        )


@dataclass(frozen=True)
class Resolution:
    taxon: str
    taxon_id: str
    nome_valido: str
    fonte: str  # "alias" | "worms" | "non_determinato" | "non_risolto"
    stato_worms: str = ""
    aphia_id: int | None = None
    aphia_id_valido: int | None = None
    nota: str = ""


def resolve_taxa(taxa: list[str], aliases: pd.DataFrame, client: WormsClient, required_phylum: str) -> pd.DataFrame:
    """Risolve i nomi puliti: una riga per nome con taxon_id, nome_valido, fonte e note."""
    alias_ids = {row.nome: int(row.aphia_id) for row in aliases.itertuples(index=False)}
    to_query = sorted({_query_name(t) for t in taxa if not _is_not_determined(t) and t not in alias_ids})
    candidates = client.match_names(to_query)

    resolutions = []
    for taxon in sorted(set(taxa)):
        if _is_not_determined(taxon):
            resolutions.append(Resolution(taxon, taxon, taxon, "non_determinato"))
        elif taxon in alias_ids:
            resolutions.append(_from_alias(taxon, client.record(alias_ids[taxon])))
        else:
            resolutions.append(_from_worms(taxon, candidates[_query_name(taxon)], required_phylum))

    return pd.DataFrame([asdict(r) for r in resolutions], columns=list(Resolution.__dataclass_fields__))


def _from_alias(taxon: str, record: dict) -> Resolution:
    name = _display_name(record["scientificname"], taxon)
    return Resolution(
        taxon, _taxon_id(record["AphiaID"], taxon), name, "alias", record.get("status", ""), record["AphiaID"],
        record["AphiaID"], "AphiaID imposto da taxon_aliases.csv",
    )


def _from_worms(taxon: str, candidates: list[dict], required_phylum: str) -> Resolution:
    in_phylum = [c for c in candidates if c.get("phylum") in (required_phylum, None)]
    exact = [c for c in in_phylum if c.get("match_type") == "exact"]
    if exact:
        c = exact[0]
        valid_id = c.get("valid_AphiaID") or c["AphiaID"]
        valid_name = c.get("valid_name") or c["scientificname"]
        note = "" if c.get("status") == "accepted" else f"{c['scientificname']} è '{c.get('status')}' in WoRMS"
        return Resolution(
            taxon, _taxon_id(valid_id, taxon), _display_name(valid_name, taxon), "worms", c.get("status", ""),
            c["AphiaID"], valid_id, note,
        )
    suggestion = "; ".join(
        f"{c['scientificname']} (AphiaID {c['AphiaID']}, {c.get('match_type')}, {c.get('status')})" for c in in_phylum
    )
    note = f"suggerimento WoRMS: {suggestion}" if suggestion else "nessuna corrispondenza in WoRMS"
    return Resolution(taxon, f"? {taxon}", taxon, "non_risolto", nota=note)


def resolution_issues(table: pd.DataFrame) -> list[Issue]:
    """T01-T04: nomi non risolti, alias applicati, sinonimi risolti, nomi diversi uniti nello stesso taxon."""
    issues = []
    for r in table.itertuples(index=False):
        if r.fonte == "non_risolto":
            issues.append(Issue("T01", WARNING, f"'{r.taxon}' non risolto in WoRMS: resta separato", dettagli=r.nota))
        elif r.fonte == "alias":
            issues.append(Issue("T02", INFO, f"'{r.taxon}' → '{r.nome_valido}' (alias)", dettagli=r.nota))
        elif r.nome_valido != r.taxon:
            issues.append(Issue("T03", INFO, f"'{r.taxon}' → '{r.nome_valido}' (WoRMS)", dettagli=r.nota))
    for taxon_id, group in table.groupby("taxon_id"):
        if len(group) > 1:
            issues.append(Issue(
                "T04", INFO, f"Nomi uniti nello stesso taxon '{group['nome_valido'].iloc[0]}'",
                dettagli=", ".join(group["taxon"]),
            ))
    return issues


def _is_not_determined(taxon: str) -> bool:
    return taxon == ND or taxon.startswith(f"{ND} ")


def _is_genus_level(taxon: str) -> bool:
    return taxon.endswith(f" {SPP}")


def _query_name(taxon: str) -> str:
    return taxon.removesuffix(f" {SPP}") if _is_genus_level(taxon) else taxon


def _taxon_id(aphia_id: int, taxon: str) -> str:
    return f"{aphia_id} {SPP}" if _is_genus_level(taxon) else str(aphia_id)


def _display_name(worms_name: str, taxon: str) -> str:
    return f"{worms_name} {SPP}" if _is_genus_level(taxon) else worms_name


def _keep(record: dict) -> dict:
    return {k: record.get(k) for k in _KEPT_FIELDS}
