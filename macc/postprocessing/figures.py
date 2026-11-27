# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""The four study figures.

Figure 1 compares capacity, electricity generation and CO2 with the EU
reference sheet. Figure 2 does the same for final energy by sector. Each
finished mitigation scenario adds a bar. Figure 3 is the MACC against the
CO2 shadow price for one planning year. Figure 4 shows how technologies
change with the CO2 reduction.
"""

from __future__ import annotations

import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd

from macc.common import RESULTS_DIR, STEPS
from macc.plot_macc import co2_shadow_price
from macc.postprocessing import FIGURE_DIR, TABLE_DIR
from macc.postprocessing.reference import (
    SERIES_LABELS,
    SERIES_ORDER,
    comparison_table,
    keep_scenario,
)

SERIES_COLORS = {
    "EU": "#bdbdbd",
    "BAU": "#4d4d4d",
    "MACC_1": "#9ecae1",
    "MACC_2": "#6baed6",
    "MACC_3": "#4292c6",
    "MACC_4": "#2171b5",
    "MACC_5": "#08519c",
    "MACC_6": "#08306b",
}
TECHNOLOGY_COLORS = {
    "Nuclear": "#6b3fa0",
    "Biomass": "#6b8f71",
    "Hydro lakes": "#4c78a8",
    "Run of river": "#72b7b2",
    "Onshore wind": "#54a24b",
    "Offshore wind": "#88d27a",
    "Solar": "#eeca3b",
    "Geothermal": "#b279a2",
    "Coal": "#4d4d4d",
    "Oil": "#e45756",
    "Gas": "#f58518",
    "Hydrogen": "#9d755d",
    "Electrolysis": "#17becf",
    "Battery": "#ff9da6",
    "Heat pumps": "#bab0ac",
    "Heat storage": "#86bcb6",
    "Pumped hydro": "#4c78a8",
    "Hydro": "#4c78a8",
}


def _years(frame: pd.DataFrame) -> list[int]:
    return sorted(int(value) for value in frame["year"].unique())


def _strategy_bars(axis, frame: pd.DataFrame, year: int, group: str, unit: str) -> None:
    subset = frame.loc[(frame["year"] == year) & (frame["group"] == group)]
    if subset.empty:
        axis.set_axis_off()
        return
    items = list(dict.fromkeys(subset["item"]))
    steps = [step for step in SERIES_ORDER if step in set(subset["step"])]
    width = 0.82 / max(len(steps), 1)
    for index, step in enumerate(steps):
        chosen = subset.loc[subset["step"] == step].drop_duplicates("item").set_index("item")
        values = [
            float(chosen.at[item, "value"]) if item in chosen.index else 0.0 for item in items
        ]
        positions = [
            place + (index - (len(steps) - 1) / 2) * width for place in range(len(items))
        ]
        axis.bar(
            positions,
            values,
            width=width * 0.92,
            label=SERIES_LABELS[step],
            color=SERIES_COLORS[step],
        )
    axis.set_xticks(list(range(len(items))))
    axis.set_xticklabels(items, rotation=40, ha="right")
    axis.set_ylabel(unit)
    axis.axhline(0.0, color="black", linewidth=0.4)


def _legend(figure, axis, ncol: int, title: str | None = "Mitigation strategy") -> None:
    handles, labels = axis.get_legend_handles_labels()
    if not handles:
        return
    figure.legend(
        handles,
        labels,
        loc="lower center",
        ncol=ncol,
        title=title,
        bbox_to_anchor=(0.5, 1.02),
        frameon=False,
        fontsize=8,
    )


def figure_supply(frame: pd.DataFrame) -> None:
    """Capacity, generation and CO2 for the EU sheet, BAU and each mitigation."""
    panels = (
        ("capacity", "GW", "Capacity"),
        ("generation", "TWh", "Electricity generation"),
        ("emissions", "Mt CO2", "CO2"),
    )
    for year in _years(frame):
        figure, axes = plt.subplots(3, 1, figsize=(14, 12))
        for axis, (group, unit, title) in zip(axes, panels, strict=False):
            _strategy_bars(axis, frame, year, group, unit)
            axis.set_title(title)
        _legend(figure, axes[0], ncol=2)
        figure.suptitle(f"{year} supply and the EU reference", fontsize=12, y=1.22)
        figure.tight_layout()
        figure.savefig(FIGURE_DIR / f"figure1_supply_{year}.png", dpi=150, bbox_inches="tight")
        plt.close(figure)


def figure_consumption(frame: pd.DataFrame) -> None:
    """Final energy by sector for the EU sheet, BAU and each mitigation."""
    for year in _years(frame):
        figure, axis = plt.subplots(figsize=(11, 5.2))
        _strategy_bars(axis, frame, year, "consumption", "TWh")
        axis.set_title("Final energy consumption")
        _legend(figure, axis, ncol=2)
        figure.suptitle(f"{year} sectoral consumption and the EU reference", fontsize=12, y=1.28)
        figure.tight_layout()
        figure.savefig(
            FIGURE_DIR / f"figure2_consumption_{year}.png",
            dpi=150,
            bbox_inches="tight",
        )
        plt.close(figure)


def figure_bau_reference(frame: pd.DataFrame) -> None:
    """EU reference and BAU values for supply and final energy, without mitigation."""
    panels = (
        ("capacity", "GW", "Capacity"),
        ("generation", "TWh", "Electricity generation"),
        ("emissions", "Mt CO2", "CO2"),
        ("consumption", "TWh", "Final energy consumption"),
    )
    kept = frame.loc[frame["step"].isin(["EU", "BAU"])]
    for year in _years(frame):
        figure, axes = plt.subplots(2, 2, figsize=(14, 10))
        for axis, (group, unit, title) in zip(axes.ravel(), panels, strict=False):
            _strategy_bars(axis, kept, year, group, unit)
            axis.set_title(title)
        _legend(figure, axes[0, 0], ncol=2, title=None)
        figure.suptitle(f"{year} BAU and the EU reference", fontsize=12, y=1.08)
        figure.tight_layout()
        figure.savefig(
            FIGURE_DIR / f"figure9_bau_reference_{year}.png",
            dpi=150,
            bbox_inches="tight",
        )
        plt.close(figure)


def _curve(year: int) -> pd.DataFrame:
    path = RESULTS_DIR / "scenario_summary.csv"
    if not path.exists():
        return pd.DataFrame()
    summary = pd.read_csv(path)
    rows = []
    for step, reduction in STEPS:
        if not keep_scenario(year, step):
            continue
        chosen = summary.loc[summary["scenario"] == f"{year}-{step}"]
        if chosen.empty:
            continue
        rows.append(
            {
                "step": step,
                "reduction": reduction,
                "emissions": float(chosen["emissions_t_per_year"].iloc[0]),
                "cost": float(chosen["system_cost_eur_per_year"].iloc[0]),
            }
        )
    if not rows:
        return pd.DataFrame()
    ordered = pd.DataFrame(rows).sort_values("reduction").reset_index(drop=True)
    ordered["abatement"] = (ordered["emissions"].iloc[0] - ordered["emissions"]) / 1e6
    ordered["MAC"] = ordered["cost"].diff() / ordered["emissions"].diff().mul(-1)
    return ordered


def figure_shadow(frame: pd.DataFrame) -> None:
    """One MACC and shadow-price figure per planning year."""
    for year in _years(frame):
        ordered = _curve(year)
        if ordered.empty or len(ordered) < 2:
            continue
        figure, axis = plt.subplots(figsize=(10, 5.4))
        labelled = False
        for index in range(1, len(ordered)):
            step = ordered.loc[index, "step"]
            width = ordered.loc[index, "abatement"] - ordered.loc[index - 1, "abatement"]
            axis.bar(
                ordered.loc[index - 1, "abatement"],
                ordered.loc[index, "MAC"],
                width=width,
                align="edge",
                color=SERIES_COLORS[step],
                edgecolor="white",
                linewidth=0.4,
                label=SERIES_LABELS[step],
            )
            labelled = True
        ordered["midpoint"] = (ordered["abatement"] + ordered["abatement"].shift()) / 2
        ordered["shadow"] = [
            co2_shadow_price(year, step) if step != "BAU" else None for step in ordered["step"]
        ]
        shadow = ordered.dropna(subset=["shadow", "midpoint"])
        if not shadow.empty:
            axis.plot(
                shadow["midpoint"],
                shadow["shadow"],
                color="#c23b22",
                marker="o",
                linewidth=1.4,
                label="CO2 shadow price",
            )
        axis.axhline(0.0, color="black", linewidth=0.6)
        axis.set_xlim(left=0)
        axis.set_xlabel(f"Abatement from {year} BAU (Mt CO2/year)")
        axis.set_ylabel("EUR/t CO2")
        axis.grid(True, axis="y", linewidth=0.3)
        if labelled:
            axis.legend(title="Mitigation strategy", fontsize=7, loc="upper left")
        figure.suptitle(f"{year} marginal abatement cost and CO2 shadow price", fontsize=12)
        figure.tight_layout()
        figure.savefig(
            FIGURE_DIR / f"figure3_macc_shadow_{year}.png",
            dpi=150,
            bbox_inches="tight",
        )
        plt.close(figure)


def _technology_lines(axis, frame: pd.DataFrame, year: int, group: str) -> None:
    subset = frame.loc[
        (frame["year"] == year) & (frame["group"] == group) & frame["step"].ne("EU")
    ].dropna(subset=["reduction"])
    if subset.empty:
        axis.set_axis_off()
        return
    for item in list(dict.fromkeys(subset["item"])):
        chosen = subset.loc[subset["item"] == item].sort_values("reduction")
        if float(chosen["value"].abs().sum()) < 1e-6:
            continue
        axis.plot(
            chosen["reduction"] * 100,
            chosen["value"],
            marker="o",
            linewidth=1.2,
            label=item,
            color=TECHNOLOGY_COLORS.get(item),
        )
    axis.grid(True, linewidth=0.3)
    axis.set_xlim(left=0)


def figure_technology(frame: pd.DataFrame) -> None:
    """Technology metrics against the CO2 reduction of each mitigation strategy."""
    panels = (
        ("capacity", "Installed capacity (GW)", "Capacity"),
        ("generation", "Annual generation (TWh)", "Generation"),
        ("fossil", "Fossil fuel consumption (TWh)", "Fossil fuel"),
        ("electrolyser", "Electrolyser capacity (GW)", "Electrolysis"),
        ("storage", "Storage capacity (GWh)", "Storage"),
        ("investment", "Annual investment (M€/year)", "Investment"),
        ("operating", "Fuel and operating costs (M€/year)", "Fuel and operation"),
    )
    for year in _years(frame):
        figure, axes = plt.subplots(4, 2, figsize=(14, 16))
        flat = list(axes.ravel())
        for axis, (group, ylabel, title) in zip(flat, panels, strict=False):
            _technology_lines(axis, frame, year, group)
            axis.set_title(title)
            axis.set_ylabel(ylabel)
            axis.set_xlabel("CO2 reduction from BAU (%)")
            handles, labels = axis.get_legend_handles_labels()
            if handles:
                axis.legend(fontsize=7, loc="best")
        flat[-1].set_axis_off()
        figure.suptitle(f"{year} technology impacts", fontsize=13)
        figure.tight_layout(rect=(0, 0, 1, 0.97))
        figure.savefig(
            FIGURE_DIR / f"figure4_technology_{year}.png",
            dpi=150,
            bbox_inches="tight",
        )
        plt.close(figure)


INVESTMENT_COLORS = {
    "Onshore wind": "#54a24b",
    "Offshore wind": "#88d27a",
    "Solar": "#eeca3b",
    "Electrolysis": "#17becf",
    "Synthetic fuels": "#9d755d",
    "DAC": "#b279a2",
    "Hydrogen": "#86bcb6",
    "Nuclear": "#6b3fa0",
    "Coal": "#4d4d4d",
    "Gas plants": "#f58518",
    "Gas supply": "#ffbf79",
    "Biomass": "#6b8f71",
    "Heat pumps": "#bab0ac",
    "Networks": "#4c78a8",
    "Retrofitting": "#e45756",
    "Battery": "#ff9da6",
    "Oil": "#9c755f",
    "Other": "#c7c7c7",
}


def _investment_group(carrier: str) -> str:
    name = str(carrier).lower()
    if name in {"onshore wind", "onwind"}:
        return "Onshore wind"
    if "offshore" in name or name.startswith("offwind"):
        return "Offshore wind"
    if "solar" in name:
        return "Solar"
    if name == "h2 electrolysis":
        return "Electrolysis"
    if name in {"fischer-tropsch", "electrobiofuels"}:
        return "Synthetic fuels"
    if name == "dac" or name.startswith("dac"):
        return "DAC"
    if name in {"h2 store", "h2 pipeline", "h2 pipeline retrofitted", "h2 turbine"}:
        return "Hydrogen"
    if name == "nuclear":
        return "Nuclear"
    if "coal" in name or name == "lignite":
        return "Coal"
    if name in {"ccgt", "ocgt", "combined-cycle gas"} or "gas chp" in name:
        return "Gas plants"
    if name in {"gas", "gas pipeline", "gas pipeline new"}:
        return "Gas supply"
    if "biomass" in name or "biogas" in name:
        return "Biomass"
    if "heat pump" in name:
        return "Heat pumps"
    if name in {"ac", "dc"} or "distribution" in name:
        return "Networks"
    if "retrofit" in name:
        return "Retrofitting"
    if "battery" in name:
        return "Battery"
    if "oil" in name:
        return "Oil"
    return "Other"


def _investment_change(year: int, steps: list[str]) -> pd.DataFrame:
    """Annual investment of each technology minus that year's BAU, in billion EUR."""
    path = RESULTS_DIR / "carrier_summary.csv"
    if not path.exists():
        return pd.DataFrame()
    carriers = pd.read_csv(path)
    chosen = carriers.loc[carriers["year"] == year].copy()
    if chosen.empty or "capital_cost_eur_per_year" not in chosen.columns:
        return pd.DataFrame()
    chosen["technology"] = chosen["carrier"].map(_investment_group)
    totals = (
        chosen.groupby(["scenario", "technology"], as_index=False)["capital_cost_eur_per_year"]
        .sum()
    )
    bau_name = f"{year}-BAU"
    bau = totals.loc[totals["scenario"] == bau_name].set_index("technology")["capital_cost_eur_per_year"]
    rows = []
    for step in steps:
        scenario = totals.loc[totals["scenario"] == f"{year}-{step}"].set_index("technology")
        for technology in INVESTMENT_COLORS:
            value = float(scenario["capital_cost_eur_per_year"].get(technology, 0.0))
            base = float(bau.get(technology, 0.0))
            rows.append({"step": step, "technology": technology, "delta": (value - base) / 1e9})
    return pd.DataFrame(rows)


