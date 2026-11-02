import pandas as pd

from foramqs.config import load_config
from foramqs.validate import check_geochemistry_columns, configured_geochemistry_columns


def test_missing_configured_geochemistry_column_is_an_error():
    cfg = load_config()
    columns = sorted({c for cols in configured_geochemistry_columns(cfg).values() for c in cols})
    values = pd.DataFrame(columns=columns)
    assert check_geochemistry_columns(values, cfg) == []

    renamed = values.rename(columns={"M-AMBI_ 2022": "M-AMBI"})
    issues = check_geochemistry_columns(renamed, cfg)
    assert {i.codice for i in issues} == {"V25"}
    assert any("tables.external_index_column" in i.messaggio for i in issues)
