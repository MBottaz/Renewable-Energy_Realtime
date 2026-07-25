"""
Scratch 05: dispatch_hour() — core matching logic with 5 scenarios.

Demonstrates how the engine dispatches inflexible, storage, and flexible sources
to meet demand, tracks state-of-charge, and preserves the invariant
dispatched_non_storage + shortfall == demand.
"""

from energy_match.dispatch import dispatch_hour
from energy_match.models import SourceMeta


# ---------------------------------------------------------------------------
# Helper factories (matching the test suite conventions)
# ---------------------------------------------------------------------------

def _inflexible(name: str) -> SourceMeta:
    return SourceMeta(name=name, category="production", flexibility="inflexible")


def _flexible(name: str) -> SourceMeta:
    return SourceMeta(name=name, category="production", flexibility="flexible")


def _storage(name: str, **overrides: float) -> SourceMeta:
    defaults: dict[str, float] = {
        "capacity_kwh": 200.0,
        "max_charge_rate_kw": 50.0,
        "max_discharge_rate_kw": 50.0,
        "initial_soc_kwh": 0.0,
        "roundtrip_efficiency": 0.9,
    }
    defaults.update(overrides)
    return SourceMeta(
        name=name,
        category="production",
        flexibility="storage",
        **defaults,
    )


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

SEP = "=" * 72


def heading(text: str) -> None:
    """Print a section heading."""
    print(f"\n{SEP}")
    print(f"  {text}")
    print(SEP)


def subheading(text: str) -> None:
    """Print a sub-heading."""
    print(f"\n  --- {text} ---")


def check_invariant(
    meta: dict[str, SourceMeta],
    coverage: dict[str, float],
    shortfall: float,
    demand: float,
    label: str = "after discharge step",
) -> None:
    """Print two invariant checks and explain the difference.

    Invariant A (non-storage only): sum of non-storage coverage + shortfall == demand.
        Fails when storage discharge covers part of demand, because storage is
        excluded from dispatched_non_storage.

    Invariant B (total including storage): total_dispatched + shortfall == demand.
        Always holds — it's an algebraic consequence of how dispatch_hour decrements
        remaining_demand and returns shortfall = max(0, remaining_demand).
    """
    total_dispatched = sum(coverage.values())
    non_storage_dispatched = sum(
        v for name, v in coverage.items()
        if meta.get(name) is None or meta[name].flexibility != "storage"
    )
    storage_dispatched = total_dispatched - non_storage_dispatched

    a_ok = abs(non_storage_dispatched + shortfall - demand) < 1e-9
    b_ok = abs(total_dispatched + shortfall - demand) < 1e-9

    print(f"\n  Invariant checks ({label}):")
    print(f"    A. dispatched_non_storage({non_storage_dispatched:.0f}) + shortfall({shortfall:.0f}) == demand({demand:.0f})")
    print(f"       => {'PASS \u2713' if a_ok else 'FAIL \u2717'}")
    if not a_ok and storage_dispatched > 0:
        print(f"       -> Storage discharged {storage_dispatched:.0f} kW (not counted in non-storage)")
        print(f"          Missing: {demand - (non_storage_dispatched + shortfall):.0f} = storage discharge")
    print(f"    B. total_dispatched({total_dispatched:.0f}) + shortfall({shortfall:.0f}) == demand({demand:.0f})")
    print(f"       => {'PASS \u2713' if b_ok else 'FAIL \u2717'}  (always holds by construction)")


# ---------------------------------------------------------------------------
# Scenario 1 — Priority among inflexible sources
# ---------------------------------------------------------------------------

def scenario_1() -> None:
    heading("Scenario 1 \u2014 Priority among inflexible sources")

    meta = {
        "a": _inflexible("a"),
        "b": _inflexible("b"),
    }
    order = ["a", "b"]
    productions = {"a": 60.0, "b": 60.0}
    demand = 100.0

    print(f"\n  Setup:")
    print(f"    Demand:          {demand:.0f} kW")
    print(f"    Production:       a = {productions['a']:.0f} kW,  b = {productions['b']:.0f} kW")
    print(f"    Dispatch order:   {order}")
    print(f"    No storage       (storage_state = {{}})")

    coverage, new_storage_state, shortfall, excess = dispatch_hour(
        demand_kw=demand,
        productions_kw=productions,
        dispatch_order=order,
        storage_state={},
        sources_meta=meta,
    )

    print(f"\n  Step-by-step:")
    print(f"    1. Inflexible 'a' (first in order):")
    print(f"       dispatch = min(60, 100) = 60")
    print(f"       remaining_demand = 100 - 60 = 40")
    print(f"    2. Inflexible 'b':")
    print(f"       dispatch = min(60, 40) = 40")
    print(f"       remaining_demand = 40 - 40 = 0")
    print(f"    3. No storage to discharge.")
    print(f"    4. No flexible sources.")
    print(f"       shortfall = 0")

    print(f"\n  Result:")
    print(f"    Coverage:  a = {coverage['a']:.0f},  b = {coverage['b']:.0f}")
    print(f"    Shortfall: {shortfall:.0f} kW")
    print(f"    Excess:    {excess:.0f} kW")
    print(f"      (total production {productions['a'] + productions['b']:.0f}"
          f" - dispatched {coverage['a'] + coverage['b']:.0f})")

    check_invariant(meta, coverage, shortfall, demand)


