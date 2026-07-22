"""Tests for the CsvReader."""

import pandas as pd
import tempfile
from pathlib import Path

import pytest

from energy_match.models import SourceMeta
from energy_match.readers.csv_reader import CsvReader


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures"


# Meta for the wide CSV sources (demand + solar + wind)
WIDE_META: dict[str, SourceMeta] = {
    "demand": SourceMeta(name="demand", category="demand", flexibility="inflexible"),
    "solar": SourceMeta(name="solar", category="production", flexibility="inflexible"),
    "wind": SourceMeta(name="wind", category="production", flexibility="inflexible"),
}


# ---------------------------------------------------------------------------
# Wide CSV tests
# ---------------------------------------------------------------------------

class TestWideRoundTrip:
    """Read the sample_wide.csv and verify the TimeSeries is correctly built."""

    def test_reads_three_timestamps(self):
        reader = CsvReader.from_wide(
            path=str(FIXTURES / "sample_wide.csv"),
            timestamp_col="timestamp",
            column_map={"demand": "demand", "solar": "solar", "wind": "wind"},
            sources_meta=WIDE_META,
        )
        ts = reader.read()
        assert len(ts.timestamps) == 3

    def test_has_two_production_sources(self):
        reader = CsvReader.from_wide(
            path=str(FIXTURES / "sample_wide.csv"),
            timestamp_col="timestamp",
            column_map={"demand": "demand", "solar": "solar", "wind": "wind"},
            sources_meta=WIDE_META,
        )
        ts = reader.read()
        assert set(ts.productions.keys()) == {"solar", "wind"}

    def test_expected_demand_values(self):
        reader = CsvReader.from_wide(
            path=str(FIXTURES / "sample_wide.csv"),
            timestamp_col="timestamp",
            column_map={"demand": "demand", "solar": "solar", "wind": "wind"},
            sources_meta=WIDE_META,
        )
        ts = reader.read()
        assert ts.demand.iloc[0] == pytest.approx(100.0)
        assert ts.demand.iloc[1] == pytest.approx(150.0)
        assert ts.demand.iloc[2] == pytest.approx(120.0)

    def test_timezone_is_utc(self):
        reader = CsvReader.from_wide(
            path=str(FIXTURES / "sample_wide.csv"),
            timestamp_col="timestamp",
            column_map={"demand": "demand", "solar": "solar", "wind": "wind"},
            sources_meta=WIDE_META,
        )
        ts = reader.read()
        assert ts.timestamps.tz is not None
        assert str(ts.timestamps.tz) == "UTC"

    def test_timestamps_are_hourly(self):
        reader = CsvReader.from_wide(
            path=str(FIXTURES / "sample_wide.csv"),
            timestamp_col="timestamp",
            column_map={"demand": "demand", "solar": "solar", "wind": "wind"},
            sources_meta=WIDE_META,
        )
        ts = reader.read()
        diffs = ts.timestamps.to_series().diff().dropna()
        assert (diffs == pd.Timedelta(hours=1)).all()

    def test_sources_meta_preserved(self):
        reader = CsvReader.from_wide(
            path=str(FIXTURES / "sample_wide.csv"),
            timestamp_col="timestamp",
            column_map={"demand": "demand", "solar": "solar", "wind": "wind"},
            sources_meta=WIDE_META,
        )
        ts = reader.read()
        assert ts.sources_meta["demand"].category == "demand"
        assert ts.sources_meta["solar"].category == "production"
        assert ts.sources_meta["wind"].category == "production"


# ---------------------------------------------------------------------------
# Narrow CSV tests
# ---------------------------------------------------------------------------

class TestNarrowRoundTrip:
    """Create separate demand/production narrow CSVs and read them back."""

    NARROW_META: dict[str, SourceMeta] = {
        "demand": SourceMeta(name="demand", category="demand", flexibility="inflexible"),
        "wind": SourceMeta(name="wind", category="production", flexibility="inflexible"),
    }

    @pytest.fixture(autouse=True)
    def _narrow_csvs(self, tmp_path: Path):
        """Create demand.csv and wind.csv in a temp directory."""
        demand_csv = tmp_path / "demand.csv"
        demand_csv.write_text(
            "timestamp,value\n"
            "2025-06-01T00:00:00Z,120.0\n"
            "2025-06-01T01:00:00Z,180.0\n"
        )
        wind_csv = tmp_path / "wind.csv"
        wind_csv.write_text(
            "timestamp,value\n"
            "2025-06-01T00:00:00Z,40.0\n"
            "2025-06-01T01:00:00Z,60.0\n"
        )
        self._demand_path = demand_csv
        self._wind_path = wind_csv
        return demand_csv, wind_csv

    def test_reads_two_timestamps(self):
        reader = CsvReader.from_narrow(
            demand_path=str(self._demand_path),
            timestamp_col="timestamp",
            value_col="value",
            production_paths={"wind": str(self._wind_path)},
            sources_meta=self.NARROW_META,
        )
        ts = reader.read()
        assert len(ts.timestamps) == 2

    def test_correct_demand_and_production(self):
        reader = CsvReader.from_narrow(
            demand_path=str(self._demand_path),
            timestamp_col="timestamp",
            value_col="value",
            production_paths={"wind": str(self._wind_path)},
            sources_meta=self.NARROW_META,
        )
        ts = reader.read()
        assert ts.demand.iloc[0] == pytest.approx(120.0)
        assert ts.demand.iloc[1] == pytest.approx(180.0)
        assert ts.productions["wind"].iloc[0] == pytest.approx(40.0)
        assert ts.productions["wind"].iloc[1] == pytest.approx(60.0)

    def test_sources_meta_preserved(self):
        reader = CsvReader.from_narrow(
            demand_path=str(self._demand_path),
            timestamp_col="timestamp",
            value_col="value",
            production_paths={"wind": str(self._wind_path)},
            sources_meta=self.NARROW_META,
        )
        ts = reader.read()
        assert ts.sources_meta["wind"].name == "wind"
        assert ts.sources_meta["wind"].category == "production"