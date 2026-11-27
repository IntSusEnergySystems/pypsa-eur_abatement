# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""Compare each planning year's BAU with the mitigation scenarios of that year.

Once a year's BAU is solved, it is compared with the EU reference sheet.
Each mitigation scenario of that year adds a bar when its network exists.
A scenario whose annual cost is more than five times that year's BAU is
left out.
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
    KTOE_TO_MWH,
    _annual_mwh,
)
from macc.common import (
    REFERENCE_WORKBOOK,
    RESULTS_DIR,
    STEPS,
    YEARS,
    scenario_name,
    solved_network_path,
)
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
# Residential and tertiary are one buildings total. Maritime includes every
# shipping fuel, so a mitigation run's methanol is not dropped.
CONSUMPTION_SECTORS = (
    ("industry", "Industry"),
    ("buildings", "Residential and tertiary"),
    ("transport", "Transport"),
    ("aviation", "International aviation"),
    ("maritime", "International maritime"),
)
# Same fleet as the BAU capacity fix, plus the capture and CHP units a
# mitigation run is allowed to build. This does not change the BAU freeze.
COMPARISON_COMPONENTS = {
    **PLANT_COMPONENTS,
    "biomass": [
        *PLANT_COMPONENTS["biomass"],
        ("links", "urban central solid biomass CHP CC", False),
    ],
    "coal": [*PLANT_COMPONENTS["coal"], ("links", "coal CC", False)],
    "gas": [
        *PLANT_COMPONENTS["gas"],
        ("links", "CCGT CC", False),
        ("links", "urban central gas CHP", False),
        ("links", "urban central gas CHP CC", False),
    ],
}
SERIES_ORDER = ("EU", "BAU", "MACC_1", "MACC_2", "MACC_3", "MACC_4", "MACC_5", "MACC_6")
SERIES_LABELS = {
    "EU": "EU reference",
    "BAU": "BAU",
    "MACC_1": "MACC 1 (10% CO2 cap decrease vs BAU)",
    "MACC_2": "MACC 2 (20% CO2 cap decrease vs BAU)",
    "MACC_3": "MACC 3 (40% CO2 cap decrease vs BAU)",
    "MACC_4": "MACC 4 (60% CO2 cap decrease vs BAU)",
    "MACC_5": "MACC 5 (80% CO2 cap decrease vs BAU)",
    "MACC_6": "MACC 6 (100% CO2 cap decrease vs BAU)",
}
# Kept so older callers still find the mitigation names.
STEP_LABELS = {key: value for key, value in SERIES_LABELS.items() if key != "EU"}
# A solved run is left out of the plots when it costs more than this multiple of BAU.
COST_LIMIT = 5.0
COST_GROUPS = {
    "Solar": ["solar", "solar rooftop", "solar-hsat"],
    "Onshore wind": ["onwind"],
    "Offshore wind": ["offwind-ac", "offwind-dc", "offwind-float"],
    "Nuclear": ["nuclear"],
    "Coal": ["coal", "lignite", "coal CC"],
    "Gas": ["CCGT", "OCGT", "CCGT CC", "gas", "urban central gas CHP", "urban central gas CHP CC"],
    "Oil": ["oil", "oil primary"],
    "Hydro": ["ror", "hydro"],
    "Biomass": ["urban central solid biomass CHP", "urban central solid biomass CHP CC"],
    "Electrolysis": ["H2 Electrolysis"],
    "Battery": ["battery", "home battery"],
    "Hydrogen": ["H2 Store", "H2 turbine"],
    "Heat pumps": [
        "rural air heat pump",
        "rural ground heat pump",
        "urban central air heat pump",
        "urban decentral air heat pump",
    ],
}


