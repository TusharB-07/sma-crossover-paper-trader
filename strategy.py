"""SMA crossover signals - pure pandas, vectorised, no look-ahead.

First principles
----------------
A Simple Moving Average (SMA) of window N is the mean of the last N closing
prices:

    SMA_N(t) = ( close(t-N+1) + ... + close(t) ) / N

It smooths daily noise into a "consensus price" of recent market
participants. A short SMA reacts quickly (recent opinion), a long SMA reacts
slowly (established opinion). When the fast line crosses the slow line, the
short-term opinion has genuinely flipped relative to the longer-term one:

    GOLDEN CROSS : SMA_fast crosses ABOVE SMA_slow -> short-term momentum
                   turning up -> go long (BUY signal)
    DEATH CROSS  : SMA_fast crosses BELOW SMA_slow -> short-term momentum
                   turning down -> exit (SELL signal)

Signal convention used everywhere in this project:

    signal[t] = +1  means "on the CLOSE of day t a market BUY is queued"
    signal[t] = -1  means "on the CLOSE of day t a market SELL is queued"

The queue is FILLED at the OPEN of day t+1 by the engine (engine.py).
Signals never trade the price that generated them - that would be
look-ahead bias, the most common way backtests lie.
"""

from __future__ import annotations

import pandas as pd


def add_smas(df: pd.DataFrame, fast: int, slow: int) -> pd.DataFrame:
    """Return a copy of df with sma_fast / sma_slow columns added."""
    out = df.copy()
    out["sma_fast"] = out["close"].rolling(fast, min_periods=fast).mean()
    out["sma_slow"] = out["close"].rolling(slow, min_periods=slow).mean()
    return out


def generate_signals(df: pd.DataFrame, fast: int = 20, slow: int = 50) -> pd.DataFrame:
    """Return df with SMAs and a {+1, 0, -1} signal column.

    +1 = golden cross on this bar's close, -1 = death cross, 0 = no event.
    """
    if fast <= 0 or slow <= 0:
        raise ValueError("SMA windows must be positive")
    if fast >= slow:
        raise ValueError(f"fast window ({fast}) must be < slow window ({slow})")

    out = add_smas(df, fast, slow)

    above = out["sma_fast"] > out["sma_slow"]
    was_above = above.shift(1, fill_value=False)

    out["signal"] = 0
    out.loc[above & ~was_above, "signal"] = 1      # golden cross
    out.loc[~above & was_above, "signal"] = -1     # death cross

    # No signal may exist before both SMAs are fully defined.
    out.loc[out["sma_slow"].isna(), "signal"] = 0
    return out
