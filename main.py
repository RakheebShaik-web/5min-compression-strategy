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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Three Inside Bar backtest")
    parser.add_argument("--data", required=True, help="Path to a 5-minute OHLCV CSV")
    parser.add_argument("--symbol", required=True, help="Symbol stored in output")
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
    config = BacktestConfig(
        symbol=args.symbol,
        instrument_type=args.instrument_type,
        timezone=args.timezone,
        quantity=args.quantity,
        contract_multiplier=args.contract_multiplier,
        expiry=args.expiry,
        strike=args.strike,
        option_type=args.option_type,
        initial_cash=args.initial_cash,
    )
    bars = load_ohlcv(args.data, timezone=config.timezone)
    if config.instrument_type == "option":
        validate_option_dates(bars, config.expiry or "")
    results = run_backtest(bars, config.symbol, config)
    metrics = calculate_metrics(results, initial_cash=config.initial_cash, bars=bars)
    data_fingerprint = fingerprint(args.data, bars, config.timezone)
    artifacts = write_artifacts(Path(args.output), results, metrics, config, data_fingerprint, bars)
    print(json.dumps(metrics, indent=2, allow_nan=False))
    print(f"Artifacts: {json.dumps(artifacts, sort_keys=True)}")


if __name__ == "__main__":
    main()
