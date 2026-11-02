# input_data

Cartella dei workbook Excel. **Non è versionata** (`.gitignore`): dopo aver clonato la repo, copiare qui i file.

| File | Obbligatorio | Serve a |
|---|---|---|
| `Campioni_P_2025_Data_Raw.xlsx` | sì | **fonte primaria**, input della pipeline (percorso in `config/pipeline.toml`, voce `[paths] data_workbook`). Contiene solo le Tabelle dei campioni e della geochimica: niente Power Query, fogli derivati o tabelle tecniche |
| `Campioni_P_2025_Data.xlsx` | no | vecchio workbook con Power Query: storico. Serve solo a `foramqs migrate-traits` (già eseguito) e ai test in `tests/legacy` |
| `Campioni_P_2025_Results.xlsx` | no | `foramqs diff` e test di parità con i vecchi risultati |
| `Raw_ForamsEcoQs.xlsx` | no | test di parità con ForamEcoQS |
| `backup/` | no | copie automatiche fatte da `add-sample` prima di modificare il workbook |

Se i file facoltativi mancano, i test in `tests/legacy` vengono saltati.

Il file `_Raw` è stato creato il 2026-10-30 copiando i valori dal vecchio workbook (dopo le correzioni di quel giorno):
stesse righe nelle stesse posizioni, stessi commenti; la geochimica senza le colonne calcolate `Shannon_H` e
`ORDINE` e con le intestazioni senza spazi ai bordi. La pipeline produce da entrambi gli stessi risultati. Le
correzioni ai dati si fanno **solo nel file `_Raw`**.

## Formato del workbook dei dati

La pipeline legge le **Tabelle Excel** (Inserisci → Tabella, ognuna con un nome), non i fogli: un intervallo di
celle che non è una Tabella viene ignorato, e lo stesso vale per eventuali altri fogli.

### 1. Una Tabella per campione

Il modo più semplice per aggiungere un campione è `uv run foramqs add-sample <NOME> --gruppo <G>`: crea il foglio
con la Tabella vuota e la riga di geochimica, che vanno poi compilati a mano.

Il **nome della Tabella è il nome del campione** (es. `MC_VI01`); il nome del foglio non conta. Viene riconosciuta
come campione qualunque Tabella con esattamente queste 7 colonne, in quest'ordine:

| Colonna | Contenuto atteso |
|---|---|
| `REPLICA`, `N°SLIDE`, `CASELLA` | interi positivi; la stessa casella non deve comparire due volte. Un campione con la sola R1 può essere trattato come N repliche identiche dichiarandolo in `config/pipeline.toml`, `[input.copied_replicas]` (oggi MC_FO02 = 3) |
| `SPECIE (LONG FORMAT)` | nome della specie, anche con autore. Sono riconosciuti: "sp."/"spp." (→ `Genere spp.`), i giovanili (→ `Genere spp.`), "Not determined" e "Specie anomala" (→ `ND <guscio>`; senza TIPO GUSCIO sono scartati e segnalati con V10), le voci di `config/non_foram_terms.csv` (diatomee, "No Forams": scartate) |
| `TIPO GUSCIO` | `A` (agglutinato), `I` (ialino), `P` (porcellanaceo) oppure vuoto. Conta solo per i non determinati: per le specie vale il guscio di `reference/species_traits.csv` |
| `N°INDIVIDUI` | intero ≥ 0. Vuoto = individuo morto (o frammento): la riga è registrata ma non conteggiata (nota I02) |
| `DEFORMATI` | intero ≥ 0, non maggiore di `N°INDIVIDUI` |

Una cella con soli spazi vale come vuota. Una riga con N°INDIVIDUI ma senza SPECIE è un errore (V13), e lo è anche
un campione che non ha nessun individuo conteggiato (V29).

Facoltativa: una colonna `COMMENTI & DUBBI` **subito a destra** della Tabella, anche fuori dal suo intervallo. Viene
letta e i commenti delle righe senza conteggio compaiono nella nota I02.

### 2. La Tabella `Geochimica_campioni`

Una riga per campione, senza ripetizioni (V28). La prima colonna (`Colonna1`) contiene i nomi dei campioni, che devono coincidere
esattamente con i nomi delle Tabelle dei campioni.

I valori devono essere numerici. L'unico testo ammesso è un valore censurato dichiarato in
`config/pipeline.toml`, `[input.censored_values]` (es. `"> 200"`).

Le colonne citate per nome in `config/pipeline.toml` devono esistere, altrimenti la validazione dà l'errore V25:

| Colonna | Voce di config | Uso |
|---|---|---|
| `GRAVEL`, `SAND`, `SILT` | `input.grain_size_columns` | granulometria: la somma deve essere circa 100% |
| `M-AMBI_ 2022` | `tables.external_index_column` | indice esterno della macrofauna (foglio `Abbondanza_rel%_gruppiecologici`) |

Se una colonna viene rinominata nel file, va aggiornato il nome corrispondente in config.

Tutte le colonne numeriche entrano in `Tabella_matrice` e nelle tabelle per la CCA (`Tabella_CCA_*`): un valore mancante è quindi un errore (V27).

Le colonne `Shannon_H` e `ORDINE` vengono ignorate, perché ora sono calcolate dalla pipeline.

## Cosa non va qui

Tratti delle specie (`reference/species_traits.csv`), correzioni e alias di nome e parametri (`config/`) sono
versionati nella repo.
