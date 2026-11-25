# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""Solve the overnight MACC scenarios with pixi, one scenario at a time.

For each planning year the order is:

1. ``pixi run snakemake`` for ``{year}-REF``, including PyPSA post-processing.
2. Read that reference and write the absolute CO2 caps.
3. ``pixi run snakemake`` for ``{year}-CO2_90``, then ``CO2_80``, down to ``CO2_0``.
4. ``pixi run snakemake macc_postprocess``, which waits for every PyPSA
   post-processing output of the year and then writes the MACC tables.
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
    REMAINING,
    ROOT,
    YEARS,
    config_path,
    dump_yaml,
    scenario_name,
)


def _run(cmd: list[str]) -> None:
    print("\n$ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def _selector(directory: Path, scenario: str) -> Path:
    """Point snakemake at one scenario so the others are not built with it."""
    path = directory / f"{scenario}.yaml"
    dump_yaml(path, {"run": {"name": [scenario]}})
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
    for path in config_files:
        cmd.extend(["--configfile", str(path)])
    if target:
        cmd.append(target)
    _run(cmd)


def solve_scenario(year: int, scenario: str, cores: str, directory: Path) -> None:
    print(f"\n=== {scenario}: solve and PyPSA post-processing ===", flush=True)
    _snakemake(
        cores,
        [config_path(year), _selector(directory, scenario)],
        target=None,
    )


def solve_year(year: int, cores: str, directory: Path) -> None:
    if not config_path(year).exists():
        raise SystemExit(
            f"Missing {config_path(year)}. Run python -m macc.generate_scenarios."
        )
    reference = scenario_name(year, 1.0)
    solve_scenario(year, reference, cores, directory)

    print(f"\n=== {year}: CO2 caps from {reference} ===", flush=True)
    from macc.apply_reference_caps import apply_year, publish

    publish([apply_year(year)])

    for remaining in REMAINING:
        if abs(remaining - 1.0) < 1e-9:
            continue
        solve_scenario(year, scenario_name(year, remaining), cores, directory)

    print(f"\n=== {year}: MACC tables after PyPSA post-processing ===", flush=True)
    _snakemake(cores, [config_path(year)], target="macc_postprocess")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--year",
        type=int,
        action="append",
        choices=YEARS,
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
