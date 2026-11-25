# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""Write the exogenous pathway used by every MACC year.

Values come from ``config/config.default.yaml``. A planning horizon selects
the matching year with the same rules as ``scripts._helpers.get``. Nothing in
the MACC configs overrides ``sector`` or ``industry``, so every CO2 case in a
year sees this same pathway.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macc.common import (  # noqa: E402
    COST_YEAR,
    CUTOUT,
    DEFAULT_CONFIG,
    PATHWAY_DIR,
    TECHNOLOGY_DATA_VERSION,
    TEMPORAL_RESOLUTION,
    WEATHER_YEAR,
    YEARS,
    load_yaml,
    looks_frozen,
    year_map,
    year_value,
)

INACTIVE_NOTES = {
    "sector.residential_heat.dsm.restriction_value": (
        "Not used while sector.residential_heat.dsm.enable is false."
    ),
    "sector.reduce_space_heat_exogenously_factor": (
        "Not used while sector.reduce_space_heat_exogenously is false. "
        "Building retrofit is optimised instead."
    ),
}


SHARE_GROUPS = {
    "land_transport": [
        "land_transport_fuel_cell_share",
        "land_transport_electric_share",
        "land_transport_ice_share",
    ],
    "shipping": [
        "shipping_hydrogen_share",
        "shipping_methanol_share",
        "shipping_oil_share",
        "shipping_lng_share",
    ],
    "agriculture_machinery": [
        "agriculture_machinery_electric_share",
        "agriculture_machinery_oil_share",
    ],
    "hvc": [
        "HVC_primary_fraction",
        "HVC_mechanical_recycling_fraction",
        "HVC_chemical_recycling_fraction",
        "HVC_environment_sequestration_fraction",
    ],
}


def iter_year_maps(node, prefix: tuple[str, ...] = ()):
    """Yield ``(path, year_map)`` for every year-keyed mapping."""
    if not isinstance(node, dict):
        return
    mapped = year_map(node)
    if mapped is not None:
        yield prefix, mapped
        return
    for key, value in node.items():
        if isinstance(value, dict):
            yield from iter_year_maps(value, prefix + (str(key),))


def pathway_table(config: dict) -> pd.DataFrame:
    rows = []
    for section in ("sector", "industry"):
        for path, mapped in iter_year_maps(config[section], (section,)):
            parameter = ".".join(path)
            frozen = looks_frozen(path[-1])
            values = [year_value(mapped, year) for year in YEARS]
            varies = len(set(values)) > 1
            if frozen and varies:
                raise SystemExit(
                    f"{parameter} changes across planning years. Technology "
                    "costs and efficiencies must stay at the 2025 value for "
                    "this experiment."
                )
            for year, value in zip(YEARS, values):
                rows.append(
                    {
                        "parameter": parameter,
                        "year": year,
                        "value": value,
                        "pathway": "fixed" if frozen or not varies else "evolves",
                        "note": INACTIVE_NOTES.get(parameter, ""),
                    }
                )
    return pd.DataFrame(rows)


