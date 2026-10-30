"""Caricamento di config/pipeline.toml e delle tabelle di configurazione (CSV)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "pipeline.toml"


@dataclass(frozen=True)
class Config:
    root: Path
    raw: dict

    def path(self, key: str) -> Path:
        """Percorso assoluto di una voce di [paths], risolto rispetto alla cartella del progetto."""
        return self.resolve(self.raw["paths"][key])

    def resolve(self, relative: str) -> Path:
        return (self.root / relative).resolve()

    @property
    def input(self) -> dict:
        return self.raw["input"]

    @property
    def cleaning(self) -> dict:
        return self.raw["cleaning"]

    @property
    def density(self) -> dict:
        return self.raw["density"]

    @property
    def taxonomy(self) -> dict:
        return self.raw["taxonomy"]

    @property
    def traits(self) -> dict:
        return self.raw["traits"]

    @property
    def migration(self) -> dict:
        return self.raw["migration"]


def load_config(path: Path = DEFAULT_CONFIG) -> Config:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    return Config(root=path.resolve().parents[1], raw=raw)


def read_config_csv(path: Path) -> pd.DataFrame:
    """Legge una tabella di configurazione: separatore ';', tutto come testo, celle vuote = ''."""
    return pd.read_csv(path, sep=";", dtype=str, keep_default_na=False, encoding="utf-8-sig")
