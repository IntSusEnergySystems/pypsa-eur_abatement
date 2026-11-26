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
v0.16.0 costs for that year, weather year 2013, a 6 h time step, and one
node per country. The sector network is built once for that year and reused.
BAU then changes the fleet and the demand in memory. The mitigation runs
leave investment open and add a CO2 cap.

1. Solve `{year}-BAU`. No extra CO2 cap. Power capacity is fixed to the EU
   Reference Scenario 2020, further investment is switched off, and the
   country-sheet demand, generation and fuel limits below are applied.
2. Read the BAU `co2 atmosphere` store and write the absolute caps into
   `macc/scenarios/{year}.yaml`.
3. Solve `{year}-MACC_1` through `{year}-MACC_6`. These keep the PyPSA-Eur
   demand pathway for that year, may invest, and must stay under the cap.
4. After every scenario, write the study figures in `macc/postprocessing`.
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
- Electricity generation by source is an annual equality, in electric output.
  If the 2013 weather cannot reach the sheet, the target is cut back to the
  fleet and a warning is written.
- Solid fuel and oil supply are capped at the sum of the modelled countries'
  gross available energy. Gas and biomass are capped country by country.
- International maritime energy is written onto the `shipping oil` load.
  In 2025 the PyPSA shipping pathway is 100% oil, so that is the whole
  maritime fuel. From 2030 the pathway also builds a methanol share (15% in
  2030, then 35%, 55%, 80% and 100% in 2050). Hydrogen and LNG stay at zero.
  That methanol load is not rescaled to the sheet.

Population, the renovation rate, the renewable-energy shares and passenger
and freight activity are stored in that table. They are already contained in
the final-energy totals and the generation mix, so they are not applied
again. The sheet's own GHG emissions are not used: BAU has no extra CO2 cap,
and the mitigation caps are taken from the solved BAU emissions.

The model keeps the EU members this PyPSA-Eur build can represent and that
have a country sheet: AT, BE, BG, CZ, DE, DK, EE, ES, FI, FR, GR, HR, HU,
IE, IT, LT, LU, LV, NL, PL, PT, RO, SE, SI and SK. Greece is `EL` in the
workbook and `GR` in the model. Cyprus and Malta have sheets, but this model
has no network data for them. Countries without a sheet are not included.

## What is the same within a year

Weather year 2013, fuel prices, technology costs, efficiencies, administrative
clustering and the 6 h time step. Costs use technology-data v0.16.0 at the
planning year: 2025 costs for 2025, 2030 costs for 2030, and the same for the
later years. BAU demand, generation and fuel supply follow the country
sheets, and its fleet cannot grow. Mitigation runs keep the PyPSA-Eur demand
for that planning year, may invest, and add the CO2 cap.

## Figures

After each scenario finishes, and again at the end of the year,
`python -m macc.postprocessing` writes the study figures in
`macc/postprocessing/figures/`. Years that are not solved yet stay as empty
panels.

- Figure 1, `figure1_system_macc.png`: six panels, one system MACC per year,
  with negative and positive abatement costs.
- Figure 2, `figure2_technology_capacity.png` and
  `figure2_technology_generation.png`: installed capacity and annual
  generation across the abatement levels.
- Figure 3, `figure3_system_cost.png`: annualised investment, fixed operation,
  variable operation, fuel and any residual.
- Figure 4, `figure4_shadow_vs_macc.png`: the same six MACC panels with the
  CO2 shadow price of `CO2Limit-upper` at the middle of each step. The stored
  dual is negative; the plotted price is its opposite, in EUR/t.
- Figure 5, `figure5_bau_capacity_{year}.png`,
  `figure5_bau_generation_{year}.png`, `figure5_bau_final_energy_{year}.png`
  and `figure5_bau_primary_{year}.png`: each solved BAU divided by the EU
  reference value, for the capacities and the energy totals imposed on that
  run. The numbers are in `macc/postprocessing/tables/bau_vs_reference.csv`.

Fixed operation is the technology-data FOM share of annualised capital.
Fuel is the operating cost of the primary fuel generators. Variable
operation is the remaining operating cost.
