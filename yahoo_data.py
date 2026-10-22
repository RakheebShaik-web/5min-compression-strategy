"""Optional Yahoo Finance adapter for recent 5-minute research data."""

from __future__ import annotations

from typing import Any

import pandas as pd

from data_loader import normalize_ohlcv


def download_yahoo_5m(
    ticker: str,
    timezone: str,
    *,
    period: str | None = "1mo",
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    if not ticker.strip():
        raise ValueError("Yahoo ticker cannot be empty")
    if (start is None) != (end is None):
        raise ValueError("Yahoo start and end must be supplied together")
    try:
        import yfinance as yf
    except ImportError as error:
        raise RuntimeError("Install project requirements to use Yahoo Finance") from error

    arguments: dict[str, Any] = {
        "tickers": ticker,
        "interval": "5m",
        "auto_adjust": False,
        "actions": False,
        "prepost": False,
        "progress": False,
        "threads": False,
        "repair": False,
        "multi_level_index": False,
    }
    if start is not None and end is not None:
        arguments.update(start=start, end=end)
    else:
        arguments["period"] = period or "1mo"

    downloaded = yf.download(**arguments)
    if downloaded is None or downloaded.empty:
        raise ValueError(f"Yahoo Finance returned no 5-minute data for {ticker}")
    downloaded = downloaded.reset_index()
    datetime_column = "Datetime" if "Datetime" in downloaded.columns else "Date"
    downloaded = downloaded.rename(
        columns={
            datetime_column: "datetime", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume",
        }
    )
    return normalize_ohlcv(downloaded, timezone)
