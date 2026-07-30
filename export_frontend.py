#!/usr/bin/env python3
"""Export ENTSO-E data to frontend static assets."""

import json
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from fetch import fetch_production, PSR_NAME, DEFAULT_PSR_TYPES
from capacity import query_installed_capacity

FRONTEND_DATA = Path("frontend/data")
COUNTRIES_FILE = Path("data/countries.json")
YEAR = 2026


def main() -> None:
    load_dotenv()
    api_key = os.getenv("ENTSOE_KEY")
    if not api_key:
        print("error: ENTSOE_KEY not found", file=sys.stderr)
        sys.exit(1)

    FRONTEND_DATA.mkdir(parents=True, exist_ok=True)
    countries = json.loads(COUNTRIES_FILE.read_text())
    start = pd.Timestamp(f"{YEAR}-01-01", tz="UTC")
    end = pd.Timestamp(f"{YEAR}-12-31", tz="UTC")

    # Phase 1: Fetch and write per country
    for c in countries:
        code = c["code"]
        # Fetch production
        print(f"Fetching production for {code} …")
        try:
            df = fetch_production(code, start, end, api_key)
        except Exception as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            continue
        csv_path = FRONTEND_DATA / f"production_{code}.csv"
        df.to_csv(csv_path, index=False)
        print(f"  → {csv_path} ({len(df)} rows)")

        # Fetch capacity
        print(f"Fetching capacity for {code} …")
        try:
            cap = query_installed_capacity(code, api_key)
        except Exception as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            cap = {}
        cap_json = {
            "country": code,
            "updated": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d"),
            "sources": cap,
        }
        json_path = FRONTEND_DATA / f"capacity_{code}.json"
        json_path.write_text(json.dumps(cap_json, indent=2) + "\n")
        print(f"  → {json_path} ({len(cap)} sources)")

    # Phase 2: Column normalization
    print("\nNormalizing columns …")
    all_source_cols: set[str] = set()
    csv_files: dict[str, pd.DataFrame] = {}
    for c in countries:
        csv_path = FRONTEND_DATA / f"production_{c['code']}.csv"
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            src_cols = set(df.columns) - {"timestamp", "demand_kw"}
            all_source_cols |= src_cols
            csv_files[c["code"]] = df

    sorted_sources = sorted(all_source_cols)
    for code, df in csv_files.items():
        for col in sorted_sources:
            if col not in df.columns:
                df[col] = 0.0
        # Reorder: timestamp, demand_kw, then sorted sources
        ordered = ["timestamp", "demand_kw"] + sorted_sources
        df = df[ordered]
        csv_path = FRONTEND_DATA / f"production_{code}.csv"
        df.to_csv(csv_path, index=False)
    print(f"  Normalized {len(csv_files)} CSVs with {len(sorted_sources)} shared sources")

    # Phase 3: Generate index.json
    print("Generating index.json …")
    index_entries = []
    for c in countries:
        csv_path = FRONTEND_DATA / f"production_{c['code']}.csv"
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            ts = pd.to_datetime(df["timestamp"])
            index_entries.append({
                "code": c["code"],
                "name": c["name"],
                "date_start": ts.min().strftime("%Y-%m-%d"),
                "date_end": ts.max().strftime("%Y-%m-%d"),
            })
    index = {"countries": index_entries}
    index_path = FRONTEND_DATA / "index.json"
    index_path.write_text(json.dumps(index, indent=2) + "\n")
    print(f"  → {index_path} ({len(index_entries)} countries)")

    print(f"\nDone: {len(csv_files)} countries exported.")


if __name__ == "__main__":
    main()