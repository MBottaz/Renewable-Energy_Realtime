Here I keep track of the assumptions I have made and some explaination that can help a better understanding of the simulations.

**Italy 2025 installed capacity**: Solar **43,512 MW** and wind **13,629 MW** (onshore + offshore combined). These values are maintained by hand because the ENTSO-E capacity data for Italy are unreliable for these technologies.

The remaining installed-capacity values are retained from the existing project snapshot.

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