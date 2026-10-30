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
| [X] | 26 | *Articulina mucronata* | gruppo ecologico | **1** (`Lista_Foram_AMBI.csv` di oggi) oppure **NA** (`specie_stilevita`) |
| [X] | 51 | *Connemarella rudis* | stile di vita | **Epifaunale** (*C. rudis*) oppure **ND** (sinonimo *Gaudryina rudis*) |
| [X] | 163 | *Quinqueloculina pulchella* | gruppo ecologico | **1** (*Adelosina pulchella*) oppure **2** (*Q. pulchella*) |
| [X] | 164 | *Quinqueloculina schlumbergeri* | gruppo ecologico | **2** (`specie_stilevita`) oppure **3** (sinonimo *Q. stelligera*, lista di oggi) |
| [X] | 168 | *Quinqueloculina variolata* | gruppo ecologico | **1** (sinonimo *Lachlanella variolata*, lista di oggi) oppure **2** (`specie_stilevita`) |
| [X] | 190 | *Sigmoilina grata* | gruppo ecologico | **1** (sinonimo *Miliolinella grata*, lista di oggi) oppure **NA** (`specie_stilevita`) |

In quattro casi la lista preparata oggi per ForamEcoQS ha ereditato il gruppo dal sinonimo che è stato fuso. Va
quindi stabilito quale attribuzione è corretta per il taxon valido.

Il conflitto alla riga 163 dipende dalla decisione 2.1.

## 2. Scelte metodologiche: hanno già un valore predefinito, va confermato o cambiato

- [X] **2.1 *Adelosina pulchella*.** La pipeline la risolve in *Quinqueloculina pulchella*, mentre la correzione di
  oggi l'ha fusa in *A. schreibersii*.
  - In WoRMS esistono due *Adelosina pulchella*: quella di d'Orbigny 1826 (→ *Q. pulchella*) e quella di
    d'Orbigny 1846 (sinonimo junior di *A. schreibersii*, AphiaID 737244). Nel file dati l'autore è
    **d'Orbigny, 1846**, quindi WoRMS conferma la scelta di oggi. La pipeline non distingue per autore (vedi 2.6).
  - Per tenere la scelta di oggi: aggiungere `Adelosina pulchella;737244;…` a `config/taxon_aliases.csv`. In quel
    caso anche il conflitto della riga 163 sparisce.
- [X] **2.2 Soglie 5% e 3%** (`threshold_mode` in `config/pipeline.toml`).
  - Predefinito `"cella"`, il metodo di Power Query: un valore sotto soglia viene azzerato in quel campione.
  - Alternativa `"specie"`: si tengono tutti i valori delle specie che superano la soglia in almeno un campione. È la
    pratica più comune per cluster e CCA.
