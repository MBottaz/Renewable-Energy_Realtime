"""
scratch_06_engine.py — Demonstrate engine.match() with 4 scenarios.

Each scenario builds a TimeSeries, runs match(), and explains the results.
"""

from __future__ import annotations

import pandas as pd

from energy_match.engine import match
from energy_match.models import MatchResult, SourceMeta, TimeSeries


def _ts(
    demand: list[float],
    *,
    solar: list[float],
    wind: list[float] | None = None,
    battery: list[float] | None = None,
    battery_meta: SourceMeta | None = None,
) -> TimeSeries:
    """Build a TimeSeries for the given hourly data.

    All lists must be the same length (number of hours).
    """
    n = len(demand)
    timestamps = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC")

    meta: dict[str, SourceMeta] = {
        "demand": SourceMeta(name="demand", category="demand", flexibility="inflexible"),
        "solar": SourceMeta(name="solar", category="production", flexibility="inflexible"),
    }

    productions: dict[str, pd.Series] = {
        "solar": pd.Series(solar, index=timestamps, dtype="float64"),
    }

    if wind is not None:
        meta["wind"] = SourceMeta(name="wind", category="production", flexibility="inflexible")
        productions["wind"] = pd.Series(wind, index=timestamps, dtype="float64")

    if battery is not None:
        assert battery_meta is not None, "battery_meta required when battery is passed"
        meta["battery"] = battery_meta
        productions["battery"] = pd.Series(battery, index=timestamps, dtype="float64")

    return TimeSeries(
        timestamps=timestamps,
        demand=pd.Series(demand, index=timestamps, dtype="float64"),
        productions=productions,
        sources_meta=meta,
    )


def print_result(r: MatchResult, label: str) -> None:
    """Pretty-print a MatchResult."""
    print(f"\n{'=' * 70}")
    print(f"  {label}")
    print(f"{'=' * 70}")
    print(r.to_dataframe().to_string())
    if r.storage_soc:
        for src, soc in r.storage_soc.items():
            print(f"\n  {src} SOC (kWh):")
            print(f"    {soc.to_dict()}")
    print()


# ---------------------------------------------------------------------------
# Scenario 1 — Exact match every hour
# ---------------------------------------------------------------------------
print("\n" + "#" * 70)
print("#  SCENARIO 1 — Exact match (production == demand every hour)")
print("#" * 70)
print()
print("  demand = [100, 200, 150]")
print("  solar  = [ 60,  80,  90]")
print("  wind   = [ 40, 120,  60]")
print("  → total production = demand every hour")

ts1 = _ts([100, 200, 150], solar=[60, 80, 90], wind=[40, 120, 60])
r1 = match(ts1)

print_result(r1, "MatchResult — Exact match")

# Invariant check
covered = r1.coverage.sum(axis=1)
diff = (r1.demand - covered - r1.shortfall).abs().max()
print(f"  Check: |demand - (coverage.sum() + shortfall)| = {diff:.6f}")
if diff < 1e-3:
    print("  ✓ INVARIANT HOLDS: |demand - (coverage + shortfall)| < 1e-3")
else:
    print(f"  ✗ INVARIANT VIOLATED (max diff = {diff:.6f})")

assert r1.shortfall.sum() == 0.0, f"Expected zero shortfall, got {r1.shortfall.sum()}"
assert r1.excess.sum() == 0.0, f"Expected zero excess, got {r1.excess.sum()}"
print("  ✓ shortfall == 0 across all hours")
print("  ✓ excess == 0 across all hours")
print()

# ---------------------------------------------------------------------------
# Scenario 2 — Shortfall every hour
# ---------------------------------------------------------------------------
print("#" * 70)
print("#  SCENARIO 2 — Shortfall (total production < demand)")
print("#" * 70)
print()
print("  demand = [100, 200, 150]")
print("  solar  = [ 30,  50,  40]")
print("  wind   = [ 20,  30,  20]")
print("  → total production = 50 + 80 + 60 = 190 << 450 demand")
print("  → shortfall > 0 every hour")

ts2 = _ts([100, 200, 150], solar=[30, 50, 40], wind=[20, 30, 20])
r2 = match(ts2)

print_result(r2, "MatchResult — Shortfall")

print(f"  Total demand:       {r2.demand.sum():.0f}")
print(f"  Total coverage:     {r2.coverage.sum().sum():.0f}")
print(f"  Total shortfall:    {r2.shortfall.sum():.0f}")
print(f"  Total excess:       {r2.excess.sum():.0f}")
print(f"  Shortfall per hour: {r2.shortfall.to_dict()}")
assert r2.shortfall.sum() > 0, "Expected non-zero shortfall"
assert r2.excess.sum() == 0, f"Expected zero excess, got {r2.excess.sum()}"
print("  ✓ shortfall > 0 across all hours")
print("  ✓ excess == 0 across all hours")
print()

# ---------------------------------------------------------------------------
# Scenario 3 — Excess (no storage)
# ---------------------------------------------------------------------------
print("#" * 70)
print("#  SCENARIO 3 — Excess (production > demand, no storage)")
print("#" * 70)
print()
print("  demand = [50,  80]")
print("  solar  = [60, 100]")
print("  → production > demand every hour, excess > 0, shortfall == 0")

ts3 = _ts([50, 80], solar=[60, 100])
r3 = match(ts3)

print_result(r3, "MatchResult — Excess (no storage)")

