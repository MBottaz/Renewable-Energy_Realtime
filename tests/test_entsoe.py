"""Tests for core.entsoe with a mocked EntsoePandasClient."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from core.entsoe import fetch_production, query_installed_capacity


@pytest.fixture
def mock_client():
    """Return a mock client that returns plausible ENTSO-E responses."""
    with patch("core.entsoe.EntsoePandasClient") as cls:
        client = MagicMock()
        cls.return_value = client

        # Mock load data
        idx = pd.date_range("2026-01-01", periods=3, freq="h", tz="UTC")
        load = pd.Series([35000.0, 34000.0, 33000.0], index=idx)
        client.query_load.return_value = load

        # Mock generation data with MultiIndex columns — entsoe-py uses
        # canonical source names as the first level (mapped via PSRTYPE_MAPPINGS).
        gen = pd.DataFrame(
            {
                ("Solar", "Actual Aggregated"): [500.0, 1200.0, 0.0],
                ("Wind Onshore", "Actual Aggregated"): [8000.0, 7500.0, 7000.0],
            },
            index=idx,
        )
        gen.columns = pd.MultiIndex.from_tuples(gen.columns)
        client.query_generation.return_value = gen

        # Mock installed capacity
        cap = pd.DataFrame(
            {"Solar": [5000.0], "Wind Onshore": [12000.0]},
            index=pd.Index(["IT"]),
        )
        client.query_installed_generation_capacity.return_value = cap

        yield client


def test_fetch_production_returns_wide_dataframe(mock_client):
    start = pd.Timestamp("2026-01-01", tz="UTC")
    end = pd.Timestamp("2026-01-02", tz="UTC")
    df = fetch_production("IT", start, end, api_key="fake-key", verbose=False)

    assert "timestamp" in df.columns
    assert "demand_kw" in df.columns
    assert "Solar" in df.columns
    assert "Wind Onshore" in df.columns
    assert len(df) == 3


def test_fetch_production_handles_empty_generation(mock_client):
    mock_client.query_generation.return_value = pd.DataFrame()
    start = pd.Timestamp("2026-01-01", tz="UTC")
    end = pd.Timestamp("2026-01-02", tz="UTC")
    df = fetch_production("IT", start, end, api_key="fake-key", verbose=False)

    assert "demand_kw" in df.columns
    # No production columns
    assert len(df.columns) == 2


def test_query_installed_capacity_returns_dict(mock_client):
    cap = query_installed_capacity("IT", api_key="fake-key")
    assert "Solar" in cap
    assert cap["Solar"] == 5000.0
    assert cap["Wind Onshore"] == 12000.0


def test_query_installed_capacity_empty(mock_client):
    mock_client.query_installed_generation_capacity.return_value = pd.DataFrame()
    cap = query_installed_capacity("IT", api_key="fake-key")
    assert cap == {}


def test_missing_api_key_raises():
    with pytest.raises(ValueError, match="ENTSOE_KEY"):
        query_installed_capacity("IT", api_key="")