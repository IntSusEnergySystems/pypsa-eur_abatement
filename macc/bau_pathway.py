# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""Apply EU Reference Scenario demand to BAU.

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

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macc.bau_capacities import _matching  # noqa: E402
from macc.common import COUNTRIES, MACC_DIR, REFERENCE_WORKBOOK, YEARS  # noqa: E402

LOGGER = logging.getLogger(__name__)

BALANCE_CSV = MACC_DIR / "data" / "ref2020_country_balances.csv"
KTOE_TO_MWH = 11_630.0
SHEET_TO_COUNTRY = {"EL": "GR"}

INDUSTRY_LOADS = (
    "coal for industry",
    "gas for industry",
    "solid biomass for industry",
    "naphtha for industry",
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
    _cover_peak(network, country, oil, "land transport oil")


def _clip_load_at_zero(network, names: pd.Index) -> None:
    """Drop a negative load, which would inject energy onto its bus."""
    if len(names) == 0:
        return
    listed = list(names)
    network.loads.loc[listed, "p_set"] = network.loads.loc[listed, "p_set"].clip(lower=0.0)
    timed = [name for name in listed if name in network.loads_t.p_set.columns]
    if timed:
        network.loads_t.p_set.loc[:, timed] = network.loads_t.p_set.loc[:, timed].clip(lower=0.0)


def _open_process_vent(network, country: str) -> None:
    """Let process CO2 reach the atmosphere. Capture stays at its frozen size."""
    subset = network.links.loc[network.links.carrier.eq("process emissions")]
    if subset.empty:
        return
    vents = subset.index[subset.bus0.map(network.buses.country).eq(country)]
    if len(vents) == 0:
        return
    injected = 0.0
    loads = _loads(network, country, ("process emissions",))
    if len(loads):
        profile = network.get_switchable_as_dense("Load", "p_set")[list(loads)].sum(axis=1)
        injected += float((-profile).clip(lower=0.0).max())
    naphtha_loads = _loads(network, country, ("naphtha for industry",))
    naphtha_links = _matching(network, network.links, "naphtha for industry", country)
    if len(naphtha_loads) and len(naphtha_links):
        naphtha = network.get_switchable_as_dense("Load", "p_set")[list(naphtha_loads)].sum(axis=1)
        factor = float(network.links.loc[naphtha_links[0], "efficiency2"])
        if factor > 0:
            injected += float((naphtha.clip(lower=0.0) * factor).max())
    if injected <= 0:
        return
    current = float(network.links.loc[vents, "p_nom"].astype(float).sum())
    if current >= injected:
        return
    network.links.loc[vents[0], "p_nom"] = injected
    if "p_nom_max" in network.links.columns:
        ceiling = float(network.links.loc[vents[0], "p_nom_max"])
        if pd.isna(ceiling):
            ceiling = 0.0
        network.links.loc[vents[0], "p_nom_max"] = max(injected, ceiling)
    network.links.loc[vents, "p_nom_extendable"] = False


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


def _zero_loads(network, loads: pd.Index) -> None:
    if len(loads) == 0:
        return
    listed = list(loads)
    network.loads.loc[listed, "p_set"] = 0.0
    timed = [name for name in listed if name in network.loads_t.p_set.columns]
    if timed:
        network.loads_t.p_set.loc[:, timed] = 0.0


def _disable_ammonia(network) -> None:
    """Remove BAU ammonia demand. Haber-Bosch stays at its frozen capacity."""
    loads = network.loads.index[network.loads.carrier.astype(str).eq("NH3")]
    _zero_loads(network, loads)
    LOGGER.info("BAU ammonia demand is turned off.")


def _disable_methanol(network) -> None:
    """Remove every BAU methanol load, including industry and shipping."""
    carriers = network.loads.carrier.astype(str)
    loads = network.loads.index[carriers.str.contains("methanol", case=False)]
    _zero_loads(network, loads)
    LOGGER.info("BAU methanol demand is turned off.")


def _oil_only_shipping(network) -> None:
    """Maritime fuel is oil in every BAU year. Drop methanol, hydrogen and LNG."""
    carriers = ("shipping methanol", "shipping hydrogen", "shipping LNG")
    loads = network.loads.index[network.loads.carrier.isin(carriers)]
    if len(loads) == 0:
        return
    listed = list(loads)
    network.loads.loc[listed, "p_set"] = 0.0
    timed = [name for name in listed if name in network.loads_t.p_set.columns]
    if timed:
        network.loads_t.p_set.loc[:, timed] = 0.0
    LOGGER.info("BAU shipping demand is oil only.")


def apply_bau_pathway(network, year: int) -> None:
    """Scale BAU demand to the reference final energy."""
    _disable_ammonia(network)
    _disable_methanol(network)
    _oil_only_shipping(network)
    balances = load_balances(year)
    present = set(network.buses.country.dropna().unique())
    for country in COUNTRIES:
        if country not in present:
            continue
        # A negative hydrogen load would force hydrogen onto the bus. The
        # pipelines and turbines that could absorb it stay at their current size.
        _clip_load_at_zero(network, _loads(network, country, ("H2 for industry",)))
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
        for carrier in (
            "coal for industry",
            "gas for industry",
            "solid biomass for industry",
            "naphtha for industry",
            "agriculture machinery oil",
        ):
            _cover_peak(network, country, _loads(network, country, (carrier,)), carrier)
        _open_process_vent(network, country)

    LOGGER.info("Applied EU Reference Scenario %s demand.", year)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    write_balance_table()


if __name__ == "__main__":
    main()
