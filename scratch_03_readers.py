#!/usr/bin/env python3
"""
Scratch 03: Demonstrate CsvReader (wide + narrow) with test fixtures.

Expected fixture at tests/fixtures/sample_wide.csv:
  timestamp,demand,solar,wind
  2025-01-01T00:00:00Z,100,40,60
  2025-01-01T01:00:00Z,150,80,70
  2025-01-01T02:00:00Z,120,60,60
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pandas as pd

from energy_match import CsvReader, SourceMeta
from energy_match.engine import match

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "tests" / "fixtures" / "sample_wide.csv"

print("=" * 68)
print("Scratch 03: CsvReader — Wide & Narrow reading")
print("=" * 68)

# ---------------------------------------------------------------------------
# Part 1 — Wide CSV reader
# ---------------------------------------------------------------------------
print("\n" + "=" * 68)
print("PART 1 — Wide CSV reader (single file, multiple columns)")
print("=" * 68)

reader = CsvReader.from_wide(
    path=str(FIXTURE),
    timestamp_col="timestamp",
    column_map={"demand": "demand", "solar": "solar", "wind": "wind"},
    sources_meta={
        "demand": SourceMeta(
            name="Demand",
            category="demand",
            flexibility="inflexible",
        ),
        "solar": SourceMeta(
            name="Solar",
            category="production",
            flexibility="inflexible",
        ),
        "wind": SourceMeta(
            name="Wind",
            category="production",
            flexibility="inflexible",
        ),
    },
)

ts = reader.read()

print(f"\nNumber of timestamps: {len(ts.timestamps)}")
print(f"Timezone:             {ts.timestamps.tz!r}")
print(f"Demand values (kW):   {ts.demand.values}")
print(f"Production sources:   {list(ts.productions.keys())}")

for key, series in ts.productions.items():
    print(f"  {key} values (kW):    {series.values}")

print()
print("Explanation: The wide CSV has one row per hour with all columns in a")
print("single file. CsvReader.from_wide() reads it, parses timestamps as UTC,")
print("renames columns via the provided column_map (identity here, since CSV")
print("columns already match canonical names), and builds a TimeSeries. The")
print("output values match the CSV exactly:")
print(f"  demand = {list(ts.demand.values)}  (CSV: 100, 150, 120)")
print(f"  solar  = {list(ts.productions['solar'].values)}  (CSV: 40, 80, 60)")
print(f"  wind   = {list(ts.productions['wind'].values)}  (CSV: 60, 70, 60)")

# ---------------------------------------------------------------------------
# Part 2 — Run match() on the reader result
# ---------------------------------------------------------------------------
print("\n" + "=" * 68)
print("PART 2 — Engine match on reader output")
print("=" * 68)

result = match(ts)

print()
print(f"Coverage per hour (kW):")
for col in result.coverage.columns:
    print(f"  {col}: {result.coverage[col].values}")
print(f"Shortfall per hour (kW): {result.shortfall.values}")
print(f"Excess per hour (kW):    {result.excess.values}")

print()
print("Explanation:")
print()
print("Hour 0: demand=100, solar=40, wind=60 -> total production = 100.")
print("  Production exactly covers demand. shortfall=0, excess=0.")
print()
print("Hour 1: demand=150, solar=80, wind=70  -> total production = 150.")
print("  Production exactly covers demand. shortfall=0, excess=0.")
print()
print("Hour 2: demand=120, solar=60, wind=60  -> total production = 120.")
print("  Production exactly covers demand. shortfall=0, excess=0.")
print()
print("In every hour, solar + wind = demand, so the engine dispatches all")
print("production to cover the load with zero shortfall and zero excess.")

# ---------------------------------------------------------------------------
# Part 3 — Narrow CSV reader (temp files)
# ---------------------------------------------------------------------------
print("\n" + "=" * 68)
print("PART 3 — Narrow CSV reader (one file per source)")
print("=" * 68)

tmp = Path(tempfile.mkdtemp(prefix="scratch_03_narrow_"))
print(f"\nTemp directory: {tmp}")

# Build 2-timestamp narrow CSV files
timestamps = ["2025-01-01T00:00:00Z", "2025-01-01T01:00:00Z"]
demand_vals = [100, 150]
wind_vals = [60, 70]

demand_csv = tmp / "demand.csv"
wind_csv = tmp / "wind.csv"

demand_csv.write_text("timestamp,value\n" + "\n".join(
    f"{t},{v}" for t, v in zip(timestamps, demand_vals)
))
wind_csv.write_text("timestamp,value\n" + "\n".join(
    f"{t},{v}" for t, v in zip(timestamps, wind_vals)
))

print(f"  demand.csv:\n{demand_csv.read_text()}")
print(f"  wind.csv:\n{wind_csv.read_text()}")

narrow_reader = CsvReader.from_narrow(
    demand_path=str(demand_csv),
    timestamp_col="timestamp",
    value_col="value",
    production_paths={"wind": str(wind_csv)},
    sources_meta={
        "demand": SourceMeta(
            name="Demand",
            category="demand",
            flexibility="inflexible",
        ),
        "wind": SourceMeta(
            name="Wind",
            category="production",
            flexibility="inflexible",
        ),
    },
)

narrow_ts = narrow_reader.read()

print(f"\nNarrow reader timestamps: {len(narrow_ts.timestamps)}")
print(f"Demand values (kW):       {narrow_ts.demand.values}")
for key, series in narrow_ts.productions.items():
    print(f"  {key} values (kW):      {series.values}")

print()
print("Explanation: Narrow mode is for when each energy source has its own")
print("CSV file (e.g., one file for demand, another for wind). CsvReader")
print("loads the demand file to establish the canonical timestamp index,")
print("then loads each production file and aligns (reindexes) production")
print("values to the demand timestamps. Here we read 2 hours of demand")
print("and wind from two separate files and get the correct paired values.")

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
shutil.rmtree(tmp)
print(f"\nCleaned up temp directory: {tmp}")

print("\n" + "=" * 68)
print("Done.")
print("=" * 68)