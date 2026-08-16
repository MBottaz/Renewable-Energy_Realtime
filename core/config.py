"""Central configuration for the Renewable Energy Realtime project.

All constants, model configuration, and project-path helpers live here so
that no module has scattered literals.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# ── Project paths (CWD-independent) ─────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"              # raw fetched data (gitignored)
OUTPUT_DIR = PROJECT_ROOT / "output"          # match/plot results (gitignored)
FRONTEND_DIR = PROJECT_ROOT / "frontend"      # static site (committed)
FRONTEND_DATA_DIR = FRONTEND_DIR / "data"     # legacy static assets dir (committed)
FRONTEND_JS_DIR = FRONTEND_DIR / "js"         # vendored libs + generated data bundle

# ── Frontend export ─────────────────────────────────────────────────────
# Default data window requested by the fetch CLI (one calendar year).
# The frontend can display any range covered by the bundled data.
DEFAULT_INTERVAL_DAYS = 365
COUNTRIES: list[dict[str, str]] = [
    {"code": "IT", "name": "Italia"},
]

# ── ENTSO-E PSR type code → canonical source name ───────────────────────
PSR_NAME: dict[str, str] = {
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
    "B25": "Energy storage",
}

# PSR types to fetch (generation sources only, no load/links)
DEFAULT_PSR_TYPES: list[str] = [
    "B01",  # Biomass
    "B09",  # Geothermal
    "B10",  # Hydro Pumped Storage
    "B11",  # Hydro Run-of-river and poundage
    "B12",  # Hydro Water Reservoir
    "B15",  # Other renewable
    "B16",  # Solar
    "B18",  # Wind Offshore
    "B19",  # Wind Onshore
    "B25",  # Energy storage
]

# ── Source metadata ─────────────────────────────────────────────────────


@dataclass
class SourceMeta:
    """Classification of a single energy source."""

    name: str
    flexibility: str  # "inflexible" | "flexible" | "storage"
    # Storage-only fields
    capacity_kwh: float = 0.0
    max_charge_rate_kw: float = 0.0
    max_discharge_rate_kw: float = 0.0
    initial_soc_kwh: float = 0.0
    roundtrip_efficiency: float = 1.0


# Every production source → its classification
SOURCE_CLASSIFICATIONS: dict[str, SourceMeta] = {
    # --- Inflexible renewables (must-run) ---
    "Solar": SourceMeta("Solar", "inflexible"),
    "Wind Onshore": SourceMeta("Wind Onshore", "inflexible"),
    "Wind Offshore": SourceMeta("Wind Offshore", "inflexible"),
    "Geothermal": SourceMeta("Geothermal", "inflexible"),
    "Hydro Run-of-river and poundage": SourceMeta(
        "Hydro Run-of-river and poundage", "inflexible"
    ),
    "Biomass": SourceMeta("Biomass", "inflexible"),
    "Marine": SourceMeta("Marine", "inflexible"),
    "Nuclear": SourceMeta("Nuclear", "inflexible"),
    # --- Storage ---
    "Hydro Pumped Storage": SourceMeta(
        "Hydro Pumped Storage",
        "storage",
        roundtrip_efficiency=0.85,
    ),
    "Energy storage": SourceMeta(
        "Energy storage",
        "storage",
        roundtrip_efficiency=0.80,
    ),
    # --- Flexible renewables ---
    "Hydro Water Reservoir": SourceMeta("Hydro Water Reservoir", "flexible"),
    "Other renewable": SourceMeta("Other renewable", "flexible"),
    # --- Fossil / dispatchable ---
    "Fossil Brown coal/Lignite": SourceMeta("Fossil Brown coal/Lignite", "flexible"),
    "Fossil Coal-derived gas": SourceMeta("Fossil Coal-derived gas", "flexible"),
    "Fossil Gas": SourceMeta("Fossil Gas", "flexible"),
    "Fossil Hard coal": SourceMeta("Fossil Hard coal", "flexible"),
    "Fossil Oil": SourceMeta("Fossil Oil", "flexible"),
    "Fossil Oil shale": SourceMeta("Fossil Oil shale", "flexible"),
    "Fossil Peat": SourceMeta("Fossil Peat", "flexible"),
    "Waste": SourceMeta("Waste", "flexible"),
    "Other": SourceMeta("Other", "flexible"),
}

# Dispatch priority (first = highest)
DISPATCH_ORDER: list[str] = [
    # Inflexible
    "Solar",
    "Wind Onshore",
    "Wind Offshore",
    "Geothermal",
    "Hydro Run-of-river and poundage",
    "Biomass",
    "Marine",
    "Nuclear",
    # Storage
    "Hydro Pumped Storage",
    # Flexible
    "Hydro Water Reservoir",
    "Other renewable",
    "Energy storage",
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

# ── Plot colours per source ─────────────────────────────────────────────
# Related technologies deliberately share colour families so charts are easy
# to scan: hydro=blue, solar=yellow, wind=green, fossil=grey, storage=red.
# Orange is intentionally reserved for non-technology UI elements.
PLOT_COLORS: dict[str, str] = {
    "Biomass": "#795548",
    "Geothermal": "#7E57C2",
    "Hydro Pumped Storage": "#1565C0",
    "Hydro Run-of-river and poundage": "#42A5F5",
    "Hydro Water Reservoir": "#0D47A1",
    "Other renewable": "#26A69A",
    "Solar": "#F4C430",
    "Wind Offshore": "#2E7D32",
    "Wind Onshore": "#66BB6A",
    "Energy storage": "#D32F2F",
    "Fossil Brown coal/Lignite": "#374151",
    "Fossil Coal-derived gas": "#4B5563",
    "Fossil Gas": "#6B7280",
    "Fossil Hard coal": "#52525B",
    "Fossil Oil": "#71717A",
    "Fossil Oil shale": "#9CA3AF",
    "Fossil Peat": "#A1A1AA",
    "Marine": "#00838F",
    "Nuclear": "#263238",
    "Waste": "#8D6E63",
    "Other": "#94A3B8",
}