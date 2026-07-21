#!/usr/bin/env python3
"""
Energy System Simulation Script

This script simulates an energy system by scaling actual production data
proportionally to target installed capacities and visualizes the results
with a stacked area chart.

Usage:
    python energy_system_simulation.py

Requires:
    - data/italy_load_generation.csv (actual generation data)
    - data/Installed_Capacity.csv (actual installed capacity)
    - data/Target.csv (target installed capacity - created if missing)
"""

import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime

# Define renewable energy sources to include in simulation
RENEWABLE_SOURCES = [
    "Biomass",
    "Geothermal",
    "Hydro Run-of-river and poundage",
    "Hydro Water Reservoir",
    "Solar",
    "Wind Offshore",
    "Wind Onshore",
]

# Color mapping for visualization
SOURCE_COLORS = {
    "Biomass": "#8C564B",  # Brown
    "Geothermal": "#D62728",  # Red
    "Hydro Pumped Storage": "#BCBD22",  # Olive
    "Hydro Run-of-river and poundage": "#1F77B4",  # Blue
    "Hydro Water Reservoir": "#17BECF",  # Cyan
    "Other renewable": "#E377C2",  # Pink
    "Solar": "#FFBF00",  # Amber / Solar yellow
    "Wind Offshore": "#9467BD",  # Purple
    "Wind Onshore": "#2CA02C",  # Green
    "Wind": "#8C564B",  # Brown (combined wind)
    "Other": "#7F7F7F",  # Gray
}


def load_generation_data():
    """Load actual generation data and electricity demand."""
    try:
        df = pd.read_csv("data/italy_load_generation.csv")

        # Convert datetime and format for display
        df["Date"] = pd.to_datetime(df.iloc[:, 0])  # First column is datetime
        df["Date_str"] = df["Date"].dt.strftime("%H:%M %d-%m")

        # Rename columns for consistency
        df.rename(
            columns={
                "Actual Load": "Demand",
                "Hydro Run-of-river and poundage": "Hydro River",
                "Hydro Water Reservoir": "Hydro Reservoir",
            },
            inplace=True,
        )

        # Combine wind sources
        if "Wind Offshore" in df.columns and "Wind Onshore" in df.columns:
            df["Wind"] = df["Wind Offshore"] + df["Wind Onshore"]

        return df

    except FileNotFoundError:
        print("Error: data/italy_load_generation.csv not found.")
        print("Please run import_API.py first to generate the data.")
        exit(1)
    except Exception as e:
        print(f"Error loading generation data: {e}")
        exit(1)


def load_installed_capacity():
    """Load actual installed capacity data."""
    try:
        df = pd.read_csv("data/Installed_Capacity.csv")

        # Clean and prepare capacity data
        capacity = {}
        for source in RENEWABLE_SOURCES:
            if source in df.columns:
                capacity[source] = df[source].iloc[0]
            else:
                capacity[source] = 0.0

        # Combine wind capacities
        wind_capacity = capacity.get("Wind Offshore", 0) + capacity.get(
            "Wind Onshore", 0
        )
        capacity["Wind"] = wind_capacity

        return capacity

    except FileNotFoundError:
        print("Error: data/Installed_Capacity.csv not found.")
        print("Please run import_API.py first to generate the data.")
        exit(1)
    except Exception as e:
        print(f"Error loading installed capacity: {e}")
        exit(1)


def load_or_create_target_capacity():
    """Load target capacity or create default example if missing."""
    target_file = "data/Target.csv"

    if os.path.exists(target_file):
        try:
            df = pd.read_csv(target_file)
            target = {}
            for source in RENEWABLE_SOURCES:
                if source in df.columns:
                    target[source] = df[source].iloc[0]
                elif source.replace(" ", "_") in df.columns:
                    target[source] = df[source.replace(" ", "_")].iloc[0]
                else:
                    # Use actual capacity as default if target not specified
                    target[source] = None
            return target
        except Exception as e:
            print(f"Error loading target capacity: {e}")
            print("Creating default target capacity...")

    # Create default target capacity (2x actual capacity for demonstration)
    print("Creating default target capacity file...")
    actual_capacity = load_installed_capacity()

    target = {}
    for source in RENEWABLE_SOURCES:
        if source in actual_capacity:
            # Default: use the actual capacity for demonstration
            target[source] = actual_capacity[source]
        else:
            target[source] = 0

    # Save default target
    target_df = pd.DataFrame([target])
    os.makedirs("data", exist_ok=True)
    target_df.to_csv(target_file, index=False)
    print(f"Created default target capacity in {target_file}")

    return target


