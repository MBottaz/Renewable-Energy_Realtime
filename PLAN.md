# PLAN: Renewable Energy Match — Modular Toolkit

## 0. Setup

### 0.1 New Git Branch

```bash
git checkout -b modular-toolkit
```

All work happens on this branch. Do NOT merge to `main` until verified.

---

## 1. Target Directory Structure

```
.
├── pyproject.toml                  # [KEEP, update] Add new deps, entry points
├── README.md                       # [KEEP, update at end]
├── sources.md                      # [KEEP, update references]
├── LICENSE                         # [KEEP]
├── .env.example                    # [KEEP]
├── .gitignore                      # [KEEP, add data/ exception]
├── .python-version                 # [KEEP]
├── uv.lock                         # [UPDATE via `uv lock`]
│
├── src/
│   └── energy_match/
│       ├── __init__.py             # Package init, public API re-exports
│       ├── models.py               # Data types: TimeSeries, MatchResult, SourceMeta
│       ├── config.py               # Default column mappings, source classifications
│       ├── engine.py               # Core matching algorithm (pure function)
│       ├── dispatch.py             # Dispatch priority logic, storage charge/discharge
│       │
│       ├── readers/
│       │   ├── __init__.py
│       │   ├── base.py             # Abstract Reader protocol
│       │   ├── csv_reader.py       # Generic CSV → TimeSeries (column-mapping driven)
│       │   └── entsoe_reader.py    # ENTSO-E API → TimeSeries (wraps entsoe-py)
│       │
│       └── writers/
│           ├── __init__.py
│           ├── base.py             # Abstract Writer protocol
│           ├── csv_writer.py       # MatchResult → CSV files
│           └── plot_writer.py      # MatchResult → matplotlib charts
│
├── cli.py                          # Top-level CLI entry point (argparse or typer)
│
├── tests/
│   ├── __init__.py
│   ├── test_engine.py              # Unit tests for core matching
│   ├── test_dispatch.py            # Unit tests for dispatch logic
│   ├── test_csv_reader.py          # Round-trip reader tests
│   └── fixtures/
│       └── sample_demand.csv       # Minimal test fixture
│       └── sample_production.csv   # Minimal test fixture
│
├── data/                           # [gitignored except .gitkeep]
│   └── .gitkeep
│
└── legacy/                         # [MOVE old scripts here, keep for reference]
    ├── import_API.py
    ├── EnergyMatch.py
    └── energy_system_simulation.py
```

---

## 2. Universal Data Format

### 2.1 Internal Representation (`models.py`)

The core engine operates on **pandas** objects with a strict contract.
All timestamps are **hourly, timezone-aware UTC**.

#### 2.1.1 `SourceMeta` (per-source metadata)

```python
@dataclass
class SourceMeta:
    name: str               # Human-readable name, e.g. "Solar"
    category: str           # "demand" | "production"
    flexibility: str        # "inflexible" | "flexible" | "storage"
    unit: str = "kW"        # Always kW internally
    # Storage-specific (only when flexibility == "storage")
    capacity_kwh: float | None = None       # Max energy stored
    max_charge_rate_kw: float | None = None # Charge power limit
    max_discharge_rate_kw: float | None = None
    initial_soc_kwh: float | None = None    # Starting state of charge
    roundtrip_efficiency: float | None = None  # 0.0–1.0
```

#### 2.1.2 `TimeSeries` (universal input container)

```python
@dataclass
class TimeSeries:
    """
    All series share the same hourly DatetimeIndex (UTC, sorted, no gaps).
    """
    timestamps: pd.DatetimeIndex
    demand: pd.Series                          # float, kW, one per timestamp
    productions: dict[str, pd.Series]          # source_name → kW per timestamp
    sources_meta: dict[str, SourceMeta]        # source_name → metadata
    # sources_meta keys MUST match productions keys + "demand"
```