def figure_macc_emissions(frame: pd.DataFrame) -> None:
    """Investment in each technology compared with BAU."""
    for year in _years(frame):
        ordered = _curve(year)
        if ordered.empty or len(ordered) < 2:
            continue
        steps = [step for step in ordered["step"] if step != "BAU"]
        change = _investment_change(year, steps)
        figure, axis = plt.subplots(figsize=(12, 6.2))
        if not change.empty:
            present = [
                technology
                for technology in INVESTMENT_COLORS
                if float(change.loc[change["technology"] == technology, "delta"].abs().max()) > 0.05
            ]
            positions = list(range(len(steps)))
            above = {step: 0.0 for step in steps}
            below = {step: 0.0 for step in steps}
            for technology in present:
                heights = []
                bottoms = []
                for step in steps:
                    delta = float(
                        change.loc[
                            (change["step"] == step) & (change["technology"] == technology),
                            "delta",
                        ].iloc[0]
                    )
                    if delta >= 0:
                        bottoms.append(above[step])
                        above[step] += delta
                    else:
                        bottoms.append(below[step])
                        below[step] += delta
                    heights.append(delta)
                axis.bar(
                    positions,
                    heights,
                    bottom=bottoms,
                    color=INVESTMENT_COLORS[technology],
                    edgecolor="white",
                    linewidth=0.3,
                    label=technology,
                )
            axis.set_xticks(positions)
            axis.set_xticklabels([SERIES_LABELS[step] for step in steps], rotation=20, ha="right")
        axis.axhline(0.0, color="black", linewidth=0.8)
        axis.set_ylabel("Investment change vs BAU (billion EUR/year)")
        axis.set_xlabel("Mitigation strategy")
        axis.grid(True, axis="y", linewidth=0.3)
        handles, labels = axis.get_legend_handles_labels()
        axis.legend().remove()
        figure.legend(
            handles,
            labels,
            loc="lower center",
            ncol=6,
            bbox_to_anchor=(0.5, 1.0),
            frameon=False,
            fontsize=8,
        )
        figure.suptitle(f"{year} investment change versus BAU", fontsize=13, y=1.18)
        figure.tight_layout()
        figure.savefig(
            FIGURE_DIR / f"figure5_macc_emissions_{year}.png",
            dpi=150,
            bbox_inches="tight",
        )
        plt.close(figure)


