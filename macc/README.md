# Overnight marginal abatement cost scenarios

This folder runs six independent overnight optimisations of the European
sector-coupled system. Each year is rebuilt on its own, with the demand and
sector pathway of that year and with technology costs frozen at 2025. Inside
one year, the only change from one solve to the next is the CO2 cap.

These are not a sequential transition. A 2050 system is not built on the
2030 investments. Existing plants and networks still enter each solve through
the model's usual overnight brownfield rules.

Run everything from the repository root:

```bash
pixi run macc
```

One planning year:

```bash
pixi run macc-year year=2030
```

The solver thread count in the config is 32. If this machine has fewer cores,
set `MACC_CORES` to a number at least that large before the pixi command, or
lower `solving.solver_options.gurobi-default.threads`.

## What pixi runs

`pixi run macc` calls `python -m macc.run_scenarios`. For each of 2025, 2030,
2035, 2040, 2045 and 2050 it does the following, and it does not start the
next scenario until the current one has finished.

1. `pixi run snakemake` for `{year}-REF` only. The default target is `all`,
   so this solves the network and then runs PyPSA-Eur's own post-processing:
   cost and energy summaries, balance time series, and the network and
   balance maps.
2. Read the reference atmosphere-store emissions and write an absolute CO2
   cap for every constrained scenario of that year.
3. `pixi run snakemake` again for `{year}-CO2_90`, then `CO2_80`, and so on
   down to `{year}-CO2_0`. Each call is a separate pixi job and includes the
   same PyPSA post-processing.
4. `pixi run snakemake macc_postprocess`. That rule depends on the PyPSA
   post-processing outputs, and only then runs `extract_results`,
   `compute_macc` and `plot_macc`.

Snakemake skips files that already exist, so stopping and running the same
command again continues with the first unfinished scenario. `--rerun-incomplete`
is set, so a scenario that stopped halfway is rebuilt.

Results of the solves are in `results/macc/{scenario}/`. The curve itself is
in `macc/results/`.

## Scenario names

There are 11 scenarios in each year and 66 solves in total. The number in the
name is the share of that year's own reference emissions that is still
allowed. It is not a reduction counted from 1990, and it is not a reduction
counted from 2025.

| Scenario | Allowed share of this year's reference | Reduction from this year's reference |
|---|---:|---:|
| `{year}-REF` | 100% | none, and no CO2 constraint |
| `{year}-CO2_90` | 90% | 10% |
| `{year}-CO2_80` | 80% | 20% |
| `{year}-CO2_70` | 70% | 30% |
| `{year}-CO2_60` | 60% | 40% |
| `{year}-CO2_50` | 50% | 50% |
| `{year}-CO2_40` | 40% | 60% |
| `{year}-CO2_30` | 30% | 70% |
| `{year}-CO2_20` | 20% | 80% |
| `{year}-CO2_10` | 10% | 90% |
| `{year}-CO2_0` | 0% | 100% |

PyPSA-Eur reads `planning_horizons` once, when the workflow is parsed, and a
scenario is not allowed to change it. Each year therefore has its own config,
`macc/config/config.{year}.yaml`, and its own scenario file,
`macc/scenarios/{year}.yaml`. The scenario file starts with the reference
only. `apply_reference_caps` adds the ten capped scenarios after the
reference network exists. Their caps cannot be known before that solve.

## What changes, and what does not

The sector and industry numbers are not copied into the scenario files. They
stay in `config/config.default.yaml`. The planning horizon selects the row
for that year, using the same lookup as the model (`scripts._helpers.get`):
an exact year is used when it is present. Every CO2 case in a year sees that
same row. A full dump of the values is in
`macc/pathways/exogenous_assumptions.csv`.

### Changes with the planning year

Road transport. The shares are exogenous. FCEV is 0 in every year. ICE is
what is left after the battery-electric share.

| | 2025 | 2030 | 2035 | 2040 | 2045 | 2050 |
|---|---:|---:|---:|---:|---:|---:|
| Battery electric | 0.05 | 0.20 | 0.45 | 0.70 | 0.85 | 1 |
| Internal combustion | 0.95 | 0.80 | 0.55 | 0.30 | 0.15 | 0 |

Shipping. Hydrogen and LNG are 0 in every year.

