"""Pass/borderline/fail robustness verdicts for seed-replication experiments.

Every threshold in this module is a fixed, named decision rule so the report
can state exactly why each verdict was reached. The thresholds follow the
simulation-methodology literature where such guidance exists and are declared
as explicit modelling choices where it does not:

- Coefficient-of-variation and confidence-interval precision targets follow
  the relative-error criterion gamma = 0.10 in Law (2015, "Simulation
  Modeling and Analysis", 5th ed., ch. 9) and the coefficient-of-variation
  stability screening for ABM outputs in Lorscheid, Heine & Meyer (2012,
  Computational and Mathematical Organization Theory 18).
- Stylised-fact success rates require a strong majority of seeds to
  reproduce each fact from Cont (2001, Quantitative Finance 1); the 80%
  cut-off is an explicit modelling choice, not an empirical constant.
- Distribution-equality and stationarity rules reuse the report-wide 5%
  significance convention (see ``abm_analysis.diagnostics``), with the
  Dickey-Fuller unit-root framework from Dickey & Fuller (1979, JASA 74).

Verdicts are diagnostic summaries: a "fail" flags a criterion for inspection
(for example, excess kurtosis is legitimately dispersed across seeds in
heavy-tailed regimes) rather than proving a modelling error.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from abm_analysis.diagnostics import SIGNIFICANCE_LEVEL
from abm_analysis.seed_convergence import final_relative_ci_half_widths


# --- Cross-seed dispersion (coefficient of variation) -----------------------
# Pass when cross-seed dispersion is within the 10% relative-error target of
# Law (2015); borderline up to 25% follows the "acceptable but report with
# caution" band used in Lorscheid, Heine & Meyer (2012).
COV_PASS_THRESHOLD = 0.10
COV_BORDERLINE_THRESHOLD = 0.25

# ``mean_log_return`` is deliberately excluded: its ensemble mean is close to
# zero by construction, which makes any mean-normalised dispersion measure
# numerically unstable (``robustness._aggregate_metric`` already yields NaN
# there). Its stability is judged through the convergence figure instead.
COV_VERDICT_METRICS = (
    "log_return_std_dev",
    "excess_kurtosis",
    "max_drawdown",
    "total_traded_volume",
)

# --- Stylised-fact reproducibility across seeds ------------------------------
# A strong majority of seeds must reproduce each stylised fact; 80% is an
# explicit modelling choice for "robust", 60% marks mixed evidence.
SUCCESS_RATE_PASS_THRESHOLD = 0.80
SUCCESS_RATE_BORDERLINE_THRESHOLD = 0.60

# --- Distributional stability (pairwise K-S share) ---------------------------
# Under the null that all seeds share one distribution, the expected share of
# non-rejections at the 5% level is 0.95. The pass threshold is relaxed to
# 0.75 because the pairwise tests share samples (positive dependence) and
# long series give the K-S test power against negligible differences.
KS_INSIGNIFICANT_SHARE_PASS_THRESHOLD = 0.75
KS_INSIGNIFICANT_SHARE_BORDERLINE_THRESHOLD = 0.50

# For the k-sample tests a rejection below this level is treated as clear
# evidence against cross-seed equality; between this and the 5% convention it
# is treated as borderline.
STRONG_REJECTION_P_VALUE = 0.01

# --- Stationarity across seeds ------------------------------------------------
# The ADF unit-root null should be rejected for essentially every seed when
# log returns are stationary; occasional non-rejections are expected from
# finite-sample power, hence the 90%/75% bands.
ADF_REJECTION_RATE_PASS_THRESHOLD = 0.90
ADF_REJECTION_RATE_BORDERLINE_THRESHOLD = 0.75

# --- Ensemble precision at the achieved replication count --------------------
# The 95% CI half-width of the ensemble mean, relative to that mean, follows
# Law's (2015) sequential relative-error criterion. Applied to the scale
# metrics only: ``mean_log_return`` is excluded for the same near-zero-mean
# reason as above.
RELATIVE_CI_HALF_WIDTH_PASS_THRESHOLD = 0.10
RELATIVE_CI_HALF_WIDTH_BORDERLINE_THRESHOLD = 0.20
RELATIVE_CI_VERDICT_METRICS = (
    "log_return_std_dev",
    "excess_kurtosis",
    "max_drawdown",
)

# Below this replication count, dispersion and rate estimates are too noisy
# for any verdict to be meaningful, so every criterion reports "not
# available" rather than a spurious pass or fail.
MINIMUM_SEEDS_FOR_VERDICTS = 5


@dataclass(frozen=True)
class VerdictThresholds:
    """Configurable decision rules for the robustness verdicts.

    Defaults reproduce the module-level literature-backed constants, so
    passing ``None`` (or this class with no overrides) keeps existing
    behaviour. Threshold descriptions in the verdict table interpolate these
    values, so configured thresholds self-document in reports.
    """

    cov_pass: float = COV_PASS_THRESHOLD
    cov_borderline: float = COV_BORDERLINE_THRESHOLD
    success_rate_pass: float = SUCCESS_RATE_PASS_THRESHOLD
    success_rate_borderline: float = SUCCESS_RATE_BORDERLINE_THRESHOLD
    ks_insignificant_share_pass: float = KS_INSIGNIFICANT_SHARE_PASS_THRESHOLD
    ks_insignificant_share_borderline: float = KS_INSIGNIFICANT_SHARE_BORDERLINE_THRESHOLD
    strong_rejection_p_value: float = STRONG_REJECTION_P_VALUE
    adf_rejection_rate_pass: float = ADF_REJECTION_RATE_PASS_THRESHOLD
    adf_rejection_rate_borderline: float = ADF_REJECTION_RATE_BORDERLINE_THRESHOLD
    relative_ci_half_width_pass: float = RELATIVE_CI_HALF_WIDTH_PASS_THRESHOLD
    relative_ci_half_width_borderline: float = RELATIVE_CI_HALF_WIDTH_BORDERLINE_THRESHOLD
    minimum_seeds_for_verdicts: int = MINIMUM_SEEDS_FOR_VERDICTS


METRIC_DISPLAY_NAMES = {
    "mean_log_return": "Mean Log Return",
    "log_return_std_dev": "Return Std. Dev.",
    "excess_kurtosis": "Excess Kurtosis",
    "max_drawdown": "Max Drawdown",
    "total_traded_volume": "Total Traded Volume",
}

_TEST_DISPLAY_NAMES = {
    "anderson_darling_ksample": "Anderson-Darling k-sample test",
    "kruskal_wallis": "Kruskal-Wallis location test",
    "levene_brown_forsythe": "Brown-Forsythe dispersion test",
}

_SUCCESS_RATE_CRITERIA = (
    ("fat_tail_success_rate", "Fat-tailed returns"),
    ("volatility_clustering_success_rate", "Volatility clustering"),
    ("weak_autocorrelation_success_rate", "Weak raw-return autocorrelation"),
)


def build_robustness_verdicts(
    seed_summary: pd.DataFrame,
    distribution_tests: pd.DataFrame,
    ks_summary: dict[str, float],
    adf_summary: dict[str, float],
    convergence_table: pd.DataFrame,
    *,
    seed_count: int,
    thresholds: VerdictThresholds | None = None,
) -> pd.DataFrame:
    """Evaluate every robustness criterion into a verdict table.

    Returns one row per criterion with columns ``criterion, category,
    hypothesis, metric_value, metric_display, threshold_description, verdict,
    interpretation``. Verdicts are ``pass``, ``borderline``, ``fail``, or
    ``not_available``. When fewer than the minimum replication count seeds
    completed, every verdict is ``not_available`` because dispersion and rate
    estimates from so few replications would be spurious. ``thresholds``
    defaults to the literature-backed module constants.
    """

    resolved = thresholds if thresholds is not None else VerdictThresholds()
    rows: list[dict[str, object]] = []
    too_few_seeds = seed_count < resolved.minimum_seeds_for_verdicts

    rows.extend(_cov_verdict_rows(seed_summary, resolved))
    rows.extend(_success_rate_verdict_rows(seed_summary, resolved))
    rows.append(_ks_share_verdict_row(ks_summary, resolved))
    rows.extend(_distribution_test_verdict_rows(distribution_tests, resolved))
    rows.append(_adf_verdict_row(adf_summary, resolved))
    rows.extend(_relative_ci_verdict_rows(convergence_table, seed_count, resolved))

    if too_few_seeds:
        for row in rows:
            row["verdict"] = "not_available"
            row["interpretation"] = (
                f"Only {seed_count} seed(s) completed, below the minimum of "
                f"{resolved.minimum_seeds_for_verdicts} required for meaningful "
                "cross-seed verdicts; run more replications before assessing "
                "this criterion."
            )
    return pd.DataFrame(rows)


def verdict_rows_for_report(verdicts: pd.DataFrame) -> list[dict[str, str]]:
    """Map the verdict table onto the report's evidence-card schema."""

    display = {
        "pass": "Pass",
        "borderline": "Borderline",
        "fail": "Fail",
        "not_available": "Not available",
    }
    tones = {
        "pass": "teal",
        "borderline": "amber",
        "fail": "amber",
        "not_available": "neutral",
    }
    cards: list[dict[str, str]] = []
    for _, row in verdicts.iterrows():
        verdict = str(row.get("verdict", "not_available"))
        cards.append(
            {
                "fact": str(row.get("criterion", "")),
                "verdict": display.get(verdict, verdict),
                "tone": tones.get(verdict, "neutral"),
                "hypothesis": str(row.get("hypothesis", "")),
                "quantitative_evidence": (
                    f"Measured value: {row.get('metric_display', 'not available')}. "
                    f"Decision rule: {row.get('threshold_description', '')}"
                ),
                "interpretation": str(row.get("interpretation", "")),
            }
        )
    return cards