# ---------------------------------------------------------------------------
# Scenario 2 — Storage discharge
# ---------------------------------------------------------------------------

def scenario_2() -> None:
    heading("Scenario 2 \u2014 Storage discharge")

    meta = {
        "solar": _inflexible("solar"),
        "battery": _storage("battery", initial_soc_kwh=80.0),
    }
    order = ["solar", "battery"]
    productions = {"solar": 40.0}
    demand = 100.0
    init_soc = {"battery": 80.0}

    print(f"\n  Setup:")
    print(f"    Demand:              {demand:.0f} kW")
    print(f"    Production:          solar = {productions['solar']:.0f} kW")
    print(f"    Dispatch order:      {order}")
    print(f"    Battery SOC:         {init_soc['battery']:.0f} kWh (init)")
    print(f"    Battery limits:      max_discharge = 50 kW, capacity = 200 kWh")

    coverage, new_storage, shortfall, excess = dispatch_hour(
        demand_kw=demand,
        productions_kw=productions,
        dispatch_order=order,
        storage_state=init_soc,
        sources_meta=meta,
    )

    print(f"\n  Step-by-step:")
    print(f"    1. Inflexible 'solar':")
    print(f"       dispatch = min(40, 100) = 40")
    print(f"       remaining_demand = 100 - 40 = 60")
    print(f"    2. Storage 'battery' discharges:")
    print(f"       SOC = 80, max_discharge = 50, need = 60")
    print(f"       discharge = min(60, 50, 80) = 50")
    print(f"       remaining_demand = 60 - 50 = 10")
    print(f"       new SOC = 80 - 50 = 30")
    print(f"    3. No flexible sources.")
    print(f"       shortfall = 10")

    print(f"\n  Result:")
    print(f"    Coverage:  solar = {coverage['solar']:.0f},  battery = {coverage['battery']:.0f}")
    print(f"    New SOC:   {new_storage['battery']:.0f} kWh")
    print(f"    Shortfall: {shortfall:.0f} kW")
    print(f"    Excess:    {excess:.0f} kW")

    check_invariant(meta, coverage, shortfall, demand)


# ---------------------------------------------------------------------------
# Scenario 3 — Storage charge from excess
# ---------------------------------------------------------------------------

def scenario_3() -> None:
    heading("Scenario 3 \u2014 Storage charge from excess")

    meta = {
        "solar": _inflexible("solar"),
        "battery": _storage("battery"),
    }
    order = ["solar", "battery"]
    productions = {"solar": 200.0}
    demand = 100.0
    init_soc = {"battery": 0.0}

    print(f"\n  Setup:")
    print(f"    Demand:              {demand:.0f} kW")
    print(f"    Production:          solar = {productions['solar']:.0f} kW")
    print(f"    Dispatch order:      {order}")
    print(f"    Battery SOC:         {init_soc['battery']:.0f} kWh (init)")
    print(f"    Battery params:      capacity = 200 kWh, max_charge = 50 kW, {chr(951)} = 0.9")

    coverage, new_storage, shortfall, excess = dispatch_hour(
        demand_kw=demand,
        productions_kw=productions,
        dispatch_order=order,
        storage_state=init_soc,
        sources_meta=meta,
    )

    print(f"\n  Step-by-step:")
    print(f"    1. Inflexible 'solar' covers demand:")
    print(f"       dispatch = min(200, 100) = 100")
    print(f"       remaining_demand = 100 - 100 = 0")
    print(f"    2. No storage discharge needed (remaining_demand = 0).")
    print(f"    3. No flexible sources needed.")
    print(f"       shortfall = 0")
    print(f"    4. Excess computation:")
    print(f"       total_production = 200")
    print(f"       non_storage_dispatched = 100")
    print(f"       excess = 200 - 100 = 100")
    print(f"    5. Storage charging (reverse priority):")
    print(f"       headroom = 200 - 0 = 200")
    print(f"       max_charge_by_capacity = 200 / 0.9 = 222.2")
    print(f"       charge_grid = min(100, 50, 222.2) = 50")
    print(f"       soc_stored = 50 {chr(215)} 0.9 = 45")
    print(f"       new SOC = 0 + 45 = 45")
    print(f"       remaining excess = 100 - 50 = 50")

    print(f"\n  Result:")
    print(f"    Coverage:         solar = {coverage['solar']:.0f}")
    print(f"    New SOC:          {new_storage['battery']:.0f} kWh")
    print(f"    Shortfall:        {shortfall:.0f} kW")
    print(f"    Excess:           {excess:.0f} kW (curtailed)")

    check_invariant(meta, coverage, shortfall, demand)