def figure_system_cost(frame: pd.DataFrame) -> None:
    """Total annual system cost of BAU and each mitigation strategy."""
    for year in _years(frame):
        ordered = _curve(year)
        if ordered.empty:
            continue
        figure, axis = plt.subplots(figsize=(10, 5.2))
        positions = list(range(len(ordered)))
        axis.bar(
            positions,
            ordered["cost"] / 1e9,
            color=[SERIES_COLORS[step] for step in ordered["step"]],
            edgecolor="white",
            linewidth=0.4,
        )
        axis.set_xticks(positions)
        axis.set_xticklabels(
            [SERIES_LABELS[step] for step in ordered["step"]],
            rotation=25,
            ha="right",
        )
        axis.set_ylabel("Total system cost (billion EUR/year)")
        axis.set_xlabel("Mitigation strategy")
        axis.grid(True, axis="y", linewidth=0.3)
        figure.suptitle(f"{year} total system cost", fontsize=12)
        figure.tight_layout()
        figure.savefig(
            FIGURE_DIR / f"figure6_system_cost_{year}.png",
            dpi=150,
            bbox_inches="tight",
        )
        plt.close(figure)


_WEDGE_ORDER = (
    "Onshore wind",
    "Solar",
    "Offshore wind",
    "Nuclear",
    "Biomass",
    "Heat pumps",
    "Transport",
    "Hydrogen",
    "Synthetic fuels",
    "DAC",
    "Other",
)
_WEDGE_COLORS = {
    "Onshore wind": "#1d6a8a",
    "Solar": "#e6b325",
    "Offshore wind": "#2a9d8f",
    "Nuclear": "#6b3fa0",
    "Biomass": "#6b8f71",
    "Heat pumps": "#e76f51",
    "Transport": "#588157",
    "Hydrogen": "#48cae4",
    "Synthetic fuels": "#9b5de5",
    "DAC": "#f4a261",
    "Other": "#b0b0b0",
}
_POWER_GENERATION = {
    "Onshore wind": "Onshore wind",
    "Solar": "Solar",
    "Offshore wind": "Offshore wind",
    "Nuclear": "Nuclear",
}


