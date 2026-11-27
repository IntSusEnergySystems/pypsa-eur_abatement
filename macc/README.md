# Overnight marginal abatement cost scenarios

Six planning years, each solved as its own overnight run. A year cannot share
a workflow with another year, because PyPSA-Eur builds the network from one
`planning_horizons` list. There are 7 scenarios per year and 42 solves.

From the repository root:

```bash
pixi run macc-year year=2025
```

All six years, in order:

```bash
pixi run macc
```

Gurobi uses 8 threads. `MACC_CORES` must be at least 8. Run one year at a
time if a solve for that year is already going.

## How one planning year is solved

`macc/config/config.{year}.yaml` sets the planning year, technology-data
v0.16.0 costs and efficiencies from the 2025 cost file, weather year 2013, a 6 h time step, and one
node per country. The sector network is built once for that year and reused.
BAU then changes the fleet and the demand in memory. The mitigation runs
leave investment open and add a CO2 cap. BAU industry uses today's specific
energy consumption and fuel mix in every year
(`sector_ratios_fraction_future` is 0 in every year). The mitigation runs keep the default
path, from 0.05 in 2025 to 1 in 2050.

1. Solve `{year}-BAU`. No extra CO2 cap. Power capacity is fixed to the EU
   Reference Scenario 2020, further investment is switched off, and the
   country-sheet demand below is applied. Generation is not capped.
2. Read the BAU `co2 atmosphere` store and write the absolute caps into
   `macc/scenarios/{year}.yaml`.
3. Solve `{year}-MACC_1` through `{year}-MACC_6`. These keep the PyPSA-Eur
   demand pathway for that year, may invest, and must stay under the cap.
4. After every scenario, refresh the study figures in `macc/postprocessing`.
   The EU reference and BAU are drawn as soon as that year's BAU exists, and
   each finished mitigation scenario adds a bar. A run costing more than
   five times BAU is left out.
5. Run `macc_postprocess` once the year's own PyPSA plots exist.

Snakemake skips files that already exist. `--rerun-incomplete` rebuilds a
scenario that stopped halfway. Mitigation demand is the PyPSA-Eur pathway,
so a MACC is the extra cost of leaving the reference fleet and meeting a
tighter cap, not a comparison of two different demand datasets.

## Scenarios

The reduction is from that year's own BAU emissions, not from 1990 and not
from another year.

| Scenario | Reduction from this year's BAU | CO2 cap |
|---|---:|---|
| `{year}-BAU` | none | no additional CO2 constraint |
| `{year}-MACC_1` | 10% | 90% of BAU emissions |
| `{year}-MACC_2` | 20% | 80% of BAU emissions |
| `{year}-MACC_3` | 40% | 60% of BAU emissions |
| `{year}-MACC_4` | 60% | 40% of BAU emissions |
| `{year}-MACC_5` | 80% | 20% of BAU emissions |
| `{year}-MACC_6` | 100% | zero, when the solve is feasible |

`E` is the final level of the `co2 atmosphere` store, divided by the number of
represented years. The cap is that quantity. It equals the cap only when the
constraint is binding.

```
E_{y,r} = E_{y,BAU} * (1 - r)
MAC_{y,i} = (C_{y,i} - C_{y,i-1}) / (E_{y,i-1} - E_{y,i})
```

`C` is the annual system cost, capital plus operation. A step that is cheaper
than the previous one has a negative marginal cost. `MACC_6` is kept even
though a zero cap may be infeasible.

## BAU fleet

BAU capacities come from the EU Reference Scenario 2020 workbook
`macc/data/ref2020_energy-transport-ghg.xlsx` (main results on energy,
transport and GHG emissions). The country sheets supply net installed power
in MW for nuclear, biomass, hydro, wind, solar, geothermal, coal, oil, gas
and hydrogen. `python -m macc.generate_scenarios` writes them to
`macc/data/ref2020_power_capacity.csv`.

On the BAU solve those capacities replace the optimised fleet, and further
investment in plants, storage, new carriers and the grid is switched off.
The mitigation solves use the same network with investment left open, plus
the CO2 cap. Coal and oil power are added as extendable plants so a
mitigation run can change them. Biomass power is the model's district-heating
CHP. BAU sets each of these to the reference capacity.

The same solve also reads the rest of each country sheet, except GHG, GDP and
imports. `python -m macc.generate_scenarios` writes the kept rows to
`macc/data/ref2020_country_balances.csv`.

BAU uses them as follows.

- Industry, residential plus tertiary, and domestic road transport are scaled
  to the sheet's final-energy totals. Residential and tertiary are one
  buildings group because the model stores useful heat, not fuel input.
  International aviation kerosene and international maritime fuel come from
  the bunker rows on each country's `_B` sheet. Their sum is the sheet's
  international-bunker energy. The domestic transport total excludes those
  bunkers, so they are applied on their own loads.
