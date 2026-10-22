"""CSV loading and strict 5-minute OHLCV validation."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


REQUIRED_COLUMNS = {"datetime", "open", "high", "low", "close", "volume"}


@dataclass(frozen=True)
class DataFingerprint:
    sha256: str
    total_bars: int
    first_timestamp: str
    last_timestamp: str
    close_sum: float
    volume_sum: float
    timezone: str
    timeframe: str = "5Min"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_ohlcv(path: str | Path, timezone: str = "UTC") -> pd.DataFrame:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"OHLCV file not found: {source}")
    ZoneInfo(timezone)
    bars = pd.read_csv(source)
    bars.columns = [column.strip().lower() for column in bars.columns]
    missing = REQUIRED_COLUMNS.difference(bars.columns)
    if missing:
        raise ValueError(f"Missing required CSV columns: {sorted(missing)}")
    if bars.empty:
        raise ValueError("OHLCV data cannot be empty")

    bars = bars[["datetime", "open", "high", "low", "close", "volume"]].copy()
    bars["datetime"] = pd.to_datetime(bars["datetime"], errors="raise")
    if isinstance(bars["datetime"].dtype, pd.DatetimeTZDtype):
        bars["datetime"] = bars["datetime"].dt.tz_convert(timezone)
    else:
        bars["datetime"] = bars["datetime"].dt.tz_localize(
            timezone, ambiguous="raise", nonexistent="raise"
        )
    for column in ("open", "high", "low", "close", "volume"):
        bars[column] = pd.to_numeric(bars[column], errors="raise")

    if bars["datetime"].duplicated().any():
        raise ValueError("Duplicate candle timestamps are not allowed")
    if not bars["datetime"].is_monotonic_increasing:
        raise ValueError("Candle timestamps must already be in chronological order")
    bars = bars.reset_index(drop=True)
    if ((bars["datetime"].dt.minute % 5) != 0).any() or (bars["datetime"].dt.second != 0).any():
        raise ValueError("Every timestamp must align to a 5-minute boundary")
    if len(bars) > 1:
        deltas = bars["datetime"].diff().dropna().dt.total_seconds()
        if ((deltas < 300) | ((deltas % 300) != 0)).any():
            raise ValueError("Data must contain only chronological 5-minute candles")
    if (bars["volume"] < 0).any():
        raise ValueError("Volume cannot be negative")
    if not bars[["open", "high", "low", "close", "volume"]].notna().all().all():
        raise ValueError("OHLCV values cannot be missing")
    if (bars[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("OHLC prices must be greater than zero")
    if (bars["high"] < bars[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("Invalid OHLC: high is below another price")
    if (bars["low"] > bars[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("Invalid OHLC: low is above another price")
    return bars


def fingerprint(path: str | Path, bars: pd.DataFrame, timezone: str) -> DataFingerprint:
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return DataFingerprint(
        sha256=digest,
        total_bars=len(bars),
        first_timestamp=bars.iloc[0]["datetime"].isoformat() if len(bars) else "",
        last_timestamp=bars.iloc[-1]["datetime"].isoformat() if len(bars) else "",
        close_sum=float(bars["close"].sum()),
        volume_sum=float(bars["volume"].sum()),
        timezone=timezone,
    )


def validate_option_dates(bars: pd.DataFrame, expiry: str) -> None:
    expiry_date = pd.Timestamp(expiry).date()
    if (bars["datetime"].dt.date > expiry_date).any():
        raise ValueError("Option data contains candles after the configured expiry")
