# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""Apply EU Reference Scenario demand, generation and fuel supply to BAU.

GHG, GDP and import rows are not used. Population, the renovation rate,
renewable shares and transport activity are kept in the table. They are
already contained in the final-energy totals and in the generation mix, so
they are not applied a second time. International aviation and maritime
bunkers, from each country's ``_B`` sheet, set the kerosene and shipping loads.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd
from xarray import DataArray

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macc.bau_capacities import _matching  # noqa: E402
from macc.common import COUNTRIES, MACC_DIR, REFERENCE_WORKBOOK, YEARS  # noqa: E402

LOGGER = logging.getLogger(__name__)

BALANCE_CSV = MACC_DIR / "data" / "ref2020_country_balances.csv"
KTOE_TO_MWH = 11_630.0
GWH_TO_MWH = 1_000.0
SHEET_TO_COUNTRY = {"EL": "GR"}

INDUSTRY_LOADS = (
    "coal for industry",
    "gas for industry",
    "solid biomass for industry",
    "naphtha for industry",
    "industry methanol",
    "H2 for industry",
    "industry electricity",
    "low-temperature heat for industry",
)
# Transport (9) excludes international aviation and maritime. Road loads follow
# that domestic total. Bunker rows on the _B sheet set aviation and shipping.
TRANSPORT_LOADS = (
    "land transport oil",
    "land transport EV",
)
AVIATION_LOADS = ("kerosene for aviation",)
SHIPPING_LOADS = ("shipping oil",)
BUILDING_LOADS = (
    "rural heat",
    "urban central heat",
    "urban decentral heat",
    "electricity",
    "agriculture electricity",
    "agriculture heat",
    "agriculture machinery oil",
    "agriculture machinery electric",
)
ROAD_EV = ("land transport EV",)
ROAD_OIL = ("land transport oil",)

GENERATION = {
    "gen_nuclear_gwh": [("generators", "nuclear", True)],
    "gen_biomass_gwh": [
        ("links", "urban central solid biomass CHP", False),
        ("links", "urban central solid biomass CHP CC", False),
    ],
    "gen_hydro_lakes_gwh": [("storage_units", "hydro", True)],
    "gen_ror_gwh": [("generators", "ror", True)],
    "gen_onwind_gwh": [("generators", "onwind", True)],
    "gen_offwind_gwh": [
        ("generators", "offwind-ac", True),
        ("generators", "offwind-dc", True),
        ("generators", "offwind-float", True),
    ],
    "gen_solar_gwh": [
        ("generators", "solar", True),
        ("generators", "solar rooftop", True),
        ("generators", "solar-hsat", True),
    ],
    "gen_geothermal_gwh": [("generators", "geothermal", True)],
    "gen_coal_gwh": [("links", "coal", False), ("links", "coal CC", False)],
    "gen_oil_gwh": [("links", "oil", False)],
    "gen_gas_gwh": [
        ("links", "CCGT", False),
        ("links", "OCGT", False),
        ("links", "urban central gas CHP", False),
        ("links", "urban central gas CHP CC", False),
    ],
    "gen_hydrogen_gwh": [("links", "H2 turbine", False)],
}

