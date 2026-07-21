"""
Data models for the Renewable Energy Match toolkit.

All internal quantities are in kW (power) and kWh (energy).
All timestamps are hourly, timezone-aware UTC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# SourceMeta — per-source metadata
# ---------------------------------------------------------------------------


@dataclass
class SourceMeta:
    """Metadata describing a single energy source."""

    name: str
    """Human-readable name, e.g. "Solar"."""

    category: str
    """"demand" | "production"."""

    flexibility: str
    """"inflexible" | "flexible" | "storage"."""

    unit: str = "kW"
    """Always kW internally."""

    # Storage-specific fields (only when flexibility == "storage")
    capacity_kwh: float | None = None
    """Max energy stored (kWh)."""
    max_charge_rate_kw: float | None = None
    """Max charging power (kW)."""
    max_discharge_rate_kw: float | None = None
    """Max discharging power (kW)."""
    initial_soc_kwh: float | None = None
    """Starting state of charge (kWh)."""
    roundtrip_efficiency: float | None = None
    """Round-trip efficiency, 0.0–1.0."""

    def __post_init__(self) -> None:
        valid_categories = {"demand", "production"}
        if self.category not in valid_categories:
            raise ValueError(
                f"SourceMeta.category must be one of {valid_categories}, "
                f"got {self.category!r}"
            )

        valid_flex = {"inflexible", "flexible", "storage"}
        if self.flexibility not in valid_flex:
            raise ValueError(
                f"SourceMeta.flexibility must be one of {valid_flex}, "
                f"got {self.flexibility!r}"
            )

        if self.flexibility == "storage":
            required = {
                "capacity_kwh": self.capacity_kwh,
                "max_charge_rate_kw": self.max_charge_rate_kw,
                "max_discharge_rate_kw": self.max_discharge_rate_kw,
                "initial_soc_kwh": self.initial_soc_kwh,
                "roundtrip_efficiency": self.roundtrip_efficiency,
            }
            missing = {k for k, v in required.items() if v is None}
            if missing:
                raise ValueError(
                    f"Storage source {self.name!r} requires: {', '.join(sorted(missing))}"
                )
            if not 0.0 <= self.roundtrip_efficiency <= 1.0:  # type: ignore[operator]
                raise ValueError(
                    f"roundtrip_efficiency must be 0.0–1.0, got {self.roundtrip_efficiency}"
                )


# ---------------------------------------------------------------------------
# TimeSeries — universal input container
# ---------------------------------------------------------------------------

_VALIDATION_MSG = "TimeSeries validation failed"


def _validate_timestamps(ts: pd.DatetimeIndex) -> None:
    """Raise if *ts* is not hourly, monotonically increasing, and tz-aware UTC."""
    if not isinstance(ts, pd.DatetimeIndex):
        raise TypeError(f"{_VALIDATION_MSG}: timestamps must be a DatetimeIndex, got {type(ts)}")
    if ts.tz is None:
        raise ValueError(f"{_VALIDATION_MSG}: timestamps must be timezone-aware")
    # Normalise to UTC for comparison
    ts_utc = ts.tz_convert("UTC")
    # Check hourly spacing (allow 1-minute tolerance for DST transitions etc.)
    diffs = pd.Series(ts_utc).diff().iloc[1:]
    if diffs.empty:
        return  # single-row is fine
    median = diffs.median()
    expected = pd.Timedelta(hours=1)
    tol = pd.Timedelta(minutes=1)
    if abs(median - expected) > tol:
        raise ValueError(
            f"{_VALIDATION_MSG}: timestamps must be hourly (median delta={median})"
        )
    # Ensure sorted
    if not ts_utc.is_monotonic_increasing:
        raise ValueError(f"{_VALIDATION_MSG}: timestamps must be monotonically increasing")
    # No duplicates
    if ts_utc.duplicated().any():
        raise ValueError(f"{_VALIDATION_MSG}: timestamps contain duplicates")


@dataclass
class TimeSeries:
    """
    All series share the same hourly DatetimeIndex (UTC, sorted, no gaps).

    Invariants enforced on construction:
    - timestamps is monotonically increasing, hourly frequency, tz-aware UTC.
    - Every pd.Series has timestamps as its index and dtype float64.
    - No NaN in demand or productions (use 0.0 for missing).
    - sources_meta has an entry for "demand" and one for every production key.
    """

    timestamps: pd.DatetimeIndex
    demand: pd.Series
    productions: dict[str, pd.Series]
    sources_meta: dict[str, SourceMeta]

    def __post_init__(self) -> None:
        _validate_timestamps(self.timestamps)

        # Check sources_meta has the required keys
        required_keys = {"demand"} | set(self.productions.keys())
        actual_keys = set(self.sources_meta.keys())
        missing = required_keys - actual_keys
        if missing:
            raise ValueError(
                f"{_VALIDATION_MSG}: sources_meta missing keys: "
                f"{', '.join(sorted(missing))}"
            )

        for label, series in [("demand", self.demand)] + list(self.productions.items()):
            if not isinstance(series, pd.Series):
                raise TypeError(
                    f"{_VALIDATION_MSG}: {label} must be a pd.Series, got {type(series)}"
                )
            if not series.index.equals(self.timestamps):
                raise ValueError(
                    f"{_VALIDATION_MSG}: {label} index does not match timestamps"
                )
            if series.isna().any():
                raise ValueError(f"{_VALIDATION_MSG}: {label} contains NaN values")

        # General sanity: no extra unknown keys in sources_meta (soft warning)
        extra = actual_keys - required_keys
        if extra:
            import warnings

            warnings.warn(
                f"sources_meta has extra keys not in demand/productions: "
                f"{sorted(extra)}"
            )

    @classmethod
    def from_wide_dataframe(
        cls,
        df: pd.DataFrame,
        sources_meta: dict[str, SourceMeta],
    ) -> "TimeSeries":
        """
        Construct a TimeSeries from a wide DataFrame.

        The DataFrame's index MUST be a tz-aware DatetimeIndex.
        Columns must include ``"demand"`` plus one column per production source
        named in *sources_meta*.
        """
        timestamps = df.index
        if not isinstance(timestamps, pd.DatetimeIndex):
            raise TypeError(
                f"DataFrame index must be a DatetimeIndex, got {type(timestamps)}"
            )

        demand: pd.Series = df["demand"].astype("float64")
        productions: dict[str, pd.Series] = {}
        for name, meta in sources_meta.items():
            if name == "demand":
                continue
            if meta.category == "production":
                if name not in df.columns:
                    raise KeyError(
                        f"Column {name!r} not found in DataFrame; "
                        f"available: {list(df.columns)}"
                    )
                productions[name] = df[name].astype("float64")

        return cls(
            timestamps=timestamps,
            demand=demand,
            productions=productions,
            sources_meta=sources_meta,
        )


# ---------------------------------------------------------------------------
# MatchResult — engine output
# ---------------------------------------------------------------------------

_MR_MSG = "MatchResult validation failed"


@dataclass
class MatchResult:
    """
    Result of a matching simulation.

    Invariants:
    - For each hour: ``demand == coverage.sum(axis=1) + shortfall``
    - For each hour: ``total_production == coverage.sum(axis=1) + excess``
    - No negative values in coverage, shortfall, excess.
    """

    timestamps: pd.DatetimeIndex
    demand: pd.Series
    coverage: pd.DataFrame
    shortfall: pd.Series
    excess: pd.Series
    storage_soc: dict[str, pd.Series] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Type checks
        for label, val in [
            ("timestamps", self.timestamps),
            ("demand", self.demand),
            ("coverage", self.coverage),
            ("shortfall", self.shortfall),
            ("excess", self.excess),
        ]:
            if isinstance(val, pd.DataFrame):
                continue
            if not isinstance(val, pd.Index):
                if not isinstance(val, pd.Series):
                    raise TypeError(f"{_MR_MSG}: {label} must be a Series/DataFrame")

        # Index alignment check
        expected_index = self.timestamps
        for label, series in [
            ("demand", self.demand),
            ("shortfall", self.shortfall),
            ("excess", self.excess),
        ]:
            if not series.index.equals(expected_index):
                raise ValueError(f"{_MR_MSG}: {label} index does not match timestamps")
        if not self.coverage.index.equals(expected_index):
            raise ValueError(f"{_MR_MSG}: coverage index does not match timestamps")

        # No negatives
        if (self.coverage < 0).any().any():
            raise ValueError(f"{_MR_MSG}: coverage contains negative values")
        if (self.shortfall < 0).any():
            raise ValueError(f"{_MR_MSG}: shortfall contains negative values")
        if (self.excess < 0).any():
            raise ValueError(f"{_MR_MSG}: excess contains negative values")

        # Invariant: demand == coverage.sum(axis=1) + shortfall
        covered = self.coverage.sum(axis=1)
        diff = (self.demand - covered - self.shortfall).abs().max()
        if diff > 1e-3:
            raise ValueError(
                f"{_MR_MSG}: demand != coverage.sum() + shortfall (max diff={diff:.4f})"
            )

    def to_dataframe(self) -> pd.DataFrame:
        """Return a wide DataFrame with demand, coverage, shortfall, excess."""
        df = pd.DataFrame({"demand": self.demand}, index=self.timestamps)
        for col in self.coverage.columns:
            df[col] = self.coverage[col]
        df["shortfall"] = self.shortfall
        df["excess"] = self.excess
        return df