# input_data

Cartella dei workbook Excel. **Non è versionata** (`.gitignore`): dopo aver clonato la repo, copiare qui i file.

| File | Obbligatorio | Serve a |
|---|---|---|
| `Campioni_P_2025_Data.xlsx` | sì | input della pipeline (nome e percorso in `config/pipeline.toml`, voce `[paths] data_workbook`) |
| `Campioni_P_2025_Results.xlsx` | no | `foramqs diff` e test di parità con i vecchi risultati |
| `Raw_ForamsEcoQs.xlsx` | no | test di parità con ForamEcoQS |

Se i due file facoltativi mancano, i test in `tests/legacy` vengono saltati.

## Formato del workbook dei dati

La pipeline legge le **Tabelle Excel** (Inserisci → Tabella, ognuna con un nome), non i fogli: un intervallo di
celle che non è una Tabella viene ignorato. Tutto il resto del workbook (`ALL`, `Elenco specie`,
`Densità faunistica`, `specie_stilevita`, altri fogli) non viene letto.

### 1. Una Tabella per campione

Il modo più semplice per aggiungere un campione è `uv run foramqs add-sample <NOME> --gruppo <G>`: crea il foglio
con la Tabella vuota e la riga di geochimica, che vanno poi compilati a mano.

Il **nome della Tabella è il nome del campione** (es. `MC_VI01`); il nome del foglio non conta. Viene riconosciuta
come campione qualunque Tabella con esattamente queste 7 colonne, in quest'ordine:

| Colonna | Contenuto atteso |
|---|---|
| `REPLICA`, `N°SLIDE`, `CASELLA` | interi positivi; la stessa casella non deve comparire due volte |
| `SPECIE (LONG FORMAT)` | nome della specie, anche con autore. Sono riconosciuti: "sp."/"spp." (→ `Genere spp.`), i giovanili (→ `Genere spp.`), "Not determined" e "Specie anomala" (→ `ND <guscio>`), le voci di `config/non_foram_terms.csv` (diatomee, "No Forams": scartate) |
| `TIPO GUSCIO` | `A` (agglutinato), `I` (ialino), `P` (porcellanaceo) oppure vuoto |
| `N°INDIVIDUI` | intero ≥ 0. Se è vuoto la riga vale 0 e genera un avviso, a meno che il commento contenga "mort" (individuo morto) |
| `DEFORMATI` | intero ≥ 0, non maggiore di `N°INDIVIDUI` |

Facoltativa: una colonna `COMMENTI & DUBBI` **subito a destra** della Tabella, anche fuori dal suo intervallo. Viene
letta ed è lì che si annotano gli individui morti ("MORTA", "Morti"…).

### 2. La Tabella `Geochimica_campioni`

Una riga per campione. La prima colonna (`Colonna1`) contiene i nomi dei campioni, che devono coincidere
esattamente con i nomi delle Tabelle dei campioni.

I valori devono essere numerici. L'unico testo ammesso è un valore censurato dichiarato in
`config/pipeline.toml`, `[input.censored_values]` (es. `"> 200"`).

Le colonne citate per nome in `config/pipeline.toml` devono esistere, altrimenti la validazione dà l'errore V25:

| Colonna | Voce di config | Uso |
|---|---|---|
| `GRAVEL`, `SAND`, `SILT` | `input.grain_size_columns` | granulometria: la somma deve essere circa 100% |
| `DEPTH (m)`, `GRAVEL`, `SAND`, `SILT`, `TOC (%)`, `As`, `Cr`, `Hg`, `Ni` | `tables.past_geochemistry_columns` | tabella per PAST e variabili della CCA |
| `TOC (%)` | `tables.toc_column` | tabella `Specie&TOC` |
| `Mn`, `Fe`, `Co`, `Cd` | `tables.complete_table_excluded_columns` | escluse da `Tabella_completa` |
| `M-AMBI_ 2022` | `tables.external_index_column` | indice esterno della macrofauna (anche etichetta nei grafici) |
| `Hg`, `As`, `Cr` | `[sqa]` | confronto con gli standard di qualità |

Se una colonna viene rinominata nel file, va aggiornato il nome corrispondente in config.

Ogni altra colonna numerica (es. `Cu`, `Zn`, `Sn`, `Pb`) entra comunque nelle tabelle ambientali e negli z-score.

Le colonne `Shannon_H` e `ORDINE` vengono ignorate, perché ora sono calcolate dalla pipeline.

## Cosa non va qui

Tratti delle specie (`reference/species_traits.csv`), correzioni e alias di nome e parametri (`config/`) sono
versionati nella repo.
