"""Scratch 07: Full Pipeline Demo — CSV → Engine → CsvWriter + Storage + Plot + CLI."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

import pandas as pd

from energy_match import (
    CsvReader,
    CsvWriter,
    MatchResult,
    PlotWriter,
    SourceMeta,
    TimeSeries,
    match,
)
from energy_match.config import SOURCE_CLASSIFICATIONS
from energy_match.dispatch import build_dispatch_order

# ============================================================
# PART 1 — CSV test fixture → engine → CSV writer
# ============================================================

print("=" * 72)
print("PART 1: CSV test fixture → engine → CSV writer")
print("=" * 72)

# 1a. Prepare output directory
out1 = Path("/tmp/scratch_07_output")
if out1.exists():
    shutil.rmtree(out1)

# 1b. Build a CsvReader from the sample_wide fixture (same style as scratch_03)
#     The fixture has columns: timestamp, demand, solar, wind
fixture_path = Path("tests/fixtures/sample_wide.csv")
assert fixture_path.exists(), f"Fixture not found: {fixture_path}"

sources_meta_wide: dict[str, SourceMeta] = {
    "demand": SourceMeta(name="demand", category="demand", flexibility="flexible"),
    "Solar": SourceMeta(
        name="Solar", category="production", flexibility="inflexible"
    ),
    "Wind": SourceMeta(
        name="Wind", category="production", flexibility="inflexible"
    ),
}

reader = CsvReader.from_wide(
    path=fixture_path,
    timestamp_col="timestamp",
    column_map={
        "demand": "demand",
        "Solar": "solar",
        "Wind": "wind",
    },
    sources_meta=sources_meta_wide,
)

# 1c. Read → TimeSeries
ts_wide: TimeSeries = reader.read()
print(f"\n  Loaded TimeSeries: {len(ts_wide.timestamps)} timestamps")
print(f"  Demand (kW):       {list(ts_wide.demand.values)}")
print(f"  Productions (kW):   { {k: list(v.values) for k, v in ts_wide.productions.items()} }")

# 1d. Run match()
result_wide: MatchResult = match(ts_wide)
print(f"\n  Coverage per hour (kW):")
print(f"    {result_wide.coverage.to_string()}")
print(f"\n  Shortfall (kW): {list(result_wide.shortfall.values)}")
print(f"\n  Excess (kW):  {list(result_wide.excess.values)}")

# 1e. Write results to /tmp/scratch_07_output/
writer = CsvWriter()
writer.write(result_wide, out1)

# 1f. Print summary.json contents
summary_path = out1 / "summary.json"
summary = json.loads(summary_path.read_text())
print(f"\n  --- summary.json ---")
print(json.dumps(summary, indent=2))

# 1g. Show renewable_share percentage
renewable_pct = summary["renewable_share"] * 100
print(f"\n  Renewable share: {renewable_pct:.1f}%")

# Verify files exist
for fname in ["coverage.csv", "shortfall.csv", "excess.csv", "summary.json"]:
    path = out1 / fname
    assert path.exists(), f"Missing expected file: {path}"
print(f"  ✓ All {len(os.listdir(out1))} output files verified in {out1}/")


# ============================================================
# PART 2 — Custom scenario with storage → CSV + Plot
# ============================================================

print("\n\n" + "=" * 72)
print("PART 2: Custom scenario with storage → CSV + Plot")
print("=" * 72)

# 2a. Build a manual TimeSeries (3 hours, tz-aware UTC)
timestamps = pd.DatetimeIndex(
    ["2025-06-01T00:00:00Z", "2025-06-01T01:00:00Z", "2025-06-01T02:00:00Z"],
    tz="UTC",
)

# Demand (kW)
demand = pd.Series([100.0, 200.0, 150.0], index=timestamps, name="demand")

# Solar production (kW) — inflexible
solar_prod = pd.Series([150.0, 50.0, 180.0], index=timestamps, name="solar")

# Wind production (kW) — inflexible
wind_prod = pd.Series([30.0, 40.0, 20.0], index=timestamps, name="wind")

# Battery — storage source (capacity=200, charge_rate=80, discharge_rate=60,
#                           init_soc=10, η=0.9)
# battery has zero production values — it's a storage, not a generator
battery_prod = pd.Series([0.0, 0.0, 0.0], index=timestamps, name="battery")

sources_meta_storage: dict[str, SourceMeta] = {
    "demand": SourceMeta(name="demand", category="demand", flexibility="flexible"),
    "solar": SourceMeta(
        name="solar", category="production", flexibility="inflexible"
    ),
    "wind": SourceMeta(
        name="wind", category="production", flexibility="inflexible"
    ),
    "battery": SourceMeta(
        name="battery",
        category="production",
        flexibility="storage",
        capacity_kwh=200.0,
        max_charge_rate_kw=80.0,
        max_discharge_rate_kw=60.0,
        initial_soc_kwh=10.0,
        roundtrip_efficiency=0.9,
    ),
}

ts_storage = TimeSeries(
    timestamps=timestamps,
    demand=demand,
    productions={
        "solar": solar_prod,
        "wind": wind_prod,
        "battery": battery_prod,
    },
    sources_meta=sources_meta_storage,
)

# 2b. Run match() — dispatch order built automatically from metadata
result_storage: MatchResult = match(ts_storage)

print(f"\n  Dispatch order: {build_dispatch_order(sources_meta_storage)}")

# 2c. Write to /tmp/scratch_07_output_storage/
out2 = Path("/tmp/scratch_07_output_storage")
if out2.exists():
    shutil.rmtree(out2)

storage_writer = CsvWriter()
storage_writer.write(result_storage, out2)
print(f"\n  ✓ Wrote results to {out2}/")

# 2d. Print detailed hourly breakdown
print("\n" + "-" * 72)
print("Hourly breakdown")
print("-" * 72)

for i, ts in enumerate(result_storage.timestamps):
    hour = f"H{i}"
    coverage_row = result_storage.coverage.iloc[i]
    shortfall_val = float(result_storage.shortfall.iloc[i])
    excess_val = float(result_storage.excess.iloc[i])

    # Per-source coverage
    cov_parts = []
    for src in result_storage.coverage.columns:
        val = float(coverage_row[src])
        if val > 0:
            cov_parts.append(f"{src}={val:.0f}")
    cov_str = ", ".join(cov_parts) if cov_parts else "none"

    print(f"\n  {hour} — demand={float(ts_storage.demand.iloc[i]):.0f} kW")
    print(f"    Coverage: {cov_str}")
    print(f"    Shortfall: {shortfall_val:.0f} kW")
    print(f"    Excess:   {excess_val:.0f} kW")

    if result_storage.storage_soc is not None:
        for sname, sseries in result_storage.storage_soc.items():
            soc_val = float(sseries.iloc[i])
            print(f"    SOC ({sname}): {soc_val:.1f} kWh")

# 2e. Storage SOC progression
print("\n  Storage SOC progression (kWh):")
if result_storage.storage_soc is not None:
    for sname, sseries in result_storage.storage_soc.items():
        soc_vals = [float(v) for v in sseries.values]
        arrow = " → ".join(f"{v:.0f}" for v in soc_vals)
        print(f"    {sname}: {arrow}")

# 2f. Save plot
plot_path = Path("/tmp/scratch_07_storage_chart.png")
plot_writer = PlotWriter()
plot_writer.write(
    result_storage,
    target=plot_path,
    title="Storage Scenario (3h)",
    show_demand=True,
    show_storage=True,
)
print(f"\n  ✓ Plot saved to {plot_path}")

# 2g. Print explanation
print("\n" + "-" * 72)
print("Hour-by-hour explanation")
print("-" * 72)

print("""
  H0: demand=100, solar=150, wind=30
      Step 1 (inflexible): solar covers min(150,100)=100 → remaining=0
      wind covers 0 (no remaining demand)
      shortfall=0
      excess = total_production(150+30) - non_storage_dispatched(100) = 80
      Step 4 (recharge): battery SOC=10, charge_rate=80, headroom=(200-10)/0.9=211
      charge_grid = min(80, 80, 211) = 80 → soc_stored = 80×0.9 = 72
      SOC: 10 → 82

  H1: demand=200, solar=50, wind=40
      Step 1: solar=50 → remaining=150; wind=40 → remaining=110
      Step 2 (storage): battery discharge = min(110, 60, 82) = 60
      remaining = 50, shortfall = 50
      excess = total(50+40) - dispatched(50+40) = 0
      SOC: 82 → 22

  H2: demand=150, solar=180, wind=20
      Step 1: solar covers min(180,150)=150 → remaining=0
      wind covers 0 (no remaining demand)
      shortfall=0
      excess = total(180+20) - non_storage(150+0) = 50
      Step 4: battery SOC=22, charge_grid = min(50, 80, (200-22)/0.9=198) = 50
      soc_stored = 50×0.9 = 45 → SOC: 22 → 67
