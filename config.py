"""Auditable execution settings; these do not alter signal generation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date


@dataclass(frozen=True)
class BacktestConfig:
    symbol: str
    instrument_type: str = "index"
    timezone: str = "UTC"
    quantity: float = 1.0
    contract_multiplier: float = 1.0
    expiry: str | None = None
    strike: float | None = None
    option_type: str | None = None
    initial_cash: float = 100_000.0
    intrabar_conflict_policy: str = "stop_first"
    fill_model: str = "stop_order_bar_proxy"

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol cannot be empty")
        if self.quantity <= 0:
            raise ValueError("quantity must be greater than zero")
        if self.contract_multiplier <= 0:
            raise ValueError("contract_multiplier must be greater than zero")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be greater than zero")
        if self.instrument_type not in {"index", "option"}:
            raise ValueError("instrument_type must be 'index' or 'option'")
        if self.instrument_type == "option":
            if not self.expiry or self.strike is None or self.option_type not in {"call", "put"}:
                raise ValueError("options require expiry, strike, and option_type=call|put")
            try:
                date.fromisoformat(self.expiry)
            except ValueError as error:
                raise ValueError("expiry must use YYYY-MM-DD") from error
            if self.strike <= 0:
                raise ValueError("option strike must be greater than zero")
            if not float(self.quantity).is_integer():
                raise ValueError("option quantity must be a whole number of contracts/lots")
        if self.intrabar_conflict_policy != "stop_first":
            raise ValueError("Only the deterministic stop_first policy is supported")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
