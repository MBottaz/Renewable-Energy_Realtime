"""Tests for the core energy matching engine."""

import pandas as pd
import pytest

from energy_match.models import SourceMeta, TimeSeries
from energy_match.engine import match


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_index(hours: int = 3) -> pd.DatetimeIndex:
    return pd.date_range("2025-01-01", periods=hours, freq="h", tz="UTC")


def _simple_meta(
    name: str,
    flexibility: str = "inflexible",
    **storage_kw,
) -> dict[str, SourceMeta]:
    """Build a small sources_meta dict from keyword arguments."""
    meta: dict[str, SourceMeta] = {
        "demand": SourceMeta(name="demand", category="demand", flexibility="inflexible"),
    }
    meta[name] = SourceMeta(
        name=name,
        category="production",
        flexibility=flexibility,
        **storage_kw,
    )
    return meta


def _from_dicts(
    demand: list[float],
    productions: dict[str, list[float]],
    sources_meta: dict[str, SourceMeta],
    hours: int | None = None,
) -> TimeSeries:
    """Build a TimeSeries from plain Python lists."""
    if hours is None:
        hours = len(demand)
    idx = _make_index(hours)
    df = pd.DataFrame({"demand": demand}, index=idx)
    for name, vals in productions.items():
        df[name] = vals
    return TimeSeries.from_wide_dataframe(df, sources_meta)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExactMatch:
    """Production exactly equals demand for every hour."""

    def test_exact_match(self):
        ts = _from_dicts(
            demand=[100, 200],
            productions={"solar": [40, 80], "wind": [60, 120]},
            sources_meta={
                "demand": SourceMeta(name="demand", category="demand", flexibility="inflexible"),
                "solar": SourceMeta(name="solar", category="production", flexibility="inflexible"),
                "wind": SourceMeta(name="wind", category="production", flexibility="inflexible"),
            },
        )
        result = match(ts)
        assert result.shortfall.sum() == pytest.approx(0)
        assert result.excess.sum() == pytest.approx(0)
        # Every hour: coverage sums to demand
        assert (result.coverage.sum(axis=1) == pd.Series([100.0, 200.0], index=result.timestamps)).all()


class TestShortfall:
    """Total production is less than demand every hour."""

    def test_shortfall(self):
        ts = _from_dicts(
            demand=[100, 200],
            productions={"solar": [30, 50]},
            sources_meta={
                "demand": SourceMeta(name="demand", category="demand", flexibility="inflexible"),
                "solar": SourceMeta(name="solar", category="production", flexibility="inflexible"),
            },
        )
        result = match(ts)
        assert result.shortfall.sum() > 0
        assert result.excess.sum() == pytest.approx(0)
        assert result.shortfall.iloc[0] == pytest.approx(70.0)
        assert result.shortfall.iloc[1] == pytest.approx(150.0)


class TestExcessWithoutStorage:
    """Production exceeds demand with no storage available."""

    def test_excess_without_storage(self):
        ts = _from_dicts(
            demand=[50, 80],
            productions={"solar": [60, 100]},
            sources_meta={
                "demand": SourceMeta(name="demand", category="demand", flexibility="inflexible"),
                "solar": SourceMeta(name="solar", category="production", flexibility="inflexible"),
            },
        )
        result = match(ts)
        assert result.excess.sum() > 0
        assert result.shortfall.sum() == pytest.approx(0)
        assert result.excess.iloc[0] == pytest.approx(10.0)
        assert result.excess.iloc[1] == pytest.approx(20.0)


class TestExcessWithStorage:
    """Production exceeds demand and storage is available — storage charges."""

    def test_excess_with_storage(self):
        ts = _from_dicts(
            demand=[50, 60],
            productions={"solar": [100, 100], "battery": [0.0, 0.0]},
            sources_meta={
                "demand": SourceMeta(name="demand", category="demand", flexibility="inflexible"),
                "solar": SourceMeta(name="solar", category="production", flexibility="inflexible"),
                "battery": SourceMeta(
                    name="battery",
                    category="production",
                    flexibility="storage",
                    capacity_kwh=200.0,
                    max_charge_rate_kw=50.0,
                    max_discharge_rate_kw=50.0,
                    initial_soc_kwh=0.0,
                    roundtrip_efficiency=0.9,
                ),
            },
        )
        result = match(ts)

        # There should be excess reduced by storage charging
        assert result.excess.sum() >= 0
        assert result.shortfall.sum() == pytest.approx(0)

        # Hour 0: demand=50, solar=100, excess before charging = 50
        # Battery max_charge_rate=50, capacity=200, η=0.9
        # charge_grid = min(50, 50, 200/0.9=222.2) = 50
        # soc_stored = 50*0.9 = 45
        # Hour 1: demand=60, solar=100, excess before charging = 40
        # charge_grid = min(40, 50, (200-45)/0.9=172.2) = 40
        # soc_stored = 40*0.9 = 36

        # So total excess = 50+40 - (50+40) = 0 (all excess went to charging)
        assert result.excess.sum() == pytest.approx(0)

        # Storage SOC should have increased
        assert result.storage_soc is not None
        soc_series = result.storage_soc["battery"]
        assert soc_series.iloc[0] == pytest.approx(45.0)  # 50*0.9
        assert soc_series.iloc[1] == pytest.approx(81.0)  # 45 + 40*0.9


