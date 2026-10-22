"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backtest import run_backtest
from data_loader import load_ohlcv
from metrics import calculate_metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Three Inside Bar backtest")
    parser.add_argument("--data", required=True, help="Path to a 5-minute OHLCV CSV")
    parser.add_argument("--symbol", required=True, help="Symbol stored in output")
    parser.add_argument("--output", default="results", help="Output directory")
    args = parser.parse_args()

    bars = load_ohlcv(args.data)
    results = run_backtest(bars, args.symbol)
    metrics = calculate_metrics(results)

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    results.to_csv(output / "trades.csv", index=False)
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print(json.dumps(metrics, indent=2))
    print(f"Detailed setups: {output / 'trades.csv'}")


if __name__ == "__main__":
    main()
