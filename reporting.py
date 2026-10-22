"""Create reproducible, machine-readable and human-readable run artifacts."""

from __future__ import annotations

import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from config import BacktestConfig
from data_loader import DataFingerprint
from metrics import build_equity_curve


DISCLOSURE = (
    "This backtest is a hypothetical historical simulation and does not represent actual "
    "trading performance. Backtested results do not guarantee future results. Results depend "
    "on market-data quality and execution assumptions. This material is for research and "
    "educational purposes only and is not investment advice."
)


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def build_warnings(results: pd.DataFrame) -> list[str]:
    warnings = [
        "OHLCV bars do not reveal intrabar price order; stop-first handling is conservative.",
        "No spread, slippage, fees, market impact, or liquidity constraints are modeled.",
        "Setups are evaluated independently; overlapping trades do not reserve shared capital.",
        "No benchmark is produced because the requested outputs define a per-strategy event study.",
    ]
    if not results.empty:
        ambiguous = int(results["status"].isin(["ambiguous_breakout", "ambiguous_entry_exit"]).sum())
        end_of_data = int((results["exit_reason"] == "end_of_data").fillna(False).sum())
        if ambiguous:
            warnings.append(f"{ambiguous} setup(s) were not traded because intrabar order was unknowable.")
        if end_of_data:
            warnings.append(f"{end_of_data} trade(s) were marked to the final close at end of data.")
    return warnings


def write_artifacts(
    output: Path,
    results: pd.DataFrame,
    metrics: dict[str, Any],
    config: BacktestConfig,
    data_fingerprint: DataFingerprint,
    bars: pd.DataFrame,
) -> dict[str, str]:
    output.mkdir(parents=True, exist_ok=True)
    equity = build_equity_curve(results, config.initial_cash, bars)
    warnings = build_warnings(results)
    if config.instrument_type == "index":
        warnings.append("A cash index may not be directly tradable; reported P&L is a point-value research ledger.")
    else:
        warnings.append("Results apply only to the explicitly supplied option contract; no contract-selection or rolling rule is inferred.")
    trades = results.loc[results["status"] == "traded"].copy() if not results.empty else results.copy()

    _write_csv(output / "setups.csv", results)
    _write_csv(output / "trades.csv", trades)
    _write_csv(output / "equity.csv", equity)
    _write_csv(output / "input_bars.csv", bars)
    _write_json(output / "metrics.json", metrics)
    _write_json(output / "config.json", config.to_dict())
    _write_json(output / "data_fingerprint.json", data_fingerprint.to_dict())
    _write_json(output / "warnings.json", warnings)

    summary = {
        "strategy_name": "Three Inside Bar + Lower Volume Breakout",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": config.symbol,
        "timeframe": "5Min",
        "config": config.to_dict(),
        "metrics": metrics,
        "data_fingerprint": data_fingerprint.to_dict(),
        "warnings": warnings,
        "runtime": {"python": sys.version.split()[0], "platform": platform.platform()},
        "artifacts": {
            "setups": "setups.csv", "trades": "trades.csv", "equity": "equity.csv",
            "input_bars": "input_bars.csv", "metrics": "metrics.json", "report": "report.md",
        },
    }
    _write_json(output / "summary.json", summary)
    (output / "report.md").write_text(_render_report(summary), encoding="utf-8")
    return summary["artifacts"]


def _render_report(summary: dict[str, Any]) -> str:
    metrics = summary["metrics"]
    warnings = "\n".join(f"- {item}" for item in summary["warnings"])
    return f"""# Backtest Report

## Results

| Metric | Value |
|---|---:|
| Total setups | {metrics['total_setups']} |
| Total trades | {metrics['total_trades']} |
| Win rate | {metrics['win_rate']:.2%} |
| Average R | {metrics['average_r_achieved']:.4f} |
| Net P&L | {metrics['net_pnl']:.4f} |
| Maximum drawdown | {metrics['maximum_drawdown']:.4f} |
| Maximum drawdown % | {metrics['maximum_drawdown_pct']:.4%} |

## Reproducibility

- Symbol: {summary['symbol']}
- Instrument type: {summary['config']['instrument_type']}
- Contract multiplier: {summary['config']['contract_multiplier']}
- Timeframe: 5-minute completed candles
- Timezone: {summary['config']['timezone']}
- Data SHA-256: `{summary['data_fingerprint']['sha256']}`
- Data provider: {summary['data_fingerprint']['provider']}
- Bars: {summary['data_fingerprint']['total_bars']}
- Fill model: {summary['config']['fill_model']}
- Intrabar conflict policy: {summary['config']['intrabar_conflict_policy']}

## Warnings

{warnings}

## Important disclosure

{DISCLOSURE}
"""
