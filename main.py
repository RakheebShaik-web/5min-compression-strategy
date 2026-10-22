"""Command-line entry point for reproducible backtest runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backtest import run_backtest
from config import BacktestConfig
from data_loader import fingerprint, load_ohlcv, validate_option_dates
from metrics import calculate_metrics
from reporting import write_artifacts
from yahoo_data import download_yahoo_5m


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Three Inside Bar backtest")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--data", help="Path to a 5-minute OHLCV CSV")
    source.add_argument("--yahoo-symbol", help="Yahoo ticker, such as ^NSEI or ^NSEBANK")
    parser.add_argument("--symbol", help="Symbol stored in output; defaults to Yahoo ticker")
    parser.add_argument("--period", help="Yahoo period, default 1mo")
    parser.add_argument("--start", help="Yahoo start date; requires --end")
    parser.add_argument("--end", help="Yahoo end date; requires --start")
    parser.add_argument("--instrument-type", choices=("index", "option"), default="index")
    parser.add_argument("--timezone", default="UTC", help="IANA timezone for naive timestamps")
    parser.add_argument("--quantity", type=float, default=1.0, help="Fixed contracts/lots per setup")
    parser.add_argument("--contract-multiplier", type=float, default=1.0, help="Currency value per price point")
    parser.add_argument("--expiry", help="Option contract expiry, such as 2026-10-29")
    parser.add_argument("--strike", type=float, help="Option strike")
    parser.add_argument("--option-type", choices=("call", "put"), help="Option contract type")
    parser.add_argument("--initial-cash", type=float, default=100000.0, help="Reference equity for return/drawdown")
    parser.add_argument("--output", default="results", help="Output directory")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    symbol = args.symbol or args.yahoo_symbol
    if not symbol:
        raise ValueError("--symbol is required when using --data")
    config = BacktestConfig(
        symbol=symbol,
        instrument_type=args.instrument_type,
        timezone=args.timezone,
        quantity=args.quantity,
        contract_multiplier=args.contract_multiplier,
        expiry=args.expiry,
        strike=args.strike,
        option_type=args.option_type,
        initial_cash=args.initial_cash,
    )
    if args.yahoo_symbol:
        bars = download_yahoo_5m(
            args.yahoo_symbol,
            config.timezone,
            period=args.period or "1mo",
            start=args.start,
            end=args.end,
        )
        provider = "yahoo_finance_via_yfinance"
        source_name = args.yahoo_symbol
        source_path = None
    else:
        bars = load_ohlcv(args.data, timezone=config.timezone)
        provider = "csv"
        source_name = str(args.data)
        source_path = args.data
    if not (bars["volume"] > 0).any():
        raise ValueError("Volume is unavailable or zero for every candle; declining-volume logic cannot run")
    if config.instrument_type == "option":
        validate_option_dates(bars, config.expiry or "")
    results = run_backtest(bars, config.symbol, config)
    metrics = calculate_metrics(results, initial_cash=config.initial_cash, bars=bars)
    data_fingerprint = fingerprint(
        source_path, bars, config.timezone, provider=provider, source=source_name
    )
    artifacts = write_artifacts(Path(args.output), results, metrics, config, data_fingerprint, bars)
    print(json.dumps(metrics, indent=2, allow_nan=False))
    print(f"Artifacts: {json.dumps(artifacts, sort_keys=True)}")


if __name__ == "__main__":
    main()
