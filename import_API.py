import os
import pandas as pd
from entsoe import EntsoePandasClient
from datetime import datetime, timedelta

def get_ENTSOe_KEY():
    key = os.environ['ENTSOe_KEY']
    return key

# Function to query installed capacity
def query_installed_capacity(api_key, country_code, start_date, end_date):
    client = EntsoePandasClient(api_key=api_key)

    new_end_date = end_date - timedelta(days=1)
    
    installed_capacity = client.query_installed_generation_capacity(country_code, start=start_date, end=new_end_date, psr_type=None)
    
    installed_capacity.to_csv('data/Installed_Capacity.csv', index=False)
    return installed_capacity


# Function to query load data
def query_load_data(api_key, country_code, start_date, end_date):
    client = EntsoePandasClient(api_key=api_key)
    load_data = client.query_load(country_code, start=start_date, end=end_date)
    return load_data

# Function to save data to CSV
def save_to_csv(data, filename, start_date, end_date):
    date_range = pd.date_range(start=start_date, end=(end_date - pd.Timedelta(hours=1)), freq='h')
    data.insert(0, 'Date', date_range)
    data.to_csv(filename, index=False)


# Main function to orchestrate the process
def main():
    api_key = get_ENTSOe_KEY()
    country_code = 'IT'
    start_date = pd.Timestamp('2023-01-01', tz='Europe/Rome')
    end_date = pd.Timestamp('2023-01-08', tz='Europe/Rome')

    print("installed capacity")
    installed_capacity = query_installed_capacity(api_key, country_code, start_date, end_date)

    print("load data")
    load_data = query_load_data(api_key, country_code, start_date, end_date)
    
    # Create a dictionary to map the old column names to the new ones
    column_mapping = {
        'A05': 'Load',
        'B01': 'Biomass',
        'B02': 'Fossil Brown coal/Lignite',
        'B03': 'Fossil Coal-derived gas',
        'B04': 'Fossil Gas',
        'B05': 'Fossil Hard coal',
        'B06': 'Fossil Oil',
        'B07': 'Fossil Oil shale',
        'B08': 'Fossil Peat',
        'B09': 'Geothermal',
        'B10': 'Hydro Pumped Storage',
        'B11': 'Hydro Run-of-river and poundage',
        'B12': 'Hydro Water Reservoir',
        'B13': 'Marine',
        'B14': 'Nuclear',
        'B15': 'Other renewable',
        'B16': 'Solar',
        'B17': 'Waste',
        'B18': 'Wind Offshore',
        'B19': 'Wind Onshore',
        'B20': 'Other',
        'B21': 'AC Link',
        'B22': 'DC Link',
        'B23': 'Substation',
        'B24': 'Transformer'
    }

    print("generation data")
    # Query generation data for each type of PSR
    generation_data = {}
    psr_types = ['B01', 'B09', 'B11', 'B16', 'B18', 'B19']
    client = EntsoePandasClient(api_key=api_key)
    for psr_type in psr_types:
        # print(psr_type)
        generation_data[psr_type] = client.query_generation(country_code, start=start_date, end=end_date, psr_type=psr_type)
    

    
    # Create a new column for each of the psr types and add the data to it
    for psr_type in psr_types:
        load_data[psr_type] = generation_data[psr_type]

    # Rename the columns in the DataFrame
    load_data = load_data.rename(columns=column_mapping)


    save_to_csv(load_data, 'data/italy_load_generation.csv', start_date, end_date)

if __name__ == "__main__":
    main()
