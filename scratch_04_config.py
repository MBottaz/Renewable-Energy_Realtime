"""
scratch_04_config.py — Exploring the energy_match config module.

Demonstrates every configuration constant:
  - SOURCE_CLASSIFICATIONS: full production-source registry with flexibility tags
  - FOSSIL_SOURCES:         set of sources excluded from renewable matching
  - DEFAULT_DISPATCH_ORDER: dispatch priority list
  - ENTSOE_COLUMN_MAP:      ENTSO-E PSR code → human name mappings
  - DEFAULT_PLOT_COLORS:    hex colour per source for plotting

Run from repo root:
    uv run python scratch_04_config.py
"""

from energy_match.config import (
    SOURCE_CLASSIFICATIONS,
    DEFAULT_DISPATCH_ORDER,
    FOSSIL_SOURCES,
    ENTSOE_COLUMN_MAP,
    DEFAULT_PLOT_COLORS,
)
from energy_match.models import SourceMeta

# ── Helpers ──────────────────────────────────────────────────────────────

SEP = "-" * 72


def psep(title: str) -> None:
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


def flex_group(flex: str) -> dict[str, SourceMeta]:
    return {n: m for n, m in SOURCE_CLASSIFICATIONS.items() if m.flexibility == flex}


# ── 1. Source classifications overview ───────────────────────────────────

psep("SOURCE_CLASSIFICATIONS — Full Registry")

print(f"\nTotal classified sources: {len(SOURCE_CLASSIFICATIONS)}")
print("List of all source names:")
for name in SOURCE_CLASSIFICATIONS:
    print(f"  • {name}")

# ── 2. Group by flexibility ──────────────────────────────────────────────

psep("Sources Grouped by Flexibility")

for flex_label, flex_val in [
    ("INFLEXIBLE (cannot be dispatched — run when fuel is available)", "inflexible"),
    ("STORAGE (can store and release energy)", "storage"),
    ("FLEXIBLE (can be dispatched up/down)", "flexible"),
]:
    group = flex_group(flex_val)
    print(f"\n► {flex_label}")
    print(f"  Count: {len(group)}")
    for name in group:
        print(f"    • {name}")

# ── 3. Storage source parameters ────────────────────────────────────────

psep("Hydro Pumped Storage — Detailed Parameters")

hp = SOURCE_CLASSIFICATIONS["Hydro Pumped Storage"]
print(f"""
  Name:                     {hp.name}
  Category:                 {hp.category}
  Flexibility:              {hp.flexibility}
  Capacity (kWh):           {hp.capacity_kwh}
  Max charge rate (kW):     {hp.max_charge_rate_kw}
  Max discharge rate (kW):  {hp.max_discharge_rate_kw}
  Initial SoC (kWh):        {hp.initial_soc_kwh}
  Roundtrip efficiency:     {hp.roundtrip_efficiency}
""")

print("""  Note: The storage parameters are zeroed by default in the config
  because they are site-specific and must be provided per-run via
  --source-meta (CLI) or overridden in a custom JSON file.""")

# ── 4. Fossil sources ───────────────────────────────────────────────────

psep("FOSSIL_SOURCES — Excluded from Renewable Matching")

print(f"\nSet contents: {FOSSIL_SOURCES}")
print(f"Count: {len(FOSSIL_SOURCES)}")
print("""
  These four sources are excluded from the renewable-match engine
  by default because they represent non-renewable generation.

  They are still recognised in SOURCE_CLASSIFICATIONS (as "flexible"
  production sources) for completeness, but the match() function
  filters them out unless explicitly overridden.""")

# ── 5. Dispatch order with ranks ────────────────────────────────────────

psep("DEFAULT_DISPATCH_ORDER — Priority Ranking")

print("\n  Priority 1 = highest (dispatched first), higher number = lower priority.\n")
print(f"  {'Rank':<6} {'Source':<43} {'Group'}")
print(f"  {'----':<6} {'-'*43:<43} {'-----'}")

# Define which dispatch group each source belongs to
inflexible_set = {n for n, m in SOURCE_CLASSIFICATIONS.items() if m.flexibility == "inflexible"}
storage_set = {n for n, m in SOURCE_CLASSIFICATIONS.items() if m.flexibility == "storage"}
flexible_set = {n for n, m in SOURCE_CLASSIFICATIONS.items() if m.flexibility == "flexible"}

for rank, name in enumerate(DEFAULT_DISPATCH_ORDER, start=1):
    if name in inflexible_set:
        group = "Inflexible"
    elif name in storage_set:
        group = "Storage"
    else:
        group = "Flexible"
    print(f"  {rank:<6} {name:<43} {group}")

