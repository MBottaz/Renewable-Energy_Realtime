"""CSV and JSON writer for match results."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from energy_match.models import MatchResult
from energy_match.writers.base import Writer


class CsvWriter(Writer):
    """Write match results to CSV files and a summary JSON.

    Produces:
      - coverage.csv   — wide per-source production coverage
      - shortfall.csv  — timestamp + shortfall_mw
      - excess.csv     — timestamp + excess_mw
      - storage_soc.csv  — (only if storage is present)
      - summary.json   — aggregate statistics
    """

    def write(self, result: MatchResult, target: str | Path) -> None:
        target = Path(target)
        target.mkdir(parents=True, exist_ok=True)

        # ── coverage.csv ───────────────────────────────────────────────
        out = pd.DataFrame({"timestamp": result.timestamps})
        for col in result.coverage.columns:
            out[col] = result.coverage[col].values
        out.to_csv(target / "coverage.csv", index=False)

        # ── shortfall.csv ──────────────────────────────────────────────
        pd.DataFrame({
            "timestamp": result.timestamps,
            "shortfall_mw": result.shortfall.values,
        }).to_csv(target / "shortfall.csv", index=False)

        # ── excess.csv ─────────────────────────────────────────────────
        pd.DataFrame({
            "timestamp": result.timestamps,
            "excess_mw": result.excess.values,
        }).to_csv(target / "excess.csv", index=False)

        # ── storage_soc.csv (conditionally) ────────────────────────────
        if result.storage_soc is not None:
            soc_df = pd.DataFrame({"timestamp": result.timestamps})
            for name, series in result.storage_soc.items():
                soc_df[name] = series.values
            soc_df.to_csv(target / "storage_soc.csv", index=False)

        # ── summary.json ───────────────────────────────────────────────
        demand = result.demand
        total_coverage = float(result.coverage.sum().sum())
        total_demand = float(demand.sum())

        summary = {
            "total_demand_mwh": total_demand / 1000.0,
            "total_renewable_mwh": total_coverage / 1000.0,
            "renewable_share": (total_coverage / total_demand)
            if total_demand > 0
            else 0.0,
            "total_shortfall_mwh": float(result.shortfall.sum()) / 1000.0,
            "total_excess_mwh": float(result.excess.sum()) / 1000.0,
            "peak_demand_mw": float(demand.max()) / 1000.0,
            "peak_shortfall_mw": float(result.shortfall.max()) / 1000.0,
            "num_hours": len(result.timestamps),
            "sources": list(result.coverage.columns),
        }
        with open(target / "summary.json", "w") as f:
            json.dump(summary, f, indent=2)