# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""Solve the overnight MACC scenarios with pixi, one scenario at a time.

For each planning year the order is:

1. ``pixi run snakemake`` for ``{year}-BAU``, including PyPSA post-processing.
2. Read that BAU and write the absolute CO2 caps.
3. ``pixi run snakemake`` for ``{year}-MACC_1`` through ``{year}-MACC_6``.
4. After every scenario, write the study figures in ``macc/postprocessing``.
5. ``pixi run snakemake macc_postprocess``, which waits for every PyPSA
   post-processing output of the year and writes the tables again.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macc.common import (  # noqa: E402
    ROOT,
    STEPS,
    YEARS,
    config_path,
    dump_yaml,
    load_yaml,
    scenario_name,
)


def _run(cmd: list[str]) -> None:
    print("\n$ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def _selector(directory: Path, year: int, scenario: str) -> Path:
    """Point snakemake at one scenario so the others are not built with it.

    Snakemake replaces a config section instead of merging inside it, so the
    selector repeats the whole ``run`` block and changes only the name.
    """
    run = dict(load_yaml(config_path(year))["run"])
    run["name"] = [scenario]
    path = directory / f"{scenario}.yaml"
    dump_yaml(path, {"run": run})
    return path


def _snakemake(cores: str, config_files: list[Path], target: str | None) -> None:
    cmd = [
        "pixi",
        "run",
        "--",
        "snakemake",
        "--cores",
        cores,
        "--rerun-incomplete",
    ]
    # One flag, several paths. A repeated --configfile replaces the previous
    # list, so the year file was dropped and planning_horizons stayed at 2050.
    if config_files:
        cmd.append("--configfile")
        cmd.extend(str(path) for path in config_files)
    if target:
        cmd.append(target)
    _run(cmd)


def solve_scenario(year: int, scenario: str, cores: str, directory: Path) -> None:
    print(f"\n=== {scenario}: solve and PyPSA post-processing ===", flush=True)
    _snakemake(
        cores,
        [config_path(year), _selector(directory, year, scenario)],
        target=None,
    )
    print(f"\n=== {scenario}: study figures ===", flush=True)
    from macc.postprocessing import update

    update()


def solve_year(year: int, cores: str, directory: Path) -> None:
    if not config_path(year).exists():
        raise SystemExit(
            f"Missing {config_path(year)}. Run python -m macc.generate_scenarios."
        )
    bau = scenario_name(year, 0.0)
    solve_scenario(year, bau, cores, directory)

    print(f"\n=== {year}: CO2 caps from {bau} ===", flush=True)
    from macc.apply_reference_caps import apply_year, publish

    publish([apply_year(year)])

    for _label, reduction in STEPS:
        if reduction == 0.0:
            continue
        solve_scenario(year, scenario_name(year, reduction), cores, directory)

    print(f"\n=== {year}: MACC tables after PyPSA post-processing ===", flush=True)
    _snakemake(cores, [config_path(year)], target="macc_postprocess")


def _year_argument(value: str) -> int:
    """Accept ``2025`` and the ``year=2025`` form pixi forwards."""
    text = value.split("=", 1)[-1]
    try:
        year = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"expected a planning year, got {value!r}"
        ) from exc
    if year not in YEARS:
        raise argparse.ArgumentTypeError(
            f"{year} is not one of {', '.join(str(item) for item in YEARS)}"
        )
    return year


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--year",
        type=_year_argument,
        action="append",
        help="Planning year. Repeat to select several. Default: all six years.",
    )
    parser.add_argument(
        "--cores",
        default=os.environ.get("MACC_CORES", "all"),
        help="Cores passed to snakemake. Default: all, or the MACC_CORES variable.",
    )
    args = parser.parse_args()
    years = args.year or YEARS
    with tempfile.TemporaryDirectory(prefix="macc-run-") as tmp:
        directory = Path(tmp)
        for year in years:
            solve_year(year, args.cores, directory)
    print("\nMACC scenarios finished.", flush=True)


if __name__ == "__main__":
    main()