# ---------------------------------------------------------------------------
# Scenario 4 — Full cycle (charge then discharge in 2 calls)
# ---------------------------------------------------------------------------

def scenario_4() -> None:
    heading("Scenario 4 \u2014 Full cycle: charge then discharge (two consecutive hours)")

    meta = {
        "solar": _inflexible("solar"),
        "battery": _storage("battery"),
    }
    order = ["solar", "battery"]

    print(f"\n  Setup:")
    print(f"    Sources:     solar (inflexible), battery (capacity=200, {chr(951)}=0.9)")
    print(f"    Dispatch:    [solar, battery]")
    print(f"    Hour 1:      solar=100, demand=50, SOC=0  {chr(8594)} CHARGE")
    print(f"    Hour 2:      solar=20,  demand=50, SOC=45 {chr(8594)} DISCHARGE")

    # --- Hour 1: Charge ---
    subheading("Hour 1 \u2014 Excess charges battery")

    productions_1 = {"solar": 100.0}
    storage_state_1 = {"battery": 0.0}
    demand_1 = 50.0

    coverage_1, storage_1, shortfall_1, excess_1 = dispatch_hour(
        demand_kw=demand_1,
        productions_kw=productions_1,
        dispatch_order=order,
        storage_state=storage_state_1,
        sources_meta=meta,
    )

    print(f"\n    Step-by-step:")
    print(f"      1. Inflexible 'solar':")
    print(f"         dispatch = min(100, 50) = 50")
    print(f"         remaining_demand = 50 - 50 = 0")
    print(f"      2. No discharge needed.")
    print(f"      3. Excess = 100 - 50 = 50")
    print(f"      4. Charging (reverse order \u2014 battery is last):")
    print(f"         headroom = 200 - 0 = 200")
    print(f"         max_charge_by_capacity = 200 / 0.9 = 222.2")
    print(f"         charge_grid = min(50, 50, 222.2) = 50")
    print(f"         soc_stored = 50 {chr(215)} 0.9 = 45")
    print(f"         new SOC = 0 + 45 = 45")
    print(f"         remaining excess = 0")

    soc_1 = storage_1["battery"]
    print(f"\n    Result hour 1:")
    print(f"      Coverage:       solar = {coverage_1['solar']:.0f}")
    print(f"      Shortfall:      {shortfall_1:.0f}")
    print(f"      Excess:         {excess_1:.0f}")
    print(f"      SOC after:      {soc_1:.0f} kWh  (0 {chr(8594)} {soc_1:.0f})")

    check_invariant(meta, coverage_1, shortfall_1, demand_1, "after hour 1")

    # --- Hour 2: Discharge ---
    subheading("Hour 2 \u2014 Shortfall discharges battery")

    productions_2 = {"solar": 20.0}
    storage_state_2 = storage_1  # SOC = 45 from hour 1
    demand_2 = 50.0

    coverage_2, storage_2, shortfall_2, excess_2 = dispatch_hour(
        demand_kw=demand_2,
        productions_kw=productions_2,
        dispatch_order=order,
        storage_state=storage_state_2,
        sources_meta=meta,
    )

    print(f"\n    Step-by-step:")
    print(f"      1. Inflexible 'solar':")
    print(f"         dispatch = min(20, 50) = 20")
    print(f"         remaining_demand = 50 - 20 = 30")
    print(f"      2. Storage 'battery' discharges:")
    print(f"         SOC = 45, max_discharge = 50, need = 30")
    print(f"         discharge = min(30, 50, 45) = 30")
    print(f"         remaining_demand = 30 - 30 = 0")
    print(f"         new SOC = 45 - 30 = 15")
    print(f"      3. shortfall = 0")

    soc_2 = storage_2["battery"]
    print(f"\n    Result hour 2:")
    print(f"      Coverage:       solar = {coverage_2['solar']:.0f},  battery = {coverage_2['battery']:.0f}")
    print(f"      Shortfall:      {shortfall_2:.0f}")
    print(f"      Excess:         {excess_2:.0f}")
    print(f"      SOC after:      {soc_2:.0f} kWh  (45 {chr(8594)} {soc_2:.0f})")

    check_invariant(meta, coverage_2, shortfall_2, demand_2, "after hour 2")

    # --- SOC trajectory ---
    print(f"\n  SOC trajectory:")
    print(f"    Initial:  0 kWh")
    print(f"    Hour 1:   {soc_1:.0f} kWh  (+45, charged from excess)")
    print(f"    Hour 2:   {soc_2:.0f} kWh  (-30, discharged to cover shortfall)")
    print(f"    Net:      {soc_2 - 0:.0f} kWh (charge 45 {chr(8722)} discharge 30)")

    print(f"\n  Cycle check:")
    print(f"    Grid energy for charging:  50 kWh (at {chr(951)}=0.9 {chr(8594)} 45 stored)")
    print(f"    Grid energy from discharge: 30 kWh")
    print(f"    Round-trip loss:           {(50 * 0.9) - 30:.0f} kWh (heat)")


