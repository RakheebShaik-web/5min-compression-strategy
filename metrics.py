"""Aggregate deterministic trade and equity statistics."""

from __future__ import annotations

from typing import Any

import pandas as pd


def calculate_metrics(
    results: pd.DataFrame,
    initial_cash: float = 100_000.0,
    bars: pd.DataFrame | None = None,
) -> dict[str, Any]:
    trades = results.loc[results["status"] == "traded"].copy() if not results.empty else pd.DataFrame()
    if trades.empty:
        metrics = _empty_metrics(initial_cash)
        metrics["total_setups"] = int(len(results))
        return metrics
    trades = trades.sort_values(["exit_datetime", "setup_id"], kind="stable")
    equity_curve = build_equity_curve(trades, initial_cash, bars)
    wins = int((trades["pnl"] > 0).sum())
    losses = int((trades["pnl"] < 0).sum())
    gross_profit = float(trades.loc[trades["pnl"] > 0, "pnl"].sum())
    gross_loss = abs(float(trades.loc[trades["pnl"] < 0, "pnl"].sum()))
    profit_factor = gross_profit / gross_loss if gross_loss else None
    total = len(trades)
    net_pnl = float(trades["pnl"].sum())
    return {
        "total_setups": int(len(results)), "total_trades": int(total),
        "long_trades": int((trades["breakout_direction"] == "long").sum()),
        "short_trades": int((trades["breakout_direction"] == "short").sum()),
        "winning_trades": wins, "losing_trades": losses,
        "breakeven_trades": int((trades["pnl"] == 0).sum()), "win_rate": wins / total,
        **{f"target_1_{m}_hit_rate": float((trades["maximum_target_reached"] >= m).mean()) for m in (2, 3, 4, 5)},
        "average_r_achieved": float(trades["r_multiple_achieved"].mean()),
        "median_r_achieved": float(trades["r_multiple_achieved"].median()),
        "gross_profit": gross_profit, "gross_loss": gross_loss, "profit_factor": profit_factor,
        "net_pnl": net_pnl, "initial_cash": initial_cash,
        "final_equity": initial_cash + net_pnl, "total_return": net_pnl / initial_cash,
        "maximum_drawdown": float(equity_curve["drawdown"].max()),
        "maximum_drawdown_pct": abs(float(equity_curve["drawdown_pct"].min())),
    }


def build_equity_curve(
    results: pd.DataFrame,
    initial_cash: float,
    bars: pd.DataFrame | None = None,
) -> pd.DataFrame:
    columns = [
        "datetime", "realized_pnl", "unrealized_pnl", "gross_exposure",
        "equity", "drawdown", "drawdown_pct",
    ]
    trades = results.loc[results["status"] == "traded"].copy() if not results.empty else pd.DataFrame()
    if trades.empty:
        return pd.DataFrame(columns=columns)
    if bars is None:
        curve = trades.groupby("exit_datetime", as_index=False, sort=True)["pnl"].sum().rename(columns={"exit_datetime": "datetime", "pnl": "realized_pnl"})
        curve["realized_pnl"] = curve["realized_pnl"].cumsum()
        curve["unrealized_pnl"] = 0.0
        curve["gross_exposure"] = 0.0
    else:
        rows: list[dict[str, float | pd.Timestamp]] = []
        for _, bar in bars.iterrows():
            timestamp = bar["datetime"]
            closed = trades.loc[trades["exit_datetime"] <= timestamp]
            opened = trades.loc[
                (trades["breakout_datetime"] <= timestamp)
                & (trades["exit_datetime"] > timestamp)
            ]
            realized = float(closed["pnl"].sum())
            unrealized = 0.0
            exposure = 0.0
            for _, trade in opened.iterrows():
                signed_change = (
                    float(bar["close"]) - float(trade["entry_price"])
                    if trade["breakout_direction"] == "long"
                    else float(trade["entry_price"]) - float(bar["close"])
                )
                scale = float(trade["quantity"]) * float(trade["contract_multiplier"])
                unrealized += signed_change * scale
                exposure += abs(float(bar["close"]) * scale)
            rows.append({
                "datetime": timestamp, "realized_pnl": realized,
                "unrealized_pnl": unrealized, "gross_exposure": exposure,
            })
        curve = pd.DataFrame(rows)
    curve["equity"] = initial_cash + curve["realized_pnl"] + curve["unrealized_pnl"]
    peak = curve["equity"].cummax().clip(lower=initial_cash)
    curve["drawdown"] = peak - curve["equity"]
    curve["drawdown_pct"] = curve["equity"] / peak - 1
    return curve[columns]


def _empty_metrics(initial_cash: float) -> dict[str, Any]:
    return {
        "total_setups": 0, "total_trades": 0, "long_trades": 0, "short_trades": 0,
        "winning_trades": 0, "losing_trades": 0, "breakeven_trades": 0,
        "win_rate": 0.0, "target_1_2_hit_rate": 0.0, "target_1_3_hit_rate": 0.0,
        "target_1_4_hit_rate": 0.0, "target_1_5_hit_rate": 0.0,
        "average_r_achieved": 0.0, "median_r_achieved": 0.0,
        "gross_profit": 0.0, "gross_loss": 0.0, "profit_factor": 0.0,
        "net_pnl": 0.0, "initial_cash": initial_cash, "final_equity": initial_cash,
        "total_return": 0.0, "maximum_drawdown": 0.0, "maximum_drawdown_pct": 0.0,
    }