class TestDischarge:
    """Production is less than demand, storage discharges to reduce shortfall."""

    def test_discharge(self):
        ts = _from_dicts(
            demand=[100, 100],
            productions={"solar": [40, 60], "battery": [0.0, 0.0]},
            sources_meta={
                "demand": SourceMeta(name="demand", category="demand", flexibility="inflexible"),
                "solar": SourceMeta(name="solar", category="production", flexibility="inflexible"),
                "battery": SourceMeta(
                    name="battery",
                    category="production",
                    flexibility="storage",
                    capacity_kwh=100.0,
                    max_charge_rate_kw=50.0,
                    max_discharge_rate_kw=30.0,
                    initial_soc_kwh=50.0,
                    roundtrip_efficiency=0.9,
                ),
            },
        )
        result = match(ts)

        # Hour 0: demand=100, solar=40, remaining=60
        #   Battery discharge = min(60, 30, 50) = 30
        #   shortfall = 60-30 = 30
        # Hour 1: demand=100, solar=60, remaining=40
        #   Battery SOC now = 50-30=20
        #   discharge = min(40, 30, 20) = 20
        #   shortfall = 40-20 = 20

        assert result.shortfall.sum() == pytest.approx(50.0)
        assert result.excess.sum() == pytest.approx(0)

        assert result.storage_soc is not None
        soc = result.storage_soc["battery"]
        assert soc.iloc[0] == pytest.approx(20.0)  # 50-30
        assert soc.iloc[1] == pytest.approx(0.0)   # 20-20


class TestZeroDemand:
    """Demand is zero — all production becomes excess."""

    def test_zero_demand(self):
        ts = _from_dicts(
            demand=[0, 0],
            productions={"solar": [50, 80]},
            sources_meta={
                "demand": SourceMeta(name="demand", category="demand", flexibility="inflexible"),
                "solar": SourceMeta(name="solar", category="production", flexibility="inflexible"),
            },
        )
        result = match(ts)
        assert result.shortfall.sum() == pytest.approx(0)
        assert result.excess.sum() == pytest.approx(130.0)
        assert result.coverage.sum(axis=1).sum() == pytest.approx(0)


class TestZeroProduction:
    """All production is zero — all demand becomes shortfall."""

    def test_zero_production(self):
        ts = _from_dicts(
            demand=[100, 200],
            productions={"solar": [0, 0]},
            sources_meta={
                "demand": SourceMeta(name="demand", category="demand", flexibility="inflexible"),
                "solar": SourceMeta(name="solar", category="production", flexibility="inflexible"),
            },
        )
        result = match(ts)
        assert result.shortfall.sum() == pytest.approx(300.0)
        assert result.excess.sum() == pytest.approx(0)
        assert result.coverage.sum(axis=1).sum() == pytest.approx(0)


class TestInvariant:
    """Every scenario must satisfy: coverage.sum(axis=1) + shortfall ≈ demand."""

    @pytest.mark.parametrize(
        "demand, productions, storage",
        [
            # Exact match
            ([100, 200], {"solar": [40, 80], "wind": [60, 120]}, False),
            # Shortfall
            ([100, 200], {"solar": [30, 50]}, False),
            # Excess without storage
            ([50, 80], {"solar": [60, 100]}, False),
            # Excess with storage
            (
                [50, 60],
                {"solar": [100, 100]},
                {
                    "capacity_kwh": 200.0,
                    "max_charge_rate_kw": 50.0,
                    "max_discharge_rate_kw": 50.0,
                    "initial_soc_kwh": 0.0,
                    "roundtrip_efficiency": 0.9,
                },
            ),
            # Discharge
            (
                [100, 100],
                {"solar": [40, 60]},
                {
                    "capacity_kwh": 100.0,
                    "max_charge_rate_kw": 50.0,
                    "max_discharge_rate_kw": 30.0,
                    "initial_soc_kwh": 50.0,
                    "roundtrip_efficiency": 0.9,
                },
            ),
        ],
    )
    def test_invariant(self, demand, productions, storage):
        meta: dict[str, SourceMeta] = {
            "demand": SourceMeta(name="demand", category="demand", flexibility="inflexible"),
        }
        for src_name in productions:
            meta[src_name] = SourceMeta(
                name=src_name,
                category="production",
                flexibility="inflexible",
            )

        if storage:
            battery_name = "battery"
            productions[battery_name] = [0.0] * len(demand)
            meta[battery_name] = SourceMeta(
                name=battery_name,
                category="production",
                flexibility="storage",
                **storage,
            )

        ts = _from_dicts(demand, productions, meta)
        result = match(ts)

        # Invariant: coverage.sum(axis=1) + shortfall ≈ demand
        covered = result.coverage.sum(axis=1)
        # For storage, non-storage coverage + shortfall == demand
        # But compute: demand == covered + shortfall
        combined = covered + result.shortfall
        assert combined.equals(result.demand) or (combined - result.demand).abs().max() < 1e-6

        # No negative values
        assert (result.coverage >= -1e-12).all().all()
        assert (result.shortfall >= -1e-12).all()
        assert (result.excess >= -1e-12).all()