**Invariants enforced on construction:**
- `timestamps` is monotonically increasing, hourly frequency, tz-aware UTC.
- Every `pd.Series` has `timestamps` as its index and dtype `float64`.
- No NaN in demand or productions (use 0.0 for missing).
- `sources_meta` has an entry for `"demand"` and one for every production key.

#### 2.1.3 `MatchResult` (engine output)

```python
@dataclass
class MatchResult:
    timestamps: pd.DatetimeIndex              # Same as input
    demand: pd.Series                         # Original demand
    coverage: pd.DataFrame                    # Columns = source names, rows = kW dispatched per hour
    shortfall: pd.Series                      # Uncovered demand (>= 0)
    excess: pd.Series                         # Curtailed production (>= 0)
    storage_soc: dict[str, pd.Series] | None  # State of charge for each storage source (kWh)
    metadata: dict                            # Provenance: input hashes, timestamp, config snapshot
```

**Invariants:**
- For each hour: `demand == coverage.sum(axis=1) + shortfall`
- For each hour: `total_production == coverage.sum(axis=1) + excess`
- No negative values in coverage, shortfall, excess.

---

## 3. File-by-File Specification

### 3.1 `src/energy_match/__init__.py`

- Re-export the public API surface:
  - `TimeSeries`, `SourceMeta`, `MatchResult` from `models`
  - `match` from `engine`
  - `CsvReader`, `EntsoeReader` from readers
  - `CsvWriter`, `PlotWriter` from writers
- Set `__all__` explicitly.

### 3.2 `src/energy_match/models.py`

- Define `SourceMeta` (dataclass, see §2.1.1).
- Define `TimeSeries` (dataclass, see §2.1.2).
  - `__post_init__` must run validation: index alignment, no NaNs, tz-aware UTC, hourly freq.
  - `from_dataframe(df, sources_meta)` factory: constructs from a wide DataFrame where columns include `"demand"` plus production names.
- Define `MatchResult` (dataclass, see §2.1.3).
  - `__post_init__` runs sanity checks: coverage sums, no negatives.
  - `to_dataframe()` → wide DataFrame with demand, coverage columns, shortfall, excess.

### 3.3 `src/energy_match/config.py`

- `RENEWABLE_SOURCES: dict[str, SourceMeta]` — default classification for every ENTSO-E source name.
- `FOSSIL_SOURCES: set[str]` — source names considered fossil (excluded from matching by default).
- `DEFAULT_DISPATCH_ORDER: list[str]` — priority from first to last (mirrors `sources.md`):
  1. Inflexible renewables (Solar, Wind Onshore, Wind Offshore, Geothermal, Hydro Run-of-river, Biomass, Marine)
  2. Hydro Pumped Storage
  3. Hydro Water Reservoir
  4. Other storage
  5. Other (fossil / shortfall)
- `ENTSOE_COLUMN_MAP: dict[str, str]` — ENTSO-E PSR codes → human-readable names.
- `DEFAULT_PLOT_COLORS: dict[str, str]` — hex colors per source (port existing palette from `energy_system_simulation.py`).

### 3.4 `src/energy_match/readers/base.py`

- Define `Reader` protocol (or ABC):
  - `read() -> TimeSeries`
  - No state; stateless class with configuration at `__init__`.

### 3.5 `src/energy_match/readers/csv_reader.py`

- `class CsvReader(Reader)`:
  - `__init__(demand_path, production_paths, column_map, source_meta, **pd_kwargs)`:
    - `demand_path`: path to CSV with at least `timestamp` + `demand` columns (names configurable).
    - `production_paths`: dict `source_name → file_path`.
    - `column_map`: {canonical_name: actual_column_name_in_csv} for each file.
    - `source_meta`: `dict[str, SourceMeta]` for each source.
  - `read() -> TimeSeries`:
    1. Parse demand CSV → `pd.DataFrame`, set `timestamp` as DatetimeIndex.
    2. For each production file, parse, align index to demand timestamps (forward-fill or error on mismatch).
    3. Construct and return `TimeSeries` (validation runs in `__post_init__`).

