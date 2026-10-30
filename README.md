# foramqs: elaborazione dei campioni di foraminiferi bentonici

Pipeline unica che sostituisce Power Query, ForamEcoQS e i passaggi manuali in PAST. Parte **solo** dai dati
grezzi (le tabelle `MC_*` e la geochimica di `input_data/Campioni_P_2025_Data_Raw.xlsx`) e da poche tabelle tecniche non
derivabili, e produce un `Results_<data>.xlsx` con gli stessi fogli di prima, più i grafici e i report di controllo.

Principi:
- **nessun dato derivato viene copiato a mano**: Shannon, densità, liste per ForamEcoQS, etichette PAST… sono calcolati;
- **gli errori negli input fermano il calcolo**; gli avvisi finiscono nel foglio `Validazione`;
- **ogni trasformazione è tracciata** (`Log_pulizia`, `Revisione_nomi`).

## Installazione

Serve solo [uv](https://docs.astral.sh/uv/), che scarica da sé Python 3.12 e tutte le dipendenze: non occorre
installare Python a parte. Per scaricare il progetto serve anche [git](https://git-scm.com/), oppure si scarica lo
ZIP da GitHub (*Code → Download ZIP*).

### macOS

Nel Terminale:

```bash
brew install uv                                   # una volta sola (senza Homebrew: curl -LsSf https://astral.sh/uv/install.sh | sh)
git clone https://github.com/VvsGitH/foramqs.git data-elaboration-python
cd data-elaboration-python
uv sync                                           # crea l'ambiente Python 3.12 con le dipendenze
```

### Windows 11

In PowerShell (o nel Terminale di Windows):

```powershell
winget install --id=astral-sh.uv -e               # una volta sola, poi chiudere e riaprire PowerShell
git clone https://github.com/VvsGitH/foramqs.git data-elaboration-python
cd data-elaboration-python
uv sync                                           # crea l'ambiente Python 3.12 con le dipendenze
```

Senza `winget`, uv si installa con `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`.

Note per Windows:
- i comandi `uv run foramqs …` sono identici a macOS; nei percorsi si possono usare sia `/` sia `\`;
- i file Excel vanno chiusi prima di `add-sample`: Windows non permette di modificare un file aperto in Excel;
- per salvare l'output dei comandi su un file (`uv run foramqs check > log.txt`) impostare prima
  `$env:PYTHONUTF8 = "1"`, altrimenti alcuni simboli dei messaggi (→, ≥) possono dare errore;
- conviene non tenere il progetto in una cartella sincronizzata da OneDrive: la sincronizzazione può bloccare i
  file mentre la pipeline li scrive.

### Dopo l'installazione

Copiare i file Excel in `input_data/` (vedi [Dati](#dati)), poi verificare che tutto funzioni:

```bash
uv run pytest                                     # test
uv run foramqs check                              # controllo degli input
```

## Dati

I workbook Excel stanno in `input_data/` e **non sono versionati** (`.gitignore`): dopo aver clonato la repo vanno
copiati lì.

| File | Uso |
|---|---|
| `input_data/Campioni_P_2025_Data_Raw.xlsx` | **fonte primaria**: input della pipeline (percorso in `config/pipeline.toml`) |
| `input_data/Campioni_P_2025_Data.xlsx` | vecchio workbook con Power Query: solo storico, migrazione dei tratti e test di parità |
| `input_data/Campioni_P_2025_Results.xlsx` | vecchi risultati: `foramqs diff` e test di parità |
| `input_data/Raw_ForamsEcoQs.xlsx` | vecchio input di ForamEcoQS: test di parità |

Se i due file storici mancano, i test in `tests/legacy` vengono saltati.

Il formato atteso (Tabelle Excel dei campioni, colonne obbligatorie, geochimica) è descritto in
[input_data/README.md](input_data/README.md).

## Comandi

| Comando | Cosa fa |
|---|---|
| `uv run foramqs check` | Legge, valida e pulisce gli input e risolve i nomi in WoRMS. Scrive `output/check_<data>.xlsx` senza calcolare indici. |
| `uv run foramqs run` | Pipeline completa → `output/Results_<data>.xlsx` e `output/figures_<data>/`. Se ci sono errori negli input si ferma e li elenca. |
| `uv run foramqs diff input_data/Campioni_P_2025_Results.xlsx` | Confronta gli indici con un vecchio Results ed elenca, per campione, i cambiamenti che spiegano le differenze. |
| `uv run foramqs add-sample MC_XX01 --gruppo G1` | Aggiunge un campione vuoto da compilare a mano: foglio con la Tabella delle conte, riga in `Geochimica_campioni`, campione nel gruppo di cluster indicato. Fa prima un backup del workbook in `input_data/backup/`. |
| `uv run foramqs migrate-traits` | Crea `reference/species_traits.csv` dalle fonti storiche. **Già eseguito**: da qui in poi la tabella dei tratti si modifica a mano. |

Con `--offline` WoRMS non viene interrogato e si usa solo la cache (`config/worms_cache.json`).

## Dati in ingresso

| File | Contenuto | Chi lo modifica |
|---|---|---|
| `input_data/Campioni_P_2025_Data_Raw.xlsx` | Tabelle `MC_*` (conte per casella), colonna `COMMENTI & DUBBI` accanto, tabella `Geochimica_campioni` | laboratorio |
| `reference/species_traits.csv` | Tratti per taxon: stile di vita, gruppo ecologico Foram-AMBI (1-5/NA), gruppo FSI (Sen/Str/ND), guscio (A/I/P) | ricercatori |
| `config/name_corrections.csv` | Refusi da correggere nel testo (`trova;sostituisci;motivo;fonte`) | ricercatori |
| `config/taxon_aliases.csv` | AphiaID imposto per un nome, con precedenza su WoRMS (`nome;aphia_id;motivo;fonte`) | ricercatori |
| `config/non_foram_terms.csv` | Voci da scartare (diatomee, "No Forams"…) | ricercatori |
| `config/pipeline.toml` | Percorsi, soglie, volume delle repliche, classi EQS, gruppi di cluster, limiti SQA | ricercatori |
| `config/worms_cache.json` | Risposte WoRMS salvate (generato) | nessuno |

Non vengono più letti: il vecchio `Campioni_P_2025_Data.xlsx` (tabella `ALL`, `Elenco specie*`, `Densità faunistica`,
`Shannon_H` e `ORDINE` della geochimica), `Raw_ForamsEcoQs.xlsx` e `lists_for_feqs/`.

## Operazioni frequenti

- **Aggiungere un campione**:
  1. con il workbook chiuso in Excel, eseguire `uv run foramqs add-sample MC_XX01 --gruppo G1`. Il gruppo è quello
     di `[cluster.groups]`; se non esiste viene creato;
  2. compilare a mano le conte nel nuovo foglio `MC_XX01` e la riga del campione in `Geochimica_campioni`;
  3. eseguire `uv run foramqs check`: finché mancano dati compaiono gli errori V26 (conte) e V27 (geochimica).

  Il campione si può anche aggiungere a mano: vedi [input_data/README.md](input_data/README.md).
- **Correggere un refuso**: aggiungere una riga a `config/name_corrections.csv` e rilanciare `check`.
- **Un nome non trovato o con suggerimento WoRMS** (codice T01): verificare su marinespecies.org e aggiungere
  `nome;AphiaID;motivo;fonte` a `config/taxon_aliases.csv`.
- **Non essere d'accordo con WoRMS su un sinonimo**: imporre l'AphiaID desiderato in `taxon_aliases.csv`.
- **Specie senza tratti** (R04): aggiungere la riga in `reference/species_traits.csv` (va bene anche un sinonimo).
- **Cambiare una soglia o le classi EQS**: modificare `config/pipeline.toml`.

## Codici delle segnalazioni

| Codice | Severità | Significato |
|---|---|---|
| V01-V05 | errore | Tabelle mancanti, posizioni/conte/deformati/guscio non validi |
| V07-V08 | avviso | Caselle duplicate, repliche mancanti o non consecutive |
| V09-V10 | avviso | Nomi con struttura anomala; non determinati senza guscio (scartati) |
| V11 | avviso | Stesso taxon con gusci diversi nei campioni (taxa senza tratti) |
| V12 | avviso | Nomi molto simili (possibili refusi) |
| V13 | errore | Riga con N°INDIVIDUI o DEFORMATI ma senza SPECIE (verrebbe scartata) |
| V20-V25 | errore/avviso | Geochimica: campioni, valori non numerici o censurati, granulometria ≠ 100%, righe copiate, colonne di config mancanti |
| V26 | errore | Tabella di un campione senza righe compilate |
| V27 | errore/avviso | Valore di geochimica mancante (errore se la colonna serve alla CCA) |
| V28 | errore | Campione ripetuto in più righe della geochimica |
| V29 | errore | Campione con righe compilate ma nessun foraminifero conteggiato |
| V30 | errore | Campione in `[input.copied_replicas]` inesistente o con più di una replica |
| T01-T04 | avviso/info | WoRMS: nome non risolto, alias applicato, sinonimo risolto, nomi uniti |
| T05 | avviso | Alias verso un AphiaID che per WoRMS è un sinonimo: il taxon resta separato da quello accettato |
| T06 | avviso | Il nome corrisponde a più taxa in WoRMS (omonimi): scelto il record accettato |
| R01-R04 | errore/avviso | Tratti: valore non ammesso o conflitto, righe in contrasto, taxa senza tratti |
| R05 | info | Guscio nei fogli diverso dalla tabella dei tratti: vale sempre quello dei tratti |
| C01 | errore/avviso | Gruppi di cluster: campioni sconosciuti o in più gruppi (errore), campioni senza gruppo (avviso) |
| C02 | avviso | Gruppo che non è un ramo del dendrogramma (solo in `run`, serve il cluster) |
| I01-I03 | info | Giovanili sommati a `Genere spp.`; righe senza N°INDIVIDUI (individui morti) non conteggiate; replica R1 copiata (`[input.copied_replicas]`) |

## Indici e metodi

- **ForamEcoQS** (`indices/foramecoqs.py`): S, exp(H'bc) (Chao–Shen), FSI, Foram-AMBI e classi EQS, portati dal
  sorgente C# con la stessa aritmetica (arrotondamenti .NET). Verificati sui vecchi risultati in `tests/legacy`.
- **PAST** (`indices/diversity.py`): i 16 indici del foglio `Indici_PAST` (Shannon con correzione di
  Miller–Madow, Simpson non distorto, Chao-1, iChao-1, ACE…), verificati sui valori di PAST.
- **Cluster**: UPGMA + Bray-Curtis sulle abbondanze relative. **CCA**: scikit-bio, sulle specie dominanti e sulle
  variabili ambientali standardizzate.

## Struttura del codice

```
src/foramqs/
  config.py, inputs.py, io_excel.py   lettura di configurazione e workbook
  validate.py                         controlli V.. sugli input
  clean.py                            normalizzazione e parsing dei nomi
  taxonomy.py                         WoRMS, alias, taxon_id
  traits.py, migrate.py               tabella dei tratti e sua migrazione
  tables.py                           abbondanze e tabelle di sintesi
  indices/                            ForamEcoQS e PAST
  multivariate.py, plots.py           cluster, CCA, grafici
  reconcile.py                        confronto con un vecchio Results
  new_sample.py                       aggiunta di un campione vuoto (comando add-sample)
  pipeline.py, cli.py, report.py      collegamento dei passi, comandi, scrittura Excel
```

Test: `uv run pytest` (`tests/unit` = regole e formule; `tests/legacy` = parità con i vecchi risultati).

## Licenza

MIT, vedi [LICENSE](LICENSE). Il calcolo degli indici ForamEcoQS è un port del codice di ForamEcoQS (MIT,
Mangiagalli et al. 2026): nota di copyright e citazione in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