def _cov_verdict_rows(
    seed_summary: pd.DataFrame,
    thresholds: VerdictThresholds,
) -> list[dict[str, object]]:
    threshold_description = (
        f"pass when CoV <= {thresholds.cov_pass:g}; borderline when "
        f"CoV <= {thresholds.cov_borderline:g}; fail otherwise."
    )
    rows: list[dict[str, object]] = []
    for condition_prefix, summary_row in _condition_rows(seed_summary):
        for metric in COV_VERDICT_METRICS:
            display_name = METRIC_DISPLAY_NAMES.get(metric, metric)
            value = _finite_or_none(summary_row.get(f"{metric}_coefficient_of_variation"))
            verdict = _threshold_verdict(
                value,
                pass_below=thresholds.cov_pass,
                borderline_below=thresholds.cov_borderline,
            )
            rows.append(
                {
                    "criterion": f"{condition_prefix}{display_name} stability (CoV)",
                    "category": "metric_stability",
                    "hypothesis": (
                        f"{display_name} varies little across random seeds: the "
                        "coefficient of variation (cross-seed std / |mean|) stays "
                        "within the relative-error target."
                    ),
                    "metric_value": value if value is not None else np.nan,
                    "metric_display": _format_value(value, "CoV = {:.3f}"),
                    "threshold_description": threshold_description,
                    "verdict": verdict,
                    "interpretation": _cov_interpretation(display_name, value, verdict),
                }
            )
    return rows


