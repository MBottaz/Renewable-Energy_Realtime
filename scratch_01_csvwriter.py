"""Scratch 01: manually construct a MatchResult and write via CsvWriter.

Teaches:
  - How MatchResult is structured (timestamps, demand, coverage, shortfall, excess)
  - How CsvWriter produces coverage.csv, shortfall.csv, excess.csv, summary.json
  - The invariant: demand == coverage.sum(axis=1) + shortfall
"""

import json
import shutil
from pathlib import Path

import pandas as pd

from energy_match import CsvWriter, MatchResult

# ---------------------------------------------------------------------------
# 1. Prepare output directory
# ---------------------------------------------------------------------------
out = Path("/tmp/scratch_01_output")
if out.exists():
    shutil.rmtree(out)

print("=" * 68)
print("Scratch 01: CsvWriter — Exploring the MatchResult output format")
print("=" * 68)

# ---------------------------------------------------------------------------
# 2. Build a MatchResult — exact-match scenario
# ---------------------------------------------------------------------------
# Three hourly timestamps, tz-aware UTC (matching the package convention).
timestamps = pd.DatetimeIndex(
    [
        "2025-01-01 00:00:00+00:00",
        "2025-01-01 01:00:00+00:00",
        "2025-01-01 02:00:00+00:00",
    ]
)

# Demand (kW) for each hour
demand = pd.Series([100.0, 200.0, 150.0], index=timestamps, name="demand")

# Coverage: which source produced how much each hour (kW)
# Exact match — coverage sums to demand, so shortfall and excess are zero.
coverage = pd.DataFrame(
    {"solar": [40.0, 80.0, 60.0], "wind": [60.0, 120.0, 90.0]},
    index=timestamps,
)

# Shortfall: demand not covered by renewable production (kW)
shortfall = pd.Series([0.0, 0.0, 0.0], index=timestamps, name="shortfall")

# Excess: renewable production beyond demand (kW)
excess = pd.Series([0.0, 0.0, 0.0], index=timestamps, name="excess")

result = MatchResult(
    timestamps=timestamps,
    demand=demand,
    coverage=coverage,
    shortfall=shortfall,
    excess=excess,
)

print("\n[MatchResult constructed]")
print(f"  Timestamps: {len(timestamps)} hours")
print(f"  Sources: {list(coverage.columns)}")
print(f"  Demand (kW): {demand.values}")
print(f"  Coverage sum per hour (kW): {coverage.sum(axis=1).values}")
print(f"  Shortfall (kW): {shortfall.values}")
print(f"  Excess (kW): {excess.values}")

# Verify invariant: demand == coverage.sum(axis=1) + shortfall
covered = coverage.sum(axis=1)
invariant = (demand == covered + shortfall).all()
print(f"\n  Invariant check: demand == coverage.sum(axis=1) + shortfall? {invariant}")

# ---------------------------------------------------------------------------
# 3. Write via CsvWriter
# ---------------------------------------------------------------------------
writer = CsvWriter()
writer.write(result, out)

print(f"\n  -> Wrote 4 files to {out}/")

# ---------------------------------------------------------------------------
# 4. Read back and explain every file
# ---------------------------------------------------------------------------

# --- coverage.csv -----------------------------------------------------------
print("\n" + "-" * 68)
print("FILE 1: coverage.csv")
print("-" * 68)
print("""
  What it is: A CSV table showing how much each renewable source produced
  at every timestamp. Every row is one hour.

  Columns:
    timestamp  — the UTC hour
    solar      — solar generation in kW
    wind       — wind generation in kW

  If more sources existed (e.g. hydro, biomass), each would have its own column.
  Coverage tells you *which* sources met the demand and by how much.
""")

cov_path = out / "coverage.csv"
print(cov_path.read_text())

# --- shortfall.csv ----------------------------------------------------------
print("-" * 68)
print("FILE 2: shortfall.csv")
print("-" * 68)
print("""
  What it is: A CSV table showing how much demand was NOT covered by
  renewable sources at each hour.

  Columns:
    timestamp     — the UTC hour
    shortfall_mw  — unmet demand in megawatts (1 MW = 1000 kW)

  In our exact-match scenario shortfall is 0 everywhere. In a real run
  this is the gap that fossil backup (or storage) must fill.
""")

short_path = out / "shortfall.csv"
print(short_path.read_text())

# --- excess.csv -------------------------------------------------------------
print("-" * 68)
print("FILE 3: excess.csv")
print("-" * 68)
print("""
  What it is: A CSV table showing renewable production that exceeded demand
  at each hour — energy that must be curtailed or stored.

  Columns:
    timestamp  — the UTC hour
    excess_mw  — surplus generation in megawatts (1 MW = 1000 kW)

  In our exact-match scenario excess is 0 everywhere. In a real run this
  would be non-zero when renewables produce more than the grid consumes.
""")

exc_path = out / "excess.csv"
print(exc_path.read_text())

# --- summary.json -----------------------------------------------------------
print("-" * 68)
print("FILE 4: summary.json")
print("-" * 68)
print("""
  What it is: A JSON file with aggregate statistics for the whole run.

  Fields:
    total_demand_mwh      — total energy demand over the period (MWh)
    total_renewable_mwh   — total renewable energy produced (MWh)
    renewable_share       — fraction of demand met by renewables (0.0–1.0)
    total_shortfall_mwh   — total unmet demand (MWh)
    total_excess_mwh      — total surplus generation (MWh)
    peak_demand_mw        — highest hourly demand (MW)
    peak_shortfall_mw     — highest hourly shortfall (MW)
    num_hours             — number of hours in the simulation
    sources               — list of renewable source names

  Note: All values are in MW / MWh (divide by 1000 from internal kW / kWh).
""")

sum_path = out / "summary.json"
print(json.dumps(json.loads(sum_path.read_text()), indent=2))

# ---------------------------------------------------------------------------
# 5. Recap
# ---------------------------------------------------------------------------
print("\n" + "=" * 68)
print("Key takeaway")
print("=" * 68)
print("""
  The CsvWriter produces 4 files per match run:

  1. coverage.csv   — per-source production (wide format, one column per source)
  2. shortfall.csv  — demand not met by renewables
  3. excess.csv     — renewable production beyond demand
  4. summary.json   — aggregate stats (MWh / MW)

  Core invariant (checked by MatchResult.__post_init__):
      demand = coverage.sum(axis=1) + shortfall

  Every hour, the sum of all source coverage columns PLUS any shortfall
  exactly equals the demand. Excess is the surplus on top.
""")