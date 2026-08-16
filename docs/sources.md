Here I keep track of the assumptions I have made and some explaination that can help a better understanding of the simulations.

**Solar Target Capacity**: TBD

**Wind Target Capacity** I've assumed 100GW, that is the amount of the wind farms currently under approval, according to [IEA](https://iea-wind.org/wp-content/uploads/2023/10/Italy_2022.pdf)

**Hydro** I've got data for three different Hydro power plants:
- *Rivers*: Not flexible;
- *Lakes*: Flaxible consumption, not flexible recharge;
- *Pumped*: Flexible consumption and recharge.

The order the power plants are exploited is the following:
1. Inflexible renewable generation (Solar, Wind, Geothermal, River-type-Hydro);
2. Pumped Hydro;
3. Lakes;
4. Storage;
5. Other sources.

In case of excess generation the model behaves as following:
1. The pumped hydro is recharged;
2. Other storage is recharged.
3. Curtailment.