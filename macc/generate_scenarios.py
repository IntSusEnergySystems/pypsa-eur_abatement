# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""Write one overnight config per planning year and the 42-scenario matrix.

PyPSA-Eur builds collection targets from the top-level ``planning_horizons``,
and a scenario is not allowed to change that list. Each year is therefore its
own workflow. Costs, demand and the sector pathway follow that planning year.
Inside a year, weather, fuel prices, technology costs, efficiencies and
resolution are shared. BAU demand, generation and fuel supply follow the
country sheets. The mitigation runs keep the PyPSA-Eur demand pathway.

BAU has no extra CO2 cap. Its power capacities are fixed to the EU Reference
Scenario 2020 when the network is solved. The six mitigation runs may invest,
and their caps are fractions of that year's BAU emissions:

    E_{y,r} = E_{y,BAU} * (1 - r)

Those caps are written by ``apply_reference_caps`` after the BAU solve.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macc.bau_capacities import write_capacity_table  # noqa: E402
from macc.bau_pathway import write_balance_table  # noqa: E402
from macc.common import (  # noqa: E402
    CONFIG_DIR,
    COUNTRIES,
    CUTOUT,
    MACC_DIR,
    RESULTS_PREFIX,
    SCENARIO_DIR,
    STEPS,
    TECHNOLOGY_DATA_VERSION,
    TEMPORAL_RESOLUTION,
    WEATHER_YEAR,
    YEARS,
    config_path,
    dump_yaml,
    load_yaml,
    remaining_fraction,
    scenario_name,
    scenario_path,
)
from macc.export_pathways import export_pathways  # noqa: E402

CONFIG_TEMPLATE = """\
# Overnight MACC for planning year {year}.
# Demand and the sector pathway come from config/config.default.yaml.
# Technology costs are this planning year's costs. Weather stays {weather_year}.
# BAU is solved first. Its emissions set the CO2 caps of MACC_1..MACC_6.
#   pixi run macc-year year={year}
foresight: overnight
planning_horizons:
- {year}
countries:
{countries}
snapshots:
  start: "{weather_start}"
  end: "{weather_end}"
co2_budget:
  emissions_scope: CO2
  international_bunkers: false
  relative: false
  upper: null
  lower: null
costs:
  year: {year}
  emission_prices:
    enable: false
    co2: 0.0
sector:
  conventional_generation:
    OCGT: gas
    CCGT: gas
    coal: coal
    oil: oil
atlite:
  default_cutout: {cutout}
# One electricity node per country. Do not set n_clusters to "all":
# that skips administrative clustering.
clustering:
  mode: administrative
  administrative:
    level: 0
  temporal:
    averaging: {temporal}
    segmentation: false
    representative: false
solving:
  options:
    noisy_costs: false
    # LP files are large. /tmp is on the small root disk, so write them on /home.
    model_kwargs:
      solver_dir: resources/macc/solver-tmp
  solver_options:
    gurobi-default:
      threads: 8
macc:
  enable: true
  bau: false
data:
  costs:
    source: archive
    version: {technology_data_version}
run:
  prefix: {prefix}
  name: all
  scenarios:
    enable: true
    file: macc/scenarios/{year}.yaml
  shared_resources:
    policy: base
  default_target_rule: all
"""


def scenario_entry(reduction: float, upper=None) -> dict:
    return {
        "co2_budget": {
            "relative": False,
            "upper": upper,
            "lower": None,
        },
        "macc": {"bau": abs(reduction) < 1e-9},
    }


def scenario_file_has_caps(path: Path) -> bool:
    if not path.exists():
        return False
    data = load_yaml(path)
    for overrides in data.values():
        upper = overrides.get("co2_budget", {}).get("upper")
        if isinstance(upper, (int, float)):
            return True
    return False


def write_config(year: int) -> Path:
    start = f"{WEATHER_YEAR}-01-01 00:00"
    end = f"{WEATHER_YEAR}-12-31 23:00"
    countries = "\n".join(f"- {code}" for code in COUNTRIES)
    text = CONFIG_TEMPLATE.format(
        year=year,
        weather_year=WEATHER_YEAR,
        weather_start=start,
        weather_end=end,
        countries=countries,
        cutout=CUTOUT,
        temporal=TEMPORAL_RESOLUTION,
        technology_data_version=TECHNOLOGY_DATA_VERSION,
        prefix=RESULTS_PREFIX,
    )
    path = config_path(year)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_scenario_file(year: int, force: bool) -> Path:
    path = scenario_path(year)
    scenarios = {}
    for _label, reduction in STEPS:
        name = scenario_name(year, reduction)
        upper = None
        if path.exists() and not force:
            current = load_yaml(path).get(name, {})
            stored = current.get("co2_budget", {}).get("upper")
            if isinstance(stored, (int, float)):
                upper = stored
        scenarios[name] = scenario_entry(reduction, upper)
    dump_yaml(path, scenarios)
    return path


def write_matrix(path: Path, force: bool) -> pd.DataFrame:
    rows = []
    for year in YEARS:
        for _label, reduction in STEPS:
            rows.append(
                {
                    "year": year,
                    "scenario": scenario_name(year, reduction),
                    "reduction_fraction": reduction,
                    "remaining_fraction": remaining_fraction(reduction),
                    "co2_cap_gt_per_year": pd.NA,
                }
            )
    frame = pd.DataFrame(rows)
    if path.exists() and not force:
        previous = pd.read_csv(path)
        if "co2_cap_gt_per_year" in previous.columns:
            frame = frame.drop(columns=["co2_cap_gt_per_year"]).merge(
                previous[["scenario", "co2_cap_gt_per_year"]],
                on="scenario",
                how="left",
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame


def generate(force: bool = False) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SCENARIO_DIR.mkdir(parents=True, exist_ok=True)
    write_capacity_table()
    write_balance_table()
    assumptions_path, checks_path = export_pathways()
    for year in YEARS:
        write_config(year)
        write_scenario_file(year, force=force)
    matrix = write_matrix(MACC_DIR / "scenario_matrix.csv", force=force)
    print(f"Wrote {len(YEARS)} configs in {CONFIG_DIR.relative_to(MACC_DIR.parent)}")
    print(f"Wrote reference scenarios in {SCENARIO_DIR.relative_to(MACC_DIR.parent)}")
    print(f"Scenario matrix: {len(matrix)} runs -> macc/scenario_matrix.csv")
    print(f"Pathways: {assumptions_path.relative_to(MACC_DIR.parent)}")
    print(f"Share checks: {checks_path.relative_to(MACC_DIR.parent)}")
    print("Solve with: pixi run macc")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace scenario files even when CO2 caps have already been filled.",
    )
    args = parser.parse_args()
    generate(force=args.force)


if __name__ == "__main__":
    main()
