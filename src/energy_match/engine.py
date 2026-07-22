"""
Core energy matching engine.

Runs the dispatch simulation over a full :class:`TimeSeries` and returns a
:class:`MatchResult`.
"""

from __future__ import annotations

import pandas as pd

from energy_match.dispatch import build_dispatch_order, dispatch_hour
from energy_match.models import MatchResult, SourceMeta, TimeSeries


def match(
    ts: TimeSeries,
    dispatch_order: list[str] | None = None,
) -> MatchResult:
    """Run the energy matching simulation over the full time series.

    Parameters
    ----------
    ts:
        Input time series (demand + production tracks + source metadata).
    dispatch_order:
        Source dispatch priority list.  Built from defaults when *None*.

    Returns
    -------
    MatchResult
        Hourly coverage, shortfall, excess, and optional storage SOC.
    """
    # 1. Resolve dispatch order
    order: list[str] = (
        dispatch_order
        if dispatch_order is not None
        else build_dispatch_order(ts.sources_meta)
    )
    # Demand is not a production source — exclude from dispatch order
    order = [name for name in order if name != "demand"]

    # 2. Initialise storage state
    storage_state: dict[str, float] = {}
    for name, meta in ts.sources_meta.items():
        if meta.flexibility == "storage":
            storage_state[name] = (
                meta.initial_soc_kwh
                if meta.initial_soc_kwh is not None
                else 0.0
            )

    # Identify storage sources (used for SOC recording)
    storage_names = list(storage_state.keys())

    # 3. Accumulators
    coverage_records: list[dict[str, float]] = []
    storage_soc_records: list[dict[str, float]] = []
    shortfall_list: list[float] = []
    excess_list: list[float] = []

    # 4. Hour-by-hour dispatch
    n = len(ts.timestamps)
    for i in range(n):
        demand_kw = float(ts.demand.iloc[i])
        productions_kw = {
            name: float(series.iloc[i])
            for name, series in ts.productions.items()
        }

        coverage, new_storage_state, shortfall, excess = dispatch_hour(
            demand_kw=demand_kw,
            productions_kw=productions_kw,
            dispatch_order=order,
            storage_state=storage_state,
            sources_meta=ts.sources_meta,
        )

        coverage_records.append(coverage)
        shortfall_list.append(shortfall)
        excess_list.append(excess)

        if storage_names:
            storage_soc_records.append(
                {name: new_storage_state.get(name, 0.0) for name in storage_names}
            )

        storage_state = new_storage_state

    # 5. Build result
    coverage = pd.DataFrame(coverage_records, index=ts.timestamps)
    # Drop "demand" column if it leaked in (dispatch_hour setdefault includes it)
    coverage = coverage.drop(columns="demand", errors="ignore")

    if storage_names:
        storage_soc: dict[str, pd.Series] | None = {
            name: pd.Series(
                [r.get(name, 0.0) for r in storage_soc_records],
                index=ts.timestamps,
            )
            for name in storage_names
        }
    else:
        storage_soc = None

    shortfall = pd.Series(shortfall_list, index=ts.timestamps, dtype="float64")
    excess = pd.Series(excess_list, index=ts.timestamps, dtype="float64")

    # 6. Return
    return MatchResult(
        timestamps=ts.timestamps,
        demand=ts.demand,
        coverage=coverage,
        shortfall=shortfall,
        excess=excess,
        storage_soc=storage_soc,
    )