def scale_production(df_generation, actual_capacity, target_capacity):
    """Scale production proportionally based on target vs actual capacity."""

    # Create a copy to avoid modifying original data
    df_scaled = df_generation.copy()

    # Scale each renewable source
    for source in RENEWABLE_SOURCES:
        if source in df_scaled.columns and source in actual_capacity:
            actual_cap = actual_capacity[source]

            # Skip if actual capacity is zero or source not in target
            if actual_cap <= 0 or source not in target_capacity:
                continue

            target_cap = target_capacity[source]

            # If target not specified, use actual capacity (no scaling)
            if target_cap is None or target_cap <= 0:
                continue

            # Calculate scaling factor
            scaling_factor = target_cap / actual_cap

            # Apply scaling
            df_scaled[source] = df_scaled[source] * scaling_factor

    # Combine wind sources after scaling
    if "Wind Offshore" in df_scaled.columns and "Wind Onshore" in df_scaled.columns:
        df_scaled["Wind"] = df_scaled["Wind Offshore"] + df_scaled["Wind Onshore"]

    return df_scaled


def calculate_other_production(df_scaled):
    """Calculate 'Other' as Load - Sum(All Generation Sources)."""

    # Get all generation source columns (exclude non-generation columns)
    exclude_columns = [
        "Date",
        "Date_str",
        "Demand",
        "Renewable Total",
        "Load",
        "Unnamed: 0",
    ]

    # Get all potential generation columns
    potential_sources = [col for col in df_scaled.columns if col not in exclude_columns]

    # Handle wind sources - avoid double counting
    # If 'Wind' column exists (combined), exclude individual wind sources
    if (
        "Wind" in potential_sources
        and "Wind Offshore" in potential_sources
        and "Wind Onshore" in potential_sources
    ):
        generation_columns = [
            col
            for col in potential_sources
            if col not in ["Wind Offshore", "Wind Onshore"]
        ]
    else:
        generation_columns = potential_sources

    # Calculate total generation from all sources
    df_scaled["Total Generation"] = df_scaled[generation_columns].sum(axis=1)

    # Calculate Other = Load - Total Generation
    # This ensures: Load = Total Generation + Other
    # Note: Other can be negative if total generation exceeds demand (excess generation)
    df_scaled["Other"] = df_scaled["Demand"] - df_scaled["Total Generation"]

    # No clipping - allow negative values for excess generation scenarios

    # Validation check
    calculation_error = df_scaled["Demand"] - (
        df_scaled["Total Generation"] + df_scaled["Other"]
    )
    max_error = abs(calculation_error).max()
    if max_error > 0.1:
        print(
            f"Warning: Calculation validation failed - max difference: {max_error:.6f}"
        )
        print(f"Generation columns used: {generation_columns}")

        # Debug first row
        first_row = df_scaled.iloc[0]
        print(f"First row debug:")
        print(f"  Demand: {first_row['Demand']}")
        print(f"  Total Generation: {first_row['Total Generation']}")
        print(f"  Other: {first_row['Other']}")
        print(
            f"  Sum check: {first_row['Demand']} = {first_row['Total Generation']} + {first_row['Other']} -> {first_row['Demand'] == first_row['Total Generation'] + first_row['Other']}"
        )

    else:
        print(f"Validation: Calculation accurate (max difference: {max_error:.6f}")

    return df_scaled


