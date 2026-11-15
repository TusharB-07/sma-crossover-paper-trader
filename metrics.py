"""Performance statistics computed from the engine's account history.

Every number a full-time trader would ask for, computed from the equity
curve and the closed-trade list - nothing is hard-coded or assumed:

    total_return     final equity / starting cash - 1
    bh_return        buy & hold benchmark over the same window (gross of costs)
    alpha            strategy return - buy & hold return
    n_trades / wins / losses / win_rate
    profit_factor    gross wins / gross losses (>1 means wins outweigh losses)
    max_drawdown     deepest peak-to-trough fall of the equity curve
    sharpe           annualised mean/std of daily equity returns, rf = 0
    cagr             compound annual growth rate (annualised total return)
    exposure         fraction of sessions with money in the market
    avg/best/worst trade, average holding period
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def summarize(
    equity: pd.DataFrame,
    trades: pd.DataFrame,
    initial_cash: float,
    periods_per_year: int = 252,
) -> dict:
    """Return a flat dict of summary statistics.

    Works on any slice of the account history, which is what makes the
    replay mode able to show "metrics so far" while stepping through time.
    """
    eq_final = float(equity["equity"].iloc[-1])
    total_return = eq_final / initial_cash - 1.0
    bh_return = float(equity["bh_equity"].iloc[-1]) / initial_cash - 1.0

    n_trades = 0 if trades is None else int(len(trades))
    wins = losses = 0
    win_rate = np.nan
    gross_win = gross_loss = 0.0
    if n_trades:
        wins = int((trades["pnl"] > 0).sum())
        losses = n_trades - wins
        win_rate = wins / n_trades
        gross_win = float(trades.loc[trades["pnl"] > 0, "pnl"].sum())
        gross_loss = float(-trades.loc[trades["pnl"] < 0, "pnl"].sum())

    profit_factor = np.nan
    if gross_loss > 0:
        profit_factor = gross_win / gross_loss
    elif gross_win > 0:
        profit_factor = float("inf")

    max_dd = float(equity["drawdown"].min()) if len(equity) else np.nan

    rets = equity["equity"].pct_change().dropna()
    sharpe = np.nan
    if len(rets) > 1 and float(rets.std()) > 0:
        sharpe = float(rets.mean() / rets.std() * np.sqrt(periods_per_year))

    years = len(equity) / periods_per_year
    cagr = np.nan
    if years > 0 and eq_final > 0:
        cagr = (eq_final / initial_cash) ** (1.0 / years) - 1.0

    exposure = float((equity["qty"] > 0).mean()) if len(equity) else np.nan

    return {
        "final_equity": eq_final,
        "total_return": total_return,
        "bh_return": bh_return,
        "alpha": total_return - bh_return,
        "n_trades": n_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "cagr": cagr,
        "exposure": exposure,
        "avg_hold_bars": float(trades["bars_held"].mean()) if n_trades else np.nan,
        "avg_pnl": float(trades["pnl"].mean()) if n_trades else np.nan,
        "best_trade": float(trades["pnl"].max()) if n_trades else np.nan,
        "worst_trade": float(trades["pnl"].min()) if n_trades else np.nan,
        "gross_profit": gross_win,
        "gross_loss": gross_loss,
    }
