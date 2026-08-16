"""Plotting helpers for match results.

The public function ``plot_match_results()`` renders a matplotlib stacked-area
chart from a ``match()`` output directory.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from core.config import PLOT_COLORS


def get_source_color(name: str) -> str:
    """Return the plot colour for a source name, falling back to a CSS-class color."""
    name_lower = name.lower()
    for key, color in PLOT_COLORS.items():
        if key.lower() == name_lower:
            return color
    return "#7F7F7F"


def plot_match_results(
    input_dir: str | Path = Path("output"),
    output: str | Path = "chart.png",
    *,
    show_demand: bool = True,
    show_storage: bool = False,
    title: str = "Energy Match",
) -> Path:
    """Render a stacked-area chart from ``match()`` output.

    Parameters
    ----------
    input_dir : str | Path
        Directory containing ``coverage.csv`` (and optionally ``shortfall.csv``,
        ``storage_soc.csv``).
    output : str | Path
        Output image path.
    show_demand : bool
        Overlay a dashed demand line.
    show_storage : bool
        Add a second subplot with storage SOC.
    title : str
        Chart title.

    Returns
    -------
    Path
        The output image path.
    """
    input_dir = Path(input_dir)
    output = Path(output)

    # Read coverage
    coverage = pd.read_csv(
        input_dir / "coverage.csv", parse_dates=["timestamp"]
    ).set_index("timestamp")
    timestamps = coverage.index

    # Read shortfall optionally
    shortfall_path = input_dir / "shortfall.csv"
    shortfall = None
    if shortfall_path.exists() and show_demand:
        shortfall = pd.read_csv(shortfall_path, parse_dates=["timestamp"])[
            "shortfall_kw"
        ].values

    # Read storage SOC optionally
    soc_path = input_dir / "storage_soc.csv"
    soc_df = None
    if soc_path.exists() and show_storage:
        soc_df = pd.read_csv(soc_path, parse_dates=["timestamp"])

    # ── Figure ──
    n_subplots = 2 if soc_df is not None else 1
    fig, axes = plt.subplots(
        n_subplots, 1, figsize=(14, 5 + 3 * n_subplots), sharex=True
    )
    ax1 = axes[0] if n_subplots > 1 else axes

    # Stacked area
    sources = [c for c in coverage.columns if c != "shortfall"]
    y_data = coverage[sources].values.T  # (n_sources, n_hours)
    colors = [get_source_color(name) for name in sources]

    ax1.stackplot(timestamps, y_data, labels=sources, colors=colors, alpha=0.85)

    # Demand line
    if shortfall is not None:
        demand_kw = coverage.sum(axis=1).values + shortfall
        ax1.plot(timestamps, demand_kw, color="black", linewidth=0.8, label="Demand")

    ax1.set_ylabel("kW")
    ax1.set_title(title)
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
    fig.savefig(output, dpi=150)
    plt.close(fig)
    print(f"Chart saved → {output}")
    return output