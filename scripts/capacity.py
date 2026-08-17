#!/usr/bin/env python3
"""Write hand-maintained installed generation capacity.

Usage:
    python scripts/capacity.py
    python scripts/capacity.py IT
    python scripts/capacity.py IT --output data/capacity_IT.json

Outputs a JSON file (default ``data/capacity_<CC>.json``) with a human summary
on stderr. Capacity is deliberately not queried from ENTSO-E because the
Italian solar and wind values returned by that API are unreliable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

# Allow `python scripts/capacity.py` to import core/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.capacity import manual_installed_capacity  # noqa: E402
from core.config import DATA_DIR  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Write hand-maintained installed capacity.")
    parser.add_argument("country", nargs="?", default="IT", help="Country code (default IT)")
    parser.add_argument(
        "--output",
        type=str,
        help=f"Output JSON path (default data/capacity_<CC>.json)",
    )
    parser.add_argument("--year", type=int, default=2025, help="Capacity year (default 2025)")
    args = parser.parse_args()

    # Default output path
    output = args.output or str(DATA_DIR / f"capacity_{args.country}.json")

    try:
        capacities = manual_installed_capacity(args.country, year=args.year)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    payload = {
        "country": args.country,
        "year": args.year,
        "updated": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d"),
        "sources": capacities,
    }
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n")

    print(json.dumps(payload, indent=2))
    print(
        f"\nTotal installed capacity: {sum(capacities.values()):,.0f} MW",
        file=sys.stderr,
    )
    print(f"Saved → {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
