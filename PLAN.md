# Frontend Implementation Plan

## Goal

Static web app (GitHub Pages) that displays pre-computed ENTSO-E production data as a stacked area chart.  
User selects country + date range, views/edits installed capacity per source, clicks **Plot** to render.

---

## Architecture

```
frontend/
  index.html          # Single-page app (HTML + CSS + JS)
  data/
    index.json        # Registry: available countries + date ranges
    production_IT.csv # Hourly production per source (kW)
    production_DE.csv
    ...
    capacity_IT.json  # Installed capacity (MW) per source
    capacity_DE.json
    ...
```

Data is produced offline by Python backend and shipped as static assets.  
No build step, no backend at runtime. Chart.js via CDN.

---

## Step 1 — Frontend Data Contract

### 1a. Production CSV (`frontend/data/production_{COUNTRY}.csv`)

Same format as existing `fetch.py` output:

```
timestamp,demand_kw,Biomass,Geothermal,Hydro Pumped Storage,Hydro Run-of-river and poundage,Hydro Water Reservoir,Solar,Wind Offshore,Wind Onshore,Energy storage
2026-01-01T00:00:00Z,35000.0,400.0,570.0,500.0,3000.0,800.0,0.0,5.0,1200.0,0.0
...
```

**Requirements:**
- Timestamps ISO 8601 UTC, 15-minute or hourly intervals (frontend aggregates to hourly)
- Columns: `timestamp`, `demand_kw`, then one per production source (PSR)
- All values in kW (float)
- One file per country, full year
- Missing sources → column with zeros (all countries share same column set)

### 1b. Capacity JSON (`frontend/data/capacity_{COUNTRY}.json`)

Same format as existing `data/capacity_XX.json`:

```json
{
  "country": "IT",
  "updated": "2026-06-24",
  "sources": {
    "Solar": 5927,
    "Wind Onshore": 11651,
    "Wind Offshore": 30,
    "Hydro": 22089,
    "Gas": 45157,
    "Coal": 7654,
    "Nuclear": 0,
    "Other": 4980
  }
}
```

- Values in MW (float)
- Source keys match production CSV column names where applicable

Build a function that queries the capacity from a country fro mthe entsoe api i can use for updating these values offline.

### 1c. Index JSON (`frontend/data/index.json`)

```json
{
  "countries": [
    {
      "code": "IT",
      "name": "Italia",
      "date_start": "2026-01-01",
      "date_end": "2026-12-31"
    }
  ]
}
```

---

## Step 2 — Backend Adaptation

### 2a. Output target

Create `frontend/data/` directory. All backend output goes there.

### 2b. `export-frontend` command
I'd prefer a simple python script instead of a cli.

New entry point that:
1. Reads `data/countries.json` for country list
2. For each country, fetches full-year production from ENTSO-E (or reuses cached)
3. Copies/fetches capacity JSON
4. Writes production CSV and capacity JSON to `frontend/data/`
5. Generates `frontend/data/index.json`

**Implementation:** new script `export_frontend.py` or a `--export-frontend` flag on `fetch.py`.

### 2c. Column normalization

All production CSVs MUST share identical column set (union of all sources across all countries). Missing sources → 0-filled column.

---

## Step 3 — Frontend Build

### 3a. Structure

Single `frontend/index.html`:
- **Header** — placeholder `<header>` with app title
- **Controls bar** — country `<select>`, start/end `<input type="date">`, **[Plot]** `<button>`
- **Capacity panel** — editable `<input type="number">` per source, initially 0, populated from capacity JSON on country select
- **Chart area** — `<canvas>` for Chart.js stacked area
- **Footer** — placeholder `<footer>`

All CSS inline in `<style>`, all JS inline in `<script type="module">`.

### 3b. Dependencies

- Chart.js 4.x via jsdelivr CDN
- No other dependencies

### 3c. Behavior

| Event | Action |
|---|---|
| Page load | Fetch `data/index.json`, populate country dropdown |
| Country selected | Fetch `data/capacity_{CODE}.json`, populate capacity textboxes |
| **Plot** clicked | Fetch `data/production_{CODE}.csv`, parse, filter by date range, render Chart.js stacked area |

### 3d. Chart

- Stacked area chart: each production source as a filled layer
- Colors from `plot.py`'s `PLOT_COLORS` dictionary (ported to JS)
- X-axis: time (hours)
- Y-axis: kW
- Demand overlaid as a dashed line on top

### 3e. Styling

- Light background (`#f8f9fa` or similar)
- Clean sans-serif font
- Controls on a white card with subtle shadow
- Responsive: chart fills available width

---

## Files to Create/Modify

| File | Action |
|---|---|
| `PLAN.md` | This file |
| `frontend/index.html` | **Create** — full app |
| `frontend/data/` | **Create** dir — output target |
| `export_frontend.py` | **Create** — backend export script |
| `pyproject.toml` | **Modify** — add `export-frontend` CLI entry point |

---

## Non-Goals (for now)

- No dispatch/matching simulation (future step)
- No API calls from frontend (all data is static)
- No authentication or user accounts
- No mobile-specific layout (responsive enough, not optimized)
