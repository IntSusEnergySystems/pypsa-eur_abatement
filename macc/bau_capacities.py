# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""BAU power capacities from the EU Reference Scenario 2020 workbook.

The BAU solve keeps the reference fleet and cannot add the investments that
the mitigation scenarios are free to choose. Capacities are net installed
power in the ``*_B`` country sheets, in MW. A link's ``p_nom`` is fuel input,
so its electric capacity is ``p_nom * efficiency``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macc.common import COUNTRIES, MACC_DIR, REFERENCE_WORKBOOK, YEARS  # noqa: E402

LOGGER = logging.getLogger(__name__)

CAPACITY_CSV = MACC_DIR / "data" / "ref2020_power_capacity.csv"
SHEET_TO_COUNTRY = {"EL": "GR"}
# Leaf rows inside "Net Installed Power Capacity". Parent totals are skipped.
PLANT_ROWS = {
    "Nuclear energy": "nuclear",
    "Biomass-waste (including biogas and waste gas)": "biomass",
    "Lakes": "hydro_lakes",
    "Run of river": "ror",
    "Wind onshore": "onwind",
    "Wind offshore": "offwind",
    "Solar": "solar",
    "Geothermal heat and other renewables (tidal etc.)": "geothermal",
    "Solid fossil fuels": "coal",
    "Petroleum products": "oil",
    "Natural and manufactured gases": "gas",
    "Hydrogen and synthetic hydrocarbons": "hydrogen_power",
}
# These links are built with no existing capacity. They are the supply path
# for the reference demand: low-voltage electricity, heat, and hydrogen for
# industry. Locking them at zero makes that demand impossible. Pipelines,
# batteries, thermal storage, DAC and the process-emissions vent stay frozen.
DEMAND_LINKS_LEFT_EXTENDABLE = {
    "electricity distribution grid",
    "rural air heat pump",
    "rural ground heat pump",
    "rural biomass boiler",
    "rural gas boiler",
    "rural oil boiler",
    "rural resistive heater",
    "urban central air heat pump",
    "urban central gas boiler",
    "urban central resistive heater",
    "urban decentral air heat pump",
    "urban decentral biomass boiler",
    "urban decentral gas boiler",
    "urban decentral oil boiler",
    "urban decentral resistive heater",
    "SMR",
    "H2 Electrolysis",
    "shipping methanol",
    "shipping hydrogen",
    "shipping LNG",
}
# Unlimited fuel markets. PyPSA-Eur adds them as extendable generators with
# no capital cost and the fuel price as the marginal cost. They are not
# power plants, so the fleet freeze must not pin them at zero.
PRIMARY_FUEL_GENERATORS = {"coal", "lignite", "oil primary", "uranium"}
# component table, carrier, True when p_nom is already electric MW
PLANT_COMPONENTS = {
    "nuclear": [("generators", "nuclear", True)],
    "biomass": [("links", "urban central solid biomass CHP", False)],
    "hydro_lakes": [("storage_units", "hydro", True)],
    "ror": [("generators", "ror", True)],
    "onwind": [("generators", "onwind", True)],
    "offwind": [
        ("generators", "offwind-ac", True),
        ("generators", "offwind-dc", True),
        ("generators", "offwind-float", True),
    ],
    "solar": [
        ("generators", "solar", True),
        ("generators", "solar rooftop", True),
        ("generators", "solar-hsat", True),
    ],
    "geothermal": [("generators", "geothermal", True)],
    "coal": [("links", "coal", False)],
    "oil": [("links", "oil", False)],
    "gas": [("links", "CCGT", False), ("links", "OCGT", False)],
    "hydrogen_power": [("links", "H2 turbine", False)],
}


def _header_years(rows: list[tuple]) -> dict[int, int]:
    for row in rows[:8]:
        located = {}
        for index, value in enumerate(row):
            if isinstance(value, (int, float)) and int(value) in YEARS:
                located[int(value)] = index
        if len(located) == len(YEARS):
            return located
    raise ValueError("The sheet has no 2025–2050 header row.")


def _country_code(sheet_name: str) -> str | None:
    if not sheet_name.endswith("_B"):
        return None
    code = sheet_name.removesuffix("_B")
    if code == "EU":
        return None
    return SHEET_TO_COUNTRY.get(code, code)