def _wedge_name(carrier: str) -> str:
    """Group a CO2-carrying link into a wedge on the emissions chart."""
    name = str(carrier).lower()
    if name == "dac" or name.startswith("dac "):
        return "DAC"
    if name in {"electrobiofuels", "fischer-tropsch", "methanolisation", "biomass to liquid", "sabatier"}:
        return "Synthetic fuels"
    if name in {"coal", "coal cc", "ccgt", "ccgt cc", "ocgt", "oil"} or "gas chp" in name:
        return "Power"
    if "boiler" in name:
        return "Heat pumps"
    if any(token in name for token in ("land transport", "shipping", "kerosene", "aviation", "machinery")):
        return "Transport"
    if "biomass" in name or "biogas" in name or "bioliquid" in name:
        return "Biomass"
    if any(token in name for token in ("industry", "naphtha", "process", "refining", "methanol")):
        return "Hydrogen"
    return "Other"


def _link_co2_megatonnes(name: str) -> pd.Series:
    """Annual CO2 added to the atmosphere by link carrier, in Mt."""
    import pypsa

    from macc.common import solved_network_path

    network = pypsa.Network(solved_network_path(name))
    weight = network.snapshot_weightings["objective"]
    nyears = float(weight.sum()) / 8760.0
    table = network.links
    pieces = []
    for column in [item for item in table.columns if str(item).startswith("bus")]:
        port = "p" if column == "bus" else "p" + column[3:]
        flows = getattr(network.links_t, port, None)
        if flows is None or flows.empty:
            continue
        connected = [
            item
            for item in table.index[table[column].astype(str).eq("co2 atmosphere")]
            if item in flows.columns
        ]
        if not connected:
            continue
        annual = -(flows[connected].mul(weight, axis=0).sum() / nyears) / 1e6
        pieces.append(annual.groupby(table.loc[annual.index, "carrier"].astype(str)).sum())
    if not pieces:
        return pd.Series(dtype=float)
    return pd.concat(pieces).groupby(level=0).sum()


