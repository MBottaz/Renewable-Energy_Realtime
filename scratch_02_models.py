"""
scratch_02_models.py — Exploring energy_match data models

Covers SourceMeta, TimeSeries, and MatchResult step by step.
Run from repo root:  uv run python scratch_02_models.py
"""

import pandas as pd
from datetime import datetime, timezone

from energy_match.models import SourceMeta, TimeSeries, MatchResult
from energy_match.engine import match


# ==========================================================================
# PART A — SourceMeta
# ==========================================================================
print("=" * 72)
print("PART A — SourceMeta: describing energy sources")
print("=" * 72)

# --- 1. Create three source metadata objects ---

solar_meta = SourceMeta(
    name="Solar",
    category="production",
    flexibility="inflexible",
)

hydro_meta = SourceMeta(
    name="Hydro Reservoir",
    category="production",
    flexibility="flexible",
)

battery_meta = SourceMeta(
    name="Battery",
    category="production",
    flexibility="storage",
    capacity_kwh=200.0,
    max_charge_rate_kw=50.0,
    max_discharge_rate_kw=50.0,
    initial_soc_kwh=100.0,
    roundtrip_efficiency=0.90,
)

# --- 2. Print each and explain flexibility ---

print("\n--- Source 1: Inflexible (Solar) ---")
print(solar_meta)
print("\n  flexibility='inflexible':")
print("    Must-run sources — they generate whenever the resource is available")
print("    (sun shines, wind blows). The grid must absorb whatever they produce;")
print("    they cannot be dialed up/down on demand.")

print("\n--- Source 2: Flexible (Hydro Reservoir) ---")
print(hydro_meta)
print("\n  flexibility='flexible':")
print("    Dispatchable sources — output can be increased or decreased on command.")
print("    Used to fill the gap between inflexible generation and demand.")

print("\n--- Source 3: Storage (Battery) ---")
print(battery_meta)
print("\n  flexibility='storage':")
print("    Can both charge (absorb excess) and discharge (cover shortfall).")
print("    Requires 5 extra fields: capacity_kwh, max_charge_rate_kw,")
print("    max_discharge_rate_kw, initial_soc_kwh, roundtrip_efficiency.")

# --- 3. Demonstrate validation error ---

print("\n--- Validation: missing storage fields ---")
print("  Trying to create a Battery without capacity_kwh...")
try:
    bad_battery = SourceMeta(
        name="Battery",
        category="production",
        flexibility="storage",
        # Omitted: capacity_kwh  ← should trigger ValueError
        max_charge_rate_kw=50.0,
        max_discharge_rate_kw=50.0,
        initial_soc_kwh=100.0,
        roundtrip_efficiency=0.90,
    )
except ValueError as e:
    print(f"  Caught expected ValueError: {e}")
    print("  ✓ Storage validation works: all 5 storage fields are required.")

print("\n  (All 5 required storage fields: capacity_kwh, max_charge_rate_kw,")
print("   max_discharge_rate_kw, initial_soc_kwh, roundtrip_efficiency)")


# ==========================================================================
# PART B — TimeSeries
# ==========================================================================
print("\n" + "=" * 72)
print("PART B — TimeSeries: the universal input container")
print("=" * 72)

# --- 4. Create a full TimeSeries from scratch ---

timestamps = pd.DatetimeIndex(
    [
        datetime(2025, 6, 1, 0, tzinfo=timezone.utc),
        datetime(2025, 6, 1, 1, tzinfo=timezone.utc),
        datetime(2025, 6, 1, 2, tzinfo=timezone.utc),
    ]
)

demand = pd.Series([100.0, 120.0, 80.0], index=timestamps, dtype="float64")
productions = {
    "Solar": pd.Series([0.0, 10.0, 40.0], index=timestamps, dtype="float64"),
    "Wind": pd.Series([60.0, 50.0, 30.0], index=timestamps, dtype="float64"),
}
sources_meta = {
    "demand": SourceMeta(name="demand", category="demand", flexibility="inflexible"),
    "Solar": solar_meta,
    "Wind": SourceMeta(
        name="Wind", category="production", flexibility="inflexible"
    ),
}

ts = TimeSeries(
    timestamps=timestamps,
    demand=demand,
    productions=productions,
    sources_meta=sources_meta,
)

# --- 5. Print contents ---

print("\n--- TimeSeries contents ---")
print(f"\n  Timestamps ({len(ts.timestamps)} hours):")
for t in ts.timestamps:
    print(f"    {t}")

print(f"\n  Demand series (kW):")
for t, v in zip(ts.timestamps, ts.demand):
    print(f"    {t}  →  {v:.1f} kW")

print(f"\n  Production keys: {list(ts.productions.keys())}")

