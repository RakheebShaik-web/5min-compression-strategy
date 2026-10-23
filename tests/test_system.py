from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from backtest import RESULT_COLUMNS, run_backtest
from config import BacktestConfig
from data_loader import fingerprint, load_ohlcv, validate_option_dates
from metrics import build_equity_curve, calculate_metrics
from strategy import detect_setups
from yahoo_data import download_yahoo_5m
from dual_backtest import OptionExecutionLeg, run_signal_to_options_backtest
from market_data import resample_one_minute_to_five, select_option_contract
from providers import dhan_rolling_to_frame, upstox_candles_to_frame


ROOT = Path(__file__).resolve().parents[1]


def test_reference_sample_detects_expected_long_and_short() -> None:
    bars = load_ohlcv(ROOT / "sample_5min.csv")
    results = run_backtest(bars, "TEST")

    assert list(results["breakout_direction"]) == ["long", "short"]
    assert list(results["entry_price"]) == [108.0, 192.0]
    assert list(results["stop_loss_price"]) == [94.0, 208.0]
    assert list(results["r_multiple_achieved"]) == [5.0, 5.0]


def test_pattern_requires_strictly_declining_volume() -> None:
    bars = load_ohlcv(ROOT / "sample_5min.csv").iloc[:4].copy()
    bars.loc[2, "volume"] = bars.loc[1, "volume"]
    assert detect_setups(bars, "TEST") == []


def test_breakout_cannot_enter_before_third_inside_bar_closes() -> None:
    bars = load_ohlcv(ROOT / "sample_5min.csv").iloc[:5]
    setup = detect_setups(bars, "TEST")[0]
    result = run_backtest(bars, "TEST").iloc[0]
    assert result["breakout_datetime"] > setup.inside_3["datetime"]


def test_gap_through_long_breakout_fills_at_open() -> None:
    bars = load_ohlcv(ROOT / "sample_5min.csv").iloc[:5].copy()
    bars.loc[4, ["open", "high", "low", "close"]] = [115, 120, 112, 118]
    result = run_backtest(bars, "TEST").iloc[0]
    assert result["entry_price"] == 115.0
    assert result["risk_per_unit"] == 21.0


def test_both_breakout_boundaries_in_one_bar_is_not_traded() -> None:
    bars = load_ohlcv(ROOT / "sample_5min.csv").iloc[:5].copy()
    bars.loc[4, ["open", "high", "low", "close"]] = [100, 109, 93, 100]
    result = run_backtest(bars, "TEST").iloc[0]
    assert result["status"] == "ambiguous_breakout"
    assert pd.isna(result["entry_price"])


def test_fourth_inside_bar_expires_original_setup() -> None:
    bars = load_ohlcv(ROOT / "sample_5min.csv").iloc[:5].copy()
    bars.loc[4, ["open", "high", "low", "close"]] = [101, 105, 97, 102]
    result = run_backtest(bars, "TEST").iloc[0]
    assert result["status"] == "no_breakout"


def test_possible_stop_before_breakout_is_ambiguous() -> None:
    bars = load_ohlcv(ROOT / "sample_5min.csv").iloc[:5].copy()
    bars.loc[4, ["open", "high", "low", "close"]] = [100, 109, 94, 108]
    result = run_backtest(bars, "TEST").iloc[0]
    assert result["status"] == "ambiguous_entry_exit"


def test_gap_open_resolves_two_sided_breakout_direction() -> None:
    bars = load_ohlcv(ROOT / "sample_5min.csv").iloc[:5].copy()
    bars.loc[4, ["open", "high", "low", "close"]] = [115, 116, 90, 95]
    result = run_backtest(bars, "TEST").iloc[0]
    assert result["status"] == "traded"
    assert result["breakout_direction"] == "long"
    assert result["entry_price"] == 115.0


def test_empty_run_preserves_export_schema() -> None:
    bars = load_ohlcv(ROOT / "sample_5min.csv").iloc[:3]
    results = run_backtest(bars, "TEST")
    assert results.empty
    assert list(results.columns) == RESULT_COLUMNS


def test_metrics_and_equity_use_realized_exit_order() -> None:
    results = pd.DataFrame(
        [
            {"setup_id": 1, "status": "traded", "exit_datetime": pd.Timestamp("2026-01-02 10:00", tz="UTC"), "pnl": 20.0, "breakout_direction": "long", "maximum_target_reached": 2, "r_multiple_achieved": 2.0},
            {"setup_id": 2, "status": "traded", "exit_datetime": pd.Timestamp("2026-01-02 09:00", tz="UTC"), "pnl": -10.0, "breakout_direction": "short", "maximum_target_reached": 0, "r_multiple_achieved": -1.0},
        ]
    )
    metrics = calculate_metrics(results, initial_cash=100.0)
    equity = build_equity_curve(results, initial_cash=100.0)
    assert metrics["maximum_drawdown"] == 10.0
    assert metrics["maximum_drawdown_pct"] == pytest.approx(0.1)
    assert list(equity["equity"]) == [90.0, 110.0]


