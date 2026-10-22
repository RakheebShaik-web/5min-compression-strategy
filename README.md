# Three Inside Bar + Lower Volume Breakout

A deterministic, auditable Python backtester for completed 5-minute index and individual option-contract candles. It implements only:

`mother candle -> 3 inside bars -> declining volume -> breakout -> structure stop -> 2R/3R/4R/5R`

No indicator, trend filter, time filter, regime filter, higher-timeframe confirmation, or additional price-action rule is used.

## Exact strategy

For each four-candle window, the first candle is the mother. The following three candles qualify when each high is less than or equal to the mother high, each low is greater than or equal to the mother low, and:

```text
inside_1.volume > inside_2.volume > inside_3.volume
```

The setup becomes eligible only after inside bar 3 closes. The immediately following candle must break out; otherwise it becomes a fourth inside candle and invalidates that mother setup:

- Long: high is strictly above the maximum high of the three inside bars.
- Short: low is strictly below the minimum low of the three inside bars.
- Long stop: minimum low of the three inside bars.
- Short stop: maximum high of the three inside bars.
- Targets: 2R, 3R, 4R, and 5R from the actual entry price.

The machine-readable definition is in `strategy_spec.json`.

## Index and option scope

For an index run, supply the index OHLCV file. A cash index may not be directly tradable, so the output is a point-value research ledger using the configured multiplier.

For an option run, supply candles for one specific option contract and explicitly identify its expiry, strike, call/put type, and multiplier. The strategy contains no contract-selection or rolling rule, so this project does not invent ATM, ITM, OTM, weekly-expiry, or rollover logic.

P&L is:

```text
directional price change × quantity × contract multiplier
```

## Input contract

CSV columns:

```text
datetime,open,high,low,close,volume
```

Validation rejects missing or nonnumeric values, duplicate timestamps, nonpositive prices, negative volume, invalid OHLC relationships, timestamps off five-minute boundaries, and intervals that are not whole five-minute multiples. Naive timestamps are localized to the configured IANA timezone; timezone-aware timestamps are converted to it.

## Execution policies

These policies resolve facts that 5-minute OHLCV cannot reveal and do not add signal logic:

- Every setup is evaluated independently, including overlapping setups.
- A setup expires if the immediately following candle does not break out, enforcing exactly three inside candles.
- If one candle crosses both breakout boundaries before entry, the setup is recorded as `ambiguous_breakout` and is not traded.
- If the breakout candle could have touched the structure stop before triggering entry, it is recorded as `ambiguous_entry_exit` and is not traded.
- Breakouts use stop-order bar fills. A gap through the trigger fills at the candle open.
- Protective stops fill at the stop, or at the candle open if price gaps through it.
- If stop and target are both reachable in one candle, the stop is processed first.
- Trades exit at the structure stop, 5R, or final data close. The 2R through 4R levels are milestones.
- Spread, slippage, fees, market impact, liquidity, and shared-capital reservation are not modeled because none were specified.

## Install and test

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
```

## Run an index backtest

```powershell
python main.py `
  --data path\to\NIFTY_5min.csv `
  --symbol NIFTY `
  --instrument-type index `
  --timezone Asia/Kolkata `
  --quantity 1 `
  --contract-multiplier 1 `
  --initial-cash 1000000 `
  --output results\nifty
```

## Run an option-contract backtest

```powershell
python main.py `
  --data path\to\NIFTY_2026-10-29_25000_CE_5min.csv `
  --symbol NIFTY-2026-10-29-25000-CE `
  --instrument-type option `
  --expiry 2026-10-29 `
  --strike 25000 `
  --option-type call `
  --timezone Asia/Kolkata `
  --quantity 1 `
  --contract-multiplier 75 `
  --initial-cash 1000000 `
  --output results\nifty_option
```

Use the actual exchange multiplier applicable to that contract and date. The example multiplier is illustrative, not a current contract specification.

## Audit artifacts

Each run writes:

- `setups.csv`: every detected setup, including nontraded and ambiguous setups.
- `trades.csv`: executed trades and complete mother/inside-bar context.
- `equity.csv`: bar-by-bar realized and unrealized P&L, gross exposure, equity, and drawdown.
- `metrics.json`: requested metrics plus gross profit/loss, profit factor, returns, and drawdown percentage.
- `config.json`: exact execution and instrument settings.
- `data_fingerprint.json`: SHA-256, row count, time bounds, and control totals.
- `warnings.json`: disclosed limitations and run-specific warnings.
- `summary.json`: consolidated machine-readable run manifest.
- `report.md`: human-readable report.

Writes use temporary files followed by replacement to avoid partial artifacts. GitHub Actions runs the regression suite on every push and pull request.

## Important disclosure

This backtest is a hypothetical historical simulation and does not represent actual trading performance. Backtested results do not guarantee future results. Results depend on market-data quality and execution assumptions. This material is for research and educational purposes only and is not investment advice. All investments involve risk and may lose value.
