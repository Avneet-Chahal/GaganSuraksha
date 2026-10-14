import math
from datetime import datetime, timezone
import numpy as np
import pytest
from sgp4.api import Satrec

from backend.services.screening import (
    check_altitude_overlap,
    refine_tca,
    decompose_rtn,
    compute_foster_2d_pc,
    classify_risk,
    compute_state_vectors_at_timestamp,
)


def test_coarse_altitude_overlap():
    """Verifies that non-intersecting orbits are rejected and intersecting orbits pass."""
    # LEO Cartosat (perigee 498, apogee 512) vs GEO GSAT-30 (perigee 35780, apogee 35794)
    assert check_altitude_overlap(498.0, 512.0, 35780.0, 35794.0, buffer_km=20.0) is False

    # LEO Cartosat (perigee 498, apogee 512) vs SL-8 Debris (perigee 485, apogee 520)
    assert check_altitude_overlap(498.0, 512.0, 485.0, 520.0, buffer_km=20.0) is True

    # Boundary case: separation exactly 40 km (20 km buffer on each side touches)
    assert check_altitude_overlap(400.0, 460.0, 500.0, 550.0, buffer_km=20.0) is True
    assert check_altitude_overlap(400.0, 450.0, 500.0, 550.0, buffer_km=20.0) is False


def test_rtn_decomposition():
    """
    Verifies RTN frame decomposition of miss distance vector against known canonical geometry.
    Primary at (7000, 0, 0) moving in +Y direction (0, 7.5, 0).
    R_hat = [1, 0, 0], T_hat = [0, 1, 0], N_hat = [0, 0, 1].
    """
    r1 = np.array([7000.0, 0.0, 0.0])
    v1 = np.array([0.0, 7.5, 0.0])

    # Secondary offset by 0.35 km Radial, 0.85 km In-Track, 0.45 km Cross-Track
    r2 = np.array([7000.35, 0.85, 0.45])
    v2 = np.array([0.0, -7.5, 0.0])

    miss_r, miss_t, miss_n, total_miss, rel_vel = decompose_rtn(r1, v1, r2, v2)

    assert pytest.approx(miss_r, abs=1e-5) == 0.35
    assert pytest.approx(miss_t, abs=1e-5) == 0.85
    assert pytest.approx(miss_n, abs=1e-5) == 0.45

    expected_total = math.sqrt(0.35**2 + 0.85**2 + 0.45**2)
    assert pytest.approx(total_miss, abs=1e-5) == expected_total
    assert pytest.approx(rel_vel, abs=1e-5) == 15.0


def test_pc_monotonic_in_miss_distance():
    """
    Verifies that Foster 2D collision probability strictly decreases
    as miss distance increases.
    """
    primary_sigmas = (25.0, 80.0, 30.0)   # meters
    secondary_sigmas = (50.0, 180.0, 60.0)

    # Series of increasing radial and in-track miss distances
    distances_km = [0.02, 0.05, 0.10, 0.20, 0.40, 0.80, 1.50, 3.00]
    pcs: list[float] = []

    for d in distances_km:
        pc = compute_foster_2d_pc(
            radial_miss_km=d * 0.4,
            in_track_miss_km=d * 0.8,
            cross_track_miss_km=d * 0.2,
            primary_sigmas_m=primary_sigmas,
            secondary_sigmas_m=secondary_sigmas,
            hard_body_radius_m=10.0,
        )
        pcs.append(pc)

    # Verify strict monotonicity: Pc(d_k) > Pc(d_{k+1})
    for i in range(len(pcs) - 1):
        assert pcs[i] > pcs[i + 1], f"Monotonicity failed between step {i} (d={distances_km[i]}, Pc={pcs[i]}) and step {i+1} (d={distances_km[i+1]}, Pc={pcs[i+1]})"


