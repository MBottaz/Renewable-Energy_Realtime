#!/usr/bin/env python3
"""Generate mock generation data for all countries (8760 hours for 2024)."""
import json
import math
import random
import os

random.seed(42)

YEARS = {"2024": 8760, "2025": 8760}  # 2025 not a leap year
HOURS = 8760  # 2024 is a leap year but we use 8760 for consistency with the prompt

COUNTRY_PARAMS = {
    "IT": {
        "load_base": 30000, "load_amplitude": 8000,
        "solar_cf": 0.18, "wind_cf": 0.20, "hydro_cf": 0.35,
        "gas_base": 12000, "coal_base": 3000, "other_base": 2000,
        "wind_offshore": 0,
    },
    "DE": {
        "load_base": 55000, "load_amplitude": 12000,
        "solar_cf": 0.12, "wind_cf": 0.25, "hydro_cf": 0.30,
        "gas_base": 10000, "coal_base": 12000, "other_base": 5000,
        "wind_offshore": 3000,
    },
    "FR": {
        "load_base": 48000, "load_amplitude": 10000,
        "solar_cf": 0.14, "wind_cf": 0.22, "hydro_cf": 0.35,
        "gas_base": 3000, "coal_base": 1000, "other_base": 1000,
        "wind_offshore": 500,
    },
    "ES": {
        "load_base": 28000, "load_amplitude": 6000,
        "solar_cf": 0.22, "wind_cf": 0.23, "hydro_cf": 0.30,
        "gas_base": 8000, "coal_base": 1500, "other_base": 1500,
        "wind_offshore": 0,
    },
    "PL": {
        "load_base": 20000, "load_amplitude": 5000,
        "solar_cf": 0.11, "wind_cf": 0.22, "hydro_cf": 0.20,
        "gas_base": 5000, "coal_base": 12000, "other_base": 1500,
        "wind_offshore": 0,
    },
    "NL": {
        "load_base": 14000, "load_amplitude": 3000,
        "solar_cf": 0.10, "wind_cf": 0.28, "hydro_cf": 0.10,
        "gas_base": 8000, "coal_base": 2000, "other_base": 1000,
        "wind_offshore": 1500,
    },
    "BE": {
        "load_base": 9000, "load_amplitude": 2000,
        "solar_cf": 0.11, "wind_cf": 0.25, "hydro_cf": 0.25,
        "gas_base": 3500, "coal_base": 200, "other_base": 500,
        "wind_offshore": 700,
    },
    "AT": {
        "load_base": 7000, "load_amplitude": 1500,
        "solar_cf": 0.13, "wind_cf": 0.20, "hydro_cf": 0.40,
        "gas_base": 2000, "coal_base": 500, "other_base": 500,
        "wind_offshore": 0,
    },
    "CH": {
        "load_base": 6000, "load_amplitude": 1200,
        "solar_cf": 0.12, "wind_cf": 0.10, "hydro_cf": 0.45,
        "gas_base": 200, "coal_base": 0, "other_base": 300,
        "wind_offshore": 0,
    },
}

CAPACITIES = {
    "IT": {"Solar": 32000,"Wind Onshore": 11800,"Wind Offshore": 0,"Hydro": 22000,"Nuclear": 0,"Gas": 46000,"Coal": 8000,"Other": 5000},
    "DE": {"Solar": 86000,"Wind Onshore": 61000,"Wind Offshore": 8000,"Hydro": 12000,"Nuclear": 0,"Gas": 37000,"Coal": 38000,"Other": 15000},
    "FR": {"Solar": 18000,"Wind Onshore": 22000,"Wind Offshore": 1500,"Hydro": 25000,"Nuclear": 61400,"Gas": 10000,"Coal": 3000,"Other": 3000},
    "ES": {"Solar": 28000,"Wind Onshore": 28000,"Wind Offshore": 0,"Hydro": 17000,"Nuclear": 7000,"Gas": 26000,"Coal": 5000,"Other": 4000},
    "PL": {"Solar": 15000,"Wind Onshore": 9000,"Wind Offshore": 0,"Hydro": 2000,"Nuclear": 0,"Gas": 14000,"Coal": 25000,"Other": 3000},
    "NL": {"Solar": 22000,"Wind Onshore": 6000,"Wind Offshore": 4500,"Hydro": 100,"Nuclear": 500,"Gas": 20000,"Coal": 5000,"Other": 3000},
    "BE": {"Solar": 9000,"Wind Onshore": 4000,"Wind Offshore": 2000,"Hydro": 1400,"Nuclear": 4000,"Gas": 9000,"Coal": 500,"Other": 1500},
    "AT": {"Solar": 5000,"Wind Onshore": 4000,"Wind Offshore": 0,"Hydro": 14000,"Nuclear": 0,"Gas": 5000,"Coal": 2000,"Other": 2000},
    "CH": {"Solar": 5000,"Wind Onshore": 100,"Wind Offshore": 0,"Hydro": 16000,"Nuclear": 3500,"Gas": 500,"Coal": 0,"Other": 1000},
}

