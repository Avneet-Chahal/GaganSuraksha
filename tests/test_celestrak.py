import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import httpx
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import SessionLocal, Base, engine
from backend.models.db_models import SatelliteModel, IngestionStatusModel
from services.celestrak import (
    compute_tle_checksum,
    validate_tle_record,
    derive_orbital_parameters,
    parse_celestrak_tle_stream,
    fetch_with_retry,
    refresh_celestrak_data,
    RateLimitError,
)

# Valid test TLEs with mathematically correct modulo-10 checksums
VALID_L1_43111 = "1 43111U 18004A   26100.25833333  .00002154  00000-0  10425-3 0  9999"
VALID_L2_43111 = "2 43111  97.5214 240.1142 0010412 112.5412 247.6214 15.20145212412857"

VALID_L1_DEBRIS = "1 33749U 93061AC  26100.12345678  .00012345  00000-0  12345-3 0  9993"
VALID_L2_DEBRIS = "2 33749  74.0123 120.4567 0123456  60.1234 300.5678 14.50123456123452"


@pytest.fixture
def db_session():
    """Provides a transactional database session for tests."""
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_tle_checksum_calculation():
    """Verifies modulo-10 checksum calculation according to standard TLE rules."""
    # Line 1: Checksum is index 68 ('9')
    assert compute_tle_checksum(VALID_L1_43111) == 9
    # Line 2: Checksum is index 68 ('7')
    assert compute_tle_checksum(VALID_L2_43111) == 7

    # Verify line with minus signs
    l1_minus = "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927"
    assert compute_tle_checksum(l1_minus) == 7

    # Short line
    assert compute_tle_checksum("1 25544U") == -1


def test_validate_tle_record_valid():
    """Verifies that a well-formed TLE passes validation and initializes SGP4 Satrec."""
    is_valid, reason, satrec = validate_tle_record(VALID_L1_43111, VALID_L2_43111)
    assert is_valid is True
    assert reason is None
    assert satrec is not None
    assert satrec.error == 0


def test_validate_tle_record_length_mismatch():
    """Verifies rejection when line length is not 69 characters."""
    # Line 1 too short
    is_valid, reason, satrec = validate_tle_record(VALID_L1_43111[:60], VALID_L2_43111)
    assert is_valid is False
    assert "Line 1 length" in reason

    # Line 2 too long
    is_valid, reason, satrec = validate_tle_record(VALID_L1_43111, VALID_L2_43111 + "0")
    assert is_valid is False
    assert "Line 2 length" in reason


def test_validate_tle_record_line_number_mismatch():
    """Verifies rejection when lines do not begin with '1 ' and '2 '."""
    bad_l1 = "X" + VALID_L1_43111[1:]
    is_valid, reason, _ = validate_tle_record(bad_l1, VALID_L2_43111)
    assert is_valid is False
    assert "Line 1 does not start with '1 '" in reason

    bad_l2 = "1" + VALID_L2_43111[1:]
    is_valid, reason, _ = validate_tle_record(VALID_L1_43111, bad_l2)
    assert is_valid is False
    assert "Line 2 does not start with '2 '" in reason


def test_validate_tle_record_checksum_tampered():
    """Verifies rejection when checksum digit does not match modulo-10 sum."""
    # Change checksum digit '9' to '2'
    tampered_l1 = VALID_L1_43111[:68] + "2"
    is_valid, reason, _ = validate_tle_record(tampered_l1, VALID_L2_43111)
    assert is_valid is False
    assert "checksum mismatch" in reason


def test_derive_orbital_parameters():
    """Verifies that orbital parameters (apogee, perigee, inclination, period, regime) are derived correctly."""
    _, _, satrec = validate_tle_record(VALID_L1_43111, VALID_L2_43111)
    derived = derive_orbital_parameters(satrec, VALID_L1_43111)

    assert "apogee_km" in derived
    assert "perigee_km" in derived
    assert "altitude_km" in derived
    assert "inclination_deg" in derived
    assert "period_min" in derived
    assert "velocity_km_s" in derived
    assert "regime" in derived
    assert "tle_epoch" in derived

    # Cartosat-2F is in LEO
    assert derived["regime"] == "LEO"
    assert derived["altitude_km"] < 2000.0
    assert 90.0 < derived["period_min"] < 110.0
    assert 90.0 < derived["inclination_deg"] < 105.0
    assert 7.0 < derived["velocity_km_s"] < 8.0