- [X] **2.3 Classi EQS di exp(H'bc)** (`[eqs]` in `config/pipeline.toml`).
  - Predefinito: soglia norvegese per la frazione 63 µm (≥22 High), quella di ForamEcoQS.
  - Alternativa: soglia italiana 63 µm (≥5 High).
  - Cambia molto la classificazione: va scelta in base alla normativa e alla frazione granulometrica usata.
- [x] **2.4 Non determinati senza guscio** ("Specie anomala" e "Not determined" senza tipo di guscio).
  - **Deciso: vengono scartati**, come faceva Power Query. Non entrano in N, S, densità e indici; restano nel
    `Log_pulizia` e sono segnalati con V10. Se il guscio è noto, basta indicarlo nel file Excel per conteggiarli come
    `ND A/I/P`.
  - Riguarda 4 individui in MC_PN01, più alcune righe con conteggio 0.
  - Nota: i non determinati con guscio (`ND A/I/P`), come in ForamEcoQS, entrano nel denominatore di Foram-AMBI e
    pesano come il gruppo I; dall'FSI invece sono esclusi.
- [x] **2.5 Gruppi di cluster** (`[cluster.groups]` in `config/pipeline.toml`, codice C02).
  - Il vecchio G3 non era un ramo del dendrogramma UPGMA + Bray-Curtis: PN01 e PN02 (il vecchio G2) cadevano al suo
    interno.
  - **Deciso: gruppi presi dal dendrogramma, con un taglio in 3 rami:**
    - G1: FL01, FO02, FO01, VI01, ML01, FL02, ML02, VI02 (invariato);
    - G2: CB01, CE01;
    - G3: CB02, PP01, PP02, PN01, PN02, SV01, CE02, SV02.
  - Nel ramo di G2 e G3 le unioni avvengono a distanze vicine tra loro (0.61-0.73): la suddivisione interna è poco
    netta. Se i dati cambiano (nuovi campioni, correzioni), rilanciare `run` e controllare l'avviso C02.

- [x] **2.6 Omonimi distinguibili solo dall'autore** (codice T06).
  - **Deciso:** per ogni nome vale un solo taxon, qualunque sia l'autore scritto nel file. Le scelte sono in
    `config/taxon_aliases.csv`:

    | Nome | Taxon scelto | AphiaID |
    |---|---|---|
    | *Valvulineria minuta* | Parker, 1954 | 911325 |
    | *Spiroloculina angulosa* | Terquem, 1878 | 112711 |
    | *Buccella granulata* | (di Napoli Alliata, 1952) | 113137 |
    | *Triloculina elongata* | d'Orbigny in Fornasini, 1905 | 889592 |

  - Gli autori diversi nel file dati sono quindi refusi (vedi la sezione 3). Gli altri tre avvisi T06
    (*Articulina carinata*, *Quinqueloculina pulchella*, *Pseudotriloculina*) indicano già il taxon accettato,
    coerente con l'autore nel file.

## 3. Verifiche sui dati: non sono scelte, ma controlli da fare nel file Excel

Il file è `input_data/Campioni_P_2025_Data_Raw.xlsx` (le correzioni fatte prima del 2026-10-30 alle 17:44 sono state
applicate al vecchio `Campioni_P_2025_Data.xlsx` e copiate nel nuovo file).

| Fatto | Codice | Cosa | Quanti |
|---|---|---|---|
| [x] | R05 | Guscio nel foglio diverso dalla tabella dei tratti, quasi sempre una "I" isolata tra molte "P". **Deciso: vale sempre il guscio di `species_traits.csv`**; R05 è ora solo una nota informativa, una per specie | 79 righe |
| [x] | V06 | Specie senza conteggio e senza commento. **Deciso: una riga senza conteggio è sempre un individuo morto** (o un frammento), non conteggiato; il commento non serve più. L'avviso V06 non esiste più, le righe sono elencate nella nota I02 | 5 righe |
| [x] | V08 | MC_FO02 ha una sola replica: R2 e R3 mancano o sono andate perse? **Deciso: si suppongono tre repliche identiche** (`[input.copied_replicas]` in `config/pipeline.toml`): R1 è contata tre volte, quindi N triplica (182 → 546). Densità, abbondanze relative, S, FSI e Foram-AMBI non cambiano; cambiano gli indici basati sulle specie rare (exp(H'bc) 11.51 → 10.81, Chao-1 21 → 19, α di Fisher 5.34 → 3.82) | 1 campione |
| [x] | V07 | Stessa casella usata due volte (MC_CE02, replica 3, slide 3, casella 28). **Corretto nel file:** riga 283 (*Massilina gualtieriana*) spostata alla casella 29 | 1 caso |
| [x] | T01 | *Elphidium aculeatum* ed *E. granosum* non risultano dalla ricerca per nome in WoRMS. **Causa:** WoRMS li segna come estinti e la ricerca per nome restituisce solo i taxa viventi. **Fatto:** alias in `config/taxon_aliases.csv`, *E. aculeatum* 113253 ed *E. granosum* 113269 | 2 nomi |
| [x] | — | **Corretto nel file** (backup in `input_data/backup/`). Autore sbagliato (non cambia i calcoli, solo la coerenza del dato): *Valvulineria minuta* "(Schubert, 1904)" → Parker, 1954; *Spiroloculina angulosa* "d'Orbigny in Fornasini, 1904" → Terquem, 1878; *Buccella granulata* "(Cushman, 1922)" → (di Napoli Alliata, 1952) | 6 righe |
| [ ] | — | Stagno in MC_CB01: il "> 200" è già stato sostituito con 201 nel file dati, quindi la pipeline non può riconoscerlo come valore censurato. Decidere se lasciarlo così o riportare "> 200" e gestirlo con `[input.censored_values]` | 1 valore |
