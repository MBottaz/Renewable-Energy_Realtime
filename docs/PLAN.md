# Plan — Offline JSON data pipeline + static Chart.js frontend

> Status: **APPROVED — ready for implementation.**

## 0. Context & locked decisions

The goal is to simplify the project to a two-step static architecture:

1. **Offline** download ENTSO-E production + installed capacity into `data/`.
2. **Static frontend** renders them with Chart.js, openable via `file://`.

Locked decisions (agreed with the user):

- **Keep 15-min granularity in the JSON files**; aggregation to hourly is done in
  JavaScript. Reason: the files stay faithful to the two API outputs, future
  graphs (15-min, hourly, daily) need no re-fetch, and file size is negligible.
- **Two distinct JSON files** mirroring the two API outputs:
  - `production_<CC>.json` ← generation/load time series (15-min, by source + demand)
  - `capacity_<CC>.json` ← installed generation capacity (by source)
- **`data.js` wrapper** (`window.APP_DATA = {production, capacity}`) is the only
  way the frontend can read data from `file://` (browsers block `fetch()` there).
  The two JSON files remain the canonical, inspectable artifacts.
- **Simulation code is kept untouched** (`core/dispatch.py`, `core/engine.py`,
  `core/plot.py`, `scripts/match.py`, `scripts/plot.py`, dispatch-related
  `core/config.py` content). It will be ported to JavaScript in the future — not now.
- **Hourly consumption math**: each 15-min value is power (MW). Hourly energy =
  sum of the ≤4 samples × 0.25 h (MWh). The raw sum is computed in JS; the ×0.25
  unit conversion is applied at display time.
- **No deployment.** Final step is a single commit.

### Target layout

```
data/                            # raw, gitignored (unchanged)
  entsoe_<CC>_<start>_<end>.csv  # 15-min, from scripts/fetch.py (unchanged)
  capacity_<CC>.json             # from scripts/capacity.py (unchanged)

scripts/
  fetch.py, capacity.py          # unchanged
  build.py                       # NEW — replaces scripts/export_frontend.py
  match.py, plot.py              # kept untouched (simulation)
  validate.py                    # updated

core/
  export.py                      # rewritten: build() → 2 JSON files + data.js
  entsoe.py, dispatch.py, engine.py, plot.py, config.py   # untouched

frontend/
  index.html, css/style.css      # minor cleanup
  js/app.js                      # loads APP_DATA, aggregates 15-min → hourly, renders
  js/chart.umd.js                # vendored (unchanged)
  js/data.js                     # generated thin wrapper
  data/
    production_<CC>.json         # generated — mirrors generation API (15-min)
    capacity_<CC>.json           # generated — mirrors capacity API
```

---

## Step 1 — Offline build step (`core/export.py` + `scripts/build.py`)

Replace the current online `export_frontend.py` with an offline build that reads
files already in `data/` (no API key, no network).

### Task 1.1 — Rewrite `core/export.py`

Implement a single `build(data_dir, frontend_dir)` function that:

1. Finds `data/entsoe_<CC>_*.csv` production files.
2. Writes `frontend/data/production_<CC>.json`:
   `{"country", "unit": "MW", "resolution": "15min", "timestamps", "demand", "sources"}`.
   Keep the 15-min rows exactly as downloaded (no aggregation).
3. Loads `data/capacity_<CC>.json` and writes it to `frontend/data/capacity_<CC>.json` as-is.
4. Writes `frontend/js/data.js` = `window.APP_DATA = {production: {...}, capacity: {...}};`.
5. Raises a clear error naming the missing file and the script to run first
   (`fetch.py` or `capacity.py`) when a required `data/` file is absent.

### Task 1.2 — Create `scripts/build.py`

Thin CLI calling `core.export.build()`. Defaults: `data/` → `frontend/`.

### Task 1.3 — Retire `scripts/export_frontend.py`

Delete it (superseded by `scripts/build.py`). Remove any remaining references in
`README.md` / `validate.py`.

### Task 1.4 — Rewrite `tests/test_export.py`

Cover: production JSON schema and length invariants; capacity JSON copy;
`data.js` round-trip; missing-file error; production-source coverage by
capacity (storage excepted, see validation).

### Step 1 validation (all functional — no visual checks)

