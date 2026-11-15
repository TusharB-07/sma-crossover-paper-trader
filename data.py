"""Data layer: NSE daily OHLCV from yfinance, cached to CSV.

Design goal: the demo must never die on a flaky network or a rate-limited
Yahoo Finance endpoint. The CSV cache in data/ acts as an offline backup:

    1. fresh yfinance download  -> served AND written to cache
    2. recent-enough local cache -> served (offline-safe)
    3. stale local cache        -> served as last resort, clearly labelled
"""

from __future__ import annotations

import os
from datetime import datetime

import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

_REQUIRED = ["open", "high", "low", "close", "volume"]

_PERIOD_OFFSETS = {
    "1mo": pd.DateOffset(months=1),
    "3mo": pd.DateOffset(months=3),
    "6mo": pd.DateOffset(months=6),
    "1y": pd.DateOffset(years=1),
    "2y": pd.DateOffset(years=2),
    "3y": pd.DateOffset(years=3),
    "5y": pd.DateOffset(years=5),
}


def _cache_path(symbol: str) -> str:
    safe = symbol.replace("/", "_").replace(".", "_")
    return os.path.join(DATA_DIR, f"{safe}.csv")


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise any yfinance frame to: naive DatetimeIndex + lowercase OHLCV."""
    if df is None or len(df) == 0:
        raise ValueError("empty dataframe from source")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    missing = [c for c in _REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    df = df[_REQUIRED].copy()
    df.index = pd.to_datetime(df.index)
    try:
        df.index = df.index.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    df.index.name = "date"
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(subset=["close"])
    for c in ["open", "high", "low", "close"]:
        df[c] = df[c].astype(float)
    df["volume"] = df["volume"].fillna(0.0).astype(float)
    return df


def _read_cache(symbol: str) -> pd.DataFrame | None:
    path = _cache_path(symbol)
    if not os.path.exists(path):
        return None
    try:
        raw = pd.read_csv(path, index_col="date", parse_dates=True)
        return _clean(raw)
    except Exception:
        return None


def _write_cache(symbol: str, df: pd.DataFrame) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_csv(_cache_path(symbol), index=True)


def _slice_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """Trim a cached frame to the requested look-back window."""
    off = _PERIOD_OFFSETS.get(period)
    if off is None:
        return df
    start = df.index[-1] - off
    sub = df.loc[df.index >= start]
    # keep at least enough bars for a 50-day SMA to mean something
    return sub if len(sub) >= 10 else df


def fetch_history(
    symbol: str,
    period: str = "2y",
    max_cache_age_days: int = 7,
    force_refresh: bool = False,
) -> tuple[pd.DataFrame, str]:
    """Return (ohlcv_dataframe, source_description).

    The second value is shown in the UI so the audience always knows whether
    they are looking at live-downloaded data or the offline cache.
    """
    cached = _read_cache(symbol)

    if cached is not None and not force_refresh:
        last = cached.index[-1].to_pydatetime()
        age_days = (datetime.now() - last).days
        if age_days <= max_cache_age_days:
            return _slice_period(cached, period), f"local cache (age {age_days} day(s))"

    try:
        import yfinance as yf

        raw = yf.download(
            symbol, period=period, interval="1d", progress=False, auto_adjust=True
        )
        fresh = _clean(raw)
        if len(fresh) > 0:
            _write_cache(symbol, fresh)
            return fresh, "yfinance (fresh download)"
    except Exception:
        pass

    if cached is not None:
        return (
            _slice_period(cached, period),
            f"local cache (OFFLINE FALLBACK, last bar {cached.index[-1].date()})",
        )

    raise RuntimeError(
        f"No data for {symbol!r}: yfinance failed and no CSV cache exists. "
        f"Run `python fetch_data.py {symbol}` while connected, then retry."
    )
