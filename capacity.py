#!/usr/bin/env python3
"""Query installed generation capacity from ENTSO-E Transparency Platform.

Usage:
    python capacity.py
    python capacity.py IT

Output: JSON dict of source name → installed capacity in MW.
"""

from __future__ import annotations

import json
import os
import sys

import pandas as pd
from dotenv import load_dotenv
from entsoe import EntsoePandasClient

from fetch import PSR_NAME


def query_installed_capacity(country: str, api_key: str | None = None) -> dict[str, float]:
    """Query installed generation capacity for a country from ENTSO-E.

    Parameters
    ----------
    country : str
        Two-letter country code (e.g. "IT", "DE", "FR").
    api_key : str | None
        ENTSO-E API key. If None, loaded from ENTSOE_KEY env var
        (via .env file or environment).

    Returns
    -------
    dict[str, float]
        Mapping of canonical source name → installed capacity in MW.
        Returns an empty dict if the API returns no data.

    Raises
    ------
    ValueError
        If no API key is available.
    """
    if api_key is None:
        load_dotenv()
        api_key = os.getenv("ENTSOE_KEY")
        if not api_key:
            raise ValueError(
                "ENTSOE_KEY not found. Set it in .env or export it."
            )

    client = EntsoePandasClient(api_key=api_key)

    # Installed capacity is reported per calendar year.
    start = pd.Timestamp("2025-01-01", tz="UTC")
    end = pd.Timestamp("2025-12-31", tz="UTC")

    df = client.query_installed_generation_capacity(country, start=start, end=end)

    if df.empty:
        return {}

    # The DataFrame has one row with canonical source-name columns
    # (already mapped by entsoe-py's internal PSRTYPE_MAPPINGS).
    # Normalise any stray PSR codes through PSR_NAME for safety.
    row = df.iloc[0]
    result: dict[str, float] = {}
    for col in df.columns:
        name = PSR_NAME.get(col, col)
        val = row[col]
        if pd.notna(val):
            result[name] = float(val)

    return result


if __name__ == "__main__":
    country = sys.argv[1] if len(sys.argv) > 1 else "IT"
    try:
        capacities = query_installed_capacity(country)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(capacities, indent=2))
    print(f"\nTotal installed capacity: {sum(capacities.values()):,.0f} MW", file=sys.stderr)