def _success_rate_verdict_rows(
    seed_summary: pd.DataFrame,
    thresholds: VerdictThresholds,
) -> list[dict[str, object]]:
    threshold_description = (
        f"pass when the success rate >= {thresholds.success_rate_pass:g}; borderline "
        f"when >= {thresholds.success_rate_borderline:g}; fail otherwise."
    )
    rows: list[dict[str, object]] = []
    for condition_prefix, summary_row in _condition_rows(seed_summary):
        for column, fact_name in _SUCCESS_RATE_CRITERIA:
            value = _finite_or_none(summary_row.get(column))
            verdict = _threshold_verdict(
                value,
                pass_above=thresholds.success_rate_pass,
                borderline_above=thresholds.success_rate_borderline,
            )
            rows.append(
                {
                    "criterion": f"{condition_prefix}{fact_name} reproducibility",
                    "category": "stylised_fact_reproducibility",
                    "hypothesis": (
                        f"The stylised fact '{fact_name}' is reproduced by a strong "
                        "majority of seeds, so it reflects the model rather than a "
                        "particular random draw."
                    ),
                    "metric_value": value if value is not None else np.nan,
                    "metric_display": _format_value(value, "success rate = {:.0%}"),
                    "threshold_description": threshold_description,
                    "verdict": verdict,
                    "interpretation": _success_rate_interpretation(fact_name, value, verdict),
                }
            )
    return rows


