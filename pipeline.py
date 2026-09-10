import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import json
    import sys
    from pathlib import Path

    import marimo as mo
    import matplotlib.pyplot as plt
    import pandas as pd

    # Make `core/` importable no matter where marimo was launched from.
    try:
        _ROOT = Path(__file__).resolve().parent
    except NameError:  # pragma: no cover - interactive fallback
        _ROOT = Path.cwd()
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))

    from core.capacity import manual_installed_capacity
    from core.config import COUNTRIES, DATA_DIR, FRONTEND_DATA_DIR
    from core.entsoe import fetch_production
    from core.plot import get_source_color

    return (
        COUNTRIES,
        DATA_DIR,
        FRONTEND_DATA_DIR,
        fetch_production,
        get_source_color,
        json,
        manual_installed_capacity,
        mo,
        pd,
        plt,
    )


@app.cell
def _(mo):
    mo.md("""
    # ⚡ Renewable Energy Realtime — step-by-step pipeline

    This notebook walks through the chain one step at a time:

    | Step | What it does | Skippable |
    |------|--------------|-----------|
    | **1. Fetch** | 15-min demand + generation from ENTSO-E (or reuse a file already on disk) | ✅ yes |
    | **2. Clean & prepare** | parse timestamps, remove duplicates, fill gaps, drop empty sources | – |
    | **3. Upscale** | you type the **target MW** for renewables → generation is scaled to match | interactive |

    All values from ENTSO-E are **MW** per 15-minute interval
    (energy of one interval = `MW × 0.25 h`).
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 1 · Fetch data from ENTSO-E

    Two ways to start, controlled by the checkbox below:

    - **checked** (default) → reuse a file already on disk (local `data/entsoe_<CC>_*.csv`,
      otherwise the bundled `frontend/data/production_<CC>.csv`): no API call at all;
    - **unchecked** → query the ENTSO-E API for the selected window and save it to
      `data/entsoe_<CC>_<start>_<end>.csv` (needs `ENTSOE_KEY` in `.env`).

    In local mode the dates are ignored — the whole local file is used.
    """)
    return


@app.cell
def _(COUNTRIES, DATA_DIR, json, mo):
    _options = {c["code"]: c["name"] for c in COUNTRIES}
    _catalog = DATA_DIR / "countries.json"
    if _catalog.exists():
        _options |= {c["code"]: c["name"] for c in json.loads(_catalog.read_text())}

    country_ui = mo.ui.dropdown(
        options=_options,
        value="IT",
        label="Country",
        searchable=True,
    )
    country_ui
    return (country_ui,)


@app.cell
def _(mo):
    country_code_ui = mo.ui.text(
        value="",
        label="…or any ENTSO-E country code (overrides the dropdown)",
    )
    country_code_ui
    return (country_code_ui,)


@app.cell
def _(mo, pd):
    _today = pd.Timestamp.now(tz="UTC").normalize()
    date_start_ui = mo.ui.date(
        value=str((_today - pd.Timedelta(days=7)).date()),
        label="Start date (API fetch only)",
    )
    date_end_ui = mo.ui.date(value=str(_today.date()), label="End date (API fetch only)")
    use_local_ui = mo.ui.checkbox(
        value=True,
        label="Step 1: reuse local data if available (skip the API)",
    )
    mo.hstack([use_local_ui, date_start_ui, date_end_ui], justify="start", gap=1.5)
    return date_end_ui, date_start_ui, use_local_ui


