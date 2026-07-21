import pandas as pd
import matplotlib.pyplot as plt


FOSSIL_COLUMNS = [
    "Fossil Coal-derived gas",
    "Fossil Gas",
    "Fossil Hard coal",
    "Fossil Oil",
]

RENEWABLE_COLUMNS = [
    "Biomass",
    "Geothermal",
    "Hydro Run-of-river and poundage",
    "Hydro Water Reservoir",
    "Solar",
    "Wind Offshore",
    "Wind Onshore",
]


def load_generation_data():
    df = pd.read_csv("data/italy_load_generation.csv")
    df["Date"] = pd.to_datetime(df["Date"], format="%Y-%m-%d %H:%M:%S%z")
    df["Date"] = df["Date"].apply(lambda x: x.strftime("%H, %d-%m-%Y"))
    df.rename(
        columns={"Hydro Run-of-river and poundage": "Hydro (River)"}, inplace=True
    )
    df["Wind"] = df["Wind Offshore"] + df["Wind Onshore"]
    df["Renewable Total"] = (
        df["Solar"]
        + df["Wind"]
        + df["Hydro (River)"]
        + df["Geothermal"]
        + df["Biomass"]
    )
    df["Actual Load"] = df["Load"] - df["Renewable Total"]
    df["Other"] = df["Actual Load"]

    return df


def load_installed_capacity():
    df = pd.read_csv("data/Installed_Capacity.csv")
    df = df.drop(
        columns=FOSSIL_COLUMNS + ["Marine", "Other", "Other renewable", "Waste"]
    )
    df["Wind"] = df["Wind Offshore"] + df["Wind Onshore"]
    df = df.drop(columns=["Wind Offshore", "Wind Onshore"])
    df.rename(
        columns={"Hydro Run-of-river and poundage": "Hydro (River)"}, inplace=True
    )

    return df


def calculate_capacity_factors(df_installed):
    df_target = pd.read_csv("data/Target.csv")
    df_installed["Solar"] = df_target["Solar"] / df_installed["Solar"]
    df_installed["Wind"] = df_target["Wind"] / df_installed["Wind"]

    return df_installed


def apply_capacity_factors(df_generation, df_capacity_factors):
    df_generation["Solar"] = df_generation["Solar"] * df_capacity_factors["Solar"][0]
    df_generation["Wind"] = df_generation["Wind"] * df_capacity_factors["Wind"][0]
    df_generation["Renewable Total"] = (
        df_generation["Solar"]
        + df_generation["Wind"]
        + df_generation["Hydro (River)"]
        + df_generation["Geothermal"]
        + df_generation["Biomass"]
    )
    df_generation["Other"] = df_generation["Load"] - df_generation["Renewable Total"]

    return df_generation


def plot_generation(df):
    plt.figure(figsize=(12, 6))
    x = range(len(df["Date"]))

    plt.bar(
        x,
        df["Solar"],
        color="yellow",
        label="Solar",
        bottom=df["Biomass"] + df["Geothermal"] + df["Hydro (River)"] + df["Wind"],
    )
    plt.bar(
        x,
        df["Wind"],
        color="blue",
        label="Wind",
        bottom=df["Biomass"] + df["Geothermal"] + df["Hydro (River)"],
    )
    plt.bar(
        x,
        df["Hydro (River)"],
        color="cyan",
        label="Hydro",
        bottom=df["Biomass"] + df["Geothermal"],
    )
    plt.bar(
        x, df["Geothermal"], color="green", label="Geothermal", bottom=df["Biomass"]
    )
    plt.bar(x, df["Biomass"], color="orange", label="Biomass")

    plt.plot(x, df["Actual Load"], color="red", linewidth=2, label="Load")

    x_labels = df["Date"][::2]
    x_positions = range(0, len(df["Date"]), 2)
    plt.xticks(x_positions, x_labels, rotation=90, fontsize=6)

    plt.xlabel("Hour of the Day")
    plt.ylabel("Power (GW)")
    plt.title("Power Generation and Load Profile")
    plt.legend()
    plt.grid(True)
    plt.show()


def main():
    df = load_generation_data()
    df_inst = load_installed_capacity()
    df_inst = calculate_capacity_factors(df_inst)
    df_enhanced = apply_capacity_factors(df, df_inst)
    plot_generation(df_enhanced)


if __name__ == "__main__":
    main()
