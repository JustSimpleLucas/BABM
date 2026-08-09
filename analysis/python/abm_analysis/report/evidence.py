"""Quantitative stylised-fact evidence summaries for static HTML reports."""

from __future__ import annotations

import numpy as np
import pandas as pd

from abm_analysis.diagnostics import SIGNIFICANCE_LEVEL


def build_run_evidence_assessment(
    diagnostics: pd.DataFrame,
    *,
    significance_level: float = SIGNIFICANCE_LEVEL,
) -> list[dict[str, str]]:
    """Explain stylised-fact evidence for one run, asset by asset.

    The report uses these texts to make each statistical decision auditable:
    readers can see the null hypothesis, the numerical threshold, and the
    measured value that produced the conclusion shown in the summary cards.

    A multi-asset run contributes one full set of cards per asset, each labelled
    with the market it describes. Every market therefore gets its own verdict
    rather than inheriting whichever one the primary asset happened to produce;
    the two markets can legitimately disagree, and that disagreement is a result
    rather than something to average away.
    """

    if diagnostics.empty:
        row = pd.Series(dtype=object)
        return _asset_evidence_cards(row, significance_level, asset_label="")

    cards: list[dict[str, str]] = []
    for _, row in diagnostics.iterrows():
        asset_label = str(row.get("asset", "") or "") if "asset" in diagnostics.columns else ""
        cards.extend(_asset_evidence_cards(row, significance_level, asset_label=asset_label))
    return cards


def _asset_evidence_cards(
    row: pd.Series,
    significance_level: float,
    *,
    asset_label: str,
) -> list[dict[str, str]]:
    """Build one run's three stylised-fact cards, optionally named by asset."""

    cards = [
        _single_autocorrelation_assessment(row, significance_level),
        _single_fat_tail_assessment(row, significance_level),
        _single_volatility_assessment(row, significance_level),
    ]
    if not asset_label:
        return cards
    for card in cards:
        card["fact"] = f"{card['fact']} — {asset_label}"
    return cards


def build_comparison_evidence_assessment(
    diagnostics: pd.DataFrame,
    *,
    significance_level: float = SIGNIFICANCE_LEVEL,
) -> list[dict[str, str]]:
    """Aggregate stylised-fact evidence across comparison-report runs."""

    return [
        _comparison_autocorrelation_assessment(diagnostics, significance_level),
        _comparison_fat_tail_assessment(diagnostics, significance_level),
        _comparison_volatility_assessment(diagnostics, significance_level),
    ]


def _single_autocorrelation_assessment(
    row: pd.Series,
    significance_level: float,
) -> dict[str, str]:
    minimum_p_value = _numeric_value(row, "minimum_ljung_box_p_value")
    threshold = _format_threshold(significance_level)
    if minimum_p_value is None:
        return _assessment_card(
            "Weak raw-return autocorrelation",
            "Not available",
            "neutral",
            "Stylised-fact hypothesis: raw log returns have weak linear autocorrelation. "
            "The Ljung-Box test evaluates the null hypothesis of no autocorrelation "
            "across the configured lags.",
            f"Minimum Ljung-Box p-value is not available; threshold = {threshold}.",
            "The report cannot classify this stylised fact without a finite Ljung-Box p-value.",
        )

    has_evidence = minimum_p_value > significance_level
    verdict = "Evidence" if has_evidence else "Not evidence / mixed evidence"
    tone = "teal" if has_evidence else "amber"
    interpretation = (
        "Evidence consistent with weak raw-return autocorrelation because the "
        "Ljung-Box no-autocorrelation null is not rejected."
        if has_evidence
        else "Not evidence for weak raw-return autocorrelation because the "
        "Ljung-Box test rejects the no-autocorrelation null."
    )
    return _assessment_card(
        "Weak raw-return autocorrelation",
        verdict,
        tone,
        "Stylised-fact hypothesis: raw log returns have weak linear autocorrelation. "
        "The Ljung-Box test evaluates the null hypothesis of no autocorrelation "
        "across the configured lags.",
        (
            f"Minimum Ljung-Box p-value = {_format_number(minimum_p_value)}; "
            f"threshold = {threshold}. Evidence is recorded when p-value > {threshold}."
        ),
        interpretation,
    )


