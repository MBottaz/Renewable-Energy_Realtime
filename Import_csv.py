import pandas as pd

def import_dem_gen():
    # Load the two datasets from the "data" folder
    demand_df = pd.read_csv("data/Demand_2022_23.csv")
    generation_df = pd.read_csv("data/Generation_Ren_2022_23.csv")

    generation_df['Date'] = generation_df['Date'].str.strip("'")
    generation_df['Renewable Generation (GWh)'] = generation_df['Renewable Generation (GWh)'].astype(float)
    
    demand_df['Date'] = pd.to_datetime(demand_df['Date'], format='%Y-%m-%d %H:%M:%S')
    generation_df['Date'] = pd.to_datetime(generation_df['Date'], format='%d/%m/%Y %H:%M', errors='coerce')


    # Pivot the generation data table
    gen_grouped_df = generation_df.groupby(['Date', 'Energy Source'])['Renewable Generation (GWh)'].sum().unstack()
    gen_grouped_df = gen_grouped_df.reset_index()

    # Merge datasets based on the 'Date' column
    em_gen_df = pd.merge(demand_df, gen_grouped_df, on='Date')
    

    # ATTENZIONE! Con l'istruzione seguente si da per scontato che le date siano nell ostesso ordine per entrambi i dataframe
    gen_grouped_df['Load'] = demand_df['Total Load (GW)']

    print(gen_grouped_df.tail())

    return gen_grouped_df

# Execute the function and save the result to a new CSV file
real_df = import_dem_gen()
real_df.to_csv("data/merged.csv", index=False)
