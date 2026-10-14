import os
from unittest.mock import patch, MagicMock
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from services.notifier import (
    mask_url,
    validate_webhook_url,
    send_webhook_alert,
    send_telegram_alert,
    send_email_alert,
    process_screening_alerts,
)
from backend.database import Base
from backend.models.db_models import (
    SatelliteModel,
    ConjunctionModel,
    WatchlistItem,
    AlertSettings,
    SentAlert,
)


# ---------------------------------------------------------------------------
# SSRF Protection & URL Masking Tests
# ---------------------------------------------------------------------------

def test_mask_url_hides_path_and_query_secrets():
    """Verifies that sensitive path tokens and query parameters are never logged."""
    raw_url = "https://hooks.slack.com/services/T00000000/B00000000/XXXXX?token=supersecret123"
    masked = mask_url(raw_url)
    assert "supersecret123" not in masked
    assert "XXXXX" not in masked
    assert masked == "https://hooks.slack.com/***"


def test_mask_url_handles_edge_cases():
    assert mask_url("") == "[invalid-url]"
    assert mask_url("invalid-url") == "https://[masked-target]"


def test_validate_webhook_url_rejects_non_https():
    """Webhook URLs must use HTTPS only."""
    with pytest.raises(ValueError, match="must use secure HTTPS scheme"):
        validate_webhook_url("http://example.com/alerts")

    with pytest.raises(ValueError, match="must use secure HTTPS scheme"):
        validate_webhook_url("ftp://example.com/alerts")


def test_validate_webhook_url_rejects_credentials():
    """Verifies that webhook URLs containing user credentials (user:pass@) are rejected."""
    with pytest.raises(ValueError, match="embedded user credentials"):
        validate_webhook_url("https://user:password@webhook.site/alerts")

    with pytest.raises(ValueError, match="embedded user credentials"):
        validate_webhook_url("https://admin@webhook.site/alerts")


def test_mask_url_strips_credentials():
    """Verifies that user:pass credentials are removed when masking URLs for logs."""
    masked = mask_url("https://operator:supersecret@webhook.site/alerts")
    assert "operator" not in masked
    assert "supersecret" not in masked
    assert masked == "https://webhook.site/***"


def test_validate_webhook_url_blocks_private_and_loopback_ips():
    """Verifies that private, loopback, link-local, and metadata IPs are rejected (SSRF protection)."""
    # Loopback IPv4
    with pytest.raises(ValueError, match="SSRF"):
        validate_webhook_url("https://127.0.0.1:8000/webhook")

    with pytest.raises(ValueError, match="SSRF"):
        validate_webhook_url("https://localhost:8000/webhook")

    # Loopback IPv6
    with pytest.raises(ValueError, match="SSRF"):
        validate_webhook_url("https://[::1]:8000/webhook")

    # RFC 1918 Private IP Ranges
    with pytest.raises(ValueError, match="SSRF"):
        validate_webhook_url("https://10.0.0.1/webhook")

    with pytest.raises(ValueError, match="SSRF"):
        validate_webhook_url("https://172.16.0.5/webhook")

    with pytest.raises(ValueError, match="SSRF"):
        validate_webhook_url("https://192.168.1.100/webhook")

    # Link-local / Cloud Metadata (169.254.169.254)
    with pytest.raises(ValueError, match="SSRF"):
        validate_webhook_url("https://169.254.169.254/latest/meta-data")

    # Internal cloud metadata domains
    with pytest.raises(ValueError, match="SSRF"):
        validate_webhook_url("https://metadata.google.internal/computeMetadata/v1")

    # Private internal domain suffixes
    with pytest.raises(ValueError, match="SSRF"):
        validate_webhook_url("https://corpservice.local/webhook")

    with pytest.raises(ValueError, match="SSRF"):
        validate_webhook_url("https://database.internal/webhook")