def _ks_share_verdict_row(
    ks_summary: dict[str, float],
    thresholds: VerdictThresholds,
) -> dict[str, object]:
    value = _finite_or_none(ks_summary.get("insignificant_share"))
    pair_count = int(ks_summary.get("pair_count", 0) or 0)
    verdict = _threshold_verdict(
        value,
        pass_above=thresholds.ks_insignificant_share_pass,
        borderline_above=thresholds.ks_insignificant_share_borderline,
    )
    if verdict == "pass":
        interpretation = (
            "Most seed pairs are statistically indistinguishable, supporting one "
            "common return distribution across seeds."
        )
    elif verdict == "borderline":
        interpretation = (
            "A substantial minority of seed pairs differ significantly; inspect "
            "the ECDF overlay to judge whether the differences are economically "
            "meaningful."
        )
    elif verdict == "fail":
        interpretation = (
            "Most seed pairs reject distributional equality; either the series "
            "are long enough to detect negligible differences or the seeds "
            "genuinely produce different return distributions."
        )
    else:
        interpretation = "No pairwise K-S results are available."
    return {
        "criterion": "Cross-seed distributional stability (pairwise K-S)",
        "category": "distributional_stability",
        "hypothesis": (
            "Log-return distributions from different seeds are pairwise "
            "indistinguishable under the two-sample K-S test at the 5% level."
        ),
        "metric_value": value if value is not None else np.nan,
        "metric_display": _format_value(
            value,
            "insignificant share = {:.0%}" + f" of {pair_count} pairs",
        ),
        "threshold_description": (
            f"pass when the share of insignificant pairs >= "
            f"{thresholds.ks_insignificant_share_pass:g}; borderline when >= "
            f"{thresholds.ks_insignificant_share_borderline:g}; fail otherwise. "
            "Pairs share samples, so the share is descriptive, not an exact test."
        ),
        "verdict": verdict,
        "interpretation": interpretation,
    }


