"""Frontend build — turns downloaded ENTSO-E data into static JSON + JS wrapper.

The frontend is fully static and works by opening ``index.html`` from disk
(``file://``), where browsers block ``fetch()``.  This module therefore reads
the raw data already downloaded into ``data/`` (no network) and emits:

- ``frontend/data/production_<CC>.json`` — 15-min generation/load series,
  mirroring the ENTSO-E generation API output (kept at 15-min granularity;
  aggregation to hourly happens in JavaScript, see ``frontend/js/app.js``);
- ``frontend/data/capacity_<CC>.json`` — installed capacity by source,
  copied as-is from ``data/capacity_<CC>.json`` (mirrors the capacity API);
- ``frontend/js/data.js`` — thin wrapper ``window.APP_DATA = {production, capacity}``
  so the browser can read the data from ``file://``.

Public API:

- ``build()`` — offline build: ``data/`` → ``frontend/data/`` + ``frontend/js/data.js``
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from core.config import DATA_DIR, FRONTEND_DIR


# ── Discovery helpers ────────────────────────────────────────────────────


def _discover_production_files(data_dir: Path) -> dict[str, Path]:
    """Find ``data/entsoe_<CC>_<start>_<end>.csv`` → {country code: path}."""
    files: dict[str, Path] = {}
    for path in sorted(Path(data_dir).glob("entsoe_*_*.csv")):
        parts = path.stem.split("_")  # ["entsoe", "IT", "20260807", "20260814"]
        if len(parts) == 4 and parts[0] == "entsoe":
            files[parts[1]] = path
    return files


def _production_json(code: str, csv_path: Path) -> dict[str, object]:
    """Build a ``production_<CC>.json`` payload from a raw 15-min CSV.

    The 15-min rows are kept exactly as downloaded — hourly aggregation is
    deliberately deferred to JavaScript.
    """
    df = pd.read_csv(csv_path)
    if "timestamp" not in df.columns or "demand_kw" not in df.columns:
        raise ValueError(f"{csv_path}: missing 'timestamp' or 'demand_kw' column")

    ts = pd.to_datetime(df["timestamp"])
    sources = sorted(set(df.columns) - {"timestamp", "demand_kw"})

    def series(col: str) -> list[float]:
        return [round(float(x), 3) if pd.notna(x) else 0.0 for x in df[col]]

    return {
        "country": code,
        "unit": "MW",
        "resolution": "15min",
        "timestamps": [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in ts],
        "demand": series("demand_kw"),
        "sources": {s: series(s) for s in sources},
    }


# ── Build ────────────────────────────────────────────────────────────────


def build(
    data_dir: str | Path = DATA_DIR,
    frontend_dir: str | Path = FRONTEND_DIR,
    *,
    verbose: bool = True,
) -> list[str]:
    """Offline build: ``data/`` → ``frontend/data/*.json`` + ``frontend/js/data.js``.

    Reads ``data/entsoe_<CC>_*.csv`` (production) and ``data/capacity_<CC>.json``
    (installed capacity) and writes, per country:

    - ``frontend/data/production_<CC>.json``
    - ``frontend/data/capacity_<CC>.json`` (copied as-is)

    plus ``frontend/js/data.js`` wrapping everything in ``window.APP_DATA``.

    Raises ``FileNotFoundError`` naming the missing file and the download
    script to run first (``fetch.py`` / ``capacity.py``).

    Returns the sorted list of built country codes.
    """
    data_dir = Path(data_dir)
    frontend_dir = Path(frontend_dir)
    data_out = frontend_dir / "data"
    js_out = frontend_dir / "js"

    production_files = _discover_production_files(data_dir)
    if verbose:
        print(f"Found production files: {list(production_files)}")

    if not production_files:
        raise FileNotFoundError(
            f"no production CSV in {data_dir}/ "
            "(expected data/entsoe_<CC>_<start>_<end>.csv).\n"
            "Run first:  python scripts/fetch.py --country IT --start ... --end ..."
        )

    production: dict[str, dict[str, object]] = {}
    capacity: dict[str, dict[str, object]] = {}

    for code, csv_path in sorted(production_files.items()):
        cap_path = data_dir / f"capacity_{code}.json"
        if not cap_path.exists():
            raise FileNotFoundError(
                f"missing {cap_path}.\n"
                f"Run first:  python scripts/capacity.py {code} --output {cap_path}"
            )
        try:
            cap = json.loads(cap_path.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError(f"{cap_path}: invalid JSON ({exc})") from exc

        prod = _production_json(code, csv_path)
        production[code] = prod
        capacity[code] = cap

        data_out.mkdir(parents=True, exist_ok=True)
        (data_out / f"production_{code}.json").write_text(
            json.dumps(prod, indent=2) + "\n"
        )
        (data_out / f"capacity_{code}.json").write_text(
            json.dumps(cap, indent=2) + "\n"
        )
        if verbose:
            print(f"  → frontend/data/production_{code}.json")
            print(f"  → frontend/data/capacity_{code}.json")

    bundle = {"production": production, "capacity": capacity}
    js_out.mkdir(parents=True, exist_ok=True)
    out = js_out / "data.js"
    out.write_text(
        "// Generated by scripts/build.py — do not edit by hand.\n"
        "window.APP_DATA = " + json.dumps(bundle) + ";\n"
    )
    if verbose:
        print(f"  → {out} ({out.stat().st_size / 1024:.0f} KB)")

    return sorted(production)
