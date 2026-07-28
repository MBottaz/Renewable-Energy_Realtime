"""
Default configuration for the Renewable Energy Match toolkit.

All source classifications, dispatch ordering, column mappings, and plot
colors are defined here as module-level constants.
"""

from energy_match.models import SourceMeta

# ---------------------------------------------------------------------------
# Fossil source names (excluded from renewable matching by default)
# ---------------------------------------------------------------------------

FOSSIL_SOURCES: set[str] = {
    "Fossil Brown coal/Lignite",
    "Fossil Coal-derived gas",
    "Fossil Gas",
    "Fossil Hard coal",
    "Fossil Oil",
    "Fossil Oil shale",
    "Fossil Peat",
}

# ---------------------------------------------------------------------------
# Source classifications — every production source mapped to a SourceMeta
# ---------------------------------------------------------------------------

SOURCE_CLASSIFICATIONS: dict[str, SourceMeta] = {
    # --- Inflexible renewables ---
    "Solar": SourceMeta(
        name="Solar", category="production", flexibility="inflexible"
    ),
    "Wind Onshore": SourceMeta(
        name="Wind Onshore", category="production", flexibility="inflexible"
    ),
    "Wind Offshore": SourceMeta(
        name="Wind Offshore", category="production", flexibility="inflexible"
    ),
    "Geothermal": SourceMeta(
        name="Geothermal", category="production", flexibility="inflexible"
    ),
    "Hydro Run-of-river and poundage": SourceMeta(
        name="Hydro Run-of-river and poundage",
        category="production",
        flexibility="inflexible",
    ),
    "Biomass": SourceMeta(
        name="Biomass", category="production", flexibility="inflexible"
    ),
    "Marine": SourceMeta(
        name="Marine", category="production", flexibility="inflexible"
    ),
    "Nuclear": SourceMeta(
        name="Nuclear", category="production", flexibility="inflexible"
    ),
    # --- Storage ---
    "Hydro Pumped Storage": SourceMeta(
        name="Hydro Pumped Storage",
        category="production",
        flexibility="storage",
        capacity_kwh=0.0,
        max_charge_rate_kw=0.0,
        max_discharge_rate_kw=0.0,
        initial_soc_kwh=0.0,
        roundtrip_efficiency=0.85,
    ),
    # --- Flexible renewables ---
    "Hydro Water Reservoir": SourceMeta(
        name="Hydro Water Reservoir",
        category="production",
        flexibility="flexible",
    ),
    "Other renewable": SourceMeta(
        name="Other renewable", category="production", flexibility="flexible"
    ),
    # --- Fossil / dispatchable ---
    "Fossil Brown coal/Lignite": SourceMeta(
        name="Fossil Brown coal/Lignite",
        category="production",
        flexibility="flexible",
    ),
    "Fossil Coal-derived gas": SourceMeta(
        name="Fossil Coal-derived gas",
        category="production",
        flexibility="flexible",
    ),
    "Fossil Gas": SourceMeta(
        name="Fossil Gas", category="production", flexibility="flexible"
    ),
    "Fossil Hard coal": SourceMeta(
        name="Fossil Hard coal", category="production", flexibility="flexible"
    ),
    "Fossil Oil": SourceMeta(
        name="Fossil Oil", category="production", flexibility="flexible"
    ),
    "Fossil Oil shale": SourceMeta(
        name="Fossil Oil shale", category="production", flexibility="flexible"
    ),
    "Fossil Peat": SourceMeta(
        name="Fossil Peat", category="production", flexibility="flexible"
    ),
    "Waste": SourceMeta(
        name="Waste", category="production", flexibility="flexible"
    ),
    "Other": SourceMeta(
        name="Other", category="production", flexibility="flexible"
    ),
}

# ---------------------------------------------------------------------------
# Default dispatch order (first = highest priority)
#
# Matches sources.md:
#   1. Inflexible renewables (Solar, Wind, Geothermal, River-type Hydro)
#   2. Pumped Hydro
#   3. Lakes (Hydro Water Reservoir)
#   4. Other storage
#   5. Other sources (fossil / shortfall)
# ---------------------------------------------------------------------------

DEFAULT_DISPATCH_ORDER: list[str] = [
    # Inflexible renewables
    "Solar",
    "Wind Onshore",
    "Wind Offshore",
    "Geothermal",
    "Hydro Run-of-river and poundage",
    "Biomass",
    "Marine",
    "Nuclear",
    # Storage (pumped hydro first)
    "Hydro Pumped Storage",
    # Flexible
    "Hydro Water Reservoir",
    "Other renewable",
    # Fossil / dispatchable
    "Fossil Brown coal/Lignite",
    "Fossil Coal-derived gas",
    "Fossil Gas",
    "Fossil Hard coal",
    "Fossil Oil",
    "Fossil Oil shale",
    "Fossil Peat",
    "Waste",
    "Other",
]

# ---------------------------------------------------------------------------
# ENTSO-E PSR code → human-readable name mapping
# Ported from legacy/import_API.py:63-89
# ---------------------------------------------------------------------------

ENTSOE_COLUMN_MAP: dict[str, str] = {
    "A05": "Load",
    "B01": "Biomass",
    "B02": "Fossil Brown coal/Lignite",
    "B03": "Fossil Coal-derived gas",
    "B04": "Fossil Gas",
    "B05": "Fossil Hard coal",
    "B06": "Fossil Oil",
    "B07": "Fossil Oil shale",
    "B08": "Fossil Peat",
    "B09": "Geothermal",
    "B10": "Hydro Pumped Storage",
    "B11": "Hydro Run-of-river and poundage",
    "B12": "Hydro Water Reservoir",
    "B13": "Marine",
    "B14": "Nuclear",
    "B15": "Other renewable",
    "B16": "Solar",
    "B17": "Waste",
    "B18": "Wind Offshore",
    "B19": "Wind Onshore",
    "B20": "Other",
    "B21": "AC Link",
    "B22": "DC Link",
    "B23": "Substation",
    "B24": "Transformer",
}

# ---------------------------------------------------------------------------
# Default plot colors (hex) per source
# Ported from legacy/energy_system_simulation.py:35-47
# ---------------------------------------------------------------------------

DEFAULT_PLOT_COLORS: dict[str, str] = {
    "Biomass": "#8C564B",
    "Geothermal": "#D62728",
    "Hydro Pumped Storage": "#BCBD22",
    "Hydro Run-of-river and poundage": "#1F77B4",
    "Hydro Water Reservoir": "#17BECF",
    "Other renewable": "#E377C2",
    "Solar": "#FFBF00",
    "Wind Offshore": "#9467BD",
    "Wind Onshore": "#2CA02C",
    "Wind": "#8C564B",
    "Other": "#7F7F7F",
}