def test_validate_webhook_url_allows_valid_public_https():
    """Legitimate public HTTPS webhooks must pass validation."""
    validate_webhook_url("https://istrac.isro.gov.in/api/v1/netra/alerts")
    validate_webhook_url("https://webhook.site/d2b56e87-a2f2-491c-b715-f55a1e204c32")


# ---------------------------------------------------------------------------
# Telegram, Webhook, and SMTP Dispatch Tests
# ---------------------------------------------------------------------------

def test_telegram_dispatch_never_logs_token(caplog):
    """Verifies that Telegram Bot Token is never exposed in log outputs."""
    token = "SECRET_BOT_TOKEN_999888"
    chat_id = "@test_alerts"

    with patch("httpx.Client.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        with caplog.at_level("INFO"):
            res = send_telegram_alert(chat_id=chat_id, message="Test collision alert", bot_token=token)
            assert res is True

    # Token must NEVER appear in logs
    assert token not in caplog.text
    assert "***MASKED***" in caplog.text
    # Verify post payload
    mock_post.assert_called_once()
    assert mock_post.call_args[1]["json"]["chat_id"] == chat_id


def test_webhook_dispatch_5s_timeout():
    """Verifies that webhook requests use a 5-second timeout."""
    url = "https://istrac.isro.gov.in/api/v1/netra/alerts"
    payload = {"event": "TEST_ALERT"}

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = MagicMock(status_code=200)
        mock_client_cls.return_value = mock_client

        res = send_webhook_alert(url=url, payload=payload, timeout=5.0)
        assert res is True
        mock_client_cls.assert_called_with(timeout=5.0)


def test_email_dispatch_via_smtp():
    """Verifies that email alerts are sent via smtplib with correct parameters."""
    env = {
        "SMTP_HOST": "smtp.isro.gov.in",
        "SMTP_PORT": "587",
        "SMTP_USER": "netra-alert",
        "SMTP_PASSWORD": "netra-password",
        "SMTP_FROM": "alerts@isro.gov.in",
        "SMTP_TLS": "true",
    }
    with patch.dict(os.environ, env):
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_server.__enter__.return_value = mock_server
            mock_smtp_cls.return_value = mock_server

            res = send_email_alert(
                to_email="operator@istrac.isro.gov.in",
                subject="Critical Collision Warning",
                message_body="Conjunction detected within 250m.",
            )
            assert res is True
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("netra-alert", "netra-password")
            mock_server.sendmail.assert_called_once()


# ---------------------------------------------------------------------------
# Screening Alert Pipeline & Deduplication Tests
# ---------------------------------------------------------------------------

@pytest.fixture
def memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Seed an Indian satellite
    sat1 = SatelliteModel(
        id="43111",
        norad_id=43111,
        name="CARTOSAT-2F",
        intl_designator="2018-004A",
        type="PAYLOAD",
        regime="LEO",
        is_indian=True,
        is_watchlist=True,
        owner_country="India (ISRO)",
        apogee_km=512.0,
        perigee_km=498.0,
        altitude_km=505.0,
        inclination_deg=97.5,
        period_min=94.7,
        velocity_km_s=7.61,
        tle_epoch="2026-10-10T06:12:00.000Z",
        tle_line1="1 43111U 18004A   26283.25833333  .00002154  00000+0  10425-3 0  9993",
        tle_line2="2 43111  97.5214 240.1142 0010412 112.5412 247.6214 15.20145212412854",
    )
    sat2 = SatelliteModel(
        id="34120",
        norad_id=34120,
        name="COSMOS 2251 DEB",
        intl_designator="1993-036AG",
        type="DEBRIS",
        regime="LEO",
        is_indian=False,
        is_watchlist=False,
        owner_country="Russia",
        apogee_km=595.0,
        perigee_km=565.0,
        altitude_km=578.0,
        inclination_deg=74.0,
        period_min=96.2,
        velocity_km_s=7.57,
        tle_epoch="2026-10-10T05:30:00.000Z",
        tle_line1="1 34120U 93036AG  26283.22916667  .00002814  00000+0  14120-3 0  9998",
        tle_line2="2 34120  74.0412 110.4120 0022140 215.1240 144.8912 14.96145212451240",
    )
    db.add(sat1)
    db.add(sat2)

    # Seed WatchlistItem
    item = WatchlistItem(
        id="43111",
        norad_id=43111,
        name="CARTOSAT-2F",
        regime="LEO",
        custom_pc_threshold=1.0e-4,
        custom_miss_distance_km=1.0,
        added_at="2026-10-10T00:00:00Z",
        active=True,
    )
    db.add(item)

    # Seed AlertSettings
    settings = AlertSettings(
        id=1,
        default_pc_threshold=1.0e-4,
        default_miss_distance_km=1.0,
        notify_email=False,
        email_address="ops@isro.gov.in",
        notify_telegram=False,
        telegram_chat_id="@netra_alerts",
        notify_istrac_webhook=True,
        webhook_url="https://istrac.isro.gov.in/api/v1/netra/alerts",
    )
    db.add(settings)
    db.commit()

    yield db
    db.close()


def test_process_screening_alerts_dispatches_and_deduplicates(memory_db):
    """
    Verifies that:
    1. Critical conjunctions exceeding threshold trigger alerts.
    2. Sub-threshold conjunctions are skipped.
    3. Running screening again does NOT send duplicates for the same conjunction ID.
    """
    db = memory_db

    # Conjunction 1: Exceeds threshold (miss = 0.284 km < 1.0 km, Pc = 6.84e-4 > 1e-4)
    conj1 = MagicMock(
        id="CONJ-TEST-EXCEED",
        primary_sat_id="43111",
        secondary_sat_id="34120",
        tca_utc="2026-10-11T12:00:00Z",
        miss_distance_km=0.284,
        calibrated_probability=6.84e-4,
        risk_level="CRITICAL",
        recommended_action="MANEUVER_RECOMMENDED",
    )
    conj1.primary_sat.name = "CARTOSAT-2F"
    conj1.primary_sat.norad_id = 43111
    conj1.secondary_sat.name = "COSMOS 2251 DEB"

    # Conjunction 2: Safe (miss = 12.5 km > 1.0 km, Pc = 1.0e-7 < 1e-4)
    conj2 = MagicMock(
        id="CONJ-TEST-SAFE",
        primary_sat_id="43111",
        secondary_sat_id="34120",
        tca_utc="2026-10-12T12:00:00Z",
        miss_distance_km=12.5,
        calibrated_probability=1.0e-7,
        risk_level="NOMINAL",
        recommended_action="WAIT_MONITOR",
    )
    conj2.primary_sat.name = "CARTOSAT-2F"
    conj2.primary_sat.norad_id = 43111
    conj2.secondary_sat.name = "COSMOS 2251 DEB"

    with patch("services.notifier.send_webhook_alert", return_value=True) as mock_webhook:
        # First screening run
        dispatched_1 = process_screening_alerts(db, [conj1, conj2])

        # conj1 exceeded thresholds and was alerted; conj2 was skipped
        assert dispatched_1 == ["CONJ-TEST-EXCEED"]
        mock_webhook.assert_called_once()
        assert mock_webhook.call_args[0][1]["conjunctionId"] == "CONJ-TEST-EXCEED"

        # Verify sent alert record created in database
        sent = db.scalars(select(SentAlert).where(SentAlert.conjunction_id == "CONJ-TEST-EXCEED")).first()
        assert sent is not None
        assert "WEBHOOK" in sent.channels_sent

        mock_webhook.reset_mock()

        # Second screening run with the same conjunctions (e.g. background job re-run)
        dispatched_2 = process_screening_alerts(db, [conj1, conj2])

        # Deduplication check: NO duplicate alerts sent for previously notified conjunction
        assert dispatched_2 == []
        mock_webhook.assert_not_called()
