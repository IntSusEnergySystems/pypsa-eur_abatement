# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

# Included only when ``macc.enable`` is true. The inputs are the same files as
# rule ``all``, so the MACC tables are built after PyPSA's own post-processing.


rule macc_postprocess:
    """Writes MACC costs, emissions and figures after the PyPSA summary plots."""
    input:
        expand(CORE_OUTPUTS, run=config["run"]["name"]),
        (
            expand(
                NETWORK_PLOT_OUTPUTS,
                run=config["run"]["name"],
                horizon=config["planning_horizons"],
            )
            if NETWORK_PLOT_OUTPUTS
            else []
        ),
        (
            expand(
                TIMESERIES_OUTPUTS,
                run=config["run"]["name"],
                horizon=config["planning_horizons"],
            )
            if TIMESERIES_OUTPUTS
            else []
        ),
        (expand(MYOPIC_OUTPUTS, run=config["run"]["name"]) if MYOPIC_OUTPUTS else []),
        sector_network_plot_paths,
        balance_map_paths,
    output:
        summary="macc/results/scenario_summary.csv",
        carriers="macc/results/carrier_summary.csv",
        curve="macc/results/macc.csv",
        comparison="macc/results/macc_by_reduction.csv",
        steps="macc/results/macc_carrier_steps.csv",
        figures=directory("macc/results/figures"),
    log:
        "macc/results/logs/macc_postprocess_%s.log"
        % config["planning_horizons"][0],
    shell:
        """
        python -m macc.extract_results && \
        python -m macc.compute_macc && \
        python -m macc.plot_macc
        """
