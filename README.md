# Renewable Energy Realtime

Progetto Python per l'analisi della produzione energetica italiana con focus sulle fonti rinnovabili.

## Scopo del progetto

Recupera dati di produzione energetica italiana dall'API pubblica ENTSO-E, rimuove le fonti fossili (Fossil Coal-derived gas, Fossil Gas, Fossil Hard coal, Fossil Oil) e calcola l'energia non coperta dalle rinnovabili nella colonna "Other".

## Dipendenze

```bash
pip install pandas matplotlib entsoe-pandas-client
```

## Configurazione API ENTSO-E

1. Registrarsi su [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/)
2. Ottenere la chiave API
3. Esportare la variabile di ambiente:
   ```bash
   export ENTSOe_KEY="la_tua_chiave_api"
   ```

## Come eseguire lo script

### 1. Recupero dati dall'API

```bash
python import_API.py
```

Genera i file:
- `data/italy_load_generation.csv` - Dati di generazione e carico
- `data/Installed_Capacity.csv` - Capacità installata

### 2. Analisi e visualizzazione

```bash
python EnergyMatch.py
```

Genera un grafico a barre della produzione energetica.

## Struttura del codice

- `import_API.py` - Fetch dei dati dall'API ENTSO-E
- `EnergyMatch.py` - Elaborazione dati e visualizzazione

### Funzioni principali (EnergyMatch.py)

| Funzione | Descrizione |
|----------|--------------|
| `load_generation_data()` | Carica dati di generazione dal CSV |
| `load_installed_capacity()` | Carica capacità installata |
| `calculate_capacity_factors()` | Calcola i fattori di capacità |
| `apply_capacity_factors()` | Applica i fattori ai dati di generazione |
| `plot_generation()` | Genera il grafico |

### Costanti

- `FOSSIL_COLUMNS` - Fonti fossili da escludere
- `RENEWABLE_COLUMNS` - Fonti rinnovabili incluse

## Dati richiesti

I seguenti file devono essere presenti nella cartella `data/`:
- `italy_load_generation.csv` - Generato da `import_API.py`
- `Installed_Capacity.csv` - Generato da `import_API.py`
- `Target.csv` - Obiettivi di capacità (Solar, Wind)
