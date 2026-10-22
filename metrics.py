"""Aggregate the requested setup and trade statistics."""

from __future__ import annotations

from typing import Any

import pandas as pd


def calculate_metrics(results: pd.DataFrame) -> dict[str, Any]:
    if results.empty:
        return _empty_metrics()

    trades = results.loc[results["status"] == "traded"].copy()
    if trades.empty:
        metrics = _empty_metrics()
        metrics["total_setups"] = int(len(results))
        return metrics

    equity = trades["pnl"].cumsum()
    drawdown = equity.cummax().clip(lower=0) - equity
    wins = int((trades["pnl"] > 0).sum())
    losses = int((trades["pnl"] < 0).sum())
    total = len(trades)
    return {
        "total_setups": int(len(results)),
        "total_trades": int(total),
        "long_trades": int((trades["breakout_direction"] == "long").sum()),
        "short_trades": int((trades["breakout_direction"] == "short").sum()),
        "winning_trades": wins,
        "losing_trades": losses,
        "win_rate": wins / total,
        **{
            f"target_1_{multiple}_hit_rate": float(
                (trades["maximum_target_reached"] >= multiple).mean()
            )
            for multiple in (2, 3, 4, 5)
        },
        "average_r_achieved": float(trades["r_multiple_achieved"].mean()),
        "net_pnl": float(trades["pnl"].sum()),
        "maximum_drawdown": float(drawdown.max()),
    }


def _empty_metrics() -> dict[str, Any]:
    return {
        "total_setups": 0,
        "total_trades": 0,
        "long_trades": 0,
        "short_trades": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "win_rate": 0.0,
        "target_1_2_hit_rate": 0.0,
        "target_1_3_hit_rate": 0.0,
        "target_1_4_hit_rate": 0.0,
        "target_1_5_hit_rate": 0.0,
        "average_r_achieved": 0.0,
        "net_pnl": 0.0,
        "maximum_drawdown": 0.0,
    }
