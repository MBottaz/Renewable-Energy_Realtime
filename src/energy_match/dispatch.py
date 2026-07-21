"""
Dispatch logic for the energy matching engine.

Pure functions — no I/O, no side effects.

Efficiency convention (standard in energy system models):
  - **Charge side**: drawing ``E / η`` from the grid stores ``E`` in the battery.
  - **Discharge side**: drawing ``E`` from the battery delivers ``E`` to the grid.
"""

from __future__ import annotations

from energy_match.config import DEFAULT_DISPATCH_ORDER
from energy_match.models import SourceMeta


def build_dispatch_order(
    sources_meta: dict[str, SourceMeta],
) -> list[str]:
    """Return source names sorted by dispatch priority.

    Rules
    -----
    1. Inflexible sources first (in config order).
    2. Storage sources (pumped hydro before generic).
    3. Flexible sources.
    4. Any remaining sources in config order.

    Within each flexibility group the relative order from
    ``DEFAULT_DISPATCH_ORDER`` is preserved.
    """
    # Build a rank map from DEFAULT_DISPATCH_ORDER
    rank = {name: i for i, name in enumerate(DEFAULT_DISPATCH_ORDER)}
    unknown_idx = len(DEFAULT_DISPATCH_ORDER)

    def sort_key(name: str) -> tuple[int, int]:
        """Priority group first, then rank within that group."""
        meta = sources_meta.get(name)
        if meta is None:
            return (99, unknown_idx)

        flex = meta.flexibility
        if flex == "inflexible":
            group = 0
        elif flex == "storage":
            group = 1
        elif flex == "flexible":
            group = 2
        else:
            group = 3  # other / unknown

        return (group, rank.get(name, unknown_idx))

    return sorted(sources_meta.keys(), key=sort_key)


def compute_storage_limits(
    sources_meta: dict[str, SourceMeta],
) -> dict[str, tuple[float, float]]:
    """Return ``(max_charge_rate_kw, max_discharge_rate_kw)`` per storage."""
    limits: dict[str, tuple[float, float]] = {}
    for name, meta in sources_meta.items():
        if meta.flexibility == "storage":
            limits[name] = (
                meta.max_charge_rate_kw or 0.0,
                meta.max_discharge_rate_kw or 0.0,
            )
    return limits


def dispatch_hour(
    demand_kw: float,
    productions_kw: dict[str, float],
    dispatch_order: list[str],
    storage_state: dict[str, float],
    sources_meta: dict[str, SourceMeta],
) -> tuple[dict[str, float], dict[str, float], float, float]:
    """Dispatch generation for a single hour.

    Parameters
    ----------
    demand_kw:
        Hourly demand in kW.
    productions_kw:
        Available production per source in kW (uncurtailed).
    dispatch_order:
        Source names in priority order (first = highest).
    storage_state:
        Current state of charge (kWh) for each storage source.
    sources_meta:
        Metadata for every source.

    Returns
    -------
    coverage:
        ``{source_name: kW_dispatched_to_meet_demand}``
        Storage discharge is included as positive coverage.
        Storage charging is *not* included in coverage — it reduces
        ``excess`` instead.
    new_storage_state:
        ``{source_name: soc_kwh}`` after charge/discharge.
    shortfall:
        Demand not covered (kW, >= 0).
    excess:
        Production that is neither dispatched to meet demand nor used
        for storage charging (kW, >= 0).  This is curtailment.
    """
    remaining_demand = demand_kw
    coverage: dict[str, float] = {}
    new_storage_state = dict(storage_state)

    # ---------------------------------------------------------------
    # Step 1 — Inflexible sources (must-run, curtailable only as excess)
    # ---------------------------------------------------------------
    for name in dispatch_order:
        meta = sources_meta.get(name)
        if meta is None or meta.flexibility != "inflexible":
            continue
        prod = productions_kw.get(name, 0.0)
        dispatch = min(prod, remaining_demand)
        coverage[name] = dispatch
        remaining_demand -= dispatch

    # ---------------------------------------------------------------
    # Step 2 — Discharge storage to cover remaining demand
    # ---------------------------------------------------------------
    if remaining_demand > 0:
        for name in dispatch_order:
            meta = sources_meta.get(name)
            if meta is None or meta.flexibility != "storage":
                continue
            if remaining_demand <= 0:
                break

            soc = new_storage_state.get(name, 0.0)
            max_rate = meta.max_discharge_rate_kw or 0.0
            discharge = min(remaining_demand, max_rate, soc)
            if discharge > 0:
                coverage[name] = discharge
                new_storage_state[name] = soc - discharge
                remaining_demand -= discharge

    # ---------------------------------------------------------------
    # Step 3 — Flexible sources (dispatchable up to remaining demand)
    # ---------------------------------------------------------------
    if remaining_demand > 0:
        for name in dispatch_order:
            meta = sources_meta.get(name)
            if meta is None or meta.flexibility != "flexible":
                continue
            if remaining_demand <= 0:
                break
            prod = productions_kw.get(name, 0.0)
            dispatch = min(prod, remaining_demand)
            coverage[name] = dispatch
            remaining_demand -= dispatch

    shortfall = max(0.0, remaining_demand)

    # ---------------------------------------------------------------
    # Compute excess — production not used for covering demand
    # ---------------------------------------------------------------
    total_production = sum(productions_kw.values())
    production_dispatched = sum(
        v
        for name, v in coverage.items()
        if sources_meta.get(name) is None
        or sources_meta[name].flexibility != "storage"
    )
    excess = max(0.0, total_production - production_dispatched)

    # ---------------------------------------------------------------
    # Step 4 — Recharge storage from excess (reverse priority)
    # ---------------------------------------------------------------
    if excess > 0:
        for name in reversed(dispatch_order):
            meta = sources_meta.get(name)
            if meta is None or meta.flexibility != "storage":
                continue
            if excess <= 0:
                break

            soc = new_storage_state.get(name, 0.0)
            max_charge_rate = meta.max_charge_rate_kw or 0.0
            capacity = meta.capacity_kwh or 0.0
            efficiency = meta.roundtrip_efficiency or 1.0

            headroom = capacity - soc
            # Grid draw needed to fill headroom
            max_charge_by_capacity = headroom / efficiency if efficiency > 0 else 0.0

            charge_grid = min(excess, max_charge_rate, max_charge_by_capacity)
            if charge_grid > 0:
                soc_stored = charge_grid * efficiency
                new_storage_state[name] = soc + soc_stored
                excess -= charge_grid

    # Ensure every source in dispatch_order has a coverage entry
    for name in dispatch_order:
        coverage.setdefault(name, 0.0)

    return coverage, new_storage_state, shortfall, excess