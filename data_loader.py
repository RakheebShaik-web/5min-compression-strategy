"""CSV loading and strict 5-minute OHLCV validation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = {"datetime", "open", "high", "low", "close", "volume"}


def load_ohlcv(path: str | Path) -> pd.DataFrame:
    bars = pd.read_csv(path)
    bars.columns = [column.strip().lower() for column in bars.columns]
    missing = REQUIRED_COLUMNS.difference(bars.columns)
    if missing:
        raise ValueError(f"Missing required CSV columns: {sorted(missing)}")

    bars = bars[["datetime", "open", "high", "low", "close", "volume"]].copy()
    bars["datetime"] = pd.to_datetime(bars["datetime"], errors="raise")
    for column in ("open", "high", "low", "close", "volume"):
        bars[column] = pd.to_numeric(bars[column], errors="raise")

    bars = bars.sort_values("datetime", kind="stable").reset_index(drop=True)
    if bars["datetime"].duplicated().any():
        raise ValueError("Duplicate candle timestamps are not allowed")
    if ((bars["datetime"].dt.minute % 5) != 0).any() or (bars["datetime"].dt.second != 0).any():
        raise ValueError("Every timestamp must align to a 5-minute boundary")
    if len(bars) > 1:
        deltas = bars["datetime"].diff().dropna().dt.total_seconds()
        if ((deltas < 300) | ((deltas % 300) != 0)).any():
            raise ValueError("Data must contain only chronological 5-minute candles")
    if (bars["volume"] < 0).any():
        raise ValueError("Volume cannot be negative")
    if (bars["high"] < bars[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("Invalid OHLC: high is below another price")
    if (bars["low"] > bars[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("Invalid OHLC: low is above another price")
    return bars
