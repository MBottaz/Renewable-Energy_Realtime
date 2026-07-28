#!/usr/bin/env python3
"""Standalone ENTSO-E data fetcher.

Reads API key from .env automatically, runs the fetch, writes a CSV.
Usage:
    python fetch.py [--country IT] [--start 2026-07-01] [--end 2026-07-28]
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
import pandas as pd

from energy_match.readers.entsoe_reader import EntsoeReader


def main() -> None:
    load_dotenv()  # reads .env in CWD (or parent dirs)

    api_key = os.environ.get("ENTSOE_KEY")
    if not api_key:
        print(
            "error: ENTSOE_KEY not found in .env or environment.\n"
            "  Add ENTSOE_KEY=\"your_key\" to a .env file next to this script.",
            file=sys.stderr,
        )
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Fetch ENTSO-E generation data.")
    parser.add_argument("--country", default="IT", help="Country code (default IT)")
    parser.add_argument("--start", type=str, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=str, help="End date YYYY-MM-DD")
    parser.add_argument("--output", type=str, help="Output CSV path")
    args = parser.parse_args()

    # Defaults: last 7 days
    end = datetime.strptime(args.end, "%Y-%m-%d") if args.end else datetime.utcnow()
    start = (
        datetime.strptime(args.start, "%Y-%m-%d")
        if args.start
        else end - timedelta(days=7)
    )

    reader = EntsoeReader(api_key=api_key, country_code=args.country, start=start, end=end)
    ts = reader.read()

    df = pd.DataFrame({"timestamp": ts.timestamps, "demand_kw": ts.demand.values})
    for name, series in ts.productions.items():
        safe_name = name.lower().replace(" ", "_").replace("-", "_")
        df[f"{safe_name}_kw"] = series.values

    output = args.output or f"entsoe_{args.country}_{start:%Y%m%d}_{end:%Y%m%d}.csv"
    df.to_csv(output, index=False)

    print(
        f"Fetched {args.country} ({ts.timestamps[0]:%Y-%m-%d %H:%M} – "
        f"{ts.timestamps[-1]:%Y-%m-%d %H:%M}) → {output}"
    )


if __name__ == "__main__":
    main()