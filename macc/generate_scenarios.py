# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""Write one overnight config per planning year and the scenario matrix.

PyPSA-Eur builds collection targets from the top-level ``planning_horizons``,
and a scenario is not allowed to change that list. Each year is therefore its
own workflow. Inside a year the only difference between runs is the CO2 cap.

The scenario files written here contain the reference only. Constrained runs
are added by ``apply_reference_caps`` once that year's reference emissions
are known, because each cap is a fraction of its own reference:

    E_{y,r} = E_y^{REF} * remaining

``CO2_90`` allows 90% of the reference emissions (a 10% reduction). ``CO2_0``
allows none. Ten allowances plus the reference, for six years, make 66 solves.

Sector and industry pathways are not copied here. They stay in
``config/config.default.yaml`` and the planning horizon selects the year.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macc.common import (  # noqa: E402
    CONFIG_DIR,
    COST_YEAR,
    CUTOUT,
    MACC_DIR,
    N_CLUSTERS,
    REMAINING,
    RESULTS_PREFIX,
    SCENARIO_DIR,
    TECHNOLOGY_DATA_VERSION,
    TEMPORAL_RESOLUTION,
    WEATHER_YEAR,
    YEARS,
    config_path,
    dump_yaml,
    load_yaml,
    reduction_fraction,
    scenario_name,
    scenario_path,
)
from macc.export_pathways import export_pathways  # noqa: E402

CONFIG_TEMPLATE = """\
# Overnight MACC for planning year {year}.
# Sector and industry pathways are taken from config/config.default.yaml.
# This file freezes costs, weather, spatial resolution and the 6h time step.
#
# Solve this year with pixi. The reference is solved first, its emissions
# set the CO2 caps, and each capped scenario is then solved on its own.
# PyPSA post-processing runs for every scenario. The MACC tables run after that.
#   pixi run macc-year year={year}
# All six years:
#   pixi run macc
foresight: overnight
planning_horizons:
- {year}
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
  year: {cost_year}
  emission_prices:
    enable: false
    co2: 0.0
atlite:
  default_cutout: {cutout}
clustering:
  cluster_network:
    n_clusters: {n_clusters}
  temporal:
    averaging: {temporal}
    segmentation: false
    representative: false
solving:
  options:
    noisy_costs: false
macc:
  enable: true
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


def reference_scenario() -> dict:
    return {
        "co2_budget": {
            "relative": False,
            "upper": None,
            "lower": None,
        }
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
    text = CONFIG_TEMPLATE.format(
        year=year,
        weather_start=start,
        weather_end=end,
        cost_year=COST_YEAR,
        cutout=CUTOUT,
        n_clusters=N_CLUSTERS,
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
    if path.exists() and scenario_file_has_caps(path) and not force:
        print(
            f"Keeping {path.relative_to(MACC_DIR.parent)} because it already "
            "contains CO2 caps. Pass --force to reset it to the reference only."
        )
        return path
    name = scenario_name(year, 1.0)
    dump_yaml(path, {name: reference_scenario()})
    return path


def write_matrix(path: Path, force: bool) -> pd.DataFrame:
    rows = []
    for year in YEARS:
        for remaining in REMAINING:
            rows.append(
                {
                    "year": year,
                    "scenario": scenario_name(year, remaining),
                    "remaining_fraction": round(remaining, 10),
                    "reduction_fraction": round(reduction_fraction(remaining), 10),
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