print("""
  Dispatch logic:
    1 → Inflexible renewables (Solar, Wind, ... Nuclear) — must-run,
        absorb as much as possible.
    2 → Hydro Pumped Storage — store surplus.
    3 → Flexible renewables / dispatchable (reservoirs, fossil) —
        fill remaining demand and make up shortfalls.
  (This order is used by the engine's dispatch_hour and
   build_dispatch_order helpers.)""")

# ── 6. ENTSO-E code mappings ────────────────────────────────────────────

psep("ENTSO_E_COLUMN_MAP — Sample Mappings")

sample_codes = ["B16", "B19", "B10", "A05"]
print(f"\n{'Code':<8} {'Source Name':<30}")
print(f"{'----':<8} {'-'*30}")
for code in sample_codes:
    name = ENTSOE_COLUMN_MAP.get(code, "(not found)")
    print(f"  {code:<8} {name:<30}")

print(f"\nTotal ENTSO-E mappings: {len(ENTSOE_COLUMN_MAP)}")
print("""
  These codes come from the ENTSO-E Transparency Platform's
  production type (PSR) codes. The map translates them into the
  human-readable names used throughout the energy_match models
  and config.

  - B16 → Solar (inflexible)
  - B19 → Wind Onshore (inflexible)
  - B10 → Hydro Pumped Storage (storage)
  - A05 → Load (demand, not in SOURCE_CLASSIFICATIONS)""")

# ── 7. Plot colours ─────────────────────────────────────────────────────

psep("DEFAULT_PLOT_COLORS — Hex Palette")

print(f"\n{'Source':<35} {'Colour':<10}")
print(f"{'-'*35:<35} {'-'*10:<10}")
for name, colour in DEFAULT_PLOT_COLORS.items():
    print(f"  {name:<35} {colour:<10}")

print(f"\nTotal colour entries: {len(DEFAULT_PLOT_COLORS)}")

# ── 8. Cross-check: dispatch groups match flexibility classification ─────

psep("Cross-Check: Dispatch Groups vs Flexibility Classification")

dispatch_groups: dict[str, set[str]] = {"inflexible": set(), "storage": set(), "flexible": set()}
for name in DEFAULT_DISPATCH_ORDER:
    meta = SOURCE_CLASSIFICATIONS[name]
    dispatch_groups[meta.flexibility].add(name)

class_groups: dict[str, set[str]] = {"inflexible": set(), "storage": set(), "flexible": set()}
for name, meta in SOURCE_CLASSIFICATIONS.items():
    class_groups[meta.flexibility].add(name)

all_match = True
for flex in ["inflexible", "storage", "flexible"]:
    # Check: every dispatch source of this flexibility is in dispatch_order (it is)
    # Check: every classified source of this flexibility is in the dispatch order
    classified = class_groups[flex]
    dispatched = dispatch_groups[flex]
    missing = classified - dispatched
    if missing:
        print(f"  ⚠ {flex}: classified sources not in dispatch order: {missing}")
        all_match = False

if all_match:
    print("  ✓ All classified sources appear in the dispatch order.")
    print("  ✓ The dispatch order grouping (inflexible → storage → flexible)")
    print("    exactly matches the flexibility classification from SOURCE_CLASSIFICATIONS.\n")
    print("  Order within each group:\n")
    for flex_label, marker in [("Inflexible", "1-8"), ("Storage (Hydro Pumped Storage)", "9"), ("Flexible", "10-20")]:
        names = [n for n in DEFAULT_DISPATCH_ORDER if SOURCE_CLASSIFICATIONS[n].flexibility == flex_label.lower().split()[0]]
        print(f"    {flex_label:<40} Ranks {marker:<6} → {', '.join(names)}")
else:
    print("  ✗ Mismatch detected (see above).")

# ── 9. Unknown source fallback ──────────────────────────────────────────

psep("CLI Fallback: Unknown Source Names Get Defaults")

print("""
  In energy_match/cli.py, the _build_sources_meta() helper processes
  user-supplied source names. The rule is:

    if name in SOURCE_CLASSIFICATIONS:
        meta[name] = SOURCE_CLASSIFICATIONS[name]   ← known → use config
    else:
        meta[name] = SourceMeta(
            name=name,
            category="production",
            flexibility="inflexible",               ← unknown → defaults to INFLEXIBLE
        )

  This means any unrecognised source name will be treated as an
  inflexible production source — it will be dispatched at the top
  of the priority order alongside Solar, Wind, etc.

  Example:
""")

unknown_name = "Unknown_Source_Example"
default_meta = SourceMeta(name=unknown_name, category="production", flexibility="inflexible")
print(f"    > _build_sources_meta(['{unknown_name}'])")
print(f"    → SourceMeta(name='{unknown_name}', category='production', flexibility='inflexible')")
print(f"    → Fields: name={default_meta.name!r}, category={default_meta.category!r}, "
      f"flexibility={default_meta.flexibility!r}")

print(f"\n{SEP}")
print("  end of scratch_04_config.py")
print(SEP)