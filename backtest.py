"""Deterministic bar-by-bar simulation for detected setups."""

from __future__ import annotations

from typing import Any

import pandas as pd

from strategy import R_MULTIPLES, Setup, detect_setups, stop_for, targets_for


def _bar_fields(prefix: str, bar: pd.Series) -> dict[str, Any]:
    return {
        f"{prefix}_datetime": bar["datetime"],
        **{f"{prefix}_{field}": float(bar[field]) for field in ("open", "high", "low", "close", "volume")},
    }


def _simulate_setup(setup: Setup, bars: pd.DataFrame) -> dict[str, Any]:
    base: dict[str, Any] = {
        "setup_id": setup.setup_id,
        "date": setup.inside_3["datetime"].date().isoformat(),
        "time": setup.inside_3["datetime"].time().isoformat(),
        "symbol": setup.symbol,
        **_bar_fields("mother", setup.mother),
        **_bar_fields("inside_1", setup.inside_1),
        **_bar_fields("inside_2", setup.inside_2),
        **_bar_fields("inside_3", setup.inside_3),
        "consolidation_high": setup.consolidation_high,
        "consolidation_low": setup.consolidation_low,
    }

    breakout_index = None
    direction = None
    for index in range(setup.ready_index + 1, len(bars)):
        bar = bars.iloc[index]
        breaks_high = bar["high"] > setup.consolidation_high
        breaks_low = bar["low"] < setup.consolidation_low
        if breaks_high and breaks_low:
            return {**base, "status": "ambiguous_breakout", "breakout_direction": ""}
        if breaks_high or breaks_low:
            breakout_index = index
            direction = "long" if breaks_high else "short"
            break

    if breakout_index is None or direction is None:
        return {**base, "status": "no_breakout", "breakout_direction": ""}

    entry = setup.consolidation_high if direction == "long" else setup.consolidation_low
    stop = stop_for(setup, direction)
    risk = abs(entry - stop)
    if risk == 0:
        return {**base, "status": "zero_risk", "breakout_direction": direction}
    targets = targets_for(entry, stop, direction)

    maximum_target = 0
    exit_price = float(bars.iloc[-1]["close"])
    exit_reason = "end_of_data"
    exit_index = len(bars) - 1
    for index in range(breakout_index, len(bars)):
        bar = bars.iloc[index]
        stop_hit = bar["low"] <= stop if direction == "long" else bar["high"] >= stop
        reached = [
            multiple
            for multiple, target in targets.items()
            if (bar["high"] >= target if direction == "long" else bar["low"] <= target)
        ]
        if stop_hit:
            exit_price = stop
            exit_reason = "stop_loss"
            exit_index = index
            break
        if reached:
            maximum_target = max(maximum_target, max(reached))
        if maximum_target == 5:
            exit_price = targets[5]
            exit_reason = "target_1_5"
            exit_index = index
            break

    pnl = exit_price - entry if direction == "long" else entry - exit_price
    return {
        **base,
        "status": "traded",
        "breakout_direction": direction,
        "breakout_datetime": bars.iloc[breakout_index]["datetime"],
        "entry_price": entry,
        "stop_loss_price": stop,
        "risk_per_unit": risk,
        **{f"target_1_{multiple}": target for multiple, target in targets.items()},
        "maximum_target_reached": maximum_target,
        "exit_datetime": bars.iloc[exit_index]["datetime"],
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "pnl": pnl,
        "r_multiple_achieved": pnl / risk,
    }


def run_backtest(bars: pd.DataFrame, symbol: str) -> pd.DataFrame:
    setups = detect_setups(bars, symbol)
    return pd.DataFrame([_simulate_setup(setup, bars) for setup in setups])