def _single_fat_tail_assessment(
    row: pd.Series,
    significance_level: float,
) -> dict[str, str]:
    excess_kurtosis = _numeric_value(row, "excess_kurtosis")
    jarque_bera_p_value = _numeric_value(row, "jarque_bera_p_value")
    threshold = _format_threshold(significance_level)
    if excess_kurtosis is None or jarque_bera_p_value is None:
        return _assessment_card(
            "Fat-tailed returns",
            "Not available",
            "neutral",
            "Stylised-fact hypothesis: simulated returns have heavier tails than a "
            "Gaussian benchmark. The report combines excess kurtosis with the "
            "Jarque-Bera normality test.",
            (
                "Excess kurtosis or Jarque-Bera p-value is not available; "
                f"threshold = {threshold}."
            ),
            "The report cannot classify this stylised fact without both tail metrics.",
        )

    has_evidence = excess_kurtosis > 0 and jarque_bera_p_value < significance_level
    verdict = "Evidence" if has_evidence else "Not evidence / mixed evidence"
    tone = "teal" if has_evidence else "amber"
    if has_evidence:
        interpretation = (
            "Evidence consistent with fat-tailed returns because excess kurtosis is "
            "positive and Jarque-Bera rejects normality."
        )
    elif excess_kurtosis > 0:
        interpretation = (
            "Mixed evidence: excess kurtosis is positive, but Jarque-Bera does not "
            "reject normality at the chosen threshold."
        )
    elif jarque_bera_p_value < significance_level:
        interpretation = (
            "Mixed evidence: Jarque-Bera rejects normality, but excess kurtosis is "
            "not positive, so the rejection is not interpreted as fat-tail evidence."
        )
    else:
        interpretation = (
            "Not evidence for fat-tailed returns because excess kurtosis is not "
            "positive and normality is not rejected."
        )

    return _assessment_card(
        "Fat-tailed returns",
        verdict,
        tone,
        "Stylised-fact hypothesis: simulated returns have heavier tails than a "
        "Gaussian benchmark. The report combines excess kurtosis with the "
        "Jarque-Bera normality test.",
        (
            f"Excess kurtosis = {_format_number(excess_kurtosis)}; "
            f"Jarque-Bera p-value = {_format_number(jarque_bera_p_value)}; "
            f"threshold = {threshold}. Evidence is recorded when excess kurtosis > 0 "
            f"and p-value < {threshold}."
        ),
        interpretation,
    )


def _single_volatility_assessment(
    row: pd.Series,
    significance_level: float,
) -> dict[str, str]:
    arch_p_value = _numeric_value(row, "minimum_arch_lm_p_value")
    alpha1 = _numeric_value(row, "garch_alpha1")
    beta1 = _numeric_value(row, "garch_beta1")
    persistence = _numeric_value(row, "garch_persistence")
    threshold = _format_threshold(significance_level)
    if arch_p_value is None:
        return _assessment_card(
            "Volatility clustering",
            "Not available",
            "neutral",
            "Stylised-fact hypothesis: absolute or squared returns show persistent "
            "volatility dependence. The ARCH LM test evaluates the null hypothesis "
            "of no ARCH effects.",
            f"Minimum ARCH LM p-value is not available; threshold = {threshold}.",
            "The report cannot classify this stylised fact without a finite ARCH LM p-value.",
        )

    has_arch_evidence = arch_p_value < significance_level
    has_garch_support = (
        alpha1 is not None
        and beta1 is not None
        and alpha1 > 0
        and beta1 > 0
    )
    verdict = "Evidence" if has_arch_evidence else "Not evidence / mixed evidence"
    tone = "teal" if has_arch_evidence else "amber"
    if has_arch_evidence and has_garch_support:
        interpretation = (
            "Evidence consistent with volatility clustering because ARCH LM rejects "
            "no ARCH effects, and positive GARCH alpha and beta indicate persistent "
            "conditional volatility."
        )
    elif has_arch_evidence:
        interpretation = (
            "Evidence consistent with volatility clustering because ARCH LM rejects "
            "no ARCH effects; GARCH persistence does not strengthen the conclusion."
        )
    elif has_garch_support:
        interpretation = (
            "Mixed evidence: GARCH alpha and beta are positive, but ARCH LM does not "
            "reject no ARCH effects at the chosen threshold."
        )
    else:
        interpretation = (
            "Not evidence for volatility clustering because ARCH LM does not reject "
            "no ARCH effects."
        )

    return _assessment_card(
        "Volatility clustering",
        verdict,
        tone,
        "Stylised-fact hypothesis: absolute or squared returns show persistent "
        "volatility dependence. The ARCH LM test evaluates the null hypothesis "
        "of no ARCH effects.",
        (
            f"Minimum ARCH LM p-value = {_format_number(arch_p_value)}; "
            f"threshold = {threshold}. Evidence is recorded when p-value < {threshold}. "
            f"GARCH alpha1 = {_format_optional_number(alpha1)}, "
            f"beta1 = {_format_optional_number(beta1)}, "
            f"persistence = {_format_optional_number(persistence)}."
        ),
        interpretation,
    )


