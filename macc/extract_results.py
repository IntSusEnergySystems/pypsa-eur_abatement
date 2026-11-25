# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""Read solved MACC networks and write annual cost, emissions and carriers.

Emissions are the final level of the ``co2 atmosphere`` store, divided by the
number of years represented by the snapshots. That is the quantity constrained
by ``CO2Limit-upper``. System cost is annualised investment plus operation,
taken from the solved network statistics.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pypsa

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macc.common import (  # noqa: E402
    MACC_DIR,
    RESULTS_DIR,
    ROOT,
    TONNES_PER_GT,
    load_yaml,
    parse_scenario_name,
    scenario_path,
    solved_network_path,
    tonnes_to_gt_per_year,
)

ATMOSPHERE_STORE = "co2 atmosphere"


def _represented_years(network: pypsa.Network) -> float:
    weightings = network.snapshot_weightings
    column = "objective" if "objective" in weightings.columns else weightings.columns[0]
    return float(weightings[column].sum()) / 8760.0


def annual_co2_tonnes(network: pypsa.Network) -> tuple[float, float]:
    """Return ``(annual CO2 tonnes, represented years)``."""
    if ATMOSPHERE_STORE not in network.stores.index:
        raise ValueError(f"Network has no {ATMOSPHERE_STORE!r} store.")
    if ATMOSPHERE_STORE not in network.stores_t.e.columns:
        raise ValueError(f"Network has no time series for {ATMOSPHERE_STORE!r}.")
    nyears = _represented_years(network)
    if nyears <= 0:
        raise ValueError("Snapshot weightings sum to zero.")
    period_tonnes = float(network.stores_t.e[ATMOSPHERE_STORE].iloc[-1])
    return period_tonnes / nyears, nyears


def annual_system_cost(network: pypsa.Network) -> tuple[float, float, float]:
    """Return ``(total, capital, marginal)`` annual cost in model currency."""
    capital = float(network.statistics.capex().sum())
    marginal = float(network.statistics.opex().sum())
    return capital + marginal, capital, marginal


def _by_carrier(series: pd.Series | pd.DataFrame) -> pd.Series:
    if isinstance(series, pd.DataFrame):
        series = series.stack()
    if isinstance(series.index, pd.MultiIndex) and "carrier" in series.index.names:
        return series.groupby(level="carrier").sum()
    return series


def carrier_table(network: pypsa.Network, label: str) -> pd.DataFrame:
    pieces = {
        "capital_cost_eur_per_year": _by_carrier(network.statistics.capex()),
        "marginal_cost_eur_per_year": _by_carrier(network.statistics.opex()),
        "optimal_capacity": _by_carrier(network.statistics.optimal_capacity()),
        "energy_balance": _by_carrier(
            network.statistics.energy_balance(groupby="carrier")
        ),
    }
    frame = pd.concat(pieces, axis=1)
    frame.index.name = "carrier"
    frame = frame.reset_index()
    frame.insert(0, "quantity_group", label)
    return frame


def _configured_cap_tonnes(year: int, name: str) -> float | None:
    path = scenario_path(year)
    if not path.exists():
        return None
    scenarios = load_yaml(path)
    if name not in scenarios:
        return None
    upper = scenarios[name]["co2_budget"]["upper"]
    if upper is None:
        return None
    return float(upper) * TONNES_PER_GT


def scenario_names() -> list[str]:
    matrix_path = MACC_DIR / "scenario_matrix.csv"
    if not matrix_path.exists():
        raise SystemExit("Missing macc/scenario_matrix.csv. Run generate_scenarios first.")
    return pd.read_csv(matrix_path)["scenario"].tolist()


def extract() -> tuple[pd.DataFrame, pd.DataFrame]:
    summaries = []
    carriers = []
    missing = []
    for name in scenario_names():
        path = solved_network_path(name)
        if not path.exists():
            missing.append(name)
            continue
        year, remaining = parse_scenario_name(name)
        network = pypsa.Network(path)
        emissions_t, nyears = annual_co2_tonnes(network)
        total, capital, marginal = annual_system_cost(network)
        cap_t = _configured_cap_tonnes(year, name)
        constraint = pd.NA
        if "CO2Limit-upper" in network.global_constraints.index:
            constraint = float(
                network.global_constraints.at["CO2Limit-upper", "constant"]
            )
        summaries.append(
            {
                "year": year,
                "scenario": name,
                "remaining_fraction": remaining,
                "reduction_fraction": 1.0 - remaining,
                "system_cost_eur_per_year": total,
                "capital_cost_eur_per_year": capital,
                "marginal_cost_eur_per_year": marginal,
                "objective": float(network.objective),
                "emissions_t_per_year": emissions_t,
                "emissions_mt_per_year": emissions_t / 1e6,
                "emissions_gt_per_year": tonnes_to_gt_per_year(emissions_t),
                "co2_cap_t_per_year": cap_t,
                "co2_constraint_constant_t": constraint,
                "nyears": nyears,
                "network": str(path.relative_to(ROOT)),
            }
        )
        table = carrier_table(network, name)
        table.insert(0, "year", year)
        table.insert(1, "scenario", name)
        carriers.append(table)
        print(f"Read {name}: {emissions_t / 1e6:.3f} Mt/year, cost {total:.3e}")
    if not summaries:
        raise SystemExit("No solved networks found under results/macc/.")
    if missing:
        print(f"Skipped {len(missing)} scenarios without a solved network.")
    summary = pd.DataFrame(summaries).sort_values(
        ["year", "remaining_fraction"], ascending=[True, False]
    )
    carrier_frame = pd.concat(carriers, ignore_index=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = RESULTS_DIR / "scenario_summary.csv"
    carrier_path = RESULTS_DIR / "carrier_summary.csv"
    summary.to_csv(summary_path, index=False)
    carrier_frame.to_csv(carrier_path, index=False)
    print(f"Wrote {summary_path.relative_to(MACC_DIR.parent)}")
    print(f"Wrote {carrier_path.relative_to(MACC_DIR.parent)}")
    return summary, carrier_frame


def main() -> None:
    extract()


if __name__ == "__main__":
    main()
