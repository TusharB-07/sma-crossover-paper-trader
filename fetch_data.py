#!/usr/bin/env python3
"""Pre-fetch NSE daily data into the CSV cache so the dashboard works offline.

Usage:
    python fetch_data.py                     # default: RELIANCE.NS, 2y
    python fetch_data.py TCS.NS INFY.NS      # multiple symbols
    python fetch_data.py --period 5y RELIANCE.NS
    python fetch_data.py --refresh RELIANCE.NS   # force re-download

Run this before a demo (or a live presentation) so the Streamlit app never
has to depend on Yahoo Finance being reachable.
"""

from __future__ import annotations

import argparse

from data import fetch_history

DEFAULT_SYMBOLS = ["RELIANCE.NS"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Cache NSE daily OHLCV to CSV.")
    parser.add_argument("symbols", nargs="*", default=DEFAULT_SYMBOLS,
                        help="NSE tickers, e.g. RELIANCE.NS TCS.NS")
    parser.add_argument("--period", default="2y",
                        help="look-back window: 1mo 3mo 6mo 1y 2y 3y 5y (default 2y)")
    parser.add_argument("--refresh", action="store_true",
                        help="ignore the cache and force a fresh download")
    args = parser.parse_args()

    for sym in args.symbols:
        try:
            df, source = fetch_history(sym.upper(), period=args.period,
                                       force_refresh=args.refresh)
            print(f"{sym:>12}: {len(df):>5} bars  "
                  f"{df.index[0].date()} -> {df.index[-1].date()}  "
                  f"last close \u20b9{df['close'].iloc[-1]:,.2f}  [{source}]")
        except Exception as exc:
            print(f"{sym:>12}: FAILED - {exc}")


if __name__ == "__main__":
    main()