def _metric(year, step, reduction, group, item, unit, value) -> dict:
    return {
        "year": year,
        "scenario": f"{year}-{step}",
        "step": step,
        "reduction": reduction,
        "label": SERIES_LABELS[step],
        "group": group,
        "item": item,
        "unit": unit,
        "value": value,
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


def _electric_mw(network, country: str, plant: str, components=None) -> float:
    total = 0.0
    for table_name, carrier, direct in (components or PLANT_COMPONENTS)[plant]:
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


def _generation_twh(network, country: str, plant: str, components=None) -> float:
    """Electricity from the plant components, in TWh."""
    total = 0.0
    for table_name, carrier, direct in (components or PLANT_COMPONENTS)[plant]:
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


def _countries(network) -> list[str]:
    present = set(network.buses.country.dropna().astype(str).unique())
    return [country for country in present if country not in {"", "nan", "EU"}]


def _sector_loads(network, country: str, sector: str) -> pd.Index:
    """Loads that belong to one consumption sector in BAU or a mitigation run."""
    carriers = network.loads.carrier.astype(str)
    bus_country = network.loads.bus.map(network.buses.country).astype(str)
    in_country = bus_country.eq(country)
    if sector == "industry":
        chosen = carriers.str.contains("industry", case=False) | carriers.eq("NH3")
    elif sector == "buildings":
        chosen = carriers.isin(BUILDING_LOADS)
    elif sector == "transport":
        chosen = carriers.str.startswith("land transport")
    elif sector == "aviation":
        chosen = carriers.isin(AVIATION_LOADS)
    elif sector == "maritime":
        chosen = carriers.str.startswith("shipping")
    else:
        chosen = pd.Series(False, index=network.loads.index)
    return network.loads.index[chosen & in_country]


def scenario_metrics(network, year: int, step: str, reduction: float) -> pd.DataFrame:
    """Capacity, generation, CO2 and sectoral final energy for one solved run."""
    countries = _countries(network)
    rows = []
    for plant, label in PLANT_LABELS.items():
        capacity_gw = sum(
            _electric_mw(network, country, plant, COMPARISON_COMPONENTS)
            for country in countries
        ) / 1e3
        generation_twh = sum(
            _generation_twh(network, country, plant, COMPARISON_COMPONENTS)
            for country in countries
        )
        rows.append(
            _metric(year, step, reduction, "capacity", label, "GW", capacity_gw)
        )
        rows.append(
            _metric(year, step, reduction, "generation", label, "TWh", generation_twh)
        )
    for sector, label in CONSUMPTION_SECTORS:
        served_mwh = sum(
            _served_mwh(network, _sector_loads(network, country, sector))
            for country in countries
        )
        rows.append(
            _metric(
                year,
                step,
                reduction,
                "consumption",
                label,
                "TWh",
                served_mwh * MWH_TO_TWH,
            )
        )
    emissions_mt = annual_co2_tonnes(network)[0] / 1e6
    rows.append(_metric(year, step, reduction, "emissions", "CO2", "Mt", emissions_mt))
    rows.extend(_technology_rows(network, year, step, reduction))
    return pd.DataFrame(rows)


def _carrier_sum(series: pd.Series | pd.DataFrame) -> pd.Series:
    if series is None or len(series) == 0:
        return pd.Series(dtype=float)
    if isinstance(series, pd.DataFrame):
        series = series.stack()
    if isinstance(series.index, pd.MultiIndex) and "carrier" in series.index.names:
        series = series.groupby(level="carrier").sum()
    return series


def _grouped(series: pd.Series | pd.DataFrame) -> dict[str, float]:
    values = _carrier_sum(series)
    totals = {}
    for label, names in COST_GROUPS.items():
        present = [name for name in names if name in values.index]
        totals[label] = float(values.loc[present].sum()) if present else 0.0
    return totals


def _fuel_twh(network, carriers: set[str]) -> float:
    generators = network.generators
    names = generators.index[generators.carrier.astype(str).isin(carriers)]
    energy = _dispatched(network, network.generators_t.p, names)
    if len(energy) == 0:
        return 0.0
    return float(energy.sum()) * MWH_TO_TWH


def _store_gwh(network, carriers: set[str]) -> float:
    stores = network.stores
    names = stores.index[stores.carrier.astype(str).isin(carriers)]
    if len(names) == 0:
        return 0.0
    column = "e_nom_opt" if "e_nom_opt" in stores.columns else "e_nom"
    return float(stores.loc[names, column].astype(float).sum()) / 1e3


def _technology_rows(network, year: int, step: str, reduction: float) -> list[dict]:
    """Fossil use, electrolysers, storage, investment and operating cost."""
    rows = [
        _metric(year, step, reduction, "fossil", "Coal", "TWh", _fuel_twh(network, {"coal", "lignite"})),
        _metric(year, step, reduction, "fossil", "Gas", "TWh", _fuel_twh(network, {"gas"})),
        _metric(
            year,
            step,
            reduction,
            "fossil",
            "Oil",
            "TWh",
            _fuel_twh(network, {"oil", "oil primary"}),
        ),
    ]
    electrolysis = network.links.index[network.links.carrier.astype(str).eq("H2 Electrolysis")]
    column = "p_nom_opt" if "p_nom_opt" in network.links.columns else "p_nom"
    electrolyser_gw = 0.0
    if len(electrolysis):
        electrolyser_gw = float(network.links.loc[electrolysis, column].astype(float).sum()) / 1e3
    rows.append(
        _metric(year, step, reduction, "electrolyser", "Electrolysis", "GW", electrolyser_gw)
    )
    hydro = network.storage_units
    pumped = hydro.index[hydro.carrier.astype(str).eq("PHS")]
    pumped_gwh = 0.0
    if len(pumped) and "max_hours" in hydro.columns:
        power = hydro.loc[pumped, column].astype(float)
        pumped_gwh = float((power * hydro.loc[pumped, "max_hours"].astype(float)).sum()) / 1e3
    for label, gwh in (
        ("Battery", _store_gwh(network, {"battery", "home battery"})),
        ("Hydrogen", _store_gwh(network, {"H2 Store"})),
        ("Heat storage", _store_gwh(network, {
            "rural water tanks",
            "urban central water pits",
            "urban central water tanks",
            "urban decentral water tanks",
        })),
        ("Pumped hydro", pumped_gwh),
    ):
        rows.append(_metric(year, step, reduction, "storage", label, "GWh", gwh))
    for label, value in _grouped(network.statistics.capex()).items():
        rows.append(_metric(year, step, reduction, "investment", label, "M€/year", value / 1e6))
    for label, value in _grouped(network.statistics.opex()).items():
        rows.append(_metric(year, step, reduction, "operating", label, "M€/year", value / 1e6))
    return rows


def eu_reference_metrics(year: int) -> pd.DataFrame:
    """EU sheet values on the same rows as a solved scenario."""
    sheet = load_eu_sheet(year)
    rows = []
    for plant, label in PLANT_LABELS.items():
        rows.append(
            _metric(year, "EU", pd.NA, "capacity", label, "GW", float(sheet["capacity_mw"][plant]) / 1e3)
        )
        rows.append(
            _metric(
                year,
                "EU",
                pd.NA,
                "generation",
                label,
                "TWh",
                float(sheet["generation_gwh"][plant]) * GWH_TO_TWH,
            )
        )
    for key, label in CONSUMPTION_SECTORS:
        rows.append(
            _metric(
                year,
                "EU",
                pd.NA,
                "consumption",
                label,
                "TWh",
                float(sheet["consumption_ktoe"][key]) * KTOE_TO_MWH * MWH_TO_TWH,
            )
        )
    rows.append(_metric(year, "EU", pd.NA, "emissions", "CO2", "Mt", float(sheet["energy_co2_mt"])))
    return pd.DataFrame(rows)


def _recorded_cost(name: str) -> float | None:
    path = RESULTS_DIR / "scenario_summary.csv"
    if not path.exists():
        return None
    frame = pd.read_csv(path)
    rows = frame.loc[frame["scenario"] == name, "system_cost_eur_per_year"]
    if rows.empty:
        return None
    return float(rows.iloc[0])


def keep_scenario(year: int, step: str) -> bool:
    """False when a mitigation run costs more than five times that year's BAU."""
    if step == "BAU":
        return solved_network_path(scenario_name(year, 0.0)).exists()
    name = f"{year}-{step}"
    if not solved_network_path(name).exists():
        return False
    bau_cost = _recorded_cost(f"{year}-BAU")
    cost = _recorded_cost(name)
    if bau_cost is None or cost is None or bau_cost <= 0:
        return True
    if cost > COST_LIMIT * bau_cost:
        print(f"Leave {name} out of the plots: its cost is more than 5 times {year}-BAU.")
        return False
    return True


def missing_scenarios(year: int) -> list[str]:
    """Scenario names of one planning year that have no solved network yet."""
    missing = []
    for _step, reduction in STEPS:
        name = scenario_name(year, reduction)
        if not solved_network_path(name).exists():
            missing.append(name)
    return missing


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
    for key, label in CONSUMPTION_SECTORS:
        reference_twh = float(sheet["consumption_ktoe"][key]) * KTOE_TO_MWH * MWH_TO_TWH
        model_mwh = sum(
            _served_mwh(network, _sector_loads(network, country, key))
            for country in countries
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
    """EU reference, BAU and every finished mitigation run that stays within the cost limit.

    A year starts as soon as its BAU network exists. Mitigation bars are added
    as those networks appear. Runs above five times the BAU cost are omitted.
    """
    frames = []
    for year in YEARS:
        if not solved_network_path(scenario_name(year, 0.0)).exists():
            continue
        frames.append(eu_reference_metrics(year))
        print(f"Read the EU reference sheet for {year}")
        for step, reduction in STEPS:
            if not keep_scenario(year, step):
                continue
            name = scenario_name(year, reduction)
            network = pypsa.Network(solved_network_path(name))
            frames.append(scenario_metrics(network, year, step, reduction))
            print(f"Read {name}")
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