| | 2025 | 2030 | 2035 | 2040 | 2045 | 2050 |
|---|---:|---:|---:|---:|---:|---:|
| Oil | 1 | 0.85 | 0.65 | 0.45 | 0.20 | 0 |
| Methanol | 0 | 0.15 | 0.35 | 0.55 | 0.80 | 1 |

District heating. `sector.district_heating.progress` is the exogenous share
of the district-heating potential that is reached in that year: 0.10, 0.25,
0.40, 0.55, 0.75, 1.

Industry. Primary production is the virgin route. `DRI_fraction` is the share
of primary steel that uses direct reduced iron. `sector_ratios_fraction_future`
blends today's industrial energy ratios toward the future technology ratios.

| | 2025 | 2030 | 2035 | 2040 | 2045 | 2050 |
|---|---:|---:|---:|---:|---:|---:|
| Steel primary fraction | 0.55 | 0.50 | 0.45 | 0.40 | 0.35 | 0.30 |
| DRI fraction of primary steel | 0 | 0.05 | 0.20 | 0.40 | 0.70 | 1 |
| Aluminium primary fraction | 0.375 | 0.350 | 0.325 | 0.300 | 0.250 | 0.200 |
| HVC primary | 0.85 | 0.78 | 0.70 | 0.60 | 0.50 | 0.40 |
| HVC mechanical recycling | 0.15 | 0.18 | 0.21 | 0.24 | 0.27 | 0.30 |
| HVC chemical recycling | 0 | 0.04 | 0.08 | 0.12 | 0.16 | 0.20 |
| Industry future-ratio blend | 0.05 | 0.20 | 0.45 | 0.70 | 0.85 | 1 |

HVC primary plus recycling sums to 1 in 2025 and 2030, then to 0.99, 0.96,
0.93 and 0.90. The model scales virgin HVC by the primary fraction and adds
the recycling routes as fractions of today's HVC, so from 2035 onward total
HVC output is lower than today's output by that gap.
`HVC_environment_sequestration_fraction` is 0.

Annual CO2 sequestration potential follows the year table in the config:
0, 40, 100, 180, 250, 250. The sequestration cost stays at 30 per tonne.

### Same in every year and every CO2 case

| Item | Value |
|---|---|
| Foresight | overnight |
| Cost database | technology-data v0.16.0, `costs.year: 2025` |
| What that database fixes | investment cost, FOM, VOM, fuel cost, efficiency, lifetime, discount rate, CO2 intensity |
| Social discount rate | 0.02 |
| Technology discount-rate fill | 0.07 |
| CO2 price | off, and the price is 0 |
| Weather | 2013, cutout `europe-2013-sarah3-era5` |
| Time step | 6h averaging of the hourly year |
| Regions | 50 clusters, same country list as the default config |
| Historical energy totals | Eurostat year 2023 |
| Biomass potential | ENS_Med, biomass year 2030 |
| Vehicle and ship efficiencies | the scalar values in `config/config.default.yaml` |
| Agriculture machinery | 50% electric and 50% oil in every year |
| Aviation demand factor | 1 |
| Random cost noise | off, so neighbouring scenarios are not split by noise |

Efficiencies that are written next to the sectors, rather than in the cost
database, were checked. They are single numbers, not year tables, so they do
not move when the planning year changes. The generator refuses to run if a
year table whose name is an efficiency, investment cost, lifetime or
discount rate takes different values across 2025–2050.

### Chosen inside each solve

Heat pumps, gas boilers, oil boilers, biomass boilers and resistive heaters
do not have exogenous shares in this model. Their capacities are investment
decisions, so they are allowed to differ between CO2 caps. That difference
is an abatement response, not a scenario assumption. District-heating
progress is the exogenous heating pathway.

Building retrofit is also optimised. `reduce_space_heat_exogenously` is
false, so the year table `reduce_space_heat_exogenously_factor` is not used.
Residential heat demand-side management is disabled, so
`residential_heat.dsm.restriction_value` is not used either.

## CO2 constraint

The reference has `co2_budget.upper: null`. No cap is added.

For a capped scenario the allowance is a fraction of the reference emissions
of the same year:

\[
E_{y,\rho} = \rho \, E_y^{\mathrm{REF}}
\]

