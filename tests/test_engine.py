"""Integration tests for core.engine.match() + write_match_results()."""

from pathlib import Path

import pandas as pd

from core.engine import match, write_match_results

FIXTURE = Path(__file__).parent / "fixtures" / "sample_production.csv"


def test_match_runs_on_fixture(tmp_path):
    df = pd.read_csv(FIXTURE)
    results = match(df)

    assert len(results["coverage"]) == len(df)
    assert len(results["shortfall"]) == len(df)
    assert len(results["excess"]) == len(df)

    # Invariant: coverage + shortfall == demand for every row
    demand = df["demand_kw"].to_numpy()
    cov_sum = results["coverage"].sum(axis=1).to_numpy()
    shortfall = results["shortfall"]
    assert abs(cov_sum + shortfall - demand).max() < 1e-6

    # No negative values anywhere
    assert (results["coverage"].to_numpy() >= 0).all()
    assert all(s >= 0 for s in results["shortfall"])
    assert all(e >= 0 for e in results["excess"])


def test_match_summary_stats():
    df = pd.read_csv(FIXTURE)
    results = match(df)
    summary = results["summary"]

    assert 0.0 <= summary["renewable_share"] <= 1.0
    assert summary["num_hours"] == len(df)
    assert summary["total_demand_mwh"] > 0
    assert set(summary["sources"]) <= set(df.columns) - {"timestamp", "demand_kw"}


def test_write_match_results_creates_files(tmp_path):
    df = pd.read_csv(FIXTURE)
    results = match(df)
    out_dir = write_match_results(results, tmp_path / "out")

    for name in ("coverage.csv", "shortfall.csv", "excess.csv", "summary.json"):
        assert (out_dir / name).exists(), f"missing {name}"

    summary = pd.read_json(out_dir / "summary.json", typ="series")
    assert summary["num_hours"] == len(df)


def test_match_ignores_unknown_columns(tmp_path):
    df = pd.read_csv(FIXTURE)
    df["Totally Unknown Source"] = 123.0
    results = match(df)
    assert "Totally Unknown Source" not in results["coverage"].columns


def test_match_with_storage_initialised():
    # Fixture has "Energy storage" column; ensure storage state is tracked.
    df = pd.read_csv(FIXTURE)
    results = match(df)
    assert results["storage_names"] == ["Energy storage"]
    assert results["storage_soc"] is not None
