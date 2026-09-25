"""MD-1.1 venue/instrument identity contract tests (written first)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from saathi.platform.market_data.contract import AssetClass, CanonicalQuote, PointInTime, ProviderReference
from saathi.platform.market_data.identity import IdentityValidationError, resolve_market_identity
from saathi.platform.tg.historical.import_service import HistoricalImportService
from saathi.platform.tg.market_data.errors import MarketDataError
from saathi.platform.tg.market_data.normalization import normalize_ohlcv_row
from saathi.platform.tg.market_data.service import reset_market_data_for_tests


def test_nepse_instrument_and_xnas_venue_is_rejected() -> None:
    with pytest.raises(IdentityValidationError) as exc:
        resolve_market_identity(
            instrument_id="NEPSE:NABIL", venue="XNAS", market="NEPSE", asset_class="EQUITY"
        )
    assert exc.value.code == "IDENTITY_CONTRADICTION"


def test_nepse_market_and_xnas_exchange_is_rejected() -> None:
    with pytest.raises(IdentityValidationError) as exc:
        resolve_market_identity(venue="XNAS", market="NEPSE", asset_class="EQUITY")
    assert exc.value.code == "IDENTITY_CONTRADICTION"


def test_nepse_identity_derives_venue_and_market_when_omitted() -> None:
    identity = resolve_market_identity(instrument_id="NEPSE:NABIL", asset_class="EQUITY")
    assert identity.venue == "NEPSE"
    assert identity.market == "NEPSE"


def test_provider_case_alias_resolves_to_canonical_nepse_identity() -> None:
    identity = resolve_market_identity(instrument_id="nepse:nabil", venue="NEPSE")
    assert identity.instrument_id == "NEPSE:NABIL"
    assert identity.venue == "NEPSE"


def test_nepse_market_resolves_an_unqualified_provider_symbol() -> None:
    identity = resolve_market_identity(instrument_id="nabil", market="NEPSE", asset_class="EQUITY")
    assert identity.instrument_id == "NEPSE:NABIL"
    assert identity.venue == "NEPSE"


def test_unknown_prefixed_instrument_cannot_inherit_a_real_venue() -> None:
    with pytest.raises(IdentityValidationError) as exc:
        resolve_market_identity(instrument_id="UNKNOWN:NABIL", market="NEPSE", asset_class="EQUITY")
    assert exc.value.code in {"UNKNOWN_VENUE", "IDENTITY_CONTRADICTION"}


def test_identity_contract_remains_multi_market_extensible() -> None:
    crypto = resolve_market_identity(
        instrument_id="BINANCE:BTCUSDT", venue="BINANCE", market="CRYPTO", asset_class="CRYPTO"
    )
    us_etf = resolve_market_identity(
        instrument_id="XNAS:QQQ", venue="XNAS", market="US", asset_class="ETF"
    )
    assert crypto.venue == "BINANCE"
    assert us_etf.venue == "XNAS"


def test_canonical_market_data_event_rejects_contradictory_identity() -> None:
    with pytest.raises(ValueError, match="IDENTITY_CONTRADICTION"):
        CanonicalQuote(
            instrument_id="NEPSE:NABIL",
            venue="XNAS",
            asset_class=AssetClass.EQUITY,
            currency="NPR",
            point_in_time=PointInTime(
                event_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
                available_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                received_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            provider=ProviderReference(provider="fixture"),
        )


def test_generic_registry_has_no_real_exchange_default() -> None:
    svc = reset_market_data_for_tests()
    registered = svc.register_dataset(name="generic_identity_probe", checksum="identity-1", licence_type="CC0-1.0")
    assert registered["exchange"] in {"", "UNKNOWN"}


def test_explicit_xnas_consumer_remains_supported() -> None:
    svc = reset_market_data_for_tests()
    registered = svc.register_dataset(
        name="explicit_xnas_probe", market="US", exchange="XNAS", asset_class="equity",
        checksum="identity-2", licence_type="CC0-1.0",
    )
    assert registered["exchange"] == "XNAS"


def test_nepse_registry_derives_nepse_exchange() -> None:
    svc = reset_market_data_for_tests()
    registered = svc.register_dataset(
        name="nepse_identity_probe", market="NEPSE", checksum="identity-3", licence_type="CC0-1.0"
    )
    assert registered["exchange"] == "NEPSE"


def test_registry_rejects_contradictory_market_and_exchange() -> None:
    svc = reset_market_data_for_tests()
    with pytest.raises(MarketDataError) as exc:
        svc.register_dataset(
            name="bad_identity_probe", market="NEPSE", exchange="XNAS",
            checksum="identity-4", licence_type="CC0-1.0",
        )
    assert exc.value.code == "IDENTITY_CONTRADICTION"


def test_calendar_check_fails_closed_when_dataset_venue_is_unknown() -> None:
    svc = reset_market_data_for_tests()
    registered = svc.register_dataset(
        name="unknown_calendar_probe", checksum="identity-5", licence_type="CC0-1.0"
    )
    result = svc.calendar.check_bars(registered["dataset_id"], "v1")
    assert result["ok"] is False
    assert result["code"] == "UNKNOWN_VENUE"


def test_normalizer_never_falls_back_to_xnas() -> None:
    row, status, reasons = normalize_ohlcv_row(
        {"date": "2026-01-01", "symbol": "NABIL", "open": "1", "high": "2", "low": "1", "close": "2"},
        dataset_id="d", source_row_ref="r", defaults={},
    )
    assert row is None
    assert status == "REJECTED"
    assert "missing_instrument_identity" in reasons


def test_nepse_historical_import_cannot_keep_us_defaults(tmp_path: Path) -> None:
    path = tmp_path / "nepse.csv"
    lines = ["date,symbol,open,high,low,close,volume"]
    for day in range(1, 21):
        lines.append(f"2024-01-{day:02d},NABIL,100,101,99,100,1000")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = HistoricalImportService().import_file(path, market="NEPSE", adapter="local_file")
    assert out["status"] in {"ACCEPTED", "ACCEPTED_WITH_WARNINGS", "QUARANTINED"}
    version = out["version"]
    assert version["market"] == "NEPSE"
    assert version["currency"] == "NPR"
    assert version["timezone"] == "Asia/Kathmandu"
    assert version["manifest"]["calendar_name"] == "NEPSE"