**CSV input contract** (what users must provide):
```csv
timestamp,value
2025-01-01T00:00:00Z,32000.5
2025-01-01T01:00:00Z,31500.0
...
```
- `timestamp` column: ISO 8601, UTC.
- `value` column: float, kW.
- One file per source OR one wide file with multiple columns.

The reader supports BOTH patterns:
- **Wide**: one file, columns = `[timestamp, demand, solar, wind, ...]` → `CsvReader.from_wide(path, column_map, source_meta)`.
- **Narrow**: one file per source → `CsvReader.from_narrow(demand_path, production_paths, source_meta)`.

### 3.6 `src/energy_match/readers/entsoe_reader.py`

- `class EntsoeReader(Reader)`:
  - `__init__(api_key, country_code, start_date, end_date, psr_types)`:
    - Wraps `EntsoePandasClient`.
    - Uses existing logic from `import_API.py` but returns `TimeSeries`, not CSV.
  - `read() -> TimeSeries`:
    1. Query load → demand series.
    2. Query generation per PSR type → production series.
    3. Classify each source using `config.py` defaults.
    4. Return `TimeSeries`.
  - `read_installed_capacity() -> pd.DataFrame`: separate method, not part of the core flow but useful.
- MUST handle the ENTSO-E MultiIndex column quirk (`process_multiindex_columns` from existing code).

### 3.7 `src/energy_match/dispatch.py`

Pure functions, no I/O.

- `build_dispatch_order(sources_meta: dict[str, SourceMeta]) -> list[str]`:
  - Groups sources by flexibility: inflexible first, then storage, then flexible, then "other".
  - Within storages: pumped hydro before generic storage (per `sources.md`).
  - Falls back to `config.DEFAULT_DISPATCH_ORDER` for known source names.

- `dispatch_hour(demand_mw, productions_mw, dispatch_order, storage_state, sources_meta) -> tuple[dict, dict, float, float]`:
  - For a single hour:
    1. Apply inflexible sources up to demand (no curtailment yet).
    2. If shortfall remains, discharge storage in dispatch order.
    3. If still shortfall, use flexible sources.
    4. If excess (production > demand after all dispatch), recharge storage in reverse order, then curtail.
  - Returns: `(coverage_dict, new_storage_state, shortfall, excess)`.

- `compute_storage_limits(sources_meta) -> dict[str, tuple[float, float]]`:
  - Returns (max_charge_rate, max_discharge_rate) per storage source.

### 3.8 `src/energy_match/engine.py`

- `match(ts: TimeSeries, dispatch_order: list[str] | None = None) -> MatchResult`:
  1. If `dispatch_order` is None, call `build_dispatch_order(ts.sources_meta)`.
  2. Iterate over every timestamp (hour):
     - Call `dispatch_hour` for that hour's demand and productions.
     - Accumulate results.
  3. Construct and return `MatchResult` (validation in `__post_init__`).
  - This function is the **only** public entry point for matching. It is stateless and deterministic.
  - MUST be vectorizable in the future (loop over hours is fine for now; data is typically < 10k rows).

### 3.9 `src/energy_match/writers/base.py`

- `Writer` protocol:
  - `write(result: MatchResult, target: str | Path) -> None`

### 3.10 `src/energy_match/writers/csv_writer.py`

- `class CsvWriter(Writer)`:
  - `write(result, output_dir)`:
    - Writes `coverage.csv` (wide: timestamp + one column per source).
    - Writes `shortfall.csv` (timestamp, shortfall_mw).
    - Writes `excess.csv` (timestamp, excess_mw).
    - If storage present, writes `storage_soc.csv` (timestamp + one column per storage).
    - Writes `summary.json` with aggregate stats (total demand, renewable share, peak shortfall, etc.).

### 3.11 `src/energy_match/writers/plot_writer.py`

