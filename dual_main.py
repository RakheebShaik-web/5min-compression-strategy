"""CLI for signal-instrument patterns executed through mapped option contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from data_loader import load_ohlcv
from dual_backtest import OptionExecutionLeg, run_signal_to_options_backtest


def _leg(args: argparse.Namespace, prefix: str) -> OptionExecutionLeg:
    return OptionExecutionLeg(
        symbol=getattr(args, f"{prefix}_symbol"),
        expiry=getattr(args, f"{prefix}_expiry"),
        strike=getattr(args, f"{prefix}_strike"),
        option_type=getattr(args, f"{prefix}_type"),
        position_side=getattr(args, f"{prefix}_side"),
        quantity=getattr(args, f"{prefix}_quantity"),
        contract_multiplier=getattr(args, f"{prefix}_multiplier"),
        tick_size=getattr(args, f"{prefix}_tick_size"),
        friction_bps=getattr(args, f"{prefix}_friction_bps"),
        fee_per_contract_per_side=getattr(args, f"{prefix}_fee_per_side"),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Futures/index signal executed with mapped options")
    parser.add_argument("--signal-data", required=True)
    parser.add_argument("--signal-symbol", required=True)
    parser.add_argument("--long-option-data", required=True)
    parser.add_argument("--short-option-data", required=True)
    parser.add_argument("--timezone", default="Asia/Kolkata")
    parser.add_argument("--output", default="results/dual")
    for prefix, option_type in (("long", "call"), ("short", "put")):
        parser.add_argument(f"--{prefix}-symbol", required=True)
        parser.add_argument(f"--{prefix}-expiry", required=True)
        parser.add_argument(f"--{prefix}-strike", type=float, required=True)
        parser.add_argument(f"--{prefix}-type", choices=("call", "put"), default=option_type)
        parser.add_argument(f"--{prefix}-side", choices=("long", "short"), required=True)
        parser.add_argument(f"--{prefix}-quantity", type=int, required=True)
        parser.add_argument(f"--{prefix}-multiplier", type=float, required=True)
        parser.add_argument(f"--{prefix}-tick-size", type=float, required=True)
        parser.add_argument(f"--{prefix}-friction-bps", type=float, default=0.0)
        parser.add_argument(f"--{prefix}-fee-per-side", type=float, default=0.0)
    return parser


def _metrics(results: pd.DataFrame) -> dict[str, float | int]:
    trades = results.loc[(results["status"] == "traded") & results["option_pnl"].notna()].copy()
    if trades.empty:
        return {"total_setups": len(results), "total_trades": 0, "win_rate": 0.0, "net_pnl": 0.0, "maximum_drawdown": 0.0}
    trades = trades.sort_values("option_exit_datetime", kind="stable")
    equity = pd.concat([pd.Series([0.0]), trades["option_pnl"].cumsum()], ignore_index=True)
    drawdown = equity.cummax() - equity
    wins = int((trades["option_pnl"] > 0).sum())
    return {
        "total_setups": len(results), "total_trades": len(trades),
        "win_rate": wins / len(trades), "net_pnl": float(trades["option_pnl"].sum()),
        "maximum_drawdown": float(drawdown.max()),
    }


def main() -> None:
    args = build_parser().parse_args()
    signal = load_ohlcv(args.signal_data, args.timezone)
    long_option = load_ohlcv(args.long_option_data, args.timezone)
    short_option = load_ohlcv(args.short_option_data, args.timezone)
    long_leg = _leg(args, "long")
    short_leg = _leg(args, "short")
    results = run_signal_to_options_backtest(signal, args.signal_symbol, long_option, short_option, long_leg, short_leg)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    results.to_csv(output / "dual_trades.csv", index=False)
    manifest = {
        "mode": "signal_to_option", "signal_symbol": args.signal_symbol,
        "fill_policy": "next available option 5-minute open after signal entry/exit bar",
        "long_leg": long_leg.to_dict(), "short_leg": short_leg.to_dict(),
        "metrics": _metrics(results),
    }
    (output / "dual_summary.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest["metrics"], indent=2))


if __name__ == "__main__":
    main()
