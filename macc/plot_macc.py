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

from macc.common import RESULTS_DIR, parse_scenario_name, solved_network_path  # noqa: E402

TOP_CARRIERS = 8


def _steps(curve: pd.DataFrame, year: int) -> pd.DataFrame:
    steps = curve.loc[
        (curve["year"] == year) & curve["mac_eur_per_t"].notna()
    ].sort_values("cumulative_abatement_mt_per_year")
    return steps


def _bar_macc(axis, steps: pd.DataFrame) -> None:
    ordered = steps.sort_values("cumulative_abatement_mt_per_year")
    previous = 0.0
    for row in ordered.itertuples(index=False):
        width = row.cumulative_abatement_mt_per_year - previous
        axis.bar(
            previous,
            row.mac_eur_per_t,
            width=width,
            align="edge",
            color="#2f6fad",
            edgecolor="white",
            linewidth=0.4,
        )
        previous = row.cumulative_abatement_mt_per_year
    axis.axhline(0.0, color="black", linewidth=0.6)
    axis.grid(True, axis="y", linewidth=0.3)


def plot_curves(curve: pd.DataFrame, figure_dir: Path) -> None:
    """Six panels, one system MACC per planning year."""
    years = sorted(int(year) for year in curve["year"].unique())
    figure, axes = plt.subplots(2, 3, figsize=(14, 8), sharey=False)
    for axis, year in zip(axes.ravel(), years, strict=False):
        steps = _steps(curve, year)
        axis.set_title(str(year))
        if steps.empty:
            continue
        _bar_macc(axis, steps)
        axis.set_xlim(left=0)
    for axis in axes[1]:
        axis.set_xlabel("Abatement from BAU (Mt CO2/year)")
    for axis in axes[:, 0]:
        axis.set_ylabel("MAC (EUR/t CO2)")
    figure.tight_layout()
    figure.savefig(figure_dir / "macc_panels.png", dpi=150)
    plt.close(figure)


TECHNOLOGY_GROUPS = {
    "Solar": ["solar", "solar rooftop", "solar-hsat"],
    "Onshore wind": ["onwind"],
    "Offshore wind": ["offwind-ac", "offwind-dc", "offwind-float"],
    "Nuclear": ["nuclear"],
    "Gas": ["CCGT", "OCGT"],
    "Coal": ["coal"],
    "Hydro": ["ror", "hydro"],
    "Battery": ["battery"],
    "Electrolysis": ["H2 Electrolysis"],
    "Hydrogen storage": ["H2 Store"],
    "Heat pumps": [
        "rural air heat pump",
        "rural ground heat pump",
        "urban central air heat pump",
        "urban decentral air heat pump",
    ],
}


def plot_technology(carriers: pd.DataFrame, curve: pd.DataFrame, figure_dir: Path) -> None:
    """Capacity and annual energy of the main technologies against the CO2 cut."""
    reduction = curve.set_index("scenario")["reduction_fraction"]
    frame = carriers.copy()
    frame["reduction_fraction"] = frame["scenario"].map(reduction)
    frame = frame.dropna(subset=["reduction_fraction"])
    years = sorted(int(year) for year in frame["year"].unique())
    for column, ylabel, filename in (
        ("optimal_capacity", "Installed capacity (model units)", "technology_capacity.png"),
        ("energy_balance", "Annual energy balance (model units)", "technology_generation.png"),
    ):
        figure, axes = plt.subplots(2, 3, figsize=(14, 8), sharex=True)
        for axis, year in zip(axes.ravel(), years, strict=False):
            subset = frame.loc[frame["year"] == year]
            axis.set_title(str(year))
            for label, names in TECHNOLOGY_GROUPS.items():
                chosen = subset.loc[subset["carrier"].isin(names)]
                if chosen.empty:
                    continue
                series = chosen.groupby("reduction_fraction")[column].sum().sort_index()
                axis.plot(series.index * 100, series, marker="o", label=label, linewidth=1)
            axis.grid(True, linewidth=0.3)
        for axis in axes[1]:
            axis.set_xlabel("Reduction from BAU (%)")
        for axis in axes[:, 0]:
            axis.set_ylabel(ylabel)
        handles, labels = axes.ravel()[0].get_legend_handles_labels()
        if handles:
            figure.legend(handles, labels, loc="upper center", ncol=6, fontsize=8)
        figure.tight_layout(rect=(0, 0, 1, 0.92))
        figure.savefig(figure_dir / filename, dpi=150)
        plt.close(figure)


