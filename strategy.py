"""Pattern detection and price-level calculations for the strategy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


R_MULTIPLES = (2, 3, 4, 5)


@dataclass(frozen=True)
class Setup:
    setup_id: int
    symbol: str
    mother_index: int
    ready_index: int
    mother: pd.Series
    inside_1: pd.Series
    inside_2: pd.Series
    inside_3: pd.Series
    consolidation_high: float
    consolidation_low: float


def is_inside(mother: pd.Series, candle: pd.Series) -> bool:
    """An inside candle may touch, but may not exceed, the mother range."""
    return candle["high"] <= mother["high"] and candle["low"] >= mother["low"]


def detect_setups(bars: pd.DataFrame, symbol: str) -> list[Setup]:
    """Detect every completed mother + three-inside-bar window."""
    setups: list[Setup] = []
    for mother_index in range(len(bars) - 3):
        mother = bars.iloc[mother_index]
        inside_1 = bars.iloc[mother_index + 1]
        inside_2 = bars.iloc[mother_index + 2]
        inside_3 = bars.iloc[mother_index + 3]

        all_inside = all(
            is_inside(mother, candle)
            for candle in (inside_1, inside_2, inside_3)
        )
        declining_volume = (
            inside_1["volume"] > inside_2["volume"] > inside_3["volume"]
        )
        if not (all_inside and declining_volume):
            continue

        setups.append(
            Setup(
                setup_id=len(setups) + 1,
                symbol=symbol,
                mother_index=mother_index,
                ready_index=mother_index + 3,
                mother=mother,
                inside_1=inside_1,
                inside_2=inside_2,
                inside_3=inside_3,
                consolidation_high=max(
                    inside_1["high"], inside_2["high"], inside_3["high"]
                ),
                consolidation_low=min(
                    inside_1["low"], inside_2["low"], inside_3["low"]
                ),
            )
        )
    return setups


def stop_for(setup: Setup, direction: str) -> float:
    inside_bars: Iterable[pd.Series] = (
        setup.inside_1,
        setup.inside_2,
        setup.inside_3,
    )
    if direction == "long":
        return min(bar["low"] for bar in inside_bars)
    if direction == "short":
        return max(bar["high"] for bar in inside_bars)
    raise ValueError(f"Unknown direction: {direction}")


def targets_for(entry: float, stop: float, direction: str) -> dict[int, float]:
    risk = abs(entry - stop)
    if direction == "long":
        return {multiple: entry + multiple * risk for multiple in R_MULTIPLES}
    if direction == "short":
        return {multiple: entry - multiple * risk for multiple in R_MULTIPLES}
    raise ValueError(f"Unknown direction: {direction}")