def test_parse_celestrak_tle_stream_formats():
    """Verifies parsing of 3-line format (with name) and 2-line format."""
    # 3-line format
    sample_3line = f"CARTOSAT-2F\n{VALID_L1_43111}\n{VALID_L2_43111}\n"
    records = parse_celestrak_tle_stream(sample_3line)
    assert len(records) == 1
    assert records[0][0] == "CARTOSAT-2F"
    assert records[0][1] == VALID_L1_43111
    assert records[0][2] == VALID_L2_43111

    # 3-line format with '0 ' prefix
    sample_0prefix = f"0 CARTOSAT-2F\n{VALID_L1_43111}\n{VALID_L2_43111}\n"
    records_prefix = parse_celestrak_tle_stream(sample_0prefix)
    assert len(records_prefix) == 1
    assert records_prefix[0][0] == "CARTOSAT-2F"

    # 2-line format (no name header)
    sample_2line = f"{VALID_L1_43111}\n{VALID_L2_43111}\n"
    records_2line = parse_celestrak_tle_stream(sample_2line)
    assert len(records_2line) == 1
    assert records_2line[0][0] is None
    assert records_2line[0][1] == VALID_L1_43111


def test_fetch_with_retry_rate_limit_429():
    """Verifies that HTTP 429 raises RateLimitError without retrying indefinitely."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_client.get.return_value = mock_resp

    with pytest.raises(RateLimitError):
        fetch_with_retry(mock_client, "https://celestrak.org/api", params={})


def test_fetch_with_retry_timeout_and_retries():
    """Verifies that timeout triggers retries up to max_retries."""
    mock_client = MagicMock()
    mock_client.get.side_effect = httpx.TimeoutException("Read timed out")

    with pytest.raises(httpx.TimeoutException):
        fetch_with_retry(mock_client, "https://celestrak.org/api", params={}, max_retries=2, initial_backoff=0.01)

    assert mock_client.get.call_count == 3  # initial + 2 retries


def test_refresh_celestrak_success_mocked(db_session):
    """
    Simulates a successful CelesTrak response:
    - Upserts satellite records into SatelliteModel marked data_source='CELESTRAK'.
    - Updates ingestion_status table to 'ONLINE'.
    """
    mock_client = MagicMock()

    def mock_get(url, params=None):
        resp = MagicMock()
        resp.status_code = 200
        if "CATNR" in (params or {}):
            resp.text = f"CARTOSAT-2F\n{VALID_L1_43111}\n{VALID_L2_43111}\n"
        else:
            resp.text = f"COSMOS-2251-DEB\n{VALID_L1_DEBRIS}\n{VALID_L2_DEBRIS}\n"
        return resp

    mock_client.get.side_effect = mock_get

    success, msg = refresh_celestrak_data(db_session, force=True, client=mock_client)
    assert success is True
    assert "Successfully ingested" in msg

    # Verify database satellite row
    sat = db_session.query(SatelliteModel).filter(SatelliteModel.norad_id == 43111).first()
    assert sat is not None
    assert sat.data_source == "CELESTRAK"
    assert sat.name == "CARTOSAT-2F"

    # Verify debris row
    deb = db_session.query(SatelliteModel).filter(SatelliteModel.norad_id == 33749).first()
    assert deb is not None
    assert deb.data_source == "CELESTRAK"
    assert deb.type == "DEBRIS"

    # Verify ingestion status row
    status = db_session.query(IngestionStatusModel).filter(IngestionStatusModel.id == 1).first()
    assert status is not None
    assert status.status == "ONLINE"
    assert status.record_count >= 2
    assert status.error_message is None


def test_refresh_celestrak_malformed_tle_skipped(db_session):
    """Verifies that malformed TLE lines are skipped and valid ones are saved."""
    mock_client = MagicMock()

    bad_checksum_l1 = VALID_L1_43111[:68] + "0"
    mock_body = f"BAD-TLE\n{bad_checksum_l1}\n{VALID_L2_43111}\nGOOD-DEB\n{VALID_L1_DEBRIS}\n{VALID_L2_DEBRIS}\n"

    def mock_get(url, params=None):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = mock_body
        return resp

    mock_client.get.side_effect = mock_get

    success, msg = refresh_celestrak_data(db_session, force=True, client=mock_client)
    assert success is True

    # Bad record should be skipped; good record 33749 should be ingested
    deb = db_session.query(SatelliteModel).filter(SatelliteModel.norad_id == 33749).first()
    assert deb is not None
    assert deb.data_source == "CELESTRAK"


def test_refresh_celestrak_timeout_marks_degraded(db_session):
    """Verifies that on network timeout, ingestion_status is marked DEGRADED without throwing unhandled error."""
    mock_client = MagicMock()
    mock_client.get.side_effect = httpx.TimeoutException("Connection timed out")

    success, msg = refresh_celestrak_data(db_session, force=True, client=mock_client)
    assert success is False
    assert "failed" in msg.lower()

    status = db_session.query(IngestionStatusModel).filter(IngestionStatusModel.id == 1).first()
    assert status is not None
    assert status.status == "DEGRADED"
    assert status.error_message is not None


def test_refresh_celestrak_rate_limit_marks_degraded(db_session):
    """Verifies that on HTTP 429 rate limit, ingestion_status is marked DEGRADED."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_client.get.return_value = mock_resp

    success, msg = refresh_celestrak_data(db_session, force=True, client=mock_client)
    assert success is False

    status = db_session.query(IngestionStatusModel).filter(IngestionStatusModel.id == 1).first()
    assert status is not None
    assert status.status == "DEGRADED"
    assert "429" in status.error_message