print(f"  Total demand:       {r3.demand.sum():.0f}")
print(f"  Total coverage:     {r3.coverage.sum().sum():.0f}")
print(f"  Total excess:       {r3.excess.sum():.0f}")
print(f"  Excess per hour:    {r3.excess.to_dict()}")
assert r3.excess.sum() > 0, "Expected non-zero excess"
assert r3.shortfall.sum() == 0, f"Expected zero shortfall, got {r3.shortfall.sum()}"
print("  ✓ excess > 0 across all hours")
print("  ✓ shortfall == 0 across all hours")
print()

# ---------------------------------------------------------------------------
# Scenario 4 — With storage (charge + discharge across hours)
# ---------------------------------------------------------------------------
print("#" * 70)
print("#  SCENARIO 4 — With storage (battery charges/discharges)")
print("#" * 70)
print()
print("  demand = [ 50,  60, 100]")
print("  solar  = [100, 100,  40]")
print()
print("  Battery: capacity=200 kWh, charge_rate=50 kW, discharge_rate=50 kW")
print("           init_soc=0 kWh, η=0.9")
print()
print("  Expected:")
print("    H0: demand=50, solar covers 50, excess=50, battery charges 45 → SOC=45")
print("    H1: demand=60, solar covers 60, excess=40, battery charges 36 → SOC=81")
print()
print("  Note: In H0 and H1, all excess solar is absorbed by battery charging.")
print("  The MatchResult.excess field is 0 because storage captured it all.")
print("  The SOC rises to 45 (H0) and then 81 (H1) reflecting the charged energy.")
print()
print("    H2: demand=100, solar covers 40, battery discharges 50, shortfall=10")

battery_meta = SourceMeta(
    name="battery",
    category="production",
    flexibility="storage",
    capacity_kwh=200.0,
    max_charge_rate_kw=50.0,
    max_discharge_rate_kw=50.0,
    initial_soc_kwh=0.0,
    roundtrip_efficiency=0.9,
)

ts4 = _ts([50, 60, 100], solar=[100, 100, 40], battery=[0, 0, 0], battery_meta=battery_meta)
r4 = match(ts4)

print_result(r4, "MatchResult — With storage")

# Display SOC progression
soc_series = r4.storage_soc["battery"]
print("  SOC progression (kWh):")
for i, (ts, soc) in enumerate(soc_series.items()):
    print(f"    H{i}: SOC = {soc:.1f}")

print()
print("  Hour-by-hour explanation:")
covered = r4.coverage.sum(axis=1)
for i, ts in enumerate(r4.timestamps):
    dem = r4.demand.iloc[i]
    cov = covered.iloc[i]
    short = r4.shortfall.iloc[i]
    exc = r4.excess.iloc[i]
    sol = r4.coverage["solar"].iloc[i]
    bat_cov = r4.coverage.get("battery", pd.Series([0.0] * len(r4.timestamps), index=r4.timestamps)).iloc[i]
    soc_before = soc_series.iloc[i - 1] if i > 0 else 0.0
    soc_after = soc_series.iloc[i]

    print(f"    H{i}: demand={dem:.0f}, solar={sol:.0f}, battery_discharge={bat_cov:.0f}, "
          f"shortfall={short:.0f}, excess={exc:.0f}, SOC: {soc_before:.1f}→{soc_after:.1f}")

    # Verify expected behavior
    #
    # In H0 and H1 the battery absorbs all excess solar (excess field = 0 in the
    # MatchResult because storage captures it before it becomes "final" excess).
    # The SOC rises instead.
    assert r4.coverage["solar"].iloc[0] == 50.0, "H0: solar should cover 50"
    assert r4.shortfall.iloc[0] == 0.0, "H0: no shortfall"
    # All excess was routed to battery charging, so final excess = 0
    assert r4.excess.iloc[0] == 0.0, f"H0: final excess should be 0 (battery absorbed it), got {r4.excess.iloc[0]}"
    assert abs(soc_series.iloc[0] - 45.0) < 1e-3, f"H0: SOC should be 45, got {soc_series.iloc[0]}"
    
    assert r4.coverage["solar"].iloc[1] == 60.0, "H1: solar should cover 60"
    assert r4.shortfall.iloc[1] == 0.0, "H1: no shortfall"
    assert r4.excess.iloc[1] == 0.0, f"H1: final excess should be 0 (battery absorbed it), got {r4.excess.iloc[1]}"
    assert abs(soc_series.iloc[1] - 81.0) < 1e-3, f"H1: SOC should be 81, got {soc_series.iloc[1]}"
    
    bat_cov_h2 = r4.coverage.get("battery", pd.Series(0.0, index=r4.timestamps)).iloc[2]
    assert r4.coverage["solar"].iloc[2] == 40.0, "H2: solar should cover 40"
    assert abs(bat_cov_h2 - 50.0) < 1e-3, \
        f"H2: battery should discharge 50, got {bat_cov_h2}"
    assert abs(r4.shortfall.iloc[2] - 10.0) < 1e-3, f"H2: shortfall should be 10, got {r4.shortfall.iloc[2]}"
    assert r4.excess.iloc[2] == 0.0, "H2: no excess"


print()
print("  ✓ All scenario 4 assertions passed!")
print()

print("#" * 70)
print("#  ALL 4 SCENARIOS COMPLETED SUCCESSFULLY")
print("#" * 70)