@app.cell
def _(
    DATA_DIR,
    FRONTEND_DATA_DIR,
    country_code_ui,
    country_ui,
    date_end_ui,
    date_start_ui,
    fetch_production,
    mo,
    pd,
    use_local_ui,
):
    # `country_ui` is built from a {code: name} dict, so the code is `selected_key`.
    code = (
        country_code_ui.value or country_ui.selected_key or country_ui.value or ""
    ).strip().upper()
    start = pd.Timestamp(date_start_ui.value, tz="UTC")
    end = pd.Timestamp(date_end_ui.value, tz="UTC") + pd.Timedelta(days=1)  # inclusive

    # ── Local candidates, most specific first ──────────────────────────────
    _exact = DATA_DIR / f"entsoe_{code}_{start:%Y%m%d}_{end:%Y%m%d}.csv"
    local_files = ([_exact] if _exact.exists() else []) + [
        p for p in sorted(DATA_DIR.glob(f"entsoe_{code}_*.csv")) if p != _exact
    ]
    _bundled = FRONTEND_DATA_DIR / f"production_{code}.csv"
    if _bundled.exists():
        local_files.append(_bundled)

    raw_df = None
    if use_local_ui.value and local_files:
        _path = local_files[0]
        raw_df = pd.read_csv(_path)
        _ts = pd.to_datetime(raw_df["timestamp"], utc=True)
        load_note = mo.md(
            f"✅ **Step 1 skipped** — loaded `{_path.name}` "
            f"({len(raw_df):,} rows × {len(raw_df.columns)} columns, "
            f"{_ts.min():%Y-%m-%d %H:%M} → {_ts.max():%Y-%m-%d %H:%M} UTC)."
        )
    else:
        try:
            raw_df = fetch_production(code, start, end, verbose=False)
            _out = DATA_DIR / f"entsoe_{code}_{start:%Y%m%d}_{end:%Y%m%d}.csv"
            _out.parent.mkdir(parents=True, exist_ok=True)
            raw_df.to_csv(_out, index=False)
            load_note = mo.md(
                f"✅ **Fetched from ENTSO-E** — {len(raw_df):,} rows → `{_out}`"
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to the user as markdown
            load_note = mo.md(
                f"❌ **Could not load data for `{code}`**: `{exc}`\n\n"
                "Either tick the checkbox to reuse local data, or put your key in "
                "`.env` as `ENTSOE_KEY=…` and untick the checkbox."
            )
    return code, load_note, raw_df


@app.cell
def _(load_note):
    load_note
    return


@app.cell
def _(mo):
    mo.md("""
    ## 2 · Clean & prepare

    Four small, visible transformations:

    1. parse timestamps (UTC), remove duplicates, sort, clip negatives;
    2. rebuild a complete 15-min grid (missing demand is interpolated, missing
       generation counts as 0);
    3. drop sources that are empty for the whole file;
    4. preview: hourly-average stacked chart + per-source statistics.
    """)
    return


@app.cell
def _(mo, pd, raw_df):
    mo.stop(raw_df is None, mo.md("_No data loaded — see Step 1 above._"))

    df = raw_df.copy()

    # 2a — normalise: types, duplicates, ordering, negatives
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    value_cols = [c for c in df.columns if c != "timestamp"]
    df[value_cols] = df[value_cols].apply(pd.to_numeric, errors="coerce")

    n_raw = len(df)
    n_dupes = int(df["timestamp"].duplicated().sum())
    n_missing = int(df[value_cols].isna().sum().sum())
    n_negative = int((df[value_cols] < 0).to_numpy().sum())

    df = df.drop_duplicates("timestamp").sort_values("timestamp")
    df[value_cols] = df[value_cols].clip(lower=0)
    df = df.reset_index(drop=True)

    mo.md(
        "**2a · Normalise**\n\n"
        f"- {n_raw:,} raw rows\n"
        f"- {n_dupes:,} duplicate timestamp(s) removed\n"
        f"- {n_missing:,} missing value(s) (filled in 2b)\n"
        f"- {n_negative:,} negative value(s) clipped to 0\n"
        f"- {len(df):,} rows left, "
        f"{df['timestamp'].min():%Y-%m-%d %H:%M} → {df['timestamp'].max():%Y-%m-%d %H:%M} UTC"
    )
    return (df,)


@app.cell
def _(df, mo, pd):
    # 2b — complete grid: detect the nominal step, then reindex onto it
    _deltas = df["timestamp"].diff().dropna()
    step = _deltas.mode().iloc[0] if len(_deltas) else pd.Timedelta(minutes=15)

    _full = pd.date_range(df["timestamp"].iloc[0], df["timestamp"].iloc[-1], freq=step)
    df_grid = df.set_index("timestamp").reindex(_full)

    if df_grid["demand_kw"].isna().any():
        df_grid["demand_kw"] = df_grid["demand_kw"].interpolate(limit_direction="both")
    _gen = [c for c in df_grid.columns if c != "demand_kw"]
    df_grid[_gen] = df_grid[_gen].fillna(0.0)
    df_grid = df_grid.reset_index(names="timestamp")

    mo.md(
        f"**2b · Regularise** — nominal step `{step}`, "
        f"{len(_full) - len(df):,} interval(s) were missing and are now filled "
        f"({len(df_grid):,} rows)."
    )
    return (df_grid,)


@app.cell
def _(df_grid, mo):
    # 2c — drop sources with no production at all in this file
    _gen = [c for c in df_grid.columns if c not in ("timestamp", "demand_kw")]
    _kept = [c for c in _gen if df_grid[c].abs().sum() > 0]
    dropped = [c for c in _gen if c not in _kept]
    df_clean = df_grid[["timestamp", "demand_kw", *_kept]].copy()

    mo.md(
        f"**2c · Sources** — keeping {len(_kept)}, "
        + (f"dropped empty: {', '.join(dropped)}." if dropped else "nothing to drop.")
    )
    return (df_clean,)


@app.cell
def _(df_clean, pd):
    # 2d — per-source statistics over the whole file
    _gen = [c for c in df_clean.columns if c not in ("timestamp", "demand_kw")]
    stats = pd.DataFrame(
        {
            "mean_MW": [df_clean[c].mean() for c in _gen],
            "peak_MW": [df_clean[c].max() for c in _gen],
            "energy_MWh": [df_clean[c].sum() * 0.25 for c in _gen],
        },
        index=pd.Index(_gen, name="source"),
    )
    stats.round(1)
    return


@app.cell
def _(df_clean, mo):
    _ts = df_clean["timestamp"]
    plot_range_ui = mo.ui.date_range(
        value=(str(_ts.min().date()), str(_ts.max().date())),
        label="Preview window",
    )
    plot_range_ui
    return (plot_range_ui,)


@app.cell
def _(df_clean, get_source_color, pd, plot_range_ui, plt):
    _lo = pd.Timestamp(plot_range_ui.value[0], tz="UTC")
    _hi = pd.Timestamp(plot_range_ui.value[1], tz="UTC") + pd.Timedelta(days=1)
    _hourly = df_clean.set_index("timestamp").loc[_lo:_hi].resample("1h").mean()
    _gen = [c for c in _hourly.columns if c != "demand_kw"]

    fig, ax = plt.subplots(figsize=(11, 4))
    ax.stackplot(
        _hourly.index,
        [_hourly[c] for c in _gen],
        labels=_gen,
        colors=[get_source_color(c) for c in _gen],
        alpha=0.95,
    )
    ax.plot(_hourly.index, _hourly["demand_kw"], color="black", lw=1.2, label="Demand")
    ax.set_ylabel("MW (hourly average)")
    ax.set_title("Observed generation and demand")
    ax.grid(alpha=0.25, axis="y")
    ax.legend(loc="upper left", ncols=4, fontsize=8, framealpha=0.9)
    ax.margins(x=0)
    fig.autofmt_xdate()
    fig
    return


@app.cell
def _(mo):
    mo.md("""
    ## 3 · Upscaling factors

    Here you decide the **future installed capacity** you want to study.

    Type the target MW for each renewable technology; the notebook derives

    ```
    factor = target MW ÷ current installed capacity (MW)
    ```

    and multiplies the historical generation of that technology by it
    (demand and non-renewable sources stay untouched). Defaults equal the
    current capacity, so the initial factors are all `1.0`.
    """)
    return


@app.cell
def _(DATA_DIR, code, json, manual_installed_capacity, mo):
    _cap_path = DATA_DIR / f"capacity_{code}.json"
    if _cap_path.exists():
        capacity = json.loads(_cap_path.read_text())["sources"]
        capacity_note = f"installed capacity read from `{_cap_path.name}`"
    else:
        try:
            capacity = manual_installed_capacity(code, 2025)
            capacity_note = (
                "installed capacity from `core.capacity` (hand-maintained 2025 snapshot)"
            )
        except ValueError:
            capacity = {}
            capacity_note = f"no installed-capacity baseline for `{code}`"

    mo.md(f"**3a · Baseline** — {capacity_note}.")
    return capacity, capacity_note


@app.cell
def _(capacity, capacity_note, df_clean, mo):
    # Which technologies may be upscaled. Edit this list to change the scope.
    RENEWABLE_SOURCES = [
        "Solar",
        "Wind Onshore",
        "Wind Offshore",
        "Hydro Run-of-river and poundage",
        "Hydro Water Reservoir",
        "Hydro Pumped Storage",
        "Geothermal",
        "Biomass",
        "Marine",
        "Other renewable",
    ]
    scalable = [c for c in df_clean.columns if c in RENEWABLE_SOURCES]

    target_inputs = mo.ui.dictionary(
        {
            src: mo.ui.number(
                value=float(capacity.get(src, 0.0)),
                start=0.0,
                step=50.0,
                label=f"{src}  ·  now {capacity.get(src, 0.0):,.0f} MW",
            )
            for src in scalable
        },
        label="Target installed capacity (MW)",
    )

    mo.vstack(
        [
            mo.md(
                f"**3b · Target capacity** — type the MW you want for the "
                f"{len(scalable)} renewable source(s) found in the data "
                f"({capacity_note})."
            ),
            target_inputs,
        ]
    )
    return scalable, target_inputs


@app.cell
def _(capacity, mo, pd, scalable, target_inputs):
    mo.stop(
        not scalable,
        mo.md("_No renewable source in this dataset — nothing to upscale._"),
    )

    _rows = []
    _no_baseline = []
    for _src in scalable:
        _current = float(capacity.get(_src, 0.0))
        _target = float(target_inputs.value.get(_src) or 0.0)
        if _current > 0:
            _factor = _target / _current
        else:
            _factor = 1.0  # no baseline → cannot scale
            if _target > 0:
                _no_baseline.append(_src)
        _rows.append(
            {
                "source": _src,
                "current_MW": _current,
                "target_MW": _target,
                "factor": _factor,
            }
        )

    factors_df = pd.DataFrame(_rows)
    factors = {r["source"]: r["factor"] for r in _rows}
    _total_before = factors_df["current_MW"].sum()
    _total_after = factors_df["target_MW"].sum()

    mo.vstack(
        [
            mo.md(
                f"**3c · Derived factors** — renewable capacity "
                f"{_total_before:,.0f} MW → **{_total_after:,.0f} MW** "
                f"({_total_after / _total_before - 1:+.1%})."
                if _total_before > 0
                else "**3c · Derived factors**"
            ),
            mo.ui.table(factors_df.round(3), selection=None, pagination=False),
            *(
                [
                    mo.md(
                        f"⚠️ No baseline capacity for **{', '.join(_no_baseline)}** — "
                        "factor kept at 1.0 (there is nothing to scale)."
                    )
                ]
                if _no_baseline
                else []
            ),
        ]
    )
    return factors, factors_df


@app.cell
def _(df_clean, factors):
    # Apply the factors to the historical generation (demand is left as is).
    df_scaled = df_clean.copy()
    for _src, _factor in factors.items():
        if _src in df_scaled.columns:
            df_scaled[_src] = df_scaled[_src] * _factor
    return (df_scaled,)


@app.cell
def _(df_clean, df_scaled, factors_df, mo):
    _gens = list(factors_df["source"])
    _before = df_clean[_gens].sum().sum() * 0.25  # MW·15min → MWh
    _after = df_scaled[_gens].sum().sum() * 0.25
    _delta = f"{_after / _before - 1:+.1%}" if _before > 0 else "n/a"

    mo.md(
        f"**3d · Effect** — renewable energy over the whole file: "
        f"**{_before:,.0f} MWh → {_after:,.0f} MWh** ({_delta})."
    )
    return


@app.cell
def _(df_clean, df_scaled, factors_df, pd, plot_range_ui, plt):
    _gens = list(factors_df["source"])
    _lo = pd.Timestamp(plot_range_ui.value[0], tz="UTC")
    _hi = pd.Timestamp(plot_range_ui.value[1], tz="UTC") + pd.Timedelta(days=1)
    _before = df_clean.set_index("timestamp").loc[_lo:_hi].resample("1h").mean()
    _after = df_scaled.set_index("timestamp").loc[_lo:_hi].resample("1h").mean()

    fig2, ax2 = plt.subplots(figsize=(11, 4))
    ax2.plot(
        _before.index,
        _before[_gens].sum(axis=1),
        color="#1f77b4",
        ls="--",
        lw=1.4,
        label="Renewables before",
    )
    ax2.plot(
        _after.index,
        _after[_gens].sum(axis=1),
        color="#2ca02c",
        lw=1.8,
        label="Renewables after upscaling",
    )
    ax2.plot(
        _before.index,
        _before["demand_kw"],
        color="black",
        lw=1.0,
        label="Demand",
    )
    ax2.set_ylabel("MW (hourly average)")
    ax2.set_title("Effect of the upscaling on renewable generation")
    ax2.grid(alpha=0.25, axis="y")
    ax2.legend(loc="upper left", ncols=3, fontsize=9, framealpha=0.9)
    ax2.margins(x=0)
    fig2.autofmt_xdate()
    fig2
    return


@app.cell
def _(mo):
    mo.md("""
    ---

    ### Next steps (not implemented yet)

    The prepared, upscaled data (`df_scaled`) is ready to be fed into the
    existing dispatch engine:

    1. **Dispatch simulation** — `core.engine.match(df_scaled)` computes hour-by-hour
       coverage, shortfall, excess and storage state of charge.
    2. **Results** — `core.engine.write_match_results(results, "output/")` + the
       matplotlib chart from `core.plot`.
    3. **Publish** — `core.export.build()` to refresh the static frontend.

    Unit convention used throughout: ENTSO-E gives **MW per 15 min**, so
    hourly energy is the mean of the ≤4 samples × 1 h
    (or `sum × 0.25 h`, same thing).
    """)
    return


if __name__ == "__main__":
    app.run()