def test_tca_crossing_synthetic_orbits():
    """
    Verifies TCA refinement for two synthetic circular orbits that cross.
    Orbit 1: Inclination 45 deg, RAAN 0 deg.
    Orbit 2: Inclination 45 deg, RAAN 180 deg.
    Both in circular LEO at ~500 km altitude (15.0 revs/day).
    """
    line1_a = "1 99001U 20001A   26283.00000000  .00000000  00000+0  00000+0 0  9991"
    line2_a = "2 99001  45.0000   0.0000 0001000   0.0000   0.0000 15.00000000000018"

    line1_b = "1 99002U 20002A   26283.00000000  .00000000  00000+0  00000+0 0  9992"
    line2_b = "2 99002  45.0000 180.0000 0001000   0.0000 180.0000 15.00000000000019"

    sat_a = Satrec.twoline2rv(line1_a, line2_a)
    sat_b = Satrec.twoline2rv(line1_b, line2_b)

    # Search window around epoch (epoch is Day 283 of 2026 = 2026-10-10 00:00:00 UTC)
    start_ts = datetime(2026, 10, 10, 0, 0, 0, tzinfo=timezone.utc).timestamp()

    # Step through first orbit period (approx 96 min = 5760 sec) to find approximate crossing
    best_step_ts = start_ts
    min_coarse_dist = float("inf")

    for t_offset in range(0, 5760, 60):
        d, _, _, _, _ = compute_state_vectors_at_timestamp(sat_a, sat_b, start_ts + t_offset)
        if d < min_coarse_dist:
            min_coarse_dist = d
            best_step_ts = start_ts + t_offset

    # Refine the local minimum to sub-second TCA
    refined_tca, miss_dist, r1, v1, r2, v2 = refine_tca(
        sat_a, sat_b, best_step_ts, step_seconds=60.0
    )

    assert miss_dist < min_coarse_dist or pytest.approx(miss_dist) == min_coarse_dist

    # Verify that refined TCA is a true local minimum of distance
    dist_before, _, _, _, _ = compute_state_vectors_at_timestamp(sat_a, sat_b, refined_tca - 2.0)
    dist_after, _, _, _, _ = compute_state_vectors_at_timestamp(sat_a, sat_b, refined_tca + 2.0)

    assert dist_before > miss_dist
    assert dist_after > miss_dist


def test_risk_classification():
    """Verifies CRITICAL, WARNING, and NOMINAL classification logic."""
    # Critical: Pc >= 1e-4 or miss < 1 km
    assert classify_risk(pc=2.5e-3, miss_distance_km=0.28) == ("CRITICAL", "MANEUVER_RECOMMENDED")
    assert classify_risk(pc=5.0e-5, miss_distance_km=0.80) == ("CRITICAL", "MANEUVER_RECOMMENDED")

    # Warning: Pc >= 1e-5 or miss < 5 km
    assert classify_risk(pc=2.0e-5, miss_distance_km=3.2) == ("WARNING", "WAIT_MONITOR")
    assert classify_risk(pc=1.0e-6, miss_distance_km=2.4) == ("WARNING", "WAIT_MONITOR")

    # Nominal: Pc < 1e-5 and miss >= 5 km
    assert classify_risk(pc=1.0e-7, miss_distance_km=8.5) == ("NOMINAL", "WAIT_MONITOR")


def test_services_screening_proxy_module():
    """Verifies that services.screening can be imported and matches backend.services.screening."""
    import services.screening as s_screen
    import backend.services.screening as b_screen

    assert s_screen.check_altitude_overlap is b_screen.check_altitude_overlap
    assert s_screen.decompose_rtn is b_screen.decompose_rtn
    assert s_screen.compute_foster_2d_pc is b_screen.compute_foster_2d_pc


def test_conjunction_endpoints_sorted_and_404():
    """Verifies GET /api/conjunctions is sorted by TCA and /api/conjunctions/{id} returns 404 for unknown."""
    from fastapi.testclient import TestClient
    from backend.main import app

    with TestClient(app) as client:
        # Ensure conjunctions are screened synchronously
        res_sync = client.post("/api/conjunctions/screen?wait=true")
        assert res_sync.status_code == 202
        assert res_sync.json()["status"] == "COMPLETED"

        # 1. Sorted by TCA
        res = client.get("/api/conjunctions")
        assert res.status_code == 200
        events = res.json()
        assert len(events) >= 2
        for i in range(len(events) - 1):
            assert events[i]["tcaMs"] <= events[i + 1]["tcaMs"]

        # 2. 404 for unknown ID
        res_404 = client.get("/api/conjunctions/CONJ-UNKNOWN-999")
        assert res_404.status_code == 404
        assert "not found" in res_404.json()["detail"].lower()

        # 3. Background screening trigger endpoint
        res_screen = client.post("/api/conjunctions/screen")
        assert res_screen.status_code == 202
        assert res_screen.json()["status"] == "QUEUED"