print(f"\n  Solar production:")
for t, v in zip(ts.timestamps, ts.productions["Solar"]):
    print(f"    {t}  →  {v:.1f} kW")

print(f"\n  Wind production:")
for t, v in zip(ts.timestamps, ts.productions["Wind"]):
    print(f"    {t}  →  {v:.1f} kW")

# --- 6. Explain validation invariants ---

print("\n--- Validation invariants ---")
print("  TimeSeries.__post_init__ enforces:")
print("    1. Timestamps: hourly frequency, monotonically increasing,")
print("       tz-aware UTC (no naive datetimes)")
print("    2. Every pd.Series shares the same DatetimeIndex")
print("    3. All series are float64 (no ints, no objects)")
print("    4. No NaN in demand or productions (use 0.0 for missing)")
print("    5. sources_meta must cover 'demand' and every production key")
print("    6. No duplicate timestamps, no gaps in the hourly sequence")

# --- 7. Demonstrate from_wide_dataframe ---

print("\n--- TimeSeries.from_wide_dataframe() ---")

wide_df = pd.DataFrame(
    {
        "demand": [100.0, 120.0, 80.0],
        "Solar": [0.0, 10.0, 40.0],
        "Wind": [60.0, 50.0, 30.0],
    },
    index=timestamps,
)
wide_df.index.name = "timestamp"

print("\n  Input DataFrame:")
print(wide_df.to_string())

ts_from_df = TimeSeries.from_wide_dataframe(wide_df, sources_meta)

print(f"\n  Constructed TimeSeries timestamps: {list(ts_from_df.timestamps)}")
print(f"  Demand: {list(ts_from_df.demand.values)}")
print(f"  Solar:  {list(ts_from_df.productions['Solar'].values)}")
print(f"  Wind:   {list(ts_from_df.productions['Wind'].values)}")
print("  ✓ from_wide_dataframe works!")


# ==========================================================================
# PART C — MatchResult
# ==========================================================================
print("\n" + "=" * 72)
print("PART C — MatchResult: the engine output")
print("=" * 72)

# --- 8. Create an exact-match scenario ---

# Demand:       100, 120, 80
# Solar:          0,  10, 40
# Wind:          60,  50, 30
# Total prod:    60,  60, 70
# Shortfall:     40,  60, 10
# Excess:         0,   0,  0   (exact match for the infeasible part — no surplus)

# Build a scenario where some hours have excess and some are tight
# Using the ts we already have, which has total production < demand always.
# To also see excess, let's make a richer scenario via match().

print("\n--- Running match() on our TimeSeries ---")
result: MatchResult = match(ts)
# With Solar+Wind both inflexible, dispatch just uses them as-is,
# so coverage = production, shortfall = demand - production.

# --- 9. Print coverage, shortfall, excess ---

print(f"\n  Coverage per source (kW):")
print(result.coverage.to_string())

print(f"\n  Shortfall (kW):")
for t, v in zip(result.timestamps, result.shortfall):
    print(f"    {t}  →  {v:.1f} kW")

print(f"\n  Excess (kW):")
for t, v in zip(result.timestamps, result.excess):
    print(f"    {t}  →  {v:.1f} kW")

# --- 10. Print to_dataframe() and explain invariant ---

print("\n--- MatchResult.to_dataframe() ---")
df_result = result.to_dataframe()
print(df_result.to_string())

print("\n  Core invariant:  demand == coverage.sum(axis=1) + shortfall")
print("  Meaning: every kW of demand is either covered by a production source")
print("  or recorded as shortfall. There is no 'missing' energy.")

# --- 11. Check invariant ---

coverage_sum = result.coverage.sum(axis=1)
invariant_holds = (
    (result.demand - coverage_sum - result.shortfall).abs().max() < 1e-3
)
print(f"\n  demand:                   {list(result.demand.values)}")
print(f"  coverage.sum(axis=1):     {list(coverage_sum.values)}")
print(f"  shortfall:                {list(result.shortfall.values)}")
print(f"  demand == coverage + shortfall?")
print(f"    INNER check: {list(result.demand.values)} == {list((coverage_sum + result.shortfall).values)}")
print(f"    INVARIANT HOLDS: demand == coverage + shortfall  →  {invariant_holds}")

# Double-check: row by row
print("\n  Per-timestamp verification:")
for t, d, c, s in zip(result.timestamps, result.demand, coverage_sum, result.shortfall):
    ok = abs(d - c - s) < 1e-3
    print(f"    {t}  {d:.1f} = {c:.1f} + {s:.1f}  {'✓' if ok else '✗'}")

print("\n" + "=" * 72)
print("All models demonstrated successfully.")
print("=" * 72)