# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""Build one marginal abatement cost curve for each planning year.

Scenarios are ordered from BAU to the tightest cap. The marginal cost of
step ``i`` is

    MAC_{y,i} = (C_{y,i} - C_{y,i-1}) / (E_{y,i-1} - E_{y,i})

in EUR per tonne. A step that costs less than the one before it is negative.
The average cost of a scenario is its extra system cost divided by its
abatement relative to that year's BAU.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macc.common import (  # noqa: E402
    RESULTS_DIR,
    marginal_abatement_cost,
)

SUMMARY_COLUMNS = [
    "capital_cost_eur_per_year",
    "marginal_cost_eur_per_year",
    "optimal_capacity",
    "energy_balance",
]


def _curve(summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for year, group in summary.groupby("year", sort=True):
        ordered = group.sort_values("remaining_fraction", ascending=False)
        reference = ordered.iloc[0]
        if not str(reference["scenario"]).endswith("-BAU"):
            raise SystemExit(f"{year} is missing its BAU scenario in the summary.")
        previous = None
        for _, current in ordered.iterrows():
            abatement = (
                reference["emissions_t_per_year"] - current["emissions_t_per_year"]
            )
            if previous is None:
                mac = np.nan
                step_abatement = np.nan
                previous_name = ""
            else:
                step_abatement = (
                    previous["emissions_t_per_year"] - current["emissions_t_per_year"]
                )
                mac = marginal_abatement_cost(
                    current["system_cost_eur_per_year"],
                    previous["system_cost_eur_per_year"],
                    current["emissions_t_per_year"],
                    previous["emissions_t_per_year"],
                )
                previous_name = previous["scenario"]
            average = np.nan
            if abatement > 1.0:
                average = (
                    current["system_cost_eur_per_year"]
                    - reference["system_cost_eur_per_year"]
                ) / abatement
            rows.append(
                {
                    "year": int(year),
                    "scenario": current["scenario"],
                    "previous_scenario": previous_name,
                    "remaining_fraction": current["remaining_fraction"],
                    "reduction_fraction": current["reduction_fraction"],
                    "system_cost_eur_per_year": current["system_cost_eur_per_year"],
                    "emissions_t_per_year": current["emissions_t_per_year"],
                    "emissions_mt_per_year": current["emissions_mt_per_year"],
                    "cumulative_abatement_t_per_year": abatement,
                    "cumulative_abatement_mt_per_year": abatement / 1e6,
                    "step_abatement_t_per_year": step_abatement,
                    "mac_eur_per_t": mac,
                    "average_abatement_cost_eur_per_t": average,
                    "cost_increase_eur_per_year": (
                        current["system_cost_eur_per_year"]
                        - reference["system_cost_eur_per_year"]
                    ),
                }
            )
            previous = current
    return pd.DataFrame(rows)


def _comparison(curve: pd.DataFrame) -> pd.DataFrame:
    """Place the six years side by side at each reduction step."""
    pieces = []
    for column, label in (
        ("mac_eur_per_t", "mac_eur_per_t"),
        ("average_abatement_cost_eur_per_t", "average_abatement_cost_eur_per_t"),
        ("system_cost_eur_per_year", "system_cost_eur_per_year"),
        ("emissions_mt_per_year", "emissions_mt_per_year"),
        ("cumulative_abatement_mt_per_year", "cumulative_abatement_mt_per_year"),
    ):
        wide = curve.pivot(index="reduction_fraction", columns="year", values=column)
        wide.columns = [f"{label}_{int(year)}" for year in wide.columns]
        pieces.append(wide)
    return pd.concat(pieces, axis=1).reset_index()


def _carrier_steps(curve: pd.DataFrame, carriers: pd.DataFrame) -> pd.DataFrame:
    indexed = carriers.set_index(["scenario", "carrier"])
    rows = []
    steps = curve.loc[curve["previous_scenario"] != ""]
    for step in steps.itertuples(index=False):
        current = indexed.loc[step.scenario]
        previous = indexed.loc[step.previous_scenario]
        aligned = current[SUMMARY_COLUMNS].subtract(
            previous[SUMMARY_COLUMNS], fill_value=0.0
        )
        aligned = aligned.reset_index()
        aligned.insert(0, "year", step.year)
        aligned.insert(1, "scenario", step.scenario)
        aligned.insert(2, "previous_scenario", step.previous_scenario)
        aligned.insert(3, "mac_eur_per_t", step.mac_eur_per_t)
        rows.append(aligned)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def compute() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summary_path = RESULTS_DIR / "scenario_summary.csv"
    carrier_path = RESULTS_DIR / "carrier_summary.csv"
    if not summary_path.exists() or not carrier_path.exists():
        raise SystemExit("Run python -m macc.extract_results before computing MACCs.")
    summary = pd.read_csv(summary_path)
    carriers = pd.read_csv(carrier_path)
    curve = _curve(summary)
    comparison = _comparison(curve)
    carrier_steps = _carrier_steps(curve, carriers)
    curve_path = RESULTS_DIR / "macc.csv"
    comparison_path = RESULTS_DIR / "macc_by_reduction.csv"
    carriers_path = RESULTS_DIR / "macc_carrier_steps.csv"
    curve.to_csv(curve_path, index=False)
    comparison.to_csv(comparison_path, index=False)
    carrier_steps.to_csv(carriers_path, index=False)
    print(f"Wrote {curve_path}")
    print(f"Wrote {comparison_path}")
    print(f"Wrote {carriers_path}")
    return curve, comparison, carrier_steps


def main() -> None:
    compute()


if __name__ == "__main__":
    main()
