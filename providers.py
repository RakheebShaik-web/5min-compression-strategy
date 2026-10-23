"""Credential-safe market-data clients for Upstox and DhanHQ."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import pandas as pd

from data_loader import normalize_ohlcv


class ProviderError(RuntimeError):
    pass


def _request_json(request: Request, timeout: int = 30, attempts: int = 3) -> dict[str, Any]:
    payload: Any = None
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except HTTPError as error:
            retryable = error.code == 429 or 500 <= error.code < 600
            if retryable and attempt + 1 < attempts:
                retry_after = error.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt
                time.sleep(min(delay, 30))
                continue
            body = error.read().decode("utf-8", errors="replace")[:500]
            raise ProviderError(f"Provider HTTP {error.code}: {body}") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
                continue
            raise ProviderError(f"Provider request failed after {attempts} attempts: {error}") from error
    if not isinstance(payload, dict):
        raise ProviderError("Provider response must be a JSON object")
    return payload


def save_raw_response(path: str | Path, payload: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(destination)


class UpstoxClient:
    base_url = "https://api.upstox.com/v2"

    def __init__(self, access_token: str | None = None) -> None:
        self.access_token = access_token or os.getenv("UPSTOX_ACCESS_TOKEN", "")
        if not self.access_token:
            raise ValueError("Set UPSTOX_ACCESS_TOKEN; credentials are never stored in project files")

    def _get(self, path: str, parameters: dict[str, str] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        if parameters:
            url += "?" + urlencode(parameters)
        request = Request(url, headers={"Accept": "application/json", "Authorization": f"Bearer {self.access_token}", "User-Agent": "5min-compression-research/1.0"})
        payload = _request_json(request)
        if payload.get("status") != "success" or "data" not in payload:
            raise ProviderError("Upstox response is missing successful data")
        return payload

    def expiries(self, underlying_key: str) -> dict[str, Any]:
        return self._get("/expired-instruments/expiries", {"instrument_key": underlying_key})

    def option_contracts(self, underlying_key: str, expiry: str, expired: bool = True) -> dict[str, Any]:
        path = "/expired-instruments/option/contract" if expired else "/option/contract"
        return self._get(path, {"instrument_key": underlying_key, "expiry_date": expiry})

    def expired_candles(self, instrument_key: str, start: str, end: str) -> dict[str, Any]:
        key = quote(instrument_key, safe="")
        return self._get(f"/expired-instruments/historical-candle/{key}/5minute/{end}/{start}")


class DhanClient:
    base_url = "https://api.dhan.co/v2"

    def __init__(self, access_token: str | None = None, client_id: str | None = None) -> None:
        self.access_token = access_token or os.getenv("DHAN_ACCESS_TOKEN", "")
        self.client_id = client_id or os.getenv("DHAN_CLIENT_ID", "")
        if not self.access_token:
            raise ValueError("Set DHAN_ACCESS_TOKEN; credentials are never stored in project files")

    def rolling_options(self, request_body: dict[str, Any]) -> dict[str, Any]:
        required = {
            "exchangeSegment", "interval", "securityId", "instrument", "expiryFlag",
            "expiryCode", "strike", "drvOptionType", "requiredData", "fromDate", "toDate",
        }
        missing = required.difference(request_body)
        if missing:
            raise ValueError(f"Missing Dhan request fields: {sorted(missing)}")
        body = json.dumps(request_body).encode("utf-8")
        headers = {"Accept": "application/json", "Content-Type": "application/json", "access-token": self.access_token}
        if self.client_id:
            headers["client-id"] = self.client_id
        payload = _request_json(Request(f"{self.base_url}/charts/rollingoption", data=body, headers=headers, method="POST"))
        if "data" not in payload:
            raise ProviderError("Dhan response is missing data")
        return payload


def upstox_candles_to_frame(payload: dict[str, Any], timezone: str) -> pd.DataFrame:
    candles = payload.get("data", {}).get("candles")
    if not isinstance(candles, list) or not candles:
        raise ProviderError("Upstox candle response is empty or malformed")
    rows = []
    for candle in candles:
        if not isinstance(candle, list) or len(candle) < 6:
            raise ProviderError("Upstox candle must contain timestamp, OHLC, and volume")
        rows.append(candle[:6])
    frame = pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close", "volume"])
    frame = frame.sort_values("datetime", kind="stable")
    return normalize_ohlcv(frame, timezone)


def dhan_rolling_to_frame(payload: dict[str, Any], option_type: str, timezone: str) -> pd.DataFrame:
    key = "ce" if option_type.lower() in {"call", "ce"} else "pe"
    series = payload.get("data", {}).get(key)
    if not isinstance(series, dict):
        raise ProviderError(f"Dhan response does not contain {key} data")
    required = ("timestamp", "open", "high", "low", "close", "volume")
    if any(not isinstance(series.get(field), list) for field in required):
        raise ProviderError("Dhan candle arrays are missing or malformed")
    lengths = {len(series[field]) for field in required}
    if len(lengths) != 1 or not lengths or next(iter(lengths)) == 0:
        raise ProviderError("Dhan candle arrays have inconsistent or empty lengths")
    frame = pd.DataFrame({field: series[field] for field in required})
    frame["datetime"] = pd.to_datetime(frame["timestamp"], unit="s", utc=True).dt.tz_convert(timezone)
    frame = frame.drop(columns="timestamp").sort_values("datetime", kind="stable")
    return normalize_ohlcv(frame, timezone)