# section, exact or prefix, variable, unit
KEEP = (
    ("policy", "Population (in million)", "population_million", "million"),
    ("policy", "Annual renovation rate", "renovation_rate_percent", "percent"),
    ("policy", "RES in Gross Final Energy Consumption", "res_share_percent", "percent"),
    ("policy", "RES-H&C share", "res_hc_share_percent", "percent"),
    ("policy", "RES-E share", "res_e_share_percent", "percent"),
    ("policy", "RES-T share", "res_t_share_percent", "percent"),
    ("final_sector", "Industry", "final_industry_ktoe", "ktoe"),
    ("final_sector", "Residential", "final_residential_ktoe", "ktoe"),
    ("final_sector", "Tertiary (8)", "final_tertiary_ktoe", "ktoe"),
    ("final_sector", "Transport (9)", "final_transport_ktoe", "ktoe"),
    ("final_fuel", "Solid fossil fuels", "final_solid_ktoe", "ktoe"),
    ("final_fuel", "Petroleum products", "final_oil_ktoe", "ktoe"),
    ("final_fuel", "Natural and manufactured gases", "final_gas_ktoe", "ktoe"),
    ("final_fuel", "Electricity", "final_electricity_ktoe", "ktoe"),
    ("final_fuel", "Heat (from CHP and District Heating)", "final_heat_ktoe", "ktoe"),
    ("final_fuel", "Biomass & waste (6)", "final_biomass_ktoe", "ktoe"),
    ("final_fuel", "Geothermal and solar heat", "final_geothermal_heat_ktoe", "ktoe"),
    ("final_fuel", "Ambient heat", "final_ambient_heat_ktoe", "ktoe"),
    ("final_fuel", "Hydrogen", "final_hydrogen_ktoe", "ktoe"),
    ("final_fuel", "Synthetic hydrocarbons", "final_synthetic_ktoe", "ktoe"),
    ("primary", "Solid fossil fuels", "primary_solid_ktoe", "ktoe"),
    ("primary", "Crude oil and petroleum products", "primary_oil_ktoe", "ktoe"),
    ("primary", "Natural and manufactured gases", "primary_gas_ktoe", "ktoe"),
    ("primary", "Biomass & Waste (6)", "primary_biomass_ktoe", "ktoe"),
    ("generation", "Nuclear energy", "gen_nuclear_gwh", "GWh"),
    ("generation", "Biomass-waste (including biogas and waste gas)", "gen_biomass_gwh", "GWh"),
    ("generation", "Lakes", "gen_hydro_lakes_gwh", "GWh"),
    ("generation", "Run of river", "gen_ror_gwh", "GWh"),
    ("generation", "Wind onshore", "gen_onwind_gwh", "GWh"),
    ("generation", "Wind offshore", "gen_offwind_gwh", "GWh"),
    ("generation", "Solar", "gen_solar_gwh", "GWh"),
    ("generation", "Geothermal heat, other renewables", "gen_geothermal_gwh", "GWh"),
    ("generation", "Solid fossil fuels", "gen_coal_gwh", "GWh"),
    ("generation", "Petroleum products", "gen_oil_gwh", "GWh"),
    ("generation", "Natural and manufactured gases", "gen_gas_gwh", "GWh"),
    ("generation", "Hydrogen and synthetic hydrocarbons", "gen_hydrogen_gwh", "GWh"),
    ("transport", "Passenger transport activity (Gpkm)", "transport_passenger_gpkm", "Gpkm"),
    ("transport", "Freight transport activity (Gtkm)", "transport_freight_gtkm", "Gtkm"),
    ("transport", "Final energy consumption in transport", "transport_energy_ktoe", "ktoe"),
    ("transport", "Energy demand for international bunkers", "bunker_ktoe", "ktoe"),
    ("transport", "International aviation", "bunker_aviation_ktoe", "ktoe"),
    ("transport", "International maritime", "bunker_maritime_ktoe", "ktoe"),
    ("transport", "Electricity in road transport", "road_electricity_percent", "percent"),
    ("transport", "Biofuels and biomethane in total fuels", "biofuel_share_percent", "percent"),
)


def _skipped(label: str) -> bool:
    text = label.lower()
    return any(word in text for word in ("ghg", "co2", "gdp", "import"))


def _section(label: str, current: str) -> str:
    if label.startswith("MACROECONOMIC") or label.startswith("POLICY"):
        return "policy"
    if label.startswith("Gross Available Energy (ktoe)"):
        return "primary"
    if label == "by sector":
        return "final_sector"
    if label == "by fuel":
        return "final_fuel"
    if label.startswith("Gross Electricity generation"):
        return "generation"
    if label.startswith("Net Installed Power Capacity"):
        return "capacity"
    if label == "TRANSPORT":
        return "transport"
    if label.startswith("DECARBONISATION"):
        return "skip"
    return current


def _country(sheet_name: str) -> str | None:
    if not (sheet_name.endswith("_A") or sheet_name.endswith("_B")):
        return None
    code = sheet_name[:-2]
    if code == "EU":
        return None
    return SHEET_TO_COUNTRY.get(code, code)


def _years(rows: list[tuple]) -> dict[int, int]:
    for row in rows[:8]:
        located = {}
        for index, value in enumerate(row):
            if isinstance(value, (int, float)) and int(value) in YEARS:
                located[int(value)] = index
        if len(located) == len(YEARS):
            return located
    raise ValueError("The sheet has no 2025–2050 header row.")


