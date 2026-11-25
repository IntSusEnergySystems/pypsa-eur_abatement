# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""Fill absolute CO2 caps from each year's solved reference network.

The reference is unconstrained. Its annual atmosphere-store emissions are
``E_y^REF``. A constrained scenario then receives

    co2_budget.upper = E_y^REF * remaining

in Gt/year, with ``relative: false``. ``CO2_90`` uses remaining 0.9.
Re-running this script recomputes the caps from the reference networks.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macc.common import (  # noqa: E402
    EMISSION_TOLERANCE_T,
    MACC_DIR,
    REMAINING,
    RESULTS_DIR,
    TONNES_PER_GT,
    YEARS,
    dump_yaml,
    load_yaml,
    parse_scenario_name,
    scenario_name,
    scenario_path,
    solved_network_path,
    tonnes_to_gt_per_year,
)
from macc.extract_results import annual_co2_tonnes  # noqa: E402


def cap_gt(reference_tonnes: float, remaining: float) -> float:
    """Annual cap in Gt, rounded to the nearest tonne."""
    tonnes = reference_tonnes * remaining
    if abs(tonnes) < EMISSION_TOLERANCE_T:
        return 0.0
    return round(tonnes / TONNES_PER_GT, 9)


def co2_override(upper) -> dict:
    return {
        "co2_budget": {
            "relative": False,
            "upper": upper,
            "lower": None,
        }
    }


def apply_year(year: int) -> dict:
    reference = scenario_name(year, 1.0)
    network = solved_network_path(reference)
    if not network.exists():
        raise SystemExit(
            f"Missing reference network {network}. Solve {reference} before "
            "setting the CO2 caps."
        )
    import pypsa

    solved = pypsa.Network(network)
    reference_tonnes, nyears = annual_co2_tonnes(solved)
    scenarios = {reference: co2_override(None)}
    caps = []
    for remaining in REMAINING:
        name = scenario_name(year, remaining)
        if remaining == 1.0:
            upper = None
        else:
            upper = cap_gt(reference_tonnes, remaining)
            if upper < 0:
                raise SystemExit(
                    f"{reference} emissions are negative ({reference_tonnes} t). "
                    "The reduction formula E*(1-r) is defined for a positive "
                    "reference."
                )
        scenarios[name] = co2_override(None if remaining == 1.0 else upper)
        caps.append(
            {
                "year": year,
                "scenario": name,
                "remaining_fraction": remaining,
                "co2_cap_gt_per_year": upper,
            }
        )
    # REF stays first and keeps a null cap. The loop above rewrites it; the
    # insertion order still starts at REF because REMAINING starts at 1.
    dump_yaml(scenario_path(year), scenarios)
    return {
        "year": year,
        "reference_emissions_t_per_year": reference_tonnes,
        "reference_emissions_gt_per_year": tonnes_to_gt_per_year(reference_tonnes),
        "nyears": nyears,
        "caps": caps,
    }


def update_matrix(applied: list[dict]) -> None:
    matrix_path = MACC_DIR / "scenario_matrix.csv"
    matrix = pd.read_csv(matrix_path)
    updates = pd.DataFrame(row for item in applied for row in item["caps"])
    merged = matrix.merge(
        updates[["scenario", "co2_cap_gt_per_year"]],
        on="scenario",
        how="left",
        suffixes=("", "_new"),
    )
    merged["co2_cap_gt_per_year"] = merged["co2_cap_gt_per_year_new"].combine_first(
        merged["co2_cap_gt_per_year"]
    )
    merged = merged.drop(columns=["co2_cap_gt_per_year_new"])
    merged.to_csv(matrix_path, index=False)


def publish(applied: list[dict]) -> None:
    """Store reference emissions and write the caps into the scenario matrix."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame(
        [
            {
                "year": item["year"],
                "reference_emissions_t_per_year": item["reference_emissions_t_per_year"],
                "reference_emissions_gt_per_year": item[
                    "reference_emissions_gt_per_year"
                ],
                "nyears": item["nyears"],
            }
            for item in applied
        ]
    )
    summary_path = RESULTS_DIR / "reference_emissions.csv"
    if summary_path.exists():
        previous = pd.read_csv(summary_path)
        summary = pd.concat(
            [previous.loc[~previous["year"].isin(summary["year"])], summary],
            ignore_index=True,
        ).sort_values("year")
    summary.to_csv(summary_path, index=False)
    if (MACC_DIR / "scenario_matrix.csv").exists():
        update_matrix(applied)
    for item in applied:
        tonnes = item["reference_emissions_t_per_year"]
        print(
            f"{item['year']}: reference emissions "
            f"{tonnes / 1e6:.3f} Mt/year, wrote {scenario_path(item['year']).name}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--year",
        type=int,
        action="append",
        choices=YEARS,
        help="Planning year to update. Repeat for several years. Default: all.",
    )
    args = parser.parse_args()
    years = args.year or YEARS
    applied = []
    skipped = []
    for year in years:
        network = solved_network_path(scenario_name(year, 1.0))
        if args.year is None and not network.exists():
            skipped.append(year)
            continue
        applied.append(apply_year(year))
    if not applied:
        raise SystemExit(
            "No reference networks found under results/macc/. Solve a "
            "reference scenario first."
        )
    publish(applied)
    if skipped:
        print("Skipped years without a reference network: " + ", ".join(map(str, skipped)))
    # Touch parse so a renamed scenario cannot drift from the matrix silently.
    for item in applied:
        for row in item["caps"]:
            parsed_year, _remaining = parse_scenario_name(row["scenario"])
            if parsed_year != item["year"]:
                raise SystemExit(f"Scenario name {row['scenario']} has the wrong year.")
    written = load_yaml(scenario_path(applied[-1]["year"]))
    print(f"Scenarios in {applied[-1]['year']}: {', '.join(written)}")


if __name__ == "__main__":
    main()
