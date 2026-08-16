#!/usr/bin/env python3
"""Fetch generation data from ENTSO-E Transparency Platform → CSV.

Usage:
    python scripts/fetch.py
    python scripts/fetch.py --country IT --start 2026-07-01 --end 2026-07-28
    python scripts/fetch.py --country DE --days 365

Output columns: timestamp, demand_kw, <source name>, …
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `python scripts/fetch.py` to import core/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from core.config import DATA_DIR, DEFAULT_INTERVAL_DAYS  # noqa: E402
from core.entsoe import fetch_production  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch ENTSO-E generation data.")
    parser.add_argument("--country", default="IT", help="Country code (default IT)")
    parser.add_argument("--start", type=str, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=str, help="End date YYYY-MM-DD")
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_INTERVAL_DAYS,
        help=f"Days to fetch (default {DEFAULT_INTERVAL_DAYS})"
    )
    parser.add_argument("--output", type=str, help="Output CSV path")
    args = parser.parse_args()

    # Date range
    end = pd.Timestamp(args.end, tz="UTC") if args.end else pd.Timestamp.now(tz="UTC")
    start = (
        pd.Timestamp(args.start, tz="UTC")
        if args.start
        else end - pd.Timedelta(days=args.days)
    )

    df = fetch_production(args.country, start, end)

    # Write CSV
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output = args.output or str(
        DATA_DIR / f"entsoe_{args.country}_{start:%Y%m%d}_{end:%Y%m%d}.csv"
    )
    df.to_csv(output, index=False)
    print(f"\n{len(df)} rows × {len(df.columns)} columns → {output}")


if __name__ == "__main__":
    main()