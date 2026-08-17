"""Hand-maintained installed-capacity data.

ENTSO-E's installed-capacity values for Italy are not reliable for the solar
and wind technologies, so the static site uses this checked-in 2025 snapshot
instead of querying the capacity API.
"""

from __future__ import annotations

from copy import deepcopy


# Wind Onshore contains the combined onshore + offshore figure.  Keeping the
# canonical ENTSO-E source names means production sources remain covered by
# the capacity payload while avoiding a second, misleading wind category.
MANUAL_CAPACITY: dict[str, dict[int, dict[str, float]]] = {
    "IT": {
        2025: {
            "Biomass": 1539.0,
            "Fossil Brown coal/Lignite": 0.0,
            "Fossil Coal-derived gas": 2076.0,
            "Fossil Gas": 45549.0,
            "Fossil Hard coal": 5227.0,
            "Fossil Oil": 1548.0,
            "Fossil Peat": 0.0,
            "Geothermal": 868.0,
            "Hydro Pumped Storage": 7245.0,
            "Hydro Run-of-river and poundage": 10317.0,
            "Hydro Water Reservoir": 4548.0,
            "Marine": 0.0,
            "Other": 437.0,
            "Other renewable": 1.0,
            "Solar": 43512.0,
            "Waste": 671.0,
            "Wind Offshore": 0.0,
            "Wind Onshore": 13629.0,
        }
    }
}


def manual_installed_capacity(country: str, year: int = 2025) -> dict[str, float]:
    """Return a copy of the hand-maintained capacity for ``country`` and year."""
    code = country.upper()
    try:
        return deepcopy(MANUAL_CAPACITY[code][year])
    except KeyError as exc:
        supported = ", ".join(
            f"{code}/{supported_year}"
            for code, years in MANUAL_CAPACITY.items()
            for supported_year in years
        )
        raise ValueError(f"no manual capacity data for {code}/{year} (available: {supported})") from exc
