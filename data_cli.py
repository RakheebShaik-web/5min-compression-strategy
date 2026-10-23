"""Download audited 5-minute option data from Upstox or DhanHQ."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from market_data import select_option_contract
from providers import (
    DhanClient,
    UpstoxClient,
    dhan_rolling_to_frame,
    save_raw_response,
    upstox_candles_to_frame,
)


def _output(payload: dict, bars, directory: Path, metadata: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    save_raw_response(directory / "raw_response.json", payload)
    bars.to_csv(directory / "bars_5min.csv", index=False)
    (directory / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download historical option candles")
    subparsers = parser.add_subparsers(dest="provider", required=True)

    upstox = subparsers.add_parser("upstox")
    upstox.add_argument("--underlying-key", required=True)
    upstox.add_argument("--expiry", required=True)
    upstox.add_argument("--option-type", choices=("call", "put"), required=True)
    selection = upstox.add_mutually_exclusive_group(required=True)
    selection.add_argument("--strike", type=float)
    selection.add_argument("--moneyness-offset", type=int)
    upstox.add_argument("--spot", type=float)
    upstox.add_argument("--start", required=True)
    upstox.add_argument("--end", required=True)
    upstox.add_argument("--timezone", default="Asia/Kolkata")
    upstox.add_argument("--output", required=True)

    dhan = subparsers.add_parser("dhan")
    dhan.add_argument("--security-id", required=True)
    dhan.add_argument("--expiry-flag", choices=("WEEK", "MONTH"), required=True)
    dhan.add_argument("--expiry-code", type=int, required=True)
    dhan.add_argument("--strike", required=True, help="ATM or ATM+/-N")
    dhan.add_argument("--option-type", choices=("call", "put"), required=True)
    dhan.add_argument("--start", required=True)
    dhan.add_argument("--end", required=True)
    dhan.add_argument("--timezone", default="Asia/Kolkata")
    dhan.add_argument("--output", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.provider == "upstox":
        client = UpstoxClient()
        contracts_payload = client.option_contracts(args.underlying_key, args.expiry, expired=True)
        contract = select_option_contract(
            contracts_payload["data"], expiry=args.expiry, option_type=args.option_type,
            strike=args.strike, spot=args.spot, moneyness_steps=args.moneyness_offset,
        )
        instrument_key = contract.get("expired_instrument_key") or contract.get("instrument_key")
        if not instrument_key:
            raise ValueError("Selected Upstox contract has no instrument key")
        payload = client.expired_candles(str(instrument_key), args.start, args.end)
        bars = upstox_candles_to_frame(payload, args.timezone)
        metadata = {"provider": "upstox", "contract": contract, "start": args.start, "end": args.end}
        output_directory = Path(args.output)
        save_raw_response(output_directory / "contracts_response.json", contracts_payload)
    else:
        if (date.fromisoformat(args.end) - date.fromisoformat(args.start)).days > 30:
            raise ValueError("Dhan rolling-option requests are limited to 30 days; split the range")
        client = DhanClient()
        body = {
            "exchangeSegment": "NSE_FNO", "interval": "5", "securityId": args.security_id,
            "instrument": "OPTIDX", "expiryFlag": args.expiry_flag,
            "expiryCode": args.expiry_code, "strike": args.strike,
            "drvOptionType": args.option_type.upper(),
            "requiredData": ["open", "high", "low", "close", "volume", "strike", "oi", "spot"],
            "fromDate": args.start, "toDate": args.end,
        }
        payload = client.rolling_options(body)
        bars = dhan_rolling_to_frame(payload, args.option_type, args.timezone)
        metadata = {"provider": "dhan", "request": body, "selection_is_rolling": True}
    _output(payload, bars, Path(args.output), metadata)
    print(f"Wrote {len(bars)} bars to {Path(args.output) / 'bars_5min.csv'}")


if __name__ == "__main__":
    main()