def test_refresh_celestrak_2hour_cache_window(db_session):
    """Verifies that CelesTrak is not polled within 2 hours of a previous success unless force=True."""
    now_utc = datetime.now(timezone.utc)
    recent_time = (now_utc - timedelta(minutes=30)).isoformat()

    status = db_session.query(IngestionStatusModel).filter(IngestionStatusModel.id == 1).first()
    if not status:
        status = IngestionStatusModel(id=1)
        db_session.add(status)
    status.last_success_utc = recent_time
    status.status = "ONLINE"
    db_session.commit()

    mock_client = MagicMock()

    # Call with force=False -> should be skipped by cache
    success, msg = refresh_celestrak_data(db_session, force=False, client=mock_client)
    assert success is True
    assert "cache is fresh" in msg.lower()
    assert mock_client.get.call_count == 0  # No HTTP requests made!


def test_sources_endpoint_reports_honest_status():
    """
    Verifies that GET /api/sources reports honest status:
    - Never returns ONLINE if all satellites are synthetic or fetch is degraded.
    - Returns ONLINE only after a successful CelesTrak fetch with real records.
    """
    with TestClient(app) as client:
        # Step 1: Simulate degraded status
        db = SessionLocal()
        status = db.query(IngestionStatusModel).filter(IngestionStatusModel.id == 1).first()
        if not status:
            status = IngestionStatusModel(id=1)
            db.add(status)
        status.status = "DEGRADED"
        status.error_message = "Simulated upstream 503 error"
        db.commit()
        db.close()

        res_degraded = client.get("/api/sources")
        assert res_degraded.status_code == 200
        sources = res_degraded.json()
        celestrak = next(s for s in sources if s["name"] == "CelesTrak TLE Ingestion")
        assert celestrak["status"] == "DEGRADED"

        # Step 2: Simulate standby when data is synthetic
        db = SessionLocal()
        status = db.query(IngestionStatusModel).filter(IngestionStatusModel.id == 1).first()
        status.status = "STANDBY"
        status.error_message = None
        # Ensure satellites are marked SYNTHETIC
        for sat in db.query(SatelliteModel).all():
            sat.data_source = "SYNTHETIC"
        db.commit()
        db.close()

        res_standby = client.get("/api/sources")
        assert res_standby.status_code == 200
        sources_standby = res_standby.json()
        celestrak_standby = next(s for s in sources_standby if s["name"] == "CelesTrak TLE Ingestion")
        assert celestrak_standby["status"] in ["STANDBY", "DEGRADED"]
        assert celestrak_standby["status"] != "ONLINE"
