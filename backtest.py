"""Deterministic bar-by-bar simulation for detected setups."""

from __future__ import annotations

from typing import Any

import pandas as pd

from config import BacktestConfig
from strategy import Setup, detect_setups, stop_for, targets_for


RESULT_COLUMNS = [
    "setup_id", "date", "time", "symbol",
    *[f"{prefix}_{field}" for prefix in ("mother", "inside_1", "inside_2", "inside_3")
      for field in ("datetime", "open", "high", "low", "close", "volume")],
    "consolidation_high", "consolidation_low", "status", "breakout_direction",
    "breakout_datetime", "entry_price", "stop_loss_price", "risk_per_unit",
    "target_1_2", "target_1_3", "target_1_4", "target_1_5",
    "maximum_target_reached", "exit_datetime", "exit_price", "exit_reason",
    "instrument_type", "expiry", "strike", "option_type", "quantity",
    "contract_multiplier", "pnl_per_unit", "pnl", "r_multiple_achieved",
]


def _bar_fields(prefix: str, bar: pd.Series) -> dict[str, Any]:
    return {
        f"{prefix}_datetime": bar["datetime"],
        **{f"{prefix}_{field}": float(bar[field]) for field in ("open", "high", "low", "close", "volume")},
    }


def _base_record(setup: Setup) -> dict[str, Any]:
    return {
        "setup_id": setup.setup_id,
        "date": setup.inside_3["datetime"].date().isoformat(),
        "time": setup.inside_3["datetime"].time().isoformat(),
        "symbol": setup.symbol,
        **_bar_fields("mother", setup.mother),
        **_bar_fields("inside_1", setup.inside_1),
        **_bar_fields("inside_2", setup.inside_2),
        **_bar_fields("inside_3", setup.inside_3),
        "consolidation_high": float(setup.consolidation_high),
        "consolidation_low": float(setup.consolidation_low),
    }


def _stop_entry_price(bar: pd.Series, trigger: float, direction: str) -> float:
    if direction == "long":
        return max(float(bar["open"]), trigger)
    return min(float(bar["open"]), trigger)


def _stop_exit_price(bar: pd.Series, stop: float, direction: str) -> float:
    if direction == "long":
        return min(float(bar["open"]), stop)
    return max(float(bar["open"]), stop)


def _simulate_setup(setup: Setup, bars: pd.DataFrame, config: BacktestConfig) -> dict[str, Any]:
    base = _base_record(setup)
    breakout_index: int | None = None
    direction = ""
    next_index = setup.ready_index + 1
    if next_index < len(bars):
        for index in (next_index,):
            bar = bars.iloc[index]
            breaks_high = bar["high"] > setup.consolidation_high
            breaks_low = bar["low"] < setup.consolidation_low
            if breaks_high and breaks_low:
                if bar["open"] > setup.consolidation_high:
                    breakout_index = index
                    direction = "long"
                elif bar["open"] < setup.consolidation_low:
                    breakout_index = index
                    direction = "short"
                else:
                    return {**base, "status": "ambiguous_breakout", "breakout_direction": ""}
            if breaks_high or breaks_low:
                if breakout_index is None:
                    breakout_index = index
                    direction = "long" if breaks_high else "short"

    if breakout_index is None:
        return {**base, "status": "no_breakout", "breakout_direction": ""}

    breakout_bar = bars.iloc[breakout_index]
    trigger = setup.consolidation_high if direction == "long" else setup.consolidation_low
    entry = _stop_entry_price(breakout_bar, float(trigger), direction)
    stop = float(stop_for(setup, direction))
    entry_was_at_open = (
        breakout_bar["open"] > trigger if direction == "long" else breakout_bar["open"] < trigger
    )
    could_stop_before_entry = (
        breakout_bar["low"] <= stop if direction == "long" else breakout_bar["high"] >= stop
    )
    if could_stop_before_entry and not entry_was_at_open:
        return {
            **base,
            "status": "ambiguous_entry_exit",
            "breakout_direction": direction,
            "breakout_datetime": breakout_bar["datetime"],
        }
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
            multiple for multiple, target in targets.items()
            if (bar["high"] >= target if direction == "long" else bar["low"] <= target)
        ]
        if stop_hit:
            exit_price = _stop_exit_price(bar, stop, direction)
            exit_reason = "stop_loss"
            exit_index = index
            break
        if reached:
            maximum_target = max(maximum_target, max(reached))
        if maximum_target == 5:
            exit_price = float(targets[5])
            exit_reason = "target_1_5"
            exit_index = index
            break

    pnl_per_unit = exit_price - entry if direction == "long" else entry - exit_price
    return {
        **base, "status": "traded", "breakout_direction": direction,
        "breakout_datetime": breakout_bar["datetime"], "entry_price": entry,
        "stop_loss_price": stop, "risk_per_unit": risk,
        **{f"target_1_{multiple}": target for multiple, target in targets.items()},
        "maximum_target_reached": maximum_target,
        "exit_datetime": bars.iloc[exit_index]["datetime"], "exit_price": exit_price,
        "exit_reason": exit_reason, "instrument_type": config.instrument_type,
        "expiry": config.expiry, "strike": config.strike, "option_type": config.option_type,
        "quantity": config.quantity, "contract_multiplier": config.contract_multiplier,
        "pnl_per_unit": pnl_per_unit,
        "pnl": pnl_per_unit * config.quantity * config.contract_multiplier,
        "r_multiple_achieved": pnl_per_unit / risk,
    }


def run_backtest(bars: pd.DataFrame, symbol: str, config: BacktestConfig | None = None) -> pd.DataFrame:
    effective_config = config or BacktestConfig(symbol=symbol)
    if effective_config.symbol != symbol:
        raise ValueError("config symbol must match the requested symbol")
    records = [_simulate_setup(setup, bars, effective_config) for setup in detect_setups(bars, symbol)]
    return pd.DataFrame.from_records(records, columns=RESULT_COLUMNS)
