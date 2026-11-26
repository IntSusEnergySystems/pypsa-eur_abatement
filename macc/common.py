# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""Shared definitions for the six overnight MACC workflows."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MACC_DIR = ROOT / "macc"
CONFIG_DIR = MACC_DIR / "config"
SCENARIO_DIR = MACC_DIR / "scenarios"
PATHWAY_DIR = MACC_DIR / "pathways"
RESULTS_DIR = MACC_DIR / "results"

DEFAULT_CONFIG = ROOT / "config" / "config.default.yaml"

YEARS = [2025, 2030, 2035, 2040, 2045, 2050]
# Reduction from that year's BAU emissions. BAU has no extra CO2 cap.
# MACC_1 is a 10% cut, MACC_6 is a 100% cut.
STEPS = (
    ("BAU", 0.0),
    ("MACC_1", 0.1),
    ("MACC_2", 0.2),
    ("MACC_3", 0.4),
    ("MACC_4", 0.6),
    ("MACC_5", 0.8),
    ("MACC_6", 1.0),
)

TECHNOLOGY_DATA_VERSION = "v0.16.0"
TEMPORAL_RESOLUTION = "6h"
WEATHER_YEAR = 2013
CUTOUT = "europe-2013-sarah3-era5"
RESULTS_PREFIX = "macc"
REFERENCE_WORKBOOK = MACC_DIR / "data" / "ref2020_energy-transport-ghg.xlsx"

# EU Reference Scenario 2020 sheets, in PyPSA country codes. Greece is EL in
# the workbook and GR here. Cyprus and Malta have sheets, but this model has
# no network data for them. Countries without a sheet are not included.
COUNTRIES = [
    "AT",
    "BE",
    "BG",
    "CZ",
    "DE",
    "DK",
    "EE",
    "ES",
    "FI",
    "FR",
    "GR",
    "HR",
    "HU",
    "IE",
    "IT",
    "LT",
    "LU",
    "LV",
    "NL",
    "PL",
    "PT",
    "RO",
    "SE",
    "SI",
    "SK",
]

TONNES_PER_GT = 1e9
# co2_budget.upper is an annual cap in Gt. Ignore sub-tonne numerical dust.
EMISSION_TOLERANCE_T = 1.0


def scenario_name(year: int, reduction: float) -> str:
    """Return the run name for one year and one reduction from BAU."""
    for label, value in STEPS:
        if abs(value - reduction) < 1e-9:
            return f"{year}-{label}"
    known = ", ".join(str(value) for _, value in STEPS)
    raise ValueError(f"Reduction {reduction} is not one of {known}.")


def parse_scenario_name(name: str) -> tuple[int, float]:
    """Return ``(year, reduction_fraction)`` from a run name."""
    year_text, label = name.split("-", 1)
    year = int(year_text)
    for step_label, reduction in STEPS:
        if label == step_label:
            return year, reduction
    raise ValueError(f"Unrecognised scenario name {name!r}.")


def reduction_fraction(reduction: float) -> float:
    return reduction


def remaining_fraction(reduction: float) -> float:
    return round(1.0 - reduction, 10)


def config_path(year: int) -> Path:
    return CONFIG_DIR / f"config.{year}.yaml"


def scenario_path(year: int) -> Path:
    return SCENARIO_DIR / f"{year}.yaml"


def solved_network_path(name: str) -> Path:
    year, _remaining = parse_scenario_name(name)
    return (
        ROOT
        / "results"
        / RESULTS_PREFIX
        / name
        / "networks"
        / f"solved_{year}.nc"
    )


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a mapping.")
    return data


def dump_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, default_flow_style=False)


def year_map(item: dict) -> dict[int, float] | None:
    """Return a year-to-value map, or None when the mapping is not one."""
    if not item:
        return None
    mapped: dict[int, float] = {}
    for key, value in item.items():
        if isinstance(key, str) and key.isdigit():
            year = int(key)
        elif isinstance(key, int) and not isinstance(key, bool):
            year = key
        else:
            return None
        if isinstance(value, (dict, list)):
            return None
        mapped[year] = value
    return mapped


def year_value(item, investment_year: int):
    """Resolve one config entry the way ``scripts._helpers.get`` does.

    Exact years are returned as stored. A missing year inside the table is
    linearly interpolated. Years outside the table take the nearest endpoint.
    """
    if not isinstance(item, dict):
        return item
    mapped = year_map(item)
    if mapped is None:
        raise TypeError(f"Expected a year mapping, got keys {list(item)}.")
    if investment_year in mapped:
        return mapped[investment_year]
    keys = sorted(mapped)
    if investment_year < keys[0]:
        return mapped[keys[0]]
    if investment_year > keys[-1]:
        return mapped[keys[-1]]
    lower_key = max(key for key in keys if key < investment_year)
    higher_key = min(key for key in keys if key > investment_year)
    lower = mapped[lower_key]
    higher = mapped[higher_key]
    return lower + (higher - lower) * (investment_year - lower_key) / (
        higher_key - lower_key
    )


def marginal_abatement_cost(
    cost: float,
    cost_previous: float,
    emissions_t: float,
    emissions_previous_t: float,
) -> float:
    """Euros per tonne from one tighter scenario relative to the previous one.

    ``MAC = (C_i - C_{i-1}) / (E_{i-1} - E_i)``. A step that does not reduce
    emissions has an undefined marginal cost.
    """
    delta_emissions = emissions_previous_t - emissions_t
    if abs(delta_emissions) < EMISSION_TOLERANCE_T:
        return float("nan")
    return (cost - cost_previous) / delta_emissions


def gt_per_year_to_tonnes(gt_per_year: float) -> float:
    return gt_per_year * TONNES_PER_GT


def tonnes_to_gt_per_year(tonnes: float) -> float:
    return tonnes / TONNES_PER_GT
