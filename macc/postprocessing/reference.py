# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""Compare each solved BAU with the EU Reference Scenario rows imposed on it."""

from __future__ import annotations

import pandas as pd
import pypsa

from macc.bau_capacities import (
    PLANT_COMPONENTS,
    _matching,
    load_capacities,
)
from macc.bau_pathway import (
    AVIATION_LOADS,
    BUILDING_LOADS,
    GENERATION,
    INDUSTRY_LOADS,
    KTOE_TO_MWH,
    ROAD_EV,
    ROAD_OIL,
    SHIPPING_LOADS,
    TRANSPORT_LOADS,
    _annual_mwh,
    _components,
    _loads,
    _lookup,
    load_balances,
)
from macc.common import COUNTRIES, YEARS, solved_network_path

GWH_TO_TWH = 1e-3
MWH_TO_TWH = 1e-6
PLANT_LABELS = {
    "nuclear": "Nuclear",
    "biomass": "Biomass",
    "hydro_lakes": "Hydro lakes",
    "ror": "Run of river",
    "onwind": "Onshore wind",
    "offwind": "Offshore wind",
    "solar": "Solar",
    "geothermal": "Geothermal",
    "coal": "Coal",
    "oil": "Oil",
    "gas": "Gas",
    "hydrogen_power": "Hydrogen",
}
GENERATION_LABELS = {
    "gen_nuclear_gwh": "Nuclear",
    "gen_biomass_gwh": "Biomass",
    "gen_hydro_lakes_gwh": "Hydro lakes",
    "gen_ror_gwh": "Run of river",
    "gen_onwind_gwh": "Onshore wind",
    "gen_offwind_gwh": "Offshore wind",
    "gen_solar_gwh": "Solar",
    "gen_geothermal_gwh": "Geothermal",
    "gen_coal_gwh": "Coal",
    "gen_oil_gwh": "Oil",
    "gen_gas_gwh": "Gas",
    "gen_hydrogen_gwh": "Hydrogen",
}


def _row(year, country, group, item, unit, reference, model) -> dict:
    ratio = pd.NA
    if reference not in (None, 0) and pd.notna(reference) and abs(reference) > 1e-9:
        ratio = model / reference
    return {
        "year": year,
        "country": country,
        "group": group,
        "item": item,
        "unit": unit,
        "reference": reference,
        "model": model,
        "model_over_reference": ratio,
    }


def _electric_mw(network, country: str, plant: str) -> float:
    total = 0.0
    for table_name, carrier, direct in PLANT_COMPONENTS[plant]:
        table = getattr(network, table_name)
        names = _matching(network, table, carrier, country)
        if len(names) == 0:
            continue
        column = "p_nom_opt" if "p_nom_opt" in table.columns else "p_nom"
        power = table.loc[names, column].astype(float)
        if not direct:
            power = power * table.loc[names, "efficiency"].astype(float)
        total += float(power.sum())
    return total


def _generation_twh(network, country: str, variable: str) -> float:
    weight = network.snapshot_weightings.objective
    total = 0.0
    for table_name, names, direct in _components(network, country, GENERATION[variable]):
        panel = getattr(network, f"{table_name}_t").p
        present = [name for name in names if name in panel.columns]
        if not present:
            continue
        energy = panel[present].mul(weight, axis=0).sum()
        if not direct:
            efficiency = getattr(network, table_name).loc[present, "efficiency"].astype(float)
            energy = energy * efficiency
        total += float(energy.sum())
    return total * MWH_TO_TWH


def _supply_twh(network, names: pd.Index) -> float:
    if len(names) == 0:
        return 0.0
    weight = network.snapshot_weightings.objective
    panel = network.generators_t.p
    present = [name for name in names if name in panel.columns]
    if not present:
        return 0.0
    return float(panel[present].mul(weight, axis=0).sum().sum()) * MWH_TO_TWH