def plot_stacked_area_chart(df_results):
    """Create stacked area chart visualization."""

    plt.figure(figsize=(14, 8))

    # Prepare data for plotting
    time_points = range(len(df_results))

    # Define plotting order (from bottom to top) - match actual data sources
    sources_to_plot = [
        "Biomass",
        "Geothermal",
        "Hydro Pumped Storage",
        "Hydro Run-of-river and poundage",
        "Hydro Water Reservoir",
        "Other renewable",
        "Wind Offshore",
        "Wind Onshore",
        "Solar",
        "Other",
    ]

    # Filter to only include available sources
    available_sources = [s for s in sources_to_plot if s in df_results.columns]

    # Handle wind sources - if 'Wind' column exists, replace individual wind sources
    if (
        "Wind" in df_results.columns
        and "Wind Offshore" in available_sources
        and "Wind Onshore" in available_sources
    ):
        available_sources = [
            s for s in available_sources if s not in ["Wind Offshore", "Wind Onshore"]
        ] + ["Wind"]

    # Create stacked area plot using cumulative sums
    cumulative_bottom = pd.Series([0] * len(df_results), index=df_results.index)

    for source in available_sources:
        if source == "Other":
            # Plot Other as a separate area on top
            plt.fill_between(
                time_points,
                cumulative_bottom,
                cumulative_bottom + df_results[source],
                color=SOURCE_COLORS.get(source, "#808080"),
                alpha=0.7,
                label=source,
            )
        else:
            plt.fill_between(
                time_points,
                cumulative_bottom,
                cumulative_bottom + df_results[source],
                color=SOURCE_COLORS.get(source, "#808080"),
                alpha=0.7,
                label=source,
            )
        cumulative_bottom += df_results[source]

    # Plot demand as a line
    plt.plot(
        time_points,
        df_results["Demand"],
        color="red",
        linewidth=2,
        linestyle="--",
        label="Electricity Demand",
    )

    # Format x-axis with time labels
    # Show every 6th label to avoid overcrowding
    step = max(1, len(time_points) // 20)
    plt.xticks(
        time_points[::step],
        df_results["Date_str"][::step],
        rotation=45,
        ha="right",
        fontsize=8,
    )

    plt.xlabel("Time", fontsize=12)
    plt.ylabel("Power (MW)", fontsize=12)
    plt.title(
        "Energy System Simulation: Production by Source vs Demand", fontsize=14, pad=20
    )
    plt.legend(loc="upper right", bbox_to_anchor=(1.15, 1))
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    # Add some padding for legend
    plt.subplots_adjust(right=0.75)

    plt.show()


def main():
    """Main execution function."""

    print("Energy System Simulation")
    print("=" * 40)

    # Load data
    print("Loading generation data...")
    df_generation = load_generation_data()

    print("Loading installed capacity...")
    actual_capacity = load_installed_capacity()

    print("Loading target capacity...")
    target_capacity = load_or_create_target_capacity()

    # Display capacity information
    print("\nCapacity Information:")
    print("Source                  Actual (MW)   Target (MW)   Scale Factor")
    print("-" * 65)

    for source in RENEWABLE_SOURCES:
        if source in actual_capacity and actual_capacity[source] > 0:
            actual = actual_capacity[source]
            target = target_capacity.get(source, actual)
            if target and target > 0:
                factor = target / actual
                print(f"{source:25} {actual:12.0f}   {target:12.0f}   {factor:.2f}x")
            else:
                print(f"{source:25} {actual:12.0f}   {'(unchanged)':12}   1.00x")

    # Scale production
    print("\nScaling production to target capacities...")
    df_scaled = scale_production(df_generation, actual_capacity, target_capacity)

    # Calculate Other
    print("Calculating 'Other' production...")
    df_results = calculate_other_production(df_scaled)

    # Generate statistics
    total_demand = df_results["Demand"].sum()
    total_generation = df_results["Total Generation"].sum()
    total_other = df_results["Other"].sum()

    generation_share = (
        (total_generation / total_demand) * 100 if total_demand > 0 else 0
    )
    other_share = (total_other / total_demand) * 100 if total_demand > 0 else 0

    # Calculate validation
    calculation_check = total_demand - (total_generation + total_other)

    print(f"\nSimulation Results:")
    print(f"Total Demand:        {total_demand:,.0f} MWh")
    print(f"Total Generation:    {total_generation:,.0f} MWh ({generation_share:.1f}%)")
    print(f"Total Other:         {total_other:,.0f} MWh ({other_share:.1f}%)")
    print(f"Calculation Check:   {calculation_check:,.0f} MWh (should be ~0)")

    df_results.to_csv("data/simulation_results.csv", index=True)

    # Plot results
    print("\nGenerating visualization...")
    plot_stacked_area_chart(df_results)

    print("\nSimulation complete!")


if __name__ == "__main__":
    main()
