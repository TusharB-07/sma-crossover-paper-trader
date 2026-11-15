"""SMA Crossover Paper-Trading Dashboard.

Streamlit front end for a simulated NSE brokerage account driven by a
simple moving-average (SMA) crossover strategy. The dashboard MEASURES a
strategy honestly - it never claims the strategy is profitable.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from data import fetch_history
from engine import run_backtest
from metrics import summarize

st.set_page_config(page_title="SMA Crossover Paper Trader", page_icon=":bar_chart:", layout="wide")

# TradingView-inspired palette
TEAL = "#26a69a"
RED = "#ef5350"
BLUE = "#42a5f5"
ORANGE = "#ffa726"
GRAY = "#787b86"


# --------------------------------------------------------------------------
# formatting helpers
# --------------------------------------------------------------------------
def inr(x: float, dec: int = 0) -> str:
    """Indian digit grouping: 100000 -> 1,00,000 (lakh/crore style)."""
    if pd.isna(x):
        return "-"
    neg = x < 0
    x = abs(float(x))
    s = f"{x:.{dec}f}"
    intpart, _, frac = s.partition(".")
    if len(intpart) > 3:
        head, tail = intpart[:-3], intpart[-3:]
        groups = []
        while len(head) > 2:
            groups.append(head[-2:])
            head = head[:-2]
        intpart = head + ("," + ",".join(reversed(groups)) + "," + tail if groups else "," + tail)
    return ("-" if neg else "") + "\u20b9" + intpart + ("." + frac if frac else "")


def fmt_pct(x: float, signed: bool = False, dec: int = 1) -> str:
    if pd.isna(x):
        return "-"
    if np.isinf(x):
        return "\u221e"
    s = f"{x * 100:.{dec}f}%"
    if signed and x > 0:
        s = "+" + s
    return s


def fmt_num(x: float, dec: int = 2) -> str:
    if pd.isna(x):
        return "-"
    return f"{x:,.{dec}f}"


# --------------------------------------------------------------------------
# sidebar controls
# --------------------------------------------------------------------------
with st.sidebar:
    st.title("SMA Crossover Paper Trader")
    st.caption(
        "A simulated brokerage account that trades NSE stocks on SMA "
        "crossover signals. Educational project - not investment advice."
    )
    st.divider()

    symbol = st.text_input("Ticker (NSE)", value="RELIANCE.NS").strip().upper()
    period = st.selectbox("Price history", ["6mo", "1y", "2y", "3y", "5y"], index=1)
    preset = st.radio(
        "SMA parameters",
        ["20 / 50  (classic trend pair)", "10 / 30  (faster, more trades)"],
        index=0,
    )
    fast, slow = (20, 50) if preset.startswith("20") else (10, 30)

    initial_cash = st.number_input(
        "Starting capital (\u20b9)", min_value=10_000, value=100_000, step=10_000
    )

    with st.expander("Execution costs (advanced)"):
        brokerage = st.number_input("Brokerage per order (\u20b9)", 0.0, 200.0, 20.0, 5.0)
        slippage_bps = st.number_input(
            "Slippage (basis points)", 0, 50, 5, 1,
            help="Market orders cross the spread. 5 bps = 0.05% adverse fill per order.",
        )

    view_mode = st.radio("View mode", ["Full backtest", "Replay - step through day by day"], index=0)
    replay_on = view_mode.startswith("Replay")

    st.divider()
    st.caption(
        "Price data is cached to CSV in data/ - the demo keeps working even "
        "if Yahoo Finance is down or rate-limited."
    )


# --------------------------------------------------------------------------
# data + backtest
# --------------------------------------------------------------------------
try:
    df, data_source = fetch_history(symbol, period=period)
except Exception as exc:
    st.error(f"Could not load price data for **{symbol}**: {exc}")
    st.info(
        f"Fix: with an internet connection run `python fetch_data.py {symbol}` "
        "to pre-fetch and cache the CSV, then reload."
    )
    st.stop()

result = run_backtest(
    df,
    fast=fast,
    slow=slow,
    initial_cash=float(initial_cash),
    brokerage=float(brokerage),
    slippage_bps=float(slippage_bps),
)
data, equity, fills, trades = result.data, result.equity, result.fills, result.trades
n = len(equity)

if replay_on:
    # -- pre-widget zone: mutating replay_idx here is safe (slider not yet
    #    instantiated this run). All replay state changes happen BEFORE the
    #    slider renders: button presses via on_click callbacks, auto-play here.
    if "replay_idx" not in st.session_state:
        st.session_state.replay_idx = 0
    if st.session_state.get("autoplay"):
        time.sleep(float(st.session_state.get("play_speed", 0.5)))
        if int(st.session_state.replay_idx) < n - 1:
            st.session_state.replay_idx = int(st.session_state.replay_idx) + 1
        else:
            st.session_state.autoplay = False   # end of history: stop playing
    st.session_state.replay_idx = int(min(max(st.session_state.replay_idx, 0), n - 1))
    i = st.session_state.replay_idx
    d_stop = equity.index[i]
    eq_slice = equity.iloc[: i + 1]
    data_slice = data.iloc[: i + 1]
    fills_sub = fills[fills["date"] <= d_stop] if not fills.empty else fills
    trades_sub = trades[trades["exit_date"] <= d_stop] if not trades.empty else trades
    metrics_now = summarize(eq_slice, trades_sub, float(initial_cash))
    row = equity.iloc[i]
else:
    eq_slice, data_slice, fills_sub, trades_sub = equity, data, fills, trades
    metrics_now = result.metrics
    row = equity.iloc[-1]

# --------------------------------------------------------------------------
# header + account bar
# --------------------------------------------------------------------------
st.title("SMA Crossover Paper Trader")
st.caption(
    f"**{symbol}** · daily bars · {equity.index[0].strftime('%d %b %Y')} to "
    f"{equity.index[-1].strftime('%d %b %Y')} · {n:,} sessions · SMA {fast}/{slow} · "
    f"starting capital {inr(initial_cash)} · data: {data_source}"
)

c1, c2, c3, c4 = st.columns(4)
ret_now = float(row["equity"]) / float(initial_cash) - 1.0
pnl_now = float(row["equity"]) - float(initial_cash)
c1.metric("Cash", inr(row["cash"]))
c2.metric(
    "Position value",
    inr(row["position_value"]),
    delta=(f"{int(row['qty']):,} sh @ {inr(row['avg_entry'], 2)}" if row["qty"] else "flat"),
    delta_color="off",
)
c3.metric("Account equity", inr(row["equity"]), delta=fmt_pct(ret_now, signed=True), delta_color="normal")
c4.metric(
    "P&L since start",
    ("+" if pnl_now >= 0 else "") + inr(pnl_now),
    delta=f"realized {inr(row['realized_pnl'])}",
    delta_color="off",
)

# --------------------------------------------------------------------------
# replay controls + "as of this day" narration
# --------------------------------------------------------------------------
if replay_on:
    st.slider(
        "Timeline",
        min_value=0,
        max_value=n - 1,
        key="replay_idx",
        label_visibility="collapsed",
    )

    def _jump(delta: int):
        """Build an on_click callback that moves the replay position by delta.

        on_click callbacks run at the start of the rerun, BEFORE the slider
        widget is instantiated - the only safe place to update its key.
        """
        def cb():
            cur = int(st.session_state.get("replay_idx", 0))
            st.session_state.replay_idx = int(min(max(cur + delta, 0), n - 1))
        return cb

    b_start, b_prev, b_next, b_end, b_play, b_speed = st.columns([1, 1, 1, 1, 1.2, 1.2])
    b_start.button("Start", on_click=lambda: st.session_state.update(replay_idx=0), use_container_width=True)
    b_prev.button("< Prev", on_click=_jump(-1), use_container_width=True)
    b_next.button("Next >", on_click=_jump(+1), use_container_width=True)
    b_end.button("End", on_click=lambda: st.session_state.update(replay_idx=n - 1), use_container_width=True)
    b_play.toggle("Auto-play", key="autoplay")
    if "play_speed" not in st.session_state:
        st.session_state.play_speed = 0.5
    b_speed.selectbox(
        "Speed", [0.2, 0.5, 1.0], key="play_speed",
        format_func=lambda s: f"{s}s / bar", label_visibility="collapsed",
    )

    d_i = d_stop
    st.markdown(f"#### Session {i + 1:,} of {n:,} - {d_i.strftime('%a %d %b %Y')}")

    k1, k2, k3, k4 = st.columns(4)
    close_i = float(data["close"].iloc[i])
    chg_i = close_i / float(data["close"].iloc[i - 1]) - 1.0 if i else 0.0
    sma_f = float(data["sma_fast"].iloc[i])
    sma_s = float(data["sma_slow"].iloc[i])
    k1.metric("Close", inr(close_i, 2), delta=(f"{chg_i:+.2%}" if i else None), delta_color="normal")
    k2.metric(f"SMA {fast}", inr(sma_f, 2))
    k3.metric(f"SMA {slow}", inr(sma_s, 2))
    if pd.isna(sma_f) or pd.isna(sma_s):
        regime = "SMA warming up"
    else:
        regime = "UP (fast > slow)" if sma_f > sma_s else "DOWN (fast < slow)"
    k4.metric("Trend regime", regime, delta_color="off")

    # the money moments of the demo: fills and signals
    if not fills.empty:
        todays_fill = fills[fills["date"] == d_i]
        if len(todays_fill):
            f0 = todays_fill.iloc[0]
            if f0["side"] == "BUY":
                st.success(
                    f"**ORDER FILLED at today's open:** BUY {int(f0['qty']):,} shares @ "
                    f"{inr(f0['price'], 2)} (open + slippage) + brokerage {inr(f0['brokerage'])}. "
                    f"Cash dropped to {inr(f0['cash_after'])}. Trigger: {f0['reason']}."
                )
            else:
                t_exit = trades[trades["exit_date"] == d_i]
                pnl_txt = f" Trade P&L: **{inr(float(t_exit['pnl'].iloc[0]))}** ({fmt_pct(float(t_exit['return_pct'].iloc[0]), signed=True)})." if len(t_exit) else ""
                st.success(
                    f"**ORDER FILLED at today's open:** SELL {int(f0['qty']):,} shares @ "
                    f"{inr(f0['price'], 2)} (open - slippage) - brokerage {inr(f0['brokerage'])}. "
                    f"Cash rose to {inr(f0['cash_after'])}.{pnl_txt} Trigger: {f0['reason']}."
                )
            st.caption("The order was queued at yesterday's close and filled at today's open - never at the price that generated the signal.")
    if int(data["signal"].iloc[i]) == 1:
        st.info(
            f"**GOLDEN CROSS today at close:** SMA{fast} ({inr(sma_f, 2)}) crossed above "
            f"SMA{slow} ({inr(sma_s, 2)}). A market BUY is queued for **tomorrow's open**. "
            f"Press Next to watch the fill."
        )
    elif int(data["signal"].iloc[i]) == -1:
        st.info(
            f"**DEATH CROSS today at close:** SMA{fast} ({inr(sma_f, 2)}) crossed below "
            f"SMA{slow} ({inr(sma_s, 2)}). A market SELL is queued for **tomorrow's open**. "
            f"Press Next to watch the fill."
        )

# --------------------------------------------------------------------------
# price chart with SMAs + trade markers
# --------------------------------------------------------------------------


def price_chart(d: pd.DataFrame, fills_sub: pd.DataFrame, height: int = 620) -> go.Figure:
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.8, 0.2], vertical_spacing=0.03,
    )
    fig.add_trace(go.Candlestick(
        x=d.index, open=d["open"], high=d["high"], low=d["low"], close=d["close"],
        increasing_line_color=TEAL, decreasing_line_color=RED,
        increasing_fillcolor=TEAL, decreasing_fillcolor=RED,
        name=symbol,
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=d.index, y=d["sma_fast"], name=f"SMA {fast}",
        line=dict(color=BLUE, width=1.6),
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=d.index, y=d["sma_slow"], name=f"SMA {slow}",
        line=dict(color=ORANGE, width=1.6),
    ), row=1, col=1)

    if fills_sub is not None and len(fills_sub):
        buys = fills_sub[fills_sub["side"] == "BUY"]
        sells = fills_sub[fills_sub["side"] == "SELL"]
        if len(buys):
            fig.add_trace(go.Scatter(
                x=buys["date"], y=buys["price"] * 0.97, mode="markers",
                marker=dict(symbol="triangle-up", size=14, color=TEAL,
                            line=dict(width=1.5, color="white")),
                name="BUY fill", customdata=buys["price"],
                hovertemplate="BUY %{x|%d %b %Y}<br>fill \u20b9%{customdata:.2f}<extra></extra>",
            ), row=1, col=1)
        if len(sells):
            fig.add_trace(go.Scatter(
                x=sells["date"], y=sells["price"] * 1.03, mode="markers",
                marker=dict(symbol="triangle-down", size=14, color=RED,
                            line=dict(width=1.5, color="white")),
                name="SELL fill", customdata=sells["price"],
                hovertemplate="SELL %{x|%d %b %Y}<br>fill \u20b9%{customdata:.2f}<extra></extra>",
            ), row=1, col=1)

    vol_colors = np.where(d["close"] >= d["open"], "rgba(38,166,154,0.45)", "rgba(239,83,80,0.45)")
    fig.add_trace(go.Bar(
        x=d.index, y=d["volume"], marker_color=vol_colors, name="Volume", showlegend=False,
    ), row=2, col=1)

    fig.update_layout(
        template="plotly_dark",
        height=height,
        margin=dict(l=10, r=10, t=28, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="Price (\u20b9)", row=1, col=1, gridcolor="rgba(128,136,144,0.15)")
    fig.update_yaxes(title_text="Volume", row=2, col=1, gridcolor="rgba(128,136,144,0.15)")
    fig.update_xaxes(gridcolor="rgba(128,136,144,0.15)")
    return fig


st.subheader("Price, moving averages and trade markers")
st.plotly_chart(
    price_chart(data_slice, fills_sub),
    use_container_width=True,
    config=dict(displayModeBar=False),
)
if replay_on:
    st.caption("Chart shows history up to the selected session only - like live trading, the future is hidden.")

# --------------------------------------------------------------------------
# equity curve vs buy & hold
# --------------------------------------------------------------------------


def equity_chart(eq: pd.DataFrame, fills_sub: pd.DataFrame, initial_cash: float, height: int = 480) -> go.Figure:
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.75, 0.25], vertical_spacing=0.03,
    )
    fig.add_trace(go.Scatter(
        x=eq.index, y=eq["bh_equity"], name="Buy & hold (all-in on day 1, no costs)",
        line=dict(color=GRAY, width=1.5, dash="dash"),
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=eq.index, y=eq["equity"], name="Strategy account equity",
        line=dict(color=TEAL, width=2.2),
    ), row=1, col=1)
    if fills_sub is not None and len(fills_sub):
        m = fills_sub.copy()
        m["equity_at_fill"] = eq.loc[m["date"], "equity"].values
        buys = m[m["side"] == "BUY"]
        sells = m[m["side"] == "SELL"]
        if len(buys):
            fig.add_trace(go.Scatter(
                x=buys["date"], y=buys["equity_at_fill"], mode="markers",
                marker=dict(symbol="triangle-up", size=12, color=TEAL,
                            line=dict(width=1.2, color="white")),
                name="BUY fill", showlegend=False,
            ), row=1, col=1)
        if len(sells):
            fig.add_trace(go.Scatter(
                x=sells["date"], y=sells["equity_at_fill"], mode="markers",
                marker=dict(symbol="triangle-down", size=12, color=RED,
                            line=dict(width=1.2, color="white")),
                name="SELL fill", showlegend=False,
            ), row=1, col=1)
    fig.add_hline(
        y=initial_cash, line_dash="dot", line_color=GRAY, opacity=0.6,
        annotation_text=f"Starting capital {inr(initial_cash)}",
        annotation_position="bottom left",
    )
    fig.add_trace(go.Scatter(
        x=eq.index, y=eq["drawdown"] * 100, name="Drawdown (%)",
        fill="tozeroy", line=dict(color=RED, width=1),
        fillcolor="rgba(239,83,80,0.25)", showlegend=False,
    ), row=2, col=1)

    fig.update_layout(
        template="plotly_dark",
        height=height,
        margin=dict(l=10, r=10, t=28, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="Account value (\u20b9)", row=1, col=1, gridcolor="rgba(128,136,144,0.15)")
    fig.update_yaxes(title_text="Drawdown (%)", row=2, col=1, gridcolor="rgba(128,136,144,0.15)")
    fig.update_xaxes(gridcolor="rgba(128,136,144,0.15)")
    return fig


st.subheader("Equity curve vs buy & hold")
st.plotly_chart(
    equity_chart(eq_slice, fills_sub, float(initial_cash)),
    use_container_width=True,
    config=dict(displayModeBar=False),
)

# --------------------------------------------------------------------------
# summary metrics
# --------------------------------------------------------------------------
m = metrics_now

st.subheader("Summary statistics")
r1c1, r1c2, r1c3, r1c4 = st.columns(4)
r2c1, r2c2, r2c3, r2c4 = st.columns(4)
r1c1.metric(
    "Total return", fmt_pct(m["total_return"], signed=True),
    delta=f"alpha {fmt_pct(m['alpha'], signed=True)} vs B&H",
    delta_color="normal",
)
r1c2.metric("Buy & hold return", fmt_pct(m["bh_return"], signed=True))
r1c3.metric(
    "Closed trades", f"{m['n_trades']:,}",
    delta=(f"{fmt_num(m['avg_hold_bars'], 0)} sessions avg hold" if m["n_trades"] else "no crossovers fired"),
    delta_color="off",
)
r1c4.metric(
    "Win rate", fmt_pct(m["win_rate"]) if m["n_trades"] else "-",
    delta=(f"{m['wins']}W / {m['losses']}L" if m["n_trades"] else None),
    delta_color="off",
)
r2c1.metric("Max drawdown", fmt_pct(m["max_drawdown"]))
r2c2.metric("Sharpe (daily, rf = 0)", fmt_num(m["sharpe"]))
r2c3.metric("Profit factor", fmt_num(m["profit_factor"]))
r2c4.metric("Time in market", fmt_pct(m["exposure"]) if not pd.isna(m["exposure"]) else "-")

with st.expander("Full statistics table"):
    st.table(pd.DataFrame(
        [
            ("Final equity", inr(m["final_equity"])),
            ("Total return", fmt_pct(m["total_return"], signed=True)),
            ("Buy & hold return (gross of costs)", fmt_pct(m["bh_return"], signed=True)),
            ("Alpha vs buy & hold", fmt_pct(m["alpha"], signed=True)),
            ("CAGR (annualised)", fmt_pct(m["cagr"], signed=True)),
            ("Closed trades", f"{m['n_trades']:,}"),
            ("Win rate", fmt_pct(m["win_rate"]) if m["n_trades"] else "-"),
            ("Profit factor (gross wins / gross losses)", fmt_num(m["profit_factor"])),
            ("Average trade P&L", inr(m["avg_pnl"]) if m["n_trades"] else "-"),
            ("Best trade", inr(m["best_trade"]) if m["n_trades"] else "-"),
            ("Worst trade", inr(m["worst_trade"]) if m["n_trades"] else "-"),
            ("Gross profit", inr(m["gross_profit"])),
            ("Gross loss", inr(m["gross_loss"])),
            ("Max drawdown", fmt_pct(m["max_drawdown"])),
            ("Sharpe (daily returns, rf = 0)", fmt_num(m["sharpe"])),
            ("Time in market", fmt_pct(m["exposure"]) if not pd.isna(m["exposure"]) else "-"),
            ("Average holding period", f"{fmt_num(m['avg_hold_bars'], 0)} sessions" if m["n_trades"] else "-"),
            ("Brokerage paid", inr(2 * m["n_trades"] * result.params["brokerage"]) if m["n_trades"] else inr(0)),
            ("Costs per order", f"{inr(result.params['brokerage'])} + {result.params['slippage_bps']:.0f} bps slippage"),
        ],
        columns=["Statistic", "Value"],
    ).set_index("Statistic"))

# --------------------------------------------------------------------------
# trade blotter
# --------------------------------------------------------------------------
st.subheader("Trade blotter")
col_fills, col_trades = st.columns(2)

with col_fills:
    st.markdown("**Fills - every simulated order execution**")
    if fills_sub.empty:
        st.caption("No fills yet - no crossover has fired in this window (or orders are queued for the next open).")
    else:
        show = fills_sub.copy()
        show["date"] = pd.to_datetime(show["date"])
        st.dataframe(
            show[["date", "side", "qty", "price", "brokerage", "cash_after", "reason"]],
            hide_index=True,
            column_config={
                "date": st.column_config.DateColumn("Date", format="DD MMM YYYY"),
                "side": st.column_config.TextColumn("Side"),
                "qty": st.column_config.NumberColumn("Qty", format="%d"),
                "price": st.column_config.NumberColumn("Fill price", format="\u20b9 %.2f"),
                "brokerage": st.column_config.NumberColumn("Fees", format="\u20b9 %.0f"),
                "cash_after": st.column_config.NumberColumn("Cash after", format="\u20b9 %.0f"),
                "reason": st.column_config.TextColumn("Triggered by", width="large"),
            },
            use_container_width=True,
        )
        st.download_button(
            "Export fills as CSV",
            data=fills_sub.to_csv(index=False).encode("utf-8"),
            file_name=f"{symbol}_fills.csv",
            mime="text/csv",
        )

with col_trades:
    st.markdown("**Closed round trips - entry to exit, per-trade P&L**")
    if trades_sub.empty:
        st.caption("No closed trades yet. A round trip appears only after a SELL fills.")
    else:
        show = trades_sub.copy()
        for c in ["entry_date", "exit_date"]:
            show[c] = pd.to_datetime(show[c])
        show["return_pct"] = show["return_pct"] * 100.0   # fraction -> % for display
        st.dataframe(
            show[["entry_date", "exit_date", "qty", "entry_price", "exit_price", "pnl", "return_pct", "bars_held"]],
            hide_index=True,
            column_config={
                "entry_date": st.column_config.DateColumn("Entry", format="DD MMM YYYY"),
                "exit_date": st.column_config.DateColumn("Exit", format="DD MMM YYYY"),
                "qty": st.column_config.NumberColumn("Qty", format="%d"),
                "entry_price": st.column_config.NumberColumn("Entry px", format="\u20b9 %.2f"),
                "exit_price": st.column_config.NumberColumn("Exit px", format="\u20b9 %.2f"),
                "pnl": st.column_config.NumberColumn("P&L", format="\u20b9 %.0f"),
                "return_pct": st.column_config.NumberColumn("Return", format="%+.1f%%"),
                "bars_held": st.column_config.NumberColumn("Held", format="%d"),
            },
            use_container_width=True,
        )
        st.download_button(
            "Export trades as CSV",
            data=trades_sub.to_csv(index=False).encode("utf-8"),
            file_name=f"{symbol}_trades.csv",
            mime="text/csv",
        )

# --------------------------------------------------------------------------
# honesty notes
# --------------------------------------------------------------------------
st.subheader("How this simulation stays honest")
with st.expander("Assumptions and execution model - read before trusting any number"):
    st.markdown(
        f"""
        - **No look-ahead bias.** Signals are computed on the close of day *t* and filled at the
          open of day *t+1*. No trade ever uses a price that did not exist yet.
        - **Costs are charged on every fill.** Brokerage {inr(result.params['brokerage'])} per order plus
          {result.params['slippage_bps']:.0f} bps slippage (buying at open + slippage, selling at open - slippage).
          With ~{inr(initial_cash)} capital these are small but real drag.
        - **Whole shares only, all-in / all-out.** Buy size = floor((cash - fees) / ask). Cash can never go negative.
        - **Long-only.** Golden cross opens a position (if flat), death cross closes it. A golden cross while
          already long does nothing; a death cross while flat does nothing.
        - **Marked to market daily.** equity(t) = cash + qty x close(t). Drawdown is measured on this curve.
        - **Buy & hold benchmark** puts the same starting capital into the stock on day 1 and holds it,
          *gross of costs* - a deliberately tough comparison for the strategy.
        - **Sharpe** uses daily equity returns annualised by sqrt(252) with risk-free rate = 0.
        - **Open position at the end** (if any) is included in equity but not in closed-trade statistics.
        """
    )
with st.expander("When does an SMA crossover lose money? (the questions a trader will ask)"):
    st.markdown(
        """
        - **Sideways, choppy markets.** Each small swing triggers a cross, the position enters late
          and exits late - "whipsaw" losses from repeated small drawdowns plus fees. Trend-following
          tools pay for their profits during ranges.
        - **Late by design.** A crossover confirms a trend only *after* part of the move has happened,
          and the exit waits for the opposite cross - it gives back open profits before selling.
        - **Parameter sensitivity.** 20/50 vs 10/30 changes trade count and behaviour a lot. Without
          walk-forward validation, any chosen pair risks being over-fitted to one history.
        - **No risk management here.** No stop-loss, no position sizing rules, no volatility filter,
          single stock, no diversification. Real desks size positions by risk, not "all-in".
        - **Data caveats.** Yahoo Finance daily bars can differ from exchange records; corporate
          actions are handled by yfinance auto-adjust. Costs here ignore STT, stamp duty, GST and
          exchange charges that a real Indian delivery account pays.
        """
    )
st.caption(
    "This dashboard measures a strategy against its benchmark with realistic frictions. "
    "It is an educational tool, not a claim of profitability and not investment advice."
)

# Auto-play heartbeat: when playing, restart the script from the top. The
# actual bar advance happens in the pre-widget zone at the start of the run,
# before the timeline slider is instantiated.
if replay_on and st.session_state.get("autoplay"):
    st.rerun()