def _comparison_autocorrelation_assessment(
    diagnostics: pd.DataFrame,
    significance_level: float,
) -> dict[str, str]:
    p_values = _finite_numeric_values(diagnostics, "minimum_ljung_box_p_value")
    threshold = _format_threshold(significance_level)
    if p_values.empty:
        return _comparison_unavailable_card(
            "Weak raw-return autocorrelation",
            "Minimum Ljung-Box p-value is unavailable for all diagnostic rows.",
        )

    evidence_mask = p_values > significance_level
    support_count = int(evidence_mask.sum())
    total_count = int(len(p_values))
    return _assessment_card(
        "Weak raw-return autocorrelation",
        _comparison_verdict(support_count, total_count),
        _comparison_tone(support_count, total_count),
        "Stylised-fact hypothesis: raw log returns have weak linear autocorrelation. "
        "A run supports the hypothesis when the Ljung-Box no-autocorrelation null "
        "is not rejected.",
        (
            f"Evidence in {_format_support(support_count, total_count)}. "
            f"Minimum Ljung-Box p-value {_format_distribution(p_values)}; "
            f"threshold = {threshold}. Evidence is recorded when p-value > {threshold}."
        ),
        _comparison_interpretation(
            support_count,
            total_count,
            "weak raw-return autocorrelation",
        ),
    )


def _comparison_fat_tail_assessment(
    diagnostics: pd.DataFrame,
    significance_level: float,
) -> dict[str, str]:
    data = _finite_numeric_frame(
        diagnostics,
        ["excess_kurtosis", "jarque_bera_p_value"],
    )
    threshold = _format_threshold(significance_level)
    if data.empty:
        return _comparison_unavailable_card(
            "Fat-tailed returns",
            "Excess kurtosis and Jarque-Bera p-value are unavailable for all diagnostic rows.",
        )

    evidence_mask = (
        data["excess_kurtosis"] > 0
    ) & (
        data["jarque_bera_p_value"] < significance_level
    )
    support_count = int(evidence_mask.sum())
    total_count = int(len(data))
    return _assessment_card(
        "Fat-tailed returns",
        _comparison_verdict(support_count, total_count),
        _comparison_tone(support_count, total_count),
        "Stylised-fact hypothesis: simulated returns have heavier tails than a "
        "Gaussian benchmark. A run supports the hypothesis when excess kurtosis "
        "is positive and Jarque-Bera rejects normality.",
        (
            f"Evidence in {_format_support(support_count, total_count)}. "
            f"Excess kurtosis {_format_distribution(data['excess_kurtosis'])}; "
            f"Jarque-Bera p-value {_format_distribution(data['jarque_bera_p_value'])}; "
            f"threshold = {threshold}. Evidence is recorded when excess kurtosis > 0 "
            f"and p-value < {threshold}."
        ),
        _comparison_interpretation(support_count, total_count, "fat-tailed returns"),
    )


def _comparison_volatility_assessment(
    diagnostics: pd.DataFrame,
    significance_level: float,
) -> dict[str, str]:
    arch_p_values = _finite_numeric_values(diagnostics, "minimum_arch_lm_p_value")
    threshold = _format_threshold(significance_level)
    if arch_p_values.empty:
        return _comparison_unavailable_card(
            "Volatility clustering",
            "Minimum ARCH LM p-value is unavailable for all diagnostic rows.",
        )

    evidence_mask = arch_p_values < significance_level
    support_count = int(evidence_mask.sum())
    total_count = int(len(arch_p_values))
    garch_positive_count = _positive_garch_count(diagnostics)
    persistence = _finite_numeric_values(diagnostics, "garch_persistence")
    persistence_text = (
        f"; GARCH persistence {_format_distribution(persistence)}"
        if not persistence.empty
        else ""
    )
    return _assessment_card(
        "Volatility clustering",
        _comparison_verdict(support_count, total_count),
        _comparison_tone(support_count, total_count),
        "Stylised-fact hypothesis: absolute or squared returns show persistent "
        "volatility dependence. A run supports the hypothesis when ARCH LM rejects "
        "the null hypothesis of no ARCH effects.",
        (
            f"Evidence in {_format_support(support_count, total_count)}. "
            f"ARCH LM p-value {_format_distribution(arch_p_values)}; "
            f"threshold = {threshold}. Evidence is recorded when p-value < {threshold}. "
            f"Positive GARCH alpha and beta appear in {garch_positive_count}/{total_count} "
            f"runs with available ARCH evidence{persistence_text}."
        ),
        _comparison_interpretation(support_count, total_count, "volatility clustering"),
    )