def test_loader_rejects_non_five_minute_timestamp(tmp_path: Path) -> None:
    source = tmp_path / "bad.csv"
    source.write_text(
        "datetime,open,high,low,close,volume\n2026-01-02 09:17:00,1,2,1,2,10\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="5-minute boundary"):
        load_ohlcv(source)


def test_fingerprint_is_stable() -> None:
    source = ROOT / "sample_5min.csv"
    bars = load_ohlcv(source)
    first = fingerprint(source, bars, "UTC")
    second = fingerprint(source, bars, "UTC")
    assert first == second
    assert len(first.sha256) == 64


def test_yahoo_adapter_normalizes_download(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = pd.DataFrame(
        {
            "Datetime": pd.date_range("2026-01-02 09:15", periods=4, freq="5min", tz="Asia/Kolkata"),
            "Open": [100, 101, 102, 103], "High": [102, 103, 104, 105],
            "Low": [99, 100, 101, 102], "Close": [101, 102, 103, 104],
            "Volume": [1000, 900, 800, 700],
        }
    ).set_index("Datetime")
    fake = SimpleNamespace(download=lambda **_: raw)
    monkeypatch.setitem(sys.modules, "yfinance", fake)
    bars = download_yahoo_5m("^NSEI", "Asia/Kolkata", period="5d")
    assert list(bars.columns) == ["datetime", "open", "high", "low", "close", "volume"]
    assert len(bars) == 4
    assert str(bars["datetime"].dt.tz) == "Asia/Kolkata"


def test_config_rejects_invalid_quantity() -> None:
    with pytest.raises(ValueError, match="quantity"):
        BacktestConfig(symbol="TEST", quantity=0)


def test_option_config_requires_explicit_contract_identity() -> None:
    with pytest.raises(ValueError, match="options require"):
        BacktestConfig(symbol="NIFTY", instrument_type="option", contract_multiplier=75)


def test_option_pnl_uses_contract_multiplier() -> None:
    bars = load_ohlcv(ROOT / "sample_5min.csv").iloc[:6]
    config = BacktestConfig(
        symbol="TESTOPT", instrument_type="option", quantity=2,
        contract_multiplier=25, expiry="2026-01-29", strike=100.0, option_type="call",
    )
    result = run_backtest(bars, "TESTOPT", config).iloc[0]
    assert result["pnl_per_unit"] == 70.0
    assert result["pnl"] == 3500.0


def test_option_data_after_expiry_is_rejected() -> None:
    bars = load_ohlcv(ROOT / "sample_5min.csv")
    with pytest.raises(ValueError, match="after the configured expiry"):
        validate_option_dates(bars, "2026-01-01")


def test_one_minute_resample_uses_exact_ohlcv_rules() -> None:
    minute = pd.DataFrame({
        "datetime": pd.date_range("2026-01-02 09:15", periods=5, freq="1min", tz="Asia/Kolkata"),
        "open": [10, 11, 12, 13, 14], "high": [12, 13, 14, 15, 16],
        "low": [9, 10, 11, 12, 13], "close": [11, 12, 13, 14, 15],
        "volume": [1, 2, 3, 4, 5],
    })
    bars, report = resample_one_minute_to_five(minute)
    assert bars.iloc[0][["open", "high", "low", "close", "volume"]].tolist() == [10, 16, 9, 15, 15]
    assert report.output_bars == 1


def test_option_selection_requires_explicit_rule() -> None:
    contracts = [
        {"expiry": "2026-01-29", "instrument_type": "CE", "strike_price": 100},
        {"expiry": "2026-01-29", "instrument_type": "CE", "strike_price": 110},
    ]
    selected = select_option_contract(contracts, expiry="2026-01-29", option_type="call", spot=104, moneyness_steps=1)
    assert selected["strike_price"] == 110


def test_signal_to_option_uses_next_option_bar_open() -> None:
    bars = load_ohlcv(ROOT / "sample_5min.csv")
    leg = OptionExecutionLeg("TESTCE", "2026-01-29", 100, "call", "long", 1, 25, 0.05)
    put = OptionExecutionLeg("TESTPE", "2026-01-29", 100, "put", "long", 1, 25, 0.05)
    results = run_signal_to_options_backtest(bars.iloc[:6], "TESTFUT", bars, bars, leg, put)
    trade = results.iloc[0]
    assert trade["option_entry_datetime"] > trade["breakout_datetime"]
    assert trade["option_entry_price"] == 108.0
    assert trade["option_exit_price"] == 200.0
    assert trade["option_pnl"] == 2300.0


def test_option_execution_applies_unfavorable_friction_tick_rounding_and_fees() -> None:
    bars = load_ohlcv(ROOT / "sample_5min.csv")
    leg = OptionExecutionLeg("TESTCE", "2026-01-29", 100, "call", "long", 1, 25, 0.05, 10, 20)
    put = OptionExecutionLeg("TESTPE", "2026-01-29", 100, "put", "long", 1, 25, 0.05)
    trade = run_signal_to_options_backtest(bars.iloc[:6], "TESTFUT", bars, bars, leg, put).iloc[0]
    assert trade["option_entry_price"] == 108.15
    assert trade["option_exit_price"] == 199.8
    assert trade["option_fees"] == 40
    assert trade["option_pnl"] == pytest.approx(2251.25)


def test_upstox_candle_parser_validates_and_sorts() -> None:
    payload = {"status": "success", "data": {"candles": [
        ["2026-01-02T09:20:00+05:30", 11, 12, 10, 11.5, 90, 1],
        ["2026-01-02T09:15:00+05:30", 10, 11, 9, 10.5, 100, 1],
    ]}}
    bars = upstox_candles_to_frame(payload, "Asia/Kolkata")
    assert list(bars["open"]) == [10, 11]


def test_dhan_candle_parser_validates_parallel_arrays() -> None:
    timestamps = [int(pd.Timestamp("2026-01-02 09:15", tz="Asia/Kolkata").timestamp())]
    payload = {"data": {"ce": {
        "timestamp": timestamps, "open": [10], "high": [11], "low": [9],
        "close": [10.5], "volume": [100],
    }, "pe": None}}
    bars = dhan_rolling_to_frame(payload, "call", "Asia/Kolkata")
    assert bars.iloc[0]["volume"] == 100
