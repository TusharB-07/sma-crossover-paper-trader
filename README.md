# SMA Crossover Paper Trader

A **paper-trading dashboard** for a classic SMA (20/50) crossover strategy on
NSE stocks, built with Streamlit, yfinance, pandas and Plotly.

It simulates a brokerage account starting with ₹1,00,000, trades the
crossover signals with realistic frictions (next-open fills, slippage,
brokerage), and reports every metric a trader would ask for — side by side
with a buy & hold benchmark.

> **This dashboard measures a strategy honestly. It does not claim the
> strategy is profitable.** Trend-following crossovers lose money in sideways
> markets, and this project is built to *show* that, not hide it.

---

## Features

| Feature | What it does |
| --- | --- |
| Price chart | NSE candles with SMA 20 / SMA 50 overlay, volume panel, BUY/SELL markers at every fill |
| Paper account | ₹1,00,000 starting cash, whole-share sizing, cash / position / equity updated every session |
| Trade blotter | Every simulated fill (price, fees, cash after) + every closed round trip with per-trade P&L |
| Equity curve | Strategy account value vs buy & hold, with drawdown panel |
| Summary stats | Total return, buy & hold return, alpha, trades, win rate, profit factor, max drawdown, Sharpe, exposure |
| Replay mode | Step through history day by day (or auto-play) — watch signals fire, orders fill and the account change, bar by bar |
| Parameter switch | One click: 20/50 classic pair vs 10/30 fast pair — the whole simulation re-runs |
| Offline-safe data | Prices cached to CSV; the demo works even when Yahoo Finance is down or rate-limited |

## Quick start (Mac)

```bash
git clone https://github.com/TusharB-07/sma-crossover-paper-trader.git
cd sma-crossover-paper-trader

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

streamlit run app.py
```

The browser opens at `http://localhost:8501`. Default view: RELIANCE.NS,
1 year of daily bars, SMA 20/50.

## Offline / demo mode

A CSV cache lives in `data/` so the app never *needs* the network. Refresh or
extend it any time:

```bash
python fetch_data.py                    # RELIANCE.NS, 2 years
python fetch_data.py TCS.NS INFY.NS     # more tickers
python fetch_data.py --refresh RELIANCE.NS
```

The caption at the top of the dashboard always states the data source:
`yfinance (fresh download)` or `local cache (age N day(s))` — you always know
what you are looking at.

## Run the tests

```bash
python test_engine.py
```

Five deterministic tests on synthetic price series where the crossover dates
are known in advance: golden-cross day detection, next-open fill timing,
fee-aware share sizing, cash conservation (no leverage), and P&L
reconciliation between the trade list and the account.

## How the simulation works

```
yfinance / CSV cache          strategy.py             engine.py                app.py
-------------------          -------------           ----------               ------
daily OHLCV bars   ------>   SMA 20, SMA 50   --->   simulated broker  --->   Streamlit UI
(parsed, cached)             golden / death cross    next-open fills, fees,   charts, blotter,
                             on close of day t       slippage, cash book,     replay, metrics
                                                     mark-to-market equity
```

**Execution model (no look-ahead bias).** A signal is computed on the *close*
of day *t* and filled at the *open* of day *t+1*. A backtest that fills at the
same close that generated the signal uses information it could not have had —
the most common way backtests lie. This project does not do that, and the
replay mode makes the queue-then-fill sequence visible.

**Frictions on every fill.**
- brokerage: flat ₹20 per order (discount-broker style, configurable)
- slippage: 5 bps per fill (buy at open + 0.05%, sell at open − 0.05%, configurable)

**Accounting.** Long-only, all-in / all-out, whole shares:
`buy qty = floor((cash − fees) / ask)`, cash can never go negative,
`equity(t) = cash + qty × close(t)`, drawdown measured on that equity curve.

**Benchmark.** Buy & hold puts the same ₹1,00,000 into the stock on day 1 and
holds it, gross of costs — a deliberately tough comparison.

## Metrics glossary

| Metric | Meaning |
| --- | --- |
| Total return | final equity / starting cash − 1 |
| Buy & hold return | what the same capital would have done in the stock, untouched |
| Alpha | strategy return − buy & hold return |
| Win rate | winning round trips / closed round trips |
| Profit factor | gross wins / gross losses (> 1 means wins outweigh losses) |
| Max drawdown | deepest peak-to-trough fall of the equity curve |
| Sharpe | annualised mean/std of daily equity returns, risk-free = 0 |
| Time in market | fraction of sessions actually holding a position |
| Exposure cost | the strategy sits in cash much of the time — that is why it can lag a bull market |

## Experiments to try (5-minute demo script)

1. **Replay.** Switch to *Replay — step through day by day*. Advance bar by
   bar; when a golden cross fires, the UI says a BUY is queued for
   *tomorrow's open*. Press Next: the fill banner shows the price, fees, and
   the cash drop; the trade blotter grows a row.
2. **The exit.** Keep stepping to the death cross. The SELL fill shows the
   closed trade's P&L; the equity curve updates; realized P&L ticks up or down.
3. **The verdict.** Read the summary stats out loud: total return, buy & hold
   return, win rate, max drawdown, Sharpe. Say what they mean — do not
   editorialise.
4. **The sweep.** Switch SMA parameters to 10/30. More signals, more trades,
   more fee drag, different drawdown. Compare alpha. This is parameter
   sensitivity, seen live.
5. **The honesty section.** Open *When does an SMA crossover lose money?* —
   whipsaws, late exits, no stop-loss, single stock. Knowing a strategy's
   failure mode is the actual skill.

## Known limitations (on purpose, and stated)

- Single stock, long-only, all-in / all-out — real desks size positions by risk.
- No stop-loss, no volatility filter, no walk-forward validation of the 20/50
  parameters.
- Costs ignore STT, stamp duty, GST and exchange charges of a real Indian
  delivery account.
- Yahoo Finance daily bars may differ slightly from exchange records; corporate
  actions are handled by `auto_adjust=True`.
- An SMA crossover is a *teaching* strategy: simple enough to audit line by
  line, not a claim of edge.

## Project structure

```
sma-crossover-paper-trader/
├── app.py            # Streamlit dashboard (charts, replay, blotter, metrics)
├── strategy.py       # SMA calculation + golden/death cross detection
├── engine.py         # paper-trading engine: fills, fees, cash book, equity
├── metrics.py        # summary statistics from the account history
├── data.py           # yfinance download + CSV cache (offline fallback)
├── fetch_data.py     # CLI to pre-fetch/refresh the CSV cache
├── test_engine.py    # deterministic unit tests (python test_engine.py)
├── requirements.txt
├── data/
│   └── RELIANCE.NS.csv   # cached daily bars for the offline demo
└── .streamlit/config.toml
```

## Disclaimer

Educational project. Nothing here is investment advice or a claim of
profitability. Past performance of any rule on any chart says almost nothing
about the future.

## License

MIT — see [LICENSE](LICENSE).
