## Goal of the project
The goal of this project is deploying a completely static website that enables user to: 
- query the entsoe public api about produced energy by source;
- get as input an installed power capacity target for each energy source;
- scale the energy production of each flexible source by the ratio between the target and the actual installed capacity;
    - the inflexible sources get scaled up;
    - the 
- Run a simulation of the energy system matching demand with production of all those sources.
- display a plot and some stats regarding the new simulation.

## Phases
Let's proceed for steps, developing a simple MVP and enhancing its capabilites time by time. 
A possible path could be:
- Entsoe API call setup and data handling;
- Simple static site just displaying a plot of the current scenario and a couple of empty textbox that can be used as input for the target capacity, precompiled at the current capacity.
- Scale inflexible production;
- Simulation;
- Result handling;
