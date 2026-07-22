"""Plot writer for match results."""

from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from energy_match.config import DEFAULT_PLOT_COLORS
from energy_match.models import MatchResult
from energy_match.writers.base import Writer


def _get_color(name: str, idx: int) -> str:
    """Resolve plot color for *name*, falling back to matplotlib default cycle."""
    name_lower = name.lower()
    for key, color in DEFAULT_PLOT_COLORS.items():
        if key.lower() == name_lower:
            return color
    return f"C{idx}"


class PlotWriter(Writer):
    """Plot match results as a stacked area chart.

    Parameters
    ----------
    show_demand : bool
        Overlay a dashed demand line (default True).
    show_storage : bool
        Add a second subplot for storage SOC (default False).
    show_pie : bool
        Add a pie chart subplot for aggregate production shares (default False).
    """

    def write(
        self,
        result: MatchResult,
        target: str | Path,
        title: str = "Energy Match",
        show_demand: bool = True,
        show_storage: bool = False,
        show_pie: bool = False,
    ) -> None:
        target = Path(target)

        # ── Layout ─────────────────────────────────────────────────────
        has_storage = show_storage and result.storage_soc is not None
        has_pie = show_pie and len(result.coverage.columns) > 0

        nrows = 1
        if has_storage:
            nrows += 1  # storage SOC subplot
        if has_pie:
            nrows += 1  # pie subplot

        fig, axes = plt.subplots(nrows, 1, figsize=(12, 6 * nrows), squeeze=False)

        # ── Main stacked area chart ────────────────────────────────────
        ax = axes[0][0]
        timestamps = result.timestamps
        x_vals = timestamps.to_numpy()  # datetime64 for matplotlib

        production_names = list(result.coverage.columns)
        if production_names:
            colors = [_get_color(n, i) for i, n in enumerate(production_names)]
            stack_data = [result.coverage[name].values for name in production_names]
            ax.stackplot(
                x_vals, stack_data, labels=production_names, colors=colors, alpha=0.8
            )

            # Shortfall band on top of the stack
            if (result.shortfall > 0).any():
                covered = result.coverage.sum(axis=1).values
                ax.fill_between(
                    x_vals,
                    covered,
                    covered + result.shortfall.values,
                    color="gray",
                    alpha=0.3,
                    label="Shortfall",
                )
        else:
            # No production sources — just plot demand or annotate
            if show_demand:
                ax.plot(
                    x_vals,
                    result.demand.values,
                    color="red",
                    linestyle="--",
                    linewidth=1.5,
                    label="Demand",
                )
            else:
                ax.text(
                    0.5, 0.5, "No production sources",
                    transform=ax.transAxes,
                    ha="center", va="center",
                )

        # Demand line (on top of everything)
        if show_demand:
            ax.plot(
                x_vals,
                result.demand.values,
                color="red",
                linestyle="--",
                linewidth=1.5,
                label="Demand",
            )

        ax.set_title(title)
        ax.set_xlabel("Time")
        ax.set_ylabel("Power (kW)")
        ax.legend(loc="upper left", fontsize="small")
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
        fig.autofmt_xdate()

        # ── Storage SOC subplot ────────────────────────────────────────
        ax_row = 1
        if has_storage:
            ax_soc = axes[ax_row][0]
            for name, series in result.storage_soc.items():
                ax_soc.plot(x_vals, series.values, label=name)
            ax_soc.set_title("Storage State of Charge")
            ax_soc.set_xlabel("Time")
            ax_soc.set_ylabel("SOC (kWh)")
            ax_soc.legend(loc="upper left", fontsize="small")
            ax_soc.grid(True, alpha=0.3)
            ax_soc.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
            fig.autofmt_xdate()
            ax_row += 1

        # ── Pie chart subplot ──────────────────────────────────────────
        if has_pie:
            ax_pie = axes[ax_row][0]
            totals = result.coverage.sum()
            pie_colors = [_get_color(n, i) for i, n in enumerate(production_names)]
            wedges, texts, autotexts = ax_pie.pie(
                totals.values,
                labels=totals.index,
                colors=pie_colors,
                autopct="%1.1f%%",
                startangle=90,
            )
            for t in autotexts:
                t.set_fontsize(8)
            ax_pie.set_title("Production Share")

        # ── Save ───────────────────────────────────────────────────────
        plt.tight_layout()
        fmt = target.suffix if target.suffix in (".png", ".pdf") else ".png"
        save_path = target.with_suffix(fmt) if target.suffix != fmt else target
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        plt.close(fig)