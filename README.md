# Renewable Energy Realtime

Modular toolkit for matching renewable energy production to demand, simulating hourly dispatch with configurable source priority and storage.

## Directory Structure

```
core/                     # Reusable Python library (no install needed)
  config.py               # Constants: PSR map, source classifications, dispatch order, colors, countries, paths
  entsoe.py               # ENTSO-E production data access (capacity is manual)
  dispatch.py             # Pure dispatch logic: dispatch_hour()
  engine.py               # Orchestrator: match() + write_match_results()
  plot.py                 # plot_match_results() — stacked area chart
  export.py               # Frontend-asset export: build() — data/ → frontend/data/*.json + js/data.js
scripts/                  # Thin runnable CLIs (python scripts/<name>.py)
  fetch.py                # Fetch ENTSO-E generation → CSV (data/)
  capacity.py             # Write hand-maintained installed capacity (MW)
  match.py                # Run dispatch simulation → output/
  plot.py                 # Plot match results → PNG
  build.py                # Offline build: data/ → frontend/data/*.json + js/data.js
  validate.py             # Offline end-to-end smoke check
frontend/                 # Static site (GitHub Pages friendly)
  index.html              # Page skeleton (filters + production/capacity charts)
  css/style.css
  js/app.js               # All frontend logic (plain JS, no build step)
  js/chart.umd.js         # Vendored Chart.js v4 — no CDN/network needed
  js/data.js              # Generated data bundle (window.APP_DATA) — committed
tests/                    # pytest suites (offline, mocked ENTSO-E)
data/                     # Raw fetched CSVs (gitignored)
output/                   # Match/plot results (gitignored)
docs/                     # PLAN.md, sources.md
```

## How the Engine Works

`match()` (in `core/engine.py`) runs the hourly dispatch simulation over a DataFrame.

### Data Flow

```
DataFrame ──► match() ──► results dict (coverage, shortfall, excess, storage_soc, summary)
                   │
                   └──► write_match_results() ──► output/ (CSVs + summary.json)
```

### Per-Hour Dispatch Algorithm (`dispatch_hour` in `core/dispatch.py`)

A single hour follows a 4-step procedure:

**Step 1 — Inflexible first** — Must-run sources (solar, wind, etc.) are dispatched in priority order up to remaining demand. Whatever isn't needed becomes excess/curtailment.

**Step 2 — Storage discharge** — If demand remains unmet, storage sources discharge (respecting `max_discharge_rate_kw` and current SOC).

**Step 3 — Flexible sources** — Any remaining gap is filled by flexible/fossil dispatchable sources.

**Step 4 — Recharge storage from excess** — If production still exceeds demand, the *reverse* dispatch order is used to charge storage.

| Output | Meaning |
|--------|---------|
| `coverage` | {source: kW} dispatched to meet demand (storage discharge included; charging is not) |
| `shortfall` | Unmet demand (kW, ≥0) |
| `excess` | Production neither dispatched nor stored (= curtailment, kW, ≥0) |
| `new_storage_state` | Updated SOC (kWh) per storage source |

### Efficiency Convention

- **Charge side**: drawing `E/η` from the grid stores `E` kWh in the battery (round-trip losses are on the charge leg).
- **Discharge side**: drawing `E` kWh from the battery delivers `E` kWh to the grid (no loss on discharge).

## CLI Usage

Run any script from the project root (`python scripts/…` or `uv run python scripts/…`).

### Fetch ENTSO-E data

```
python scripts/fetch.py --country IT --start 2025-01-01 --end 2025-01-08
python scripts/fetch.py --country IT --start 2025-08-01 --end 2026-07-31
```

Writes `data/entsoe_<CC>_<start>_<end>.csv`.

### Set installed capacity

```
python scripts/capacity.py            # defaults to IT (no API call)
python scripts/capacity.py IT --year 2025
```

### Run the dispatch simulation

```
python scripts/match.py data/entsoe_IT_20260101_20260108.csv
python scripts/match.py data.csv --output-dir output/my_run
```

Writes `coverage.csv`, `shortfall.csv`, `excess.csv`, `storage_soc.csv` (if storage), `summary.json` into `output/`.

### Plot match results

```
python scripts/plot.py output/
python scripts/plot.py output/ --output output/chart.png --show-storage
```

### Build the static frontend (offline — no API key)

Complete offline workflow:

```
python scripts/fetch.py --country IT --start 2025-08-01 --end 2026-07-31  # 1. download one year
python scripts/capacity.py IT                      # 2. hand-maintained capacity → data/capacity_IT.json
python scripts/build.py                            # 3. regenerate frontend assets
# 4. open frontend/index.html (double-click — works via file://, no server)
```

`build.py` reads `data/entsoe_<CC>_*.csv` and `data/capacity_<CC>.json`, writes
per-country JSON files (`frontend/data/production_<CC>.json` at 15-min
resolution, `frontend/data/capacity_<CC>.json` copied as-is), and generates the
`frontend/js/data.js` wrapper (`window.APP_DATA`) that lets the page load from
disk. If a required `data/` file is missing it names the file and the script
to run first (`fetch.py` / `capacity.py`).

## Python API

```python
from core import match, fetch_production, SourceMeta

# Fetch data
df = fetch_production("IT", start, end, api_key)

# Run the matching engine
results = match(df)
write_match_results(results, "output/")
```

## Frontend

Fully static single-page app (HTML + CSS + JS). No build step, no backend, no network at runtime — Chart.js is vendored locally and the data ships in `js/data.js`, so the page works by simply opening `frontend/index.html` from disk (`file://`).

To preview locally:

```
python -m http.server -d frontend
```

### How it works

`js/data.js` assigns `window.APP_DATA` (unit `MW`; per country: `timestamps`,
`demand`, per-source production series, and installed capacity). On load,
`js/app.js` populates the country selector from the data, sets the date inputs
to the full timestamp span, renders the installed-capacity panel, and plots the
full available range by default. You can select any covered period, including a
full year such as `01/08/2025` to `31/07/2026`. Changing the country or either date immediately re-aggregates the selected
range: 15-minute ENTSO-E rows are bucketed by hour (UTC) and summed, and the
×0.25 h conversion to hourly energy (MWh) is applied at display time. The
production result is drawn with Chart.js as stacked production areas plus a
demand line (on its own stack, so it isn't added on top of the areas). Installed
capacity is shown as a pie chart and a complete value list, including zero-value
technologies. The selected country and date range are persisted in the URL when
the browser allows history updates.

The dispatch simulation is **not** part of the frontend — it runs offline in
the Python engine (`scripts/match.py` → `output/`), and the frontend only
visualizes observed production, demand, and installed capacity. For Italy, the
2025 installed values are maintained by hand: 43,512 MW solar and 13,629 MW
combined onshore/offshore wind. The simulation is kept as-is for now; porting it
to JavaScript is planned for the future.

## Validation

```
uv run pytest                  # unit/integration tests (offline)
uv run python scripts/validate.py   # end-to-end offline smoke check
```

Both must pass before/after any change.

## Data Format

Wide-format CSV with columns: `timestamp` (ISO 8601 UTC), `demand_kw`, then one column per production source (all values in kW).

## License

This project is part of the Renewable Energy Realtime project and follows the same licensing terms.
