"""Numbered manuscript sections combining report figures and tables."""

from __future__ import annotations

from abm_analysis.plots import figure_to_html

from .figures import _figure_display_title

def _run_report_sections(
    figure_objects: dict[str, object],
    tables: dict[str, str],
    *,
    has_benchmarks: bool,
) -> list[dict[str, object]]:
    """Assemble the numbered body sections of a single-run report."""

    sections = [
        _section(
            "market-dynamics",
            "Market Dynamics",
            "Price paths, log returns, and traded volume describe the simulated "
            "market trajectory before any distributional analysis.",
            figure_objects,
            figure_names=["price_timeseries", "market_fundamental_log_returns", "trade_volume"],
        ),
        _section(
            "return-stylised-facts",
            "Return Stylised Facts",
            "Distributional and dependence diagnostics of simulated log returns.",
            figure_objects,
            figure_names=["return_histogram", "return_ecdf", "acf"],
            table_entries=[("Stylised-Fact Diagnostics", tables.get("stylised_fact_diagnostics"))],
            footnote=(
                "Figures are descriptive. Formal hypothesis tests for the stylised facts "
                "shown here are reported in the Stylised-Fact Evidence section above."
            ),
        ),
        _section(
            "market-microstructure",
            "Market Microstructure",
            "Order-book quotes, liquidity, order flow, and double-auction allocative "
            "efficiency characterise the trading mechanism.",
            figure_objects,
            figure_names=[
                "microstructure_quotes",
                "microstructure_liquidity",
                "order_flow_microstructure",
                "allocative_efficiency_timeseries",
            ],
        ),
        _section(
            "agent-outcomes",
            "Agent Outcomes",
            "Wealth, inequality, portfolio composition, trading activity, and "
            "behavioural diagnostics at the agent level.",
            figure_objects,
            figure_names=[
                "agent_wealth",
                "agent_return_lorenz",
                "wealth_gini_timeseries",
                "agent_portfolio_distribution",
                "agent_trading_activity",
                "agent_reference_points",
                "agent_behavioural_outcomes",
            ],
            table_entries=[("Agent Summary Statistics", tables.get("agent_summary"))],
        ),
    ]
    if has_benchmarks:
        sections.insert(2, _benchmark_section(figure_objects, tables))
    multi_asset = _multi_asset_section(figure_objects, tables)
    if multi_asset is not None:
        # Placed directly after market dynamics: the preceding sections now draw
        # every asset individually, so what remains here is the joint behaviour
        # those per-asset panels cannot show.
        sections.insert(1, multi_asset)
    return sections

def _multi_asset_section(
    figure_objects: dict[str, object],
    tables: dict[str, str],
) -> dict[str, object] | None:
    """Build the cross-asset section, or ``None`` for single-asset runs.

    Returning ``None`` rather than an empty section is what guarantees that a
    run with Asset B disabled produces exactly the report it produced before
    the two-asset extension.

    The section holds only joint quantities. Per-asset prices, returns,
    liquidity, order flow, and efficiency are drawn by the core sections, which
    show every asset rather than the nominated primary one.
    """

    multi_asset_figures = [
        "cross_asset_dependence",
        "portfolio_composition",
    ]
    if not any(name in figure_objects for name in multi_asset_figures):
        return None

    return _section(
        "multi-asset-dynamics",
        "Cross-Asset Dynamics",
        "The preceding sections report each asset in its own right. This one "
        "reports what only exists jointly: agents allocate across assets "
        "through a single Markowitz problem, so cross-asset dependence and the "
        "resulting portfolio composition are model outputs rather than "
        "assumptions.",
        figure_objects,
        figure_names=multi_asset_figures,
        table_entries=[("Asset Configuration", tables.get("asset_configuration"))],
        footnote=(
            "Realised return correlation differs from the configured fundamental "
            "correlation because prices are set by order flow: trading can amplify "
            "or dampen the co-movement built into the fundamentals. Portfolio "
            "weights are cross-sectional means over agents with strictly positive "
            "wealth and sum to one with the cash weight."
        ),
    )