- `class PlotWriter(Writer)`:
  - `write(result, output_path, title="Energy Match", show_demand=True)`:
    - **Primary chart**: Stacked area chart (like existing `energy_system_simulation.py`):
      - Each production source as a colored band.
      - Shortfall as gray band at top.
      - Demand as red dashed line overlay.
    - **Optional secondary charts** (controlled by flags):
      - `show_storage=True`: second subplot with storage SOC over time.
      - `show_pie=True`: aggregate share pie chart.
    - Saves to `output_path` (PNG or PDF based on extension).
    - Colors from `config.DEFAULT_PLOT_COLORS`, fallback to matplotlib defaults for unknown sources.
  - Use matplotlib's object-oriented API (no `plt.figure()` global state).

### 3.12 `cli.py`

- Uses `argparse` (stdlib, zero new deps) OR `typer` if added to deps.
- Subcommands:
  - `match`:
    - `--demand-csv PATH`
    - `--production-csv PATH [PATH ...]` (wide) OR `--production-dir PATH` (narrow files)
    - `--source-names NAME [NAME ...]` (order must match production files)
    - `--source-meta PATH` (JSON file with SourceMeta definitions)
    - `--dispatch-order NAME [NAME ...]` (optional override)
    - `--output-dir PATH` (default `./output`)
    - `--plot PATH` (optional, saves chart)
    - `--format csv|json` (output format)
  - `fetch-entsoe`:
    - `--country CODE` (default IT)
    - `--start DATE`
    - `--end DATE`
    - `--output-dir PATH`
    - Uses ENTSOe_KEY from env.
- Both commands construct the pipeline: Reader → Engine → Writer.

### 3.13 `pyproject.toml` (updates)

- Add `[project.scripts]` entry point:
  ```toml
  [project.scripts]
  energy-match = "cli:main"
  ```
- Add dev dependencies: `pytest`.
- Keep existing deps: `pandas`, `matplotlib`, `entsoe-py`, `python-dotenv`.

---

## 4. Implementation Roadmap

Each step is self-contained and verifiable. Execute in order; each step builds on the previous.

### Step 1 — Core Engine (`engine.py`)

**Actions:**
1. Implement `match(ts: TimeSeries, dispatch_order=None) -> MatchResult`:
   - Resolve dispatch order if not provided.
   - Initialize storage state from `SourceMeta.initial_soc_mwh`.
   - Loop over each timestamp:
     - Extract `demand_mw = ts.demand.iloc[i]`
     - Extract `productions_mw = {name: series.iloc[i] for name, series in ts.productions.items()}`
     - Call `dispatch_hour(...)`
     - Accumulate coverage, storage SOC, shortfall, excess.
   - Build `MatchResult`.
2. Handle edge cases:
   - Zero demand hour (all production is excess → curtail or store).
   - Zero production hour (all demand is shortfall).
   - Single source scenario.

**Verification:**
- Unit test with simple 3-hour scenario.
- Property test: `coverage.sum(axis=1) + shortfall == demand` for every hour.
- Property test: all values >= 0.

---

### Step 2 — Writer Base + CSV Writer

**Actions:**
1. Implement `Writer` ABC in `writers/base.py`.
2. Implement `CsvWriter` as specified in §3.10:
   - Output files: `coverage.csv`, `shortfall.csv`, `excess.csv`, `storage_soc.csv` (conditional), `summary.json`.
   - `summary.json` schema:
     ```json
     {
       "total_demand_mwh": float,
       "total_renewable_mwh": float,
       "renewable_share": float,       // 0.0–1.0
       "total_shortfall_mwh": float,
       "total_excess_mwh": float,
       "peak_demand_mw": float,
       "peak_shortfall_mw": float,
       "num_hours": int,
       "sources": ["solar", "wind", ...]
     }
     ```

**Verification:** Run engine on test data, write CSV, read back and check values.

---

### Step 3 — Plot Writer