def compare_network(network, year: int) -> pd.DataFrame:
    """Sheet values against the solved BAU, for every imposed quantity."""
    balances = load_balances(year)
    capacities = load_capacities(year)
    present = set(network.buses.country.dropna().unique())
    rows = []
    modelled = [country for country in COUNTRIES if country in present]
    for country in modelled:
        for plant, label in PLANT_LABELS.items():
            sheet = capacities.loc[
                (capacities["country"] == country) & (capacities["plant"] == plant),
                "capacity_mw",
            ]
            reference = float(sheet.iloc[0]) if len(sheet) else 0.0
            rows.append(
                _row(
                    year,
                    country,
                    "capacity",
                    label,
                    "MW",
                    reference,
                    _electric_mw(network, country, plant),
                )
            )
        industry = _lookup(balances, country, "final_industry_ktoe") or 0.0
        residential = _lookup(balances, country, "final_residential_ktoe") or 0.0
        tertiary = _lookup(balances, country, "final_tertiary_ktoe") or 0.0
        transport = _lookup(balances, country, "final_transport_ktoe") or 0.0
        aviation = _lookup(balances, country, "bunker_aviation_ktoe") or 0.0
        maritime = _lookup(balances, country, "bunker_maritime_ktoe") or 0.0
        demands = (
            ("Industry", industry, INDUSTRY_LOADS),
            ("Buildings", residential + tertiary, BUILDING_LOADS),
            ("Road transport", transport, TRANSPORT_LOADS),
            ("International aviation", aviation, AVIATION_LOADS),
            ("International maritime", maritime, SHIPPING_LOADS),
        )
        for label, ktoe, carriers in demands:
            rows.append(
                _row(
                    year,
                    country,
                    "final_energy",
                    label,
                    "TWh",
                    ktoe * KTOE_TO_MWH * MWH_TO_TWH,
                    _annual_mwh(network, _loads(network, country, carriers)) * MWH_TO_TWH,
                )
            )
        share = _lookup(balances, country, "road_electricity_percent")
        electric = _annual_mwh(network, _loads(network, country, ROAD_EV))
        oil = _annual_mwh(network, _loads(network, country, ROAD_OIL))
        model_share = 100.0 * electric / (electric + oil) if electric + oil else 0.0
        rows.append(
            _row(
                year,
                country,
                "transport_share",
                "Road electricity",
                "percent",
                0.0 if share is None else share,
                model_share,
            )
        )
        for variable, label in GENERATION_LABELS.items():
            sheet_gwh = _lookup(balances, country, variable) or 0.0
            rows.append(
                _row(
                    year,
                    country,
                    "generation",
                    label,
                    "TWh",
                    sheet_gwh * GWH_TO_TWH,
                    _generation_twh(network, country, variable),
                )
            )
        gas = _lookup(balances, country, "primary_gas_ktoe") or 0.0
        biomass = _lookup(balances, country, "primary_biomass_ktoe") or 0.0
        gas_units = _matching(network, network.generators, "gas", country)
        biomass_units = network.generators.index[
            network.generators.carrier.isin(["solid biomass", "unsustainable solid biomass"])
            & network.generators.bus.map(network.buses.country).eq(country)
        ]
        rows.append(
            _row(
                year,
                country,
                "primary",
                "Gas",
                "TWh",
                gas * KTOE_TO_MWH * MWH_TO_TWH,
                _supply_twh(network, gas_units),
            )
        )
        rows.append(
            _row(
                year,
                country,
                "primary",
                "Biomass",
                "TWh",
                biomass * KTOE_TO_MWH * MWH_TO_TWH,
                _supply_twh(network, biomass_units),
            )
        )
    solid = balances.loc[
        balances["country"].isin(modelled) & balances["variable"].eq("primary_solid_ktoe"),
        "value",
    ].sum()
    oil = balances.loc[
        balances["country"].isin(modelled) & balances["variable"].eq("primary_oil_ktoe"),
        "value",
    ].sum()
    rows.append(
        _row(
            year,
            "EU",
            "primary",
            "Solid fuel",
            "TWh",
            solid * KTOE_TO_MWH * MWH_TO_TWH,
            _supply_twh(network, network.generators.index[network.generators.carrier.eq("coal")]),
        )
    )
    rows.append(
        _row(
            year,
            "EU",
            "primary",
            "Oil",
            "TWh",
            oil * KTOE_TO_MWH * MWH_TO_TWH,
            _supply_twh(
                network,
                network.generators.index[network.generators.carrier.eq("oil primary")],
            ),
        )
    )
    return pd.DataFrame(rows)


def comparison_table() -> pd.DataFrame:
    """One table for every solved ``{year}-BAU`` network."""
    frames = []
    for year in YEARS:
        path = solved_network_path(f"{year}-BAU")
        if not path.exists():
            continue
        network = pypsa.Network(path)
        frames.append(compare_network(network, year))
        print(f"Compared {year}-BAU with the EU reference sheet")
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