def _comparison_report_sections(
    figure_objects: dict[str, object],
    tables: dict[str, str],
    *,
    has_benchmarks: bool,
) -> list[dict[str, object]]:
    """Assemble the numbered body sections of an experiment-comparison report."""

    sections = _run_report_sections(figure_objects, tables, has_benchmarks=has_benchmarks)
    for section in sections:
        if section["slug"] != "return-stylised-facts":
            continue
        section["figures"] += _figure_entries(
            figure_objects, ["metric_comparison", "ks_heatmap"]
        )
        section["tables"] += _table_entries(
            [("Pairwise K-S Log-Return Comparison", tables.get("pairwise_ks"))]
        )
    sections.append(
        _section(
            "seed-robustness",
            "Seed Robustness",
            "Condition-level summaries aggregate replicated seeds so random draws "
            "are not mistaken for behavioural effects.",
            figure_objects,
            figure_names=["seed_robustness"],
            table_entries=[
                ("Seed Robustness by Experimental Condition", tables.get("seed_robustness")),
            ],
            footnote=(
                "Each condition aggregates repeated-seed runs; a wide within-condition spread "
                "reflects sensitivity to random initialisation, not a modelling error."
            ),
        )
    )
    return sections

def _seed_robustness_report_sections(
    figure_objects: dict[str, object],
    tables: dict[str, str],
) -> list[dict[str, object]]:
    """Assemble the numbered body sections of a seed-robustness report."""

    return [
        _section(
            "cross-seed-distributions",
            "Cross-Seed Return Distributions",
            "If seeds are true replicates of one data-generating process, their "
            "log-return distributions should be statistically indistinguishable. "
            "The ECDF overlay shows the distributions directly; the pairwise K-S "
            "heatmap and the k-sample tests quantify their distance.",
            figure_objects,
            figure_names=["return_ecdf", "ks_heatmap"],
            table_entries=[
                ("Cross-Seed Distribution Tests", tables.get("distribution_tests")),
                ("Pairwise K-S Log-Return Comparison", tables.get("pairwise_ks")),
            ],
            footnote=(
                "Pairwise K-S tests share samples and are therefore dependent; the "
                "share of insignificant pairs is descriptive, not an exact test. "
                "Anderson-Darling k-sample p-values are capped by SciPy to the "
                "interval [0.001, 0.25] and are shown as bounds when capped."
            ),
        ),
        _section(
            "metric-stability",
            "Metric Stability Across Seeds",
            "Headline metrics should vary little when only the random seed "
            "changes. The box plots keep every seed visible so influential single "
            "draws are not hidden by averaging; the summary table reports "
            "cross-seed dispersion, coefficients of variation, and confidence "
            "intervals per experimental condition.",
            figure_objects,
            figure_names=["seed_metric_distribution", "seed_robustness"],
            table_entries=[
                ("Seed Robustness by Experimental Condition", tables.get("seed_robustness")),
            ],
            footnote=(
                "A wide within-condition spread reflects sensitivity to random "
                "initialisation, not a modelling error; heavy-tailed regimes "
                "legitimately produce dispersed higher-moment estimates."
            ),
        ),
        _section(
            "stylised-fact-reproducibility",
            "Stylised-Fact Reproducibility",
            "Each seed's diagnostics classify the run as consistent or not with "
            "the core stylised facts (fat tails, volatility clustering, weak raw-"
            "return autocorrelation). The success rates show how many seeds "
            "reproduce each fact; robust facts should not depend on the draw.",
            figure_objects,
            figure_names=["stylised_fact_success"],
            table_entries=[
                ("Per-Seed Stylised-Fact Diagnostics", tables.get("stylised_fact_diagnostics")),
            ],
        ),
        _section(
            "stationarity",
            "Log-Return Stationarity by Seed",
            "Moment-based robustness metrics presuppose stationary log returns. "
            "The Augmented Dickey-Fuller test is run per seed; stationarity is "
            "supported when the unit-root null is rejected for (nearly) every "
            "seed.",
            figure_objects,
            figure_names=["adf_pvalues"],
            table_entries=[
                ("ADF Stationarity by Seed", tables.get("adf_stationarity")),
            ],
            footnote=(
                "The headline quantity is the rejection rate across seeds; a "
                "single non-rejection among many seeds is expected from "
                "finite-sample power and does not overturn stationarity."
            ),
        ),
        _section(
            "seed-convergence",
            "Seed-Count Convergence",
            "Running ensemble means with 95% confidence bands show how the "
            "headline metrics stabilise as seeds accumulate. When the bands stop "
            "narrowing meaningfully, additional replications no longer change the "
            "conclusions, which justifies the chosen replication count.",
            figure_objects,
            figure_names=["seed_convergence"],
            table_entries=[
                ("Seed-Count Convergence Table", tables.get("seed_convergence")),
            ],
            footnote=(
                "Seeds are accumulated in ascending seed order so the convergence "
                "path is reproducible across report regenerations."
            ),
        ),
    ]

