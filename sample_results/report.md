# Backtest Report

## Results

| Metric | Value |
|---|---:|
| Total setups | 2 |
| Total trades | 2 |
| Win rate | 100.00% |
| Average R | 5.0000 |
| Net P&L | 150.0000 |
| Maximum drawdown | 0.0000 |
| Maximum drawdown % | 0.0000% |

## Reproducibility

- Symbol: TEST
- Instrument type: index
- Contract multiplier: 1.0
- Timeframe: 5-minute completed candles
- Timezone: UTC
- Data SHA-256: `4f83e04e8124cf72d6664ba75f76337233113685479716544f0f1777c90e1134`
- Data provider: csv
- Bars: 12
- Fill model: stop_order_bar_proxy
- Intrabar conflict policy: stop_first

## Warnings

- OHLCV bars do not reveal intrabar price order; stop-first handling is conservative.
- No spread, slippage, fees, market impact, or liquidity constraints are modeled.
- Setups are evaluated independently; overlapping trades do not reserve shared capital.
- No benchmark is produced because the requested outputs define a per-strategy event study.
- A cash index may not be directly tradable; reported P&L is a point-value research ledger.

## Important disclosure

This backtest is a hypothetical historical simulation and does not represent actual trading performance. Backtested results do not guarantee future results. Results depend on market-data quality and execution assumptions. This material is for research and educational purposes only and is not investment advice.
