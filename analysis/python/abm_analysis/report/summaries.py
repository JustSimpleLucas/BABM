"""Key-metric summary rows for static ABM reports."""

from __future__ import annotations

import pandas as pd

def _comparison_key_metric_rows(
    runs_index: pd.DataFrame,
    diagnostics: pd.DataFrame,
) -> list[dict[str, str]]:
    """Build the key-metrics table rows for an experiment comparison report."""

    run_count = _row_count(runs_index, diagnostics)
    return [
        _metric_row(
            "Runs Analysed",
            f"{run_count:,}",
            "Archived simulation runs included in this comparison.",
        ),
        _numeric_metric_row(
            "Observation Count",
            diagnostics,
            "observation_count",
            "Finite log-return observations used by the diagnostics.",
            integer=True,
        ),
        _numeric_metric_row(
            "Max Drawdown",
            runs_index,
            "max_drawdown",
            "Range across available run-level summary metrics.",
        ),
        _numeric_metric_row(
            "Mean Allocative Efficiency",
            runs_index,
            "mean_allocative_efficiency",
            "Gross CDA surplus captured across positive-surplus double-auction steps.",
        ),
        _numeric_metric_row(
            "Return Std. Dev.",
            diagnostics,
            "log_return_std_dev",
            "Range of realised log-return dispersion across runs.",
        ),
        _numeric_metric_row(
            "Excess Kurtosis",
            diagnostics,
            "excess_kurtosis",
            "Range of tail-thickness diagnostics across runs.",
        ),
        _evidence_metric_row(
            "Fat-Tail Evidence",
            diagnostics,
            "fat_tail_conclusion",
            "fat-tailed returns",
            "Evidence consistent with fat-tailed returns.",
        ),
        _evidence_metric_row(
            "Volatility Clustering",
            diagnostics,
            "volatility_clustering_conclusion",
            "volatility clustering",
            "Evidence consistent with volatility clustering.",
        ),
        _evidence_metric_row(
            "Raw-Return Autocorrelation",
            diagnostics,
            "autocorrelation_conclusion",
            "absence of autocorrelation",
            "Consistent with weak raw-return autocorrelation.",
        ),
    ]

def _run_key_metric_rows(
    runs_index: pd.DataFrame,
    diagnostics: pd.DataFrame,
) -> list[dict[str, str]]:
    """Build the key-metrics table rows for a single-run report."""

    return [
        _metric_row(
            "Runs Analysed",
            "1",
            "Single archived simulation run.",
        ),
        _numeric_metric_row(
            "Observation Count",
            diagnostics,
            "observation_count",
            "Finite log-return observations used by the diagnostics.",
            integer=True,
        ),
        _numeric_metric_row(
            "Max Drawdown",
            runs_index,
            "max_drawdown",
            "Run-level summary metric when available.",
        ),
        _numeric_metric_row(
            "Mean Allocative Efficiency",
            runs_index,
            "mean_allocative_efficiency",
            "Gross CDA surplus captured across positive-surplus double-auction steps.",
        ),
        _numeric_metric_row(
            "Return Std. Dev.",
            diagnostics,
            "log_return_std_dev",
            "Realised log-return dispersion for this run.",
        ),
        _numeric_metric_row(
            "Excess Kurtosis",
            diagnostics,
            "excess_kurtosis",
            "Tail-thickness diagnostic for this run.",
        ),
        _single_evidence_metric_row(
            "Fat-Tail Evidence",
            diagnostics,
            "fat_tail_conclusion",
            "fat-tailed returns",
        ),
        _single_evidence_metric_row(
            "Volatility Clustering",
            diagnostics,
            "volatility_clustering_conclusion",
            "volatility clustering",
        ),
        _single_evidence_metric_row(
            "Raw-Return Autocorrelation",
            diagnostics,
            "autocorrelation_conclusion",
            "absence of autocorrelation",
        ),
    ]

def _seed_robustness_key_metric_rows(
    runs_index: pd.DataFrame,
    diagnostics: pd.DataFrame,
    ks_summary: dict[str, float],
    adf_summary: dict[str, float],
    verdicts: pd.DataFrame,
) -> list[dict[str, str]]:
    """Build the key-metrics table rows for a seed-robustness report."""

    seed_count = 0
    if not runs_index.empty and "seed" in runs_index.columns:
        seed_count = int(pd.to_numeric(runs_index["seed"], errors="coerce").nunique())
    rows = [
        _metric_row(
            "Seeds Analysed",
            f"{seed_count:,}" if seed_count else "Not available",
            "Distinct random seeds with archived simulation runs.",
        ),
        _numeric_metric_row(
            "Observation Count",
            diagnostics,
            "observation_count",
            "Finite log-return observations per seed used by the diagnostics.",
            integer=True,
        ),
        _metric_row(
            "Mean Pairwise K-S Statistic",
            _format_optional_summary_number(ks_summary.get("mean_ks_statistic")),
            "Average distributional distance between seed pairs (0 = identical).",
        ),
        _metric_row(
            "K-S Insignificant Share",
            _format_optional_share(ks_summary.get("insignificant_share")),
            "Share of seed pairs whose return distributions are statistically "
            "indistinguishable at the 5% level.",
        ),
        _metric_row(
            "ADF Rejection Rate",
            _format_optional_share(adf_summary.get("rejection_rate")),
            "Share of seeds rejecting the unit-root null, i.e. with stationary "
            "log returns.",
        ),
        _metric_row(
            "Verdict Tally",
            _verdict_tally(verdicts),
            "Pass / borderline / fail counts across all robustness criteria "
            "in the verdict table.",
        ),
    ]
    return rows