def parse_workbook(path: Path = REFERENCE_WORKBOOK) -> pd.DataFrame:
    """Return country, year, plant and capacity_mw from every country sheet."""
    import openpyxl

    if not path.exists():
        raise SystemExit(
            f"Missing {path}. Download ref2020_energy-transport-ghg.xlsx into macc/data/."
        )
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    records = []
    try:
        for sheet_name in workbook.sheetnames:
            country = _country_code(sheet_name)
            if country is None:
                continue
            rows = list(workbook[sheet_name].iter_rows(values_only=True))
            columns = _header_years(rows)
            in_capacity = False
            for row in rows:
                label = "" if row[0] is None else str(row[0]).strip()
                if label.startswith("Net Installed Power Capacity"):
                    in_capacity = True
                    continue
                if in_capacity and label == "TRANSPORT":
                    break
                plant = PLANT_ROWS.get(label)
                if not in_capacity or plant is None:
                    continue
                for year, column in columns.items():
                    value = row[column] if column < len(row) else None
                    capacity = 0.0 if value in {None, "", "-"} else float(value)
                    records.append(
                        {
                            "country": country,
                            "year": year,
                            "plant": plant,
                            "capacity_mw": capacity,
                        }
                    )
    finally:
        workbook.close()
    frame = pd.DataFrame(records)
    if frame.empty:
        raise SystemExit(f"{path} did not contain country capacity sheets.")
    return frame


def write_capacity_table(path: Path = CAPACITY_CSV) -> pd.DataFrame:
    frame = parse_workbook()
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    modelled = sorted(set(frame["country"]).intersection(COUNTRIES))
    skipped = sorted(set(frame["country"]).difference(COUNTRIES))
    print(f"Wrote {path.relative_to(MACC_DIR.parent)} ({len(frame)} rows)")
    print("Model countries: " + ", ".join(modelled))
    if skipped:
        print("Workbook countries left out of the model: " + ", ".join(skipped))
    return frame


def load_capacities(year: int, path: Path = CAPACITY_CSV) -> pd.DataFrame:
    if not path.exists():
        write_capacity_table(path)
    frame = pd.read_csv(path)
    return frame.loc[frame["year"] == year].copy()


def _matching(network, table: pd.DataFrame, carrier: str, country: str) -> pd.Index:
    subset = table.loc[table["carrier"] == carrier]
    if subset.empty:
        return subset.index
    if "bus" in subset.columns:
        bus = subset["bus"]
    else:
        bus = subset["bus1"].where(subset["bus1"].isin(network.buses.index), subset["bus0"])
    bus_country = bus.map(network.buses.country)
    return subset.index[bus_country.eq(country)]


def _electric_mw(table: pd.DataFrame, idx: pd.Index, direct: bool) -> pd.Series:
    power = table.loc[idx, "p_nom"].astype(float)
    if direct:
        return power
    return power * table.loc[idx, "efficiency"].astype(float)


def _set_electric(table: pd.DataFrame, idx: pd.Index, direct: bool, electric: pd.Series) -> None:
    if direct:
        table.loc[idx, "p_nom"] = electric.to_numpy()
        return
    efficiency = table.loc[idx, "efficiency"].astype(float).clip(lower=1e-6)
    table.loc[idx, "p_nom"] = (electric / efficiency).to_numpy()


def _lock(table: pd.DataFrame, idx: pd.Index) -> None:
    table.loc[idx, "p_nom_extendable"] = False
    power = table.loc[idx, "p_nom"].astype(float)
    if "p_nom_min" in table.columns:
        table.loc[idx, "p_nom_min"] = np.minimum(
            table.loc[idx, "p_nom_min"].astype(float).fillna(0.0), power
        )
    if "p_nom_max" in table.columns:
        ceiling = table.loc[idx, "p_nom_max"].astype(float)
        table.loc[idx, "p_nom_max"] = np.maximum(ceiling.fillna(power), power)


def _assign_plant(network, country: str, plant: str, target_mw: float) -> bool:
    pieces = []
    for table_name, carrier, direct in PLANT_COMPONENTS[plant]:
        table = getattr(network, table_name)
        idx = _matching(network, table, carrier, country)
        if len(idx):
            pieces.append((table, idx, direct))
    if not pieces:
        return False
    current = []
    for table, idx, direct in pieces:
        current.append(_electric_mw(table, idx, direct))
    existing = pd.concat(current)
    total = float(existing.sum())
    if total <= 1e-6:
        weights = pd.Series(0.0, index=existing.index)
        weights.iloc[0] = target_mw
    else:
        weights = existing / total * target_mw
    for table, idx, direct in pieces:
        _set_electric(table, idx, direct, weights.loc[idx])
        _lock(table, idx)
    return True


