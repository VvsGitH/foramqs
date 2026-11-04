# CONTEXT: foramqs — Elaborazione Dati e Statistica per Foraminiferi Bentonici

Questo documento fornisce il contesto scientifico, architetturale e metodologico del progetto `foramqs`. Serve come memoria permanente del progetto per orientare lo sviluppo futuro, la manutenzione del codice, la stesura della tesi di dottorato e la preparazione di pubblicazioni scientifiche.

---

## 1. Visione del Progetto e Obiettivi Scientifici

- **Ricercatrice / Utente**: Dottoranda di ricerca in scienze ambientali / paleontologia / biologia marina.
- **Oggetto di studio**: Comunità di **foraminiferi bentonici viventi** (marini e/o di ambienti costieri/transizionali) utilizzati come bioindicatori della qualità ecologica e dello stress ambientale.
- **Scopo di `foramqs`**:
  Sostituire un workflow legacy frammentato e incline a errori umani (che combinava fogli Excel con Power Query complessi, il software standalone C# *ForamEcoQS* e calcoli manuali in *PAST*).
  La pipeline riceve in input esclusivamente i dati grezzi di laboratorio (conteggi per casella e parametri ambientali/geochimici) e genera in modo deterministico e tracciabile un report Excel completo (`Results_<timestamp>.xlsx`), corredato di grafici nativi modificabili, dendrogramma cluster e tabelle formattate per la Canonical Correspondence Analysis (CCA).

---

## 2. Architettura del Software e Stack Tecnologico

- **Linguaggio & Runtime**: Python `>=3.12` (sviluppato con Python 3.12).
- **Package & Environment Manager**: [uv](https://docs.astral.sh/uv/) (Astral), con supporto multipiattaforma (Windows / macOS / Linux).
- **Dipendenze principali**:
  - `pandas` (>=3.1.0) & `numpy` (>=2.5.4): Elaborazione matriciale e manipolazione tabellare.
  - `openpyxl` (>=3.1.5): Lettura delle tabelle Excel native e generazione avanzata di cartelle di lavoro con filtri, blocco riquadri, colonne proporzionali e grafici nativi collegati alle celle.
  - `scipy` (>=1.18.1): Ottimizzazioni numeriche, funzioni speciali (`gammaln`, `brentq`), calcolo distanze (`braycurtis`) e linkage gerarchico (`UPGMA`).
  - `matplotlib` (>=3.11.2): Generazione del dendrogramma cluster vettoriale esportato in PNG ad alta risoluzione (150 dpi).
  - `typer` (>=0.27.3): Interfaccia da riga di comando (CLI).
  - `requests` (>=2.34.2): Chiamate REST alle API tassonomiche di WoRMS (*World Register of Marine Species*).
  - `tomlkit` (>=0.15.2): Modifica preservando commenti e formattazione del file di configurazione `pipeline.toml`.
  - `pytest` (>=9.2.0): Suite di test unitari e di regressione storica (legacy).

### Moduli del Pacchetto (`src/foramqs/`)

```
src/foramqs/
├── __init__.py           # Versione del pacchetto
├── cli.py                # Comandi Typer: check, run, diff, add-sample, migrate-traits
├── config.py             # Caricamento e risoluzione percorsi di config/pipeline.toml
├── inputs.py             # Caricamento dati grezzi e geochimica
├── io_excel.py           # Lettura e binding tabelle Excel (oggetti ListObject / Table)
├── clean.py              # Parsing, sanitizzazione testo, gestione 'spp.', giovanili e ND
├── taxonomy.py           # Integrazione WoRMS REST API, cache locale, gestione sinonimi e omonimi
├── traits.py             # Gestione reference/species_traits.csv (stili di vita, gruppi ecologici, guscio)
├── tables.py             # Matrici di abbondanza assoluta, relativa, tagli percentuali, z-score
├── multivariate.py       # Cluster UPGMA + Bray-Curtis, validazione coerenza rami/gruppi
├── charts.py             # Generazione grafici nativi Excel (openpyxl BarChart/LineChart) con soglie EQS
├── plots.py              # Generazione figura Matplotlib del dendrogramma
├── report.py             # Scrittura workbook finale Excel (auto-fit, freeze-panes, filtri)
├── new_sample.py         # Scaffold protetto di un nuovo campione con backup automatico
├── reconcile.py          # Comparatore con risultati storici e tracciamento scostamenti
├── csharp_compat.py      # Funzioni di arrotondamento (.NET MidpointRounding) e sommatorie C#
└── indices/
    ├── diversity.py      # Indici di diversità e ricchezza compatibili PAST (16 indici)
    └── foramecoqs.py     # Port C# di ForamEcoQS (S, exp(H'bc), FSI, Foram-AMBI, classi EQS)
```

---

## 3. Flusso Dati e Fonti di Input

### Fonti Primarie (in `input_data/` e `reference/`)

1. **`input_data/Campioni_P_2025_Data_Raw.xlsx`** (fonte primaria dei dati):
   - Una **Tabella Excel** per ogni campione (il nome della tabella corrisponde all'identificativo del campione, es. `MC_VI01`). Colonne fisse obbligatorie:
     1. `REPLICA` (intero ≥ 1)
     2. `N°SLIDE` (intero ≥ 1)
     3. `CASELLA` (intero ≥ 1; non duplicabile all'interno della stessa replica/slide)
     4. `SPECIE (LONG FORMAT)` (nome con autore o annotazioni tassonomiche)
     5. `TIPO GUSCIO` (`A` = Agglutinato, `I` = Ialino, `P` = Porcellanaceo, o vuoto)
     6. `N°INDIVIDUI` (intero ≥ 0; cella vuota = individuo morto/guscio vuoto, non conteggiato)
     7. `DEFORMATI` (intero ≥ 0; $\le$ individui)
   - Colonna facoltativa a destra: `COMMENTI & DUBBI` (tracciata nei log e associata alle righe).
   - Tabella **`Geochimica_campioni`**:
     - Colonna identificativa: `Colonna1` (nomi dei campioni corrispondenti alle tabelle di conteggio).
     - Parametri granulometrici (`GRAVEL`, `SAND`, `SILT`), con controllo della somma a 100% $\pm$ 1%.
     - Parametri geochimici e ambientali continui (metalli, TOC, nutrienti, indici esterni come `M-AMBI_ 2022`).
     - Gestione valori censurati configurabile (es. `"> 200"` $\to$ `201`).

2. **`reference/species_traits.csv`** (reference tassonomico e funzionale):
   - Colonne: `nome;stile_di_vita;gruppo_ecologico;gruppo_fsi;guscio;fonte;note`
   - *Stili di vita ammessi*: `Epifaunale`, `Epifita`, `Infaunale superficiale`, `Infaunale profondo`, `ND`.
   - *Gruppi ecologici Foram-AMBI*: `1`, `2`, `3`, `4`, `5`, `NA`.
   - *Gruppi FSI*: `Sen` (Sensibile), `Str` (Stress tollerante), `ND` (Non Determinato).
   - *Tipo guscio*: `A`, `I`, `P`.
   - **Regola cardine**: Il tipo di guscio per le specie determinate deriva sempre da questa tabella, correggendo eventuali refusi di battitura nel foglio del campione (segnalati con nota informativa R05). Per i non determinati (`ND`), fa fede il guscio inserito nel foglio.

3. **File di configurazione (`config/`)**:
   - `pipeline.toml`: parametri di sistema, soglie dominanza, volume replica, gruppi cluster, regole EQS.
   - `name_corrections.csv`: correzione ortografica a monte (es. refusi di genere o autori uniti).
   - `taxon_aliases.csv`: override tassonomico esplicito (forzatura di AphiaID rispetto a WoRMS per separare o selezionare omonimi).
   - `non_foram_terms.csv`: termini non foraminiferi scartati (diatomee, frammenti, "No Forams").
   - `worms_cache.json`: cache locale JSON delle chiamate API a marinespecies.org (permette riproducibilità totale e funzionamento offline con `--offline`).

---

## 4. Metodologie Statistiche ed Ecologiche Implementate

### A. Tassonomia e Normalizzazione WoRMS
- I nomi vengono puliti separando Genere, Epiteto, Autore e qualificatori.
- Forme come `sp.` o `spp.` e giovanili (es. *Quinqueloculina Juvenile*) vengono ricondotti a `Genere spp.`.
- Gli esemplari non determinabili senza tipo di guscio vengono scartati e segnalati (V10). Se hanno il guscio (`ND A`, `ND I`, `ND P`), entrano nel conteggio come entità distinte.
- Attraverso WoRMS REST API, ogni nome ottiene un `taxon_id` (AphiaID standard o AphiaID Genere + `spp.`). Sinonimi biologici o ortografici convergono sullo stesso `taxon_id` e vengono automaticamente sommati.

### B. Indici di Qualità Ecologica (ForamEcoQS)
Porting matematico dal codice C# originale (*Mangiagalli et al. 2026, SoftwareX*):
1. **Ricchezza Specifica ($S$)**: Numero di taxa vivi con abbondanza $>0$.
2. **Abbondanza Totale ($N$)**: Somma degli individui vivi.
3. **Entropia di Chao-Shen corretta per la copertura ($H'_{bc}$)** e suo esponenziale $\exp(H'_{bc})$:
   - Copertura campionaria: $C = 1 - f_1 / N$ (dove $f_1$ è il numero di singletons). Se $C = 0 \implies C = 0.001$.
   - Arrotondamenti secondo aritmetica C#/.NET a 4 decimali.
4. **Foram Stress Index ($FSI$, Dimiza et al. 2016)**:
   $$FSI = \frac{10 \cdot \%Sen + \%Str}{\%Sen + \%Str}$$
   Calcolato esclusivamente sui taxa assegnati a `Sen` o `Str` (ND e non assegnati sono esclusi dal denominatore).
5. **Foram-AMBI (Alve et al. 2016, Jorissen et al. 2018)**:
   $$Foram\text{-}AMBI = \frac{\sum (W_g \cdot \%EG_g)}{100}$$
   Pesi: $EG_1 = 0.0, EG_2 = 1.5, EG_3 = 3.0, EG_4 = 4.5, EG_5 = 6.0$.
   *Importante*: con `[foram_ambi].redistribute_unassigned = true` (impostazione attuale) gli individui senza gruppo (NA, compresi gli ND) sono ridistribuiti nei gruppi 1–5 in proporzione agli assegnati, cioè le percentuali sono calcolate sul totale dei soli individui assegnati; se nessuno è assegnato il Foram-AMBI è vuoto (EQS `N/A`). Vale per il `Foram-AMBI` e per il Foram-AMBI alternativo di tutti i campioni, qualunque sia la quota di NA. Con `false` si torna al calcolo di ForamEcoQS: percentuali sul totale di tutti i foraminiferi, con NA e ND che agiscono come $EG_1$ (peso 0.0). La colonna `% non assegnati Foram-AMBI`, subito dopo `Foram-AMBI`, indica la quota ridistribuita.
6. **Classificazione EQS (Ecological Quality Status)**:
   Regole a soglie per $FSI$, $Foram\text{-}AMBI$ ed $\exp(H'_{bc})$ (assegnazione a classi: High, Good, Moderate, Poor, Bad, Azoic).

### C. Indici di Biodiversità (PAST)
Calcolati secondo il manuale di riferimento di PAST 4 (*Hammer et al. 2001*):
- Shannon $H$ con correzione per bias di Miller-Madow: $H_{MM} = H_{plugin} + \frac{S - 1}{2N}$
- Dominanza $D$ e Simpson $1 - D$ non distorti: $D = \frac{\sum x_i(x_i - 1)}{N(N - 1)}$
- Evenness $e^H / S$ (basata su $H_{MM}$) ed Equitability $J$ (basata su $H_{plugin} / \ln S$)
- Indici di Menhinick, Margalef, Brillouin, Berger-Parker
- $\alpha$ di Fisher (risoluzione dell'equazione implicita con algoritmo di Brent)
- Stimatori non parametrici di ricchezza asintotica: Chao-1 (corretto per bias), iChao-1 (Chiu et al. 2014), ACE (Abundance-based Coverage Estimator, Chao & Lee 1992, soglia rari $\le 10$), Squares (Alroy 2018).

### D. Densità Faunistica e Deformazioni
- **Densità faunistica media**: individui per $10\text{ ml}$ di sedimento, calcolata sulle singole repliche ($V_{replica} = 150\text{ ml}$) e poi mediata per campione.
- **Percentuale di deformati**: frazione $\frac{\sum DEFORMATI}{\sum INDIVIDUI}$.

### E. Statistica Multivariata e Output per PAST
- **Cluster Gerarchico**: Matrice di dissimilarità Bray-Curtis sulle abbondanze relative totali; linkage UPGMA (`average`). L'ordine dei campioni nelle tabelle e nei grafici segue esattamente le foglie del dendrogramma.
- **Gruppi di Cluster**: Configurazione di tre rami principali nel dendrogramma (G1, G2, G3).
- **Tabelle per Canonical Correspondence Analysis (CCA)**:
  - `Tabella_CCA_All`: tutti i parametri geochimici e indici + tutte le specie (%) con indicazione dello stile di vita abbreviato (es. `Ammonia beccarii (Inf sup)`).
  - `Tabella_CCA_3%`: solo specie dominanti con abbondanza $\ge 3\%$ in almeno un campione (`threshold_mode = "specie"`).
  - `Tabella_CCA_3%_norm`: parametri ambientali e indici standardizzati con Z-score campionario ($ddof = 1$) + specie dominanti (%).

---

## 5. Output Generati dalla Pipeline

L'esecuzione del comando `uv run foramqs run` produce:
- **`output/Results_<timestamp>.xlsx`** contenente i fogli:
  - `Indici_PAST` (con grafici nativi: Ricchezza S, Shannon H)
  - `Foram Echo QS` (con grafici nativi e linee di soglia EQS: exp(H'bc), Foram-AMBI; colonne `exp(H'bc) EQR` = exp(H'bc) / massimo tra i campioni ed `EQS exp(H'bc) EQR` = classe dell'EQR in 5 intervalli da 0.2, BAD → HIGH, soglie in `[eqs].exp_hbc_eqr`)
  - `Abbondanze_assolute`
  - `Abbondanza_relativa%`
  - `Abbondanza_rel%_deformati` (grafico % deformati)
  - `Abbondanza_relativa%_guscio` (grafico a barre 100% impilate)
  - `Abbondanza_rel%_stilivita` (grafico a barre 100% impilate)
  - `Abbondanza_rel%_gruppiecologici` (grafico a barre 100% impilate + colonna indice esterno M-AMBI; con `redistribute_unassigned = true` GI–GV sono frazioni dei soli individui assegnati, come nel calcolo del Foram-AMBI, e la quota NA è nella colonna `NA`, fuori dal grafico, in tutti i campioni)
  - `Abbondanza_rel%_gruppiecol_alt` (presente se configurato `foram_ambi_alternative`: ripartizione dei gruppi e Foram-AMBI alternativo con grafici dedicati per i soli campioni selezionati)
  - `Confronto_gruppi_ecologici` (presente se configurato `foram_ambi_alternative`: per ogni specie dei campioni, gruppo ecologico della lista principale Jorissen et al. 2018 e della lista alternativa, colonna `groups_column`)
  - `FSI` (grafico nativo con soglie EQS)
  - `Densità_faunistica_media` (grafico densità)
  - `Tabella_Cluster` (dati specie dominanti + dendrogramma PNG ad alta definizione + grafico a barre impilate delle specie)
  - `Tabella_matrice` (tutti i parametri sintetici e geochimici uniti)
  - `Tabella_CCA_All`, `Tabella_CCA_3%`, `Tabella_CCA_3%_norm` (pronte da incollare direttamente in PAST)
  - `Grafico_specie` (foglio nascosto con i dati di alimentazione del grafico delle specie dominanti)
  - `Validazione` (elenco di tutti gli avvisi, info o errori riscontrati)
  - `Log_pulizia` (audit trail riga per riga di ogni trasformazione di testo effettuata)
  - `Revisione_nomi` (dettaglio di come ciascun taxon è stato risolto con WoRMS o alias)
  - `Osservazioni` (tabella normalizzata flat casella per casella con taxon_id)
- **`output/figures_<timestamp>/dendrogramma.png`**: dendrogramma UPGMA vettoriale salvato in formato raster ad alta risoluzione.

---

## 6. Sistema di Validazione e Segnalazioni (Audit Trail)

| Codice | Severità | Descrizione sintetica |
|---|---|---|
| **V01–V05** | Errore | Tabelle mancanti, dati di posizione/conteggio/deformati o guscio non validi |
| **V07–V08** | Avviso | Caselle duplicate nella stessa slide/replica, numerazione repliche non consecutiva |
| **V09–V10** | Avviso | Nomi con sintassi anomala; forme non determinate senza guscio (scartate) |
| **V11** | Avviso | Stesso taxon con gusci diversi nei fogli (per specie non presenti in `species_traits.csv`) |
| **V12** | Avviso | Nomi con elevata somiglianza fuzzy (possibili refusi o varianti) |
| **V13** | Errore | Conteggio presente ma campo specie vuoto (evita perdita silenziosa di dati) |
| **V20–V25** | Errore/Avviso | Geochimica: campioni disallineati, valori non numerici, granulometria $\ne 100\%$, duplicazioni |
| **V26** | Errore | Tabella campione vuota (nuovo campione non ancora compilato) |
| **V27** | Errore | Valore geochimico mancante (bloccante per la CCA) |
| **V28** | Errore | Campione duplicato nella tabella geochimica |
| **V29** | Errore | Campione senza nessun individuo vivo conteggiato |
| **V30** | Errore | Errore di configurazione nelle repliche duplicate |
| **T01–T06** | Info/Avviso | Risoluzione WoRMS: non risolto, alias applicato, sinonimo risolto, omonimi scelti |
| **R01–R04** | Errore/Avviso | `species_traits.csv`: valori non ammessi, conflitti tra righe, specie prive di tratti |
| **R05** | Info | Guscio nel foglio grezzo corretto dal guscio autoritativo della tabella dei tratti |
| **C01–C02** | Errore/Avviso | Gruppi cluster non presenti nei campioni o non formanti un ramo valido del dendrogramma |
| **A01–A05** | Errore | Foram-AMBI alternativo: campioni sconosciuti, file non trovato, valori non ammessi, conflitti o nome del foglio non valido per Excel |
| **I01–I03** | Info | Giovanili sommati a `spp.`; individui morti (righe senza conteggio); repliche duplicate da config |

---

## 7. Decisioni Metodologiche Pregresse e Parametri Confermati

1. **Protocollo biologico e frazione**: Colorazione con soluzione di **Rosa Bengala**; frazione analizzata al microscopio **$> 125\ \mu\text{m}$**.
2. **Gestione individui morti**: Le righe con specie registrata ma con cella `N°INDIVIDUI` vuota rappresentano foraminiferi morti (non colorati con Rosa Bengala o gusci vuoti). Vengono escluse dalle conte del vivente ma tracciate con la nota informativa `I02` e commento associato.
3. **Individui non determinati**: Le etichette "Not determined" o "Specie anomala" prive dell'indicazione del guscio vengono scartate (V10). Se è presente il guscio (`ND A`, `ND I`, `ND P`), vengono conteggiate e contribuiscono al totale degli individui $N$, alla densità e, come i taxa NA, al Foram-AMBI (ridistribuiti nei gruppi assegnati, oppure come $EG_1$ con `redistribute_unassigned = false`), ma sono escluse da FSI.
4. **Giovanili**: I record "Genere Juvenile" confluiscono sistematicamente in "Genere spp." per evitare sovrastima artificiale della ricchezza specifica.
5. **Trattamento replica singola MC_FO02**: Avendo una sola replica campionata (R1), è stato deciso di replicare R1 tre volte (`[input.copied_replicas]`) per renderla comparabile con il volume standard delle altre stazioni (450 ml totali = 3 repliche da 150 ml).
6. **Classi EQS**: Confermata la soglia norvegese per $\exp(H'_{bc})$ (High $\ge 22$, Good $\ge 13$, Moderate $\ge 7$, Poor $> 3$, Bad), con l'alternativa italiana documentata in config.
7. **Deformità morfologiche**: Si utilizza esclusivamente l'abbondanza relativa complessiva dei deformati ($\sum DEFORMATI / \sum INDIVIDUI$), senza calcolo di indici teratologici secondari (FDI).
8. **Analisi multivariata CCA**: Flusso ibrido Python/PAST confermato: `foramqs` prepara e formatta le matrici complete e standardizzate (`Tabella_CCA_*`), mentre l'elaborazione biplot/triplot e l'esplorazione dell'ordinamento sono demandate all'ambiente interattivo di PAST.
9. **Foram-AMBI Alternativo Configurabile**: Possibilità di calcolare, per un sottoinsieme di campioni configurato in `[foram_ambi_alternative]`, un Foram-AMBI secondario basato su un file CSV dedicato (`reference/foram_ambi_alt.csv`). La lista è indipendente (solo le specie presenti nel file ricevono il gruppo ecologico 1–5, le altre sono `NA`), valorizza le colonne dedicate in `Foram Echo QS` ed esporta il foglio/grafico `Abbondanza_rel%_gruppiecol_alt`.
10. **Geochimica e valori censurati**: Nessun valore censurato aggiuntivo (LOD/LOQ) da gestire oltre alla regola storica dello Stagno ($>200 \to 201$).
11. **Grafici Excel Nativi**: Tutti i grafici nel file dei risultati (tranne il dendrogramma) sono inseriti come grafici Excel collegati dinamicamente alle celle, rendendoli personalizzabili per tesi e presentazioni.

---

## 8. Guida Operativa Rapida

```powershell
# 1. Verifica preliminare della coerenza dei dati (genera report di validazione)
uv run foramqs check

# 2. Esecuzione completa della pipeline (genera Results_<data>.xlsx e dendrogramma)
uv run foramqs run

# 3. Aggiunta guidata di un nuovo campione (crea template, backup e aggiorna config)
uv run foramqs add-sample MC_XX01 --gruppo G1

# 4. Confronto tra risultati attuali e vecchi Results storici
uv run foramqs diff input_data/Campioni_P_2025_Results.xlsx

# 5. Suite di test automatici
uv run pytest
```

