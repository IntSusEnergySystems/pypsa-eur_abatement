# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""Study figures written after each solved MACC scenario."""

from __future__ import annotations

from macc.common import MACC_DIR

POST_DIR = MACC_DIR / "postprocessing"
FIGURE_DIR = POST_DIR / "figures"
TABLE_DIR = POST_DIR / "tables"


def update() -> None:
    """Refresh tables and the four study figures from every solved network."""
    from macc.compute_macc import compute
    from macc.extract_results import extract
    from macc.postprocessing.figures import write_figures

    extract()
    compute()
    write_figures()