def _generation_increase(frame: pd.DataFrame, year: int, step: str) -> dict[str, float]:
    subset = frame.loc[(frame["year"] == year) & (frame["group"] == "generation")]
    baseline = subset.loc[subset["step"] == "BAU"].drop_duplicates("item").set_index("item")["value"]
    chosen = subset.loc[subset["step"] == step].drop_duplicates("item").set_index("item")["value"]
    extra = {}
    for label, item in _POWER_GENERATION.items():
        extra[label] = max(0.0, float(chosen.get(item, 0.0)) - float(baseline.get(item, 0.0)))
    return extra


def _emission_wedges(frame: pd.DataFrame, year: int, steps: list[str]) -> pd.DataFrame:
    """CO2 reduction from BAU assigned to each technology, in Mt.

    The values of one scenario sum to the drop in atmospheric CO2. Less CO2
    from power plants is shared across the wind, solar and nuclear that
    generate more than in BAU. Direct removals stay with DAC, synthetic fuels
    and biomass.
    """
    grouped = {}
    for step in steps:
        emissions = _link_co2_megatonnes(f"{year}-{step}")
        grouped[step] = emissions.groupby(emissions.index.map(_wedge_name)).sum()
    baseline = grouped["BAU"]
    rows = []
    for step in steps:
        if step == "BAU":
            for technology in _WEDGE_ORDER:
                rows.append({"step": step, "technology": technology, "abatement_mt": 0.0})
            continue
        change = baseline.subtract(grouped[step], fill_value=0.0)
        power = float(change.pop("Power")) if "Power" in change.index else 0.0
        extra = _generation_increase(frame, year, step)
        extra_total = sum(extra.values())
        raw = {name: float(change.get(name, 0.0)) for name in _WEDGE_ORDER}
        if extra_total > 0 and power > 0:
            for name, value in extra.items():
                raw[name] = raw.get(name, 0.0) + power * value / extra_total
        else:
            raw["Other"] = raw.get("Other", 0.0) + power
        total = sum(raw.values())
        positive = {name: value for name, value in raw.items() if value > 0.05}
        positive_total = sum(positive.values())
        bands = {}
        if total > 0 and positive_total > 0:
            if positive_total >= total:
                bands = {name: value * total / positive_total for name, value in positive.items()}
            else:
                bands = dict(positive)
                bands["Other"] = bands.get("Other", 0.0) + total - positive_total
        for technology in _WEDGE_ORDER:
            rows.append({"step": step, "technology": technology, "abatement_mt": bands.get(technology, 0.0)})
    return pd.DataFrame(rows)