**Actions:**
1. Implement `PlotWriter` as specified in §3.11.
2. Port the stacked area chart from `energy_system_simulation.py` but use the OO API (`fig, ax = plt.subplots()`).
3. Storage subplot: SOC line chart below the main area chart.
4. Legend, title, axis labels, grid.
5. Color mapping from config.

**Verification:** Generate a plot from test data, verify it renders without errors.

---

### Step 4 — CLI

**Actions:**
1. Implement `cli.py` with argparse:
   - `match` subcommand: CSV inputs → match → output.
   - `fetch-entsoe` subcommand: API → save CSV (for later `match`).
2. Wire up: parse args → build readers → call `match()` → call writers.
3. Add `[project.scripts]` to `pyproject.toml`.

**Verification:**
```bash
uv run energy-match match --demand-csv data/demand.csv --production-csv data/solar.csv data/wind.csv --source-names Solar Wind --output-dir output --plot output/chart.png
```

---

### Step 5 — Tests

**Actions:**
1. Create `tests/fixtures/sample_wide.csv` — 24 hours, demand + 2 production sources.
2. `test_engine.py`:
   - Test exact match (production == demand).
   - Test shortfall (production < demand).
   - Test excess (production > demand, no storage → curtailment).
   - Test excess with storage (production > demand, storage charges).
   - Test discharge (production < demand, storage discharges to cover).
   - Test dispatch order (inflexible used before storage).
   - Test invariants across all scenarios.
3. `test_dispatch.py`:
   - Single hour dispatch with various input combinations.
   - Storage charge/discharge rate limits.
   - Storage capacity limits.
   - Round-trip efficiency accounting.
4. `test_csv_reader.py`:
   - Wide format round-trip.
   - Narrow format round-trip.
   - Missing timestamp handling.
5. Run with `uv run pytest tests/ -v`.

**Verification:** All tests pass.

---

### Step 6 — Cleanup & Documentation

**Actions:**
1. Update `README.md`:
   - New project description (modular toolkit).
   - New usage examples (CLI + Python API).
   - Data format specification.
   - Remove old usage instructions.
2. Update `sources.md` if assumptions changed.
3. Verify `legacy/` scripts still work if run from project root (paths may need adjustment).
4. Run `uv lock` to update lockfile.
5. Final `git status` check — no untracked generated files, no data files.

**Verification:** `uv run energy-match match --help` prints usage. `uv run pytest` passes.
---

## 5. Design Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| **pandas as internal format** | Already a dependency; hourly energy data is small (<100k rows); pandas vectorization is fast enough. |
| **UTC timestamps, hourly** | Eliminates timezone bugs; hourly is the native resolution of ENTSO-E and most energy datasets. |
| **Storage modeled in dispatch, not the engine** | Keeps `engine.py` as a thin loop; all complexity lives in `dispatch.py` and is unit-testable per hour. |
| **Readers return `TimeSeries`, not raw DataFrames** | Enforces the contract at the boundary; invalid data is caught early. |
| **`legacy/` directory, not deletion** | Preserves reference implementations; users can still run old scripts if needed. |
| **argparse over typer/click** | Zero new dependencies; the CLI surface is small (2 subcommands). |
| **Efficiency applied on charge** | Standard in energy system models: charging draws `energy / eff`, discharging delivers `energy`. Documented in `dispatch.py` docstring. |

---

## 6. Acceptance Criteria (for the final deliverable)

1. `uv run energy-match match --demand-csv <d> --production-csv <p1> <p2> --output-dir <out>` produces valid CSVs and a summary JSON.
2. `uv run energy-match fetch-entsoe --start 2025-01-01 --end 2025-01-08` produces CSV files readable by `match`.
3. `uv run pytest tests/ -v` — all tests pass.
4. Coverage/shortfall invariants hold on real ENTSO-E data (spot-check).
5. `legacy/` scripts still runnable.
6. No hard-coded paths outside `data/` and `legacy/`.
7. `README.md` accurately describes the new workflow.
