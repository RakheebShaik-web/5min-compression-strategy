# Three Inside Bar + Lower Volume Breakout Backtest

This project implements only the requested 5-minute strategy:

`mother candle -> 3 inside bars -> declining volume -> breakout -> structure stop -> 2R/3R/4R/5R targets`

## Input

Provide a CSV with these columns:

```text
datetime,open,high,low,close,volume
```

Timestamps must be chronological and aligned to 5-minute boundaries. Gaps such as overnight and market-closure gaps are allowed when they are whole multiples of five minutes.

## Exact rules

For each four-candle window, candle 1 is the mother. Candles 2, 3, and 4 qualify when each high is less than or equal to the mother high, each low is greater than or equal to the mother low, and their volumes satisfy `inside_1 > inside_2 > inside_3`. Equality at the mother boundary is treated as inside.

The setup becomes eligible only after inside bar 3 has closed. Starting with the next candle, the first high strictly above the maximum high of the three inside bars creates a long entry at that consolidation high. The first low strictly below the minimum low creates a short entry at that consolidation low. A touch without crossing is not a breakout.

Long stop: minimum low of the three inside bars. Short stop: maximum high of the three inside bars. Risk is the absolute distance from entry to stop. Targets are entry plus `2R`, `3R`, `4R`, and `5R` for longs, and entry minus those distances for shorts.

## Explicit simulation policies

The prompt does not define intrabar price order, trade expiry, position size, fees, or the final exit. The engine therefore uses auditable policies without adding signal filters:

- Every detected setup is evaluated independently; overlapping setups are retained.
- A setup remains eligible through the end of the supplied data.
- If one candle crosses both breakout boundaries before direction is known, it is recorded as `ambiguous_breakout` and is not traded because OHLCV cannot reveal which boundary broke first.
- Entry fills at the crossed consolidation boundary, with no fees or slippage.
- A trade remains open until its structure stop, its 5R target, or the end of the data. The 2R through 4R levels are milestones used for hit rates.
- If a candle touches both the stop and a target, the stop is processed first because OHLCV cannot reveal intrabar order.
- P&L is per unit. No capital or position sizing rule is introduced.
- End-of-data trades exit at the final close.
- `maximum_drawdown` is the largest peak-to-trough decline in cumulative per-unit trade P&L, ordered by detected setup.
- Zero-risk structures are recorded but not traded.

## Run

```powershell
python -m pip install -r requirements.txt
python main.py --data path\to\bars.csv --symbol SYMBOL --output results
```

Outputs:

- `results/trades.csv`: every setup and all requested candle/trade fields
- `results/metrics.json`: requested aggregate statistics

## Files

- `strategy.py`: pattern, stop, and target logic
- `data_loader.py`: CSV loading and 5-minute validation
- `backtest.py`: post-pattern breakout and trade simulation
- `metrics.py`: aggregate metrics
- `main.py`: command-line interface

## Important disclosure

This backtest is a hypothetical historical simulation and does not represent actual trading performance. Backtested results do not guarantee future results. Results depend on market-data quality, data feed selection, corporate-action handling, fees, slippage, liquidity, taxes, execution assumptions, and implementation details. This material is for research and educational purposes only and is not investment advice, a recommendation, an offer, or a solicitation to buy or sell securities, options, cryptocurrencies, or any other financial product. All investments involve risk and may lose value. Review Alpaca's disclosures at https://alpaca.markets/disclosures.
