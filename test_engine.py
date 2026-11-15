"""Deterministic unit tests for the strategy and the paper-trading engine.

Run with plain Python (no pytest needed):

    python test_engine.py

The tests use synthetic price series where the crossover dates are known in
advance, so correctness can be checked exactly - including the no-look-ahead
rule (a signal at close of day t must fill at open of day t+1).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from engine import run_backtest
from strategy import generate_signals


def make_df(closes, opens=None, start="2025-01-01"):
    """Build a minimal OHLCV frame from a close series."""
    closes = np.asarray(closes, dtype=float)
    opens = np.asarray(opens if opens is not None else closes, dtype=float)
    idx = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, closes),
            "low": np.minimum(opens, closes),
            "close": closes,
            "volume": 1_000_000.0,
        },
        index=idx,
    )


def test_golden_cross_fires_on_exact_day():
    # 50 flat days at 100 (both SMAs = 100), then a ramp starting at day 50.
    closes = [100.0] * 50 + [100.0 + k for k in range(1, 31)]
    sig = generate_signals(make_df(closes), 20, 50)
    assert int(sig["signal"].iloc[50]) == 1, "golden cross must fire on the first ramp day"
    assert (sig["signal"].iloc[:50] == 0).all(), "no signal allowed before the cross"
    assert int(sig["signal"].sum()) == 1, "exactly one cross in this series"


def test_fill_happens_at_next_open_with_costs():
    # Signal on day 50's close -> BUY must fill on day 51's OPEN.
    closes = [100.0] * 50 + [100.0 + k for k in range(1, 12)]
    opens = [100.0] * 51 + [105.0] * 10
    res = run_backtest(make_df(closes, opens), initial_cash=100_000,
                       brokerage=20.0, slippage_bps=5.0)
    assert len(res.fills) == 1, "exactly one fill expected"
    f = res.fills.iloc[0]
    assert f["side"] == "BUY"
    assert f["date"] == res.data.index[51], "fill must be on the day AFTER the signal"
    assert abs(f["price"] - 105.0 * (1 + 5 / 10_000)) < 1e-9, "fill = open + slippage"
    assert f["qty"] == int((100_000 - 20.0) // (105.0 * 1.0005)), "whole shares, fees-aware sizing"


def test_cash_conservation_and_no_leverage():
    # Up-trend then down-trend: forces a full round trip.
    closes = [100.0] * 50 + list(100 + np.arange(1, 41)) + list(np.linspace(140, 90, 40))
    res = run_backtest(make_df(closes), initial_cash=100_000)
    eq = res.equity
    assert np.allclose(eq["cash"] + eq["position_value"], eq["equity"]), "equity = cash + position"
    assert (eq["cash"] >= -1e-9).all(), "cash can never go negative"
    flat = eq[eq["qty"] == 0]
    assert len(flat) and np.allclose(flat["cash"], flat["equity"]), "when flat, equity == cash"


def test_trade_pnl_reconciles_with_account():
    closes = [100.0] * 50 + list(100 + np.arange(1, 41)) + list(np.linspace(140, 90, 40))
    res = run_backtest(make_df(closes), initial_cash=100_000)
    # The series ends flat, so: final equity = initial cash + sum of closed P&L.
    assert len(res.trades) >= 1, "an up-move followed by a down-move must close at least one trade"
    recon = res.metrics["final_equity"] - 100_000 - res.trades["pnl"].sum()
    assert abs(recon) < 1e-6, "closed-trade P&L must reconcile with the account"


def test_metrics_are_sane():
    closes = [100.0] * 50 + list(100 + np.arange(1, 41)) + list(np.linspace(140, 90, 40))
    res = run_backtest(make_df(closes), initial_cash=100_000)
    m = res.metrics
    assert 0.0 <= m["win_rate"] <= 1.0
    assert m["max_drawdown"] <= 0.0
    assert m["exposure"] <= 1.0
    assert m["n_trades"] == len(res.trades)


if __name__ == "__main__":
    tests = [
        test_golden_cross_fires_on_exact_day,
        test_fill_happens_at_next_open_with_costs,
        test_cash_conservation_and_no_leverage,
        test_trade_pnl_reconciles_with_account,
        test_metrics_are_sane,
    ]
    for fn in tests:
        fn()
        print(f"PASS  {fn.__name__}")
    print("All tests passed.")