def _draw_emissions_cost(
    year: int,
    steps: list[str],
    mac: list[float],
    emissions: list[float],
    wedges: pd.DataFrame,
    cost: list[float],
    cost_label: str,
    cost_ylabel: str,
    cost_color: str,
    title: str,
    filename: str,
) -> None:
    """Emissions wedges and one cost change versus BAU, along the MACC."""
    present = [
        technology
        for technology in _WEDGE_ORDER
        if float(wedges.loc[wedges["technology"] == technology, "abatement_mt"].max()) > 1
    ]
    bands = {}
    for technology in present:
        band = []
        for step in steps[: len(mac)]:
            chosen = wedges.loc[
                (wedges["step"] == step) & (wedges["technology"] == technology),
                "abatement_mt",
            ]
            band.append(float(chosen.iloc[0]) if len(chosen) else 0.0)
        bands[technology] = band
    # A later step can be cheaper than the one before it. Filling across
    # that backward jump paints over the chart, so each rising stretch is
    # filled on its own. The lines still follow the scenario order.
    stretches = []
    start = 0
    for index in range(1, len(mac)):
        if mac[index] + 1e-6 < mac[index - 1]:
            stretches.append((start, index))
            start = index
    stretches.append((start, len(mac)))
    figure, axis = plt.subplots(figsize=(11, 6.6))
    labelled = set()
    for start, stop in stretches:
        if stop - start < 2:
            continue
        top = [emissions[0]] * (stop - start)
        xs = mac[start:stop]
        for technology in present:
            band = bands[technology][start:stop]
            bottom = [top[index] - band[index] for index in range(len(xs))]
            axis.fill_between(
                xs,
                bottom,
                top,
                color=_WEDGE_COLORS[technology],
                label=technology if technology not in labelled else None,
                linewidth=0.4,
                edgecolor="white",
            )
            labelled.add(technology)
            top = bottom
    axis.plot(mac, emissions, color="black", linewidth=1.1, marker="o", markersize=4.5, zorder=4)
    for index, step in enumerate(steps[: len(mac)]):
        at_end = index == len(mac) - 1
        axis.annotate(
            "BAU" if step == "BAU" else step.replace("MACC_", "MACC "),
            (mac[index], emissions[index]),
            textcoords="offset points",
            xytext=(-8, 8) if at_end else (4, 6),
            ha="right" if at_end else "left",
            fontsize=7,
        )
    axis.set_xlabel("MACC (EUR/t CO2)")
    axis.set_ylabel("Total CO2 emissions (Mt/year)")
    axis.set_xlim(left=min(0.0, min(mac)))
    axis.grid(True, linewidth=0.3)
    cost_axis = axis.twinx()
    cost_axis.plot(
        mac,
        cost,
        color=cost_color,
        linewidth=2,
        marker="s",
        markersize=5,
        label=cost_label,
        zorder=5,
    )
    cost_axis.set_ylabel(cost_ylabel, color=cost_color)
    cost_axis.tick_params(axis="y", colors=cost_color)
    cost_axis.axhline(0.0, color=cost_color, linewidth=0.4, linestyle=":")
    handles, labels = axis.get_legend_handles_labels()
    extra_handles, extra_labels = cost_axis.get_legend_handles_labels()
    axis.legend(
        handles + extra_handles,
        labels + extra_labels,
        loc="center left",
        bbox_to_anchor=(1.14, 0.5),
        frameon=False,
        fontsize=8,
    )
    figure.suptitle(title, fontsize=13)
    figure.tight_layout()
    figure.savefig(FIGURE_DIR / filename, dpi=150, bbox_inches="tight")
    plt.close(figure)


