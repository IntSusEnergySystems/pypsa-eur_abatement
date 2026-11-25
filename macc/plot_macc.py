# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""Plot the six marginal abatement cost curves and the carrier cost steps."""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macc.common import RESULTS_DIR  # noqa: E402

TOP_CARRIERS = 8


def _steps(curve: pd.DataFrame, year: int) -> pd.DataFrame:
    steps = curve.loc[
        (curve["year"] == year) & curve["mac_eur_per_t"].notna()
    ].sort_values("cumulative_abatement_mt_per_year")
    return steps


def plot_curves(curve: pd.DataFrame, figure_dir: Path) -> None:
    figure, axis = plt.subplots(figsize=(8, 5))
    for year, group in curve.groupby("year"):
        steps = _steps(curve, int(year))
        if steps.empty:
            continue
        abatement = [0.0, *steps["cumulative_abatement_mt_per_year"].tolist()]
        costs = [steps["mac_eur_per_t"].iloc[0], *steps["mac_eur_per_t"].tolist()]
        axis.step(abatement, costs, where="pre", label=str(int(year)))
    axis.set_xlabel("Abatement from that year's reference (Mt CO2/year)")
    axis.set_ylabel("Marginal abatement cost (EUR/t)")
    axis.legend(title="Planning year")
    axis.grid(True, linewidth=0.3)
    figure.tight_layout()
    figure.savefig(figure_dir / "macc_vs_abatement.png", dpi=150)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(8, 5))
    for year, group in curve.groupby("year"):
        ordered = group.sort_values("reduction_fraction")
        axis.plot(
            ordered["reduction_fraction"] * 100,
            ordered["mac_eur_per_t"],
            marker="o",
            label=str(int(year)),
        )
    axis.set_xlabel("Emissions reduction from that year's reference (%)")
    axis.set_ylabel("Marginal abatement cost (EUR/t)")
    axis.legend(title="Planning year")
    axis.grid(True, linewidth=0.3)
    figure.tight_layout()
    figure.savefig(figure_dir / "macc_vs_reduction.png", dpi=150)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(8, 5))
    for year, group in curve.groupby("year"):
        ordered = group.sort_values("reduction_fraction")
        axis.plot(
            ordered["reduction_fraction"] * 100,
            ordered["system_cost_eur_per_year"] / 1e9,
            marker="o",
            label=str(int(year)),
        )
    axis.set_xlabel("Emissions reduction from that year's reference (%)")
    axis.set_ylabel("Annual system cost (billion EUR/year)")
    axis.legend(title="Planning year")
    axis.grid(True, linewidth=0.3)
    figure.tight_layout()
    figure.savefig(figure_dir / "system_cost_vs_reduction.png", dpi=150)
    plt.close(figure)


def plot_carriers(steps: pd.DataFrame, figure_dir: Path) -> None:
    if steps.empty:
        return
    cost = "capital_cost_eur_per_year"
    marginal = "marginal_cost_eur_per_year"
    steps = steps.copy()
    steps["annual_cost_delta"] = steps[cost].fillna(0) + steps[marginal].fillna(0)
    for year, group in steps.groupby("year"):
        totals = (
            group.groupby("carrier")["annual_cost_delta"].apply(lambda s: s.abs().sum())
        )
        keep = set(totals.nlargest(TOP_CARRIERS).index)
        plot_frame = group.copy()
        plot_frame["carrier"] = plot_frame["carrier"].where(
            plot_frame["carrier"].isin(keep), "other"
        )
        pivot = plot_frame.pivot_table(
            index="scenario",
            columns="carrier",
            values="annual_cost_delta",
            aggfunc="sum",
        ).fillna(0.0)
        order = (
            group[["scenario", "remaining_fraction"]]
            .drop_duplicates()
            .sort_values("remaining_fraction", ascending=False)["scenario"]
        )
        pivot = pivot.reindex(order)
        figure, axis = plt.subplots(figsize=(10, 5))
        pivot.div(1e9).plot.bar(stacked=True, ax=axis, width=0.8)
        axis.set_xlabel("")
        axis.set_ylabel("Change in annual cost from the previous step (billion EUR/year)")
        axis.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=8)
        axis.grid(True, axis="y", linewidth=0.3)
        figure.tight_layout()
        figure.savefig(figure_dir / f"carrier_cost_steps_{int(year)}.png", dpi=150)
        plt.close(figure)


def main() -> None:
    curve_path = RESULTS_DIR / "macc.csv"
    steps_path = RESULTS_DIR / "macc_carrier_steps.csv"
    if not curve_path.exists():
        raise SystemExit("Run python -m macc.compute_macc before plotting.")
    figure_dir = RESULTS_DIR / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    curve = pd.read_csv(curve_path)
    plot_curves(curve, figure_dir)
    if steps_path.exists():
        plot_carriers(pd.read_csv(steps_path), figure_dir)
    print(f"Wrote figures in {figure_dir}")


if __name__ == "__main__":
    main()
