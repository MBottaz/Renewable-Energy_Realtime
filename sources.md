# Fonti e Assunzioni

## ENTSO-E Transparency Platform

I dati provengono da ENTSO-E, la piattaforma europea di trasparenza energetica.
API: https://transparency.entsoe.eu/

## Categorie semplificate

Il frontend usa 8 categorie raggruppate dai codici ENTSO-E:

| Categoria | Codici ENTSO-E | Rinnovabile |
|-----------|----------------|-------------|
| Solar | B16 | ✅ |
| Wind Onshore | B19 | ✅ |
| Wind Offshore | B18 | ✅ |
| Hydro | B10, B11, B12 | ✅ |
| Nuclear | B14 | ❌ (neutro) |
| Gas | B04 | ❌ |
| Coal | B02, B03, B05 | ❌ |
| Other | B01, B06-B09, B13, B15, B17, B20 | ❌ |

## Scenario scaling

Quando l'utente modifica la capacità scenario per una fonte:
  gen_scaled[h] = gen_originale[h] × (capacità_scenario / capacità_attuale)

Questo avviene lato client (JavaScript), senza modificare i dati caricati.