def generate_hourly_data(cc, hours=HOURS):
    params = COUNTRY_PARAMS[cc]
    caps = CAPACITIES[cc]
    
    load = []
    solar_gen = []
    wind_onshore = []
    wind_offshore = []
    hydro = []
    gas = []
    coal = []
    other = []
    
    for h in range(hours):
        # Day of year (1-366) and hour of day (0-23)
        day = h // 24
        hour = h % 24
        
        # Seasonal factor (0 in winter, 1 in summer)
        season = 0.5 + 0.5 * math.sin(2 * math.pi * (day - 80) / 366)
        
        # Hourly factor (0 at night, 1 at midday)
        hour_factor = max(0, math.sin(math.pi * (hour - 6) / 12)) if 6 <= hour <= 18 else 0
        
        # Load: daily pattern with seasonal variation
        load_val = params["load_base"]
        load_val += params["load_amplitude"] * 0.3 * math.sin(2 * math.pi * hour / 24 - math.pi)
        load_val += params["load_amplitude"] * 0.15 * math.cos(2 * math.pi * (h % 168) / 168)  # weekly
        load_val += random.gauss(0, params["load_amplitude"] * 0.05)
        # Winter has higher load
        load_val += params["load_base"] * 0.15 * (1 - season)
        load.append(round(max(load_val * 0.5, load_val), 1))
        
        # Solar: only during daytime, peak at hour 12, seasonal
        solar_cf = params["solar_cf"] * hour_factor * (0.7 + 0.3 * season)
        solar_noise = random.uniform(0.85, 1.0)
        solar_val = caps["Solar"] * solar_cf * solar_noise
        solar_gen.append(round(solar_val, 1))
        
        # Wind: random with some seasonal and autocorrelation
        if h == 0:
            wind_base = params["wind_cf"]
        else:
            wind_base = 0.9 * wind_base + 0.1 * random.uniform(0.05, 0.45)
        wind_val = caps["Wind Onshore"] * wind_base * (0.9 + 0.2 * season)
        wind_onshore.append(round(wind_val, 1))
        
        # Wind offshore
        if h == 0:
            wo_base = 0.3
        else:
            wo_base = 0.9 * wo_base + 0.1 * random.uniform(0.1, 0.5)
        wo_val = caps["Wind Offshore"] * wo_base
        wind_offshore.append(round(wo_val, 1))
        
        # Hydro: higher in spring (snow melt), lower in winter
        hydro_season = 0.5 + 0.5 * math.sin(2 * math.pi * (day - 120) / 366)
        hydro_cf = params["hydro_cf"] * (0.7 + 0.3 * hydro_season)
        hydro_val = caps["Hydro"] * hydro_cf * (0.9 + 0.2 * random.random())
        hydro.append(round(hydro_val, 1))
        
        # Dispatchable: Gas, Coal, Other - fill the gap
        renew_total = solar_val + wind_val + wo_val + hydro_val
        remaining = load_val - renew_total
        
        if remaining > 0:
            gas_val = min(caps["Gas"], remaining * 0.6 + random.gauss(0, caps["Gas"] * 0.05))
            gas_val = max(0, gas_val)
            remaining -= gas_val
            
            coal_val = min(caps["Coal"], remaining * 0.5 + random.gauss(0, caps["Coal"] * 0.05))
            coal_val = max(0, coal_val)
            remaining -= coal_val
            
            other_val = max(0, remaining)
        else:
            gas_val = max(0, caps["Gas"] * 0.1 * random.uniform(0, 0.3))
            coal_val = 0
            other_val = 0
        
        gas.append(round(gas_val, 1))
        coal.append(round(coal_val, 1))
        other.append(round(other_val, 1))
    
    return {
        "country": cc,
        "year": 2024,
        "hours": hours,
        "sources": ["Solar", "Wind Onshore", "Wind Offshore", "Hydro", "Gas", "Coal", "Other"],
        "load": load,
        "generation": {
            "Solar": solar_gen,
            "Wind Onshore": wind_onshore,
            "Wind Offshore": wind_offshore,
            "Hydro": hydro,
            "Gas": gas,
            "Coal": coal,
            "Other": other,
        }
    }

if __name__ == "__main__":
    data_dir = os.path.join(os.path.dirname(__file__), "energy-scenarios", "data")
    os.makedirs(data_dir, exist_ok=True)
    
    for cc in COUNTRY_PARAMS:
        print(f"Generating data for {cc}...")
        data = generate_hourly_data(cc)
        path = os.path.join(data_dir, f"generation_{cc}_2024.json")
        with open(path, "w") as f:
            json.dump(data, f)
        print(f"  -> {path} ({len(data['load'])} hours)")
    
    print("\nDone! Generated mock data for all countries.")