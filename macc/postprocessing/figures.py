# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""The five figures of the MACC study."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd

from macc.common import RESULTS_DIR, YEARS
from macc.plot_macc import (
    TECHNOLOGY_GROUPS,
    _bar_macc,
    _steps,
    _system_steps,
    co2_shadow_price,
)
from macc.postprocessing import FIGURE_DIR, TABLE_DIR
from macc.postprocessing.reference import comparison_table

COST_COLUMNS = (
    ("investment_eur_per_year", "Annualised investment", "#2f6fad"),
    ("fixed_om_eur_per_year", "Fixed operation", "#7aa2d4"),
    ("variable_om_eur_per_year", "Variable operation", "#d4a017"),
    ("fuel_cost_eur_per_year", "Fuel", "#c23b22"),
    ("other_cost_eur_per_year", "Other", "#6b6b6b"),
)


def _panels():
    figure, axes = plt.subplots(2, 3, figsize=(14, 8))
    return figure, axes


def _finish(figure, axes, ylabel: str, filename: str, ncol: int = 4) -> None:
    for axis in axes[1]:
        axis.set_xlabel("Reduction from BAU (%)")
    for axis in axes[:, 0]:
        axis.set_ylabel(ylabel)
    handles, labels = axes.ravel()[0].get_legend_handles_labels()
    if handles:
        figure.legend(handles, labels, loc="upper center", ncol=ncol, fontsize=8)
        figure.tight_layout(rect=(0, 0, 1, 0.92))
    else:
        figure.tight_layout()
    figure.savefig(FIGURE_DIR / filename, dpi=150)
    plt.close(figure)


def figure_macc(curve: pd.DataFrame) -> None:
    """Six panels of system marginal abatement cost, including negative steps."""
    figure, axes = _panels()
    for axis, year in zip(axes.ravel(), YEARS, strict=False):
        axis.set_title(str(year))
        steps = _steps(curve, year)
        if steps.empty:
            axis.axhline(0.0, color="black", linewidth=0.6)
            continue
        _bar_macc(axis, steps)
        axis.set_xlim(left=0)
    for axis in axes[1]:
        axis.set_xlabel("Abatement from BAU (Mt CO2/year)")
    for axis in axes[:, 0]:
        axis.set_ylabel("MAC (EUR/t CO2)")
    figure.tight_layout()
    figure.savefig(FIGURE_DIR / "figure1_system_macc.png", dpi=150)
    plt.close(figure)


def figure_technology(carriers: pd.DataFrame, curve: pd.DataFrame) -> None:
    """Installed capacity and annual generation against the abatement level."""
    reduction = curve.set_index("scenario")["reduction_fraction"]
    frame = carriers.copy()
    frame["reduction_fraction"] = frame["scenario"].map(reduction)
    frame = frame.dropna(subset=["reduction_fraction"])
    specs = (
        ("optimal_capacity", 1e-3, "Capacity (GW or GWh)", "figure2_technology_capacity.png"),
        ("energy_balance", 1e-6, "Annual energy (TWh)", "figure2_technology_generation.png"),
    )
    for column, scale, ylabel, filename in specs:
        figure, axes = _panels()
        for axis, year in zip(axes.ravel(), YEARS, strict=False):
            subset = frame.loc[frame["year"] == year]
            axis.set_title(str(year))
            for label, names in TECHNOLOGY_GROUPS.items():
                chosen = subset.loc[subset["carrier"].isin(names)]
                if chosen.empty:
                    continue
                series = chosen.groupby("reduction_fraction")[column].sum().sort_index()
                axis.plot(
                    series.index * 100,
                    series * scale,
                    marker="o",
                    label=label,
                    linewidth=1,
                )
            axis.grid(True, linewidth=0.3)
        _finish(figure, axes, ylabel, filename, ncol=6)


def figure_costs(summary: pd.DataFrame) -> None:
    """Investment, fixed operation, variable operation, fuel and other costs."""
    figure, axes = _panels()
    for axis, year in zip(axes.ravel(), YEARS, strict=False):
        ordered = summary.loc[summary["year"] == year].sort_values("reduction_fraction")
        axis.set_title(str(year))
        if ordered.empty:
            continue
        x = ordered["reduction_fraction"] * 100
        bottom = pd.Series(0.0, index=ordered.index)
        for column, label, color in COST_COLUMNS:
            if column not in ordered.columns:
                continue
            height = ordered[column].fillna(0.0) / 1e9
            axis.bar(x, height, width=6, bottom=bottom, label=label, color=color)
            bottom = bottom + height
        axis.grid(True, axis="y", linewidth=0.3)
    _finish(figure, axes, "Annual cost (billion EUR/year)", "figure3_system_cost.png", ncol=5)


