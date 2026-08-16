"""Dispatch engine — runs the full simulation over a DataFrame.

``match()`` is the main orchestrator; ``write_match_results()`` writes
the output CSVs and summary JSON.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from core.config import (
    DISPATCH_ORDER,
    OUTPUT_DIR,
    SOURCE_CLASSIFICATIONS,
    SourceMeta,
)
from core.dispatch import build_dispatch_order, dispatch_hour


def match(
    df: pd.DataFrame,
    demand_col: str = "demand_kw",
    sources_meta: dict[str, SourceMeta] | None = None,
    dispatch_order: list[str] | None = None,
) -> dict:
    """Run the dispatch simulation on a DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain a ``timestamp`` column, the *demand_col* column, and one
        column per production source (named as in ``SOURCE_CLASSIFICATIONS``).
    demand_col : str
        Name of the demand column (default ``"demand_kw"``).
    sources_meta : dict[str, SourceMeta] | None
        Source classifications.  Defaults to ``SOURCE_CLASSIFICATIONS``.
    dispatch_order : list[str] | None
        Dispatch priority.  Defaults to ``DISPATCH_ORDER`` filtered to the
        sources actually present in the data.

    Returns
    -------
    dict
        Keys:

        - ``timestamps`` (pd.DatetimeIndex)
        - ``coverage`` (pd.DataFrame — source x hour)
        - ``shortfall`` (list[float])
        - ``excess`` (list[float])
        - ``storage_soc`` (list[dict[str, float]] | None)
        - ``summary`` (dict)
    """
    if sources_meta is None:
        sources_meta = SOURCE_CLASSIFICATIONS

    timestamps = pd.to_datetime(df["timestamp"])

    # Identify production columns
    production_cols = [c for c in df.columns if c not in ("timestamp", demand_col)]
    known_sources = {
        name: sources_meta[name]
        for name in production_cols
        if name in sources_meta
    }
    unknown = set(production_cols) - set(known_sources.keys())
    if unknown:
        print(f"warning: skipping unknown columns: {sorted(unknown)}", file=sys.stderr)

    # Build dispatch order (only the sources present in the data)
    order = build_dispatch_order(set(known_sources.keys()), sources_meta, dispatch_order)

    # Initialise storage state
    storage_state: dict[str, float] = {}
    storage_names: list[str] = []
    for name, meta in known_sources.items():
        if meta.flexibility == "storage":
            storage_state[name] = meta.initial_soc_kwh
            storage_names.append(name)

    # Hourly dispatch loop
    coverage_records: list[dict[str, float]] = []
    soc_records: list[dict[str, float]] = []
    shortfall_list: list[float] = []
    excess_list: list[float] = []

    n = len(df)
    for i in range(n):
        demand = float(df[demand_col].iloc[i])
        productions = {name: float(df[name].iloc[i]) for name in known_sources}
        cov, new_soc, shortfall, excess = dispatch_hour(
            demand_kw=demand,
            productions_kw=productions,
            dispatch_order=order,
            storage_state=storage_state,
            sources_meta=known_sources,
        )
        coverage_records.append(cov)
        shortfall_list.append(shortfall)
        excess_list.append(excess)
        if storage_names:
            soc_records.append({name: new_soc.get(name, 0.0) for name in storage_names})
        storage_state = new_soc

    # Build coverage DataFrame
    coverage_df = pd.DataFrame(coverage_records, index=timestamps)

    # Summary
    demand_series = df[demand_col].set_axis(timestamps)
    total_demand = float(demand_series.sum())
    total_coverage = float(coverage_df.sum().sum())
    summary = {
        "total_demand_mwh": total_demand / 1000.0,
        "total_renewable_mwh": total_coverage / 1000.0,
        "renewable_share": (total_coverage / total_demand) if total_demand > 0 else 0.0,
        "total_shortfall_mwh": float(sum(shortfall_list)) / 1000.0,
        "total_excess_mwh": float(sum(excess_list)) / 1000.0,
        "peak_demand_mw": float(demand_series.max()) / 1000.0,
        "peak_shortfall_mw": float(max(shortfall_list)) / 1000.0,
        "num_hours": n,
        "sources": list(coverage_df.columns),
    }

    return {
        "timestamps": timestamps,
        "coverage": coverage_df,
        "shortfall": shortfall_list,
        "excess": excess_list,
        "storage_soc": soc_records if storage_names else None,
        "storage_names": storage_names,
        "summary": summary,
    }


def write_match_results(results: dict, output_dir: str | Path = OUTPUT_DIR) -> Path:
    """Write match results to CSV files and ``summary.json``.

    Parameters
    ----------
    results : dict
        Return value of ``match()``.
    output_dir : str | Path
        Directory to write into (created if missing).

    Returns
    -------
    Path
        The *output_dir* that was used.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamps = results["timestamps"]
    coverage_df = results["coverage"]
    shortfall_list = results["shortfall"]
    excess_list = results["excess"]
    soc_records = results["storage_soc"]
    storage_names = results["storage_names"]

    # Write coverage.csv
    out = pd.DataFrame({"timestamp": timestamps})
    for col in coverage_df.columns:
        out[col] = coverage_df[col].values
    out.to_csv(output_dir / "coverage.csv", index=False)

    # Write shortfall.csv
    pd.DataFrame(
        {"timestamp": timestamps, "shortfall_kw": shortfall_list}
    ).to_csv(output_dir / "shortfall.csv", index=False)

    # Write excess.csv
    pd.DataFrame(
        {"timestamp": timestamps, "excess_kw": excess_list}
    ).to_csv(output_dir / "excess.csv", index=False)

    # Write storage_soc.csv (only if storage is present)
    if storage_names and soc_records:
        soc_df = pd.DataFrame({"timestamp": timestamps})
        for name in storage_names:
            soc_df[name] = [r.get(name, 0.0) for r in soc_records]
        soc_df.to_csv(output_dir / "storage_soc.csv", index=False)

    # Write summary.json
    (output_dir / "summary.json").write_text(
        json.dumps(results["summary"], indent=2)
    )

    print(
        f"Match complete — renewable share: {results['summary']['renewable_share']:.1%} → {output_dir}/"
    )
    return output_dir