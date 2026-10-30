"""Interfaccia a riga di comando: `uv run foramqs --help`."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer

from foramqs import pipeline, reconcile
from foramqs.config import DEFAULT_CONFIG, load_config
from foramqs.migrate import migrate_traits
from foramqs.new_sample import NewSampleError, add_sample
from foramqs.report import issue_summary, write_workbook
from foramqs.taxonomy import WormsClient

app = typer.Typer(help="Elaborazione dei campioni di foraminiferi bentonici.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """Elaborazione dei campioni di foraminiferi bentonici."""


@app.command()
def check(
    config: Path = typer.Option(DEFAULT_CONFIG, help="File di configurazione"),
    offline: bool = typer.Option(False, help="Usa solo la cache WoRMS"),
) -> None:
    """Valida, pulisce e risolve i nomi in WoRMS; scrive output/check_<data>.xlsx senza calcolare indici."""
    cfg = load_config(config)
    result = pipeline.check(cfg, offline=offline)
    out = cfg.path("output_dir") / f"check_{datetime.now():%Y%m%d_%H%M}.xlsx"
    write_workbook(out, {
        "Riepilogo": issue_summary(result.issues),
        "Validazione": result.issues,
        "Log_pulizia": result.cleaning_log,
        "Revisione_nomi": result.name_review,
        "Osservazioni": result.observations,
        "Geochimica": result.geochemistry.reset_index(),
    })
    counts = result.issues["severita"].value_counts().to_dict()
    typer.echo(f"Segnalazioni: {counts}. Report: {out}")
    if result.has_errors:
        raise typer.Exit(code=1)


@app.command("migrate-traits")
def migrate_traits_command(
    config: Path = typer.Option(DEFAULT_CONFIG, help="File di configurazione"),
    force: bool = typer.Option(False, help="Sovrascrive reference/species_traits.csv se esiste già"),
    offline: bool = typer.Option(False, help="Usa solo la cache WoRMS"),
) -> None:
    """Crea reference/species_traits.csv dalle fonti storiche (da eseguire una sola volta)."""
    cfg = load_config(config)
    target = cfg.path("species_traits")
    if target.exists() and not force:
        typer.echo(f"{target} esiste già: la tabella dei tratti si modifica a mano. Usa --force per ricrearla.")
        raise typer.Exit(code=1)
    client = WormsClient(cfg.path("worms_cache"), offline=offline)
    traits, conflicts, resolutions = migrate_traits(cfg, client)
    target.parent.mkdir(parents=True, exist_ok=True)
    traits.to_csv(target, sep=";", index=False, encoding="utf-8")
    out = cfg.path("output_dir") / f"migrazione_tratti_{datetime.now():%Y%m%d_%H%M}.xlsx"
    write_workbook(out, {"Conflitti": conflicts, "Risoluzione_nomi": resolutions, "Tratti": traits})
    typer.echo(f"{len(traits)} taxa scritti in {target}; {len(conflicts)} conflitti da risolvere. Dettagli: {out}")


@app.command()
def run(
    config: Path = typer.Option(DEFAULT_CONFIG, help="File di configurazione"),
    offline: bool = typer.Option(False, help="Usa solo la cache WoRMS"),
) -> None:
    """Pipeline completa: scrive output/Results_<data>.xlsx con tabelle, indici e grafici."""
    cfg = load_config(config)
    stamp = f"{datetime.now():%Y%m%d_%H%M}"
    out_dir = cfg.path("output_dir")
    try:
        result = pipeline.run(cfg, figures_dir=out_dir / f"figures_{stamp}", offline=offline)
    except pipeline.PipelineBlocked as blocked:
        errors = blocked.checked.issues[blocked.checked.issues["severita"] == "errore"]
        out = write_workbook(out_dir / f"check_{stamp}.xlsx", {"Validazione": blocked.checked.issues})
        typer.echo(f"{len(errors)} errori negli input: nessun risultato calcolato. Dettagli: {out}")
        for message in errors["messaggio"].head(10):
            typer.echo(f"  - {message}")
        raise typer.Exit(code=1)
    checked = result.checked
    out = write_workbook(out_dir / f"Results_{stamp}.xlsx", {
        **result.sheets,
        "Validazione": result.issues,
        "Log_pulizia": checked.cleaning_log,
        "Revisione_nomi": checked.name_review,
        "Osservazioni": checked.observations,
    }, result.figures)
    counts = result.issues["severita"].value_counts().to_dict()
    typer.echo(f"Segnalazioni: {counts}. Risultati: {out}")


@app.command()
def diff(
    old_results: Path = typer.Argument(..., help="Vecchio Results.xlsx da confrontare"),
    config: Path = typer.Option(DEFAULT_CONFIG, help="File di configurazione"),
    offline: bool = typer.Option(False, help="Usa solo la cache WoRMS"),
) -> None:
    """Confronta gli indici calcolati ora con quelli di un vecchio Results.xlsx."""
    cfg = load_config(config)
    stamp = f"{datetime.now():%Y%m%d_%H%M}"
    out_dir = cfg.path("output_dir")
    try:
        result = pipeline.run(cfg, figures_dir=out_dir / f"figures_{stamp}", offline=offline)
    except pipeline.PipelineBlocked:
        typer.echo("Gli input contengono errori: eseguire `foramqs check` e correggerli prima del confronto.")
        raise typer.Exit(code=1)
    out = write_workbook(out_dir / f"Differenze_{stamp}.xlsx", {
        "Differenze_indici": reconcile.compare(old_results, result.sheets),
        "Cambi_per_campione": reconcile.sample_changes(result.checked.observations, result.checked.cleaning_log),
        "Cause_note": reconcile.KNOWN_CAUSES,
    })
    typer.echo(f"Confronto: {out}")


@app.command("add-sample")
def add_sample_command(
    nome: str = typer.Argument(..., help="Nome del nuovo campione, es. MC_XX01"),
    gruppo: str = typer.Option(..., "--gruppo", help="Gruppo di cluster a cui assegnarlo (es. G1; se non esiste viene creato)"),
    config: Path = typer.Option(DEFAULT_CONFIG, help="File di configurazione"),
) -> None:
    """Aggiunge un campione vuoto: Tabella delle conte, riga di geochimica e gruppo di cluster, da compilare a mano."""
    cfg = load_config(config)
    try:
        added = add_sample(cfg, config, nome, gruppo)
    except NewSampleError as error:
        typer.echo(f"Campione non aggiunto: {error}")
        raise typer.Exit(code=1)
    workbook = cfg.path("data_workbook").name
    typer.echo(f"Backup del workbook: {added.backup}")
    if added.removed_power_query:
        typer.echo("Attenzione: le query Power Query e le connessioni dati del workbook sono state rimosse "
                   "(non servono alla pipeline; restano nel backup).")
    typer.echo(f"1. {workbook}: nuovo foglio '{added.name}' con la Tabella '{added.name}' vuota")
    typer.echo(f"2. {workbook}: riga {added.geochemistry_row} della tabella {cfg.input['geochemistry_table']} con il solo nome")
    action = "creato" if added.group_created else "aggiornato"
    typer.echo(f"3. {config.name}: gruppo di cluster {added.group} {action}")
    typer.echo("Compilare conte e geochimica, poi `uv run foramqs check` (V26/V27 indicano cosa manca).")
