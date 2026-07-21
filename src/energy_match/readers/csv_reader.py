"""
CSV-backed reader for energy time series data.

Supports two input patterns:
- **Wide** — one file with columns ``[timestamp, demand, source1, source2, ...]``
- **Narrow** — one file per source, each with ``[timestamp, value]``
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from energy_match.models import SourceMeta, TimeSeries
from energy_match.readers.base import Reader


class CsvReader(Reader):
    """Read energy data from CSV files and return a ``TimeSeries``."""

    def __init__(
        self,
        read_fn: callable,
        sources_meta: dict[str, SourceMeta],
    ) -> None:
        self._read_fn = read_fn
        self._sources_meta = sources_meta

    def read(self) -> TimeSeries:
        return self._read_fn()

    # ------------------------------------------------------------------
    # Factory constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_wide(
        cls,
        path: str | Path,
        timestamp_col: str,
        column_map: dict[str, str],
        sources_meta: dict[str, SourceMeta],
        **pd_kwargs: Any,
    ) -> "CsvReader":
        """
        Build a CsvReader from a single wide CSV file.

        Parameters
        ----------
        path:
            Path to the CSV file.
        timestamp_col:
            Name of the timestamp column.
        column_map:
            Maps canonical names (``"demand"``, ``"Solar"``, …) to actual
            column names in the CSV.
        sources_meta:
            Metadata for every source (must include ``"demand"``).
        **pd_kwargs:
            Extra keyword arguments forwarded to ``pd.read_csv``.
        """
        column_map = dict(column_map)  # shallow copy

        def _read() -> TimeSeries:
            df = pd.read_csv(path, **pd_kwargs)
            # Parse timestamps
            df[timestamp_col] = pd.to_datetime(
                df[timestamp_col], utc=True
            )
            df = df.set_index(timestamp_col).sort_index()

            # Rename columns to canonical names
            reverse_map = {v: k for k, v in column_map.items()}
            df = df.rename(columns=reverse_map)

            # Build TimeSeries from the wide DataFrame
            return TimeSeries.from_wide_dataframe(df, sources_meta)

        return cls(_read, sources_meta)

    @classmethod
    def from_narrow(
        cls,
        demand_path: str | Path,
        timestamp_col: str,
        value_col: str,
        production_paths: dict[str, str | Path],
        sources_meta: dict[str, SourceMeta],
        **pd_kwargs: Any,
    ) -> "CsvReader":
        """
        Build a CsvReader from separate CSV files (one per source).

        Parameters
        ----------
        demand_path:
            Path to the demand CSV.
        timestamp_col:
            Name of the timestamp column in every file.
        value_col:
            Name of the value column in every file.
        production_paths:
            Maps source name -> file path for each production source.
        sources_meta:
            Metadata for every source (must include ``"demand"``).
        **pd_kwargs:
            Extra keyword arguments forwarded to ``pd.read_csv``.
        """
        production_paths = dict(production_paths)  # shallow copy

        def _read() -> TimeSeries:
            # Load demand
            demand_df = pd.read_csv(demand_path, **pd_kwargs)
            demand_df[timestamp_col] = pd.to_datetime(
                demand_df[timestamp_col], utc=True
            )
            demand_df = demand_df.set_index(timestamp_col).sort_index()
            timestamps = demand_df.index
            demand: pd.Series = demand_df[value_col].astype("float64")

            # Load each production source, align to demand index
            productions: dict[str, pd.Series] = {}
            for name, prod_path in production_paths.items():
                pdf = pd.read_csv(prod_path, **pd_kwargs)
                pdf[timestamp_col] = pd.to_datetime(
                    pdf[timestamp_col], utc=True
                )
                pdf = pdf.set_index(timestamp_col).sort_index()
                series = pdf[value_col].astype("float64")

                # Reindex to demand timestamps — forward-fill gaps, error
                # on timestamps in demand that are not in production
                series = series.reindex(timestamps, method=None)
                if series.isna().any():
                    raise ValueError(
                        f"Production source {name!r} is missing timestamps "
                        f"that exist in demand data; cannot align."
                    )
                productions[name] = series

            return TimeSeries(
                timestamps=timestamps,
                demand=demand,
                productions=productions,
                sources_meta=sources_meta,
            )

        return cls(_read, sources_meta)