def figure_shadow(curve: pd.DataFrame) -> None:
    """Marginal abatement cost and the CO2 shadow price, one panel per year."""
    figure, axes = _panels()
    labelled = False
    shadow_labelled = False
    for axis, year in zip(axes.ravel(), YEARS, strict=False):
        axis.set_title(str(year))
        subset = curve.loc[
            curve["year"] == year, ["scenario", "emissions_t_per_year", "system_cost_eur_per_year"]
        ].rename(
            columns={
                "emissions_t_per_year": "emissions",
                "system_cost_eur_per_year": "cost",
            }
        )
        subset["scenario"] = subset["scenario"].str.replace(rf"^{year}-", "", regex=True)
        if not subset["scenario"].isin(["BAU"]).any() or len(subset) < 2:
            axis.axhline(0.0, color="black", linewidth=0.6)
            continue
        ordered = _system_steps(subset)
        ordered["shadow"] = [
            co2_shadow_price(year, scenario) for scenario in ordered["scenario"]
        ]
        for i in range(1, len(ordered)):
            width = ordered.loc[i, "abatement"] - ordered.loc[i - 1, "abatement"]
            axis.bar(
                ordered.loc[i - 1, "abatement"],
                ordered.loc[i, "MAC"],
                width=width,
                align="edge",
                color="#2f6fad",
                edgecolor="white",
                linewidth=0.4,
                label="MACC" if not labelled else None,
            )
            labelled = True
        ordered["midpoint"] = (ordered["abatement"] + ordered["abatement"].shift()) / 2
        shadow = ordered.dropna(subset=["shadow"])
        if not shadow.empty:
            axis.plot(
                shadow["midpoint"],
                shadow["shadow"],
                color="#c23b22",
                marker="o",
                linewidth=1.2,
                label="CO2 shadow price" if not shadow_labelled else None,
            )
            shadow_labelled = True
        axis.axhline(0.0, color="black", linewidth=0.6)
        axis.set_xlim(left=0)
        axis.grid(True, axis="y", linewidth=0.3)
    for axis in axes[1]:
        axis.set_xlabel("Abatement from BAU (Mt CO2/year)")
    for axis in axes[:, 0]:
        axis.set_ylabel("EUR/t CO2")
    handles, labels = [], []
    for axis in axes.ravel():
        found_handles, found_labels = axis.get_legend_handles_labels()
        for handle, label in zip(found_handles, found_labels, strict=False):
            if label not in labels:
                handles.append(handle)
                labels.append(label)
    if handles:
        figure.legend(handles, labels, loc="upper center", ncol=2)
        figure.tight_layout(rect=(0, 0, 1, 0.93))
    else:
        figure.tight_layout()
    figure.savefig(FIGURE_DIR / "figure4_shadow_vs_macc.png", dpi=150)
    plt.close(figure)


def _heatmap(frame: pd.DataFrame, year: int, group: str, filename: str, title: str) -> None:
    subset = frame.loc[(frame["year"] == year) & (frame["group"] == group)]
    if subset.empty:
        return
    pivot = subset.pivot(index="country", columns="item", values="model_over_reference")
    pivot = pivot.apply(pd.to_numeric, errors="coerce")
    figure, axis = plt.subplots(figsize=(1.15 * len(pivot.columns) + 2, 0.32 * len(pivot.index) + 1.6))
    values = pivot.to_numpy(dtype=float)
    finite = values[pd.notna(values)]
    span = float(pd.Series(finite - 1.0).abs().max()) if len(finite) else 1.0
    span = max(span, 0.05)
    colours = plt.get_cmap("RdBu_r").copy()
    colours.set_bad("#f0f0f0")
    image = axis.imshow(
        values, cmap=colours, vmin=1.0 - span, vmax=1.0 + span, aspect="auto"
    )
    axis.set_xticks(range(len(pivot.columns)))
    axis.set_xticklabels(pivot.columns, rotation=45, ha="right")
    axis.set_yticks(range(len(pivot.index)))
    axis.set_yticklabels(pivot.index)
    axis.set_title(title)
    figure.colorbar(image, ax=axis, label="Model / reference")
    figure.tight_layout()
    figure.savefig(FIGURE_DIR / filename, dpi=150)
    plt.close(figure)


def figure_reference(frame: pd.DataFrame) -> None:
    """Solved BAU against the reference capacities and the imposed energy totals."""
    if frame.empty:
        print("No solved BAU network, so figure 5 was not written.")
        return
    path = TABLE_DIR / "bau_vs_reference.csv"
    frame.to_csv(path, index=False)
    print(f"Wrote {path}")
    for year in sorted(int(value) for value in frame["year"].unique()):
        _heatmap(
            frame,
            year,
            "capacity",
            f"figure5_bau_capacity_{year}.png",
            f"{year} BAU capacity, model / EU reference",
        )
        _heatmap(
            frame,
            year,
            "generation",
            f"figure5_bau_generation_{year}.png",
            f"{year} BAU electricity generation, model / EU reference",
        )
        _heatmap(
            frame,
            year,
            "final_energy",
            f"figure5_bau_final_energy_{year}.png",
            f"{year} BAU final energy, model / EU reference",
        )
        _heatmap(
            frame,
            year,
            "primary",
            f"figure5_bau_primary_{year}.png",
            f"{year} BAU primary supply, model / EU reference",
        )


def write_figures() -> None:
    """Write figures 1–5 from the extracted tables and the solved BAU networks."""
    curve_path = RESULTS_DIR / "macc.csv"
    if not curve_path.exists():
        raise SystemExit("Run python -m macc.compute_macc before the study figures.")
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    curve = pd.read_csv(curve_path)
    figure_macc(curve)
    summary_path = RESULTS_DIR / "scenario_summary.csv"
    if summary_path.exists():
        figure_costs(pd.read_csv(summary_path))
        figure_shadow(curve)
    carrier_path = RESULTS_DIR / "carrier_summary.csv"
    if carrier_path.exists():
        figure_technology(pd.read_csv(carrier_path), curve)
    figure_reference(comparison_table())
    print(f"Wrote study figures in {FIGURE_DIR}")
