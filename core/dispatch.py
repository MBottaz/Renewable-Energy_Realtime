"""Pure dispatch logic — single-hour demand/supply balancing.

The public function ``dispatch_hour()`` is a pure function with no I/O.
"""

from __future__ import annotations

from core.config import DISPATCH_ORDER, SOURCE_CLASSIFICATIONS, SourceMeta


def build_dispatch_order(
    present_sources: set[str],
    sources_meta: dict[str, SourceMeta] | None = None,
    default_order: list[str] | None = None,
) -> list[str]:
    """Build a dispatch order from the default order, filtered to present sources.

    Parameters
    ----------
    present_sources : set[str]
        Names of sources actually present in the data.
    sources_meta : dict[str, SourceMeta] | None
        Source classifications.  If None, uses ``SOURCE_CLASSIFICATIONS``.
    default_order : list[str] | None
        Default priority order.  If None, uses ``DISPATCH_ORDER``.

    Returns
    -------
    list[str]
        Ordered source names (only those in *present_sources*).
    """
    if sources_meta is None:
        sources_meta = SOURCE_CLASSIFICATIONS
    order = default_order if default_order is not None else DISPATCH_ORDER
    return [name for name in order if name in present_sources and name in sources_meta]


def dispatch_hour(
    demand_kw: float,
    productions_kw: dict[str, float],
    dispatch_order: list[str],
    storage_state: dict[str, float],
    sources_meta: dict[str, SourceMeta],
) -> tuple[dict[str, float], dict[str, float], float, float]:
    """Dispatch one hour of generation.

    Returns
    -------
    tuple[dict[str, float], dict[str, float], float, float]
        ``(coverage, new_storage_state, shortfall, excess)``:

        - **coverage**: {source_name: kW dispatched toward demand}
        - **new_storage_state**: {name: SOC_kWh} after charge/discharge
        - **shortfall**: demand not covered (kW, >= 0)
        - **excess**: production not used by demand or storage charging (kW, >= 0)
    """
    remaining = demand_kw
    coverage: dict[str, float] = {}
    new_soc = dict(storage_state)

    # Step 1 — Inflexible sources (must-run, first in line)
    for name in dispatch_order:
        meta = sources_meta.get(name)
        if meta is None or meta.flexibility != "inflexible":
            continue
        prod = productions_kw.get(name, 0.0)
        used = min(prod, remaining)
        coverage[name] = used
        remaining -= used

    # Step 2 — Discharge storage to cover remaining demand
    if remaining > 0:
        for name in dispatch_order:
            meta = sources_meta.get(name)
            if meta is None or meta.flexibility != "storage":
                continue
            if remaining <= 0:
                break
            soc = new_soc.get(name, 0.0)
            rate = meta.max_discharge_rate_kw or 0.0
            discharge = min(remaining, rate, soc)
            if discharge > 0:
                coverage[name] = discharge
                new_soc[name] = soc - discharge
                remaining -= discharge

    # Step 3 — Flexible sources (dispatchable)
    if remaining > 0:
        for name in dispatch_order:
            meta = sources_meta.get(name)
            if meta is None or meta.flexibility != "flexible":
                continue
            if remaining <= 0:
                break
            prod = productions_kw.get(name, 0.0)
            used = min(prod, remaining)
            coverage[name] = used
            remaining -= used

    shortfall = max(0.0, remaining)

    # Excess = total production minus what went toward demand (excl. storage discharge)
    total_prod = sum(productions_kw.values())
    dispatched_no_storage = sum(
        v
        for name, v in coverage.items()
        if sources_meta.get(name) is None
        or sources_meta[name].flexibility != "storage"
    )
    excess = max(0.0, total_prod - dispatched_no_storage)

    # Step 4 — Charge storage from excess (reverse priority)
    if excess > 0:
        for name in reversed(dispatch_order):
            meta = sources_meta.get(name)
            if meta is None or meta.flexibility != "storage":
                continue
            if excess <= 0:
                break
            soc = new_soc.get(name, 0.0)
            charge_rate = meta.max_charge_rate_kw or 0.0
            capacity = meta.capacity_kwh or 0.0
            efficiency = meta.roundtrip_efficiency or 1.0
            headroom = capacity - soc
            max_by_capacity = headroom / efficiency if efficiency > 0 else 0.0
            charge = min(excess, charge_rate, max_by_capacity)
            if charge > 0:
                new_soc[name] = soc + charge * efficiency
                excess -= charge

    # Ensure every source appears in coverage
    for name in dispatch_order:
        coverage.setdefault(name, 0.0)

    return coverage, new_soc, shortfall, excess