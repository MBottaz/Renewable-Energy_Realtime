# Energy Scenarios — Mix Energetico Europeo

Sito web **statico** (GitHub Pages-ready) per visualizzare e simulare scenari
di mix energetico orario per uno o più paesi europei.

**Dati**: [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/)<br>
**Stack**: HTML + CSS + JavaScript vanilla + [Chart.js](https://www.chartjs.org/) (CDN)<br>
**Pre-processing**: script Python `energy-scenarios/fetch_data.py`

---

## Funzionalità

- **Selezione multi-paese** — scegli e combina paesi (IT, DE, FR, ES, ...)
- **Tabella capacità installata** — modifica la potenza per fonte e scala la generazione
- **KPI** — ore surplus rinnovabile, ore fissate dal gas, quota rinnovabile %
- **Duration curve** — surplus rinnovabile ordinato decrescente
- **Grafico settimanale** — stacked area per fonte + linea carico

## Struttura

```
energy-scenarios/
├── index.html              ← pagina principale
├── style.css               ← stili
├── app.js                  ← logica frontend (Chart.js)
├── config.json             ← configurazione API (da editare)
├── fetch_data.py           ← script Python per scaricare dati reali
└── data/
    ├── countries.json      ← elenco paesi
    ├── capacity_IT.json    ← capacità installata (mock o reali)
    ├── capacity_DE.json
    ├── ...
    ├── generation_IT_2024.json  ← generazione oraria (mock o reali)
    └── generation_DE_2024.json
```

---

## Come usare

### 1. Apri la pagina

Con i dati mock già pronti:

```bash
cd energy-scenarios
python -m http.server 8000
```

Apri `http://localhost:8000` nel browser.

### 2. Scarica dati reali (opzionale)

1. Ottieni un token API da [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/)
2. Configuralo in `config.json` o come variabile d'ambiente (`ENTSOE_TOKEN`)
3. Esegui lo script:

```bash
cd energy-scenarios
pip install entsoe-py pandas python-dotenv requests
python fetch_data.py
```

I file JSON nella cartella `data/` verranno sovrascritti con dati reali.

---

## Struttura dei dati

### `capacity_{CC}.json`

```json
{
  "country": "IT",
  "updated": "2024-11-01",
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
  "hours": 8760,
  "sources": ["Solar","Wind Onshore","Hydro","Gas","Coal","Other"],
  "load": [array di 8760 float in MW],
  "generation": {
    "Solar": [8760 float],
    "Wind Onshore": [8760 float],
    "Hydro": [8760 float],
    "Gas": [8760 float],
    "Coal": [8760 float],
    "Other": [8760 float]
  }
}
```

---

## Sviluppo

### Generazione dati mock

```bash
python generate_mock_data.py
```

Genera 8760 ore di dati sintetici realistici per tutti i 9 paesi.

---

## Cronologia

| Versione | Descrizione |
|----------|-------------|
| v0.1     | Script Python per analisi energetica Italia (import_API.py, EnergyMatch.py) |
| **v0.2** | **Riscrittura completa**: sito statico web, multi-paese, Chart.js |