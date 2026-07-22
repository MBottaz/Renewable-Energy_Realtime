"""Tests for the dispatch_hour pure function."""

import pytest

from energy_match.dispatch import dispatch_hour
from energy_match.models import SourceMeta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _inflexible(name: str) -> SourceMeta:
    return SourceMeta(name=name, category="production", flexibility="inflexible")


def _flexible(name: str) -> SourceMeta:
    return SourceMeta(name=name, category="production", flexibility="flexible")


def _storage(
    name: str,
    capacity_kwh: float = 100.0,
    max_charge_rate_kw: float = 50.0,
    max_discharge_rate_kw: float = 50.0,
    initial_soc_kwh: float = 0.0,
    roundtrip_efficiency: float = 0.9,
) -> SourceMeta:
    return SourceMeta(
        name=name,
        category="production",
        flexibility="storage",
        capacity_kwh=capacity_kwh,
        max_charge_rate_kw=max_charge_rate_kw,
        max_discharge_rate_kw=max_discharge_rate_kw,
        initial_soc_kwh=initial_soc_kwh,
        roundtrip_efficiency=roundtrip_efficiency,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestInflexibleSourcesUsedFirst:
    """Inflexible sources are dispatched in priority order before others."""

    def test_priority_order(self):
        """Two inflexible sources, first in dispatch order gets priority."""
        meta = {
            "a": _inflexible("a"),
            "b": _inflexible("b"),
        }
        order = ["a", "b"]
        productions = {"a": 60.0, "b": 60.0}
        storage_state = {}

        coverage, new_storage, shortfall, excess = dispatch_hour(
            demand_kw=100.0,
            productions_kw=productions,
            dispatch_order=order,
            storage_state=storage_state,
            sources_meta=meta,
        )

        # "a" is first, gets min(60, 100) = 60
        # "b" gets min(60, 40) = 40
        assert coverage["a"] == pytest.approx(60.0)
        assert coverage["b"] == pytest.approx(40.0)
        assert shortfall == pytest.approx(0.0)
        assert excess == pytest.approx(20.0)


class TestStorageDischarge:
    """Storage discharges to cover remaining demand when production is insufficient."""

    def test_storage_discharge(self):
        meta = {
            "solar": _inflexible("solar"),
            "battery": _storage("battery", initial_soc_kwh=80.0),
        }
        order = ["solar", "battery"]
        productions = {"solar": 40.0}
        storage_state = {"battery": 80.0}

        coverage, new_storage, shortfall, excess = dispatch_hour(
            demand_kw=100.0,
            productions_kw=productions,
            dispatch_order=order,
            storage_state=storage_state,
            sources_meta=meta,
        )

        # solar covers 40, remaining = 60
        # battery discharges min(60, 50, 80) = 50
        # shortfall = 60 - 50 = 10
        assert coverage["solar"] == pytest.approx(40.0)
        assert coverage["battery"] == pytest.approx(50.0)
        assert new_storage["battery"] == pytest.approx(30.0)  # 80 - 50
        assert shortfall == pytest.approx(10.0)
        assert excess == pytest.approx(0.0)


class TestStorageChargeRateLimit:
    """Storage charging is limited by max_charge_rate."""

    def test_charge_rate_limit(self):
        meta = {
            "solar": _inflexible("solar"),
            "battery": _storage("battery", max_charge_rate_kw=50.0),
        }
        order = ["solar", "battery"]
        productions = {"solar": 200.0}
        storage_state = {"battery": 0.0}

        coverage, new_storage, shortfall, excess = dispatch_hour(
            demand_kw=100.0,
            productions_kw=productions,
            dispatch_order=order,
            storage_state=storage_state,
            sources_meta=meta,
        )

        # solar covers 100, remaining = 0
        # excess = 200 - 100 = 100
        # battery charges: charge_grid = min(100, 50, 100/0.9=111.1) = 50
        # soc stored = 50 * 0.9 = 45
        assert coverage["solar"] == pytest.approx(100.0)
        assert new_storage["battery"] == pytest.approx(45.0)
        assert excess == pytest.approx(50.0)  # 100 - 50 = 50


class TestStorageCapacityLimit:
    """Storage does not charge beyond its capacity."""

    def test_capacity_limit(self):
        meta = {
            "solar": _inflexible("solar"),
            "battery": _storage(
                "battery",
                capacity_kwh=60.0,
                max_charge_rate_kw=200.0,
                initial_soc_kwh=55.0,
            ),
        }
        order = ["solar", "battery"]
        productions = {"solar": 200.0}
        storage_state = {"battery": 55.0}

        coverage, new_storage, shortfall, excess = dispatch_hour(
            demand_kw=100.0,
            productions_kw=productions,
            dispatch_order=order,
            storage_state=storage_state,
            sources_meta=meta,
        )

        # solar covers 100, excess = 100
        # headroom = 60 - 55 = 5
        # max_charge_by_capacity = 5 / 0.9 = 5.555...
        # charge_grid = min(100, 200, 5.5555) = 5.5555...
        # soc_stored = 5.5555... * 0.9 = 5.0
        headroom = 60.0 - 55.0
        max_charge_by_capacity = headroom / 0.9
        charge_grid = min(100.0, 200.0, max_charge_by_capacity)
        soc_stored = charge_grid * 0.9

        assert new_storage["battery"] == pytest.approx(60.0)
        assert excess == pytest.approx(100.0 - charge_grid)


class TestRoundTripEfficiency:
    """Charging 100 kWh with η=0.9 stores 90 kWh in the battery."""

    def test_round_trip_efficiency(self):
        meta = {
            "solar": _inflexible("solar"),
            "battery": _storage(
                "battery",
                capacity_kwh=200.0,
                max_charge_rate_kw=200.0,
                initial_soc_kwh=0.0,
                roundtrip_efficiency=0.9,
            ),
        }
        order = ["solar", "battery"]
        productions = {"solar": 200.0}
        storage_state = {"battery": 0.0}

        coverage, new_storage, shortfall, excess = dispatch_hour(
            demand_kw=100.0,
            productions_kw=productions,
            dispatch_order=order,
            storage_state=storage_state,
            sources_meta=meta,
        )

        # excess = 200 - 100 = 100
        # charge_grid = min(100, 200, 200/0.9=222.2) = 100
        # soc_stored = 100 * 0.9 = 90
        assert new_storage["battery"] == pytest.approx(90.0)
        assert excess == pytest.approx(0.0)


class TestFlexibleSources:
    """Flexible sources cover remaining demand after inflexible and storage."""

    def test_flexible_sources(self):
        meta = {
            "solar": _inflexible("solar"),
            "battery": _storage("battery", initial_soc_kwh=20.0, max_discharge_rate_kw=20.0),
            "gas": _flexible("gas"),
        }
        order = ["solar", "battery", "gas"]
        productions = {"solar": 30.0, "gas": 100.0}
        storage_state = {"battery": 20.0}

        coverage, new_storage, shortfall, excess = dispatch_hour(
            demand_kw=200.0,
            productions_kw=productions,
            dispatch_order=order,
            storage_state=storage_state,
            sources_meta=meta,
        )

        # solar covers 30, remaining = 170
        # battery discharges min(170, 50, 20) = 20, remaining = 150
        # gas (flexible) covers min(100, 150) = 100, remaining = 50
        assert coverage["solar"] == pytest.approx(30.0)
        assert coverage["battery"] == pytest.approx(20.0)
        assert coverage["gas"] == pytest.approx(100.0)
        assert new_storage["battery"] == pytest.approx(0.0)
        assert shortfall == pytest.approx(50.0)
        # total_production = 30+100 = 130
        # non-storage dispatched = 30+100 = 130
        # excess = 130 - 130 = 0
        assert excess == pytest.approx(0.0)


class TestFullCycle:
    """Charge then discharge in sequence (two dispatch_hour calls)."""

    def test_full_cycle(self):
        meta = {
            "solar": _inflexible("solar"),
            "battery": _storage(
                "battery",
                capacity_kwh=50.0,
                max_charge_rate_kw=50.0,
                max_discharge_rate_kw=50.0,
                initial_soc_kwh=0.0,
                roundtrip_efficiency=0.9,
            ),
        }
        order = ["solar", "battery"]

        # Hour 1: excess → charge battery
        productions = {"solar": 100.0}
        storage_state = {"battery": 0.0}

        coverage1, storage1, shortfall1, excess1 = dispatch_hour(
            demand_kw=50.0,
            productions_kw=productions,
            dispatch_order=order,
            storage_state=storage_state,
            sources_meta=meta,
        )

        # solar covers 50, remaining=0, excess=50
        # charge_grid = min(50, 50, 50/0.9=55.5) = 50
        # soc_stored = 50*0.9 = 45
        assert shortfall1 == pytest.approx(0.0)
        assert excess1 == pytest.approx(0.0)
        assert storage1["battery"] == pytest.approx(45.0)

        # Hour 2: shortfall → discharge battery
        productions2 = {"solar": 20.0}
        storage_state2 = storage1

        coverage2, storage2, shortfall2, excess2 = dispatch_hour(
            demand_kw=50.0,
            productions_kw=productions2,
            dispatch_order=order,
            storage_state=storage_state2,
            sources_meta=meta,
        )

        # solar covers 20, remaining=30
        # battery discharges min(30, 50, 45) = 30
        # shortfall = 0
        assert coverage2["solar"] == pytest.approx(20.0)
        assert coverage2["battery"] == pytest.approx(30.0)
        assert storage2["battery"] == pytest.approx(15.0)  # 45 - 30
        assert shortfall2 == pytest.approx(0.0)
        assert excess2 == pytest.approx(0.0)