def figure_technology_macc(frame: pd.DataFrame) -> None:
    """Emissions along the MACC, with investment and operating cost versus BAU."""
    summary = pd.read_csv(RESULTS_DIR / "scenario_summary.csv")
    for year in _years(frame):
        ordered = _curve(year)
        if ordered.empty or len(ordered) < 2:
            continue
        steps = ["BAU", *[step for step in ordered["step"] if step != "BAU"]]
        wedges = _emission_wedges(frame, year, steps)
        mac = [0.0]
        emissions = [float(ordered.loc[ordered["step"] == "BAU", "emissions"].iloc[0]) / 1e6]
        investment = [0.0]
        operating = [0.0]
        bau = summary.loc[summary["scenario"] == f"{year}-BAU"].iloc[0]
        bau_capital = float(bau["capital_cost_eur_per_year"])
        bau_operating = float(bau["marginal_cost_eur_per_year"])
        for index in range(1, len(ordered)):
            step = ordered.loc[index, "step"]
            height = float(ordered.loc[index, "MAC"])
            if pd.isna(height) or not math.isfinite(height):
                continue
            mac.append(height)
            emissions.append(float(ordered.loc[index, "emissions"]) / 1e6)
            row = summary.loc[summary["scenario"] == f"{year}-{step}"].iloc[0]
            investment.append((float(row["capital_cost_eur_per_year"]) - bau_capital) / 1e9)
            operating.append((float(row["marginal_cost_eur_per_year"]) - bau_operating) / 1e9)
            if step != steps[len(mac) - 1]:
                steps[len(mac) - 1] = step
        shared = (year, steps, mac, emissions, wedges)
        _draw_emissions_cost(
            *shared,
            investment,
            "Investment increase vs BAU",
            "Investment increase vs BAU (billion EUR/year)",
            "#9b2226",
            f"{year} emissions and investment along the MACC",
            f"figure7_technology_macc_{year}.png",
        )
        _draw_emissions_cost(
            *shared,
            operating,
            "Operating cost change vs BAU",
            "Operating cost change vs BAU (billion EUR/year)",
            "#1d4e89",
            f"{year} emissions and operating cost along the MACC",
            f"figure8_operating_macc_{year}.png",
        )


def write_figures() -> None:
    """Replace the study figures with the four current plots."""
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    for path in FIGURE_DIR.glob("*.png"):
        path.unlink()
    frame = comparison_table()
    if frame.empty:
        print("No solved BAU network, so the study figures were not written.")
        return
    path = TABLE_DIR / "scenario_comparison.csv"
    frame.to_csv(path, index=False)
    print(f"Wrote {path}")
    figure_supply(frame)
    figure_consumption(frame)
    figure_bau_reference(frame)
    figure_shadow(frame)
    figure_technology(frame)
    figure_macc_emissions(frame)
    figure_system_cost(frame)
    figure_technology_macc(frame)
    print(f"Wrote study figures in {FIGURE_DIR}")
