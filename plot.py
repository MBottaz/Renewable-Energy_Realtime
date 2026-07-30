#!/usr/bin/env python3
"""Plot match results as a stacked area chart.

Reads the output of match.py (coverage.csv, shortfall.csv) and renders
a matplotlib chart.

Usage:
    python plot.py results/
    python plot.py results/ --output chart.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ── Plot colours per source ──────────────────────────────────────────────

PLOT_COLORS: dict[str, str] = {
    "Biomass": "#8C564B",
    "Geothermal": "#D62728",
    "Hydro Pumped Storage": "#BCBD22",
    "Hydro Run-of-river and poundage": "#1F77B4",
    "Hydro Water Reservoir": "#17BECF",
    "Other renewable": "#E377C2",
    "Solar": "#FFBF00",
    "Wind Offshore": "#9467BD",
    "Wind Onshore": "#2CA02C",
    "Other": "#7F7F7F",
    "Energy storage": "#7F7F7F",
}


def _color(name: str, idx: int) -> str:
    name_lower = name.lower()
    for key, color in PLOT_COLORS.items():
        if key.lower() == name_lower:
            return color
    return f"C{idx}"


# ── Main ─────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot match results.")
    parser.add_argument("input_dir", type=str, help="Directory with match.py output")
    parser.add_argument("--output", type=str, default="chart.png", help="Output image")
    parser.add_argument("--show-demand", action="store_true", default=True)
    parser.add_argument("--no-demand", dest="show_demand", action="store_false")
    parser.add_argument("--show-storage", action="store_true")
    parser.add_argument("--title", type=str, default="Energy Match")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)

    # Read coverage
    coverage = pd.read_csv(
        input_dir / "coverage.csv", parse_dates=["timestamp"]
    ).set_index("timestamp")
    timestamps = coverage.index

    # Read shortfall optionally
    shortfall_path = input_dir / "shortfall.csv"
    shortfall = None
    if shortfall_path.exists() and args.show_demand:
        shortfall = pd.read_csv(
            shortfall_path, parse_dates=["timestamp"]
        )["shortfall_kw"].values

    # Read storage SOC optionally
    soc_path = input_dir / "storage_soc.csv"
    soc_df = None
    if soc_path.exists() and args.show_storage:
        soc_df = pd.read_csv(soc_path, parse_dates=["timestamp"])

    # ── Figure ────────────────────────────────────────────────────────
    n_subplots = 2 if soc_df is not None else 1
    fig, axes = plt.subplots(
        n_subplots, 1, figsize=(14, 5 + 3 * n_subplots), sharex=True
    )
    ax1 = axes[0] if n_subplots > 1 else axes

    # Stacked area
    sources = [c for c in coverage.columns if c != "shortfall"]
    y_data = coverage[sources].values.T  # (n_sources, n_hours)
    colors = [_color(name, i) for i, name in enumerate(sources)]

    ax1.stackplot(timestamps, y_data, labels=sources, colors=colors, alpha=0.85)

    # Demand line
    if shortfall is not None:
        demand_kw = coverage.sum(axis=1).values + shortfall
        ax1.plot(
            timestamps, demand_kw, color="black", linewidth=0.8, label="Demand"
        )

    ax1.set_ylabel("kW")
    ax1.set_title(args.title)
    ax1.legend(loc="upper left", fontsize="small", ncol=2)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    fig.autofmt_xdate()

    # Storage SOC subplot
    if soc_df is not None:
        ax2 = axes[1]
        for name in soc_df.columns:
            if name == "timestamp":
                continue
            ax2.plot(
                pd.to_datetime(soc_df["timestamp"]),
                soc_df[name].values,
                label=name,
                linewidth=1.0,
            )
        ax2.set_ylabel("State of Charge (kWh)")
        ax2.legend(loc="upper left", fontsize="small")
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))

    plt.tight_layout()
    fig.savefig(args.output, dpi=150)
    print(f"Chart saved → {args.output}")


if __name__ == "__main__":
    main()
