"""Sequenza dei passi della pipeline. Ogni passo è una funzione di un modulo dedicato; qui vengono solo collegati."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from foramqs import multivariate as mv
from foramqs import plots
from foramqs import tables as tb
from foramqs import traits as tr
from foramqs import validate as v
from foramqs.clean import build_observations, clean_taxon_name, cleaning_log, copy_single_replica
from foramqs.config import Config, read_config_csv
from foramqs.indices.diversity import diversity_table
from foramqs.indices.foramecoqs import EXP_HBC_COLUMNS, FORAM_AMBI_COLUMNS, FSI_COLUMNS, foramecoqs_table
from foramqs.inputs import geochemistry_values, load_inputs
from foramqs.taxonomy import WormsClient, resolution_issues, resolve_taxa

ALT_GROUPS_SHEET = "Abbondanza_rel%_gruppiecol_alt"  # i nomi dei fogli Excel hanno al massimo 31 caratteri


@dataclass(frozen=True)
class CheckResult:
    observations: pd.DataFrame  # una riga per casella, con taxon_id e nome_valido
    cleaning_log: pd.DataFrame
    name_review: pd.DataFrame  # come è stato risolto ogni nome pulito
    traits: pd.DataFrame  # tratti indicizzati per taxon_id
    geochemistry: pd.DataFrame
    issues: pd.DataFrame
    alt_traits: pd.DataFrame | None = None

    @property
    def has_errors(self) -> bool:
        return bool((self.issues["severita"] == v.ERROR).any())


def check(cfg: Config, offline: bool = False) -> CheckResult:
    """Lettura, validazione, pulizia e risoluzione tassonomica degli input, senza calcolare indici."""
    inputs = load_inputs(cfg)
    juveniles = cfg.cleaning["juveniles_into_genus_spp"]
    observations, cleaned_rows = build_observations(
        inputs.samples,
        inputs.name_corrections,
        inputs.non_foram_terms,
        {label.casefold() for label in cfg.cleaning["not_determined_labels"]},
        juveniles,
        cfg.input["sample_comment_column"],
    )
    geochemistry = geochemistry_values(inputs.geochemistry, cfg)

    traits_path = cfg.path("species_traits")
    if not traits_path.exists():
        raise FileNotFoundError(f"{traits_path} non esiste: eseguire prima `foramqs migrate-traits`")
    traits = read_config_csv(traits_path)
    traits_names = {n: clean_taxon_name(n, inputs.name_corrections, juveniles) for n in traits["nome"]}

    alt_cfg = cfg.raw.get("foram_ambi_alternative", {})
    alt_samples_cfg = alt_cfg.get("samples", [])
    alt_file = alt_cfg.get("file", "reference/foram_ambi_alt.csv")
    alt_path = cfg.resolve(alt_file) if alt_file else None
    alt_traits_raw = None
    alt_names = {}
    alt_issues = []

    if alt_samples_cfg and alt_path:
        if not alt_path.exists():
            alt_issues.append(v.Issue("A02", v.ERROR, f"File alternativo dei gruppi ecologici non trovato: {alt_path}"))
        else:
            alt_traits_raw = read_config_csv(alt_path)
            if "nome" in alt_traits_raw.columns:
                alt_names = {n: clean_taxon_name(n, inputs.name_corrections, juveniles) for n in alt_traits_raw["nome"]}

    resolutions = resolve_taxa(
        sorted(set(observations["taxon"]) | set(traits_names.values()) | set(alt_names.values())),
        read_config_csv(cfg.path("taxon_aliases")),
        WormsClient(cfg.path("worms_cache"), offline=offline),
        cfg.taxonomy["required_phylum"],
    )
    observations = observations.join(resolutions.set_index("taxon")[["taxon_id", "nome_valido"]], on="taxon")
    traits = tr.attach_taxon_ids(traits, traits_names, resolutions)
    traits_table = tr.traits_by_taxon(traits)

    alt_traits_table = None
    if alt_traits_raw is not None and "nome" in alt_traits_raw.columns:
        alt_traits_attached = tr.attach_taxon_ids(alt_traits_raw, alt_names, resolutions)
        alt_issues.extend(v.check_alternative_ambi_traits(alt_traits_attached, cfg.traits["eco_groups"], alt_path.name))
        alt_traits_table = alt_traits_attached

    if alt_samples_cfg:
        alt_issues.extend(v.check_alternative_ambi_samples(alt_samples_cfg, set(inputs.samples)))
        alt_issues.extend(v.check_alternative_ambi_sheet(alt_cfg.get("groups_sheet", ALT_GROUPS_SHEET)))

    allowed = {
        "stile_di_vita": cfg.traits["lifestyles"],
        "gruppo_ecologico": cfg.traits["eco_groups"],
        "gruppo_fsi": cfg.traits["fsi_groups"],
        "guscio": cfg.cleaning["valid_shell_types"],
    }

    # Le repliche copiate servono ai calcoli e al controllo del numero di repliche (V08); gli altri controlli
    # guardano le righe del workbook, che non vanno segnalate più volte.
    copies = cfg.input.get("copied_replicas", {})
    with_copies = copy_single_replica(observations, copies)
    issues = [
        *v.check_sample_tables(inputs.samples),
        *v.check_row_values(inputs.samples, cfg),
        *v.check_missing_counts(observations),
        *v.check_copied_replicas(observations, copies),
        *v.check_positions(with_copies),
        *v.check_counted_individuals(inputs.samples, observations),
        *v.check_parsed_names(cleaned_rows),
        *v.check_shell_consistency(observations[~observations["taxon_id"].isin(traits_table.index)]),
        *v.check_similar_names(observations, cfg.cleaning["similar_names_threshold"]),
        *v.check_juveniles(cleaned_rows),
        *v.check_cluster_groups(cfg.raw["cluster"]["groups"], set(inputs.samples)),
        *v.check_geochemistry_columns(geochemistry, cfg),
        *v.check_geochemistry(inputs.geochemistry, geochemistry, set(inputs.samples), cfg),
        *resolution_issues(resolutions[resolutions["taxon"].isin(observations["taxon"])]),
        *tr.check_traits(traits, allowed),
        *tr.check_coverage(observations, traits_table),
        *tr.check_shell_against_traits(observations, traits_table),
        *alt_issues,
    ]
    return CheckResult(
        observations=with_copies,
        cleaning_log=cleaning_log(cleaned_rows),
        name_review=_name_review(resolutions, observations),
        traits=traits_table,
        geochemistry=geochemistry,
        issues=v.issues_frame(issues),
        alt_traits=alt_traits_table,
    )


def _name_review(resolutions: pd.DataFrame, observations: pd.DataFrame) -> pd.DataFrame:
    """Risoluzione dei nomi presenti nei campioni: prima i non risolti, poi i nomi cambiati, poi gli altri."""
    used = resolutions[resolutions["taxon"].isin(observations["taxon"])]
    priority = used["fonte"].eq("non_risolto").map({True: 0, False: 2}) - used["taxon"].ne(used["nome_valido"]).astype(int)
    return used.assign(_p=priority).sort_values(["_p", "taxon"]).drop(columns="_p").reset_index(drop=True)


class PipelineBlocked(Exception):
    """Gli input contengono errori: nessun risultato viene calcolato finché non sono corretti."""

    def __init__(self, checked: CheckResult):
        super().__init__("Gli input contengono errori (foglio Validazione)")
        self.checked = checked


# Fogli dei risultati (i fogli della Fase 1 seguono, aggiunti dalla CLI).
ABSOLUTE, RELATIVE = "Abb_assolute", "Abb_rel%"  # il foglio delle specie dominanti è Abb_rel_<soglia>%
PAST, EXP_HBC, FSI, FORAM_AMBI, OTHER = "Indici_PAST", "Exp(H'bc)", "FSI", "Foram-AMBI", "Altre_info"
CA, PCA_CCA = "CA", "PCA_CCA"


@dataclass(frozen=True)
class RunResult:
    checked: CheckResult
    sheets: dict[str, pd.DataFrame]  # nome del foglio → tabella (l'indice diventa la prima colonna), nell'ordine di scrittura
    figures: dict[str, list[Path]]  # nome del foglio → immagini da inserire accanto alla tabella (dendrogrammi)
    formulas: dict[str, pd.DataFrame]  # nome del foglio → formule Excel con la stessa forma della tabella
    issues: pd.DataFrame


def run(cfg: Config, figures_dir: Path, offline: bool = False) -> RunResult:
    """Pipeline completa: controlli della Fase 1, poi i dieci fogli dei risultati.

    Tutti i fogli hanno i campioni nell'ordine delle foglie del dendrogramma Q-mode. I fogli 1–8 hanno i campioni
    nelle colonne, CA e PCA_CCA nelle righe. Il foglio CA è scritto con formule `=LOG10(1+x)` che puntano ad Abb_rel_<soglia>%.
    """
    checked = check(cfg, offline=offline)
    if checked.has_errors:
        raise PipelineBlocked(checked)

    obs, traits, geo = checked.observations, checked.traits, checked.geochemistry
    t, labels, cl = cfg.raw["tables"], cfg.raw["labels"], cfg.raw["cluster"]
    samples = list(dict.fromkeys(obs["campione"]))

    counts = tb.abundance(obs, samples)
    rel = tb.relative(counts)
    cut = t["dominant_species_threshold"]
    dominant_sheet = f"Abb_rel_{cut * 100:g}%"
    dominant = tb.above_threshold(rel, cut, t["threshold_mode"]) * 100

    # Cluster Analysis (Q-mode sui campioni, R-mode sulle specie) sulle specie dominanti trasformate con log(1+x).
    ca = tb.log10_1px(dominant.T)
    metric_name = {"euclidean": "euclidea", "braycurtis": "di Bray-Curtis"}.get(cl["metric"], cl["metric"])
    method = f"{cl['method'].capitalize()}, distanza {metric_name}"
    q_mode = mv.cluster(ca, cl["method"], cl["metric"])
    r_mode = mv.cluster(ca.T, cl["method"], cl["metric"])
    order = q_mode.order

    def trait(column: str) -> pd.Series:
        return tb.trait_of(counts, traits, column)

    feqs = foramecoqs_table(counts, trait("gruppo_fsi"), trait("gruppo_ecologico"), cfg.raw["eqs"])
    shell = tb.by_trait(counts, trait("guscio"), labels["shell"]) * 100
    lifestyle = tb.by_trait(counts, trait("stile_di_vita"), labels["lifestyle"]) * 100
    _, density = tb.density(obs, samples, cfg.density["replica_volume_ml"], cfg.density["per_ml"])
    deformed = tb.deformed_fraction(obs, samples) * 100
    other = pd.concat([
        density.to_frame().T,
        shell.rename(index=lambda c: f"% {c}"),
        lifestyle.rename(index=lambda c: f"% {c}"),
        deformed.rename("% Deformati").to_frame().T,
    ])

    environment = t["pca_cca_environment"]
    missing = [c for c in environment if c not in geo.columns]
    if missing:
        raise ValueError(f"Colonne di [tables].pca_cca_environment assenti dalla geochimica: {', '.join(missing)}")
    pca_cca = pd.concat([
        dominant.T,
        geo[environment],
        feqs[["Species Richness (S)", "exp(H'bc)", "FSI", "Foram-AMBI"]].rename(columns={"Species Richness (S)": "S"}),
    ], axis=1)

    def by_index(columns: list[str]) -> pd.DataFrame:
        return feqs[columns].T.rename_axis("Indice")

    sheets = {
        ABSOLUTE: counts[order],
        RELATIVE: (rel * 100)[order],
        dominant_sheet: dominant[order],
        PAST: diversity_table(counts)[order].rename_axis("Indice"),
        EXP_HBC: by_index(EXP_HBC_COLUMNS)[order],
        FSI: by_index(FSI_COLUMNS)[order],
        FORAM_AMBI: by_index(FORAM_AMBI_COLUMNS)[order],
        OTHER: other[order].rename_axis("Parametro"),
        CA: ca.loc[order],
        PCA_CCA: tb.log10_1px(pca_cca).loc[order],
    }
    sheets = {name: frame.rename_axis(frame.index.name or "Campione") for name, frame in sheets.items()}
    formulas = {CA: tb.log10_1px_formulas(dominant_sheet, sheets[dominant_sheet])}

    groups = cl["groups"]
    figures = {CA: [
        plots.q_mode_chart(q_mode, groups, method, figures_dir / "dendrogramma_Q_mode.png"),
        plots.r_mode_chart(r_mode, method, figures_dir / "dendrogramma_R_mode.png"),
    ]}
    issues = v.issues_frame([
        *[v.Issue(**row) for row in checked.issues.to_dict("records")],
        *mv.check_group_branches(q_mode, groups, method),
    ])
    return RunResult(checked=checked, sheets=sheets, figures=figures, formulas=formulas, issues=issues)
