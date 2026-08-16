#!/usr/bin/env python3
"""Dispatch simulation: match renewable production to hourly demand.

Reads a CSV produced by scripts/fetch.py, runs the hourly dispatch
algorithm, writes results (coverage, shortfall, excess, summary).

Usage:
    python scripts/match.py data/entsoe_IT_20260701_20260728.csv
    python scripts/match.py data.csv --output-dir output/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `python scripts/match.py` to import core/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from core.config import OUTPUT_DIR  # noqa: E402
from core.engine import match, write_match_results  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run dispatch simulation on ENTSO-E data."
    )
    parser.add_argument("input", type=str, help="CSV from scripts/fetch.py")
    parser.add_argument(
        "--output-dir", type=str, default=str(OUTPUT_DIR), help="Output directory"
    )
    args = parser.parse_args()

    # Read input CSV
    df = pd.read_csv(args.input)
    if "demand_kw" not in df.columns:
        print(
            "error: input CSV has no 'demand_kw' column",
            file=sys.stderr,
        )
        sys.exit(1)

    results = match(df)
    write_match_results(results, args.output_dir)


if __name__ == "__main__":
    main()