#!/usr/bin/env python3
"""Plot match results as a stacked area chart.

Reads the output of scripts/match.py (coverage.csv, shortfall.csv) and
renders a matplotlib chart.

Usage:
    python scripts/plot.py output/
    python scripts/plot.py output/ --output output/chart.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `python scripts/plot.py` to import core/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import OUTPUT_DIR  # noqa: E402
from core.plot import plot_match_results  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot match results.")
    parser.add_argument(
        "input_dir",
        type=str,
        nargs="?",
        default=str(OUTPUT_DIR),
        help="Directory with match.py output",
    )
    parser.add_argument(
        "--output", type=str, default=str(OUTPUT_DIR / "chart.png"), help="Output image"
    )
    parser.add_argument("--show-demand", action="store_true", default=True)
    parser.add_argument("--no-demand", dest="show_demand", action="store_false")
    parser.add_argument("--show-storage", action="store_true")
    parser.add_argument("--title", type=str, default="Energy Match")
    args = parser.parse_args()

    plot_match_results(
        input_dir=args.input_dir,
        output=args.output,
        show_demand=args.show_demand,
        show_storage=args.show_storage,
        title=args.title,
    )


if __name__ == "__main__":
    main()