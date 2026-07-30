#!/usr/bin/env python3
"""Fetch generation data from ENTSO-E Transparency Platform → CSV.

Usage:
    python fetch.py
    python fetch.py --country IT --start 2026-07-01 --end 2026-07-28
    python fetch.py --country DE --days 14

Output columns: timestamp, demand_kw, <source name>, …
Source names match the canonical names used by match.py.
"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd
from dotenv import load_dotenv
from entsoe import EntsoePandasClient

# ── ENTSO-E PSR type code → canonical source name ────────────────────────
PSR_NAME: dict[str, str] = {
    "A05": "Load",
    "B01": "Biomass",
    "B02": "Fossil Brown coal/Lignite",
    "B03": "Fossil Coal-derived gas",
    "B04": "Fossil Gas",
    "B05": "Fossil Hard coal",
    "B06": "Fossil Oil",
    "B07": "Fossil Oil shale",
    "B08": "Fossil Peat",
    "B09": "Geothermal",
    "B10": "Hydro Pumped Storage",
    "B11": "Hydro Run-of-river and poundage",
    "B12": "Hydro Water Reservoir",
    "B13": "Marine",
    "B14": "Nuclear",
    "B15": "Other renewable",
    "B16": "Solar",
    "B17": "Waste",
    "B18": "Wind Offshore",
    "B19": "Wind Onshore",
    "B20": "Other",
    "B21": "AC Link",
    "B22": "DC Link",
    "B23": "Substation",
    "B24": "Transformer",
    "B25": "Energy storage",
}

# PSR types to fetch (generation sources only, no load/links)
DEFAULT_PSR_TYPES: list[str] = [
    "B01",  # Biomass
    "B09",  # Geothermal
    "B10",  # Hydro Pumped Storage
    "B11",  # Hydro Run-of-river and poundage
    "B12",  # Hydro Water Reservoir
    "B15",  # Other renewable
    "B16",  # Solar
    "B18",  # Wind Offshore
    "B19",  # Wind Onshore
    "B25", # Energy storage
]


# ── Helpers ──────────────────────────────────────────────────────────────


def _as_utc_series(obj: pd.Series | pd.DataFrame) -> pd.Series:
    """Normalise ENTSO-E output to a tz-aware UTC Series."""
    if isinstance(obj, pd.DataFrame):
        s = obj.iloc[:, 0]
    else:
        s = obj
    if s.index.tz is None:
        return s.tz_localize("UTC")
    return s.tz_convert("UTC")


def _process_multiindex(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse MultiIndex columns (PSR_CODE, 'Actual Aggregated') → single level."""
    if df.columns.nlevels > 1:
        try:
            df = df.xs("Actual Aggregated", level=1, axis=1)
        except KeyError:
            pass
    return df

def fetch_production(
    country: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    api_key: str | None = None,
) -> pd.DataFrame:
    """Fetch generation and load (demand) data from ENTSO-E Transparency Platform.

    Parameters
    ----------
    country : str
        Two-letter country code (e.g. ``"IT"``, ``"DE"``).
    start : pd.Timestamp
        Start of the query range (UTC-aware).
    end : pd.Timestamp
        End of the query range (UTC-aware).
    api_key : str | None
        ENTSO-E API key.  If *None*, loaded from the ``ENTSOE_KEY`` environment
        variable via ``load_dotenv``.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns ``timestamp``, ``demand_kw``, and one column per
        production source (from :data:`DEFAULT_PSR_TYPES` mapped through
        :data:`PSR_NAME`).

    Raises
    ------
    ValueError
        If no API key is available.
    """
    if api_key is None:
        load_dotenv()
        api_key = os.environ.get("ENTSOE_KEY")
    if not api_key:
        raise ValueError("ENTSOE_KEY not found. Set it in .env or export it.")

    client = EntsoePandasClient(api_key=api_key)

    # 1. Load (demand)
    print(f"Fetching load for {country} \u2026")
    load_raw = client.query_load(country, start=start, end=end)
    load_series = _as_utc_series(load_raw).astype("float64")
    timestamps = load_series.index

    # 2. Generation \u2014 single call for all PSR types
    productions: dict[str, pd.Series] = {}
    print(f"  Fetching generation for {country} \u2026")
    try:
        raw = client.query_generation(country, start=start, end=end)
        raw = _process_multiindex(raw)
        for psr in DEFAULT_PSR_TYPES:
            name = PSR_NAME.get(psr, psr)
            if name not in raw.columns:
                print(f"  ({name} not in response)")
                continue
            series = _as_utc_series(raw[name]).astype("float64")
            series = series.reindex(timestamps).fillna(0.0)
            productions[name] = series
    except Exception as exc:
        print(f"  (generation unavailable: {exc})")

    # 3. Build wide DataFrame
    df = pd.DataFrame({"timestamp": timestamps, "demand_kw": load_series.values})
    for name, series in productions.items():
        df[name] = series.values

    return df


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> None:
    load_dotenv()

    api_key = os.environ.get("ENTSOE_KEY")
    if not api_key:
        print(
            "error: ENTSOE_KEY not found. Set it in .env or export it.",
            file=sys.stderr,
        )
        sys.exit(1)
    parser = argparse.ArgumentParser(description="Fetch ENTSO-E generation data.")
    parser.add_argument("--country", default="IT", help="Country code (default IT)")
    parser.add_argument("--start", type=str, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=str, help="End date YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=7, help="Days to fetch (default 7)")
    parser.add_argument("--output", type=str, help="Output CSV path")
    args = parser.parse_args()
    # Date range
    end = pd.Timestamp(args.end, tz="UTC") if args.end else pd.Timestamp.now(tz="UTC")
    start = (
        pd.Timestamp(args.start, tz="UTC")
        if args.start
        else end - pd.Timedelta(days=args.days)
    )

    df = fetch_production(args.country, start, end, api_key)

    # 4. Write CSV
    output = args.output or f"entsoe_{args.country}_{start:%Y%m%d}_{end:%Y%m%d}.csv"
    df.to_csv(output, index=False)
    print(f"\n{len(df)} rows × {len(df.columns)} columns → {output}")


if __name__ == "__main__":
    main()