def _scalar_rows(config: dict) -> pd.DataFrame:
    """Record assumptions that are constant across the six planning years."""
    sector = config["sector"]
    industry = config["industry"]
    fixed = {
        "costs.year": COST_YEAR,
        "costs.social_discountrate": config["costs"]["social_discountrate"],
        "costs.fill_values.discount rate": config["costs"]["fill_values"][
            "discount rate"
        ],
        "data.costs.version": TECHNOLOGY_DATA_VERSION,
        "snapshots.start": config["snapshots"]["start"],
        "snapshots.end": config["snapshots"]["end"],
        "atlite.default_cutout": CUTOUT,
        "clustering.mode": "administrative",
        "clustering.administrative.level": 0,
        "clustering.temporal.averaging": TEMPORAL_RESOLUTION,
        "energy.energy_totals_year": config["energy"]["energy_totals_year"],
        "biomass.year": config["biomass"]["year"],
        "biomass.scenario": config["biomass"]["scenario"],
        "sector.transport_electric_efficiency": sector[
            "transport_electric_efficiency"
        ],
        "sector.transport_fuel_cell_efficiency": sector[
            "transport_fuel_cell_efficiency"
        ],
        "sector.transport_ice_efficiency": sector["transport_ice_efficiency"],
        "sector.shipping_methanol_efficiency": sector["shipping_methanol_efficiency"],
        "sector.shipping_oil_efficiency": sector["shipping_oil_efficiency"],
        "sector.shipping_lng_efficiency": sector["shipping_lng_efficiency"],
        "sector.agriculture_machinery_electric_share": sector[
            "agriculture_machinery_electric_share"
        ],
        "sector.agriculture_machinery_oil_share": sector[
            "agriculture_machinery_oil_share"
        ],
        "sector.agriculture_machinery_electric_efficiency": sector[
            "agriculture_machinery_electric_efficiency"
        ],
        "sector.agriculture_machinery_fuel_efficiency": sector[
            "agriculture_machinery_fuel_efficiency"
        ],
        "sector.aviation_demand_factor": sector["aviation_demand_factor"],
        "sector.reduce_space_heat_exogenously": sector[
            "reduce_space_heat_exogenously"
        ],
        "sector.co2_sequestration_cost": sector["co2_sequestration_cost"],
        "industry.H2_DRI": industry["H2_DRI"],
        "industry.elec_DRI": industry["elec_DRI"],
        "electricity.powerplants_filter": config["electricity"]["powerplants_filter"],
        "weather_year": WEATHER_YEAR,
    }
    rows = [
        {
            "parameter": name,
            "year": "all",
            "value": value,
            "pathway": "fixed",
            "note": "Same value in every planning year and every CO2 case.",
        }
        for name, value in fixed.items()
    ]
    rows.append(
        {
            "parameter": "heating_technology_shares",
            "year": "all",
            "value": "endogenous",
            "pathway": "optimised",
            "note": (
                "Heat pumps, gas boilers, oil boilers, biomass boilers and "
                "resistive heaters are investment decisions. District-heating "
                "progress is the exogenous heating pathway. Building retrofit "
                "is optimised because reduce_space_heat_exogenously is false."
            ),
        }
    )
    return pd.DataFrame(rows)


def share_checks(config: dict) -> pd.DataFrame:
    rows = []
    for group, names in SHARE_GROUPS.items():
        section = "industry" if group == "hvc" else "sector"
        block = config[section]
        for year in YEARS:
            total = 0.0
            parts = {}
            for name in names:
                value = year_value(block[name], year)
                parts[name] = value
                total += float(value)
            rows.append(
                {
                    "group": group,
                    "year": year,
                    "sum": total,
                    **parts,
                }
            )
    frame = pd.DataFrame(rows)
    for group in ("land_transport", "shipping"):
        bad = frame.loc[frame["group"] == group]
        if (bad["sum"] - 1).abs().max() > 1e-6:
            raise SystemExit(
                f"{group} shares do not sum to 1 in config/config.default.yaml."
            )
    return frame


def export_pathways(config_path: Path = DEFAULT_CONFIG) -> tuple[Path, Path]:
    config = load_yaml(config_path)
    assumptions = pd.concat(
        [pathway_table(config), _scalar_rows(config)], ignore_index=True
    )
    checks = share_checks(config)
    PATHWAY_DIR.mkdir(parents=True, exist_ok=True)
    assumptions_path = PATHWAY_DIR / "exogenous_assumptions.csv"
    checks_path = PATHWAY_DIR / "share_checks.csv"
    assumptions.to_csv(assumptions_path, index=False)
    checks.to_csv(checks_path, index=False)
    return assumptions_path, checks_path


if __name__ == "__main__":
    assumptions_path, checks_path = export_pathways()
    print(assumptions_path)
    print(checks_path)
