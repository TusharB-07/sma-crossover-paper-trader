"""Paper-trading engine: turns signals into simulated fills and an account.

This module IS the simulated broker. It keeps the cash book, executes
orders, charges fees, and marks the account to market every day.

Frictions modelled (all configurable from the UI)
--------------------------------------------------
    brokerage      flat fee per executed order (discount-broker style, e.g. 20)
    slippage_bps   market orders cross the spread and walk the book; we pay
                   slippage_bps / 10,000 of the fill price, buying higher and
                   selling lower than the touch

Execution model (the single most important honesty rule here)
--------------------------------------------------------------
    A signal is computed on the CLOSE of day t.
    The order executes at the OPEN of day t+1 (plus slippage, plus fees).
    A backtest that fills at the same close that generated the signal uses
    information it could not have had - look-ahead bias - and will show
    returns a live account can never achieve.

Accounting rules
----------------
    * long-only, all-in / all-out, whole shares only
      buy qty = floor( (cash - brokerage) / ask ),  ask = open * (1 + slip)
      sell proceeds = qty * bid - brokerage,        bid = open * (1 - slip)
    * cash can never go negative (the floor() above guarantees it)
    * equity[t] = cash + qty * close[t]  (marked to market at every close)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from metrics import summarize
from strategy import generate_signals


@dataclass
class BacktestResult:
    """Everything the dashboard needs, in one bundle."""

    data: pd.DataFrame        # OHLCV + sma_fast / sma_slow / signal
    equity: pd.DataFrame      # daily account history (cash, qty, equity, ...)
    fills: pd.DataFrame       # every executed order (the blotter)
    trades: pd.DataFrame      # closed round trips with per-trade P&L
    metrics: dict             # summary statistics over the full period
    params: dict = field(default_factory=dict)


def run_backtest(
    df: pd.DataFrame,
    fast: int = 20,
    slow: int = 50,
    initial_cash: float = 100_000.0,
    brokerage: float = 20.0,
    slippage_bps: float = 5.0,
) -> BacktestResult:
    """Run the paper-trading simulation over df and return a BacktestResult."""
    data = generate_signals(df, fast=fast, slow=slow)
    slip = slippage_bps / 10_000.0

    cash = float(initial_cash)
    qty = 0
    avg_entry = np.nan
    entry_cost_basis = 0.0        # what the whole position cost incl. fees
    realized = 0.0                # cumulative P&L of closed trades
    pending: str | None = None    # "BUY" / "SELL" queued at close, filled next open
    pending_reason = ""
    open_trade: dict | None = None

    fills: list[dict] = []
    closed: list[dict] = []
    rows: list[dict] = []

    bh_units = initial_cash / float(data["close"].iloc[0])  # buy & hold benchmark

    for dt, bar in data.iterrows():

        # ---- 1) execute any order queued at yesterday's close, at today's open ----
        if pending == "BUY" and qty == 0:
            ask = float(bar["open"]) * (1.0 + slip)
            affordable = int((cash - brokerage) // ask)      # whole shares, cash >= 0 always
            if affordable >= 1:
                qty = affordable
                cost = qty * ask + brokerage
                cash -= cost
                avg_entry = ask
                entry_cost_basis = cost
                open_trade = {
                    "entry_date": dt,
                    "entry_price": ask,
                    "qty": qty,
                    "entry_cost": cost,
                    "reason": pending_reason,
                }
                fills.append({
                    "date": dt, "side": "BUY", "qty": qty, "price": ask,
                    "brokerage": brokerage, "cash_after": cash,
                    "reason": pending_reason,
                })
            pending, pending_reason = None, ""

        elif pending == "SELL" and qty > 0:
            bid = float(bar["open"]) * (1.0 - slip)
            proceeds = qty * bid - brokerage
            cash += proceeds
            pnl = proceeds - entry_cost_basis
            realized += pnl
            closed.append({
                "entry_date": open_trade["entry_date"],
                "exit_date": dt,
                "qty": open_trade["qty"],
                "entry_price": open_trade["entry_price"],
                "exit_price": bid,
                "pnl": pnl,
                "return_pct": pnl / entry_cost_basis,
                "bars_held": int(data.index.get_loc(dt) - data.index.get_loc(open_trade["entry_date"])),
                "reason": open_trade["reason"],
            })
            fills.append({
                "date": dt, "side": "SELL", "qty": qty, "price": bid,
                "brokerage": brokerage, "cash_after": cash,
                "reason": pending_reason,
            })
            qty, avg_entry, entry_cost_basis, open_trade = 0, np.nan, 0.0, None
            pending, pending_reason = None, ""

        else:
            pending, pending_reason = None, ""   # drop stale / invalid orders

        # ---- 2) evaluate today's CLOSE for a new signal -> queue for tomorrow ----
        sig = int(bar["signal"])
        if sig == 1 and qty == 0:
            pending = "BUY"
            pending_reason = f"golden cross ({fast}/{slow}) at {dt.date()} close"
        elif sig == -1 and qty > 0:
            pending = "SELL"
            pending_reason = f"death cross ({fast}/{slow}) at {dt.date()} close"

        # ---- 3) mark the account to market at today's close ----
        close = float(bar["close"])
        pos_val = qty * close
        unreal = (close - avg_entry) * qty if qty else np.nan
        rows.append({
            "cash": cash,
            "qty": qty,
            "position_value": pos_val,
            "avg_entry": avg_entry,
            "unrealized_pnl": unreal,
            "realized_pnl": realized,
            "equity": cash + pos_val,
            "bh_equity": bh_units * close,
            "pending": pending,          # order queued at THIS close for NEXT open
        })

    equity = pd.DataFrame(rows, index=data.index)
    equity.index.name = "date"
    equity["drawdown"] = equity["equity"] / equity["equity"].cummax() - 1.0

    fills_df = pd.DataFrame(fills)
    if not fills_df.empty:
        fills_df = fills_df.sort_values("date").reset_index(drop=True)

    trades_df = pd.DataFrame(closed)
    if not trades_df.empty:
        trades_df = trades_df.sort_values("exit_date").reset_index(drop=True)
        trades_df["win"] = trades_df["pnl"] > 0

    metrics = summarize(equity, trades_df, initial_cash)

    return BacktestResult(
        data=data,
        equity=equity,
        fills=fills_df,
        trades=trades_df,
        metrics=metrics,
        params={
            "fast": fast, "slow": slow, "initial_cash": initial_cash,
            "brokerage": brokerage, "slippage_bps": slippage_bps,
        },
    )
