"""
ENTSO-E Transparency Platform reader.

Wraps ``entsoe.EntsoePandasClient`` and returns a ``TimeSeries``
instead of writing raw CSVs.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from entsoe import EntsoePandasClient

from energy_match.config import ENTSOE_COLUMN_MAP, SOURCE_CLASSIFICATIONS
from energy_match.models import SourceMeta, TimeSeries
from energy_match.readers.base import Reader


def _process_multiindex_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Extract 'Actual Aggregated' level from a MultiIndex columns DataFrame.

    ENTSO-E generation queries sometimes return a MultiIndex with columns
    ``(PSR_CODE, "Actual Aggregated")``.  This helper collapses it to a
    single level.
    """
    if df.columns.nlevels > 1:
        try:
            df = df.xs("Actual Aggregated", level=1, axis=1)
        except KeyError:
            pass  # leave as-is if the level doesn't exist
    return df


class EntsoeReader(Reader):
    """Read load and generation data from the ENTSO-E Transparency Platform.

    Parameters
    ----------
    api_key:
        ENTSO-E REST API security token.
    country_code:
        Two-letter country code (e.g. ``"IT"``).
    start:
        Start timestamp (UTC).  Anything parseable by ``pd.Timestamp``.
    end:
        End timestamp (UTC).  Anything parseable by ``pd.Timestamp``.
    psr_types:
        ENTSO-E PSR type codes to query.  Defaults to the renewable + hydro
        types used by the legacy ``import_API.py``.
    """

    _DEFAULT_PSR_TYPES = [
        "B01",  # Biomass
        "B09",  # Geothermal
        "B10",  # Hydro Pumped Storage
        "B11",  # Hydro Run-of-river and poundage
        "B12",  # Hydro Water Reservoir
        "B15",  # Other renewable
        "B16",  # Solar
        "B18",  # Wind Offshore
        "B19",  # Wind Onshore
    ]

    def __init__(
        self,
        api_key: str,
        country_code: str,
        start: str | pd.Timestamp | datetime,
        end: str | pd.Timestamp | datetime,
        psr_types: list[str] | None = None,
    ) -> None:
        self._api_key = api_key
        self._country_code = country_code
        self._start = pd.Timestamp(start)
        self._end = pd.Timestamp(end)
        self._psr_types = psr_types or list(self._DEFAULT_PSR_TYPES)
        self._client = EntsoePandasClient(api_key=api_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read(self) -> TimeSeries:
        """Query load and generation, return a single ``TimeSeries``."""
        # --- Load (demand) ---
        load_raw = self._client.query_load(
            self._country_code,
            start=self._start,
            end=self._end,
        )
        load_series = _as_utc_series(load_raw).astype("float64")

        # --- Generation per PSR type ---
        generation_data: dict[str, pd.DataFrame] = {}
        for psr in self._psr_types:
            try:
                raw = self._client.query_generation(
                    self._country_code,
                    start=self._start,
                    end=self._end,
                    psr_type=psr,
                )
                raw = _process_multiindex_columns(raw)
                generation_data[psr] = raw
            except Exception:
                # Some PSR types may not be available for a given country/period
                continue

        # Build productions dict from the first common index
        # (ENTSO-E returns hourly data, but columns may differ)
        timestamps = load_series.index
        productions: dict[str, pd.Series] = {}
        sources_meta: dict[str, SourceMeta] = {
            "demand": SourceMeta("demand", "demand", "inflexible"),
        }

        for psr, df in generation_data.items():
            name = ENTSOE_COLUMN_MAP.get(psr, psr)
            meta = SOURCE_CLASSIFICATIONS.get(name)
            if meta is None:
                continue  # skip unknown sources

            # Extract the single column (or the first column)
            series = df.iloc[:, 0].astype("float64")
            # Align to the load index
            series = series.reindex(timestamps).fillna(0.0)
            productions[name] = series
            sources_meta[name] = meta

        return TimeSeries(
            timestamps=timestamps,
            demand=load_series,
            productions=productions,
            sources_meta=sources_meta,
        )

    def read_installed_capacity(self) -> pd.DataFrame:
        """Query installed generation capacity.

        Returns a DataFrame with PSR codes as columns and capacity in MW.
        """
        # ENTSO-E's query_installed_generation_capacity expects end date
        # to be *before* the actual end (it returns data for the range).
        adjusted_end = self._end - timedelta(days=1)
        df = self._client.query_installed_generation_capacity(
            self._country_code,
            start=self._start,
            end=adjusted_end,
            psr_type=None,
        )
        # Rename columns to human-readable names
        df = df.rename(columns=ENTSOE_COLUMN_MAP)
        return df


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _as_utc_series(obj: Any) -> pd.Series:
    """Convert whatever ENTSO-E returns into a tz-aware UTC Series.

    ENTSO-E may return a DataFrame, a Series, or a tuple.  This normalises
    to a single-column Series with a UTC DatetimeIndex.
    """
    if isinstance(obj, tuple):
        # Some queries return (DataFrame, metadata)
        obj = obj[0]
    if isinstance(obj, pd.DataFrame):
        # Take the first (or only) column
        obj = obj.iloc[:, 0]
    if not isinstance(obj, pd.Series):
        raise TypeError(f"Expected pd.Series from ENTSO-E, got {type(obj)}")
    # Ensure UTC
    if obj.index.tz is not None:
        obj.index = obj.index.tz_convert("UTC")
    return obj