# Renewable Energy Match

Modular toolkit for matching renewable energy production to demand, simulating hourly dispatch with configurable source priority and storage.

## Directory Structure

```
src/
  energy_match/
    __init__.py       # Public API surface: exports match(), TimeSeries, SourceMeta, etc.
    engine.py         # Core orchestrator — runs dispatch over a full TimeSeries
    dispatch.py       # Pure dispatch logic: single-hour demand/supply balancing
    models.py         # Data classes: SourceMeta, TimeSeries, MatchResult
    config.py         # Default source classifications, dispatch order, ENTSOE map, plot colors
    cli.py            # CLI entry points: `energy-match match`, `energy-match fetch-entsoe`
    readers/
      base.py         # Abstract Reader base class
      csv_reader.py   # CsvReader (wide or narrow CSV input → TimeSeries)
      entsoe_reader.py# EntsoeReader (ENTSO-E API → TimeSeries)
    writers/
      base.py         # Abstract Writer base class
      csv_writer.py   # CsvWriter (MatchResult → CSVs + summary.json)
      plot_writer.py  # PlotWriter (MatchResult → stacked area chart)
tests/
  fixtures/           # Sample CSV for tests
  test_engine.py      # Integration tests for the full match() pipeline
  test_dispatch.py    # Unit tests for dispatch_hour()
  test_csv_reader.py  # Unit tests for CSV ingestion
data/                 # Data directory (gitignored, populated by fetch-entsoe or user CSVs)
legacy/               # REMOVED — superseded by the modular toolkit
```

## How the Engine Works (`engine.py`)

`engine.py` is the top-level orchestrator. Its single public function, `match(ts, dispatch_order?)`, runs the full dispatch simulation over a `TimeSeries` and returns a `MatchResult`.

### Data Flow

```
TimeSeries ──► match() ──► MatchResult
                  │
          ┌───────┴───────┐
          ▼               ▼
  build_dispatch    dispatch_hour
  _order()          (×N hours, per-timestamp)
                        │
                    coverage / shortfall / excess
```

### Step-by-Step

**1. Resolve dispatch order** (line 35–41) — If no explicit order is provided, `build_dispatch_order()` from `dispatch.py` sorts all production sources by flexibility group then priority within group:

| Group | Flexibility | Examples |
|-------|-------------|---------|
| 0 | Inflexible | Solar, Wind, Geothermal, River Hydro, Biomass, Nuclear |
| 1 | Storage | Hydro Pumped Storage |
| 2 | Flexible | Hydro Water Reservoir, Fossil Gas, Other |
| 3 | Unknown catch‑all | — |

Demand is explicitly excluded from the dispatch order.

**2. Initialise storage state** (lines 44–54) — For every source with `flexibility == "storage"`, the initial state-of-charge (`initial_soc_kwh`) is read from `SourceMeta`. Sources are identified by name for SOC recording.

**3. Hour-by-hour dispatch** (lines 63–88) — For each hourly timestamp, the engine:

1. Extracts the current hour's demand (`ts.demand.iloc[i]`) and production (`ts.productions[name].iloc[i]`).
2. Calls `dispatch_hour(demand_kw, productions_kw, dispatch_order, storage_state, sources_meta)`.
3. Records `coverage`, `shortfall`, and `excess`.
4. Tracks storage SOC changes (if any storage sources exist).
5. Advances `storage_state` for the next hour.

**4. Post-process & return** (lines 90–117) — Coverage records are assembled into a `DataFrame`. The `"demand"` column is dropped (it leaks from `dispatch_hour`'s `setdefault`). Storage SOC time series are built if applicable. Results are packaged into a `MatchResult`.

### Per-Hour Dispatch Algorithm (`dispatch_hour` in `dispatch.py`)

A single hour follows a 4-step procedure:

**Step 1 — Inflexible first** (lines 115–122)  
Must-run sources (solar, wind, etc.) are dispatched in priority order up to remaining demand. Whatever isn't needed becomes excess/curtailment.

**Step 2 — Storage discharge** (lines 127–141)  
If demand remains unmet after inflexible sources, storage sources discharge (respecting `max_discharge_rate_kw` and current SOC).

**Step 3 — Flexible sources** (lines 146–156)  
Any remaining gap is filled by flexible/fossil dispatchable sources.

**Step 4 — Recharge storage from excess** (lines 175–196)  
If production still exceeds demand after meeting all needs, the *reverse* dispatch order is used to charge storage. Charging draws `excess` kW from the grid at `charge_grid × η = soc_stored` (efficiency convention: storing `E` kWh requires `E/η` from the grid).

| Output | Meaning |
|--------|---------|
| `coverage` | {source: kW} dispatched to meet demand (storage discharge included; charging is not) |
| `shortfall` | Unmet demand (kW, ≥0) |
| `excess` | Production neither dispatched nor stored (= curtailment, kW, ≥0) |
| `new_storage_state` | Updated SOC (kWh) per storage source |

### Efficiency Convention

Standard across energy system models — consistent with how real pumped-hydro works:

- **Charge side**: drawing `E/η` from the grid stores `E` kWh in the battery (round-trip losses are on the charge leg).
- **Discharge side**: drawing `E` kWh from the battery delivers `E` kWh to the grid (no loss on discharge).

### Key Classes

**`SourceMeta`** — Per-source metadata: name, category (`demand`/`production`), flexibility (`inflexible`/`flexible`/`storage`), plus storage-specific fields (capacity, charge/discharge rates, roundtrip efficiency, initial SOC).

**`TimeSeries`** — Input container with invariants: hourly UTC tz-aware monotonic timestamps, float64 series, no NaN, `sources_meta` covers every production key plus `demand`. Constructed via constructor or `from_wide_dataframe()`.

**`MatchResult`** — Output container with invariants: `demand == coverage.sum() + shortfall`, no negative values. Exposes `to_dataframe()` for wide-format export.

## CLI Usage

### `energy-match match`

Match demand and production data from CSV files:

```
uv run energy-match match --demand-csv <path> --production-csv <path>... [--source-names <name>...] [--output-dir <dir>] [--plot <path>]
```

### `energy-match fetch-entsoe`

Fetch data from the ENTSO-E Transparency Platform:

```
uv run energy-match fetch-entsoe --country IT --start 2025-01-01 --end 2025-01-08 --output-dir ./data
```

## Python API

```python
from energy_match import TimeSeries, SourceMeta, match, CsvWriter, PlotWriter

# Build a TimeSeries from data
ts = TimeSeries(...)

# Run the matching engine
result = match(ts)

# Write results
csv_writer = CsvWriter()
csv_writer.write(result, "./output")

plot_writer = PlotWriter()
plot_writer.write(result, "./output/chart.png")
```

## Data Format

The project supports wide-format CSV files for demand and production data:

- **Demand CSV**: Must contain a timestamp column and a demand/load column.
- **Production CSV(s)**: Must contain a timestamp column and production columns for each energy source.

## License

This project is part of the Renewable Energy Realtime project and follows the same licensing terms.