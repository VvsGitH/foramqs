# Decisioni da prendere

Stato al 2026-10-30. Il dettaglio riga per riga delle segnalazioni si ottiene con `uv run foramqs check`: produce
`output/check_<data>.xlsx`, con il foglio `Validazione` filtrabile per codice. Le alternative di ogni conflitto di
tratti sono anche in `output/migrazione_tratti_<data>.xlsx`.

Una volta presa una decisione, spuntare la casella e rilanciare `uv run foramqs check`.

## 1. Bloccanti: senza queste `foramqs run` non calcola nulla

Sono 6 conflitti nei tratti delle specie (codice R01). Si risolvono in `reference/species_traits.csv`, sostituendo
la cella "CONFLITTO: …" con il valore scelto.

| Fatto | Riga CSV | Specie | Tratto | Alternative (da quale nome/fonte vengono) |
|---|---|---|---|---|
| [ ] | 26 | *Articulina mucronata* | gruppo ecologico | **1** (`Lista_Foram_AMBI.csv` di oggi) oppure **NA** (`specie_stilevita`) |
| [ ] | 51 | *Connemarella rudis* | stile di vita | **Epifaunale** (*C. rudis*) oppure **ND** (sinonimo *Gaudryina rudis*) |
| [ ] | 163 | *Quinqueloculina pulchella* | gruppo ecologico | **1** (*Adelosina pulchella*) oppure **2** (*Q. pulchella*) |
| [ ] | 164 | *Quinqueloculina schlumbergeri* | gruppo ecologico | **2** (`specie_stilevita`) oppure **3** (sinonimo *Q. stelligera*, lista di oggi) |
| [ ] | 168 | *Quinqueloculina variolata* | gruppo ecologico | **1** (sinonimo *Lachlanella variolata*, lista di oggi) oppure **2** (`specie_stilevita`) |
| [ ] | 190 | *Sigmoilina grata* | gruppo ecologico | **1** (sinonimo *Miliolinella grata*, lista di oggi) oppure **NA** (`specie_stilevita`) |

In quattro casi la lista preparata oggi per ForamEcoQS ha ereditato il gruppo dal sinonimo che è stato fuso. Va
quindi stabilito quale attribuzione è corretta per il taxon valido.

Il conflitto alla riga 163 dipende dalla decisione 2.1.

## 2. Scelte metodologiche: hanno già un valore predefinito, va confermato o cambiato

- [ ] **2.1 *Adelosina pulchella*.** Per WoRMS è *Quinqueloculina pulchella*, mentre la correzione di oggi l'ha fusa in
  *A. schreibersii*.
  - Se si segue WoRMS non serve fare nulla.
  - Se si tiene la scelta di oggi, aggiungere una riga in `config/taxon_aliases.csv` con l'AphiaID di
    *A. schreibersii*. In quel caso anche il conflitto della riga 163 sparisce.
- [ ] **2.2 Soglie 5% e 3%** (`threshold_mode` in `config/pipeline.toml`).
  - Predefinito `"cella"`, il metodo di Power Query: un valore sotto soglia viene azzerato in quel campione.
  - Alternativa `"specie"`: si tengono tutti i valori delle specie che superano la soglia in almeno un campione. È la
    pratica più comune per cluster e CCA.
- [ ] **2.3 Classi EQS di exp(H'bc)** (`[eqs]` in `config/pipeline.toml`).
  - Predefinito: soglia norvegese per la frazione 63 µm (≥22 High), quella di ForamEcoQS.
  - Alternativa: soglia italiana 63 µm (≥5 High).
  - Cambia molto la classificazione: va scelta in base alla normativa e alla frazione granulometrica usata.
- [ ] **2.4 Non determinati senza guscio** ("Specie anomala" e "Not determined" senza tipo di guscio).
  - Ora contano come taxon `ND`, quindi entrano in N, S e densità. Power Query li scartava.
  - Riguarda 4 individui in MC_PN01, più alcune righe con conteggio 0.
- [ ] **2.5 Gruppo di cluster G3** (`[cluster.groups]` in `config/pipeline.toml`, codice C02).
  - G1 e G2 corrispondono a rami del dendrogramma UPGMA + Bray-Curtis, G3 no: PN01 e PN02 cadono dentro il gruppo
    costiero.
  - Si può tenere G3 come raggruppamento interpretativo (resta un avviso) oppure ridefinire i gruppi.

## 3. Verifiche sui dati: non sono scelte, ma controlli da fare nel file Excel

Il file è `input_data/Campioni_P_2025_Data.xlsx`.

| Fatto | Codice | Cosa | Quanti |
|---|---|---|---|
| [ ] | R05 | Guscio nel foglio diverso dalla tabella dei tratti, quasi sempre una "I" isolata tra molte "P" | 79 righe |
| [ ] | V06 | Specie senza conteggio e senza commento: conteggio dimenticato, oppure individuo morto da annotare in "COMMENTI & DUBBI" | 8 righe |
| [ ] | V08 | MC_FO02 ha una sola replica: R2 e R3 mancano o sono andate perse? | 1 campione |
| [ ] | V07 | Stessa casella usata due volte (MC_CE02, replica 3, slide 3, casella 28) | 1 caso |
| [ ] | T01 | *Elphidium aculeatum* ed *E. granosum* non sono in WoRMS: verificare il nome o imporre un AphiaID in `config/taxon_aliases.csv` | 2 nomi |
| [ ] | — | Stagno in MC_CB01: il "> 200" è già stato sostituito con 201 nel file dati, quindi la pipeline non può riconoscerlo come valore censurato. Decidere se lasciarlo così o riportare "> 200" e gestirlo con `[input.censored_values]` | 1 valore |
