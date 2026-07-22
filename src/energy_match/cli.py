"""
Command-line interface for the Renewable Energy Match toolkit.

Subcommands
-----------
match         Run the energy matching simulation.
fetch-entsoe  Fetch data from the ENTSO-E Transparency Platform.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

from energy_match.config import SOURCE_CLASSIFICATIONS
from energy_match.engine import match
from energy_match.models import SourceMeta
from energy_match.readers import CsvReader, EntsoeReader
from energy_match.writers import CsvWriter, PlotWriter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_sources_meta(
    source_names: list[str],
    source_meta_path: str | None = None,
) -> dict[str, SourceMeta]:
    """Build a sources_meta dict from known classifications and optional JSON overrides.

    Always includes the ``"demand"`` entry.  Unknown source names get a default
    ``SourceMeta(name, category="production", flexibility="inflexible")``.
    """
    meta: dict[str, SourceMeta] = {
        "demand": SourceMeta(name="demand", category="demand", flexibility="inflexible"),
    }
    for name in source_names:
        if name in SOURCE_CLASSIFICATIONS:
            meta[name] = SOURCE_CLASSIFICATIONS[name]
        else:
            meta[name] = SourceMeta(
                name=name,
                category="production",
                flexibility="inflexible",
            )

    if source_meta_path is not None:
        with open(source_meta_path) as f:
            overrides: dict[str, dict] = json.load(f)
        for name, data in overrides.items():
            existing = meta.get(name)
            if existing is not None:
                # Shallow merge (only the fields the user explicitly provides)
                for k, v in data.items():
                    setattr(existing, k, v)
            else:
                meta[name] = SourceMeta(**data)

    return meta


# ---------------------------------------------------------------------------
# match subcommand
# ---------------------------------------------------------------------------


def _run_match(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp_col = "timestamp"
    value_col = "value"

    if len(args.production_csv) == 1:
        # ── Wide mode: single file with timestamp + demand + production columns ──
        wide_path = args.production_csv[0]

        # Peek at the header to discover columns
        header = pd.read_csv(wide_path, nrows=0)
        cols = list(header.columns)

        if timestamp_col not in cols:
            print(
                f"error: wide CSV {wide_path!r} has no {timestamp_col!r} column",
                file=sys.stderr,
            )
            sys.exit(1)

        # The demand column is expected to be named "demand"
        demand_col = "demand"
        if demand_col not in cols:
            # Try a fuzzy fallback
            candidates = [c for c in cols if "demand" in c.lower() or "load" in c.lower()]
            if candidates:
                demand_col = candidates[0]
            else:
                print(
                    f"error: cannot locate a demand column in {wide_path!r}",
                    file=sys.stderr,
                )
                sys.exit(1)

        production_cols = [c for c in cols if c != timestamp_col and c != demand_col]
        source_names = production_cols

        # Identity column map (CSV already uses canonical names)
        column_map: dict[str, str] = {demand_col: demand_col}
        for col in production_cols:
            column_map[col] = col

        sources_meta = _build_sources_meta(source_names, args.source_meta)

        reader = CsvReader.from_wide(
            wide_path,
            timestamp_col=timestamp_col,
            column_map=column_map,
            sources_meta=sources_meta,
        )
    else:
        # ── Narrow mode: separate demand CSV + one production CSV per source ──
        if args.source_names is None:
            print("error: --source-names is required when multiple --production-csv files are given", file=sys.stderr)
            sys.exit(1)
        if len(args.source_names) != len(args.production_csv):
            print(
                f"error: --source-names count ({len(args.source_names)}) must match "
                f"--production-csv count ({len(args.production_csv)})",
                file=sys.stderr,
            )
            sys.exit(1)

        source_names = args.source_names
        sources_meta = _build_sources_meta(source_names, args.source_meta)

        production_paths = dict(zip(source_names, args.production_csv))

        reader = CsvReader.from_narrow(
            args.demand_csv,
            timestamp_col=timestamp_col,
            value_col=value_col,
            production_paths=production_paths,
            sources_meta=sources_meta,
        )

    # Read the time series
    ts = reader.read()

    # Run the matching engine
    result = match(ts, dispatch_order=args.dispatch_order)

    # Write CSV / JSON results
    csv_writer = CsvWriter()
    csv_writer.write(result, output_dir)

    # Optionally render a plot
    if args.plot:
        plot_path = Path(args.plot)
        plot_path.parent.mkdir(parents=True, exist_ok=True)
        plot_writer = PlotWriter()
        plot_writer.write(result, plot_path)

    # Summary to stdout
    summary_path = output_dir / "summary.json"
    if summary_path.exists():
        with open(summary_path) as f:
            summary = json.load(f)
        print(
            f"Match complete — renewable share: {summary.get('renewable_share', 'N/A'):.1%}"
        )


# ---------------------------------------------------------------------------
# fetch-entsoe subcommand
# ---------------------------------------------------------------------------


def _run_fetch(args: argparse.Namespace) -> None:
    api_key = os.environ.get("ENTSOE_KEY")
    if not api_key:
        print(
            "error: ENTSOE_KEY environment variable is not set.\n"
            "  Set it to your ENTSO-E Transparency Platform REST API key.",
            file=sys.stderr,
        )
        sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    reader = EntsoeReader(
        api_key=api_key,
        country_code=args.country,
        start=args.start,
        end=args.end,
    )
    ts = reader.read()

    # Save demand
    demand_df = pd.DataFrame({
        "timestamp": ts.timestamps,
        "demand_kw": ts.demand.values,
    })
    demand_df.to_csv(output_dir / "demand.csv", index=False)

    # Save each production source
    for name, series in ts.productions.items():
        safe_name = name.lower().replace(" ", "_").replace("-", "_")
        pdf = pd.DataFrame({
            "timestamp": ts.timestamps,
            f"{safe_name}_kw": series.values,
        })
        pdf.to_csv(output_dir / f"{safe_name}.csv", index=False)

    print(
        f"Fetched ENTSO-E data for {args.country} "
        f"({ts.timestamps[0]:%Y-%m-%d %H:%M} – {ts.timestamps[-1]:%Y-%m-%d %H:%M}) "
        f"→ {output_dir}/"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="energy-match",
        description="Renewable Energy Match — simulation and data tools",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── match ────────────────────────────────────────────────────────────
    match_parser = subparsers.add_parser(
        "match",
        help="Run the energy matching simulation",
        description=(
            "Parse demand and production data from CSV files, run the "
            "dispatch simulation, and write results."
        ),
    )
    match_parser.add_argument(
        "--demand-csv",
        type=str,
        help="Path to demand CSV (required in narrow mode)",
    )
    match_parser.add_argument(
        "--production-csv",
        type=str,
        nargs="+",
        required=True,
        help=(
            "One or more production CSV files.  A single file is treated as "
            "a wide CSV containing timestamp + demand + production columns.  "
            "Multiple files activate narrow mode (one per source)."
        ),
    )
    match_parser.add_argument(
        "--source-names",
        type=str,
        nargs="+",
        help=(
            "Canonical source names.  Required in narrow mode.  "
            "Count must match --production-csv."
        ),
    )
    match_parser.add_argument(
        "--source-meta",
        type=str,
        help=(
            "Optional JSON file with SourceMeta overrides.  Keys are source "
            "names, values are partial dataclass fields."
        ),
    )
    match_parser.add_argument(
        "--dispatch-order",
        type=str,
        nargs="+",
        help="Override the default dispatch order (highest priority first).",
    )
    match_parser.add_argument(
        "--output-dir",
        type=str,
        default="./output",
        help="Output directory for results (default: ./output)",
    )
    match_parser.add_argument(
        "--plot",
        type=str,
        help="Optional path to save a stacked-area plot (e.g. chart.png)",
    )
    match_parser.add_argument(
        "--format",
        type=str,
        choices=["csv", "json"],
        default="csv",
        help="Output format (default: csv, not yet used for output selection)",
    )

    # ── fetch-entsoe ─────────────────────────────────────────────────────
    fetch_parser = subparsers.add_parser(
        "fetch-entsoe",
        help="Fetch data from ENTSO-E Transparency Platform",
        description=(
            "Query the ENTSO-E Transparency Platform for load and generation "
            "data and save raw CSVs."
        ),
    )
    fetch_parser.add_argument(
        "--country",
        type=str,
        default="IT",
        help="Country code (default: IT)",
    )
    fetch_parser.add_argument(
        "--start",
        type=str,
        required=True,
        help="Start date (e.g. 2024-01-01)",
    )
    fetch_parser.add_argument(
        "--end",
        type=str,
        required=True,
        help="End date (e.g. 2024-12-31)",
    )
    fetch_parser.add_argument(
        "--output-dir",
        type=str,
        default="./output",
        help="Output directory for fetched CSVs (default: ./output)",
    )

    args = parser.parse_args()

    if args.command == "match":
        _run_match(args)
    elif args.command == "fetch-entsoe":
        _run_fetch(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()