def _verdict_tally(verdicts: pd.DataFrame) -> str:
    if verdicts.empty or "verdict" not in verdicts.columns:
        return "Not available"
    counts = verdicts["verdict"].astype(str).value_counts()
    return (
        f"{int(counts.get('pass', 0))} pass / "
        f"{int(counts.get('borderline', 0))} borderline / "
        f"{int(counts.get('fail', 0))} fail"
    )

def _format_optional_share(value: object) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return "Not available"
    return f"{float(numeric):.0%}"

def _format_optional_summary_number(value: object) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return "Not available"
    return _format_summary_number(float(numeric))

def _row_count(primary: pd.DataFrame, fallback: pd.DataFrame) -> int:
    if not primary.empty:
        return int(len(primary))
    return int(len(fallback))

def _metric_row(metric: str, value: str, note: str) -> dict[str, str]:
    return {
        "metric": metric,
        "value": value if value else "Not available",
        "note": note,
    }

def _numeric_metric_row(
    metric: str,
    data: pd.DataFrame,
    column: str,
    note: str,
    *,
    integer: bool = False,
) -> dict[str, str]:
    values = _finite_numeric_values(data, column)
    value = _format_numeric_range(values, integer=integer)
    return _metric_row(metric, value, note)

def _evidence_metric_row(
    metric: str,
    diagnostics: pd.DataFrame,
    column: str,
    evidence_phrase: str,
    note: str,
) -> dict[str, str]:
    values = _non_empty_strings(diagnostics, column)
    if not values:
        return _metric_row(metric, "Not available", note)

    evidence_count = sum(evidence_phrase.lower() in value.lower() for value in values)
    return _metric_row(metric, f"{evidence_count}/{len(values)} runs", note)

def _single_evidence_metric_row(
    metric: str,
    diagnostics: pd.DataFrame,
    column: str,
    evidence_phrase: str,
) -> dict[str, str]:
    """Summarise one stylised fact for a single run, asset by asset.

    A multi-asset run has one conclusion per market and they need not agree, so
    the value names each asset instead of collapsing to the first row. Reducing
    two markets to one verdict would hide exactly the cross-asset difference the
    two-asset model exists to show.
    """

    conclusions = _conclusions_by_asset(diagnostics, column)
    if not conclusions:
        return _metric_row(metric, "Not available", "Diagnostic conclusion is unavailable.")

    def summarise(conclusion: str) -> str:
        if evidence_phrase.lower() in conclusion.lower():
            return "Consistent"
        return _short_conclusion(conclusion)

    if len(conclusions) == 1:
        asset, conclusion = conclusions[0]
        return _metric_row(metric, summarise(conclusion), conclusion)

    value = " · ".join(f"{asset}: {summarise(conclusion)}" for asset, conclusion in conclusions)
    note = " ".join(f"{asset}: {conclusion}" for asset, conclusion in conclusions)
    return _metric_row(metric, value, note)

def _conclusions_by_asset(diagnostics: pd.DataFrame, column: str) -> list[tuple[str, str]]:
    """Pair each diagnostic conclusion with the asset that produced it.

    Falls back to positional labels for frames without an ``asset`` column, so
    archives predating the multi-asset extension keep their single-row summary.
    """

    if diagnostics.empty or column not in diagnostics.columns:
        return []

    assets: list[str]
    if "asset" in diagnostics.columns:
        assets = [str(value or "") for value in diagnostics["asset"].tolist()]
    else:
        assets = [""] * len(diagnostics)

    pairs: list[tuple[str, str]] = []
    for asset, conclusion in zip(assets, diagnostics[column].tolist()):
        text = "" if pd.isna(conclusion) else str(conclusion).strip()
        if text:
            pairs.append((asset, text))
    return pairs

def _finite_numeric_values(data: pd.DataFrame, column: str) -> pd.Series:
    if data.empty or column not in data.columns:
        return pd.Series(dtype=float)
    values = pd.to_numeric(data[column], errors="coerce")
    return values[values.notna()]

def _non_empty_strings(data: pd.DataFrame, column: str) -> list[str]:
    if data.empty or column not in data.columns:
        return []
    values = data[column].dropna().astype(str).str.strip()
    return [value for value in values if value]

def _format_numeric_range(values: pd.Series, *, integer: bool = False) -> str:
    if values.empty:
        return "Not available"
    minimum = values.min()
    maximum = values.max()
    if pd.isna(minimum) or pd.isna(maximum):
        return "Not available"
    if minimum == maximum:
        return _format_summary_number(float(minimum), integer=integer)
    return (
        f"{_format_summary_number(float(minimum), integer=integer)} to "
        f"{_format_summary_number(float(maximum), integer=integer)}"
    )

def _format_summary_number(value: float, *, integer: bool = False) -> str:
    if integer:
        return f"{int(round(value)):,}"
    magnitude = abs(value)
    if magnitude != 0 and magnitude < 0.001:
        return f"{value:.3e}"
    return f"{value:.4f}"

def _short_conclusion(conclusion: str) -> str:
    lowered = conclusion.lower()
    if "unavailable" in lowered:
        return "Not available"
    if "weak" in lowered or "mixed" in lowered:
        return "Weak or mixed"
    if "evidence" in lowered or "rejected" in lowered or "persistence" in lowered:
        return "Evidence present"
    return "Review"
