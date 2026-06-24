#!/usr/bin/env python3
"""
fetch_data.py — Popola data/ con dati reali da ENTSO-E.

Utilizza il codice adattato da import_API.py (progetto esistente).
Sostituisce i file JSON mock con dati reali.

Dipendenze:
    pip install requests pandas entsoe-py python-dotenv

Config:
    Legge config.json nella root del progetto.
    Oppure usa variabili d'ambiente ENTSOE_TOKEN.

Output:
    - data/capacity_{CC}.json
    - data/generation_{CC}_{YYYY}.json
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

# Tentativo di import con fallback informativo
try:
    from entsoe import EntsoePandasClient
except ImportError:
    print("ERROR: entsoe-py non installato. Esegui: pip install entsoe-py")
    sys.exit(1)


# ─── Mappatura codici ENTSO-E → categorie semplificate ───
# Basata sulla mappatura già presente in import_API.py
ENTSOE_TO_SOURCE = {
    "B01": "Other",       # Biomass → Other
    "B02": "Coal",        # Fossil Brown coal/Lignite → Coal
    "B03": "Coal",        # Fossil Coal-derived gas → Coal
    "B04": "Gas",         # Fossil Gas → Gas
    "B05": "Coal",        # Fossil Hard coal → Coal
    "B06": "Other",       # Fossil Oil → Other
    "B07": "Other",       # Fossil Oil shale → Other
    "B08": "Other",       # Fossil Peat → Other
    "B09": "Other",       # Geothermal → Other
    "B10": "Hydro",       # Hydro Pumped Storage → Hydro
    "B11": "Hydro",       # Hydro Run-of-river → Hydro
    "B12": "Hydro",       # Hydro Water Reservoir → Hydro
    "B13": "Other",       # Marine → Other
    "B14": "Nuclear",     # Nuclear → Nuclear
    "B15": "Other",       # Other renewable → Other
    "B16": "Solar",       # Solar → Solar
    "B17": "Other",       # Waste → Other
    "B18": "Wind Offshore",  # Wind Offshore
    "B19": "Wind Onshore",   # Wind Onshore
    "B20": "Other",       # Other
}

# Categorie finali (output)
CATEGORIES = ["Solar", "Wind Onshore", "Wind Offshore", "Hydro", "Nuclear", "Gas", "Coal", "Other"]
RENEWABLE_CATEGORIES = ["Solar", "Wind Onshore", "Wind Offshore", "Hydro"]

# Mappa ISO → ENTSOE key (da countries.json)
COUNTRIES = {
    "IT": "10YIT-GRTN-----B",
    "DE": "10Y1001A1001A83F",
    "FR": "10YFR-RTE------C",
    "ES": "10YES-REE------0",
    "PL": "10YPL-AREA-----S",
    "NL": "10YNL----------L",
    "BE": "10YBE----------2",
    "AT": "10YAT-APG------L",
    "CH": "10YCH-SWISSGRIDZ",
}


# ─── Funzioni adattate da import_API.py ───

def get_entsoe_key_from_env():
    """
    Recupera la chiave ENTSO-E da variabili d'ambiente o .env.
    Adattato da import_API.py.
    """
    # Prova variabile d'ambiente
    key = os.getenv("ENTSOE_TOKEN") or os.getenv("ENTSOe_KEY")
    if key:
        return key

    # Prova .env nella root del progetto
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=env_path)
            key = os.getenv("ENTSOE_TOKEN") or os.getenv("ENTSOe_KEY")
            if key:
                return key
        except ImportError:
            pass

    raise RuntimeError(
        "ENTSOE_TOKEN non trovato. Imposta la variabile d'ambiente o "
        "aggiungila a .env. Oppure configura config.json."
    )


def parse_config():
    """
    Legge config.json dalla root del progetto.
    Restituisce { entsoe_token, countries, year }.
    """
    # Cerca config.json nella root del progetto
    paths = [
        Path(__file__).resolve().parent / "config.json",           # accanto a fetch_data.py
    ]

    config = {}
    for p in paths:
        if p.exists():
            with open(p) as f:
                config = json.load(f)
            break

    if not config.get("countries"):
        config["countries"] = ["IT"]

    if not config.get("year"):
        config["year"] = 2024

    if not config.get("entsoe_token"):
        try:
            config["entsoe_token"] = get_entsoe_key_from_env()
        except RuntimeError as e:
            print(f"AVVISO: {e}")
            print("Tento di proseguire senza token (solo paesi con dati esistenti)...")
            config["entsoe_token"] = None

    return config


def process_multiindex_columns(df):
    """
    Appiattisce colonne MultiIndex.
    Prende 'Actual Aggregated' o 'Actual Consumption' (somma se entrambi presenti).
    Se stesso nome colonna appare più volte (es. due 'Hydro Pumped Storage'),
    somma i valori. Adattato da import_API.py.
    """
    if df.columns.nlevels <= 1:
        return df

    level0 = df.columns.get_level_values(0)
    level1 = df.columns.get_level_values(1)

    # Raggruppa colonne per nome (livello 0)
    result = {}
    seen = set()
    for i in range(len(df.columns)):
        name = str(level0[i])
        typ = str(level1[i])
        if typ not in ("Actual Aggregated", "Actual Consumption"):
            continue
        series = df.iloc[:, i]
        if name in result:
            result[name] = result[name].add(series, fill_value=0)
        else:
            result[name] = series

    if not result:
        return df

    out = pd.DataFrame(result)
    out.index = df.index
    return out


def resample_hourly(series):
    """
    Aggrega dati a risoluzione < 60 minuti a ore (somma per energia).
    """
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]  # Prende prima colonna se DataFrame
    return series.resample("h").sum()


# Mappa diretta da nomi colonna ENTSO-E a categorie semplificate
# (usata per query_installed_generation_capacity che restituisce nomi leggibili)
COLUMN_TO_SOURCE = {
    "Solar": "Solar",
    "Wind Onshore": "Wind Onshore",
    "Wind Offshore": "Wind Offshore",
    "Wind": "Wind Onshore",
    "Hydro Run-of-river and poundage": "Hydro",
    "Hydro Water Reservoir": "Hydro",
    "Hydro Pumped Storage": "Hydro",
    "Nuclear": "Nuclear",
    "Fossil Gas": "Gas",
    "Fossil Brown coal/Lignite": "Coal",
    "Fossil Coal-derived gas": "Coal",
    "Fossil Hard coal": "Coal",
    "Fossil Oil": "Other",
    "Fossil Oil shale": "Other",
    "Fossil Peat": "Other",
    "Biomass": "Other",
    "Geothermal": "Other",
    "Other renewable": "Other",
    "Marine": "Other",
    "Waste": "Other",
    "Other": "Other",
}

# Mappa da nome colonna a codice PSR (per generazione che può usare nomi leggibili)
NAME_TO_PSR = {
    "Solar": "B16",
    "Wind Onshore": "B19",
    "Wind Offshore": "B18",
    "Wind": "B19",
    "Hydro Run-of-river and poundage": "B11",
    "Hydro Water Reservoir": "B12",
    "Hydro Pumped Storage": "B10",
    "Nuclear": "B14",
    "Fossil Gas": "B04",
    "Gas": "B04",
    "Fossil Hard coal": "B05",
    "Fossil Brown coal/Lignite": "B02",
    "Fossil Coal-derived gas": "B03",
    "Fossil Oil": "B06",
    "Fossil Peat": "B08",
    "Biomass": "B01",
    "Geothermal": "B09",
    "Other renewable": "B15",
    "Marine": "B13",
    "Waste": "B17",
    "Other": "B20",
}


def _find_psr_code(col_name):
    """Riconverti nome colonna leggibile in codice PSR."""
    col_str = str(col_name).strip()
    if col_str.startswith("B") and col_str[1:].isdigit():
        return col_str
    return NAME_TO_PSR.get(col_str, col_str)


def fetch_capacity(client, country_code, year):
    """
    Recupera capacità installata per un paese.
    Usa mapping diretto COLUMN_TO_SOURCE (nomi colonna leggibili).
    """
    start = pd.Timestamp(f"{year}-01-01", tz="Europe/Rome")
    end = pd.Timestamp(f"{year}-12-31", tz="Europe/Rome")

    try:
        cap_df = client.query_installed_generation_capacity(
            country_code, start=start, end=end, psr_type=None
        )
    except Exception as e:
        print(f"  ERRORE recupero capacità per {country_code}: {e}")
        return None

    if cap_df is None or cap_df.empty:
        print(f"  Nessun dato capacità per {country_code}")
        return None

    # Prende l'ultima riga (più recente)
    if isinstance(cap_df, pd.DataFrame):
        cap_series = cap_df.iloc[-1]
    else:
        cap_series = cap_df

    # Mappa colonne ENTSO-E alle categorie semplificate
    sources = {}
    for col in cap_series.index:
        col_str = str(col).strip()
        mapped = COLUMN_TO_SOURCE.get(col_str)
        if mapped:
            val = float(cap_series[col]) if pd.notna(cap_series[col]) else 0
            sources[mapped] = sources.get(mapped, 0) + val

    # Assicura che tutte le categorie esistano
    for cat in CATEGORIES:
        sources.setdefault(cat, 0.0)

    return {
        "country": country_code if len(country_code) == 2 else _cc_from_key(country_code),
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "sources": {k: round(v) for k, v in sources.items()},
    }


def _cc_from_key(key):
    """Riconverti ENTSO-E key in codice ISO a 2 lettere."""
    rev = {v: k for k, v in COUNTRIES.items()}
    return rev.get(key, key)


def fetch_generation(client, country_code, year):
    """
    Recupera generazione oraria per un intero anno.
    Ispirato da import_API.py — recupera tutti i tipi PSR e li aggrega.
    """
    start = pd.Timestamp(f"{year}-01-01", tz="Europe/Rome")
    end = pd.Timestamp(f"{year + 1}-01-01", tz="Europe/Rome")

    # Recupera generazione in un'unica chiamata (tutti i PSR insieme)
    try:
        gen_df = client.query_generation(
            country_code, start=start, end=end, psr_type=None
        )
    except Exception as e:
        print(f"  ERRORE generazione per {country_code}: {e}")
        return None

    if gen_df is None or gen_df.empty:
        print(f"  Nessun dato generazione per {country_code}")
        return None

    # Appiattisce MultiIndex colonne e resample orario
    gen_df = process_multiindex_columns(gen_df)
    if isinstance(gen_df, pd.DataFrame):
        gen_df = gen_df.resample("h").sum()
    else:
        gen_df = gen_df.resample("h").sum().to_frame()

    # Mappa ogni colonna (nome leggibile) alla categoria semplificata
    all_data = {}
    for col in gen_df.columns:
        col_str = str(col).strip()
        mapped = COLUMN_TO_SOURCE.get(col_str)
        if not mapped:
            # Prova reverse lookup via _find_psr_code
            psr_code = _find_psr_code(col_str)
            mapped = ENTSOE_TO_SOURCE.get(psr_code, "Other")
        if mapped:
            series = gen_df[col]
            if mapped not in all_data:
                all_data[mapped] = pd.Series(0.0, index=series.index)
            all_data[mapped] = all_data[mapped].add(series, fill_value=0)

    if not all_data:
        print(f"  Nessun dato generazione per {country_code}")
        return None

    # Recupera anche il carico
    try:
        client2 = EntsoePandasClient(api_key=client.api_key)
        load_df = client2.query_load(country_code, start=start, end=end)
        if isinstance(load_df, pd.DataFrame):
            load_series = load_df.iloc[:, 0]
        else:
            load_series = load_df

        if load_series.index.inferred_freq != "h":
            load_series = resample_hourly(load_series)
    except Exception as e:
        print(f"  ERRORE recupero carico per {country_code}: {e}")
        load_series = None

    # Allinea tutti gli indici
    common_index = None
    for src, series in all_data.items():
        if common_index is None:
            common_index = series.index
        else:
            common_index = common_index.union(series.index)

    if load_series is not None:
        common_index = common_index.union(load_series.index)

    common_index = pd.date_range(
        start=common_index.min(), end=common_index.max(), freq="h"
    )

    load_arr = []
    if load_series is not None:
        load_series = load_series.reindex(common_index, fill_value=0)
        load_arr = [round(float(v), 1) for v in load_series.values]
    else:
        load_arr = [0.0] * len(common_index)

    generation = {}
    for src in CATEGORIES:
        if src in all_data:
            series = all_data[src].reindex(common_index, fill_value=0)
            generation[src] = [round(float(v), 1) for v in series.values]
        else:
            generation[src] = [0.0] * len(common_index)

    # Costruisce il record dei source (solo quelli non tutti zero)
    active_sources = [src for src in CATEGORIES if any(v > 0 for v in generation[src])]
    if not active_sources:
        active_sources = CATEGORIES

    return {
        "country": _cc_from_key(country_code),
        "year": year,
        "hours": len(common_index),
        "sources": active_sources,
        "load": load_arr,
        "generation": {src: generation[src] for src in active_sources},
    }


# ─── Funzioni di utilità ───

def save_json(data, path):
    """Salva dati JSON con formattazione."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  -> Salvato: {path}")


