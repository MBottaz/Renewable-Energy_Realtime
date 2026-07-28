#!/usr/bin/env python3
"""Dispatch simulation: match renewable production to hourly demand.

Reads a CSV produced by fetch.py, runs the hourly dispatch algorithm,
writes results (coverage, shortfall, excess, summary).

Usage:
    python match.py entsoe_IT_20260701_20260728.csv
    python match.py data.csv --output-dir results/
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# ── Source metadata ──────────────────────────────────────────────────────


@dataclass
class SourceMeta:
    """Classification of a single energy source."""

    name: str
    flexibility: str  # "inflexible" | "flexible" | "storage"
    # Storage-only fields
    capacity_kwh: float = 0.0
    max_charge_rate_kw: float = 0.0
    max_discharge_rate_kw: float = 0.0
    initial_soc_kwh: float = 0.0
    roundtrip_efficiency: float = 1.0


# Every production source → its classification
SOURCE_CLASSIFICATIONS: dict[str, SourceMeta] = {
    # --- Inflexible renewables (must-run) ---
    "Solar": SourceMeta("Solar", "inflexible"),
    "Wind Onshore": SourceMeta("Wind Onshore", "inflexible"),
    "Wind Offshore": SourceMeta("Wind Offshore", "inflexible"),
    "Geothermal": SourceMeta("Geothermal", "inflexible"),
    "Hydro Run-of-river and poundage": SourceMeta(
        "Hydro Run-of-river and poundage", "inflexible"
    ),
    "Biomass": SourceMeta("Biomass", "inflexible"),
    "Marine": SourceMeta("Marine", "inflexible"),
    "Nuclear": SourceMeta("Nuclear", "inflexible"),
    # --- Storage ---
    "Hydro Pumped Storage": SourceMeta(
        "Hydro Pumped Storage",
        "storage",
        roundtrip_efficiency=0.85,
    ),
    # --- Flexible renewables ---
    "Hydro Water Reservoir": SourceMeta("Hydro Water Reservoir", "flexible"),
    "Other renewable": SourceMeta("Other renewable", "flexible"),
    # --- Fossil / dispatchable ---
    "Fossil Brown coal/Lignite": SourceMeta("Fossil Brown coal/Lignite", "flexible"),
    "Fossil Coal-derived gas": SourceMeta("Fossil Coal-derived gas", "flexible"),
    "Fossil Gas": SourceMeta("Fossil Gas", "flexible"),
    "Fossil Hard coal": SourceMeta("Fossil Hard coal", "flexible"),
    "Fossil Oil": SourceMeta("Fossil Oil", "flexible"),
    "Fossil Oil shale": SourceMeta("Fossil Oil shale", "flexible"),
    "Fossil Peat": SourceMeta("Fossil Peat", "flexible"),
    "Waste": SourceMeta("Waste", "flexible"),
    "Other": SourceMeta("Other", "flexible"),
}

# Dispatch priority (first = highest)
DISPATCH_ORDER: list[str] = [
    # Inflexible
    "Solar",
    "Wind Onshore",
    "Wind Offshore",
    "Geothermal",
    "Hydro Run-of-river and poundage",
    "Biomass",
    "Marine",
    "Nuclear",
    # Storage
    "Hydro Pumped Storage",
    # Flexible
    "Hydro Water Reservoir",
    "Other renewable",
    "Fossil Brown coal/Lignite",
    "Fossil Coal-derived gas",
    "Fossil Gas",
    "Fossil Hard coal",
    "Fossil Oil",
    "Fossil Oil shale",
    "Fossil Peat",
    "Waste",
    "Other",
]


# ── Dispatch logic ───────────────────────────────────────────────────────


def dispatch_hour(
    demand_kw: float,
    productions_kw: dict[str, float],
    dispatch_order: list[str],
    storage_state: dict[str, float],
    sources_meta: dict[str, SourceMeta],
) -> tuple[dict[str, float], dict[str, float], float, float]:
    """Dispatch one hour of generation.

    Returns (coverage, new_storage_state, shortfall, excess).
    - coverage: {source_name: kW dispatched toward demand}
    - new_storage_state: {name: SOC_kWh} after charge/discharge
    - shortfall: demand not covered (kW, >= 0)
    - excess: production not used by demand or storage charging (kW, >= 0)
    """
    remaining = demand_kw
    coverage: dict[str, float] = {}
    new_soc = dict(storage_state)

    # Step 1 — Inflexible sources (must-run, first in line)
    for name in dispatch_order:
        meta = sources_meta.get(name)
        if meta is None or meta.flexibility != "inflexible":
            continue
        prod = productions_kw.get(name, 0.0)
        used = min(prod, remaining)
        coverage[name] = used
        remaining -= used

    # Step 2 — Discharge storage to cover remaining demand
    if remaining > 0:
        for name in dispatch_order:
            meta = sources_meta.get(name)
            if meta is None or meta.flexibility != "storage":
                continue
            if remaining <= 0:
                break
            soc = new_soc.get(name, 0.0)
            rate = meta.max_discharge_rate_kw or 0.0
            discharge = min(remaining, rate, soc)
            if discharge > 0:
                coverage[name] = discharge
                new_soc[name] = soc - discharge
                remaining -= discharge

    # Step 3 — Flexible sources (dispatchable)
    if remaining > 0:
        for name in dispatch_order:
            meta = sources_meta.get(name)
            if meta is None or meta.flexibility != "flexible":
                continue
            if remaining <= 0:
                break
            prod = productions_kw.get(name, 0.0)
            used = min(prod, remaining)
            coverage[name] = used
            remaining -= used

    shortfall = max(0.0, remaining)

    # Excess = total production minus what went toward demand (excl. storage discharge)
    total_prod = sum(productions_kw.values())
    dispatched_no_storage = sum(
        v
        for name, v in coverage.items()
        if sources_meta.get(name) is None
        or sources_meta[name].flexibility != "storage"
    )
    excess = max(0.0, total_prod - dispatched_no_storage)

    # Step 4 — Charge storage from excess (reverse priority)
    if excess > 0:
        for name in reversed(dispatch_order):
            meta = sources_meta.get(name)
            if meta is None or meta.flexibility != "storage":
                continue
            if excess <= 0:
                break
            soc = new_soc.get(name, 0.0)
            charge_rate = meta.max_charge_rate_kw or 0.0
            capacity = meta.capacity_kwh or 0.0
            efficiency = meta.roundtrip_efficiency or 1.0
            headroom = capacity - soc
            max_by_capacity = headroom / efficiency if efficiency > 0 else 0.0
            charge = min(excess, charge_rate, max_by_capacity)
            if charge > 0:
                new_soc[name] = soc + charge * efficiency
                excess -= charge

    # Ensure every source appears in coverage
    for name in dispatch_order:
        coverage.setdefault(name, 0.0)

    return coverage, new_soc, shortfall, excess


# ── Main ─────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run dispatch simulation on ENTSO-E data."
    )
    parser.add_argument("input", type=str, help="CSV from fetch.py")
    parser.add_argument(
        "--output-dir", type=str, default="results", help="Output directory"
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Read input CSV
    df = pd.read_csv(args.input)
    timestamps = pd.to_datetime(df["timestamp"])

    # Identify demand column and production columns
    demand_col = "demand_kw"
    if demand_col not in df.columns:
        print(f"error: input CSV has no '{demand_col}' column", file=sys.stderr)
        sys.exit(1)

    production_cols = [c for c in df.columns if c not in ("timestamp", demand_col)]
    # Filter to only the sources we recognise
    known_sources = {
        name: SOURCE_CLASSIFICATIONS[name]
        for name in production_cols
        if name in SOURCE_CLASSIFICATIONS
    }
    unknown = set(production_cols) - set(known_sources.keys())
    if unknown:
        print(f"warning: skipping unknown columns: {sorted(unknown)}", file=sys.stderr)

    # Build dispatch order (only the sources present in the data)
    order = [name for name in DISPATCH_ORDER if name in known_sources]

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
        productions = {
            name: float(df[name].iloc[i]) for name in known_sources
        }
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
            soc_records.append(
                {name: new_soc.get(name, 0.0) for name in storage_names}
            )
        storage_state = new_soc

    # Build output DataFrames
    coverage_df = pd.DataFrame(coverage_records, index=timestamps)
    demand_series = df[demand_col].set_axis(timestamps)

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
    if storage_names:
        soc_df = pd.DataFrame({"timestamp": timestamps})
        for name in storage_names:
            soc_df[name] = [r.get(name, 0.0) for r in soc_records]
        soc_df.to_csv(output_dir / "storage_soc.csv", index=False)

    # Write summary.json
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
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print(
        f"Match complete — renewable share: {summary['renewable_share']:.1%} → {output_dir}/"
    )


if __name__ == "__main__":
    main()