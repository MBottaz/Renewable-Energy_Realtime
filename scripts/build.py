#!/usr/bin/env python3
"""Build the static frontend data from already-downloaded data.

Usage:
    python scripts/build.py [--data DIR] [--frontend DIR]

Reads ``data/entsoe_<CC>_*.csv`` (production) and the hand-maintained
``data/capacity_<CC>.json`` (installed capacity) and writes, per country:

    frontend/data/production_<CC>.json   # 15-min series, mirrors generation API
    frontend/data/capacity_<CC>.json     # installed capacity, mirrors capacity API
    frontend/js/data.js                  # thin wrapper: window.APP_DATA = {production, capacity}

No network calls.  Download the data first with:

    python scripts/fetch.py --country IT --start ... --end ...
    python scripts/capacity.py IT --output data/capacity_IT.json  # hand-maintained values

The frontend is then a fully static site that works by opening ``index.html``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `python scripts/build.py` to import core/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import DATA_DIR, FRONTEND_DIR  # noqa: E402
from core.export import build  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build frontend data (per-country JSON + data.js) from data/."
    )
    parser.add_argument(
        "--data", default=str(DATA_DIR), help="raw data dir (default: data/)"
    )
    parser.add_argument(
        "--frontend",
        default=str(FRONTEND_DIR),
        help="frontend dir (default: frontend/)",
    )
    args = parser.parse_args()

    try:
        codes = build(Path(args.data), Path(args.frontend))
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    print(f"\nDone — built: {codes}")


if __name__ == "__main__":
    main()