def plot_cost_composition(summary: pd.DataFrame, figure_dir: Path) -> None:
    """Annualised investment and operating cost against the CO2 cut."""
    years = sorted(int(year) for year in summary["year"].unique())
    figure, axes = plt.subplots(2, 3, figsize=(14, 8), sharex=True)
    for axis, year in zip(axes.ravel(), years, strict=False):
        ordered = summary.loc[summary["year"] == year].sort_values("reduction_fraction")
        axis.set_title(str(year))
        if ordered.empty:
            continue
        x = ordered["reduction_fraction"] * 100
        capital = ordered["capital_cost_eur_per_year"] / 1e9
        operating = ordered["marginal_cost_eur_per_year"] / 1e9
        axis.bar(x, capital, width=6, label="Investment", color="#2f6fad")
        axis.bar(x, operating, width=6, bottom=capital, label="Operation", color="#d4a017")
        axis.grid(True, axis="y", linewidth=0.3)
    for axis in axes[1]:
        axis.set_xlabel("Reduction from BAU (%)")
    for axis in axes[:, 0]:
        axis.set_ylabel("Annual cost (billion EUR/year)")
    handles, labels = axes.ravel()[0].get_legend_handles_labels()
    if handles:
        figure.legend(handles, labels, loc="upper center", ncol=2)
    figure.tight_layout(rect=(0, 0, 1, 0.93))
    figure.savefig(figure_dir / "system_cost_composition.png", dpi=150)
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
            group[["scenario"]]
            .drop_duplicates()
            .assign(
                reduction_fraction=lambda frame: frame["scenario"].map(
                    lambda name: parse_scenario_name(name)[1]
                )
            )
            .sort_values("reduction_fraction", ascending=True)["scenario"]
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


def plot_system_macc(frame: pd.DataFrame, figure_dir: Path, year: int) -> None:
    """One bar for each step from the reference to a tighter cap."""
    ordered = _system_steps(frame)

    figure, axis = plt.subplots(figsize=(12, 6))
    for i in range(1, len(ordered)):
        width = ordered.loc[i, "abatement"] - ordered.loc[i - 1, "abatement"]
        axis.bar(
            ordered.loc[i - 1, "abatement"],
            ordered.loc[i, "MAC"],
            width=width,
            align="edge",
            color="#2f6fad",
            edgecolor="white",
            linewidth=0.5,
        )
        axis.text(
            ordered.loc[i - 1, "abatement"] + width / 2,
            ordered.loc[i, "MAC"],
            ordered.loc[i, "scenario"],
            rotation=90,
            ha="center",
            va="bottom",
            fontsize=8,
        )
    axis.set_xlabel(f"Abatement from the {year} reference (Mt CO2/year)")
    axis.set_ylabel("Marginal abatement cost (EUR/t CO2)")
    axis.set_xlim(left=0)
    low = min(0.0, float(ordered["MAC"].min()))
    high = max(0.0, float(ordered["MAC"].max()))
    pad = max((high - low) * 0.18, 1.0)
    axis.set_ylim(low - pad * 0.05, high + pad)
    axis.grid(True, axis="y", linewidth=0.3)
    figure.tight_layout()
    figure.savefig(figure_dir / f"macc_{year}.png", dpi=150)
    plt.close(figure)


def _system_steps(frame: pd.DataFrame) -> pd.DataFrame:
    ordered = frame.sort_values("emissions", ascending=False).reset_index(drop=True)
    reference_emissions = ordered.loc[0, "emissions"]
    ordered["abatement"] = (reference_emissions - ordered["emissions"]) / 1e6
    ordered["delta_emissions"] = ordered["emissions"].shift() - ordered["emissions"]
    ordered["delta_cost"] = ordered["cost"].diff()
    ordered["MAC"] = ordered["delta_cost"] / ordered["delta_emissions"]
    return ordered


