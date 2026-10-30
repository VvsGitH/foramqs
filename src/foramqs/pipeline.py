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
from foramqs.indices.foramecoqs import foramecoqs_table
from foramqs.inputs import geochemistry_values, load_inputs
from foramqs.taxonomy import WormsClient, resolution_issues, resolve_taxa


@dataclass(frozen=True)
class CheckResult:
    observations: pd.DataFrame  # una riga per casella, con taxon_id e nome_valido
    cleaning_log: pd.DataFrame
    name_review: pd.DataFrame  # come è stato risolto ogni nome pulito
    traits: pd.DataFrame  # tratti indicizzati per taxon_id
    geochemistry: pd.DataFrame
    issues: pd.DataFrame

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

    resolutions = resolve_taxa(
        sorted(set(observations["taxon"]) | set(traits_names.values())),
        read_config_csv(cfg.path("taxon_aliases")),
        WormsClient(cfg.path("worms_cache"), offline=offline),
        cfg.taxonomy["required_phylum"],
    )
    observations = observations.join(resolutions.set_index("taxon")[["taxon_id", "nome_valido"]], on="taxon")
    traits = tr.attach_taxon_ids(traits, traits_names, resolutions)
    traits_table = tr.traits_by_taxon(traits)
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
    ]
    return CheckResult(
        observations=with_copies,
        cleaning_log=cleaning_log(cleaned_rows),
        name_review=_name_review(resolutions, observations),
        traits=traits_table,
        geochemistry=geochemistry,
        issues=v.issues_frame(issues),
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


@dataclass(frozen=True)
class RunResult:
    checked: CheckResult
    sheets: dict[str, pd.DataFrame]  # nome del foglio → tabella (l'indice diventa la prima colonna)
    figures: dict[str, list[Path]]  # nome del foglio → grafici da inserire accanto alla tabella
    issues: pd.DataFrame


def run(cfg: Config, figures_dir: Path, offline: bool = False) -> RunResult:
    """Pipeline completa: controlli, tabelle, indici, analisi multivariate e grafici."""
    checked = check(cfg, offline=offline)
    if checked.has_errors:
        raise PipelineBlocked(checked)

    obs, traits, geo = checked.observations, checked.traits, checked.geochemistry
    t, labels = cfg.raw["tables"], cfg.raw["labels"]
    samples = list(dict.fromkeys(obs["campione"]))
    mode = t["threshold_mode"]

    counts = tb.abundance(obs, samples)
    rel = tb.relative(counts)
    clustering = mv.cluster_samples(rel, cfg.raw["cluster"]["method"], cfg.raw["cluster"]["metric"])
    order = clustering.order
    groups = cfg.raw["cluster"]["groups"]

    def trait(column: str, name: str) -> pd.Series:
        return tb.trait_of(counts, traits, column).rename(name)

    feqs = foramecoqs_table(counts, trait("gruppo_fsi", "FSI"), trait("gruppo_ecologico", "EG"), cfg.raw["eqs"])
    past = diversity_table(counts).rename_axis("Indice")
    eco_labels = {"1": "GI", "2": "GII", "3": "GIII", "4": "GIV", "5": "GV"}
    shell = tb.by_trait(counts, trait("guscio", "TIPO GUSCIO"), labels["shell"])
    lifestyle = tb.by_trait(counts, trait("stile_di_vita", "STILE DI VITA"), labels["lifestyle"])
    eco = tb.by_trait(counts, trait("gruppo_ecologico", "Gruppo ecologico"), eco_labels)
    fsi_groups = tb.by_trait(counts, trait("gruppo_fsi", "Gruppo FSI"))
    deformed = tb.deformed_fraction(obs, samples)
    per_replica, density = tb.density(obs, samples, cfg.density["replica_volume_ml"], cfg.density["per_ml"])
    dominant = tb.above_threshold(rel, t["dominant_species_threshold"], mode)
    genera = tb.genera_composition(rel, t["genera_threshold"], mode)
    past5 = tb.species_columns_for_past(rel, traits, t["dominant_species_threshold"], mode,
                                        labels["lifestyle_abbreviation"])

    environment = geo.assign(Shannon_H=past.loc["Shannon_H"])
    main_indices = feqs[["exp(H'bc)", "FSI", "Species Richness (S)", "Foram-AMBI"]]
    matrix = environment.join(pd.DataFrame({
        "FSI": feqs["FSI"],
        "Foram-AMBI": feqs["Foram-AMBI"],
        "Deformed_rel%_abundance": deformed * 100,
        "Densità faunistica media": density,
    }))
    env_z = tb.zscore(environment)
    cca_env_columns = t["past_geochemistry_columns"]
    cca_environment = tb.zscore(geo[cca_env_columns])
    cca_result = mv.canonical_correspondence(past5, cca_environment)

    sheets = {
        "Indici_PAST": past[order],
        "Foram Echo QS": feqs.loc[order],
        "Foram_Echo_QS_Norm": tb.zscore(main_indices).loc[order],
        "Abbondanze_assolute": counts,
        "Abbondanza_relativa%": rel,
        "Abbondanza_rel%_deformati": deformed.loc[order].to_frame(),
        "Abbondanza_relativa%_guscio": shell[order],
        "Abbondanza_rel%_stilivita": lifestyle[order],
        "Abbondanza_rel%_gruppiecologici": eco[order].T.join(feqs["Foram-AMBI"]).join(geo[t["external_index_column"]]),
        "FSI": fsi_groups[order].T.join(feqs["FSI"]),
        "FSI-M-AMBI": feqs[["FSI", "Foram-AMBI"]].join(geo[t["external_index_column"]]).loc[order],
        "Densità_faunistica_media": density.loc[order].to_frame(),
        "Densità_per_replica": per_replica.set_index("campione"),
        "Tabella_Cluster": dominant[order],
        **{f"Tabella_Cluster_{g}": dominant[[s for s in order if s in members]] for g, members in groups.items()},
        "Tabella_comunità_3%": genera[order],
        "Abb_rel%_cut5": dominant[order],
        "Abbondanza_relativa_PAST_5%": geo[cca_env_columns].join(past5).loc[order],
        "Specie&TOC": geo[[t["toc_column"]]].join(past5).loc[order],
        "Tabella_matrice": matrix.loc[order],
        "Tabella_completa": matrix.drop(columns=t["complete_table_excluded_columns"]).join(past5).loc[order],
        "Variabili_campioni_normalizzate": env_z.loc[order],
        "Tabella_CCA_normalizzata": tb.zscore(main_indices).join(env_z).join(past5).loc[order],
        "CCA_assi": mv.cca_axes(cca_result, cca_environment),
        "CCA_campioni": cca_result.samples,
        "CCA_variabili": cca_result.biplot_scores.rename_axis("Variabile"),
        "Specchietto_limiti HMe": tb.sqa_exceedances(geo, cfg.raw["sqa"]),
    }

    fig = figures_dir
    eqs = cfg.raw["eqs"]
    figures = {
        "Indici_PAST": [
            plots.bar_chart(past.loc["Taxa_S"], order, "Ricchezza specifica (S)", "Taxa", fig / "ricchezza.png"),
            plots.bar_chart(past.loc["Shannon_H"], order, "Indice di Shannon (PAST, Miller–Madow)", "H'", fig / "shannon.png"),
        ],
        "Foram Echo QS": [
            plots.bar_chart(feqs["exp(H'bc)"], order, "exp(H'bc)", "exp(H'bc)", fig / "exp_hbc.png", _limits(eqs["exp_hbc"])),
            plots.bar_chart(feqs["Foram-AMBI"], order, "Foram-AMBI", "Foram-AMBI", fig / "foram_ambi.png", _limits(eqs["foram_ambi"])),
        ],
        "FSI": [plots.bar_chart(feqs["FSI"], order, "Foram Stress Index (FSI)", "FSI", fig / "fsi.png", _limits(eqs["fsi"]))],
        "FSI-M-AMBI": [plots.panels({
            "FSI": feqs["FSI"], "Foram-AMBI": feqs["Foram-AMBI"], t["external_index_column"]: geo[t["external_index_column"]],
        }, order, f"FSI, Foram-AMBI e {t['external_index_column']}", fig / "fsi_ambi_mambi.png")],
        "Abbondanza_rel%_deformati": [plots.bar_chart(deformed * 100, order, "Individui deformati", "%", fig / "deformati.png")],
        "Abbondanza_relativa%_guscio": [plots.stacked_composition(shell, order, "Tipi di guscio", fig / "guscio.png")],
        "Abbondanza_rel%_stilivita": [plots.stacked_composition(lifestyle, order, "Stili di vita", fig / "stili_di_vita.png")],
        "Abbondanza_rel%_gruppiecologici": [plots.stacked_composition(eco, order, "Gruppi ecologici", fig / "gruppi_ecologici.png")],
        "Densità_faunistica_media": [plots.bar_chart(density, order, "Densità faunistica media", "individui / 10 ml", fig / "densita.png")],
        "Tabella_comunità_3%": [plots.stacked_composition(genera, order, "Generi (specie ≥ 3%)", fig / "generi.png")],
        "Abb_rel%_cut5": [plots.stacked_composition(dominant, order, "Specie dominanti (≥ 5%)", fig / "specie_dominanti.png")],
        "Tabella_Cluster": [plots.dendrogram_chart(clustering, groups, fig / "dendrogramma.png")],
        "CCA_campioni": [plots.cca_biplot(cca_result, fig / "cca.png")],
    }

    issues = v.issues_frame([
        *[v.Issue(**row) for row in checked.issues.to_dict("records")],
        *mv.check_group_branches(clustering, groups),
    ])
    sheets = {name: frame.rename_axis(frame.index.name or "Campione") for name, frame in sheets.items()}
    return RunResult(checked=checked, sheets=sheets, figures=figures, issues=issues)


def _limits(rules: list[list]) -> list[tuple[str, float]]:
    """Limiti di classe EQS da disegnare: una linea per regola con soglia (esclusa l'uguaglianza esatta)."""
    return [(label, limit) for label, operator, limit in (r for r in rules if len(r) == 3) if operator != "=="]