def _freeze_extendable(table: pd.DataFrame, nominal: str, extendable: str) -> None:
    if extendable not in table.columns:
        return
    mask = table[extendable].fillna(False).astype(bool)
    if nominal == "e_nom" and nominal in table.columns:
        mask &= np.isfinite(table[nominal].astype(float))
    if "carrier" in table.columns and nominal == "e_nom":
        mask &= ~table["carrier"].astype(str).eq("co2")
    if "carrier" in table.columns and nominal == "p_nom":
        # Heat vents are built with no capacity and a negative dispatch range
        # so surplus heat can leave the bus. Freezing them at zero makes any
        # surplus hour infeasible.
        vents = table["carrier"].astype(str).str.endswith("heat vent")
        mask &= ~vents
        fuels = table["carrier"].isin(PRIMARY_FUEL_GENERATORS)
        mask &= ~fuels
        empty = table[nominal].astype(float).fillna(0.0).le(1e-6)
        opened = table["carrier"].isin(DEMAND_LINKS_LEFT_EXTENDABLE) & empty
        mask &= ~opened
    chosen = table.index[mask]
    if not len(chosen):
        return
    table.loc[chosen, extendable] = False
    ceiling = nominal.replace("nom", "nom_max") if nominal != "s_nom" else "s_nom_max"
    floor = nominal.replace("nom", "nom_min") if nominal != "s_nom" else "s_nom_min"
    if ceiling in table.columns:
        table.loc[chosen, ceiling] = table.loc[chosen, nominal]
    if floor in table.columns:
        table.loc[chosen, floor] = table.loc[chosen, nominal]


def _relax_forced_fuel(network) -> None:
    """Keep biomass and biogas potentials as upper bounds.

    PyPSA-Eur forces unsustainable biogas and bioliquids to be used in full,
    and does the same for unsustainable solid biomass through a global
    equality. Biogas upgrading is frozen at zero capacity, so that forced
    production has nowhere to go.
    """
    minimum = network.generators["e_sum_min"].astype(float)
    chosen = network.generators.index[minimum.gt(0) & minimum.lt(1e30)]
    if len(chosen):
        network.generators.loc[chosen, "e_sum_min"] = 0.0
        LOGGER.info(
            "BAU drops the minimum annual energy on %s fuel generators.",
            len(chosen),
        )
    constraints = network.global_constraints
    if constraints.empty or "sense" not in constraints.columns:
        return
    must = constraints.index[
        constraints["type"].astype(str).eq("operational_limit")
        & constraints["sense"].astype(str).eq("==")
    ]
    if len(must):
        network.global_constraints.loc[must, "sense"] = "<="
        LOGGER.info(
            "BAU turns mandatory fuel limits into upper bounds: %s",
            ", ".join(map(str, must)),
        )


def apply_bau_capacities(network, year: int) -> None:
    """Fix the solved fleet to the reference capacities and stop further investment."""
    capacities = load_capacities(year)
    capacities = capacities.loc[capacities["country"].isin(COUNTRIES)]
    missing = []
    for row in capacities.itertuples(index=False):
        if row.country not in set(network.buses.country):
            continue
        found = _assign_plant(network, row.country, row.plant, float(row.capacity_mw))
        if not found and float(row.capacity_mw) > 1.0:
            missing.append(f"{row.country} {row.plant} {row.capacity_mw:.0f} MW")
    for table_name, nominal, extendable in (
        ("generators", "p_nom", "p_nom_extendable"),
        ("links", "p_nom", "p_nom_extendable"),
        ("storage_units", "p_nom", "p_nom_extendable"),
        ("stores", "e_nom", "e_nom_extendable"),
        ("lines", "s_nom", "s_nom_extendable"),
    ):
        table = getattr(network, table_name, None)
        if table is not None and not table.empty:
            _freeze_extendable(table, nominal, extendable)
    if missing:
        LOGGER.warning(
            "BAU capacities with no matching component: %s",
            "; ".join(missing),
        )
    _relax_forced_fuel(network)
    LOGGER.info("Applied EU Reference Scenario %s capacities to the BAU network.", year)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    write_capacity_table()


if __name__ == "__main__":
    main()
