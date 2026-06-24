# Energy Scenarios — Mix Energetico Europeo

Sito web **statico** (GitHub Pages-ready) per visualizzare e simulare scenari
di mix energetico orario per uno o più paesi europei.

**Dati**: [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/) (dati reali)<br>
**Stack**: HTML + CSS + JavaScript vanilla + [Chart.js](https://www.chartjs.org/) (CDN)<br>
**Pre-processing**: script Python `fetch_data.py`

---

## Funzionalità

- **Selezione multi-paese** — scegli e combina paesi (IT, DE, FR, ES, PL, NL, BE, AT, CH)
- **Tabella capacità installata** — modifica la potenza per fonte e scala la generazione oraria
- **KPI** — ore surplus rinnovabile, ore fissate dal gas, quota rinnovabile %
- **Duration curve** — surplus rinnovabile ordinato decrescente
- **Grafico settimanale** — stacked area per fonte (rinnovabili + nucleare + fossili) + linea carico

## Struttura

```
.
├── index.html              ← pagina principale
├── style.css               ← stili
├── app.js                  ← logica frontend (Chart.js)
├── config.json             ← configurazione paesi/anno
├── fetch_data.py           ← script Python per scaricare dati reali da ENTSO-E
├── data/
│   ├── countries.json      ← elenco paesi supportati
│   ├── capacity_IT.json    ← capacità installata (da ENTSO-E)
│   ├── capacity_DE.json
│   ├── ...
│   ├── generation_IT_2024.json  ← generazione oraria (da ENTSO-E)
│   └── generation_DE_2024.json
├── sources.md              ← fonti e assunzioni
├── pyproject.toml          ← configurazione progetto Python
└── README.md
```

---

## Come usare

### 1. Scarica i dati

```bash
pip install entsoe-py pandas python-dotenv requests
```

Configura il token ENTSO-E in `.env` come `ENTSOe_KEY=il_tuo_token` o come
variabile d'ambiente `ENTSOE_TOKEN`, poi:

```bash
python fetch_data.py
```

I file JSON nella cartella `data/` verranno popolati con dati reali.

### 2. Avvia la pagina

```bash
python -m http.server 8000
```

Apri `http://localhost:8000` nel browser.

Il sito è completamente statico e hostabile su GitHub Pages senza backend.

---

## Struttura dei dati

### `capacity_{CC}.json`

```json
{
  "country": "IT",
  "updated": "2024-06-01",
  "sources": {
    "Solar": 32000,
    "Wind Onshore": 11800,
    "Wind Offshore": 0,
    "Hydro": 22000,
    "Nuclear": 0,
    "Gas": 46000,
    "Coal": 8000,
    "Other": 5000
  }
}
```

### `generation_{CC}_{YYYY}.json`

```json
{
  "country": "IT",
  "year": 2024,
  "hours": 8784,
  "sources": ["Solar","Wind Onshore","Hydro","Gas","Coal","Other"],
  "load": [array di float in MW],
  "generation": {
    "Solar": [array orario in MW],
    "Wind Onshore": [array orario in MW],
    ...
  }
}
```

---

## Sviluppo

### Aggiornamento dati

Modifica `config.json` per cambiare paesi o anno, poi:

```bash
python fetch_data.py
```

### GitHub Pages

Il sito è pronto per GitHub Pages. Basta pushare il repository e abilitare
GitHub Pages dal branch `main`, cartella root `/`.

---

## Cronologia

| Versione | Descrizione |
|----------|------------|
| v0.1     | Script Python per analisi energetica Italia (legacy) |
| v0.2     | Riscrittura completa: sito statico web, multi-paese, Chart.js |
| v0.3     | Refactoring: codice spostato nella directory principale, rimossi script legacy |
| **v0.4** | **Dati reali ENTSO-E**: rimosso mock generator, fetch_data.py rifattorizzato |