def co2_shadow_price(year: int, scenario: str) -> float | None:
    """Carbon price from ``CO2Limit-upper``, in EUR per tonne.

    The constraint is an upper bound on the CO2 atmosphere store, so the
    stored dual is negative. The price of one more tonne of emissions is
    the negative of that dual.
    """
    import xarray as xr

    path = solved_network_path(f"{year}-{scenario}")
    if not path.exists():
        return None
    with xr.open_dataset(path) as dataset:
        names = [str(name) for name in dataset["global_constraints_i"].values]
        if "CO2Limit-upper" not in names:
            return None
        index = names.index("CO2Limit-upper")
        return -float(dataset["global_constraints_mu"].values[index])


def plot_macc_vs_shadow(frame: pd.DataFrame, figure_dir: Path, year: int) -> None:
    """MACC bars with the CO2 shadow price at the end of each step."""
    ordered = _system_steps(frame)
    ordered["shadow"] = [
        co2_shadow_price(year, scenario) for scenario in ordered["scenario"]
    ]
    comparison = ordered.loc[ordered["MAC"].notna(), ["scenario", "abatement", "MAC", "shadow"]]
    comparison.to_csv(RESULTS_DIR / f"macc_vs_shadow_{year}.csv", index=False)

    figure, axis = plt.subplots(figsize=(12, 6))
    for i in range(1, len(ordered)):
        width = ordered.loc[i, "abatement"] - ordered.loc[i - 1, "abatement"]
        axis.bar(
            ordered.loc[i - 1, "abatement"],
            ordered.loc[i, "MAC"],
            width=width,
            align="edge",
            color="#2f6fad",
            edgecolor="white",
            linewidth=0.5,
            label="MACC" if i == 1 else None,
        )
    ordered["bar_midpoint"] = (ordered["abatement"] + ordered["abatement"].shift()) / 2
    shadow = ordered.dropna(subset=["shadow"])
    axis.plot(
        shadow["bar_midpoint"],
        shadow["shadow"],
        color="#c23b22",
        marker="o",
        linewidth=1.5,
        label="CO2 shadow price",
    )
    axis.set_xlabel(f"Abatement from the {year} reference (Mt CO2/year)")
    axis.set_ylabel("EUR/t CO2")
    axis.set_xlim(left=0)
    values = pd.concat([ordered["MAC"], shadow["shadow"]], ignore_index=True).dropna()
    low = min(0.0, float(values.min()))
    high = max(0.0, float(values.max()))
    pad = max((high - low) * 0.08, 1.0)
    axis.set_ylim(low - pad, high + pad)
    axis.legend()
    axis.grid(True, axis="y", linewidth=0.3)
    figure.tight_layout()
    figure.savefig(figure_dir / f"macc_vs_co2_shadow_{year}.png", dpi=150)
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
    summary_path = RESULTS_DIR / "scenario_summary.csv"
    if summary_path.exists():
        plot_cost_composition(pd.read_csv(summary_path), figure_dir)
    carrier_path = RESULTS_DIR / "carrier_summary.csv"
    if carrier_path.exists():
        plot_technology(pd.read_csv(carrier_path), curve, figure_dir)
    if steps_path.exists():
        plot_carriers(pd.read_csv(steps_path), figure_dir)
    for year in sorted(int(value) for value in curve["year"].unique()):
        system = curve.loc[curve["year"] == year, ["scenario", "emissions_t_per_year", "system_cost_eur_per_year"]]
        system = system.rename(columns={"emissions_t_per_year": "emissions", "system_cost_eur_per_year": "cost"})
        system["scenario"] = system["scenario"].str.replace(rf"^{year}-", "", regex=True)
        if system["scenario"].isin(["BAU"]).any():
            plot_macc_vs_shadow(system, figure_dir, year)
    print(f"Wrote figures in {figure_dir}")


if __name__ == "__main__":
    main()
