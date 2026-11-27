# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""Set cross-border transmission to the capacities operating in 2025.

AC capacities are the ENTSO-E ERAA 2024 National Trends net transfer
capacities for 2026, the earliest year published in that edition
(https://www.entsoe.eu/eraa/2024/modelling-data/). Each border uses the
lower of the two directions, in MW. DC capacities are the same source.
Spain–France is the exception: Red Eléctrica puts the whole border at
2,800 MW, of which the operating INELFE link is 2,000 MW, so the AC
border is 800 MW. The Bay of Biscay link is due in 2028 and is left out.

An AC line is one bidirectional corridor. A DC link keeps one component
in each direction. Mitigation solves can still expand them. The BAU
freeze, which runs after this, closes that expansion.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from macc.common import MACC_DIR

LOGGER = logging.getLogger(__name__)

TRANSMISSION_CSV = MACC_DIR / "data" / "transmission_2025.csv"
# Same headroom as config.default.yaml lines.s_nom_max_extension and
# links.p_nom_max_extension. Applied again because the existing capacity changes.
AC_EXTENSION_MW = 20_000.0
DC_EXTENSION_MW = 30_000.0


def _country(bus: str) -> str:
    return str(bus)[:2]


def _parallel(values: pd.Series) -> float:
    values = values.astype(float)
    values = values[values > 0]
    if values.empty:
        return np.nan
    return float(1.0 / (1.0 / values).sum())


def _extension(old_capacity: float, old_maximum: float, default: float) -> float:
    if np.isfinite(old_maximum) and np.isfinite(old_capacity):
        headroom = float(old_maximum) - float(old_capacity)
        if headroom > 0:
            return headroom
    return default


def _scale_impedance(table: pd.DataFrame, name: str, column: str, new_value: float) -> None:
    if column not in table.columns or not np.isfinite(new_value):
        return
    old_value = float(table.at[name, column])
    if old_value <= 0 or not np.isfinite(old_value):
        table.at[name, column] = new_value
        return
    factor = new_value / old_value
    table.at[name, column] = new_value
    for derived in (f"{column}_pu", f"{column}_pu_eff"):
        if derived in table.columns:
            current = float(table.at[name, derived])
            if np.isfinite(current):
                table.at[name, derived] = current * factor


def apply_existing_transmission(network) -> None:
    """Keep 2025 AC lines and DC links and set their existing capacity."""
    table = pd.read_csv(TRANSMISSION_CSV)
    alternating = table.loc[table.kind == "AC", ["from", "to", "mw"]]
    direct = table.loc[table.kind == "DC", ["from", "to", "mw"]]
    ac_capacity = {
        tuple(sorted((origin, destination))): float(megawatts)
        for origin, destination, megawatts in alternating.itertuples(index=False, name=None)
    }
    dc_capacity = {
        (origin, destination): float(megawatts)
        for origin, destination, megawatts in direct.itertuples(index=False, name=None)
    }
    _apply_ac(network, ac_capacity)
    _apply_dc(network, dc_capacity)


def _apply_ac(network, capacity: dict[tuple[str, str], float]) -> None:
    lines = network.lines
    if lines.empty:
        return
    countries = pd.DataFrame(
        {"a": lines.bus0.map(_country), "b": lines.bus1.map(_country)},
        index=lines.index,
    )
    countries["pair"] = countries.apply(lambda row: tuple(sorted((row.a, row.b))), axis=1)
    remove: list[str] = []
    kept = 0
    for pair, index in countries.groupby("pair").groups.items():
        names = list(index)
        if pair not in capacity:
            remove.extend(names)
            continue
        keeper = names[0]
        group = lines.loc[names]
        headroom = _extension(
            float(group.at[keeper, "s_nom"]),
            float(group.at[keeper, "s_nom_max"]) if "s_nom_max" in group else np.nan,
            AC_EXTENSION_MW,
        )
        for column in ("x", "r"):
            _scale_impedance(lines, keeper, column, _parallel(group[column]))
        if "num_parallel" in lines.columns:
            lines.at[keeper, "num_parallel"] = 1.0
        megawatts = capacity[pair]
        lines.at[keeper, "s_nom"] = megawatts
        lines.at[keeper, "s_nom_min"] = megawatts
        lines.at[keeper, "s_nom_extendable"] = True
        lines.at[keeper, "s_max_pu"] = 1.0
        if "s_nom_max" in lines.columns:
            lines.at[keeper, "s_nom_max"] = megawatts + headroom
        remove.extend(names[1:])
        kept += 1
    if remove:
        network.remove("Line", remove)
    LOGGER.info(
        "BAU and mitigation keep %s AC borders at their 2025 capacity. Removed %s lines.",
        kept,
        len(remove),
    )


def _apply_dc(network, capacity: dict[tuple[str, str], float]) -> None:
    links = network.links
    if links.empty or "carrier" not in links.columns:
        return
    direct = links.index[links.carrier.astype(str).eq("DC")]
    if len(direct) == 0:
        return
    countries = pd.DataFrame(
        {"a": links.loc[direct, "bus0"].map(_country), "b": links.loc[direct, "bus1"].map(_country)},
        index=direct,
    )
    remove: list[str] = []
    kept = 0
    for (origin, destination), index in countries.groupby(["a", "b"]).groups.items():
        names = list(index)
        megawatts = capacity.get((origin, destination))
        if megawatts is None:
            remove.extend(names)
            continue
        keeper = max(names, key=lambda name: float(links.at[name, "length"]))
        headroom = _extension(
            float(links.at[keeper, "p_nom"]),
            float(links.at[keeper, "p_nom_max"]) if "p_nom_max" in links else np.nan,
            DC_EXTENSION_MW,
        )
        links.at[keeper, "p_nom"] = megawatts
        links.at[keeper, "p_nom_min"] = megawatts
        links.at[keeper, "p_nom_extendable"] = True
        if "p_nom_max" in links.columns:
            links.at[keeper, "p_nom_max"] = megawatts + headroom
        remove.extend(name for name in names if name != keeper)
        kept += 1
    if remove:
        network.remove("Link", remove)
    LOGGER.info(
        "BAU and mitigation keep %s DC directions at their 2025 capacity. Removed %s links.",
        kept,
        len(remove),
    )