# ---------------------------------------------------------------------------
# Scenario 5 — Flexible source fills remaining demand
# ---------------------------------------------------------------------------

def scenario_5() -> None:
    heading("Scenario 5 \u2014 Flexible source fills remaining demand")

    meta = {
        "solar": _inflexible("solar"),
        "battery": _storage("battery", initial_soc_kwh=20.0, max_discharge_rate_kw=20.0),
        "gas": _flexible("gas"),
    }
    order = ["solar", "battery", "gas"]
    productions = {"solar": 30.0, "gas": 100.0}
    demand = 200.0
    init_soc = {"battery": 20.0}

    print(f"\n  Setup:")
    print(f"    Demand:              {demand:.0f} kW")
    print(f"    Production:          solar = {productions['solar']:.0f},  gas = {productions['gas']:.0f}")
    print(f"    Dispatch order:      {order}")
    print(f"    Battery SOC:         {init_soc['battery']:.0f} kWh (init)")
    print(f"    Battery limits:      max_discharge = 20 kW")

    coverage, new_storage, shortfall, excess = dispatch_hour(
        demand_kw=demand,
        productions_kw=productions,
        dispatch_order=order,
        storage_state=init_soc,
        sources_meta=meta,
    )

    print(f"\n  Step-by-step:")
    print(f"    1. Inflexible 'solar':")
    print(f"       dispatch = min(30, 200) = 30")
    print(f"       remaining_demand = 200 - 30 = 170")
    print(f"    2. Storage 'battery' discharges:")
    print(f"       SOC = 20, max_discharge = 20, need = 170")
    print(f"       discharge = min(170, 20, 20) = 20")
    print(f"       remaining_demand = 170 - 20 = 150")
    print(f"       new SOC = 20 - 20 = 0")
    print(f"    3. Flexible 'gas':")
    print(f"       dispatch = min(100, 150) = 100")
    print(f"       remaining_demand = 150 - 100 = 50")
    print(f"    4. shortfall = 50")

    print(f"\n  Result:")
    solar = coverage["solar"]
    battery = coverage["battery"]
    gas = coverage["gas"]
    print(f"    Coverage:  solar = {solar:.0f},  battery = {battery:.0f},  gas = {gas:.0f}")
    print(f"    New SOC:   {new_storage['battery']:.0f} kWh")
    print(f"    Shortfall: {shortfall:.0f} kW")
    print(f"    Excess:    {excess:.0f} kW")

    check_invariant(meta, coverage, shortfall, demand)

    print(f"\n  Note: Invariant A fails here because battery discharge ({battery:.0f} kW) is")
    print(f"  excluded from non_storage_dispatched but still covers part of the demand.")
    print(f"  Invariant B always holds by construction \u2014 every kW dispatched")
    print(f"  decrements remaining_demand, and shortfall = max(0, remaining_demand).")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(SEP)
    print("  Scratch 05: dispatch_hour() \u2014 Core Matching Logic")
    print("  Demonstrating 5 scenarios that exercise inflexible, storage,")
    print("  and flexible dispatch, including state-of-charge tracking.")
    print(SEP)

    scenario_1()
    scenario_2()
    scenario_3()
    scenario_4()
    scenario_5()

    print(f"\n\n{SEP}")
    print("  All 5 scenarios complete.")
    print(SEP)


if __name__ == "__main__":
    main()