import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

def read_generation():
    df = pd.read_csv('data/italy_load_generation.csv')
    df['Date'] = pd.to_datetime(df['Date'], format='%Y-%m-%d %H:%M:%S%z')
    df['Date'] = df['Date'].apply(lambda x: x.strftime('%H, %d-%m-%Y'))
    df.rename(columns={"Hydro Run-of-river and poundage": "Hydro (River)"}, inplace=True)
    df['Wind'] = df['Wind Offshore'] + df['Wind Onshore']

    # Add new columns to the dataframe
    df['PumpedHydro'] = 0
    df['PumpedHydro_Stored'] = 0
    df['Batteries'] = 0
    df['Batteries_Stored'] = 0
    df['Others'] = 0


    # df.to_csv('output.csv', index=False)

    return df



def read_installed():
    df = pd.read_csv('data/Installed_Capacity.csv')

    df = df.drop(columns=['Fossil Coal-derived gas', 'Fossil Gas', 'Fossil Hard coal', 'Fossil Oil',
                          'Marine', 'Other', 'Other renewable', 'Waste'])
    
    df['Wind'] = df['Wind Offshore'] + df['Wind Onshore']
    df = df.drop(columns=['Wind Offshore', 'Wind Onshore'])

    df.rename(columns={"Hydro Run-of-river and poundage": "Hydro (River)"}, inplace=True)

    return df


def calculate_target(df_inst): # Passare un anno alla volta
    
    df_target = pd.read_csv('data/Target.csv')

    # df = pd.DataFrame()
    df_inst['Solar']= df_target['Solar']/df_inst['Solar']
    df_inst['Wind']= df_target['Wind'] / (df_inst['Wind'])
    # df.rename(columns={"Hydro Run-of-river and poundage": "Hydro"}, inplace=True)

    return df_inst

def enhance_generation(df, df_target):
    df['Solar'] = df['Solar'] * df_target['Solar'][0]
    df['Wind'] = df['Wind'] * df_target['Wind'][0]

    return df

def flexibility(df, df_target):

    for i in range(len(df)):
        TBS = df['Actual Load'] - df['Solar'] - df['Wind'] - df['Hydro (River)'] - df['Geothermal'] - df['Biomass']

        

    return df

def plot_generation(df):
    plt.figure(figsize=(12, 6))

    # Crea una variabile per l'asse x
    x = range(len(df['Date']))

    # Grafico a barre
    plt.bar(x, df['Solar'], color='yellow', label='Solar', bottom=df['Biomass']+df['Geothermal']+df['Hydro (River)']+df['Wind'])
    plt.bar(x, df['Wind'], color='blue', label='Wind', bottom=df['Biomass']+df['Geothermal']+df['Hydro (River)'])
    plt.bar(x, df['Hydro (River)'], color='cyan', label='Hydro', bottom=df['Biomass']+df['Geothermal'])
    plt.bar(x, df['Geothermal'], color='green', label='Geothermal', bottom=df['Biomass'])
    plt.bar(x, df['Biomass'], color='orange', label='Biomass')

    # Linea continua per la grandezza 'Load'
    plt.plot(x, df['Actual Load'], color='red', linewidth=2, label='Load')

    # Etichette per l'asse x
    x_labels = df['Date'][::2]  # Seleziona ogni secondo elemento
    x_positions = range(0, len(df['Date']), 2)  # Posizioni per le etichette selezionate
    plt.xticks(x_positions, x_labels, rotation=90, fontsize=6)

    plt.xlabel('Hour of the Day')
    plt.ylabel('Power (GW)')
    plt.title('Power Generation and Load Profile')
    plt.legend()
    plt.grid(True)
    plt.show()


df = read_generation()
df_inst = read_installed()
df_inst = calculate_target(df_inst)

df_enhanced = enhance_generation(df, df_inst)

plot_generation(df_enhanced)

# print(df_enhanced[['Date', 'Wind', 'Solar']])

