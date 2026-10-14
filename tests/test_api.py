import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import Base, engine, SessionLocal
from backend.seed_data import seed_database


@pytest.fixture(scope="session", autouse=True)
def init_test_db():
    """Initializes tables, seeds test data, and computes real conjunctions."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed_database(db)
    from backend.services.screening import screen_all_watchlist_pairs
    screen_all_watchlist_pairs(db)
    db.close()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_check(client: TestClient):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ONLINE", "system": "Gagan Suraksha Core API"}


def test_get_satellites_camel_case(client: TestClient):
    """Verifies that satellites endpoint returns camelCase keys matching SatelliteRecord."""
    res = client.get("/api/satellites")
    assert res.status_code == 200
    satellites = res.json()
    assert isinstance(satellites, list)
    assert len(satellites) > 0

    first_sat = satellites[0]
    # Check camelCase fields required by frontend SatelliteRecord interface
    assert "noradId" in first_sat
    assert "intlDesignator" in first_sat
    assert "isIndian" in first_sat
    assert "isWatchlist" in first_sat
    assert "apogeeKm" in first_sat
    assert "perigeeKm" in first_sat
    assert "altitudeKm" in first_sat
    assert "inclinationDeg" in first_sat
    assert "periodMin" in first_sat
    assert "velocityKmS" in first_sat
    assert "tleEpoch" in first_sat
    assert "tleLine1" in first_sat
    assert "tleLine2" in first_sat


def test_get_satellites_filters(client: TestClient):
    """Tests regime and nationality filtering."""
    res_leo = client.get("/api/satellites?regime=LEO")
    assert res_leo.status_code == 200
    for sat in res_leo.json():
        assert sat["regime"] == "LEO"

    res_indian = client.get("/api/satellites?is_indian=true")
    assert res_indian.status_code == 200
    for sat in res_indian.json():
        assert sat["isIndian"] is True


def test_get_trajectories(client: TestClient):
    """Verifies trajectory generation for given satellite IDs."""
    start = "2026-10-10T12:00:00Z"
    end = "2026-10-10T12:30:00Z"
    res = client.get(f"/api/trajectories?ids=43111&start={start}&end={end}&step=60")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 1

    traj = data[0]
    assert traj["satelliteId"] == "43111"
    assert traj["stepSeconds"] == 60
    assert len(traj["points"]) > 0

    point = traj["points"][0]
    assert "timeMs" in point
    assert "x" in point
    assert "y" in point
    assert "z" in point
    assert "vx" in point
    assert "vy" in point
    assert "vz" in point
    assert isinstance(point["timeMs"], int)
    assert isinstance(point["x"], float)
    assert isinstance(point["vx"], float)


def test_get_trajectories_more_than_20_ids(client: TestClient):
    """Verifies that requesting more than 20 IDs returns 422 with a clear message."""
    ids = ",".join(str(i) for i in range(1, 23))  # 22 IDs
    res = client.get(f"/api/trajectories?ids={ids}&start=2026-10-10T12:00:00Z&end=2026-10-10T13:00:00Z&step=120")
    assert res.status_code == 422
    assert "Maximum of 20 satellite IDs" in res.json()["detail"]


def test_get_trajectories_window_over_7_days(client: TestClient):
    """Verifies that requesting a time window > 7 days returns 422 with a clear message."""
    res = client.get(
        "/api/trajectories?ids=43111&start=2026-10-10T00:00:00Z&end=2026-10-18T00:00:00Z&step=120"  # 8 days
    )
    assert res.status_code == 422
    assert "Time window cannot exceed 7 days" in res.json()["detail"]


def test_get_trajectories_end_before_start(client: TestClient):
    """Verifies that end before start returns 422."""
    res = client.get(
        "/api/trajectories?ids=43111&start=2026-10-10T15:00:00Z&end=2026-10-10T12:00:00Z&step=120"
    )
    assert res.status_code == 422
    assert "End time" in res.json()["detail"]


def test_get_trajectories_points_over_5000(client: TestClient):
    """Verifies that requesting > 5000 points returns 422 with a clear message."""
    # 7 days = 604,800 s. step=60 -> 10,081 points > 5000 points limit
    res = client.get(
        "/api/trajectories?ids=43111&start=2026-10-10T00:00:00Z&end=2026-10-17T00:00:00Z&step=60"
    )
    assert res.status_code == 422
    assert "exceeds maximum limit of 5,000 points" in res.json()["detail"]


def test_get_trajectories_invalid_step(client: TestClient):
    """Verifies that step <= 0 returns 422."""
    res = client.get(
        "/api/trajectories?ids=43111&start=2026-10-10T12:00:00Z&end=2026-10-10T13:00:00Z&step=0"
    )
    assert res.status_code == 422
    assert "Step interval must be greater than 0" in res.json()["detail"]


def test_get_trajectories_unknown_ids(client: TestClient):
    """Verifies that unknown satellite IDs return 404 listing the missing IDs."""
    res = client.get(
        "/api/trajectories?ids=43111,99998,99999&start=2026-10-10T12:00:00Z&end=2026-10-10T13:00:00Z&step=120"
    )
    assert res.status_code == 404
    detail = res.json()["detail"]
    assert "Satellite IDs not found" in detail
    assert "99998" in detail
    assert "99999" in detail



def test_get_conjunctions(client: TestClient):
    """Verifies conjunction list serialization with nested satellites and covariance."""
    res = client.get("/api/conjunctions")
    assert res.status_code == 200
    conjunctions = res.json()
    assert isinstance(conjunctions, list)
    assert len(conjunctions) >= 1

    first_conj = conjunctions[0]
    assert "primarySat" in first_conj
    assert "secondarySat" in first_conj
    assert "tcaUtc" in first_conj
    assert "tcaMs" in first_conj
    assert "missDistanceKm" in first_conj
    assert "radialMissKm" in first_conj
    assert "inTrackMissKm" in first_conj
    assert "crossTrackMissKm" in first_conj
    assert "relativeVelocityKmS" in first_conj
    assert "rawProbability" in first_conj
    assert "calibratedProbability" in first_conj
    assert "riskLevel" in first_conj
    assert "primaryCovariance" in first_conj
    assert "secondaryCovariance" in first_conj

    assert "radialSigmaM" in first_conj["primaryCovariance"]
    assert first_conj["missDistanceKm"] < 50.0


def test_get_conjunctions_risk_filter(client: TestClient):
    """Verifies filtering by ?risk=CRITICAL|WARNING|NOMINAL query parameter."""
    res_all = client.get("/api/conjunctions")
    assert res_all.status_code == 200
    all_events = res_all.json()
    assert len(all_events) > 0

    for test_risk in ["CRITICAL", "WARNING", "NOMINAL"]:
        res_filtered = client.get(f"/api/conjunctions?risk={test_risk}")
        assert res_filtered.status_code == 200
        filtered_events = res_filtered.json()
        for evt in filtered_events:
            assert evt["riskLevel"] == test_risk


def test_get_conjunction_by_id(client: TestClient):
    """Verifies single conjunction lookup using dynamically computed ID."""
    res_list = client.get("/api/conjunctions")
    assert res_list.status_code == 200
    events = res_list.json()
    assert len(events) > 0
    target_id = events[0]["id"]

    res = client.get(f"/api/conjunctions/{target_id}")
    assert res.status_code == 200
    conj = res.json()
    assert conj["id"] == target_id
    assert conj["riskLevel"] in ("CRITICAL", "WARNING", "NOMINAL")


def test_post_maneuver(client: TestClient):
    """Verifies maneuver calculation endpoint with dynamic conjunction ID."""
    res_list = client.get("/api/conjunctions")
    assert res_list.status_code == 200
    events = res_list.json()
    assert len(events) > 0
    target_id = events[0]["id"]

    payload = {
        "conjunctionId": target_id,
        "deltaVMs": 0.45,
        "burnTimeUtc": "2026-10-10T12:00:00Z",
        "direction": "PROGRADE",
        "spacecraftMassKg": 1200.0,
        "ispSeconds": 290.0,
    }
    res = client.post("/api/maneuver", json=payload)
    assert res.status_code == 200
    result = res.json()

    assert result["conjunctionId"] == target_id
    assert "originalMissDistanceKm" in result
    assert "newMissDistanceKm" in result
    assert "originalProbability" in result
    assert "newProbability" in result
    assert "deltaVMs" in result
    assert "fuelCostKg" in result
    assert "status" in result
    assert "summary" in result
    assert "assumptions" in result
    assert result["deltaVMs"] == 0.45
    assert result["fuelCostKg"] > 0


def test_post_maneuver_validation_failures(client: TestClient):
    """Verifies that invalid maneuver parameters return HTTP 422."""
    res_list = client.get("/api/conjunctions")
    assert res_list.status_code == 200
    events = res_list.json()
    target_id = events[0]["id"] if events else "CONJ-TEST"

    base_payload = {
        "conjunctionId": target_id,
        "deltaVMs": 0.45,
        "burnTimeUtc": "2026-10-10T12:00:00Z",
        "direction": "PROGRADE",
        "spacecraftMassKg": 1200.0,
        "ispSeconds": 290.0,
    }

    # Delta-v > 5.0 m/s
    res = client.post("/api/maneuver", json={**base_payload, "deltaVMs": 6.0})
    assert res.status_code == 422

    # Delta-v < 0.0 m/s
    res = client.post("/api/maneuver", json={**base_payload, "deltaVMs": -0.5})
    assert res.status_code == 422

    # Mass <= 0
    res = client.post("/api/maneuver", json={**base_payload, "spacecraftMassKg": 0.0})
    assert res.status_code == 422

    # Isp <= 0
    res = client.post("/api/maneuver", json={**base_payload, "ispSeconds": -5.0})
    assert res.status_code == 422


def test_post_maneuver_unknown_id_404(client: TestClient):
    """Verifies that POST /api/maneuver returns 404 when conjunctionId is unknown."""
    res = client.post(
        "/api/maneuver",
        json={
            "conjunctionId": "CONJ-UNKNOWN-NONEXISTENT",
            "deltaVMs": 0.45,
            "burnTimeUtc": "2026-10-10T12:00:00Z",
            "direction": "PROGRADE",
            "spacecraftMassKg": 1200.0,
            "ispSeconds": 290.0,
        },
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()



def test_get_metrics(client: TestClient):
    """Verifies analytics metrics endpoint with isDemo: true flag for sample data."""
    res = client.get("/api/metrics")
    assert res.status_code == 200
    metrics = res.json()

    assert isinstance(metrics.get("isDemo"), bool)
    assert "dataSource" in metrics
    assert "evaluationPeriod" in metrics
    assert "totalConjunctionsMonitored" in metrics
    assert "unnecessaryManeuversAvoided" in metrics
    assert "fuelSavedKg" in metrics
    assert "falseAlarmReductionRate" in metrics
    assert "falseAlarmsByMonth" in metrics
    assert "reliabilityCurve" in metrics
    assert "positionErrorByHorizon" in metrics

    assert len(metrics["falseAlarmsByMonth"]) > 0
    assert "rawCount" in metrics["falseAlarmsByMonth"][0]
    assert "mlCorrectedCount" in metrics["falseAlarmsByMonth"][0]


def test_get_sources(client: TestClient):
    """Verifies real operational status for CelesTrak ingestion and SGP4 engine."""
    res = client.get("/api/sources")
    assert res.status_code == 200
    sources = res.json()
    assert isinstance(sources, list)
    assert len(sources) == 2

    source_names = [s["name"] for s in sources]
    assert "CelesTrak TLE Ingestion" in source_names
    assert "SGP4 Orbit Propagator" in source_names

    celestrak = next(s for s in sources if s["name"] == "CelesTrak TLE Ingestion")
    # Must report real status (STANDBY / DEGRADED when synthetic, ONLINE only when real data ingested)
    assert celestrak["status"] in ["STANDBY", "DEGRADED", "ONLINE"]
    assert "lastUpdatedUtc" in celestrak
    assert "latencySeconds" in celestrak

    sgp4 = next(s for s in sources if s["name"] == "SGP4 Orbit Propagator")
    assert sgp4["status"] == "ONLINE"
    assert sgp4["recordCount"] > 0
    assert sgp4["latencySeconds"] >= 0



def test_endpoints_without_api_prefix_return_404(client: TestClient):
    """Verifies that endpoints are strictly mounted under /api and unprefixed paths return 404."""
    res_sat = client.get("/satellites")
    assert res_sat.status_code == 404

    res_health = client.get("/health")
    assert res_health.status_code == 404

    res_api_health = client.get("/api/health")
    assert res_api_health.status_code == 200


def test_watchlist_crud_endpoints(client: TestClient):
    """Verifies GET, POST, and DELETE /api/watchlist endpoints with camelCase fields."""
    # 1. GET /api/watchlist
    res = client.get("/api/watchlist")
    assert res.status_code == 200
    watchlist = res.json()
    assert isinstance(watchlist, list)
    assert len(watchlist) > 0

    first = watchlist[0]
    assert "id" in first
    assert "noradId" in first
    assert "name" in first
    assert "regime" in first
    assert "customPcThreshold" in first
    assert "customMissDistanceKm" in first
    assert "addedAt" in first
    assert "active" in first

    # 2. POST /api/watchlist
    new_item = {
        "noradId": 55100,
        "name": "OCEANSAT-3",
        "regime": "LEO",
        "customPcThreshold": 5e-5,
        "customMissDistanceKm": 1.5,
        "active": True,
    }
    res_post = client.post("/api/watchlist", json=new_item)
    assert res_post.status_code == 201
    created = res_post.json()
    assert created["noradId"] == 55100
    assert created["name"] == "OCEANSAT-3"
    assert created["customPcThreshold"] == 5e-5
    assert created["customMissDistanceKm"] == 1.5

    # Verify added item is in watchlist
    res_get_after = client.get("/api/watchlist")
    ids = [item["noradId"] for item in res_get_after.json()]
    assert 55100 in ids

    # 3. DELETE /api/watchlist?id=55100
    res_del = client.delete(f"/api/watchlist/{created['id']}")
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "DELETED"

    # Verify removed
    res_get_final = client.get("/api/watchlist")
    final_ids = [item["noradId"] for item in res_get_final.json()]
    assert 55100 not in final_ids


def test_alert_settings_get_and_put(client: TestClient):
    """Verifies GET and PUT /api/alert-settings endpoints."""
    from backend.models.db_models import AlertSettings

    # Ensure baseline safe defaults for test isolation
    db = SessionLocal()
    st = db.query(AlertSettings).first()
    if st:
        st.notify_email = False
        st.email_address = ""
        st.notify_telegram = False
        st.telegram_chat_id = ""
        st.notify_istrac_webhook = False
        st.webhook_url = ""
        db.commit()
    db.close()

    # 1. GET (Safe defaults: disabled channels, empty credentials and URLs)
    res = client.get("/api/alert-settings")
    assert res.status_code == 200
    settings = res.json()
    assert settings["notifyEmail"] is False
    assert settings["emailAddress"] == ""
    assert settings["notifyTelegram"] is False
    assert settings["telegramChatId"] == ""
    assert settings["notifyIstracWebhook"] is False
    assert settings["webhookUrl"] == ""
    assert "defaultPcThreshold" in settings
    assert "defaultMissDistanceKm" in settings

    # 2. Valid PUT
    update_payload = {
        "defaultPcThreshold": 2.5e-4,
        "defaultMissDistanceKm": 1.25,
        "notifyEmail": True,
        "emailAddress": "alert-center@isro.gov.in",
        "notifyTelegram": True,
        "telegramChatId": "@netra_live",
        "notifyIstracWebhook": True,
        "webhookUrl": "https://istrac.isro.gov.in/api/v1/netra/alerts",
    }
    res_put = client.put("/api/alert-settings", json=update_payload)
    assert res_put.status_code == 200
    updated = res_put.json()
    assert updated["defaultPcThreshold"] == 2.5e-4
    assert updated["defaultMissDistanceKm"] == 1.25
    assert updated["emailAddress"] == "alert-center@isro.gov.in"
    assert updated["telegramChatId"] == "@netra_live"

    # Restore safe defaults after test
    db = SessionLocal()
    st = db.query(AlertSettings).first()
    if st:
        st.notify_email = False
        st.email_address = ""
        st.notify_telegram = False
        st.telegram_chat_id = ""
        st.notify_istrac_webhook = False
        st.webhook_url = ""
        db.commit()
    db.close()


def test_alert_settings_webhook_ssrf_rejection(client: TestClient):
    """Verifies that unsafe webhook URLs and URLs with embedded credentials are rejected with HTTP 422."""
    # Embedded credentials (user:pass@)
    res = client.put("/api/alert-settings", json={"webhookUrl": "https://user:pass@istrac.isro.gov.in/alerts"})
    assert res.status_code == 422
    assert "credentials" in res.json()["detail"].lower()

    # Non-https
    res = client.put("/api/alert-settings", json={"webhookUrl": "http://istrac.isro.gov.in/alerts"})
    assert res.status_code == 422
    assert "SSRF" in res.json()["detail"]

    # Localhost
    res = client.put("/api/alert-settings", json={"webhookUrl": "https://localhost:8000/webhook"})
    assert res.status_code == 422
    assert "SSRF" in res.json()["detail"]

    # Loopback IP
    res = client.put("/api/alert-settings", json={"webhookUrl": "https://127.0.0.1:8000/webhook"})
    assert res.status_code == 422
    assert "SSRF" in res.json()["detail"]

    # Private RFC 1918 IP
    res = client.put("/api/alert-settings", json={"webhookUrl": "https://192.168.1.1/webhook"})
    assert res.status_code == 422
    assert "SSRF" in res.json()["detail"]

    # Link-local cloud metadata
    res = client.put("/api/alert-settings", json={"webhookUrl": "https://169.254.169.254/latest/meta-data"})
    assert res.status_code == 422
    assert "SSRF" in res.json()["detail"]

