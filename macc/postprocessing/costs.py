# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""Split a solved network's annual cost into the study components.

Annualised investment and fixed operation come from ``capital_cost``.
Technology-data gives the fixed-operation share as ``FOM / (annuity + FOM)``.
Fuel is the operating cost of primary fuel generators. Variable operation is
the remaining operating cost.
"""

from __future__ import annotations

import pandas as pd
import pypsa

from macc.common import ROOT, TECHNOLOGY_DATA_VERSION

DEFAULT_DISCOUNT = 0.07
# Operating cost of these generators is the fuel price. Power plants are links
# and stay in variable operation.
FUEL_GENERATORS = {
    "coal",
    "lignite",
    "gas",
    "oil",
    "oil primary",
    "uranium",
    "solid biomass",
    "unsustainable solid biomass",
    "biogas",
    "unsustainable biogas",
    "unsustainable bioliquids",
}
TABLES = {
    "Generator": "generators",
    "Link": "links",
    "StorageUnit": "storage_units",
    "Store": "stores",
    "Line": "lines",
    "Transformer": "transformers",
}


def _costs(year: int) -> pd.DataFrame:
    path = (
        ROOT
        / "data"
        / "costs"
        / "archive"
        / TECHNOLOGY_DATA_VERSION
        / f"costs_{year}.csv"
    )
    if not path.exists():
        return pd.DataFrame()
    raw = pd.read_csv(path)
    return raw.pivot_table(
        index="technology",
        columns="parameter",
        values="value",
        aggfunc="first",
    )


def _fom_share(costs: pd.DataFrame, carrier: str) -> float:
    """Share of annualised capital that is fixed operation, for one technology."""
    if costs.empty or carrier not in costs.index:
        return 0.0
    row = costs.loc[carrier]
    if "FOM" not in row or "lifetime" not in row:
        return 0.0
    lifetime = float(row["lifetime"])
    fom = float(row["FOM"])
    if pd.isna(lifetime) or pd.isna(fom) or lifetime <= 0:
        return 0.0
    rate = DEFAULT_DISCOUNT
    if "discount rate" in row and pd.notna(row["discount rate"]):
        rate = float(row["discount rate"])
    annuity = float(pypsa.costs.annuity(rate, lifetime))
    denominator = annuity + fom / 100.0
    if denominator <= 0:
        return 0.0
    return (fom / 100.0) / denominator


def _with_carrier(network, values: pd.Series) -> pd.DataFrame:
    if values is None or len(values) == 0:
        return pd.DataFrame(columns=["component", "name", "value", "carrier"])
    frame = values.rename("value").reset_index()
    carriers = []
    for row in frame.itertuples(index=False):
        table_name = TABLES.get(row.component)
        table = getattr(network, table_name) if table_name else None
        if table is not None and row.name in table.index and "carrier" in table.columns:
            carriers.append(str(table.at[row.name, "carrier"]))
        else:
            carriers.append("")
    frame["carrier"] = carriers
    return frame


def cost_components(network, year: int) -> dict[str, float]:
    """Return annual investment, fixed O&M, variable O&M, fuel and other."""
    costs = _costs(year)
    capital = _with_carrier(network, network.statistics.capex(groupby=False))
    operating = _with_carrier(network, network.statistics.opex(groupby=False))
    investment = 0.0
    fixed = 0.0
    for row in capital.itertuples(index=False):
        share = _fom_share(costs, row.carrier)
        fixed += share * float(row.value)
        investment += (1.0 - share) * float(row.value)
    fuel = 0.0
    variable = 0.0
    for row in operating.itertuples(index=False):
        amount = float(row.value)
        if row.component == "Generator" and row.carrier in FUEL_GENERATORS:
            fuel += amount
        else:
            variable += amount
    accounted = investment + fixed + variable + fuel
    capex_sum = float(capital["value"].sum()) if len(capital) else 0.0
    opex_sum = float(operating["value"].sum()) if len(operating) else 0.0
    other = capex_sum + opex_sum - accounted
    return {
        "investment_eur_per_year": investment,
        "fixed_om_eur_per_year": fixed,
        "variable_om_eur_per_year": variable,
        "fuel_cost_eur_per_year": fuel,
        "other_cost_eur_per_year": other,
    }
