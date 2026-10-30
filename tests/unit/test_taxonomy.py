import json

import pandas as pd
import pytest

from foramqs import taxonomy
from foramqs.taxonomy import WormsClient, resolution_issues, resolve_taxa


def record(aphia_id, name, status, valid_id=None, valid_name=None, match_type="exact"):
    return {
        "AphiaID": aphia_id, "scientificname": name, "authority": "", "status": status, "unacceptreason": None,
        "rank": "Species", "phylum": "Foraminifera", "valid_AphiaID": valid_id or aphia_id,
        "valid_name": valid_name or name, "match_type": match_type,
    }


class FakeClient:
    """Stessa interfaccia di WormsClient, con risposte scritte nel test."""

    def __init__(self, by_name=None, by_id=None):
        self.by_name, self.by_id = by_name or {}, by_id or {}

    def match_names(self, names):
        return {n: self.by_name.get(n, []) for n in names}

    def record(self, aphia_id):
        return self.by_id[str(aphia_id)]


NO_ALIASES = pd.DataFrame(columns=["nome", "aphia_id"])


def test_accepted_record_is_preferred_and_homonyms_are_reported():
    client = FakeClient({"Genus homonymus": [
        record(2, "Genus homonymus", "unreplaced junior homonym"),
        record(1, "Genus homonymus", "accepted"),
    ]})
    resolved = resolve_taxa(["Genus homonymus"], NO_ALIASES, client, "Foraminifera").iloc[0]
    assert resolved["taxon_id"] == "1"
    issues = resolution_issues(pd.DataFrame([resolved]))
    assert [i.codice for i in issues] == ["T06"]
    assert "AphiaID 2" in issues[0].dettagli


def test_duplicate_records_of_the_same_taxon_are_not_ambiguous():
    client = FakeClient({"Genus speciesa": [
        record(1, "Genus speciesa", "accepted"),
        record(3, "Genus speciesa", "superseded combination", valid_id=1, valid_name="Genus speciesa"),
    ]})
    resolved = resolve_taxa(["Genus speciesa"], NO_ALIASES, client, "Foraminifera")
    assert resolved.iloc[0]["alternative"] == ""
    assert resolution_issues(resolved) == []


def test_alias_to_a_synonym_is_kept_separate_and_reported():
    synonym = record(7, "Genus vetus", "unaccepted", valid_id=8, valid_name="Genus novus")
    client = FakeClient(by_id={"7": synonym})
    aliases = pd.DataFrame({"nome": ["Genus vetus"], "aphia_id": [7]})
    resolved = resolve_taxa(["Genus vetus"], aliases, client, "Foraminifera").iloc[0]
    assert (resolved["taxon_id"], resolved["aphia_id_valido"]) == ("7", 8)
    assert [i.codice for i in resolution_issues(pd.DataFrame([resolved]))] == ["T05"]


def test_worms_cache_is_saved_after_each_batch(tmp_path, monkeypatch):
    class Response:
        status_code = 200

        def __init__(self, names):
            self.names = names

        def raise_for_status(self):
            pass

        def json(self):
            return [[record(1, n, "accepted")] for n in self.names]

    calls = []

    def fake_get(url, params, timeout):
        calls.append(params)
        if len(calls) > 1:
            raise ConnectionError("rete persa")
        return Response([value for key, value in params if key == "scientificnames[]"])

    monkeypatch.setattr(taxonomy, "BATCH_SIZE", 1)
    monkeypatch.setattr(taxonomy.requests, "get", fake_get)
    cache = tmp_path / "worms_cache.json"
    with pytest.raises(ConnectionError):
        WormsClient(cache).match_names(["Genus primus", "Genus secundus"])
    assert list(json.loads(cache.read_text(encoding="utf-8"))["by_name"]) == ["Genus primus"]