def print_summary(cc, gen_data):
    """Stampa riepilogo per un paese."""
    if not gen_data:
        return
    hours = gen_data["hours"]
    missing = 0
    for src, arr in gen_data["generation"].items():
        missing += sum(1 for v in arr if v == 0)
    total_missing = missing
    total_values = hours * len(gen_data["sources"])
    pct_missing = (total_missing / total_values * 100) if total_values > 0 else 0

    from_dt = gen_data.get("_from", "?")
    to_dt = gen_data.get("_to", "?")

    print(
        f"  {cc}: {hours} ore, "
        f"{total_missing}/{total_values} valori zero ({pct_missing:.1f}%), "
        f"range: {from_dt} → {to_dt}"
    )


# ─── MAIN ───

def main():
    print("=" * 60)
    print("fetch_data.py — Aggiornamento dati ENTSO-E")
    print("=" * 60)

    config = parse_config()
    token = config.get("entsoe_token")
    countries = config.get("countries", ["IT"])
    year = config.get("year", 2024)

    if not token:
        print("ERRORE: Token ENTSO-E non configurato.")
        print("Imposta ENTSOE_TOKEN in config.json, .env, o come variabile d'ambiente.")
        sys.exit(1)

    print(f"Token: {'✅ configurato' if token else '❌ mancante'}")
    print(f"Paesi: {', '.join(countries)}")
    print(f"Anno:  {year}")
    print()

    data_dir = Path(__file__).resolve().parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    client = EntsoePandasClient(api_key=token)

    for cc in countries:
        print(f"\n--- {cc} ---")

        # 1. Capacità installata
        print("  Capacità installata...")
        cap_data = fetch_capacity(client, cc, year)
        if cap_data:
            save_json(cap_data, data_dir / f"capacity_{cc}.json")
        else:
            print("  ⚠️ Capacità non disponibile, salto.")

        # 2. Generazione oraria
        print("  Generazione oraria...")
        gen_data = fetch_generation(client, cc, year)
        if gen_data:
            # Aggiunge metadati per riepilogo
            if gen_data["load"]:
                gen_data["_from"] = str(
                    pd.Timestamp(f"{year}-01-01", tz="Europe/Rome")
                )
                gen_data["_to"] = str(
                    pd.Timestamp(f"{year}-12-31 23:00", tz="Europe/Rome")
                )
            save_json(
                gen_data,
                data_dir / f"generation_{cc}_{year}.json",
            )
            print_summary(cc, gen_data)
        else:
            print("  ⚠️ Generazione non disponibile, salto.")

    print("\n✅ Completato!")


if __name__ == "__main__":
    main()