"""Consistency checks for core.config constants."""

from core.config import (
    COUNTRIES,
    DEFAULT_PSR_TYPES,
    DISPATCH_ORDER,
    PLOT_COLORS,
    PSR_NAME,
    SOURCE_CLASSIFICATIONS,
)


def test_classifications_and_dispatch_order_are_consistent():
    # Every classified source appears in the dispatch order, and vice versa.
    assert set(SOURCE_CLASSIFICATIONS) == set(DISPATCH_ORDER)
    # No duplicates in the dispatch order.
    assert len(DISPATCH_ORDER) == len(set(DISPATCH_ORDER))


def test_psr_name_covers_default_psr_types():
    for code in DEFAULT_PSR_TYPES:
        assert code in PSR_NAME, f"PSR code {code} missing from PSR_NAME"
    assert all(name for name in PSR_NAME.values())


def test_plot_colors_are_nonempty():
    assert PLOT_COLORS
    for name, color in PLOT_COLORS.items():
        assert isinstance(color, str) and color.startswith("#")


def test_solar_color_is_bright_yellow():
    assert PLOT_COLORS["Solar"] == "#FFD700"


def test_countries_are_well_formed():
    assert COUNTRIES
    for c in COUNTRIES:
        assert c["code"].isalpha() and len(c["code"]) == 2
        assert c["name"]


def test_source_meta_storage_fields():
    storage = SOURCE_CLASSIFICATIONS["Hydro Pumped Storage"]
    assert storage.flexibility == "storage"
    assert storage.roundtrip_efficiency > 0