```bash
# Unit tests pass
uv run pytest tests/test_export.py

# Build runs end-to-end on the real data/ and exits 0
uv run python scripts/build.py

# Every production JSON parses and has the required top-level keys
for f in frontend/data/production_*.json; do
  jq -e 'has("country") and has("unit") and has("resolution")
         and has("timestamps") and has("demand") and has("sources")' "$f" >/dev/null
done

# Lengths match: len(timestamps) == len(demand) == len(each source series)
python -c "
import json,glob
for p in glob.glob('frontend/data/production_*.json'):
    d=json.load(open(p)); n=len(d['timestamps'])
    assert len(d['demand'])==n, (p,'demand')
    assert all(len(v)==n for v in d['sources'].values()), (p,'sources')
print('lengths OK')"

# Resolution is 15 minutes (consecutive timestamps differ by 900 s)
python -c "
import json,glob
from datetime import datetime
for p in glob.glob('frontend/data/production_*.json'):
    ts=json.load(open(p))['timestamps']
    diffs={(datetime.fromisoformat(b)-datetime.fromisoformat(a)).total_seconds() for a,b in zip(ts,ts[1:])}
    assert diffs=={900.0}, (p,diffs)
print('15min resolution OK')"

# Production sources are covered by capacity, except 'Energy storage'
# (storage is not 'installed generation capacity' in the ENTSO-E API,
# so it legitimately has no capacity entry).
python -c "
import json,glob
for p in glob.glob('frontend/data/production_*.json'):
    prod=json.load(open(p)); cc=prod['country']
    cap=json.load(open(f'frontend/data/capacity_{cc}.json'))
    missing=set(prod['sources'])-set(cap['sources'])
    assert missing <= {'Energy storage'}, (cc, missing)
print('source/capacity coverage OK')"

# data.js is a valid wrapper that round-trips back to {production, capacity}
# (the file starts with a generated-comment header, so match the marker)
python -c "
import json
t=open('frontend/js/data.js').read()
marker='window.APP_DATA = '
assert marker in t, 'missing window.APP_DATA'
payload=t.split(marker,1)[1].rstrip().rstrip(';')
d=json.loads(payload)
assert set(d)=={'production','capacity'}, set(d)
print('data.js round-trip OK')"
```

---

## Step 2 — Frontend: load data + aggregate in JS (`frontend/js/app.js`)

### Task 2.1 — Load `window.APP_DATA`

`app.js` reads `window.APP_DATA.production` / `.capacity`. Country selector is
populated from the keys of `production`. No `fetch()`, no `XMLHttpRequest`.

### Task 2.2 — Date range from timestamps

Compute available `min`/`max` from each country's `timestamps` array and set the
date inputs as defaults. (Drops the old precompiled `index.json` — nothing else
may reference it.)

### Task 2.3 — Pure aggregation function

Add a pure, exported function `aggregateHourly(timestamps, values)` returning
`{labels: string[], sums: number[]}` — one entry per hour bucket, `sums[i]` =
raw sum of the ≤4 samples in that hour. The ×0.25 (MW·15min → MWh) conversion is
applied only at display time. Export it for node tests:
`if (typeof module !== 'undefined') module.exports = { aggregateHourly }`.

### Task 2.4 — Render capacity + hourly chart

Read-only capacity panel (one row per source + total) and a Chart.js stacked
chart fed by `aggregateHourly` over the selected range. Keep vendored
`js/chart.umd.js`.

### Task 2.5 — `index.html` / `css/style.css` cleanup

Minor only; no structural change. Remove any `index.json` references.

### Step 2 validation (functional — no screenshots/visual review)

```bash
# JS syntax is valid
node --check frontend/js/app.js

# aggregateHourly returns correct hourly sums on a known 15-min fixture:
#   00:00..00:45 → [10,10,20,40] = 80 ;  01:00 → [50] = 50
node -e "
const {aggregateHourly}=require('./frontend/js/app.js');
const ts=['2026-08-07T00:00:00Z','2026-08-07T00:15:00Z','2026-08-07T00:30:00Z','2026-08-07T00:45:00Z','2026-08-07T01:00:00Z'];
const v=[10,10,20,40,50];
const out=aggregateHourly(ts,v);
const exp=JSON.stringify({labels:['2026-08-07T00:00','2026-08-07T01:00'],sums:[80,50]});
if(JSON.stringify(out)!==exp){console.error('FAIL',out);process.exit(1)}
console.log('aggregateHourly OK');"

# app.js uses the data wrapper, never the network
grep -n 'window.APP_DATA' frontend/js/app.js
! grep -nE 'fetch\(|XMLHttpRequest|index\.json' frontend/js/app.js

# data.js and the two JSON files are all present
test -f frontend/js/data.js
test -f frontend/data/production_IT.json
test -f frontend/data/capacity_IT.json
```

---

## Step 3 — Validation script + docs

### Task 3.1 — Update `scripts/validate.py`

Replace frontend checks with functional ones: `frontend/js/data.js` exists and
round-trips; the two JSON files are valid; production sources covered by
capacity (except `Energy storage`, which is storage and not installed
generation capacity); `app.js` contains no `fetch()`/`XMLHttpRequest`/`index.json`.

### Task 3.2 — Update `README.md`

Document the offline workflow:
`fetch.py` → `capacity.py` → `build.py` → open `frontend/index.html`.
Add a note that the dispatch/plot simulation is kept and will be ported to JS
in the future (not now).

### Step 3 validation

```bash
uv run python scripts/validate.py     # exits 0, every check passes
grep -n 'build.py' README.md          # workflow is documented
```

---

## Step 4 — Full suite + commit

### Task 4.1 — Run the full test suite

```bash
uv run pytest
uv run python scripts/validate.py
```

### Task 4.2 — Commit (no deploy)

```bash
git add -A
git commit -m "offline JSON data pipeline and static Chart.js frontend"
```

### Step 4 validation

```bash
git status --short      # clean (nothing left uncommitted)
git log -1 --oneline    # shows the new commit
```
