# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""Compare each solved BAU with the EU sheets of the reference workbook.

Capacity, electricity generation and energy CO2 are read from ``EU_B``.
Sectoral final energy is read from ``EU_A``, and international bunkers from
``EU_B``. The model side is the solved network.
"""

from __future__ import annotations

import pandas as pd
import pypsa

from macc.bau_capacities import (
    PLANT_COMPONENTS,
    PLANT_ROWS,
    _header_years,
    _matching,
)
from macc.bau_pathway import (
    AVIATION_LOADS,
    BUILDING_LOADS,
    INDUSTRY_LOADS,
    KTOE_TO_MWH,
    SHIPPING_LOADS,
    TRANSPORT_LOADS,
    _annual_mwh,
    _loads,
)
from macc.common import REFERENCE_WORKBOOK, YEARS, solved_network_path
from macc.extract_results import annual_co2_tonnes

GWH_TO_TWH = 1e-3
MWH_TO_TWH = 1e-6
EU = "EU"
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
# Same leaf rows as capacity. The generation block uses a comma in the
# geothermal label; the capacity block uses "and".
GENERATION_ROWS = {
    **PLANT_ROWS,
    "Geothermal heat, other renewables (tidal etc.)": "geothermal",
}
# Residential and tertiary are one buildings total in the BAU. Tertiary on
# the sheet already includes agriculture.
CONSUMPTION_SECTORS = (
    ("industry", "Industry", INDUSTRY_LOADS),
    ("buildings", "Residential and tertiary", BUILDING_LOADS),
    ("transport", "Transport", TRANSPORT_LOADS),
    ("aviation", "International aviation", AVIATION_LOADS),
    ("maritime", "International maritime", SHIPPING_LOADS),
)


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


def _weights(network) -> pd.Series:
    weightings = network.snapshot_weightings
    if "generators" in weightings.columns:
        return weightings.generators
    return weightings.iloc[:, 0]


def _dispatched(network, panel: pd.DataFrame, names: pd.Index) -> pd.Series:
    present = [name for name in names if name in panel.columns]
    if not present:
        return pd.Series(dtype=float)
    return panel[present].mul(_weights(network), axis=0).sum()


def _generation_twh(network, country: str, plant: str) -> float:
    """Electricity from the same components whose capacity is fixed to the sheet."""
    total = 0.0
    for table_name, carrier, direct in PLANT_COMPONENTS[plant]:
        table = getattr(network, table_name)
        names = _matching(network, table, carrier, country)
        if len(names) == 0:
            continue
        if table_name == "links":
            energy = _dispatched(network, network.links_t.p0, names)
            if not direct and len(energy):
                energy = energy * table.loc[energy.index, "efficiency"].astype(float)
        elif table_name == "storage_units":
            dispatch = getattr(network.storage_units_t, "p_dispatch", None)
            if dispatch is None:
                continue
            energy = _dispatched(network, dispatch, names)
        else:
            energy = _dispatched(network, network.generators_t.p, names)
        total += float(energy.sum()) if len(energy) else 0.0
    return total * MWH_TO_TWH


def _sheet_number(row: tuple, column: int) -> float:
    if column >= len(row):
        return 0.0
    value = row[column]
    if value in {None, "", "-"}:
        return 0.0
    return float(value)


def _consumption_ktoe(rows_a: list[tuple], rows_b: list[tuple], year: int) -> dict[str, float]:
    """Final energy by sector from ``EU_A``, plus bunker rows from ``EU_B``."""
    column_a = _header_years(rows_a)[year]
    industry = residential = tertiary = transport = 0.0
    section = ""
    for row in rows_a:
        label = "" if not row or row[0] is None else str(row[0]).strip()
        if label == "by sector":
            section = "sector"
            continue
        if label == "by fuel":
            section = ""
        if section != "sector":
            continue
        if label == "Industry":
            industry = _sheet_number(row, column_a)
        elif label == "Residential":
            residential = _sheet_number(row, column_a)
        elif label.startswith("Tertiary"):
            tertiary = _sheet_number(row, column_a)
        elif label.startswith("Transport"):
            transport = _sheet_number(row, column_a)
    column_b = _header_years(rows_b)[year]
    aviation = maritime = 0.0
    for row in rows_b:
        label = "" if not row or row[0] is None else str(row[0]).strip()
        if label == "International aviation":
            aviation = _sheet_number(row, column_b)
        elif label == "International maritime":
            maritime = _sheet_number(row, column_b)
    return {
        "industry": industry,
        "buildings": residential + tertiary,
        "transport": transport,
        "aviation": aviation,
        "maritime": maritime,
    }


def _served_mwh(network, names: pd.Index) -> float:
    """Annual load energy, without energy supplied by load shedding."""
    if len(names) == 0:
        return 0.0
    demanded = _annual_mwh(network, names)
    buses = pd.Index(network.loads.loc[list(names), "bus"].unique())
    on_bus = network.loads.index[network.loads.bus.isin(buses)]
    bus_demand = _annual_mwh(network, on_bus)
    generators = network.generators.index[
        network.generators.carrier.astype(str).eq("load")
        & network.generators.bus.isin(buses)
    ]
    shed = 0.0
    if len(generators):
        energy = _dispatched(network, network.generators_t.p, generators)
        if len(energy):
            shed = float(energy.clip(lower=0.0).sum())
    if bus_demand > 1e-6:
        shed *= demanded / bus_demand
    return demanded - shed


def load_eu_sheet(year: int) -> dict[str, dict[str, float] | float]:
    """Capacity, generation, energy CO2 and sectoral final energy from the EU sheets."""
    import openpyxl

    workbook = openpyxl.load_workbook(REFERENCE_WORKBOOK, read_only=True, data_only=True)
    try:
        rows = list(workbook["EU_B"].iter_rows(values_only=True))
        rows_a = list(workbook["EU_A"].iter_rows(values_only=True))
    finally:
        workbook.close()
    column = _header_years(rows)[year]
    consumption = _consumption_ktoe(rows_a, rows, year)
    capacity = {plant: 0.0 for plant in PLANT_LABELS}
    generation = {plant: 0.0 for plant in PLANT_LABELS}
    domestic = bunkers = 0.0
    section = ""
    for row in rows:
        label = "" if not row or row[0] is None else str(row[0]).strip()
        if label.startswith("Gross Electricity generation"):
            section = "generation"
            continue
        if label.startswith("Net Installed Power Capacity"):
            section = "capacity"
            continue
        if label == "TRANSPORT":
            section = ""
        if label.startswith("Domestic energy-related CO2 Emissions"):
            domestic = _sheet_number(row, column)
        elif label.startswith("International bunkers emissions"):
            bunkers = _sheet_number(row, column)
        if section == "capacity" and label in PLANT_ROWS:
            capacity[PLANT_ROWS[label]] = _sheet_number(row, column)
        elif section == "generation" and label in GENERATION_ROWS:
            generation[GENERATION_ROWS[label]] = _sheet_number(row, column)
    return {
        "capacity_mw": capacity,
        "generation_gwh": generation,
        "energy_co2_mt": domestic + bunkers,
        "consumption_ktoe": consumption,
    }


def compare_network(network, year: int) -> pd.DataFrame:
    """EU_B reference against the solved BAU."""
    sheet = load_eu_sheet(year)
    present = set(network.buses.country.dropna().astype(str).unique())
    rows = []
    for plant, label in PLANT_LABELS.items():
        reference_mw = float(sheet["capacity_mw"][plant])
        model_mw = sum(
            _electric_mw(network, country, plant)
            for country in present
            if country not in {"", "nan", "EU"}
        )
        rows.append(
            _row(year, EU, "capacity", label, "GW", reference_mw / 1e3, model_mw / 1e3)
        )
        reference_gwh = float(sheet["generation_gwh"][plant])
        model_twh = sum(
            _generation_twh(network, country, plant)
            for country in present
            if country not in {"", "nan", "EU"}
        )
        rows.append(
            _row(
                year,
                EU,
                "generation",
                label,
                "TWh",
                reference_gwh * GWH_TO_TWH,
                model_twh,
            )
        )
    countries = [country for country in present if country not in {"", "nan", "EU"}]
    for key, label, carriers in CONSUMPTION_SECTORS:
        reference_twh = float(sheet["consumption_ktoe"][key]) * KTOE_TO_MWH * MWH_TO_TWH
        model_mwh = sum(
            _served_mwh(network, _loads(network, country, carriers)) for country in countries
        )
        rows.append(
            _row(
                year,
                EU,
                "consumption",
                label,
                "TWh",
                reference_twh,
                model_mwh * MWH_TO_TWH,
            )
        )
    model_mt = annual_co2_tonnes(network)[0] / 1e6
    rows.append(
        _row(
            year,
            EU,
            "emissions",
            "Energy CO2",
            "Mt",
            float(sheet["energy_co2_mt"]),
            model_mt,
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
