"""Smoothing a price path for display: moving averages of the price.

A simulated price moves noisily from step to step, and over a few hundred steps
that noise hides the trend a reader is trying to judge. The dashboard therefore
draws a smoothed line over the raw one. The line is computed here, in the layer
every reported number comes from, so a smoothed value on the page and the same
value quoted anywhere else have one definition.

Three averages are offered. All are moving averages of the price; they differ in
how they weight the observations and in whether they look ahead.

``simple`` (trailing)
    **The average the model's chartists read.** The engine's
    ``Market::calculateMovingAverage`` is ``MA_t(h) = (1 / h) * sum_{k=0}^{h-1} P_{t-k}``:
    the mean of the last ``h`` prices, the current one included.
    :func:`compute_simple_moving_average` is that formula. A momentum chartist
    trades on ``log(MA_short / MA_long)`` and a mean-reversion chartist on the
    price against ``MA_long``, so this is the very quantity their rules compare
    with the price, and two such lines crossing is a momentum signal changing sign
    (when the rule's dead band is zero).
``exponential`` (trailing)
    Weights fall geometrically with age, ``w_k proportional to (1 - alpha)^k`` with
    ``alpha = 2 / (h + 1)``, so recent prices count most and no price drops out of
    the average abruptly. The equal-weight average jumps ``h`` steps after a large
    move, when the move leaves its window; this one does not. The weights are
    normalised over the observations available, so the first values do not lean on
    an arbitrary starting value (Roberts, 1959).
``centred``
    The simple average of the ``h`` prices centred on each step, later prices
    included. It does not lag the price, which makes it the better picture of the
    *shape* of a finished path (Hyndman and Athanasopoulos, 2021, use it to estimate
    a trend). But the value at step ``t`` depends on prices after ``t``, so it is
    not something a trader standing at ``t`` could have seen, and it is for reading
    the trend, not for explaining behaviour.

**A trailing average lags, and the lag is part of the reading.** On a steady trend a
trailing average trails the price by the mean age of its weights: ``(h - 1) / 2``
steps for the simple average (the group delay of an equal-weight filter; Oppenheim
and Schafer, 2010) and, by the same calculation, for the exponential average with
span ``h``. A crash therefore reaches the average later than it reaches the price,
so *when* something happened is read from the raw price and the average is read for
where the price was heading. The centred average has no lag, to within half a step
when ``h`` is even.

**None of them invents early or missing values.** No value is produced until ``h``
prices stand behind it (and, for the centred average, ahead of it too), and a step
with no price has no average. Averaging the few prices available at the start of a
series would draw a line that looks smoother than the data it rests on.

References:
    Brock, W., Lakonishok, J. and LeBaron, B. (1992). Simple technical trading
    rules and the stochastic properties of stock returns. *Journal of Finance*,
    47(5), 1731-1764.

    Hyndman, R. J. and Athanasopoulos, G. (2021). *Forecasting: Principles and
    Practice* (3rd ed.). OTexts. (Centred moving averages for trend estimation, in
    the chapter on time series decomposition.)

    Oppenheim, A. V. and Schafer, R. W. (2010). *Discrete-Time Signal Processing*
    (3rd ed.). Pearson.

    Roberts, S. W. (1959). Control chart tests based on geometric moving averages.
    *Technometrics*, 1(3), 239-250.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
import pandas as pd


#: Tokens naming the averages, in the order the interface offers them. They are
#: the keys of the dashboard payload, so a reader of the payload (or a test) can
#: tell which average a list of numbers is.
SIMPLE_METHOD = "simple"
EXPONENTIAL_METHOD = "exponential"
CENTRED_METHOD = "centred"
SMOOTHING_METHODS = (SIMPLE_METHOD, EXPONENTIAL_METHOD, CENTRED_METHOD)

#: The average shown first. The simple average is the one the chartists read, so
#: it is the one a reader is most likely to want to compare with their behaviour.
DEFAULT_SMOOTHING_METHOD = SIMPLE_METHOD

#: Which observations the average at step ``t`` uses: those up to and including
#: ``t`` (``"trailing"``), as an agent standing at ``t`` could; or those on both
#: sides of ``t`` (``"centred"``), which removes the lag but needs the future.
SMOOTHING_ALIGNMENTS = {
    SIMPLE_METHOD: "trailing",
    EXPONENTIAL_METHOD: "trailing",
    CENTRED_METHOD: "centred",
}

#: Window lengths, in observations, offered for smoothing a price path. 5 and 20
#: are the default short and long windows of the model's chartists
#: (``chartist_short_window`` and ``chartist_long_window``), so those two lines are
#: the averages their rules read. 50 is the shortest of the long windows tested by
#: Brock, Lakonishok and LeBaron (1992). These are display choices, not calibrated
#: parameters: nothing in the simulation depends on them.
PRICE_SMOOTHING_WINDOWS: tuple[int, ...] = (5, 20, 50)

#: A window is offered only when the series is at least this many windows long,
#: so the average covers at least half of the chart. A window that fills most of
#: the series leaves a line that is blank for most of the chart and says little.
#: This is a readability rule for the display, not a statistical one.
MINIMUM_WINDOWS_PER_SERIES = 2


def compute_simple_moving_average(values: pd.Series, window: int) -> pd.Series:
    """Return the trailing simple moving average of a series.

    The value at position ``t`` is the mean of the ``window`` observations ending
    at ``t``, the one at ``t`` included, which is the engine's own definition of a
    moving average.

    Args:
        values: Prices (or any series) in time order. Values that are not finite
            numbers are treated as missing.
        window: Number of observations averaged; a positive integer.

    Returns:
        A series on the same index as ``values``. The first ``window - 1``
        positions, and any position whose window holds a missing value, are
        ``NaN``: an average is reported only when ``window`` observed values stand
        behind it.

    Raises:
        ValueError: If ``window`` is not a positive integer.
    """

    length = _require_window(window)
    numbers = _finite_numbers(values)
    return numbers.rolling(window=length, min_periods=length).mean()


def compute_exponential_moving_average(values: pd.Series, window: int) -> pd.Series:
    """Return the trailing exponentially weighted moving average of a series.

    The value at position ``t`` is the weighted mean of the prices up to ``t``,
    with the price ``k`` steps back weighted ``(1 - alpha)^k`` and
    ``alpha = 2 / (window + 1)``. The weights are divided by their sum over the
    observations available, so every value is a weighted average of observed
    prices and none depends on a starting value. Its average age, and so its lag
    behind a steady trend, is ``(1 - alpha) / alpha = (window - 1) / 2`` steps: the
    same as the simple average of ``window`` steps.

    Args:
        values: Prices (or any series) in time order. Values that are not finite
            numbers are treated as missing.
        window: The span of the average, a positive integer. It is a *span*, not a
            cut-off: older prices still count, with weights that fall away.

    Returns:
        A series on the same index as ``values``. The first ``window - 1``
        positions are ``NaN``, as for the simple average, so that the two are
        comparable; a position with no price is ``NaN`` rather than the previous
        average carried forward.

    Raises:
        ValueError: If ``window`` is not a positive integer.
    """

    length = _require_window(window)
    numbers = _finite_numbers(values)
    average = numbers.ewm(span=length, adjust=True, min_periods=length).mean()
    return average.where(numbers.notna())


def compute_centred_moving_average(values: pd.Series, window: int) -> pd.Series:
    """Return the centred simple moving average of a series.

    The value at position ``t`` is the mean of the ``window`` observations centred
    on ``t``, so it uses prices after ``t`` and has no lag behind a steady trend.
    For an even window the observations cannot be split evenly: the average is
    taken over one more step before ``t`` than after it, which puts it half a step
    behind the price.

    Args:
        values: Prices (or any series) in time order. Values that are not finite
            numbers are treated as missing.
        window: Number of observations averaged; a positive integer.

    Returns:
        A series on the same index as ``values``. The positions without a full
        window on both sides, at the start and at the end of the series, and any
        position whose window holds a missing value, are ``NaN``.

    Raises:
        ValueError: If ``window`` is not a positive integer.
    """

    length = _require_window(window)
    numbers = _finite_numbers(values)
    return numbers.rolling(window=length, min_periods=length, center=True).mean()


_AVERAGES: dict[str, Callable[[pd.Series, int], pd.Series]] = {
    SIMPLE_METHOD: compute_simple_moving_average,
    EXPONENTIAL_METHOD: compute_exponential_moving_average,
    CENTRED_METHOD: compute_centred_moving_average,
}


def compute_price_average(method: str, values: pd.Series, window: int) -> pd.Series:
    """Return one of the offered averages of a series, chosen by name.

    Args:
        method: One of :data:`SMOOTHING_METHODS`.
        values: Prices in time order.
        window: Window (or span) of the average; a positive integer.

    Raises:
        ValueError: If ``method`` is not offered or ``window`` is not a positive
            integer.
    """

    try:
        average = _AVERAGES[method]
    except KeyError:
        raise ValueError(
            f"Unknown smoothing method {method!r}; expected one of {SMOOTHING_METHODS}."
        ) from None
    return average(values, window)


def usable_smoothing_windows(
    observation_count: int,
    windows: Sequence[int] = PRICE_SMOOTHING_WINDOWS,
) -> tuple[int, ...]:
    """Return the windows a series of this length can sensibly be smoothed with.

    Args:
        observation_count: Number of observations in the full-resolution series
            (not the thinned one drawn on the chart).
        windows: Candidate window lengths, shortest first.

    Returns:
        The candidates for which the series is at least
        :data:`MINIMUM_WINDOWS_PER_SERIES` windows long, in the order given. Empty
        when the series is too short for any of them.
    """

    return tuple(
        int(window)
        for window in windows
        if MINIMUM_WINDOWS_PER_SERIES * window <= observation_count
    )


def _require_window(window: object) -> int:
    """Return ``window`` as an ``int``, or raise if it is not a positive integer."""

    if not isinstance(window, (int, np.integer)) or window < 1:
        raise ValueError(f"Moving-average window must be a positive integer, got {window!r}.")
    return int(window)


def _finite_numbers(values: pd.Series) -> pd.Series:
    """Return ``values`` as floats, with anything that is not a finite number missing."""

    numbers = pd.to_numeric(pd.Series(values), errors="coerce")
    return numbers.where(np.isfinite(numbers))