- Road electricity and oil are then split by the sheet's electricity share
  in road transport.
- Supply-side generation is limited by the reference capacities only. Annual
  electricity output is not capped. Unsustainable biomass, biogas and
  bioliquids stay available up to their potentials, but BAU does not force
  those potentials to be used.   Coal and primary oil stay available at their
  fuel price: those generators are the fuel market, not power plants.
- Ammonia and methanol demand are turned off in BAU. Haber-Bosch and
  methanolisation stay at their current capacity.
- Load shedding is enabled in every scenario. A bus can leave demand unmet at
  the default penalty of 100 000 EUR per unit, which is only used when no
  feasible supply remains.
- International maritime energy is written onto the `shipping oil` load in
  every year. BAU has no methanol, hydrogen or LNG share of shipping. The
  mitigation runs keep the default pathway: oil only in 2025, then 15%
  methanol in 2030, 35% in 2035, 55% in 2040, 80% in 2045 and 100% in 2050.

Population, the renovation rate, the renewable-energy shares and passenger
and freight activity are stored in that table. They are already contained in
the final-energy totals and the generation mix, so they are not applied
again. The sheet's own GHG emissions are not used: BAU has no extra CO2 cap,
and the mitigation caps are taken from the solved BAU emissions.

The model keeps the EU members this PyPSA-Eur build can represent and that
have a country sheet: AT, BE, BG, CZ, DE, DK, EE, ES, FI, FR, GR, HR, HU,
IT, LT, LU, LV, NL, PL, PT, RO, SE, SI and SK. Greece is `EL` in the
workbook and `GR` in the model. Ireland is left out because, without Great
Britain, its land and sea area is disconnected from the modelled region.
Cyprus and Malta have sheets, but this model has no network data for them.
Countries without a sheet are not included.

## What is the same within a year

Weather year 2013, fuel prices, technology costs, efficiencies, administrative
clustering and the 6 h time step. Every planning year uses technology-data
v0.16.0 for 2025, so investment costs, fuel prices and efficiencies do not
change between 2025 and 2050. BAU demand follows the country sheets. Its supply-side fleet
cannot grow, and that fleet's annual generation is not capped. Mitigation
runs keep the PyPSA-Eur demand
for that planning year, may invest, and add the CO2 cap.

## Figures

After each scenario finishes, `python -m macc.postprocessing` rewrites the
study figures in `macc/postprocessing/figures/`. A year appears once its BAU
is solved. The EU reference sheet is the first bar. Each finished mitigation
scenario adds a bar to that year's figure. A scenario whose annual cost is
more than five times that year's BAU is left out. The numbers are in
`macc/postprocessing/tables/scenario_comparison.csv`.

- Figure 1, `figure1_supply_{year}.png`: capacity, electricity generation and
  CO2. The reference bars are the EU sheet. Model CO2 is what the solved
  network adds to the atmosphere.
- Figure 2, `figure2_consumption_{year}.png`: final energy for industry,
  residential and tertiary, transport, international aviation and
  international maritime. Maritime includes every shipping fuel.
- Figure 9, `figure9_bau_reference_{year}.png`: the same capacity,
  electricity generation, CO2 and final energy as Figures 1 and 2, drawn
  only for the EU reference and BAU.
- Figure 3, `figure3_macc_shadow_{year}.png`: the marginal abatement cost of
  each mitigation strategy and the CO2 shadow price of `CO2Limit-upper`. The
  stored dual is negative; the plotted price is its opposite, in EUR/t.
- Figure 4, `figure4_technology_{year}.png`: installed capacity, electricity
  generation, fossil fuel use, electrolyser capacity, storage capacity,
  annual investment, and fuel plus operating cost, against the CO2 reduction
  from BAU.
- Figure 5, `figure5_macc_emissions_{year}.png`: change in annual investment
  of each technology relative to BAU. Extra investment is drawn above the
  axis and lower investment below it.
- Figure 6, `figure6_system_cost_{year}.png`: total annual system cost of
  BAU and each mitigation strategy.
- Figure 7, `figure7_technology_macc_{year}.png`: emissions and investment
  along the marginal abatement cost. The x-axis is the MACC of each step
  from one scenario to the next, `(C_i - C_{i-1}) / (E_{i-1} - E_i)`. The
  left axis is total CO2 emissions. The coloured bands are the technologies
  that deliver the reduction from that year's BAU, so the bottom of the
  bands is the scenario's emissions. The right axis is the change in annual
  investment compared with BAU. A planning year is drawn once its BAU and
  mitigation scenarios are solved.
- Figure 8, `figure8_operating_macc_{year}.png`: the same emissions chart.
  The right axis is the change in annual operating cost, fuel plus variable
  operation, compared with BAU. A lower operating bill is below zero.