def _appendices(
    *,
    output_files: list[str],
    run_inventory_tables: list[tuple[str, str | None]] | None = None,
) -> list[dict[str, object]]:
    """Assemble the lettered appendix sections shared by both report kinds."""

    appendices: list[dict[str, object]] = []
    inventory_entries = _table_entries(run_inventory_tables or [])
    if inventory_entries:
        appendices.append(
            {
                "slug": "run-inventory",
                "title": "Run Inventory",
                "paragraph": (
                    "Use these tables to identify which dataset is shown by each short "
                    "chart label. Full run identifiers remain in the CSV exports for "
                    "reproducibility."
                ),
                "footnote": "",
                "figures": [],
                "tables": inventory_entries,
                "files": [],
            }
        )
    appendices.append(
        {
            "slug": "data-availability",
            "title": "Data Availability",
            "paragraph": (
                "CSV exports sit beside this HTML report for replication checks and "
                "supplementary analysis."
            ),
            "footnote": "",
            "figures": [],
            "tables": [],
            "files": list(output_files),
        }
    )
    return appendices

def _benchmark_section(
    figure_objects: dict[str, object],
    tables: dict[str, str],
) -> dict[str, object]:
    return _section(
        "benchmark-comparison",
        "Benchmark Comparison",
        "Empirical benchmark overlays compare simulated return distributions, "
        "quantiles, and tail behaviour against historical market data.",
        figure_objects,
        figure_names=[
            "simulation_benchmark_ecdf",
            "simulation_benchmark_qq",
            "return_tail_quantiles",
        ],
        table_entries=[
            ("Empirical Benchmark Scorecard", tables.get("benchmark_scorecard")),
            ("Simulation-vs-Market Distribution Comparison", tables.get("simulation_vs_benchmark")),
        ],
        footnote=(
            "Empirical benchmark series are historical reference data, not causal "
            "counterfactuals; distributional overlap does not establish that the "
            "simulator reproduces the same generative process."
        ),
    )

def _section(
    slug: str,
    title: str,
    paragraph: str,
    figure_objects: dict[str, object],
    *,
    figure_names: list[str] | None = None,
    table_entries: list[tuple[str, str | None]] | None = None,
    footnote: str = "",
) -> dict[str, object]:
    return {
        "slug": slug,
        "title": title,
        "paragraph": paragraph,
        "footnote": footnote,
        "figures": _figure_entries(figure_objects, figure_names or []),
        "tables": _table_entries(table_entries or []),
        "files": [],
    }

def _figure_entries(
    figure_objects: dict[str, object],
    figure_names: list[str],
) -> list[dict[str, str]]:
    return [
        {
            "name": name,
            "title": _figure_display_title(name, figure_objects[name]),
            "html": figure_to_html(figure_objects[name]),
        }
        for name in figure_names
        if name in figure_objects
    ]

def _table_entries(entries: list[tuple[str, str | None]]) -> list[dict[str, str]]:
    return [{"title": title, "html": html} for title, html in entries if html]