def _assessment_card(
    fact: str,
    verdict: str,
    tone: str,
    hypothesis: str,
    quantitative_evidence: str,
    interpretation: str,
) -> dict[str, str]:
    return {
        "fact": fact,
        "verdict": verdict,
        "tone": tone,
        "hypothesis": hypothesis,
        "quantitative_evidence": quantitative_evidence,
        "interpretation": interpretation,
    }


def _comparison_unavailable_card(fact: str, reason: str) -> dict[str, str]:
    return _assessment_card(
        fact,
        "Not available",
        "neutral",
        "The stylised-fact hypothesis is defined, but the required quantitative "
        "diagnostics are unavailable in this report.",
        reason,
        "No evidence classification is made for this stylised fact.",
    )


def _numeric_value(row: pd.Series, column: str) -> float | None:
    if column not in row:
        return None
    value = pd.to_numeric(pd.Series([row[column]]), errors="coerce").iloc[0]
    if pd.isna(value) or not np.isfinite(value):
        return None
    return float(value)


def _finite_numeric_values(data: pd.DataFrame, column: str) -> pd.Series:
    if data.empty or column not in data.columns:
        return pd.Series(dtype=float)
    values = pd.to_numeric(data[column], errors="coerce")
    return values[values.notna() & np.isfinite(values)].astype(float)


def _finite_numeric_frame(data: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if data.empty or not set(columns).issubset(data.columns):
        return pd.DataFrame(columns=columns, dtype=float)
    numeric = data[columns].apply(pd.to_numeric, errors="coerce")
    finite_mask = numeric.notna().all(axis=1) & np.isfinite(numeric).all(axis=1)
    return numeric[finite_mask].astype(float)


def _positive_garch_count(diagnostics: pd.DataFrame) -> int:
    data = _finite_numeric_frame(
        diagnostics,
        ["minimum_arch_lm_p_value", "garch_alpha1", "garch_beta1"],
    )
    if data.empty:
        return 0
    return int(((data["garch_alpha1"] > 0) & (data["garch_beta1"] > 0)).sum())


def _format_distribution(values: pd.Series) -> str:
    median = float(values.median())
    minimum = float(values.min())
    maximum = float(values.max())
    if len(values) == 1:
        return f"= {_format_number(median)}"
    return (
        f"median = {_format_number(median)}, "
        f"range = {_format_number(minimum)} to {_format_number(maximum)}"
    )


def _format_support(support_count: int, total_count: int) -> str:
    percentage = 100.0 * support_count / total_count if total_count else 0.0
    return f"{support_count}/{total_count} runs ({percentage:.1f}%)"


def _comparison_verdict(support_count: int, total_count: int) -> str:
    if total_count == 0:
        return "Not available"
    if support_count > 0:
        return "Evidence" if support_count == total_count else "Mixed evidence"
    return "Not evidence / mixed evidence"


def _comparison_tone(support_count: int, total_count: int) -> str:
    if total_count == 0:
        return "neutral"
    return "teal" if support_count / total_count >= 0.5 else "amber"


def _comparison_interpretation(
    support_count: int,
    total_count: int,
    stylised_fact: str,
) -> str:
    if support_count == total_count:
        return (
            f"All analysed runs provide evidence consistent with {stylised_fact}; "
            "the conclusion is robust across the available experiment rows."
        )
    if support_count > 0:
        return (
            f"Some runs provide evidence consistent with {stylised_fact}, but the "
            "experiment-level conclusion is mixed across seeds or parameter settings."
        )
    return (
        f"No analysed runs provide quantitative evidence consistent with {stylised_fact} "
        "under the configured decision rule."
    )


def _format_optional_number(value: float | None) -> str:
    return _format_number(value) if value is not None else "not available"


def _format_number(value: float) -> str:
    magnitude = abs(value)
    if magnitude != 0 and magnitude < 0.001:
        return f"{value:.3e}"
    return f"{value:.4f}"


def _format_threshold(value: float) -> str:
    return f"{value:g}"
