#!/usr/bin/env python3
"""Offline end-to-end smoke check — no network required.

Validates:

1. ``core`` package imports cleanly.
2. ``match()`` + ``write_match_results()`` on the fixture CSV.
3. ``plot_match_results()`` produces a PNG.
4. ``build()`` — offline build: ``data/`` → ``frontend/data/*.json`` + ``js/data.js``.
5. Frontend: ``data.js`` round-trips, per-country JSON files are valid,
   production sources are covered by capacity (except ``Energy storage``),
   and ``app.js`` reads the wrapper — never the network.

Usage:
    uv run python scripts/validate.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Allow `python scripts/validate.py` to import core/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ── 1. Import check ─────────────────────────────────────────────────────
print("1. Checking core imports …", end=" ")
try:
    import core  # noqa: F401
    from core.config import (  # noqa: F401
        COUNTRIES,
        DISPATCH_ORDER,
        PSR_NAME,
        SOURCE_CLASSIFICATIONS,
    )
    from core.dispatch import dispatch_hour  # noqa: F401
    from core.engine import match, write_match_results  # noqa: F401
    from core.entsoe import fetch_production  # noqa: F401
    from core.export import build  # noqa: F401
    from core.plot import plot_match_results  # noqa: F401

    print("✅")
except Exception as exc:
    print(f"❌ {exc}")
    sys.exit(1)

# ── 2. Config consistency ───────────────────────────────────────────────
print("2. Checking config consistency …", end=" ")
try:
    assert set(SOURCE_CLASSIFICATIONS) == set(DISPATCH_ORDER)
    for code in ("B01", "B09", "B10", "B11", "B12", "B15", "B16", "B18", "B19", "B25"):
        assert code in PSR_NAME, f"Missing {code}"
    assert COUNTRIES
    assert COUNTRIES[0]["code"] == "IT"
    print("✅")
except Exception as exc:
    print(f"❌ {exc}")
    sys.exit(1)

# ── 3. Engine match + write on fixture ──────────────────────────────────
FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sample_production.csv"
print(f"3. Running match on {FIXTURE.name} …", end=" ")

import pandas as pd  # noqa: E402

if not FIXTURE.exists():
    print(f"❌ fixture not found at {FIXTURE}")
    sys.exit(1)

df = pd.read_csv(FIXTURE)
results = match(df)

# Invariants
demand = df["demand_kw"].to_numpy()
cov_sum = results["coverage"].sum(axis=1).to_numpy()
shortfall = results["shortfall"]
assert abs(cov_sum + shortfall - demand).max() < 1e-6, "coverage + shortfall != demand"
assert all(s >= 0 for s in shortfall)
assert all(e >= 0 for e in results["excess"])
summary = results["summary"]
assert 0.0 <= summary["renewable_share"] <= 1.0
print("✅")

# ── 4. Write results to temp dir ────────────────────────────────────────
print("4. Writing match results …", end=" ")
with tempfile.TemporaryDirectory() as tmp:
    out_dir = write_match_results(results, Path(tmp) / "out")
    for name in ("coverage.csv", "shortfall.csv", "excess.csv", "summary.json"):
        assert (out_dir / name).exists(), f"missing {name}"
    print("✅")

    # ── 5. Plot ─────────────────────────────────────────────────────────
    print("5. Plotting match results …", end=" ")
    try:
        chart_path = plot_match_results(
            input_dir=out_dir,
            output=Path(tmp) / "chart.png",
            show_demand=True,
            show_storage=False,
            title="Smoke Test",
        )
        assert chart_path.exists() and chart_path.stat().st_size > 0
        print("✅")
    except Exception as exc:
        print(f"❌ {exc}")
        sys.exit(1)

    # ── 6. Export helpers (build → JSON + data.js) ────────────────────
    print("6. Testing export helpers …", end=" ")
    # Create two synthetic production CSVs + capacity JSONs in a temp dir
    for code, sources in [
        ("IT", {"Solar": [1.0, 2.0, 3.0], "Wind Onshore": [5.0, 6.0, 7.0]}),
        ("DE", {"Solar": [1.0, 2.0, 3.0]}),
    ]:
        p = Path(tmp) / f"entsoe_{code}_20260101_20260101.csv"
        df = pd.DataFrame({"timestamp": ["2026-01-01T00:00:00Z"] * 3, "demand_kw": [1000.0] * 3})
        for k, v in sources.items():
            df[k] = v
        df.to_csv(p, index=False)
        # IT capacity includes both sources; DE capacity only Solar
        (Path(tmp) / f"capacity_{code}.json").write_text(
            json.dumps({"sources": {"Solar": 5000.0, "Wind Onshore": 12000.0}})
        )

    codes = build(Path(tmp), Path(tmp) / "frontend", verbose=False)
    assert sorted(codes) == ["DE", "IT"]
    assert (Path(tmp) / "frontend/data/production_IT.json").exists()
    assert (Path(tmp) / "frontend/data/capacity_DE.json").exists()
    assert (Path(tmp) / "frontend/js/data.js").exists()
    print("✅")

# ── 7. Frontend functional checks ───────────────────────────────────────
print("7. Checking frontend assets …", end=" ")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = PROJECT_ROOT / "frontend"

# Static skeleton
index_html = FRONTEND / "index.html"
assert index_html.exists(), "frontend/index.html missing"
html_text = index_html.read_text()
assert 'src="js/data.js"' in html_text, "index.html doesn't link js/data.js"
assert 'src="js/app.js"' in html_text, "index.html doesn't link js/app.js"
assert (FRONTEND / "css" / "style.css").exists(), "css/style.css missing"
assert (FRONTEND / "js" / "chart.umd.js").exists(), "js/chart.umd.js missing (vendor Chart.js locally)"

# js/data.js exists and round-trips back to {production, capacity}
data_js = FRONTEND / "js" / "data.js"
assert data_js.exists(), "frontend/js/data.js missing — run scripts/build.py"
marker = "window.APP_DATA = "
text = data_js.read_text()
assert marker in text, "data.js missing window.APP_DATA"
payload = text.split(marker, 1)[1].rstrip().rstrip(";")
bundle = json.loads(payload)
assert set(bundle) == {"production", "capacity"}, set(bundle)

# The two per-country JSON files exist, are valid, and match the bundle
for code in bundle["production"]:
    prod = json.loads((FRONTEND / "data" / f"production_{code}.json").read_text())
    cap = json.loads((FRONTEND / "data" / f"capacity_{code}.json").read_text())
    assert {"country", "unit", "resolution", "timestamps", "demand", "sources"} <= set(prod)
    assert {"country", "sources"} <= set(cap)
    assert prod["country"] == cap["country"] == code
    n = len(prod["timestamps"])
    assert len(prod["demand"]) == n, (code, "demand length")
    assert all(len(v) == n for v in prod["sources"].values()), (code, "source length")
    # Production sources are covered by capacity, except 'Energy storage'
    # (storage is not 'installed generation capacity' in the ENTSO-E API).
    missing = set(prod["sources"]) - set(cap["sources"])
    assert missing <= {"Energy storage"}, (code, missing)

# app.js must read the wrapper, never the network
app_js = (FRONTEND / "js" / "app.js").read_text()
assert "window.APP_DATA" in app_js, "app.js doesn't use window.APP_DATA"
for forbidden in ("fetch(", "XMLHttpRequest", "index.json"):
    assert forbidden not in app_js, f"app.js uses {forbidden!r}"
print(f"✅ ({data_js.stat().st_size / 1024:.0f} KB)")

# ── Done ────────────────────────────────────────────────────────────────
print("\n✅✅ VALIDATION PASSED ✅✅")