""")

# 2h. Confirm plot exists
print(f"  Plot file exists: {os.path.exists(plot_path)}")
assert plot_path.exists(), f"Plot file missing: {plot_path}"


# ============================================================
# PART 3 — CLI simulation
# ============================================================

print("\n\n" + "=" * 72)
print("PART 3: CLI argument parser examination")
print("=" * 72)

from energy_match.cli import main

# Build the same parser as cli.main() to inspect it non-destructively
def show_cli_help() -> None:
    """Replicate the CLI parser construction and print help."""
    parser = argparse.ArgumentParser(
        prog="energy-match",
        description="Renewable Energy Match — simulation and data tools",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── match ──
    mp = subparsers.add_parser(
        "match",
        help="Run the energy matching simulation",
        description=(
            "Parse demand and production data from CSV files, run the "
            "dispatch simulation, and write results."
        ),
    )
    mp.add_argument("--demand-csv", type=str, help="Path to demand CSV (narrow mode)")
    mp.add_argument(
        "--production-csv",
        type=str,
        nargs="+",
        required=True,
        help="Production CSV(s) — single = wide, multiple = narrow",
    )
    mp.add_argument(
        "--source-names",
        type=str,
        nargs="+",
        help="Canonical source names (required in narrow mode)",
    )
    mp.add_argument(
        "--source-meta",
        type=str,
        help="JSON file with SourceMeta overrides",
    )
    mp.add_argument(
        "--dispatch-order",
        type=str,
        nargs="+",
        help="Override dispatch priority (highest first)",
    )
    mp.add_argument(
        "--output-dir",
        type=str,
        default="./output",
        help="Output directory (default: ./output)",
    )
    mp.add_argument(
        "--plot",
        type=str,
        help="Path to save stacked-area plot (e.g. chart.png)",
    )
    mp.add_argument(
        "--format",
        type=str,
        choices=["csv", "json"],
        default="csv",
        help="Output format (default: csv)",
    )

    # ── fetch-entsoe ──
    fp = subparsers.add_parser(
        "fetch-entsoe",
        help="Fetch data from ENTSO-E Transparency Platform",
        description="Query ENTSO-E for load and generation data, save CSVs.",
    )
    fp.add_argument("--country", type=str, default="IT", help="Country code (default: IT)")
    fp.add_argument("--start", type=str, required=True, help="Start date (e.g. 2024-01-01)")
    fp.add_argument("--end", type=str, required=True, help="End date (e.g. 2024-12-31)")
    fp.add_argument(
        "--output-dir",
        type=str,
        default="./output",
        help="Output directory (default: ./output)",
    )

    parser.print_help()


show_cli_help()

print("\n" + "=" * 72)
print("Available subcommands and their options:")
print("=" * 72)

print("""
  1. match
     --production-csv  (required)  One or more CSV files
     --demand-csv                  Demand CSV (narrow mode only)
     --source-names                Canonical source names (narrow mode)
     --source-meta                 JSON override file for SourceMeta
     --dispatch-order              Custom dispatch priority list
     --output-dir                  Output directory (default: ./output)
     --plot                        Save a stacked-area plot
     --format                      Output format: csv | json

  2. fetch-entsoe
     --country        (default: IT)
     --start          (required)  Start date YYYY-MM-DD
     --end            (required)  End date YYYY-MM-DD
     --output-dir                 Output directory (default: ./output)
""")


print("\n" + "=" * 72)
print("ALL PARTS COMPLETE")
print("=" * 72)