def _match(section: str, label: str) -> tuple[str, str] | None:
    for kept_section, prefix, variable, unit in KEEP:
        if section == kept_section and label.startswith(prefix):
            return variable, unit
    return None


def parse_balances(path: Path = REFERENCE_WORKBOOK) -> pd.DataFrame:
    import openpyxl

    if not path.exists():
        raise SystemExit(f"Missing {path}.")
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    records = []
    try:
        for sheet_name in workbook.sheetnames:
            country = _country(sheet_name)
            if country is None:
                continue
            rows = list(workbook[sheet_name].iter_rows(values_only=True))
            columns = _years(rows)
            section = ""
            for row in rows:
                label = "" if not row or row[0] is None else str(row[0]).strip()
                if not label:
                    continue
                section = _section(label, section)
                if _skipped(label):
                    continue
                matched = _match(section, label)
                if matched is None:
                    continue
                variable, unit = matched
                for year, column in columns.items():
                    value = row[column] if column < len(row) else None
                    if value in {None, "", "-"}:
                        continue
                    records.append(
                        {
                            "country": country,
                            "year": year,
                            "variable": variable,
                            "value": float(value),
                            "unit": unit,
                        }
                    )
    finally:
        workbook.close()
    frame = pd.DataFrame(records).drop_duplicates(["country", "year", "variable"])
    if frame.empty:
        raise SystemExit(f"{path} did not contain country balance rows.")
    return frame


def write_balance_table(path: Path = BALANCE_CSV) -> pd.DataFrame:
    frame = parse_balances()
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    print(f"Wrote {path.relative_to(MACC_DIR.parent)} ({len(frame)} rows)")
    return frame


def load_balances(year: int, path: Path = BALANCE_CSV) -> pd.DataFrame:
    if not path.exists():
        write_balance_table(path)
    frame = pd.read_csv(path)
    return frame.loc[frame["year"] == year].copy()


def _lookup(table: pd.DataFrame, country: str, variable: str) -> float | None:
    rows = table.loc[(table["country"] == country) & (table["variable"] == variable), "value"]
    if rows.empty:
        return None
    return float(rows.iloc[0])


def _loads(network, country: str, carriers: tuple[str, ...]) -> pd.Index:
    bus_country = network.loads.bus.map(network.buses.country)
    chosen = network.loads.index[
        network.loads.carrier.isin(carriers) & bus_country.eq(country)
    ]
    return chosen


def _annual_mwh(network, names: pd.Index) -> float:
    if len(names) == 0:
        return 0.0
    series = network.get_switchable_as_dense("Load", "p_set")[list(names)]
    weight = network.snapshot_weightings.objective
    return float(series.mul(weight, axis=0).sum().sum())


def _scale(network, names: pd.Index, target_mwh: float) -> float | None:
    current = _annual_mwh(network, names)
    if current == 0 or target_mwh < 0:
        return None
    factor = target_mwh / current
    listed = list(names)
    timed = [name for name in listed if name in network.loads_t.p_set.columns]
    if timed:
        network.loads_t.p_set.loc[:, timed] *= factor
    network.loads.loc[listed, "p_set"] *= factor
    return factor


def _scale_group(network, country: str, carriers: tuple[str, ...], target_mwh: float | None) -> None:
    if target_mwh is None:
        return
    names = _loads(network, country, carriers)
    if len(names) == 0 or _annual_mwh(network, names) == 0:
        if target_mwh > 1:
            LOGGER.warning(
                "%s has no %s load to scale to %.1f TWh",
                country,
                carriers[0],
                target_mwh / 1e6,
            )
        return
    factor = _scale(network, names, target_mwh)
    if factor is not None:
        LOGGER.info(
            "%s %s scaled by %.3f to %.1f TWh",
            country,
            ",".join(carriers[:2]),
            factor,
            target_mwh / 1e6,
        )


def _split_road(network, country: str, electric_share: float | None) -> None:
    if electric_share is None:
        return
    share = min(max(electric_share / 100.0, 0.0), 1.0)
    electric = _loads(network, country, ROAD_EV)
    oil = _loads(network, country, ROAD_OIL)
    total = _annual_mwh(network, electric.append(oil))
    if total <= 0:
        return
    _scale(network, electric, total * share)
    _scale(network, oil, total * (1.0 - share))
    _cover_peak(network, country, electric, "BEV charger")


