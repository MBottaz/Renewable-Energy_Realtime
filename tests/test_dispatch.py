"""Unit tests for core.dispatch.dispatch_hour()."""

from core.config import SOURCE_CLASSIFICATIONS, SourceMeta
from core.dispatch import build_dispatch_order, dispatch_hour

# Minimal classifications for isolated tests
META = {
    "Solar": SourceMeta("Solar", "inflexible"),
    "Hydro Pumped Storage": SourceMeta(
        "Hydro Pumped Storage",
        "storage",
        capacity_kwh=100_000.0,
        max_charge_rate_kw=10_000.0,
        max_discharge_rate_kw=10_000.0,
        initial_soc_kwh=50_000.0,
        roundtrip_efficiency=0.85,
    ),
    "Fossil Gas": SourceMeta("Fossil Gas", "flexible"),
}

ORDER = ["Solar", "Hydro Pumped Storage", "Fossil Gas"]


def test_build_dispatch_order_filters_to_present():
    order = build_dispatch_order({"Solar", "Fossil Gas"}, META, ORDER)
    assert order == ["Solar", "Fossil Gas"]


def test_invariant_coverage_plus_shortfall_equals_demand():
    productions = {"Solar": 2000.0, "Fossil Gas": 1000.0}
    coverage, _, shortfall, _ = dispatch_hour(
        demand_kw=5000.0,
        productions_kw=productions,
        dispatch_order=ORDER,
        storage_state={"Hydro Pumped Storage": 50000.0},
        sources_meta=META,
    )
    assert abs(sum(coverage.values()) + shortfall - 5000.0) < 1e-6
    assert shortfall >= 0


def test_storage_discharges_when_demand_exceeds_inflexible():
    # Demand 20 GW, only 3 GW from Solar → storage should discharge.
    productions = {"Solar": 3000.0}
    coverage, new_soc, shortfall, _ = dispatch_hour(
        demand_kw=20_000.0,
        productions_kw=productions,
        dispatch_order=ORDER,
        storage_state={"Hydro Pumped Storage": 50_000.0},
        sources_meta=META,
    )
    assert coverage["Hydro Pumped Storage"] > 0
    assert new_soc["Hydro Pumped Storage"] < 50_000.0
    assert shortfall >= 0


def test_storage_charges_from_excess():
    # Huge solar surplus → storage should charge and excess shrinks.
    productions = {"Solar": 30_000.0}
    coverage, new_soc, shortfall, excess = dispatch_hour(
        demand_kw=10_000.0,
        productions_kw=productions,
        dispatch_order=ORDER,
        storage_state={"Hydro Pumped Storage": 0.0},
        sources_meta=META,
    )
    assert new_soc["Hydro Pumped Storage"] > 0
    # Charging is not part of coverage; excess = prod - dispatched (non-storage)
    assert coverage["Hydro Pumped Storage"] == 0.0
    assert shortfall == 0.0
    assert excess >= 0
    assert excess < 20_000.0  # some was absorbed by charging


def test_soc_stays_within_capacity():
    productions = {"Solar": 30_000.0}
    _, new_soc, _, _ = dispatch_hour(
        demand_kw=0.0,
        productions_kw=productions,
        dispatch_order=ORDER,
        storage_state={"Hydro Pumped Storage": 99_000.0},
        sources_meta=META,
    )
    soc = new_soc["Hydro Pumped Storage"]
    assert 0 <= soc <= META["Hydro Pumped Storage"].capacity_kwh + 1e-6


def test_storage_discharge_respects_rate_and_soc():
    productions = {}
    _, new_soc, shortfall, _ = dispatch_hour(
        demand_kw=100_000.0,
        productions_kw=productions,
        dispatch_order=ORDER,
        storage_state={"Hydro Pumped Storage": 10_000.0},
        sources_meta=META,
    )
    # Only 10 MWh available, discharged at ≤10 GW rate → SOC hits 0
    assert new_soc["Hydro Pumped Storage"] == 0.0
    assert shortfall == 100_000.0 - 10_000.0


def test_full_classification_set_works_with_default_config():
    # Sanity: dispatch with the real config doesn't raise.
    from core.config import DISPATCH_ORDER as FULL_ORDER
    from core.config import SOURCE_CLASSIFICATIONS as FULL_META

    productions = {"Solar": 100.0, "Wind Onshore": 200.0}
    coverage, _, shortfall, excess = dispatch_hour(
        demand_kw=1000.0,
        productions_kw=productions,
        dispatch_order=FULL_ORDER,
        storage_state={},
        sources_meta=FULL_META,
    )
    assert abs(sum(coverage.values()) + shortfall - 1000.0) < 1e-6
    assert excess >= 0
