"""Execute futures/index signals through explicitly mapped option contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

import pandas as pd

from backtest import run_backtest
from config import BacktestConfig


@dataclass(frozen=True)
class OptionExecutionLeg:
    symbol: str
    expiry: str
    strike: float
    option_type: str
    position_side: str
    quantity: int
    contract_multiplier: float
    tick_size: float
    friction_bps: float = 0.0
    fee_per_contract_per_side: float = 0.0

    def __post_init__(self) -> None:
        if self.option_type not in {"call", "put"}:
            raise ValueError("option_type must be call or put")
        if self.position_side not in {"long", "short"}:
            raise ValueError("position_side must be long or short")
        if self.quantity <= 0 or self.contract_multiplier <= 0 or self.strike <= 0 or self.tick_size <= 0:
            raise ValueError("quantity, multiplier, strike, and tick_size must be positive")
        if self.friction_bps < 0 or self.fee_per_contract_per_side < 0:
            raise ValueError("friction and fees cannot be negative")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _next_bar(bars: pd.DataFrame, timestamp: pd.Timestamp) -> pd.Series | None:
    matches = bars.loc[bars["datetime"] > timestamp]
    return None if matches.empty else matches.iloc[0]


def _option_fill(price: float, side: str, leg: OptionExecutionLeg) -> float:
    factor = 1 + leg.friction_bps / 10_000 if side == "buy" else 1 - leg.friction_bps / 10_000
    raw = Decimal(str(price * factor))
    tick = Decimal(str(leg.tick_size))
    rounding = ROUND_CEILING if side == "buy" else ROUND_FLOOR
    return float((raw / tick).to_integral_value(rounding=rounding) * tick)


def run_signal_to_options_backtest(
    signal_bars: pd.DataFrame,
    signal_symbol: str,
    long_option_bars: pd.DataFrame,
    short_option_bars: pd.DataFrame,
    long_leg: OptionExecutionLeg,
    short_leg: OptionExecutionLeg,
) -> pd.DataFrame:
    """Use signal-instrument structure levels and next-bar option-open execution."""
    signal_config = BacktestConfig(symbol=signal_symbol, instrument_type="index")
    signals = run_backtest(signal_bars, signal_symbol, signal_config)
    records: list[dict[str, object]] = []
    for _, signal in signals.iterrows():
        record = signal.to_dict()
        record.update({
            "signal_symbol": signal_symbol,
            "execution_mode": "signal_to_option",
            "option_symbol": None,
            "option_entry_datetime": None,
            "option_entry_price": None,
            "option_exit_datetime": None,
            "option_exit_price": None,
            "option_position_side": None,
            "option_pnl_per_unit": None,
            "option_pnl": None,
        })
        if signal["status"] != "traded":
            records.append(record)
            continue
        is_long_signal = signal["breakout_direction"] == "long"
        option_bars = long_option_bars if is_long_signal else short_option_bars
        leg = long_leg if is_long_signal else short_leg
        entry_bar = _next_bar(option_bars, signal["breakout_datetime"])
        exit_bar = _next_bar(option_bars, signal["exit_datetime"])
        if entry_bar is None:
            record["status"] = "missing_option_entry"
            records.append(record)
            continue
        if exit_bar is None:
            record["status"] = "missing_option_exit"
            records.append(record)
            continue
        if entry_bar["datetime"] >= exit_bar["datetime"]:
            record["status"] = "signal_closed_before_option_entry"
            records.append(record)
            continue
        entry_side = "buy" if leg.position_side == "long" else "sell"
        exit_side = "sell" if leg.position_side == "long" else "buy"
        entry_price = _option_fill(float(entry_bar["open"]), entry_side, leg)
        exit_price = _option_fill(float(exit_bar["open"]), exit_side, leg)
        pnl_per_unit = exit_price - entry_price if leg.position_side == "long" else entry_price - exit_price
        fees = leg.fee_per_contract_per_side * leg.quantity * 2
        record.update({
            "status": "traded",
            "option_symbol": leg.symbol,
            "option_expiry": leg.expiry,
            "option_strike": leg.strike,
            "executed_option_type": leg.option_type,
            "option_entry_datetime": entry_bar["datetime"],
            "option_entry_price": entry_price,
            "option_exit_datetime": exit_bar["datetime"],
            "option_exit_price": exit_price,
            "option_position_side": leg.position_side,
            "option_quantity": leg.quantity,
            "option_contract_multiplier": leg.contract_multiplier,
            "option_friction_bps": leg.friction_bps,
            "option_fees": fees,
            "option_pnl_per_unit": pnl_per_unit,
            "option_pnl": pnl_per_unit * leg.quantity * leg.contract_multiplier - fees,
        })
        records.append(record)
    return pd.DataFrame.from_records(records)