def _distribution_test_verdict_rows(
    distribution_tests: pd.DataFrame,
    thresholds: VerdictThresholds,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    threshold_description = (
        f"pass when p-value >= {SIGNIFICANCE_LEVEL:g}; borderline when "
        f"{thresholds.strong_rejection_p_value:g} <= p-value < {SIGNIFICANCE_LEVEL:g}; "
        "fail on strong rejection below that."
    )
    if distribution_tests.empty:
        return [
            {
                "criterion": "Cross-seed distribution equality (k-sample tests)",
                "category": "distributional_stability",
                "hypothesis": (
                    "All seeds draw log returns from one common distribution "
                    "(location, dispersion, and shape)."
                ),
                "metric_value": np.nan,
                "metric_display": "not available",
                "threshold_description": threshold_description,
                "verdict": "not_available",
                "interpretation": (
                    "The k-sample tests could not run; at least two seeds with "
                    "enough finite log returns are required."
                ),
            }
        ]
    for _, test_row in distribution_tests.iterrows():
        test_name = str(test_row.get("test_name", ""))
        display_name = _TEST_DISPLAY_NAMES.get(test_name, test_name)
        status = str(test_row.get("status", ""))
        p_value = _finite_or_none(test_row.get("p_value"))
        if status != "completed" or p_value is None:
            verdict = "not_available"
        elif p_value >= SIGNIFICANCE_LEVEL:
            verdict = "pass"
        elif p_value >= thresholds.strong_rejection_p_value:
            verdict = "borderline"
        else:
            verdict = "fail"
        rows.append(
            {
                "criterion": f"Cross-seed equality: {display_name}",
                "category": "distributional_stability",
                "hypothesis": str(test_row.get("null_hypothesis", "")),
                "metric_value": p_value if p_value is not None else np.nan,
                "metric_display": (
                    f"p-value {test_row.get('p_value_display', 'not available')}"
                    if status == "completed"
                    else f"status: {status or 'unknown'}"
                ),
                "threshold_description": threshold_description,
                "verdict": verdict,
                "interpretation": _distribution_test_interpretation(display_name, verdict),
            }
        )
    return rows


def _adf_verdict_row(
    adf_summary: dict[str, float],
    thresholds: VerdictThresholds,
) -> dict[str, object]:
    value = _finite_or_none(adf_summary.get("rejection_rate"))
    tested = int(adf_summary.get("tested_seed_count", 0) or 0)
    verdict = _threshold_verdict(
        value,
        pass_above=thresholds.adf_rejection_rate_pass,
        borderline_above=thresholds.adf_rejection_rate_borderline,
    )
    if verdict == "pass":
        interpretation = (
            "The unit-root null is rejected for (nearly) every seed, supporting "
            "stationary log returns and hence well-defined moment-based metrics."
        )
    elif verdict in ("borderline", "fail"):
        interpretation = (
            "Several seeds fail to reject a unit root; moment-based summaries "
            "for those seeds should be interpreted with caution."
        )
    else:
        interpretation = "No per-seed ADF results are available."
    return {
        "criterion": "Log-return stationarity across seeds (ADF)",
        "category": "stationarity",
        "hypothesis": (
            "Each seed's log-return series is stationary: the Augmented "
            "Dickey-Fuller unit-root null is rejected seed by seed."
        ),
        "metric_value": value if value is not None else np.nan,
        "metric_display": _format_value(
            value,
            "rejection rate = {:.0%}" + f" of {tested} seeds",
        ),
        "threshold_description": (
            f"pass when the rejection rate >= {thresholds.adf_rejection_rate_pass:g}; "
            f"borderline when >= {thresholds.adf_rejection_rate_borderline:g}; "
            "fail otherwise."
        ),
        "verdict": verdict,
        "interpretation": interpretation,
    }


def _relative_ci_verdict_rows(
    convergence_table: pd.DataFrame,
    seed_count: int,
    thresholds: VerdictThresholds,
) -> list[dict[str, object]]:
    final_widths = final_relative_ci_half_widths(convergence_table)
    threshold_description = (
        f"pass when the relative 95% CI half-width <= "
        f"{thresholds.relative_ci_half_width_pass:g}; borderline when <= "
        f"{thresholds.relative_ci_half_width_borderline:g}; fail otherwise."
    )
    rows: list[dict[str, object]] = []
    for metric in RELATIVE_CI_VERDICT_METRICS:
        display_name = METRIC_DISPLAY_NAMES.get(metric, metric)
        value = _finite_or_none(final_widths.get(metric))
        verdict = _threshold_verdict(
            value,
            pass_below=thresholds.relative_ci_half_width_pass,
            borderline_below=thresholds.relative_ci_half_width_borderline,
        )
        if verdict == "pass":
            interpretation = (
                f"With {seed_count} seeds, the ensemble mean of {display_name} is "
                "estimated within the relative-error target, so the replication "
                "count is sufficient for this metric."
            )
        elif verdict in ("borderline", "fail"):
            interpretation = (
                f"The ensemble mean of {display_name} is still imprecise at "
                f"{seed_count} seeds; the convergence figure indicates how many "
                "additional replications would tighten it."
            )
        else:
            interpretation = (
                f"The relative precision of {display_name} is undefined (near-zero "
                "mean or too few seeds)."
            )
        rows.append(
            {
                "criterion": f"{display_name} ensemble precision at {seed_count} seeds",
                "category": "estimate_precision",
                "hypothesis": (
                    f"The achieved replication count estimates the ensemble mean of "
                    f"{display_name} to within the relative-error target of "
                    "Law (2015)."
                ),
                "metric_value": value if value is not None else np.nan,
                "metric_display": _format_value(value, "relative CI half-width = {:.3f}"),
                "threshold_description": threshold_description,
                "verdict": verdict,
                "interpretation": interpretation,
            }
        )
    return rows


def _condition_rows(seed_summary: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    """Yield (criterion prefix, summary row) pairs, one per condition.

    Replicate batches hold the configuration fixed, so the summary normally
    has exactly one condition row and the prefix stays empty. When several
    conditions appear (a manually assembled experiment folder), each verdict
    is labelled so per-condition rows stay distinguishable.
    """

    if seed_summary.empty:
        return [("", pd.Series(dtype=object))]
    if len(seed_summary) == 1:
        return [("", seed_summary.iloc[0])]
    return [
        (f"{_condition_display(row, index)}: ", row)
        for index, (_, row) in enumerate(seed_summary.iterrows(), start=1)
    ]


def _condition_display(row: pd.Series, index: int) -> str:
    """Match the verdict prefix to the summary table's short condition id."""

    condition_id = str(row.get("condition_id", "") or "")
    suffix = condition_id.removeprefix("condition_")
    if suffix != condition_id and suffix.isdigit():
        return f"Condition {suffix}"
    return f"Condition {index}"


def _threshold_verdict(
    value: float | None,
    *,
    pass_below: float | None = None,
    borderline_below: float | None = None,
    pass_above: float | None = None,
    borderline_above: float | None = None,
) -> str:
    if value is None:
        return "not_available"
    if pass_below is not None and borderline_below is not None:
        if value <= pass_below:
            return "pass"
        if value <= borderline_below:
            return "borderline"
        return "fail"
    if pass_above is not None and borderline_above is not None:
        if value >= pass_above:
            return "pass"
        if value >= borderline_above:
            return "borderline"
        return "fail"
    raise ValueError("A pass/borderline threshold pair must be supplied.")


def _cov_interpretation(display_name: str, value: float | None, verdict: str) -> str:
    if verdict == "pass":
        return (
            f"{display_name} is stable across random seeds: cross-seed dispersion "
            "is small relative to the ensemble mean."
        )
    if verdict == "borderline":
        return (
            f"{display_name} shows moderate cross-seed dispersion; report the "
            "ensemble mean together with its confidence interval."
        )
    if verdict == "fail":
        return (
            f"{display_name} varies strongly across seeds. Inspect the metric "
            "distribution figure before concluding anything: heavy-tailed "
            "regimes legitimately produce dispersed higher-moment estimates, so "
            "this flags sensitivity to random initialisation, not necessarily a "
            "modelling error."
        )
    return f"The coefficient of variation for {display_name} is unavailable."


def _success_rate_interpretation(
    fact_name: str,
    value: float | None,
    verdict: str,
) -> str:
    if verdict == "pass":
        return (
            f"'{fact_name}' is reproduced by a strong majority of seeds; the "
            "stylised fact is a property of the model, not of one random draw."
        )
    if verdict == "borderline":
        return (
            f"'{fact_name}' appears in a majority of seeds but not a strong one; "
            "the evidence is mixed across random draws."
        )
    if verdict == "fail":
        return (
            f"'{fact_name}' is reproduced by fewer seeds than required; the "
            "stylised fact is not robust to random initialisation at these "
            "parameter settings."
        )
    return f"The cross-seed success rate for '{fact_name}' is unavailable."


def _distribution_test_interpretation(display_name: str, verdict: str) -> str:
    if verdict == "pass":
        return (
            f"The {display_name} does not reject cross-seed equality; the seeds "
            "behave as replicates of one data-generating process."
        )
    if verdict == "borderline":
        return (
            f"The {display_name} rejects at the 5% level but not strongly; with "
            "long series, small and economically negligible differences can "
            "reach statistical significance."
        )
    if verdict == "fail":
        return (
            f"The {display_name} strongly rejects cross-seed equality; inspect "
            "the ECDF overlay and per-seed metrics to locate the difference."
        )
    return f"The {display_name} could not be evaluated."


def _finite_or_none(value: object) -> float | None:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric) or not np.isfinite(numeric):
        return None
    return float(numeric)


def _format_value(value: float | None, template: str) -> str:
    if value is None:
        return "not available"
    return template.format(value)