def _cover_peak(network, country: str, loads: pd.Index, link_carrier: str) -> None:
    if len(loads) == 0 or link_carrier not in set(network.links.carrier):
        return
    profile = network.get_switchable_as_dense("Load", "p_set")[list(loads)].sum(axis=1)
    peak = float(profile.max())
    links = _matching(network, network.links, link_carrier, country)
    if len(links) == 0 or peak <= 0:
        return
    efficiency = float(network.links.loc[links[0], "efficiency"])
    needed = peak / max(efficiency, 1e-6)
    capacity = float(network.links.loc[links, "p_nom"].sum())
    if capacity < needed:
        network.links.loc[links[0], "p_nom"] = needed
        if "p_nom_max" in network.links.columns:
            network.links.loc[links[0], "p_nom_max"] = max(
                needed, float(network.links.loc[links[0], "p_nom_max"])
            )
        network.links.loc[links, "p_nom_extendable"] = False


def _components(network, country: str | None, specs: list[tuple[str, str, bool]]):
    found = []
    for table_name, carrier, direct in specs:
        table = getattr(network, table_name)
        if country is None:
            idx = table.index[table.carrier == carrier]
        else:
            idx = _matching(network, table, carrier, country)
        if len(idx):
            found.append((table_name, idx, direct))
    return found


def _remember(network, kind: str, item: dict) -> None:
    items = getattr(network, kind, [])
    items.append(item)
    setattr(network, kind, items)


def _queue_generation(network, country: str, variable: str, gwh: float | None) -> None:
    if gwh is None:
        return
    specs = GENERATION[variable]
    pieces = _components(network, country, specs)
    if not pieces:
        if gwh > 1:
            LOGGER.warning("%s has no component for %s (%.0f GWh)", country, variable, gwh)
        return
    _remember(
        network,
        "bau_generation_targets",
        {
            "name": f"{country}_{variable}",
            "pieces": [(table, list(idx), direct) for table, idx, direct in pieces],
            "target_mwh": gwh * GWH_TO_MWH,
        },
    )


def _queue_supply(network, name: str, generators: pd.Index, limit_mwh: float) -> None:
    if len(generators) == 0:
        return
    _remember(
        network,
        "bau_supply_caps",
        {"name": name, "generators": list(generators), "limit_mwh": max(limit_mwh, 0.0)},
    )


def apply_bau_pathway(network, year: int) -> None:
    """Scale BAU demand to the reference final energy and queue its energy limits."""
    balances = load_balances(year)
    present = set(network.buses.country.dropna().unique())
    for country in COUNTRIES:
        if country not in present:
            continue
        industry = _lookup(balances, country, "final_industry_ktoe")
        residential = _lookup(balances, country, "final_residential_ktoe")
        tertiary = _lookup(balances, country, "final_tertiary_ktoe")
        transport = _lookup(balances, country, "final_transport_ktoe")
        _scale_group(
            network,
            country,
            INDUSTRY_LOADS,
            None if industry is None else industry * KTOE_TO_MWH,
        )
        _scale_group(
            network,
            country,
            TRANSPORT_LOADS,
            None if transport is None else transport * KTOE_TO_MWH,
        )
        buildings = None
        if residential is not None or tertiary is not None:
            buildings = ((residential or 0.0) + (tertiary or 0.0)) * KTOE_TO_MWH
        _scale_group(network, country, BUILDING_LOADS, buildings)
        _split_road(network, country, _lookup(balances, country, "road_electricity_percent"))
        aviation = _lookup(balances, country, "bunker_aviation_ktoe")
        maritime = _lookup(balances, country, "bunker_maritime_ktoe")
        _scale_group(
            network,
            country,
            AVIATION_LOADS,
            None if aviation is None else aviation * KTOE_TO_MWH,
        )
        _scale_group(
            network,
            country,
            SHIPPING_LOADS,
            None if maritime is None else maritime * KTOE_TO_MWH,
        )
        _cover_peak(network, country, _loads(network, country, AVIATION_LOADS), "kerosene for aviation")
        _cover_peak(network, country, _loads(network, country, SHIPPING_LOADS), "shipping oil")
        for variable in GENERATION:
            _queue_generation(network, country, variable, _lookup(balances, country, variable))
        gas = _lookup(balances, country, "primary_gas_ktoe")
        biomass = _lookup(balances, country, "primary_biomass_ktoe")
        if gas is not None:
            _queue_supply(
                network,
                f"{country}_primary_gas",
                _matching(network, network.generators, "gas", country),
                gas * KTOE_TO_MWH,
            )
        if biomass is not None:
            names = network.generators.index[
                network.generators.carrier.isin(["solid biomass", "unsustainable solid biomass"])
                & network.generators.bus.map(network.buses.country).eq(country)
            ]
            _queue_supply(network, f"{country}_primary_biomass", names, biomass * KTOE_TO_MWH)

    modelled = balances.loc[balances["country"].isin(present)]
    for variable, carrier in (
        ("primary_solid_ktoe", "coal"),
        ("primary_oil_ktoe", "oil primary"),
    ):
        total = modelled.loc[modelled["variable"] == variable, "value"].sum()
        generators = network.generators.index[network.generators.carrier == carrier]
        _queue_supply(network, f"EU_{variable}", generators, total * KTOE_TO_MWH)
    LOGGER.info("Applied EU Reference Scenario %s demand and energy limits.", year)


