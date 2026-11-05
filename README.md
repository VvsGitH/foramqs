# foramqs: elaborazione dei campioni di foraminiferi bentonici

Pipeline unica che sostituisce Power Query, ForamEcoQS e i passaggi manuali in PAST. Parte **solo** dai dati
grezzi (le tabelle `MC_*` e la geochimica di `input_data/Campioni_P_2025_Data_Raw.xlsx`) e da poche tabelle tecniche non
derivabili, e produce un `Results_<data>.xlsx` con dieci fogli di risultati (vedi [Fogli dei risultati](#fogli-dei-risultati))
più i report di controllo. I due dendrogrammi della Cluster Analysis (Q-mode e R-mode) sono immagini nel foglio `CA`.

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
| `uv run foramqs run` | Pipeline completa → `output/Results_<data>.xlsx` (i dieci fogli dei risultati) e i dendrogrammi `output/figures_<data>/dendrogramma_Q_mode.png`, `dendrogramma_R_mode.png`. Se ci sono errori negli input si ferma e li elenca. |
| `uv run foramqs diff input_data/Campioni_P_2025_Results.xlsx` | Confronta gli indici con un vecchio Results ed elenca, per campione, i cambiamenti che spiegano le differenze. |
| `uv run foramqs add-sample MC_XX01 --gruppo G1` | Aggiunge un campione vuoto da compilare a mano: foglio con la Tabella delle conte, riga in `Geochimica_campioni`, campione nel gruppo di cluster indicato. Fa prima un backup del workbook in `input_data/backup/`. |
| `uv run foramqs migrate-traits` | Crea `reference/species_traits.csv` dalle fonti storiche. **Già eseguito**: da qui in poi la tabella dei tratti si modifica a mano. |

Con `--offline` WoRMS non viene interrogato e si usa solo la cache (`config/worms_cache.json`).

## Dati in ingresso

| File | Contenuto | Chi lo modifica |
|---|---|---|
| `input_data/Campioni_P_2025_Data_Raw.xlsx` | Tabelle `MC_*` (conte per casella), colonna `COMMENTI & DUBBI` accanto, tabella `Geochimica_campioni` | laboratorio |
| `reference/species_traits.csv` | Tratti per taxon: stile di vita, gruppo ecologico Foram-AMBI (1-5/NA), gruppo FSI (Sen/Str/ND), guscio (A/I/P) | ricercatori |
| `reference/foram_ambi_alt.csv` | Assegnazione alternativa ai gruppi ecologici Foram-AMBI per campioni specifici (`nome;gruppo_ecologico`): oggi solo controllata da `check` (A01–A05), il Foram-AMBI alternativo non è più calcolato | ricercatori |
| `config/name_corrections.csv` | Refusi da correggere nel testo (`trova;sostituisci;motivo;fonte`) | ricercatori |
| `config/taxon_aliases.csv` | AphiaID imposto per un nome, con precedenza su WoRMS (`nome;aphia_id;motivo;fonte`) | ricercatori |
| `config/non_foram_terms.csv` | Voci da scartare (diatomee, "No Forams"…) | ricercatori |
| `config/pipeline.toml` | Percorsi, soglie, volume delle repliche, classi EQS, gruppi di cluster | ricercatori |
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
| V27 | errore | Valore di geochimica mancante (tutte le colonne servono alle tabelle per la CCA) |
| V28 | errore | Campione ripetuto in più righe della geochimica |
| V29 | errore | Campione con righe compilate ma nessun foraminifero conteggiato |
| V30 | errore | Campione in `[input.copied_replicas]` inesistente o con più di una replica |
| T01-T04 | avviso/info | WoRMS: nome non risolto, alias applicato, sinonimo risolto, nomi uniti |
| T05 | avviso | Alias verso un AphiaID che per WoRMS è un sinonimo: il taxon resta separato da quello accettato |
| T06 | avviso | Il nome corrisponde a più taxa in WoRMS (omonimi): scelto il record accettato |
| R01-R04 | errore/avviso | Tratti: valore non ammesso o conflitto, righe in contrasto, taxa senza tratti |
| R05 | info | Guscio nei fogli diverso dalla tabella dei tratti: vale sempre quello dei tratti |
| C01 | errore/avviso | Gruppi di cluster: campioni sconosciuti o in più gruppi (errore), campioni senza gruppo (avviso) |
| C02 | avviso | Gruppo che non è un ramo del dendrogramma Q-mode (solo in `run`, serve il cluster) |
| A01-A05 | errore | Foram-AMBI alternativo: campioni sconosciuti, file non trovato, valori non ammessi, conflitti o nome del foglio non valido per Excel |
| I01-I03 | info | Giovanili sommati a `Genere spp.`; righe senza N°INDIVIDUI (individui morti) non conteggiate; replica R1 copiata (`[input.copied_replicas]`) |

## Indici e metodi

- **ForamEcoQS** (`indices/foramecoqs.py`): S, exp(H'bc) (Chao–Shen), FSI, Foram-AMBI e classi EQS, portati dal
  sorgente C# con la stessa aritmetica (arrotondamenti .NET). Verificati sui vecchi risultati in `tests/legacy`.
  Il Foram-AMBI è calcolato in due modi: `Foram-AMBI ori` come ForamEcoQS (gli individui senza gruppo ecologico
  restano al denominatore e pesano come GI) e `Foram-AMBI` con gli NA ridistribuiti nei gruppi assegnati, in
  proporzione; la classe `EQS Foram-AMBI` si riferisce a quest'ultimo.
- **PAST** (`indices/diversity.py`): i 16 indici del foglio `Indici_PAST` (Shannon con correzione di
  Miller–Madow, Simpson non distorto, Chao-1, iChao-1, ACE…), verificati sui valori di PAST.
- **Cluster Analysis** (foglio `CA`): metodo di Ward, distanza euclidea (`[cluster]`), sulle specie dominanti
  trasformate con log₁₀(1+x). Q-mode sui campioni, R-mode sulle specie. L'ordine delle foglie del Q-mode è l'ordine
  dei campioni in tutti i fogli.
- **PCA/CCA**: non sono calcolate dalla pipeline, si fanno in PAST sul foglio `PCA_CCA`.

## Fogli dei risultati

| Foglio | Righe × colonne | Contenuto |
|---|---|---|
| `Abb_assolute` | specie × campioni | individui per specie |
| `Abb_rel%` | specie × campioni | abbondanze relative (%) di tutte le specie |
| `Abb_rel_5%` | specie × campioni | specie con abbondanza ≥ `tables.dominant_species_threshold` (5%) in almeno un campione, con tutti i loro valori (%) |
| `Indici_PAST` | indici × campioni | i 16 indici di PAST |
| `Exp(H'bc)` | indici × campioni | exp(H'bc), exp(H'bc) EQR (= exp(H'bc) / massimo tra i campioni), EQS exp(H'bc) EQR |
| `FSI` | indici × campioni | % Sen, % Str (sul totale Sen + Str), FSI, EQS FSI |
| `Foram-AMBI` | indici × campioni | % GE1–GE5 e % NA (sul totale degli individui), Foram-AMBI ori, Foram-AMBI, EQS Foram-AMBI |
| `Altre_info` | parametri × campioni | densità faunistica media, % per tipo di guscio, % per stile di vita, % deformati |
| `CA` | campioni × specie | log₁₀(1+x) di `Abb_rel_5%`, scritto come formule Excel `=LOG10(1+'Abb_rel_5%'!…)`; dendrogrammi Q-mode e R-mode |
| `PCA_CCA` | campioni × parametri | log₁₀(1+x) di specie di `Abb_rel_5%`, `tables.pca_cca_environment` (profondità, granulometria, TOC, metalli), S, exp(H'bc), FSI, Foram-AMBI |

Seguono i fogli dei controlli: `Validazione`, `Log_pulizia`, `Revisione_nomi`, `Osservazioni`.
Il nome del foglio delle specie dominanti segue la soglia (`Abb_rel_<soglia>%`). Le formule del foglio `CA` sono
calcolate da Excel all'apertura del file.

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
  multivariate.py                     Cluster Analysis (Q-mode e R-mode)
  charts.py, plots.py                 grafici Excel (oggi non usati dalla pipeline); dendrogrammi
  reconcile.py                        confronto con un vecchio Results
  new_sample.py                       aggiunta di un campione vuoto (comando add-sample)
  pipeline.py, cli.py, report.py      collegamento dei passi, comandi, scrittura Excel
```

Test: `uv run pytest` (`tests/unit` = regole e formule; `tests/legacy` = parità con i vecchi risultati).

## Licenza

MIT, vedi [LICENSE](LICENSE). Il calcolo degli indici ForamEcoQS è un port del codice di ForamEcoQS (MIT,
Mangiagalli et al. 2026): nota di copyright e citazione in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
