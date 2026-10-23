"""Audited candle aggregation and explicit option-contract selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import pandas as pd

from data_loader import normalize_ohlcv


@dataclass(frozen=True)
class ResampleReport:
    input_bars: int
    output_bars: int
    dropped_incomplete_groups: int


def resample_one_minute_to_five(
    bars: pd.DataFrame, timezone: str = "Asia/Kolkata"
) -> tuple[pd.DataFrame, ResampleReport]:
    source = normalize_ohlcv(bars, timezone, expected_minutes=1)
    index_frame = source.set_index("datetime")
    grouped = index_frame.resample("5min", origin="start_day")
    counts = grouped["close"].count()
    complete = counts == 5
    aggregated = grouped.agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    aggregated = aggregated.loc[complete].dropna().reset_index()
    output = normalize_ohlcv(aggregated, timezone)
    report = ResampleReport(
        input_bars=len(source),
        output_bars=len(output),
        dropped_incomplete_groups=int((~complete).sum()),
    )
    return output, report


def select_option_contract(
    contracts: Sequence[dict[str, Any]],
    *,
    expiry: str,
    option_type: str,
    strike: float | None = None,
    spot: float | None = None,
    moneyness_steps: int | None = None,
) -> dict[str, Any]:
    """Select one contract using either an exact strike or explicit ATM offset."""
    normalized_type = {"call": "CE", "put": "PE", "CE": "CE", "PE": "PE"}.get(option_type)
    if normalized_type is None:
        raise ValueError("option_type must be call/put or CE/PE")
    candidates = [
        item for item in contracts
        if str(item.get("expiry")) == expiry
        and str(item.get("instrument_type", item.get("option_type", ""))).upper() == normalized_type
    ]
    if not candidates:
        raise ValueError("No contracts match the requested expiry and option type")
    if strike is not None and moneyness_steps is not None:
        raise ValueError("Use exact strike or moneyness_steps, not both")
    if strike is not None:
        matches = [item for item in candidates if float(item["strike_price"]) == float(strike)]
        if len(matches) != 1:
            raise ValueError("Exact strike did not resolve to one contract")
        return matches[0]
    if spot is None or moneyness_steps is None:
        raise ValueError("ATM selection requires spot and explicit moneyness_steps")
    strikes = sorted({float(item["strike_price"]) for item in candidates})
    atm_index = min(range(len(strikes)), key=lambda index: abs(strikes[index] - spot))
    target_index = atm_index + moneyness_steps
    if target_index < 0 or target_index >= len(strikes):
        raise ValueError("Requested moneyness offset is outside available strikes")
    target = strikes[target_index]
    matches = [item for item in candidates if float(item["strike_price"]) == target]
    if len(matches) != 1:
        raise ValueError("ATM offset did not resolve to one contract")
    return matches[0]