def test_screening_stable_ids_and_alert_deduplication():
    """
    Verifies that running screening twice on the same data produces
    identical conjunction IDs and dispatches alerts only once.
    """
    from unittest.mock import patch
    from backend.database import SessionLocal
    from backend.services.screening import screen_all_watchlist_pairs
    from backend.models.db_models import SentAlert, AlertSettings, WatchlistItem
    from sqlalchemy import select

    db = SessionLocal()
    try:
        # Clear sent alerts to start from a clean state for this test
        db.query(SentAlert).delete()
        # Set miss threshold on alert settings and watchlist items to 50 km so computed conjunctions trigger alerts
        alert_setting = db.scalars(select(AlertSettings).where(AlertSettings.id == 1)).first()
        orig_threshold = alert_setting.default_miss_distance_km if alert_setting else 1.0
        if alert_setting:
            alert_setting.default_miss_distance_km = 50.0

        watchlist_items = db.scalars(select(WatchlistItem)).all()
        orig_watchlist_thresholds = {item.id: item.custom_miss_distance_km for item in watchlist_items}
        for item in watchlist_items:
            item.custom_miss_distance_km = 50.0
        db.commit()

        fixed_now = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)

        with patch("services.notifier.send_webhook_alert", return_value=True), \
             patch("services.notifier.send_telegram_alert", return_value=True), \
             patch("services.notifier.send_email_alert", return_value=True):

            # Run 1
            results_run1 = screen_all_watchlist_pairs(db, start_dt=fixed_now)
            ids_run1 = [c.id for c in results_run1]
            assert len(ids_run1) > 0

            # Conjunction IDs match the required stable format CONJ-<primaryNorad>-<secondaryNorad>-<YYYYMMDDHHMM>
            for conj_id in ids_run1:
                assert conj_id.startswith("CONJ-")
                parts = conj_id.split("-")
                assert len(parts) >= 4
                # Validate NORAD IDs are numeric
                assert parts[1].isdigit()
                assert parts[2].isdigit()
                # Validate timestamp format YYYYMMDDHHMM
                assert len(parts[3][:12]) == 12 and parts[3][:12].isdigit()

            # Check dispatched alerts count after Run 1
            sent_after_run1 = db.scalars(select(SentAlert.conjunction_id)).all()
            assert len(sent_after_run1) > 0

            # Run 2 on the exact same dataset and screening window
            results_run2 = screen_all_watchlist_pairs(db, start_dt=fixed_now)
            ids_run2 = [c.id for c in results_run2]

            # 1. Produced IDs must be strictly identical
            assert ids_run1 == ids_run2

            # 2. Sent alerts count must NOT increase (alerted only once)
            sent_after_run2 = db.scalars(select(SentAlert.conjunction_id)).all()
            assert len(sent_after_run1) == len(sent_after_run2)
            assert set(sent_after_run1) == set(sent_after_run2)

        # Restore original thresholds
        if alert_setting:
            alert_setting.default_miss_distance_km = orig_threshold
        for item in db.scalars(select(WatchlistItem)).all():
            if item.id in orig_watchlist_thresholds:
                item.custom_miss_distance_km = orig_watchlist_thresholds[item.id]
        db.commit()
    finally:
        db.close()


def test_returned_conjunctions_sgp4_separation_at_tca():
    """
    Verifies that every returned conjunction has an SGP4-computed separation
    at its TCA equal to missDistanceKm within 0.05 km.
    """
    from backend.database import SessionLocal
    from backend.models.db_models import ConjunctionModel
    from backend.services.screening import compute_state_vectors_at_timestamp
    from sqlalchemy import select

    db = SessionLocal()
    try:
        conjunctions = db.scalars(select(ConjunctionModel)).all()
        assert len(conjunctions) > 0

        for conj in conjunctions:
            primary_sat = conj.primary_sat
            secondary_sat = conj.secondary_sat
            assert primary_sat is not None
            assert secondary_sat is not None

            # Propagate both satellites at TCA using SGP4
            satrec_p = Satrec.twoline2rv(primary_sat.tle_line1.strip(), primary_sat.tle_line2.strip())
            satrec_s = Satrec.twoline2rv(secondary_sat.tle_line1.strip(), secondary_sat.tle_line2.strip())

            tca_ts = conj.tca_ms / 1000.0
            dist_km, _, _, _, _ = compute_state_vectors_at_timestamp(satrec_p, satrec_s, tca_ts)

            # Separation at TCA must match missDistanceKm within 0.05 km
            assert abs(dist_km - conj.miss_distance_km) <= 0.05, (
                f"Conjunction {conj.id} separation at TCA ({dist_km:.4f} km) deviates "
                f"from stored missDistanceKm ({conj.miss_distance_km:.4f} km) by more than 0.05 km"
            )
    finally:
        db.close()

