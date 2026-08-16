"""Tests for core.export — offline build (production/capacity JSON + data.js)."""

import json

import pandas as pd
import pytest

from core.export import build


def _make_data_dir(tmp_path, code="IT"):
    """Create a data/ dir with one 15-min production CSV + one capacity JSON."""
    idx = pd.date_range("2026-08-07", periods=8, freq="15min", tz="UTC")
    df = pd.DataFrame({"timestamp": idx.strftime("%Y-%m-%dT%H:%M:%SZ")})
    df["demand_kw"] = [1000.0] * 8
    df["Solar"] = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0]
    df["Wind Onshore"] = [5.0] * 8
    df.to_csv(tmp_path / f"entsoe_{code}_20260807_20260807.csv", index=False)

    (tmp_path / f"capacity_{code}.json").write_text(
        json.dumps({"country": code, "sources": {"Solar": 5000.0, "Wind Onshore": 12000.0}})
    )
    return tmp_path


def test_build_writes_production_json(tmp_path):
    _make_data_dir(tmp_path)
    assert build(tmp_path, tmp_path / "frontend", verbose=False) == ["IT"]

    prod = json.loads((tmp_path / "frontend/data/production_IT.json").read_text())
    assert prod["country"] == "IT"
    assert prod["unit"] == "MW"
    assert prod["resolution"] == "15min"
    # 15-min rows kept exactly as downloaded (no aggregation)
    assert prod["timestamps"][:2] == ["2026-08-07T00:00:00Z", "2026-08-07T00:15:00Z"]
    assert prod["demand"] == [1000.0] * 8
    assert prod["sources"]["Solar"] == [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0]


def test_build_copies_capacity_json_as_is(tmp_path):
    _make_data_dir(tmp_path)
    build(tmp_path, tmp_path / "frontend", verbose=False)
    cap = json.loads((tmp_path / "frontend/data/capacity_IT.json").read_text())
    assert cap == {"country": "IT", "sources": {"Solar": 5000.0, "Wind Onshore": 12000.0}}


def test_build_writes_data_js_wrapper(tmp_path):
    _make_data_dir(tmp_path)
    build(tmp_path, tmp_path / "frontend", verbose=False)

    text = (tmp_path / "frontend/js/data.js").read_text()
    assert text.startswith("// Generated")
    assert "window.APP_DATA = " in text
    payload = text.split("window.APP_DATA = ", 1)[1].rstrip().rstrip(";")
    bundle = json.loads(payload)
    assert set(bundle) == {"production", "capacity"}
    assert set(bundle["production"]) == {"IT"}
    assert set(bundle["capacity"]) == {"IT"}
    # production payload inside data.js equals the standalone production JSON
    assert bundle["production"]["IT"] == json.loads(
        (tmp_path / "frontend/data/production_IT.json").read_text()
    )


def test_build_lengths_match(tmp_path):
    _make_data_dir(tmp_path)
    build(tmp_path, tmp_path / "frontend", verbose=False)
    prod = json.loads((tmp_path / "frontend/data/production_IT.json").read_text())
    n = len(prod["timestamps"])
    assert len(prod["demand"]) == n
    assert all(len(v) == n for v in prod["sources"].values())


def test_build_raises_when_no_production_csv(tmp_path):
    with pytest.raises(FileNotFoundError, match="fetch.py"):
        build(tmp_path, tmp_path / "frontend", verbose=False)


def test_build_raises_when_capacity_missing(tmp_path):
    _make_data_dir(tmp_path)
    (tmp_path / "capacity_IT.json").unlink()
    with pytest.raises(FileNotFoundError, match="capacity.py"):
        build(tmp_path, tmp_path / "frontend", verbose=False)