\(\rho\) is the allowed share: 0.9 for `CO2_90`, 0 for `CO2_0`. In the
illustrative numbers from the experiment design, a 2025 reference of
3500 Mt/year gives 2450 Mt at `CO2_70` (\(\rho = 0.7\)) and 1750 Mt at
`CO2_50`.

The solved reference emissions are the final level of the `co2 atmosphere`
store, divided by the number of years the snapshots represent:

\[
E_y^{\mathrm{REF}}
= \frac{e_{y,\mathrm{REF}}(t_{\mathrm{end}})}{n_y},
\qquad
n_y = \frac{1}{8760}\sum_t w_t
\]

\(e\) is in tonnes. With a full non-leap year, \(n_y = 1\). The 6h averaging
keeps the weights summing to the same year, so \(n_y\) stays 1.

`co2_budget.relative` is false. The value written into the scenario file is
the annual cap in Gt/year, rounded to the nearest tonne:

\[
\texttt{co2\_budget.upper}
= \mathrm{round}\!\left(\frac{\rho \, E_y^{\mathrm{REF}}}{10^9}\right)
\]

PyPSA-Eur then puts one upper global constraint on the atmosphere store,
named `CO2Limit-upper`. Its constant is the annual cap converted back to
tonnes and multiplied by \(n_y\):

\[
e(t_{\mathrm{end}}) \le \texttt{upper} \times 10^9 \times n_y
\]

There is no lower cap. International bunkers are not added to a 1990
baseline, because the cap is not a fraction of 1990 emissions. Shipping and
aviation fuel used inside the model still emits into the atmosphere store.

## Marginal abatement cost

Scenarios of one year are ordered from the reference to the tightest cap.
\(C\) is the annual system cost in EUR/year: annualised investment plus
operation, from the solved-network statistics. \(E\) is the annual
atmosphere-store emissions in tonnes/year, measured the same way as the
reference.

The marginal cost of moving from scenario \(i-1\) to the next tighter
scenario \(i\) is

\[
\mathrm{MAC}_{y,i}
= \frac{C_{y,i} - C_{y,i-1}}{E_{y,i-1} - E_{y,i}}
\]

The unit is EUR per tonne of CO2. The reference has no previous step, so it
has no marginal cost. If a step does not reduce emissions by at least one
tonne, the marginal cost is left empty rather than divided by zero.

The average cost of reaching scenario \(i\), measured from the reference of
the same year, is

\[
\mathrm{AAC}_{y,i}
= \frac{C_{y,i} - C_{y,\mathrm{REF}}}{E_{y,\mathrm{REF}} - E_{y,i}}
\]

A 2050 curve therefore prices abatement relative to the unconstrained 2050
system, not relative to 2025. Comparing `MAC` at the same \(\rho\) across
years shows how the cost of a given cut changes as the exogenous pathway
moves. Comparing the width of the cheap part of each curve shows whether
low-cost abatement grows or shrinks. The carrier table records the change in
annual capital cost, operating cost, capacity and energy balance on each
step, which shows which technologies take the low-cost and high-cost parts
of the curve.

## Files

| Path | Role |
|---|---|
| `macc/config/config.{year}.yaml` | One overnight workflow: horizon, frozen costs, 6h, 2013 weather |
| `macc/scenarios/{year}.yaml` | Reference, then the capped runs once the reference has been solved |
| `macc/scenario_matrix.csv` | All 66 names, allowed shares, and caps after they are known |
| `macc/pathways/` | Exogenous values actually selected for each year |
| `macc/run_scenarios.py` | Pixi sequence: reference, caps, each CO2 case, then MACC tables |
| `rules/macc.smk` | Snakemake rule that runs after PyPSA post-processing |
| `results/macc/{scenario}/` | Solved network and PyPSA plots for one scenario |
| `macc/results/scenario_summary.csv` | Annual cost and emissions of every finished scenario |
| `macc/results/macc.csv` | Marginal and average abatement costs |
| `macc/results/macc_by_reduction.csv` | The six years side by side at each reduction |
| `macc/results/macc_carrier_steps.csv` | Cost and capacity change by carrier on each step |
| `macc/results/figures/` | Curves and carrier-step charts |

Regenerate the configs and the pathway tables, without solving, with:

```bash
python -m macc.generate_scenarios
```

That command leaves a scenario file alone once it contains numeric CO2 caps.
Use `--force` only when those caps should be discarded and the file returned
to the reference alone.
