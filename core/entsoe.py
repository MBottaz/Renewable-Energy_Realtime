"""ENSTO-E Transparency Platform data access layer.

Provides ``fetch_production()`` and ``query_installed_capacity()``.
"""

from __future__ import annotations

import os

import pandas as pd
from dotenv import load_dotenv
from entsoe import EntsoePandasClient

from core.config import DEFAULT_PSR_TYPES, PSR_NAME

# ── Helpers ──────────────────────────────────────────────────────────────


def _as_utc_series(obj: pd.Series | pd.DataFrame) -> pd.Series:
    """Normalise ENTSO-E output to a tz-aware UTC Series."""
    if isinstance(obj, pd.DataFrame):
        s = obj.iloc[:, 0]
    else:
        s = obj
    if s.index.tz is None:
        return s.tz_localize("UTC")
    return s.tz_convert("UTC")


def _process_multiindex(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse MultiIndex columns (PSR_CODE, 'Actual Aggregated') → single level."""
    if df.columns.nlevels > 1:
        try:
            df = df.xs("Actual Aggregated", level=1, axis=1)
        except KeyError:
            pass
    return df


def _resolve_api_key(api_key: str | None) -> str:
    """Return a valid API key or raise."""
    if api_key is None:
        load_dotenv()
        api_key = os.environ.get("ENTSOE_KEY")
    if not api_key:
        raise ValueError("ENTSOE_KEY not found. Set it in .env or export it.")
    return api_key


# ── Public API ───────────────────────────────────────────────────────────


def fetch_production(
    country: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    api_key: str | None = None,
    *,
    verbose: bool = True,
) -> pd.DataFrame:
    """Fetch generation and load (demand) data from ENTSO-E Transparency Platform.

    Parameters
    ----------
    country : str
        Two-letter country code (e.g. ``"IT"``, ``"DE"``).
    start : pd.Timestamp
        Start of the query range (UTC-aware).
    end : pd.Timestamp
        End of the query range (UTC-aware).
    api_key : str | None
        ENTSO-E API key.  If *None*, loaded from the ``ENTSOE_KEY`` environment
        variable via ``load_dotenv``.
    verbose : bool
        If True, print progress stderr-style messages.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns ``timestamp``, ``demand_kw``, and one column per
        production source (from :data:`DEFAULT_PSR_TYPES` mapped through
        :data:`PSR_NAME`).
    """
    key = _resolve_api_key(api_key)
    client = EntsoePandasClient(api_key=key)

    # 1. Load (demand)
    if verbose:
        print(f"Fetching load for {country} \u2026")
    load_raw = client.query_load(country, start=start, end=end)
    load_series = _as_utc_series(load_raw).astype("float64")
    timestamps = load_series.index

    # 2. Generation — single call for all PSR types
    productions: dict[str, pd.Series] = {}
    if verbose:
        print(f"  Fetching generation for {country} \u2026")
    try:
        raw = client.query_generation(country, start=start, end=end)
        raw = _process_multiindex(raw)
        for psr in DEFAULT_PSR_TYPES:
            name = PSR_NAME.get(psr, psr)
            if name not in raw.columns:
                if verbose:
                    print(f"  ({name} not in response)")
                continue
            series = _as_utc_series(raw[name]).astype("float64")
            series = series.reindex(timestamps).fillna(0.0)
            productions[name] = series
    except Exception as exc:
        if verbose:
            print(f"  (generation unavailable: {exc})")

    # 3. Build wide DataFrame
    df = pd.DataFrame({"timestamp": timestamps, "demand_kw": load_series.values})
    for name, series in productions.items():
        df[name] = series.values

    return df


def query_installed_capacity(
    country: str,
    api_key: str | None = None,
    year: int = 2025,
) -> dict[str, float]:
    """Query installed generation capacity for a country from ENTSO-E.

    Parameters
    ----------
    country : str
        Two-letter country code (e.g. ``"IT"``, ``"DE"``, ``"FR"``).
    api_key : str | None
        ENTSO-E API key. If None, loaded from ``ENTSOE_KEY`` env var.
    year : int
        Calendar year to query (default 2025).

    Returns
    -------
    dict[str, float]
        Mapping of canonical source name → installed capacity in MW.
        Returns an empty dict if the API returns no data.
    """
    key = _resolve_api_key(api_key)
    client = EntsoePandasClient(api_key=key)

    start = pd.Timestamp(f"{year}-01-01", tz="UTC")
    end = pd.Timestamp(f"{year}-12-31", tz="UTC")

    df = client.query_installed_generation_capacity(country, start=start, end=end)

    if df.empty:
        return {}

    row = df.iloc[0]
    result: dict[str, float] = {}
    for col in df.columns:
        name = PSR_NAME.get(col, col)
        val = row[col]
        if pd.notna(val):
            result[name] = float(val)

    return result