def _weighted(variable, snapshots, weight: pd.Series):
    data = DataArray(
        weight.reindex(snapshots).to_numpy(),
        coords={"snapshot": list(snapshots)},
        dims=["snapshot"],
    )
    return (variable * data).sum()


def _max_mwh(network, table_name: str, names: list[str], direct: bool) -> float:
    weight = network.snapshot_weightings.objective
    if table_name == "generators":
        table = network.generators
        profile = network.get_switchable_as_dense("Generator", "p_max_pu")
    elif table_name == "storage_units":
        table = network.storage_units
        profile = network.get_switchable_as_dense("StorageUnit", "p_max_pu")
    else:
        table = network.links
        profile = network.get_switchable_as_dense("Link", "p_max_pu")
    profile = profile.reindex(columns=names).fillna(1.0)
    power = table.loc[names, "p_nom"].astype(float)
    if not direct:
        power = power * table.loc[names, "efficiency"].astype(float).clip(lower=1e-6)
    return float(profile.mul(power, axis=1).mul(weight, axis=0).sum().sum())


def add_bau_energy_constraints(network, snapshots) -> None:
    """Constrain BAU generation and primary fuel supply to the reference values."""
    weight = network.snapshot_weightings.objective
    for item in getattr(network, "bau_generation_targets", []):
        expressions = []
        available = 0.0
        for table_name, names, direct in item["pieces"]:
            available += _max_mwh(network, table_name, names, direct)
            if table_name == "generators":
                variable = network.model["Generator-p"].sel(name=names, snapshot=snapshots)
                expressions.append(_weighted(variable, snapshots, weight))
            elif table_name == "storage_units":
                variable = network.model["StorageUnit-p"].sel(name=names, snapshot=snapshots)
                expressions.append(_weighted(variable, snapshots, weight))
            else:
                variable = network.model["Link-p"].sel(name=names, snapshot=snapshots)
                efficiency = DataArray(
                    network.links.loc[names, "efficiency"].astype(float).clip(lower=1e-6).to_numpy(),
                    coords={"name": names},
                    dims=["name"],
                )
                expressions.append(_weighted(variable * efficiency, snapshots, weight))
        target = item["target_mwh"]
        if available > 0 and target > available:
            LOGGER.warning(
                "%s generation %.0f GWh is above the weather-limited maximum %.0f GWh",
                item["name"],
                target / GWH_TO_MWH,
                available / GWH_TO_MWH,
            )
            target = available
        lhs = expressions[0]
        for expression in expressions[1:]:
            lhs = lhs + expression
        network.model.add_constraints(lhs, "==", target, name=f"BAU-gen-{item['name']}")

    for item in getattr(network, "bau_supply_caps", []):
        variable = network.model["Generator-p"].sel(
            name=item["generators"], snapshot=snapshots
        )
        lhs = _weighted(variable, snapshots, weight)
        network.model.add_constraints(
            lhs, "<=", item["limit_mwh"], name=f"BAU-supply-{item['name']}"
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    write_balance_table()


if __name__ == "__main__":
    main()
